import importlib.util
import pathlib
import unittest

import httpx
from httpx import ASGITransport
from httpx import AsyncClient as RealAsyncClient


ROOT = pathlib.Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "ai-service" / "ai_assistant.py"
SPEC = importlib.util.spec_from_file_location("ai_assistant_proxy_test", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.text = "" if payload is None else str(payload)

    @property
    def is_success(self):
        return 200 <= self.status_code < 300

    def json(self):
        return self._payload


class FakeStreamResponse:
    def __init__(self, chunks, status_code=200):
        self._chunks = list(chunks)
        self.status_code = status_code
        self.text = "".join(
            chunk.decode("utf-8", errors="replace") if isinstance(chunk, bytes) else str(chunk)
            for chunk in self._chunks
        )
        self.closed = False

    @property
    def is_success(self):
        return 200 <= self.status_code < 300

    async def aread(self):
        return b"".join(
            chunk if isinstance(chunk, bytes) else str(chunk).encode("utf-8")
            for chunk in self._chunks
        )

    async def aiter_raw(self):
        for chunk in self._chunks:
            yield chunk if isinstance(chunk, bytes) else str(chunk).encode("utf-8")

    async def aclose(self):
        self.closed = True


class FakeAsyncClient:
    def __init__(self, recorder):
        self.recorder = recorder

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url, headers=None, json=None):
        self.recorder["url"] = url
        self.recorder["headers"] = headers or {}
        self.recorder["json"] = json or {}
        return FakeResponse(
            {
                "id": "chatcmpl-test",
                "object": "chat.completion",
                "created": 123,
                "model": json.get("model") or "deepseek-chat",
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": "代理返回内容",
                        },
                        "finish_reason": "stop",
                    }
                ],
            }
        )

    def build_request(self, method, url, headers=None, json=None):
        return {
            "method": method,
            "url": url,
            "headers": headers or {},
            "json": json or {},
        }

    async def send(self, request, stream=False):
        self.recorder["url"] = request["url"]
        self.recorder["headers"] = request["headers"]
        self.recorder["json"] = request["json"]
        self.recorder["stream"] = stream
        return FakeStreamResponse(
            [
                b'data: {"id":"chatcmpl-upstream","object":"chat.completion.chunk","created":123,"model":"deepseek-chat","choices":[{"index":0,"delta":{"role":"assistant"},"finish_reason":null}]}\n\n',
                b'data: {"id":"chatcmpl-upstream","object":"chat.completion.chunk","created":123,"model":"deepseek-chat","choices":[{"index":0,"delta":{"content":"\xe4\xbb\xa3\xe7\x90\x86\xe6\xb5\x81\xe5\xbc\x8f\xe5\x9b\x9e\xe5\xa4\x8d"},"finish_reason":null}]}\n\n',
                b'data: {"id":"chatcmpl-upstream","object":"chat.completion.chunk","created":123,"model":"deepseek-chat","choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}\n\n',
                b"data: [DONE]\n\n",
            ]
        )

    async def aclose(self):
        return None


class OpenAIProxyTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.recorder = {}
        self.original_async_client = MODULE.httpx.AsyncClient
        self.original_api_key = MODULE.DEEPSEEK_API_KEY
        self.original_prompt = MODULE.OPENAI_PROXY_SYSTEM_PROMPT
        MODULE.httpx.AsyncClient = lambda timeout=None: FakeAsyncClient(self.recorder)
        MODULE.DEEPSEEK_API_KEY = ""
        MODULE.OPENAI_PROXY_SYSTEM_PROMPT = "学生代理限制提示"
        self.client = RealAsyncClient(
            transport=ASGITransport(app=MODULE.app),
            base_url="http://testserver",
        )

    async def asyncTearDown(self):
        MODULE.httpx.AsyncClient = self.original_async_client
        MODULE.DEEPSEEK_API_KEY = self.original_api_key
        MODULE.OPENAI_PROXY_SYSTEM_PROMPT = self.original_prompt
        await self.client.aclose()

    async def test_models_endpoint(self):
        response = await self.client.get("/openai/v1/models")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["object"], "list")
        self.assertTrue(payload["data"])

    async def test_chat_completions_proxy(self):
        response = await self.client.post(
            "/openai/v1/chat/completions",
            headers={"Authorization": "Bearer proxy-demo-key"},
            json={
                "model": "deepseek-chat",
                "messages": [{"role": "user", "content": "帮我分析这个报错"}],
                "stream": False,
            },
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["choices"][0]["message"]["content"], "代理返回内容")
        self.assertEqual(self.recorder["headers"]["Authorization"], "Bearer proxy-demo-key")
        self.assertEqual(self.recorder["json"]["messages"][0]["role"], "system")
        self.assertEqual(self.recorder["json"]["messages"][0]["content"], "学生代理限制提示")

    async def test_chat_completions_stream(self):
        async with self.client.stream(
            "POST",
            "/openai/v1/chat/completions",
            headers={"Authorization": "Bearer proxy-demo-key"},
            json={
                "model": "deepseek-chat",
                "messages": [{"role": "user", "content": "解释这个异常"}],
                "stream": True,
                "stream_options": {"include_usage": True},
            },
        ) as response:
            self.assertEqual(response.status_code, 200)
            body = "".join([chunk async for chunk in response.aiter_text()])
        self.assertIn("data: ", body)
        self.assertIn("[DONE]", body)
        self.assertIn("代理流式回复", body)
        self.assertTrue(self.recorder["stream"])
        self.assertTrue(self.recorder["json"]["stream"])
        self.assertNotIn("stream_options", self.recorder["json"])


if __name__ == "__main__":
    unittest.main()
