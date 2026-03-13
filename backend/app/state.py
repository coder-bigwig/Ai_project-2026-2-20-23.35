"""Runtime in-memory caches.

Authoritative state is PostgreSQL. Legacy registry dicts are intentionally
write-blocked to avoid per-process divergence in multi-worker deployments.
"""

from typing import Dict, List

from .config import DEFAULT_AI_SHARED_CONFIG


class LegacyStateWriteBlockedError(RuntimeError):
    """Raised when legacy in-memory registries are mutated."""


class _LegacyStateWriteBlockedDict(dict):
    _name: str

    def __init__(self, name: str):
        super().__init__()
        self._name = name

    def _blocked(self, *_args, **_kwargs):
        raise LegacyStateWriteBlockedError(
            f"{self._name} is a legacy in-memory registry and is write-blocked. Use PostgreSQL repositories."
        )

    __setitem__ = _blocked
    __delitem__ = _blocked
    clear = _blocked
    pop = _blocked
    popitem = _blocked
    setdefault = _blocked
    update = _blocked


class _LegacyStateWriteBlockedList(list):
    _name: str

    def __init__(self, name: str):
        super().__init__()
        self._name = name

    def _blocked(self, *_args, **_kwargs):
        raise LegacyStateWriteBlockedError(
            f"{self._name} is a legacy in-memory registry and is write-blocked. Use PostgreSQL repositories."
        )

    append = _blocked
    clear = _blocked
    extend = _blocked
    insert = _blocked
    pop = _blocked
    remove = _blocked
    reverse = _blocked
    sort = _blocked
    __delitem__ = _blocked
    __setitem__ = _blocked


def _blocked_dict(name: str) -> Dict[str, object]:
    return _LegacyStateWriteBlockedDict(name)


def assert_legacy_state_write_blocked() -> None:
    targets = {
        "experiments_db": experiments_db,
        "courses_db": courses_db,
        "student_experiments_db": student_experiments_db,
        "classes_db": classes_db,
        "teachers_db": teachers_db,
        "students_db": students_db,
        "teacher_account_password_hashes_db": teacher_account_password_hashes_db,
        "account_security_questions_db": account_security_questions_db,
        "submission_pdfs_db": submission_pdfs_db,
        "resource_files_db": resource_files_db,
        "operation_logs_db": operation_logs_db,
        "attachments_db": attachments_db,
    }
    for name, value in targets.items():
        is_dict_target = isinstance(value, _LegacyStateWriteBlockedDict)
        is_list_target = isinstance(value, _LegacyStateWriteBlockedList)
        if not (is_dict_target or is_list_target):
            raise RuntimeError(f"{name} must stay write-blocked in runtime state.")


experiments_db: Dict[str, object] = _blocked_dict("experiments_db")
courses_db: Dict[str, object] = _blocked_dict("courses_db")
student_experiments_db: Dict[str, object] = _blocked_dict("student_experiments_db")
classes_db: Dict[str, object] = _blocked_dict("classes_db")
teachers_db: Dict[str, object] = _blocked_dict("teachers_db")
students_db: Dict[str, object] = _blocked_dict("students_db")
teacher_account_password_hashes_db: Dict[str, str] = _blocked_dict("teacher_account_password_hashes_db")
account_security_questions_db: Dict[str, Dict[str, str]] = _blocked_dict("account_security_questions_db")
submission_pdfs_db: Dict[str, object] = _blocked_dict("submission_pdfs_db")
resource_files_db: Dict[str, object] = _blocked_dict("resource_files_db")

# AI/session caches are process-local ephemera; not business source-of-truth.
ai_shared_config_db: Dict[str, str] = dict(DEFAULT_AI_SHARED_CONFIG)
ai_chat_history_db: Dict[str, List[Dict[str, str]]] = {}
ai_session_tokens_db: Dict[str, Dict[str, object]] = {}
ai_web_search_cache_db: Dict[str, Dict[str, object]] = {}
resource_policy_db: Dict[str, dict] = {}

operation_logs_db: List[object] = _LegacyStateWriteBlockedList("operation_logs_db")
attachments_db: Dict[str, object] = _blocked_dict("attachments_db")
