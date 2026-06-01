"""add course scoped resources

Revision ID: 20260510_0002
Revises: 20260220_0001
Create Date: 2026-05-10 00:00:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

from app.storage_config import POSTGRES_SCHEMA


revision: str = "20260510_0002"
down_revision: Union[str, None] = "20260220_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _schema() -> str | None:
    return POSTGRES_SCHEMA if POSTGRES_SCHEMA and POSTGRES_SCHEMA != "public" else None


def upgrade() -> None:
    bind = op.get_bind()
    schema = _schema()
    inspector = inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("resources", schema=schema)}
    if "course_id" not in columns:
        op.add_column("resources", sa.Column("course_id", sa.String(length=64), nullable=True), schema=schema)

    indexes = {index["name"] for index in inspector.get_indexes("resources", schema=schema)}
    if "ix_resources_course_id_created_at" not in indexes:
        op.create_index(
            "ix_resources_course_id_created_at",
            "resources",
            ["course_id", "created_at"],
            unique=False,
            schema=schema,
        )


def downgrade() -> None:
    schema = _schema()
    bind = op.get_bind()
    inspector = inspect(bind)
    indexes = {index["name"] for index in inspector.get_indexes("resources", schema=schema)}
    if "ix_resources_course_id_created_at" in indexes:
        op.drop_index("ix_resources_course_id_created_at", table_name="resources", schema=schema)

    columns = {column["name"] for column in inspector.get_columns("resources", schema=schema)}
    if "course_id" in columns:
        op.drop_column("resources", "course_id", schema=schema)
