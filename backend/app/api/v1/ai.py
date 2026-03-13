from datetime import datetime, timezone
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.session import get_db
from ...repositories import KVStoreRepository
from ...services.identity_service import normalize_text, resolve_user_role


def _get_main_module():
    from ... import main
    return main


main = _get_main_module()
router = APIRouter()


async def _load_ai_shared_config(db: AsyncSession) -> dict:
    row = await KVStoreRepository(db).get("ai_shared_config")
    payload = row.value_json if row and isinstance(row.value_json, dict) else {}
    normalized = dict(main.DEFAULT_AI_SHARED_CONFIG)
    normalized.update(main._normalize_ai_shared_config(payload))
    return normalized


async def _save_ai_shared_config(db: AsyncSession, payload: dict) -> None:
    await KVStoreRepository(db).upsert("ai_shared_config", payload)
    await db.commit()


async def _load_ai_chat_history_map(db: AsyncSession) -> dict:
    row = await KVStoreRepository(db).get("ai_chat_history")
    payload = row.value_json if row and isinstance(row.value_json, dict) else {}
    output = {}
    for username, items in payload.items() if isinstance(payload, dict) else []:
        normalized_username = normalize_text(username)
        if not normalized_username:
            continue
        output[normalized_username] = main._normalize_chat_history_items(items)
    return output


async def _save_ai_chat_history_map(db: AsyncSession, payload: dict) -> None:
    await KVStoreRepository(db).upsert("ai_chat_history", payload)
    await db.commit()


async def _is_known_user(db: AsyncSession, username: str) -> bool:
    return bool(await resolve_user_role(db, username))


async def get_ai_shared_config(username: str, request: Request, db: AsyncSession = Depends(get_db)):
    normalized_user = normalize_text(username)
    if not normalized_user:
        raise HTTPException(status_code=400, detail="username不能为空")
    if not await _is_known_user(db, normalized_user):
        raise HTTPException(status_code=404, detail="用户不存在")
    main._require_ai_session(request, expected_username=normalized_user, allow_admin_override=True)
    config = await _load_ai_shared_config(db)
    sanitized = dict(config)
    sanitized["api_key"] = ""
    sanitized["tavily_api_key"] = ""
    return main.AISharedConfigResponse(**sanitized)


async def update_ai_shared_config(
    payload: main.AISharedConfigUpdateRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    teacher_username = normalize_text(payload.teacher_username)
    main._require_ai_session(request, expected_username=teacher_username, allow_admin_override=True)
    role = await resolve_user_role(db, teacher_username)
    if role not in {"teacher", "admin"}:
        raise HTTPException(status_code=403, detail="权限不足")

    updated = main._normalize_ai_shared_config(payload.dict())
    await _save_ai_shared_config(db, updated)
    sanitized = dict(updated)
    sanitized["api_key"] = ""
    sanitized["tavily_api_key"] = ""
    return main.AISharedConfigResponse(**sanitized)


async def get_ai_chat_history(username: str, request: Request, db: AsyncSession = Depends(get_db)):
    normalized_user = normalize_text(username)
    if not normalized_user:
        raise HTTPException(status_code=400, detail="username不能为空")
    if not await _is_known_user(db, normalized_user):
        raise HTTPException(status_code=404, detail="用户不存在")
    main._require_ai_session(request, expected_username=normalized_user, allow_admin_override=True)

    history_map = await _load_ai_chat_history_map(db)
    messages = history_map.get(normalized_user, [])
    return main.AIChatHistoryResponse(
        username=normalized_user,
        message_count=len(messages),
        messages=[main.AIChatHistoryMessage(**item) for item in messages],
    )


async def update_ai_chat_history(
    payload: main.AIChatHistoryUpdateRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    normalized_user = normalize_text(payload.username)
    if not normalized_user:
        raise HTTPException(status_code=400, detail="username不能为空")
    if not await _is_known_user(db, normalized_user):
        raise HTTPException(status_code=404, detail="用户不存在")
    main._require_ai_session(request, expected_username=normalized_user, allow_admin_override=True)

    history_map = await _load_ai_chat_history_map(db)
    raw_messages = [{"role": item.role, "content": item.content} for item in payload.messages]
    normalized_messages = main._normalize_chat_history_items(raw_messages)
    if normalized_messages:
        history_map[normalized_user] = normalized_messages
    else:
        history_map.pop(normalized_user, None)

    await _save_ai_chat_history_map(db, history_map)
    return main.AIChatHistoryResponse(
        username=normalized_user,
        message_count=len(normalized_messages),
        messages=[main.AIChatHistoryMessage(**item) for item in normalized_messages],
    )


async def ai_network_time(request: Request):
    main._require_ai_session(request)
    system_now = datetime.now().astimezone()
    network_time, errors = main._fetch_network_time()
    return {
        "network_available": bool(network_time),
        "network_time": network_time,
        "system_time": {
            "local_iso": system_now.isoformat(),
            "local_readable": system_now.strftime("%Y-%m-%d %H:%M:%S %Z"),
            "utc_iso": system_now.astimezone(timezone.utc).isoformat(),
        },
        "errors": errors[:3],
    }


async def ai_web_search(payload: main.AIWebSearchRequest, request: Request, db: AsyncSession = Depends(get_db)):
    main._require_ai_session(request)
    config = await _load_ai_shared_config(db)
    main._refresh_ai_shared_config_cache(config)
    return main._run_web_search(payload.query, payload.limit)


async def ai_chat_with_search(
    payload: main.AIChatWithSearchRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    username = normalize_text(payload.username)
    if not username:
        raise HTTPException(status_code=400, detail="username不能为空")
    if not await _is_known_user(db, username):
        raise HTTPException(status_code=404, detail="用户不存在")
    main._require_ai_session(request, expected_username=username, allow_admin_override=True)

    message = normalize_text(payload.message)
    if not message:
        raise HTTPException(status_code=400, detail="message不能为空")
    is_today_relative = main._is_today_relative_query(message)
    is_time_sensitive = main._is_time_sensitive_query(message)

    config = await _load_ai_shared_config(db)
    main._refresh_ai_shared_config_cache(config)

    model = normalize_text(payload.model) or normalize_text(config.get("chat_model")) or main.DEFAULT_AI_SHARED_CONFIG["chat_model"]
    base_url = normalize_text(config.get("base_url")) or main.DEFAULT_AI_SHARED_CONFIG["base_url"]
    api_key = normalize_text(config.get("api_key"))
    system_prompt = normalize_text(config.get("system_prompt")) or main.DEFAULT_AI_SHARED_CONFIG["system_prompt"]
    if not api_key:
        raise HTTPException(status_code=400, detail="AI 配置未保存 API Key，请先在教师端 AI 模块保存配置")

    need_web_search = bool(payload.use_web_search)
    search_decision_reason = "联网模式已关闭"
    if payload.use_web_search and payload.auto_web_search:
        try:
            need_web_search, search_decision_reason = main._decide_need_web_search(
                message=message,
                model=model,
                base_url=base_url,
                api_key=api_key,
            )
        except HTTPException:
            need_web_search, search_decision_reason = main._fallback_need_web_search_decision(message)
            search_decision_reason = f"AI decision failed, fallback rule used: {search_decision_reason}"
    elif payload.use_web_search:
        search_decision_reason = "联网模式强制开启（跳过 AI 判定）"

    search_provider = ""
    search_resolved_query = ""
    search_cached = False
    search_depth_used = ""
    search_results: List[Dict[str, str]] = []
    search_error = ""
    if need_web_search:
        try:
            search_payload = main._run_web_search(message, payload.search_limit)
            search_provider = str(search_payload.get("provider") or "")
            search_resolved_query = str(search_payload.get("resolved_query") or message)
            search_cached = bool(search_payload.get("cached"))
            search_depth_used = str(search_payload.get("search_depth") or "")
            raw_results = search_payload.get("results")
            if isinstance(raw_results, list):
                search_results = [item for item in raw_results if isinstance(item, dict)]
        except HTTPException as exc:
            search_error = str(exc.detail)

    search_context = main._build_web_search_context(search_results)

    system_parts = [system_prompt, main.AI_RESPONSE_STYLE_RULES]
    if is_time_sensitive:
        date_tokens = main._current_local_date_tokens()
        system_parts.append(
            f"Current server date is {date_tokens['cn']} ({date_tokens['iso']}). "
            "Do not present historical events as if they happened today. "
            "If search results are old, explicitly include the source date."
        )
    if search_context:
        system_parts.append(
            "如果用户消息包含 [WEB_SEARCH_CONTEXT_START]... [WEB_SEARCH_CONTEXT_END]，"
            "必须优先依据这些联网检索内容回答。"
            "回答时在对应句子后使用 [1] [2] 这类编号标注来源，编号对应检索上下文条目。"
            "若没有可用来源，不要编造链接。"
        )
    final_system_prompt = "\n".join(part for part in system_parts if part)

    messages: List[Dict[str, str]] = [{"role": "system", "content": final_system_prompt}]
    raw_history = payload.history if isinstance(payload.history, list) else []
    trimmed_history = [] if is_today_relative else main._trim_ai_history_for_context(raw_history)
    for item in trimmed_history:
        messages.append({"role": item.get("role", "user"), "content": str(item.get("content") or "")})

    user_content = message
    if search_context:
        user_content = f"{message}\n\n{search_context}"
    messages.append({"role": "user", "content": user_content})

    answer = main._call_ai_chat_model(model=model, messages=messages, base_url=base_url, api_key=api_key)
    return {
        "answer": answer,
        "model": model,
        "search_decision": {"need_web_search": bool(need_web_search), "reason": search_decision_reason},
        "search_provider": search_provider,
        "search_resolved_query": search_resolved_query or message,
        "search_cached": search_cached,
        "search_depth": search_depth_used,
        "search_results": search_results[:8],
        "search_error": search_error,
    }


async def ai_code_review(code: str, language: str = "python"):
    return {
        "issues": [
            {"line": 5, "type": "warning", "message": "变量名不规范"},
            {"line": 12, "type": "error", "message": "缺少异常处理"},
        ],
        "suggestions": ["建议添加类型注解", "考虑使用列表推导式优化性能"],
        "overall_score": 85,
    }


async def ai_explain_code(code: str):
    return {"explanation": "这段代码实现了...", "key_concepts": ["循环", "条件判断", "列表操作"], "complexity": "O(n)"}


async def ai_debug_help(code: str, error_message: str):
    return {"possible_causes": ["数组越界", "类型不匹配"], "suggestions": ["检查循环索引范围", "使用try-except捕获异常"], "fixed_code": "# 修复后的代码..."}


async def ai_chat(question: str, context: Optional[str] = None):
    return {"answer": "根据你的问题...", "related_topics": ["Python基础", "数据结构"], "references": ["官方文档链接"]}


router.add_api_route("/api/ai/config", get_ai_shared_config, methods=["GET"], response_model=main.AISharedConfigResponse)
router.add_api_route("/api/ai/config", update_ai_shared_config, methods=["PUT"], response_model=main.AISharedConfigResponse)
router.add_api_route("/api/ai/chat-history", get_ai_chat_history, methods=["GET"], response_model=main.AIChatHistoryResponse)
router.add_api_route("/api/ai/chat-history", update_ai_chat_history, methods=["PUT"], response_model=main.AIChatHistoryResponse)
router.add_api_route("/api/ai/network-time", ai_network_time, methods=["GET"])
router.add_api_route("/api/ai/web-search", ai_web_search, methods=["POST"])
router.add_api_route("/api/ai/chat-with-search", ai_chat_with_search, methods=["POST"])
router.add_api_route("/api/ai/code-review", ai_code_review, methods=["POST"])
router.add_api_route("/api/ai/explain-code", ai_explain_code, methods=["POST"])
router.add_api_route("/api/ai/debug-help", ai_debug_help, methods=["POST"])
router.add_api_route("/api/ai/chat", ai_chat, methods=["POST"])
