from __future__ import annotations

from typing import Any

from .identity_service import normalize_text


TEACHER_CLASS_NAMES_KEY = "teacher_class_names"


def _extra_dict(student_row) -> dict[str, Any]:
    extra = getattr(student_row, "extra", {})
    return extra if isinstance(extra, dict) else {}


def teacher_class_names(student_row) -> dict[str, str]:
    raw = _extra_dict(student_row).get(TEACHER_CLASS_NAMES_KEY)
    if not isinstance(raw, dict):
        return {}
    return {
        normalize_text(teacher): normalize_text(class_name)
        for teacher, class_name in raw.items()
        if normalize_text(teacher) and normalize_text(class_name)
    }


def class_name_for_teacher(student_row, teacher_username: str) -> str:
    teacher = normalize_text(teacher_username)
    if teacher:
        aliased = teacher_class_names(student_row).get(teacher, "")
        if aliased:
            return aliased
    return normalize_text(getattr(student_row, "class_name", ""))


def set_class_name_for_teacher(student_row, teacher_username: str, class_name: str) -> bool:
    teacher = normalize_text(teacher_username)
    normalized_class = normalize_text(class_name)
    if not teacher or not normalized_class:
        return False

    base_extra = _extra_dict(student_row)
    aliases = teacher_class_names(student_row)
    if aliases.get(teacher) == normalized_class:
        return False

    aliases[teacher] = normalized_class
    next_extra = dict(base_extra)
    next_extra[TEACHER_CLASS_NAMES_KEY] = dict(sorted(aliases.items()))
    student_row.extra = next_extra
    return True
