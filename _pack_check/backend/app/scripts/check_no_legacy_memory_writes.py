from __future__ import annotations

import re
import sys
from pathlib import Path

LEGACY_CACHE_NAMES = (
    "teachers_db",
    "students_db",
    "classes_db",
    "courses_db",
    "experiments_db",
    "student_experiments_db",
    "submission_pdfs_db",
    "resource_files_db",
    "attachments_db",
    "teacher_account_password_hashes_db",
    "account_security_questions_db",
    "operation_logs_db",
)

WRITE_REGEXES = (
    re.compile(rf"\b({'|'.join(LEGACY_CACHE_NAMES)})\s*\[[^\n]+\]\s*="),
    re.compile(rf"\b({'|'.join(LEGACY_CACHE_NAMES)})\.(clear|update|setdefault|pop|popitem|append|extend)\s*\("),
)

# `registry_store.py` is legacy compatibility code and remains quarantined.
ALLOWED_PATHS = {
    Path("backend/app/state.py").as_posix(),
    Path("backend/app/registry_store.py").as_posix(),
}


def main() -> int:
    repo_root = Path(__file__).resolve().parents[3]
    app_root = repo_root / "backend" / "app"
    offenders: list[str] = []

    for path in app_root.rglob("*.py"):
        rel = path.relative_to(repo_root).as_posix()
        if rel in ALLOWED_PATHS:
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            content = path.read_text(encoding="utf-8", errors="ignore")

        lines = content.splitlines()
        for idx, line in enumerate(lines, start=1):
            for regex in WRITE_REGEXES:
                if regex.search(line):
                    offenders.append(f"{rel}:{idx}: {line.strip()}")

    if offenders:
        print("Legacy in-memory write operations are forbidden:")
        for item in offenders:
            print(f" - {item}")
        return 1

    print("OK: no forbidden legacy in-memory writes found outside the quarantine modules.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
