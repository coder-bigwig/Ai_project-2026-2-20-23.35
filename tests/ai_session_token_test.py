from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.services import ai_service
from app.state import ai_session_tokens_db


def test_ai_session_token_survives_process_local_cache_loss():
    token = ai_service._create_ai_session_token("teacher_001")

    ai_session_tokens_db.clear()

    assert ai_service._resolve_ai_session_user(token) == "teacher_001"
