"""add ai invocation logs

Revision ID: 20260529_0004
Revises: 20260524_0003
Create Date: 2026-05-29 00:00:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect, text
from sqlalchemy.dialects import postgresql

from app.storage_config import POSTGRES_SCHEMA


revision: str = "20260529_0004"
down_revision: Union[str, None] = "20260524_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _schema() -> str | None:
    return POSTGRES_SCHEMA if POSTGRES_SCHEMA and POSTGRES_SCHEMA != "public" else None


def upgrade() -> None:
    bind = op.get_bind()
    schema = _schema()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names(schema=schema))

    if "ai_invocation_logs" not in tables:
        op.create_table(
            "ai_invocation_logs",
            sa.Column("id", sa.String(length=64), nullable=False),
            sa.Column("source", sa.String(length=64), nullable=False, server_default=""),
            sa.Column("endpoint", sa.String(length=128), nullable=False, server_default=""),
            sa.Column("username", sa.String(length=128), nullable=False, server_default=""),
            sa.Column("role", sa.String(length=32), nullable=False, server_default=""),
            sa.Column("model", sa.String(length=128), nullable=False, server_default=""),
            sa.Column("provider", sa.String(length=128), nullable=False, server_default=""),
            sa.Column("success", sa.Boolean(), nullable=False, server_default=text("true")),
            sa.Column("status_code", sa.Integer(), nullable=True),
            sa.Column("latency_ms", sa.Float(), nullable=True),
            sa.Column("prompt_chars", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("response_chars", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("history_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("used_search", sa.Boolean(), nullable=False, server_default=text("false")),
            sa.Column("search_provider", sa.String(length=128), nullable=False, server_default=""),
            sa.Column("search_depth", sa.String(length=32), nullable=False, server_default=""),
            sa.Column("search_cached", sa.Boolean(), nullable=False, server_default=text("false")),
            sa.Column("search_result_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("cache_hit_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("error", sa.Text(), nullable=False, server_default=""),
            sa.Column("request_id", sa.String(length=128), nullable=False, server_default=""),
            sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=text("'{}'::jsonb")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.PrimaryKeyConstraint("id"),
            schema=schema,
        )

    indexes = {index["name"] for index in inspector.get_indexes("ai_invocation_logs", schema=schema)}
    index_specs = {
        "ix_ai_invocation_logs_source_created_at": ["source", "created_at"],
        "ix_ai_invocation_logs_username_created_at": ["username", "created_at"],
        "ix_ai_invocation_logs_endpoint_created_at": ["endpoint", "created_at"],
        "ix_ai_invocation_logs_success_created_at": ["success", "created_at"],
        "ix_ai_invocation_logs_created_at": ["created_at"],
        "ix_ai_invocation_logs_request_id": ["request_id"],
        "ix_ai_invocation_logs_used_search": ["used_search"],
    }
    for name, columns in index_specs.items():
        if name not in indexes:
            op.create_index(name, "ai_invocation_logs", columns, unique=False, schema=schema)


def downgrade() -> None:
    schema = _schema()
    inspector = inspect(op.get_bind())
    tables = set(inspector.get_table_names(schema=schema))
    if "ai_invocation_logs" in tables:
        op.drop_table("ai_invocation_logs", schema=schema)
