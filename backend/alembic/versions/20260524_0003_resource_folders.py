"""add resource folders

Revision ID: 20260524_0003
Revises: 20260510_0002
Create Date: 2026-05-24 00:00:00
"""

from typing import Sequence, Union
import uuid

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect, text

from app.storage_config import POSTGRES_SCHEMA


revision: str = "20260524_0003"
down_revision: Union[str, None] = "20260510_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

DEFAULT_FOLDER_NAME = "默认文件夹"


def _schema() -> str | None:
    return POSTGRES_SCHEMA if POSTGRES_SCHEMA and POSTGRES_SCHEMA != "public" else None


def _qualified(table_name: str) -> str:
    schema = _schema()
    if schema:
        return f'"{schema}"."{table_name}"'
    return table_name


def upgrade() -> None:
    bind = op.get_bind()
    schema = _schema()
    inspector = inspect(bind)

    tables = set(inspector.get_table_names(schema=schema))
    if "resource_folders" not in tables:
        op.create_table(
            "resource_folders",
            sa.Column("id", sa.String(length=64), nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("owner_username", sa.String(length=128), nullable=False),
            sa.Column("created_by", sa.String(length=128), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("owner_username", "name", name="uq_resource_folders_owner_name"),
            schema=schema,
        )
        op.create_index("ix_resource_folders_owner_username", "resource_folders", ["owner_username"], schema=schema)
        op.create_index(
            "ix_resource_folders_owner_updated_at",
            "resource_folders",
            ["owner_username", "updated_at"],
            schema=schema,
        )

    columns = {column["name"] for column in inspector.get_columns("resources", schema=schema)}
    if "folder_id" not in columns:
        op.add_column("resources", sa.Column("folder_id", sa.String(length=64), nullable=True), schema=schema)

    indexes = {index["name"] for index in inspector.get_indexes("resources", schema=schema)}
    if "ix_resources_folder_id_created_at" not in indexes:
        op.create_index(
            "ix_resources_folder_id_created_at",
            "resources",
            ["folder_id", "created_at"],
            unique=False,
            schema=schema,
        )

    rows = bind.execute(
        text(
            f"""
            SELECT DISTINCT COALESCE(NULLIF(TRIM(created_by), ''), 'admin') AS owner_username
            FROM {_qualified("resources")}
            WHERE course_id IS NULL AND folder_id IS NULL
            """
        )
    ).mappings()
    for row in rows:
        owner = row["owner_username"]
        folder_id = str(uuid.uuid4())
        existing = bind.execute(
            text(
                f"""
                SELECT id FROM {_qualified("resource_folders")}
                WHERE owner_username = :owner AND name = :name
                LIMIT 1
                """
            ),
            {"owner": owner, "name": DEFAULT_FOLDER_NAME},
        ).scalar()
        if existing:
            folder_id = existing
        else:
            bind.execute(
                text(
                    f"""
                    INSERT INTO {_qualified("resource_folders")}
                    (id, name, owner_username, created_by, created_at, updated_at, version)
                    VALUES (:id, :name, :owner, :created_by, now(), now(), 1)
                    """
                ),
                {"id": folder_id, "name": DEFAULT_FOLDER_NAME, "owner": owner, "created_by": owner},
            )
        bind.execute(
            text(
                f"""
                UPDATE {_qualified("resources")}
                SET folder_id = :folder_id, updated_at = now()
                WHERE course_id IS NULL
                  AND folder_id IS NULL
                  AND COALESCE(NULLIF(TRIM(created_by), ''), 'admin') = :owner
                """
            ),
            {"folder_id": folder_id, "owner": owner},
        )


def downgrade() -> None:
    schema = _schema()
    inspector = inspect(op.get_bind())

    indexes = {index["name"] for index in inspector.get_indexes("resources", schema=schema)}
    if "ix_resources_folder_id_created_at" in indexes:
        op.drop_index("ix_resources_folder_id_created_at", table_name="resources", schema=schema)

    columns = {column["name"] for column in inspector.get_columns("resources", schema=schema)}
    if "folder_id" in columns:
        op.drop_column("resources", "folder_id", schema=schema)

    tables = set(inspector.get_table_names(schema=schema))
    if "resource_folders" in tables:
        op.drop_table("resource_folders", schema=schema)
