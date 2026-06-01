from fastapi import HTTPException, Request
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Tuple
from datetime import datetime, timezone
from copy import deepcopy
import html
import json
import re
import requests
import secrets
import time
from urllib.parse import parse_qs, urlparse, unquote
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

try:
    from tavily import TavilyClient
except Exception:
    TavilyClient = None

from ..config import (
    DEFAULT_AI_SHARED_CONFIG,
    AI_RESPONSE_STYLE_RULES,
    AI_CHAT_HISTORY_MAX_MESSAGES,
    AI_CHAT_HISTORY_MAX_MESSAGE_CHARS,
    AI_CONTEXT_MAX_HISTORY_MESSAGES,
    AI_CONTEXT_MAX_TOTAL_CHARS,
    AI_SESSION_TTL_SECONDS,
    AI_SESSION_MAX_TOKENS,
    AI_WEB_SEARCH_CACHE_TTL_SECONDS,
    AI_WEB_SEARCH_CACHE_MAX_ITEMS,
    TAVILY_API_KEY,
)
from ..state import (
    ai_shared_config_db,
    ai_chat_history_db,
    ai_session_tokens_db,
    ai_web_search_cache_db,
)
from ..registry_store import _normalize_text, is_admin

def _cleanup_ai_sessions(now_ts: Optional[float] = None):
    now_value = float(now_ts if now_ts is not None else time.time())

    expired_tokens = [
        token
        for token, item in ai_session_tokens_db.items()
        if float(item.get("expires_at") or 0.0) <= now_value
    ]
    for token in expired_tokens:
        ai_session_tokens_db.pop(token, None)

    if len(ai_session_tokens_db) <= AI_SESSION_MAX_TOKENS:
        return

    sorted_items = sorted(
        ai_session_tokens_db.items(),
        key=lambda pair: float((pair[1] or {}).get("expires_at") or 0.0),
    )
    overflow = len(sorted_items) - AI_SESSION_MAX_TOKENS
    for token, _ in sorted_items[:overflow]:
        ai_session_tokens_db.pop(token, None)


def _create_ai_session_token(username: str) -> str:
    normalized_user = _normalize_text(username)
    if not normalized_user:
        return ""

    now_ts = time.time()
    _cleanup_ai_sessions(now_ts)

    token = secrets.token_urlsafe(36)
    ai_session_tokens_db[token] = {
        "username": normalized_user,
        "expires_at": now_ts + AI_SESSION_TTL_SECONDS,
    }
    return token


def _resolve_ai_session_user(token: str) -> str:
    normalized_token = _normalize_text(token)
    if not normalized_token:
        return ""

    now_ts = time.time()
    _cleanup_ai_sessions(now_ts)

    session_item = ai_session_tokens_db.get(normalized_token) or {}
    username = _normalize_text(session_item.get("username"))
    expires_at = float(session_item.get("expires_at") or 0.0)
    if not username or expires_at <= now_ts:
        ai_session_tokens_db.pop(normalized_token, None)
        return ""

    # Sliding window refresh for active users.
    session_item["expires_at"] = now_ts + AI_SESSION_TTL_SECONDS
    ai_session_tokens_db[normalized_token] = session_item
    return username


def _require_ai_session(
    request: Request,
    *,
    expected_username: Optional[str] = None,
    allow_admin_override: bool = True,
) -> str:
    token = _normalize_text(request.headers.get("X-AI-Session-Token"))
    if not token:
        raise HTTPException(status_code=401, detail="AI会话不存在或已过期，请重新登录")

    actor = _resolve_ai_session_user(token)
    if not actor:
        raise HTTPException(status_code=401, detail="AI会话不存在或已过期，请重新登录")

    normalized_expected = _normalize_text(expected_username)
    if normalized_expected and actor != normalized_expected:
        if not (allow_admin_override and is_admin(actor)):
            raise HTTPException(status_code=403, detail="无权访问该用户AI数据")

    return actor
def _normalize_ai_shared_config(raw: Optional[dict]) -> dict:
    payload = raw or {}
    chat_model = _normalize_text(payload.get("chat_model")) or DEFAULT_AI_SHARED_CONFIG["chat_model"]
    reasoner_model = _normalize_text(payload.get("reasoner_model")) or DEFAULT_AI_SHARED_CONFIG["reasoner_model"]
    base_url = _normalize_text(payload.get("base_url")) or DEFAULT_AI_SHARED_CONFIG["base_url"]
    system_prompt = _normalize_text(payload.get("system_prompt")) or DEFAULT_AI_SHARED_CONFIG["system_prompt"]
    api_key = _normalize_text(payload.get("api_key"))
    tavily_api_key = _normalize_text(payload.get("tavily_api_key"))

    return {
        "api_key": api_key[:512],
        "tavily_api_key": tavily_api_key[:512],
        "chat_model": chat_model[:120],
        "reasoner_model": reasoner_model[:120],
        "base_url": base_url[:500].rstrip("/") or DEFAULT_AI_SHARED_CONFIG["base_url"],
        "system_prompt": system_prompt[:4000],
    }


def _refresh_ai_shared_config_cache(raw: Optional[dict]) -> dict:
    normalized = dict(DEFAULT_AI_SHARED_CONFIG)
    normalized.update(_normalize_ai_shared_config(raw))
    ai_shared_config_db.clear()
    ai_shared_config_db.update(normalized)
    return normalized


def _save_ai_shared_config():
    _refresh_ai_shared_config_cache(ai_shared_config_db)


def _load_ai_shared_config():
    _refresh_ai_shared_config_cache(None)


def _normalize_chat_history_message(raw: Optional[dict]) -> Optional[Dict[str, str]]:
    if not isinstance(raw, dict):
        return None

    role = _normalize_text(raw.get("role")).lower()
    if role not in {"system", "user", "assistant"}:
        return None

    content = str(raw.get("content") or "").strip()
    if not content:
        return None

    return {
        "role": role,
        "content": content[:AI_CHAT_HISTORY_MAX_MESSAGE_CHARS],
    }


def _normalize_chat_history_items(raw_items) -> List[Dict[str, str]]:
    output: List[Dict[str, str]] = []
    for item in raw_items if isinstance(raw_items, list) else []:
        normalized = _normalize_chat_history_message(item)
        if normalized:
            output.append(normalized)
    return output[-AI_CHAT_HISTORY_MAX_MESSAGES:]


def _save_ai_chat_history():
    payload = {}
    for username, items in ai_chat_history_db.items():
        normalized_username = _normalize_text(username)
        if not normalized_username:
            continue
        payload[normalized_username] = _normalize_chat_history_items(items)
    ai_chat_history_db.clear()
    ai_chat_history_db.update(payload)


def _load_ai_chat_history():
    ai_chat_history_db.clear()


def _get_ai_chat_history(username: str) -> List[Dict[str, str]]:
    normalized_username = _normalize_text(username)
    if not normalized_username:
        return []
    return deepcopy(ai_chat_history_db.get(normalized_username, []))


def _set_ai_chat_history(username: str, raw_items) -> List[Dict[str, str]]:
    normalized_username = _normalize_text(username)
    if not normalized_username:
        return []
    normalized_items = _normalize_chat_history_items(raw_items)
    if normalized_items:
        ai_chat_history_db[normalized_username] = normalized_items
    else:
        ai_chat_history_db.pop(normalized_username, None)
    _save_ai_chat_history()
    return deepcopy(normalized_items)


def _trim_ai_history_for_context(raw_items) -> List[Dict[str, str]]:
    normalized_items = _normalize_chat_history_items(raw_items)
    if len(normalized_items) > AI_CONTEXT_MAX_HISTORY_MESSAGES:
        normalized_items = normalized_items[-AI_CONTEXT_MAX_HISTORY_MESSAGES:]

    total_chars = 0
    selected: List[Dict[str, str]] = []
    for item in reversed(normalized_items):
        content = item.get("content", "")
        estimated_chars = len(content) + 16
        if selected and (total_chars + estimated_chars > AI_CONTEXT_MAX_TOTAL_CHARS):
            break
        selected.append({"role": item.get("role", "user"), "content": content})
        total_chars += estimated_chars

    if not selected and normalized_items:
        last_item = normalized_items[-1]
        selected.append({
            "role": last_item.get("role", "user"),
            "content": str(last_item.get("content") or "")[:AI_CONTEXT_MAX_TOTAL_CHARS],
        })

    return list(reversed(selected))
class AISharedConfigResponse(BaseModel):
    api_key: str = ""
    tavily_api_key: str = ""
    chat_model: str = DEFAULT_AI_SHARED_CONFIG["chat_model"]
    reasoner_model: str = DEFAULT_AI_SHARED_CONFIG["reasoner_model"]
    base_url: str = DEFAULT_AI_SHARED_CONFIG["base_url"]
    system_prompt: str = DEFAULT_AI_SHARED_CONFIG["system_prompt"]


class AISharedConfigUpdateRequest(BaseModel):
    teacher_username: str = Field(..., min_length=1, max_length=80)
    api_key: str = Field(default="", max_length=512)
    tavily_api_key: str = Field(default="", max_length=512)
    chat_model: str = Field(default=DEFAULT_AI_SHARED_CONFIG["chat_model"], min_length=1, max_length=120)
    reasoner_model: str = Field(default=DEFAULT_AI_SHARED_CONFIG["reasoner_model"], min_length=1, max_length=120)
    base_url: str = Field(default=DEFAULT_AI_SHARED_CONFIG["base_url"], min_length=1, max_length=500)
    system_prompt: str = Field(default=DEFAULT_AI_SHARED_CONFIG["system_prompt"], min_length=1, max_length=4000)


class AIWebSearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=200)
    limit: int = Field(default=5, ge=1, le=8)


class AIChatWithSearchRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=120)
    message: str = Field(..., min_length=1, max_length=4000)
    history: Optional[List[Dict]] = None
    model: str = Field(default="", max_length=120)
    use_web_search: bool = True
    auto_web_search: bool = True
    search_limit: int = Field(default=4, ge=1, le=8)


class AIChatHistoryMessage(BaseModel):
    role: str = Field(..., min_length=1, max_length=20)
    content: str = Field(..., min_length=1, max_length=AI_CHAT_HISTORY_MAX_MESSAGE_CHARS)


class AIChatHistoryUpdateRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=120)
    messages: List[AIChatHistoryMessage] = Field(default_factory=list)


class AIChatHistoryResponse(BaseModel):
    username: str
    message_count: int
    messages: List[AIChatHistoryMessage]


def _build_ai_shared_config_response(include_secrets: bool = False) -> AISharedConfigResponse:
    payload = dict(ai_shared_config_db)
    if not include_secrets:
        payload["api_key"] = ""
        payload["tavily_api_key"] = ""
    return AISharedConfigResponse(**payload)


def _strip_html_tags(value: str) -> str:
    if not value:
        return ""
    text = re.sub(r"<[^>]+>", " ", value)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _decode_duckduckgo_redirect(url: str) -> str:
    value = html.unescape(url or "").strip()
    if not value:
        return ""
    parsed = urlparse(value)
    if "duckduckgo.com" in parsed.netloc and parsed.path.startswith("/l/"):
        uddg = parse_qs(parsed.query).get("uddg")
        if uddg and uddg[0]:
            return unquote(uddg[0])
    return value


def _extract_duckduckgo_results(html_text: str, limit: int) -> List[Dict[str, str]]:
    link_pattern = re.compile(
        r'<a[^>]*class="result__a"[^>]*href="(?P<url>[^"]+)"[^>]*>(?P<title>.*?)</a>',
        re.IGNORECASE | re.DOTALL,
    )
    snippet_pattern = re.compile(
        r'class="result__snippet"[^>]*>(?P<snippet>.*?)</',
        re.IGNORECASE | re.DOTALL,
    )

    output: List[Dict[str, str]] = []
    seen_urls = set()
    for link_match in link_pattern.finditer(html_text or ""):
        url = _decode_duckduckgo_redirect(link_match.group("url"))
        if not url or url in seen_urls:
            continue

        title = _strip_html_tags(link_match.group("title"))
        nearby_html = (html_text or "")[link_match.end(): link_match.end() + 2200]
        snippet_match = snippet_pattern.search(nearby_html)
        snippet = _strip_html_tags(snippet_match.group("snippet")) if snippet_match else ""

        output.append({
            "title": title or url,
            "url": url,
            "snippet": snippet[:240],
        })
        seen_urls.add(url)
        if len(output) >= limit:
            break
    return output


def _extract_bing_results(html_text: str, limit: int) -> List[Dict[str, str]]:
    pattern = re.compile(
        r'<li class="b_algo".*?<a href="(?P<url>[^"]+)"[^>]*>(?P<title>.*?)</a>.*?(?:<p>(?P<snippet>.*?)</p>)?',
        re.IGNORECASE | re.DOTALL,
    )

    output: List[Dict[str, str]] = []
    seen_urls = set()
    for match in pattern.finditer(html_text or ""):
        url = html.unescape(match.group("url") or "").strip()
        if not url or url in seen_urls:
            continue
        title = _strip_html_tags(match.group("title"))
        snippet = _strip_html_tags(match.group("snippet") or "")
        output.append({
            "title": title or url,
            "url": url,
            "snippet": snippet[:240],
        })
        seen_urls.add(url)
        if len(output) >= limit:
            break
    return output


def _extract_bing_rss_results(xml_text: str, limit: int) -> List[Dict[str, str]]:
    output: List[Dict[str, str]] = []
    seen_urls = set()

    if not xml_text:
        return output

    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return output

    for item in root.findall(".//item"):
        url = (item.findtext("link") or "").strip()
        if not url or url in seen_urls:
            continue

        title = html.unescape((item.findtext("title") or "").strip())
        snippet = html.unescape((item.findtext("description") or "").strip())
        output.append({
            "title": title or url,
            "url": url,
            "snippet": _strip_html_tags(snippet)[:240],
        })
        seen_urls.add(url)
        if len(output) >= limit:
            break

    return output


def _extract_duckduckgo_instant_results(payload: Dict, limit: int) -> List[Dict[str, str]]:
    output: List[Dict[str, str]] = []
    seen_urls = set()

    def _append_result(title: str, url: str, snippet: str):
        cleaned_url = (url or "").strip()
        if not cleaned_url or cleaned_url in seen_urls:
            return
        output.append({
            "title": (title or cleaned_url).strip(),
            "url": cleaned_url,
            "snippet": (snippet or "").strip()[:240],
        })
        seen_urls.add(cleaned_url)

    abstract = _strip_html_tags(str(payload.get("AbstractText") or ""))
    abstract_url = str(payload.get("AbstractURL") or "").strip()
    abstract_title = str(payload.get("Heading") or "").strip() or abstract_url
    if abstract and abstract_url:
        _append_result(abstract_title, abstract_url, abstract)

    related = payload.get("RelatedTopics") or []
    for item in related:
        if len(output) >= limit:
            break

        if isinstance(item, dict) and isinstance(item.get("Topics"), list):
            topics = item.get("Topics") or []
        else:
            topics = [item]

        for topic in topics:
            if len(output) >= limit:
                break
            if not isinstance(topic, dict):
                continue
            topic_url = str(topic.get("FirstURL") or "").strip()
            topic_text = _strip_html_tags(str(topic.get("Text") or ""))
            topic_title = topic_text.split(" - ", 1)[0] if topic_text else topic_url
            _append_result(topic_title, topic_url, topic_text)

    return output[:limit]


def _resolve_tavily_api_key() -> str:
    shared_key = _normalize_text(ai_shared_config_db.get("tavily_api_key"))
    if shared_key:
        return shared_key[:512]
    return TAVILY_API_KEY[:512]


def _cleanup_ai_web_search_cache(now_ts: Optional[float] = None):
    now_value = float(now_ts if now_ts is not None else time.time())

    expired = [
        key
        for key, item in ai_web_search_cache_db.items()
        if float(item.get("expires_at") or 0.0) <= now_value
    ]
    for key in expired:
        ai_web_search_cache_db.pop(key, None)

    if len(ai_web_search_cache_db) <= AI_WEB_SEARCH_CACHE_MAX_ITEMS:
        return

    sorted_items = sorted(
        ai_web_search_cache_db.items(),
        key=lambda pair: float((pair[1] or {}).get("expires_at") or 0.0),
    )
    overflow = len(sorted_items) - AI_WEB_SEARCH_CACHE_MAX_ITEMS
    for key, _ in sorted_items[:overflow]:
        ai_web_search_cache_db.pop(key, None)


def _build_ai_web_search_cache_key(query: str, limit: int, search_depth: str) -> str:
    normalized_query = _normalize_text(query).lower()
    normalized_depth = "advanced" if _normalize_text(search_depth).lower() == "advanced" else "basic"
    normalized_limit = max(1, min(int(limit or 5), 10))
    return f"{normalized_query}|{normalized_depth}|{normalized_limit}"


def _get_ai_web_search_cache(query: str, limit: int, search_depth: str) -> Optional[Dict]:
    _cleanup_ai_web_search_cache()
    key = _build_ai_web_search_cache_key(query, limit, search_depth)
    payload = ai_web_search_cache_db.get(key) or {}
    cached_data = payload.get("data")
    return deepcopy(cached_data) if isinstance(cached_data, dict) else None


def _set_ai_web_search_cache(query: str, limit: int, search_depth: str, payload: Dict):
    if not isinstance(payload, dict):
        return
    _cleanup_ai_web_search_cache()
    key = _build_ai_web_search_cache_key(query, limit, search_depth)
    ai_web_search_cache_db[key] = {
        "expires_at": time.time() + AI_WEB_SEARCH_CACHE_TTL_SECONDS,
        "data": deepcopy(payload),
    }


def _choose_search_depth(query: str) -> str:
    normalized = (query or "").strip().lower()
    if not normalized:
        return "basic"

    advanced_patterns = [
        r"(深度|深入|详细|系统|全面|综述|对比|研究|报告|分析|多来源|论文)",
        r"(advanced|in depth|deep dive|research|compare|benchmark)",
    ]
    if any(re.search(pattern, normalized) for pattern in advanced_patterns):
        return "advanced"

    # 默认优先 basic，降低延迟。
    return "basic"


def _search_with_tavily(query: str, limit: int, search_depth: str = "basic") -> List[Dict[str, str]]:
    api_key = _resolve_tavily_api_key()
    if not api_key:
        return []
    if TavilyClient is None:
        raise RuntimeError("tavily-python dependency is not installed")

    client = TavilyClient(api_key)
    normalized_depth = "advanced" if _normalize_text(search_depth).lower() == "advanced" else "basic"
    max_results = max(1, min(int(limit or 5), 10 if normalized_depth == "advanced" else 5))
    payload = client.search(
        query=query,
        search_depth=normalized_depth,
        max_results=max_results,
        include_answer=True,
        include_raw_content=False,
    ) or {}

    raw_results = payload.get("results") if isinstance(payload, dict) else []
    output: List[Dict[str, str]] = []
    seen_urls = set()
    for item in raw_results or []:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or "").strip()
        if not url or url in seen_urls:
            continue
        title = _strip_html_tags(str(item.get("title") or ""))
        snippet = _strip_html_tags(str(item.get("content") or item.get("snippet") or ""))
        output.append({
            "title": title or url,
            "url": url,
            "snippet": snippet[:500],
        })
        seen_urls.add(url)
        if len(output) >= max_results:
            break
    return output


def _build_web_search_context(results: List[Dict[str, str]]) -> str:
    if not results:
        return ""
    lines: List[str] = []
    for index, item in enumerate(results, start=1):
        title = str(item.get("title") or "").strip() or "Untitled"
        url = str(item.get("url") or "").strip()
        snippet = str(item.get("snippet") or "").strip() or "N/A"
        if not url:
            continue
        lines.append(f"{index}. {title}\nURL: {url}\nSummary: {snippet}")
    if not lines:
        return ""
    return f"[WEB_SEARCH_CONTEXT_START]\n{chr(10).join(lines)}\n[WEB_SEARCH_CONTEXT_END]"


def _run_web_search(query: str, limit: int) -> Dict:
    normalized_query = (query or "").strip()
    if not normalized_query:
        raise HTTPException(status_code=400, detail="query 不能为空")

    safe_limit = max(1, min(int(limit or 5), 8))
    search_depth = _choose_search_depth(normalized_query)
    cache_payload = _get_ai_web_search_cache(normalized_query, safe_limit, search_depth)
    if cache_payload:
        cache_payload["cached"] = True
        return cache_payload

    search_queries = _build_search_queries(normalized_query)
    search_errors: List[str] = []
    results: List[Dict[str, str]] = []
    provider = ""
    resolved_query = ""

    for search_query in search_queries:
        try:
            results = _search_with_tavily(search_query, safe_limit, search_depth)
            if results:
                provider = f"tavily-{search_depth}"
                resolved_query = search_query
                break
        except Exception as exc:
            search_errors.append(f"Tavily [{search_query}]: {exc}")

    for search_query in search_queries:
        if results:
            break
        try:
            ddg_html = _request_search_html("https://duckduckgo.com/html/", data={"q": search_query})
            results = _extract_duckduckgo_results(ddg_html, safe_limit)
            provider = "duckduckgo"
            if results:
                resolved_query = search_query
                break
        except requests.RequestException as exc:
            search_errors.append(f"DuckDuckGo [{search_query}]: {exc}")

    if not results:
        for search_query in search_queries:
            try:
                bing_html = _request_search_html(
                    "https://www.bing.com/search",
                    params={"q": search_query, "ensearch": "1"},
                )
                results = _extract_bing_results(bing_html, safe_limit)
                provider = "bing"
                if results:
                    resolved_query = search_query
                    break
            except requests.RequestException as exc:
                search_errors.append(f"Bing [{search_query}]: {exc}")

    if not results:
        for search_query in search_queries:
            try:
                bing_rss = _request_search_html(
                    "https://www.bing.com/search",
                    params={"q": search_query, "format": "rss"},
                )
                results = _extract_bing_rss_results(bing_rss, safe_limit)
                provider = "bing-rss"
                if results:
                    resolved_query = search_query
                    break
            except requests.RequestException as exc:
                search_errors.append(f"Bing RSS [{search_query}]: {exc}")

    if not results:
        for search_query in search_queries:
            try:
                ddg_response = requests.get(
                    "https://api.duckduckgo.com/",
                    params={
                        "q": search_query,
                        "format": "json",
                        "no_html": "1",
                        "no_redirect": "1",
                        "skip_disambig": "1",
                    },
                    timeout=12,
                    headers={
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                    },
                )
                ddg_response.raise_for_status()
                results = _extract_duckduckgo_instant_results(ddg_response.json(), safe_limit)
                provider = "duckduckgo-instant"
                if results:
                    resolved_query = search_query
                    break
            except (requests.RequestException, ValueError) as exc:
                search_errors.append(f"DuckDuckGo Instant [{search_query}]: {exc}")

    if not results and search_errors:
        raise HTTPException(status_code=502, detail=f"联网搜索不可用：{'; '.join(search_errors)}")

    payload = {
        "query": normalized_query,
        "resolved_query": resolved_query or normalized_query,
        "provider": provider or "none",
        "search_depth": search_depth,
        "cached": False,
        "count": len(results),
        "results": results,
    }
    _set_ai_web_search_cache(normalized_query, safe_limit, search_depth, payload)
    return payload


def _chat_completions_url(base_url: str) -> str:
    normalized = _normalize_text(base_url).rstrip("/")
    if not normalized:
        normalized = DEFAULT_AI_SHARED_CONFIG["base_url"].rstrip("/")
    if normalized.endswith("/chat/completions"):
        return normalized
    if normalized.endswith("/v1"):
        return f"{normalized}/chat/completions"
    return f"{normalized}/v1/chat/completions"


def _call_ai_chat_model(*, model: str, messages: List[Dict], base_url: str, api_key: str) -> str:
    if not api_key:
        raise HTTPException(status_code=400, detail="AI API Key 未配置")

    url = _chat_completions_url(base_url)
    try:
        response = requests.post(
            url,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            json={
                "model": model,
                "stream": False,
                "messages": messages,
            },
            timeout=70,
        )
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"调用大模型失败：{exc}") from exc

    raw_text = response.text or ""
    try:
        payload = response.json() if raw_text else {}
    except ValueError:
        payload = {}

    if not response.ok:
        detail = ""
        if isinstance(payload, dict):
            detail = (
                str(((payload.get("error") or {}) if isinstance(payload.get("error"), dict) else {}).get("message") or "")
                or str(payload.get("message") or "")
            )
        detail = detail or raw_text[:300] or f"HTTP {response.status_code}"
        raise HTTPException(status_code=502, detail=f"大模型接口返回错误：{detail}")

    answer = ""
    if isinstance(payload, dict):
        choices = payload.get("choices")
        if isinstance(choices, list) and choices:
            first = choices[0] if isinstance(choices[0], dict) else {}
            message = first.get("message") if isinstance(first, dict) else {}
            if isinstance(message, dict):
                answer = str(message.get("content") or "").strip()

    if not answer:
        raise HTTPException(status_code=502, detail="大模型未返回有效内容")
    return answer


def _extract_json_object(text: str) -> Dict:
    raw = str(text or "").strip()
    if not raw:
        return {}
    try:
        payload = json.loads(raw)
        return payload if isinstance(payload, dict) else {}
    except ValueError:
        pass

    match = re.search(r"\{[\s\S]*\}", raw)
    if not match:
        return {}
    try:
        payload = json.loads(match.group(0))
        return payload if isinstance(payload, dict) else {}
    except ValueError:
        return {}


def _fallback_need_web_search_decision(message: str) -> Tuple[bool, str]:
    text = (message or "").strip().lower()
    if not text:
        return False, "空问题默认不联网"
    patterns = [
        r"(今天|现在|当前|最新|最近|实时|近期|新闻|价格|汇率|天气|股价|比分|赛程|票房|发布日期|官网)",
        r"(what\s+time|what\s+date|latest|news|price|weather|today|current|update)",
    ]
    for pattern in patterns:
        if re.search(pattern, text):
            return True, "规则判断为时效性问题"
    return False, "规则判断为常识/离线可答问题"


def _decide_need_web_search(*, message: str, model: str, base_url: str, api_key: str) -> Tuple[bool, str]:
    decision_system_prompt = (
        "你是联网搜索路由器。只判断当前问题是否需要联网搜索。"
        "当问题涉及时效性信息、最新数据、新闻、价格、天气、日期时间、官网动态时，need_web_search=true。"
        "纯编程解释、数学推导、通用概念、与时效无关内容时，need_web_search=false。"
        "必须只输出 JSON，不要输出其它文本，格式为："
        "{\"need_web_search\": true/false, \"reason\": \"<=30字\"}"
    )
    decision_messages = [
        {"role": "system", "content": decision_system_prompt},
        {"role": "user", "content": message},
    ]
    decision_answer = _call_ai_chat_model(
        model=model,
        messages=decision_messages,
        base_url=base_url,
        api_key=api_key,
    )
    payload = _extract_json_object(decision_answer)
    if not payload:
        return _fallback_need_web_search_decision(message)

    need_value = payload.get("need_web_search")
    if isinstance(need_value, bool):
        need_web_search = need_value
    elif isinstance(need_value, str):
        need_web_search = need_value.strip().lower() in {"1", "true", "yes", "y"}
    else:
        need_web_search, _ = _fallback_need_web_search_decision(message)

    reason = _normalize_text(payload.get("reason"))[:60]
    if not reason:
        reason = "AI已完成联网判定"
    return need_web_search, reason


def _request_search_html(url: str, *, params: Optional[dict] = None, data: Optional[dict] = None) -> str:
    method = "POST" if data is not None else "GET"
    response = requests.request(
        method,
        url,
        params=params,
        data=data,
        timeout=12,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        },
    )
    response.raise_for_status()
    response.encoding = response.encoding or "utf-8"
    return response.text


def _is_datetime_query(query: str) -> bool:
    normalized = (query or "").strip().lower()
    if not normalized:
        return False
    patterns = [
        r"(今天|现在|当前).*(几号|日期|时间|几点|星期)",
        r"(几号|日期|时间|几点|星期).*(今天|现在|当前)",
        r"(what\s+date|what\s+time|current\s+date|current\s+time|today's\s+date)",
        r"(北京时间|上海时间|中国时间|china\s+time|beijing\s+time)",
    ]
    return any(re.search(pattern, normalized) for pattern in patterns)


def _is_today_relative_query(query: str) -> bool:
    normalized = (query or "").strip().lower()
    if not normalized:
        return False
    patterns = [
        r"(今天|今日).*(发生了什么|发生什么|有什么|新闻|热点|头条|消息|动态|事件)",
        r"(发生了什么|发生什么|有什么新闻).*(今天|今日)",
        r"(today\s+news|what\s+happened\s+today|news\s+today)",
    ]
    return any(re.search(pattern, normalized) for pattern in patterns)


def _is_time_sensitive_query(query: str) -> bool:
    normalized = (query or "").strip().lower()
    if not normalized:
        return False
    patterns = [
        r"(今天|今日|现在|当前|最新|最近|实时|近期|刚刚|目前|最新消息|动态|新闻|热点|发生了什么)",
        r"(today|now|current|latest|recent|real[-\s]?time|breaking|news|updates)",
    ]
    return any(re.search(pattern, normalized) for pattern in patterns)


def _current_local_date_tokens() -> Dict[str, str]:
    now_local = datetime.now().astimezone()
    weekday_map = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    weekday = weekday_map[now_local.weekday()]
    return {
        "iso": now_local.strftime("%Y-%m-%d"),
        "cn": f"{now_local.year}年{now_local.month}月{now_local.day}日",
        "compact": now_local.strftime("%Y%m%d"),
        "weekday": weekday,
    }


def _build_search_queries(query: str) -> List[str]:
    base = (query or "").strip()
    if not base:
        return []

    if _is_today_relative_query(base):
        date_tokens = _current_local_date_tokens()
        candidates = [
            f"{base} {date_tokens['cn']}",
            f"{base} {date_tokens['iso']}",
            f"{date_tokens['cn']} {date_tokens['weekday']} 中国 新闻 热点",
            f"{date_tokens['iso']} China today news",
            base,
        ]
        output: List[str] = []
        for item in candidates:
            value = (item or "").strip()
            if value and value not in output:
                output.append(value)
        return output

    if _is_datetime_query(base):
        candidates = [
            f"{base} 实时日期 时间 星期",
            "中国 当前 日期 时间 北京时间 星期几",
            base,
        ]
        output: List[str] = []
        for item in candidates:
            value = (item or "").strip()
            if value and value not in output:
                output.append(value)
        return output

    if _is_time_sensitive_query(base):
        date_tokens = _current_local_date_tokens()
        year = date_tokens["iso"][:4]
        candidates = [
            f"{base} {year}",
            f"{base} 最新动态",
            base,
        ]
        output: List[str] = []
        for item in candidates:
            value = (item or "").strip()
            if value and value not in output:
                output.append(value)
        return output

    return [base]


def _request_network_time(url: str) -> Dict[str, str]:
    response = requests.get(
        url,
        timeout=8,
        allow_redirects=True,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Cache-Control": "no-cache",
        },
    )
    response.raise_for_status()
    date_header = (response.headers.get("Date") or "").strip()
    if not date_header:
        raise ValueError("response missing Date header")

    parsed = parsedate_to_datetime(date_header)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    local_time = parsed.astimezone()
    return {
        "source": url,
        "http_date": date_header,
        "utc_iso": parsed.astimezone(timezone.utc).isoformat(),
        "local_iso": local_time.isoformat(),
        "local_readable": local_time.strftime("%Y-%m-%d %H:%M:%S %Z"),
    }


def _fetch_network_time() -> Tuple[Optional[Dict[str, str]], List[str]]:
    providers = [
        "https://www.bing.com/",
        "https://www.baidu.com/",
        "https://www.cloudflare.com/",
    ]
    errors: List[str] = []
    for provider_url in providers:
        try:
            return _request_network_time(provider_url), errors
        except (requests.RequestException, ValueError) as exc:
            errors.append(f"{provider_url}: {exc}")
    return None, errors
