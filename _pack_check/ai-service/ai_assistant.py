import asyncio
import json
import logging
import os
import re
import time
from dataclasses import dataclass
from threading import Lock
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

import httpx
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

try:
    from tavily import TavilyClient
except Exception:  # pragma: no cover - dependency may be absent in local dev
    TavilyClient = None


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ai-assistant")


def _read_int_env(name: str, default: int, min_value: int, max_value: int) -> int:
    raw = str(os.getenv(name, str(default)) or "").strip()
    try:
        value = int(raw)
    except ValueError:
        return default
    return max(min_value, min(value, max_value))


DEEPSEEK_API_KEY = str(os.getenv("DEEPSEEK_API_KEY", "") or "").strip()
DEEPSEEK_BASE_URL = str(os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com") or "").strip()
DEEPSEEK_MODEL = str(os.getenv("DEEPSEEK_MODEL", "deepseek-chat") or "").strip()
TAVILY_API_KEY = str(os.getenv("TAVILY_API_KEY", "") or "").strip()
CACHE_TTL = _read_int_env("CACHE_TTL", 3600, 60, 86400 * 7)
MAX_HISTORY = _read_int_env("MAX_HISTORY", 10, 0, 50)


def _chat_completions_url(base_url: str) -> str:
    normalized = str(base_url or "").strip().rstrip("/")
    if not normalized:
        normalized = "https://api.deepseek.com"
    if normalized.endswith("/chat/completions"):
        return normalized
    if normalized.endswith("/v1"):
        return f"{normalized}/chat/completions"
    return f"{normalized}/v1/chat/completions"


DEEPSEEK_CHAT_URL = _chat_completions_url(DEEPSEEK_BASE_URL)


SYSTEM_PROMPT = """你是一个教学平台的 AI 助手，回答要简洁、准确、可执行。

联网搜索策略（通过 web_search 工具）：
1. 需要搜索：
- 2024 年后的事件或“最新/最近/今日/当前”相关问题
- 实时数据（新闻、价格、政策、股价、天气、比赛、官网更新）
- 你对事实不确定，或用户明确要求“查一下/搜索一下”
2. 不需要搜索：
- 通用知识、稳定历史事实
- 纯代码解释、调试、算法推导
- 明确不依赖实时信息的学习问题
3. 搜索深度：
- 默认优先 basic（更快）
- 仅在用户要求深度研究/多来源对比时使用 advanced

回答风格：
- 优先直接回答，避免冗长前言
- 如果使用了检索结果，按 [1] [2] 标注来源
- 不编造来源和数据；不确定时明确说明不确定"""


WEB_SEARCH_TOOL = {
    "type": "function",
    "function": {
        "name": "web_search",
        "description": "联网搜索最新信息。默认使用 basic，深度研究时使用 advanced。",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "搜索关键词，尽量精炼具体。",
                },
                "search_depth": {
                    "type": "string",
                    "enum": ["basic", "advanced"],
                    "description": "搜索深度：basic 或 advanced。",
                },
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    },
}


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=8000)
    history: Optional[List[Dict[str, Any]]] = None
    context: Optional[str] = None


class SearchSource(BaseModel):
    title: str
    url: str
    snippet: str
    relevance: Optional[float] = None
    query: Optional[str] = None
    search_depth: Optional[str] = None


class ChatResponse(BaseModel):
    response: str
    answer: str
    used_search: bool
    search_queries: List[str]
    sources: List[SearchSource]


class StatsResponse(BaseModel):
    total_queries: int
    search_triggered: int
    search_trigger_rate: float
    search_requests: int
    cache_hits: int
    cache_hit_rate: float
    avg_response_time_ms: float
    cache_entries: int
    uptime_seconds: int
    model: str


@dataclass
class CacheEntry:
    value: Dict[str, Any]
    expires_at: float


class TTLSearchCache:
    def __init__(self, ttl_seconds: int):
        self.ttl_seconds = ttl_seconds
        self._store: Dict[str, CacheEntry] = {}
        self._lock = Lock()

    def _cleanup_locked(self, now_ts: float) -> None:
        expired_keys = [k for k, v in self._store.items() if v.expires_at <= now_ts]
        for key in expired_keys:
            self._store.pop(key, None)

    def get(self, key: str) -> Tuple[Optional[Dict[str, Any]], bool]:
        now_ts = time.time()
        with self._lock:
            self._cleanup_locked(now_ts)
            entry = self._store.get(key)
            if entry is None:
                return None, False
            return entry.value, True

    def set(self, key: str, value: Dict[str, Any]) -> None:
        now_ts = time.time()
        with self._lock:
            self._cleanup_locked(now_ts)
            self._store[key] = CacheEntry(
                value=value,
                expires_at=now_ts + float(self.ttl_seconds),
            )

    def size(self) -> int:
        now_ts = time.time()
        with self._lock:
            self._cleanup_locked(now_ts)
            return len(self._store)


class RuntimeStats:
    def __init__(self):
        self._lock = Lock()
        self.started_at = time.time()
        self.total_queries = 0
        self.search_triggered = 0
        self.search_requests = 0
        self.cache_hits = 0
        self.total_response_time_ms = 0.0

    def record(
        self,
        *,
        response_time_ms: float,
        used_search: bool,
        search_request_count: int,
        cache_hit_count: int,
    ) -> None:
        with self._lock:
            self.total_queries += 1
            if used_search:
                self.search_triggered += 1
            self.search_requests += max(0, int(search_request_count))
            self.cache_hits += max(0, int(cache_hit_count))
            self.total_response_time_ms += max(0.0, float(response_time_ms))

    def snapshot(self, cache_entries: int, model: str) -> Dict[str, Any]:
        with self._lock:
            total_queries = self.total_queries
            search_triggered = self.search_triggered
            search_requests = self.search_requests
            cache_hits = self.cache_hits
            total_response_time_ms = self.total_response_time_ms
            uptime_seconds = int(max(0.0, time.time() - self.started_at))

        search_trigger_rate = (search_triggered / total_queries * 100.0) if total_queries else 0.0
        cache_hit_rate = (cache_hits / search_requests * 100.0) if search_requests else 0.0
        avg_response_time_ms = (total_response_time_ms / total_queries) if total_queries else 0.0

        return {
            "total_queries": total_queries,
            "search_triggered": search_triggered,
            "search_trigger_rate": round(search_trigger_rate, 2),
            "search_requests": search_requests,
            "cache_hits": cache_hits,
            "cache_hit_rate": round(cache_hit_rate, 2),
            "avg_response_time_ms": round(avg_response_time_ms, 2),
            "cache_entries": int(cache_entries),
            "uptime_seconds": uptime_seconds,
            "model": model,
        }


class DeepSeekClient:
    def __init__(self, *, api_key: str, chat_url: str, model: str):
        self.api_key = api_key
        self.chat_url = chat_url
        self.model = model

    async def chat_completion(
        self,
        *,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not self.api_key:
            raise HTTPException(status_code=400, detail="DEEPSEEK_API_KEY 未配置")

        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "temperature": 0.2,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = tool_choice or "auto"

        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(90.0, connect=15.0)) as client:
                response = await client.post(
                    self.chat_url,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
        except httpx.TimeoutException as exc:
            raise HTTPException(status_code=504, detail="调用 DeepSeek 超时") from exc
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=f"调用 DeepSeek 失败: {exc}") from exc

        raw_text = response.text or ""
        try:
            data = response.json() if raw_text else {}
        except ValueError:
            data = {}

        if not response.is_success:
            detail = ""
            if isinstance(data, dict):
                error_obj = data.get("error")
                if isinstance(error_obj, dict):
                    detail = str(error_obj.get("message") or "").strip()
                if not detail:
                    detail = str(data.get("message") or "").strip()
            detail = detail or raw_text[:300] or f"HTTP {response.status_code}"
            raise HTTPException(status_code=502, detail=f"DeepSeek 接口错误: {detail}")

        if not isinstance(data, dict):
            raise HTTPException(status_code=502, detail="DeepSeek 返回了无效响应")

        choices = data.get("choices")
        if not isinstance(choices, list) or not choices:
            raise HTTPException(status_code=502, detail="DeepSeek 未返回 choices")

        first_choice = choices[0] if isinstance(choices[0], dict) else {}
        message = first_choice.get("message") if isinstance(first_choice, dict) else None
        if not isinstance(message, dict):
            raise HTTPException(status_code=502, detail="DeepSeek 未返回 message")

        return message


class TavilySearchService:
    def __init__(self, *, api_key: str, cache: TTLSearchCache):
        self.api_key = api_key
        self.cache = cache
        self.client = TavilyClient(api_key=api_key) if api_key and TavilyClient is not None else None

    async def search(self, *, query: str, search_depth: str) -> Tuple[Dict[str, Any], bool]:
        normalized_query = str(query or "").strip()
        if not normalized_query:
            raise HTTPException(status_code=400, detail="搜索 query 不能为空")

        normalized_depth = "advanced" if str(search_depth).strip().lower() == "advanced" else "basic"
        cache_key = f"{normalized_query}_{normalized_depth}"

        cached_payload, hit = self.cache.get(cache_key)
        if hit and cached_payload is not None:
            return cached_payload, True

        if not self.api_key:
            raise HTTPException(status_code=400, detail="TAVILY_API_KEY 未配置")
        if self.client is None:
            raise HTTPException(status_code=500, detail="tavily-python 依赖不可用")

        max_results = 10 if normalized_depth == "advanced" else 5

        try:
            raw_payload = await asyncio.to_thread(
                self.client.search,
                query=normalized_query,
                search_depth=normalized_depth,
                max_results=max_results,
                include_answer=True,
                include_raw_content=False,
            )
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Tavily 搜索失败: {exc}") from exc

        formatted_payload = self._format_payload(
            raw_payload=raw_payload,
            query=normalized_query,
            search_depth=normalized_depth,
            max_results=max_results,
        )
        self.cache.set(cache_key, formatted_payload)
        return formatted_payload, False

    @staticmethod
    def _normalize_text(value: Any, *, collapse_ws: bool = False) -> str:
        text = str(value or "").strip()
        if collapse_ws:
            text = re.sub(r"\s+", " ", text)
        return text

    @classmethod
    def _format_payload(
        cls,
        *,
        raw_payload: Any,
        query: str,
        search_depth: str,
        max_results: int,
    ) -> Dict[str, Any]:
        payload = raw_payload if isinstance(raw_payload, dict) else {}
        ai_summary = cls._normalize_text(payload.get("answer"), collapse_ws=True)[:1200]

        sources: List[Dict[str, Any]] = []
        seen_urls = set()
        raw_results = payload.get("results")
        if not isinstance(raw_results, list):
            raw_results = []

        for item in raw_results:
            if not isinstance(item, dict):
                continue
            url = cls._normalize_text(item.get("url"))
            if not url or url in seen_urls:
                continue

            title = cls._normalize_text(item.get("title")) or url
            snippet = cls._normalize_text(item.get("content") or item.get("snippet"), collapse_ws=True)[:500]

            relevance_raw = item.get("score")
            relevance: Optional[float]
            if isinstance(relevance_raw, (int, float)):
                relevance = float(relevance_raw)
            else:
                relevance = None

            sources.append(
                {
                    "title": title,
                    "url": url,
                    "snippet": snippet,
                    "relevance": relevance,
                    "query": query,
                    "search_depth": search_depth,
                }
            )
            seen_urls.add(url)

            if len(sources) >= max_results:
                break

        context_lines: List[str] = []
        if ai_summary:
            context_lines.append(f"AI摘要: {ai_summary}")
        for idx, source in enumerate(sources, start=1):
            relevance = source.get("relevance")
            relevance_str = f"{relevance:.3f}" if isinstance(relevance, float) else "N/A"
            context_lines.append(
                f"[{idx}] 标题: {source['title']}\n"
                f"URL: {source['url']}\n"
                f"相关度: {relevance_str}\n"
                f"摘要: {source['snippet']}"
            )

        context_text = "\n\n".join(context_lines) if context_lines else "未检索到可用来源。"

        return {
            "query": query,
            "search_depth": search_depth,
            "ai_summary": ai_summary,
            "sources": sources,
            "context_text": context_text,
        }


def _model_dump(instance: BaseModel) -> Dict[str, Any]:
    if hasattr(instance, "model_dump"):
        return instance.model_dump()  # type: ignore[attr-defined]
    return instance.dict()


def _coerce_message_content(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        parts: List[str] = []
        for item in value:
            if isinstance(item, str):
                parts.append(item)
                continue
            if isinstance(item, dict):
                text = item.get("text")
                if text is None:
                    text = item.get("content")
                if text is not None:
                    parts.append(str(text))
        return "\n".join(part.strip() for part in parts if str(part).strip()).strip()
    if value is None:
        return ""
    return str(value).strip()


def _normalize_history(history: Optional[List[Dict[str, Any]]]) -> List[Dict[str, str]]:
    if not isinstance(history, list):
        return []

    normalized: List[Dict[str, str]] = []
    for item in history:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "").strip().lower()
        content = _coerce_message_content(item.get("content"))
        if role not in {"user", "assistant"}:
            continue
        if not content:
            continue
        normalized.append({"role": role, "content": content})

    if MAX_HISTORY and len(normalized) > MAX_HISTORY:
        normalized = normalized[-MAX_HISTORY:]
    return normalized


def _normalize_depth(raw_depth: Any) -> str:
    return "advanced" if str(raw_depth or "").strip().lower() == "advanced" else "basic"


def _parse_json_object(raw_text: str) -> Dict[str, Any]:
    text = str(raw_text or "").strip()
    if not text:
        return {}
    try:
        payload = json.loads(text)
        return payload if isinstance(payload, dict) else {}
    except ValueError:
        pass

    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        return {}
    try:
        payload = json.loads(match.group(0))
        return payload if isinstance(payload, dict) else {}
    except ValueError:
        return {}


def _chunk_text(text: str, chunk_size: int = 120) -> List[str]:
    if chunk_size <= 0:
        chunk_size = 120
    return [text[i:i + chunk_size] for i in range(0, len(text), chunk_size)] or [""]


def _deduplicate_sources(sources: List[SearchSource]) -> List[SearchSource]:
    output: List[SearchSource] = []
    seen_urls = set()
    for source in sources:
        url = str(source.url or "").strip()
        if not url or url in seen_urls:
            continue
        output.append(source)
        seen_urls.add(url)
    return output


StatusCallback = Callable[[str, Optional[Dict[str, Any]]], Awaitable[None]]

cache = TTLSearchCache(ttl_seconds=CACHE_TTL)
stats = RuntimeStats()
deepseek_client = DeepSeekClient(api_key=DEEPSEEK_API_KEY, chat_url=DEEPSEEK_CHAT_URL, model=DEEPSEEK_MODEL)
tavily_service = TavilySearchService(api_key=TAVILY_API_KEY, cache=cache)

app = FastAPI(title="AI Assistant Service", version="2.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


async def _run_chat_pipeline(
    request: ChatRequest,
    *,
    status_callback: Optional[StatusCallback] = None,
) -> ChatResponse:
    started_at = time.perf_counter()
    used_search = False
    search_request_count = 0
    cache_hit_count = 0
    search_queries: List[str] = []
    collected_sources: List[SearchSource] = []

    try:
        raw_user_message = _coerce_message_content(request.message)
        if not raw_user_message:
            raise HTTPException(status_code=400, detail="message 不能为空")

        user_message = raw_user_message
        history = _normalize_history(request.history)
        if request.context:
            context_text = _coerce_message_content(request.context)[:2000]
            if context_text:
                user_message = f"{user_message}\n\n补充上下文：\n{context_text}"

        messages: List[Dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]
        messages.extend(history)
        messages.append({"role": "user", "content": user_message})

        if status_callback is not None:
            await status_callback("thinking", None)

        first_message = await deepseek_client.chat_completion(
            messages=messages,
            tools=[WEB_SEARCH_TOOL],
            tool_choice="auto",
        )

        first_content = _coerce_message_content(first_message.get("content"))
        tool_calls = first_message.get("tool_calls")

        if isinstance(tool_calls, list) and tool_calls:
            used_search = True
            if status_callback is not None:
                await status_callback("searching", None)

            second_round_messages: List[Dict[str, Any]] = list(messages)
            second_round_messages.append(
                {
                    "role": "assistant",
                    "content": first_content,
                    "tool_calls": tool_calls,
                }
            )

            for tool_call in tool_calls:
                if not isinstance(tool_call, dict):
                    continue

                function_obj = tool_call.get("function")
                if not isinstance(function_obj, dict):
                    continue

                function_name = str(function_obj.get("name") or "").strip()
                if function_name != "web_search":
                    continue

                args = _parse_json_object(str(function_obj.get("arguments") or "{}"))
                query = str(args.get("query") or raw_user_message).strip()
                depth = _normalize_depth(args.get("search_depth"))
                if not query:
                    query = raw_user_message

                search_request_count += 1
                search_queries.append(query)

                tool_content: Dict[str, Any]
                try:
                    search_payload, is_cache_hit = await tavily_service.search(
                        query=query,
                        search_depth=depth,
                    )
                    if is_cache_hit:
                        cache_hit_count += 1

                    raw_sources = search_payload.get("sources")
                    if isinstance(raw_sources, list):
                        for item in raw_sources:
                            if not isinstance(item, dict):
                                continue
                            source = SearchSource(
                                title=str(item.get("title") or item.get("url") or "Untitled"),
                                url=str(item.get("url") or "").strip(),
                                snippet=str(item.get("snippet") or "").strip()[:500],
                                relevance=item.get("relevance") if isinstance(item.get("relevance"), (int, float)) else None,
                                query=query,
                                search_depth=depth,
                            )
                            if source.url:
                                collected_sources.append(source)

                    tool_content = {
                        "query": query,
                        "search_depth": depth,
                        "cached": is_cache_hit,
                        "ai_summary": str(search_payload.get("ai_summary") or "").strip(),
                        "sources": raw_sources if isinstance(raw_sources, list) else [],
                        "context_text": str(search_payload.get("context_text") or "").strip(),
                    }

                    if status_callback is not None:
                        await status_callback(
                            "searching",
                            {
                                "query": query,
                                "search_depth": depth,
                                "cached": is_cache_hit,
                                "result_count": len(tool_content.get("sources") or []),
                            },
                        )
                except HTTPException as exc:
                    tool_content = {
                        "query": query,
                        "search_depth": depth,
                        "error": str(exc.detail),
                        "sources": [],
                    }
                    if status_callback is not None:
                        await status_callback(
                            "searching",
                            {
                                "query": query,
                                "search_depth": depth,
                                "error": str(exc.detail),
                            },
                        )
                except Exception as exc:
                    tool_content = {
                        "query": query,
                        "search_depth": depth,
                        "error": f"搜索异常: {exc}",
                        "sources": [],
                    }
                    if status_callback is not None:
                        await status_callback(
                            "searching",
                            {
                                "query": query,
                                "search_depth": depth,
                                "error": f"搜索异常: {exc}",
                            },
                        )

                tool_call_id = str(tool_call.get("id") or f"tool_call_{search_request_count}")
                second_round_messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call_id,
                        "name": "web_search",
                        "content": json.dumps(tool_content, ensure_ascii=False),
                    }
                )

            if status_callback is not None:
                await status_callback("generating", None)

            final_message = await deepseek_client.chat_completion(messages=second_round_messages)
            final_response = _coerce_message_content(final_message.get("content"))
        else:
            if status_callback is not None:
                await status_callback("generating", None)
            final_response = first_content

        if not final_response:
            raise HTTPException(status_code=502, detail="DeepSeek 未返回有效回答")

        deduped_sources = _deduplicate_sources(collected_sources)
        return ChatResponse(
            response=final_response,
            answer=final_response,  # 兼容现有前端 response.data.answer
            used_search=bool(used_search),
            search_queries=search_queries,
            sources=deduped_sources,
        )
    finally:
        elapsed_ms = (time.perf_counter() - started_at) * 1000.0
        stats.record(
            response_time_ms=elapsed_ms,
            used_search=used_search,
            search_request_count=search_request_count,
            cache_hit_count=cache_hit_count,
        )


@app.get("/")
def root() -> Dict[str, Any]:
    return {
        "service": "AI Assistant Service",
        "status": "running",
        "model": DEEPSEEK_MODEL,
        "deepseek_base_url": DEEPSEEK_BASE_URL,
        "cache_ttl": CACHE_TTL,
        "max_history": MAX_HISTORY,
    }


@app.get("/health")
def health() -> Dict[str, Any]:
    return {
        "status": "ok",
        "deepseek_configured": bool(DEEPSEEK_API_KEY),
        "tavily_configured": bool(TAVILY_API_KEY),
        "model": DEEPSEEK_MODEL,
    }


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    return await _run_chat_pipeline(request)


@app.websocket("/ws/chat")
async def ws_chat(websocket: WebSocket) -> None:
    await websocket.accept()
    try:
        while True:
            try:
                payload = await websocket.receive_json()
            except WebSocketDisconnect:
                break
            except Exception:
                await websocket.send_json({"type": "error", "detail": "消息格式错误，需发送 JSON"})
                continue

            try:
                chat_request = ChatRequest(**payload)
            except Exception as exc:
                await websocket.send_json({"type": "error", "detail": f"请求参数错误: {exc}"})
                continue

            async def _send_status(status: str, extra: Optional[Dict[str, Any]] = None) -> None:
                event: Dict[str, Any] = {"type": "status", "status": status}
                if extra:
                    event.update(extra)
                await websocket.send_json(event)

            try:
                result = await _run_chat_pipeline(chat_request, status_callback=_send_status)
                for chunk in _chunk_text(result.response):
                    await websocket.send_json({"type": "chunk", "delta": chunk})
                final_payload = _model_dump(result)
                final_payload["type"] = "final"
                await websocket.send_json(final_payload)
            except HTTPException as exc:
                await websocket.send_json({"type": "error", "detail": str(exc.detail)})
            except Exception as exc:
                logger.exception("WebSocket chat failed: %s", exc)
                await websocket.send_json({"type": "error", "detail": "服务器内部错误"})
    finally:
        try:
            await websocket.close()
        except Exception:
            pass


@app.get("/api/stats", response_model=StatsResponse)
def get_stats() -> StatsResponse:
    payload = stats.snapshot(cache_entries=cache.size(), model=DEEPSEEK_MODEL)
    return StatsResponse(**payload)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
