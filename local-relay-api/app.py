import json
import os
import time
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel


load_dotenv()


def _env(name: str, default: str = "") -> str:
    return str(os.getenv(name, default) or "").strip()


def _build_chat_completions_url(base_url: str) -> str:
    normalized = str(base_url or "").strip().rstrip("/")
    if not normalized:
        raise ValueError("RELAY_UPSTREAM_BASE_URL is required")
    if normalized.endswith("/chat/completions"):
        return normalized
    if normalized.endswith("/v1"):
        return f"{normalized}/chat/completions"
    return f"{normalized}/v1/chat/completions"


def _build_models_url(base_url: str) -> str:
    normalized = str(base_url or "").strip().rstrip("/")
    if not normalized:
        raise ValueError("RELAY_UPSTREAM_BASE_URL is required")
    if normalized.endswith("/v1/models"):
        return normalized
    if normalized.endswith("/v1"):
        return f"{normalized}/models"
    return f"{normalized}/v1/models"


UPSTREAM_BASE_URL = _env("RELAY_UPSTREAM_BASE_URL", "https://codeflow.asia")
UPSTREAM_API_KEY = _env("RELAY_UPSTREAM_API_KEY")
DEFAULT_MODEL = _env("RELAY_DEFAULT_MODEL", "claude-sonnet-4-6")
ACCESS_TOKEN = _env("RELAY_ACCESS_TOKEN")
REQUEST_TIMEOUT_SECONDS = float(_env("RELAY_REQUEST_TIMEOUT_SECONDS", "180"))

CHAT_COMPLETIONS_URL = _build_chat_completions_url(UPSTREAM_BASE_URL)
MODELS_URL = _build_models_url(UPSTREAM_BASE_URL)

app = FastAPI(title="Local Relay API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ModelInfo(BaseModel):
    id: str
    object: str = "model"
    created: int
    owned_by: str = "local-relay"


class ModelsResponse(BaseModel):
    object: str = "list"
    data: List[ModelInfo]


def _extract_bearer_token(authorization: Optional[str]) -> str:
    value = str(authorization or "").strip()
    if not value.lower().startswith("bearer "):
        return ""
    return value[7:].strip()


def _require_access_token(request: Request) -> None:
    if not ACCESS_TOKEN:
        return
    incoming = _extract_bearer_token(request.headers.get("Authorization"))
    if incoming != ACCESS_TOKEN:
        raise HTTPException(status_code=401, detail="invalid relay access token")


def _resolve_upstream_api_key(request: Request) -> str:
    header_token = _extract_bearer_token(request.headers.get("X-Upstream-Authorization"))
    if header_token:
        return header_token
    return UPSTREAM_API_KEY


def _normalize_messages(messages: Any) -> List[Dict[str, Any]]:
    output: List[Dict[str, Any]] = []
    source = messages if isinstance(messages, list) else []
    for item in source:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "").strip().lower()
        if role not in {"system", "user", "assistant", "tool"}:
            continue
        content = item.get("content")
        if content is None:
            continue
        normalized = dict(item)
        normalized["role"] = role
        output.append(normalized)
    if not output:
        raise HTTPException(status_code=400, detail="messages must contain at least one valid item")
    return output


def _prepare_payload(raw_payload: Dict[str, Any]) -> Dict[str, Any]:
    payload = dict(raw_payload or {})
    payload["model"] = str(payload.get("model") or DEFAULT_MODEL).strip() or DEFAULT_MODEL
    payload["messages"] = _normalize_messages(payload.get("messages"))
    payload["stream"] = bool(payload.get("stream"))
    return payload


async def _post_json(*, url: str, api_key: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    if not api_key:
        raise HTTPException(status_code=400, detail="missing upstream API key")
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(REQUEST_TIMEOUT_SECONDS, connect=20.0)) as client:
            response = await client.post(
                url,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=504, detail="upstream request timed out") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"upstream request failed: {exc}") from exc

    raw_text = response.text or ""
    try:
        data = response.json() if raw_text else {}
    except ValueError:
        data = {}

    if not response.is_success:
        detail = raw_text[:400] or f"HTTP {response.status_code}"
        if isinstance(data, dict):
            error_payload = data.get("error")
            if isinstance(error_payload, dict):
                detail = str(error_payload.get("message") or "").strip() or detail
            else:
                detail = str(data.get("message") or "").strip() or detail
        raise HTTPException(status_code=502, detail=f"upstream model error: {detail}")

    if not isinstance(data, dict):
        raise HTTPException(status_code=502, detail="upstream returned invalid JSON")
    return data


async def _get_json(*, url: str, api_key: str) -> Dict[str, Any]:
    if not api_key:
        raise HTTPException(status_code=400, detail="missing upstream API key")
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(REQUEST_TIMEOUT_SECONDS, connect=20.0)) as client:
            response = await client.get(
                url,
                headers={
                    "Authorization": f"Bearer {api_key}",
                },
            )
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=504, detail="upstream request timed out") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"upstream request failed: {exc}") from exc

    raw_text = response.text or ""
    try:
        data = response.json() if raw_text else {}
    except ValueError:
        data = {}

    if not response.is_success:
        detail = raw_text[:400] or f"HTTP {response.status_code}"
        if isinstance(data, dict):
            error_payload = data.get("error")
            if isinstance(error_payload, dict):
                detail = str(error_payload.get("message") or "").strip() or detail
            else:
                detail = str(data.get("message") or "").strip() or detail
        raise HTTPException(status_code=502, detail=f"upstream model error: {detail}")

    if not isinstance(data, dict):
        raise HTTPException(status_code=502, detail="upstream returned invalid JSON")
    return data


async def _open_stream(*, url: str, api_key: str, payload: Dict[str, Any]) -> Tuple[httpx.AsyncClient, httpx.Response]:
    if not api_key:
        raise HTTPException(status_code=400, detail="missing upstream API key")

    client = httpx.AsyncClient(timeout=httpx.Timeout(REQUEST_TIMEOUT_SECONDS, connect=20.0))
    request = client.build_request(
        "POST",
        url,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json=payload,
    )

    try:
        response = await client.send(request, stream=True)
    except httpx.TimeoutException as exc:
        await client.aclose()
        raise HTTPException(status_code=504, detail="upstream request timed out") from exc
    except httpx.HTTPError as exc:
        await client.aclose()
        raise HTTPException(status_code=502, detail=f"upstream request failed: {exc}") from exc

    if response.is_success:
        return client, response

    raw_text = ""
    try:
        raw_bytes = await response.aread()
        raw_text = raw_bytes.decode("utf-8", errors="replace")
    finally:
        await response.aclose()
        await client.aclose()

    detail = raw_text[:400] or f"HTTP {response.status_code}"
    try:
        data = json.loads(raw_text) if raw_text else {}
    except ValueError:
        data = {}
    if isinstance(data, dict):
        error_payload = data.get("error")
        if isinstance(error_payload, dict):
            detail = str(error_payload.get("message") or "").strip() or detail
        else:
            detail = str(data.get("message") or "").strip() or detail
    raise HTTPException(status_code=502, detail=f"upstream model error: {detail}")


@app.get("/")
def root() -> Dict[str, Any]:
    return {
        "service": "local-relay-api",
        "status": "running",
        "upstream_base_url": UPSTREAM_BASE_URL,
        "default_model": DEFAULT_MODEL,
        "access_token_enabled": bool(ACCESS_TOKEN),
    }


@app.get("/health")
def health() -> Dict[str, Any]:
    return {
        "status": "ok",
        "upstream_base_url": UPSTREAM_BASE_URL,
        "default_model": DEFAULT_MODEL,
        "upstream_api_key_configured": bool(UPSTREAM_API_KEY),
        "access_token_enabled": bool(ACCESS_TOKEN),
    }


@app.get("/v1/models", response_model=ModelsResponse)
async def list_models(request: Request) -> ModelsResponse:
    _require_access_token(request)
    api_key = _resolve_upstream_api_key(request)

    if api_key:
        try:
            payload = await _get_json(url=MODELS_URL, api_key=api_key)
            raw_models = payload.get("data") if isinstance(payload, dict) else None
            if isinstance(raw_models, list):
                models: List[ModelInfo] = []
                for item in raw_models:
                    if not isinstance(item, dict):
                        continue
                    model_id = str(item.get("id") or "").strip()
                    if not model_id:
                        continue
                    models.append(
                        ModelInfo(
                            id=model_id,
                            object=str(item.get("object") or "model"),
                            created=int(item.get("created") or int(time.time())),
                            owned_by=str(item.get("owned_by") or "local-relay"),
                        )
                    )
                if models:
                    return ModelsResponse(data=models)
        except HTTPException:
            pass

    return ModelsResponse(data=[ModelInfo(id=DEFAULT_MODEL, created=int(time.time()))])


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    _require_access_token(request)

    try:
        raw_payload = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"invalid JSON payload: {exc}") from exc

    if not isinstance(raw_payload, dict):
        raise HTTPException(status_code=400, detail="request body must be a JSON object")

    payload = _prepare_payload(raw_payload)
    api_key = _resolve_upstream_api_key(request)

    if payload.get("stream"):
        upstream_client, upstream_response = await _open_stream(
            url=CHAT_COMPLETIONS_URL,
            api_key=api_key,
            payload=payload,
        )

        async def _relay() -> AsyncIterator[bytes]:
            try:
                async for chunk in upstream_response.aiter_raw():
                    if chunk:
                        yield chunk
            finally:
                await upstream_response.aclose()
                await upstream_client.aclose()

        return StreamingResponse(
            _relay(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    upstream_payload = await _post_json(
        url=CHAT_COMPLETIONS_URL,
        api_key=api_key,
        payload=payload,
    )
    return JSONResponse(content=upstream_payload)


if __name__ == "__main__":
    import uvicorn

    host = _env("RELAY_LISTEN_HOST", "127.0.0.1")
    port = int(_env("RELAY_LISTEN_PORT", "8010"))
    uvicorn.run(app, host=host, port=port)
