"""init core tables

Revision ID: 20260220_0001
Revises:
Create Date: 2026-02-20 12:00:00
"""

from typing import Sequence, Union

from alembic import op

from app.db.base import Base
from app.db import models  # noqa: F401

# revision identifiers, used by Alembic.
revision: str = "20260220_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
