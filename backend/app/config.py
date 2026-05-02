from typing import List
import os
import re


def _parse_int_env(name: str, default: int) -> int:
    raw = str(os.getenv(name, str(default)) or str(default)).strip()
    try:
        return int(raw)
    except ValueError:
        return default

APP_TITLE = "福州理工学院AI编程实践教学平台 - 实验管理API"

JUPYTERHUB_INTERNAL_URL = os.getenv("JUPYTERHUB_INTERNAL_URL", "http://jupyterhub:8000").rstrip("/")
# Prefer same-origin reverse-proxy path to avoid cross-origin cookie/WebSocket auth mismatches.
JUPYTERHUB_PUBLIC_URL = os.getenv("JUPYTERHUB_PUBLIC_URL", "/jupyter").rstrip("/")
JUPYTERHUB_API_TOKEN = os.getenv("JUPYTERHUB_API_TOKEN", "").strip()
JUPYTERHUB_REQUEST_TIMEOUT_SECONDS = float(os.getenv("JUPYTERHUB_REQUEST_TIMEOUT_SECONDS", "30"))
JUPYTERHUB_START_TIMEOUT_SECONDS = float(os.getenv("JUPYTERHUB_START_TIMEOUT_SECONDS", "180"))
# Keep user browser sessions stable for long classes.
JUPYTERHUB_USER_TOKEN_EXPIRES_SECONDS = int(os.getenv("JUPYTERHUB_USER_TOKEN_EXPIRES_SECONDS", "43200"))
JUPYTER_WORKSPACE_UI = str(os.getenv("JUPYTER_WORKSPACE_UI", "lab") or "").strip().lower()
ENABLE_CODE_SERVER = str(os.getenv("ENABLE_CODE_SERVER", "1") or "").strip().lower() not in {"0", "false", "no", "off"}
CODE_SERVER_PORT = max(1024, _parse_int_env("CODE_SERVER_PORT", 13337))
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "").strip()

def _parse_account_list(raw: str) -> List[str]:
    parts = [item.strip() for item in str(raw or "").split(",")]
    return [item for item in parts if item]


# 教师账号列表
TEACHER_ACCOUNTS = _parse_account_list(
    os.getenv("TEACHER_ACCOUNTS", "teacher_001,teacher_002,teacher_003,teacher_004,teacher_005")
)
ADMIN_ACCOUNTS = _parse_account_list(os.getenv("ADMIN_ACCOUNTS", "fit_admin"))
DEFAULT_PASSWORD = os.getenv("DEFAULT_PASSWORD", "fit350506")
UPLOAD_DIR = "/app/uploads"
SEED_MARKER_FILE = os.path.join(UPLOAD_DIR, ".seed_defaults_v1")  # legacy filename (kept for backward compat)
TEXT_PREVIEW_CHAR_LIMIT = 20000
ALLOWED_RESOURCE_EXTENSIONS = {
    ".pdf",
    ".doc",
    ".docx",
    ".md",
    ".markdown",
    ".txt",
    ".csv",
    ".json",
    ".ppt",
    ".pptx",
    ".xls",
    ".xlsx",
}
TEMPLATE_HEADERS = ["学号", "姓名", "班级", "单位名称", "手机号", "入学年级"]
LEGACY_TEMPLATE_HEADERS = TEMPLATE_HEADERS[:5]
DEFAULT_ADMISSION_YEAR_OPTIONS = ["2020", "2021", "2022", "2023", "2024", "2025", "2026", "2027", "2028"]
CLASS_TEMPLATE_HEADERS = ["入学年级", "专业", "班级"]
DEFAULT_AI_SHARED_CONFIG = {
    "api_key": "",
    "tavily_api_key": "",
    "chat_model": "deepseek-chat",
    "reasoner_model": "deepseek-reasoner",
    "base_url": "https://api.deepseek.com",
    "system_prompt": "你是福州理工学院AI编程实践教学平台小助手。请使用简洁、准确、教学友好的中文回答。"
}
AI_RESPONSE_STYLE_RULES = (
    "回答规则：先给结论，再给关键依据或步骤；"
    "代码问题优先给最小可运行示例；"
    "避免空话和套话，不要编造事实；"
    "不确定时明确写“我不确定/需要进一步检索确认”。"
)
DEFAULT_RESOURCE_ROLE_LIMITS = {
    "student": {"cpu_limit": 2.0, "memory_limit": "8G", "storage_limit": "2G"},
    "teacher": {"cpu_limit": 2.0, "memory_limit": "8G", "storage_limit": "2G"},
    "admin": {"cpu_limit": 4.0, "memory_limit": "8G", "storage_limit": "20G"},
}
DEFAULT_SERVER_RESOURCE_BUDGET = {
    "max_total_cpu": 64.0,
    "max_total_memory": "128G",
    "max_total_storage": "1T",
    "enforce_budget": False,
}
MAX_OPERATION_LOG_ITEMS = 5000
AI_CHAT_HISTORY_MAX_MESSAGES = max(20, int(os.getenv("AI_CHAT_HISTORY_MAX_MESSAGES", "240")))
AI_CHAT_HISTORY_MAX_MESSAGE_CHARS = max(1000, int(os.getenv("AI_CHAT_HISTORY_MAX_MESSAGE_CHARS", "12000")))
AI_CONTEXT_MAX_HISTORY_MESSAGES = max(10, int(os.getenv("AI_CONTEXT_MAX_HISTORY_MESSAGES", "80")))
AI_CONTEXT_MAX_TOTAL_CHARS = max(4000, int(os.getenv("AI_CONTEXT_MAX_TOTAL_CHARS", "48000")))
AI_SESSION_TTL_SECONDS = max(900, int(os.getenv("AI_SESSION_TTL_SECONDS", "43200")))
AI_SESSION_MAX_TOKENS = max(100, int(os.getenv("AI_SESSION_MAX_TOKENS", "5000")))
AI_WEB_SEARCH_CACHE_TTL_SECONDS = max(60, int(os.getenv("AI_WEB_SEARCH_CACHE_TTL_SECONDS", "3600")))
AI_WEB_SEARCH_CACHE_MAX_ITEMS = max(50, int(os.getenv("AI_WEB_SEARCH_CACHE_MAX_ITEMS", "1000")))
PASSWORD_HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")

os.makedirs(UPLOAD_DIR, exist_ok=True)
