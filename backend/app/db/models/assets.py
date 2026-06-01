from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base
from .mixins import TimestampVersionMixin


class ResourceFolderORM(Base, TimestampVersionMixin):
    __tablename__ = "resource_folders"
    __table_args__ = (
        Index("ux_resource_folders_owner_course_name", "owner_username", "course_id", "name", unique=True),
        Index("ix_resource_folders_owner_updated_at", "owner_username", "updated_at"),
        Index("ix_resource_folders_course_updated_at", "course_id", "updated_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    owner_username: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    created_by: Mapped[str] = mapped_column(String(128), nullable=False, default="", server_default=text("''"))
    course_id: Mapped[str | None] = mapped_column(String(64), nullable=True)


class ResourceORM(Base, TimestampVersionMixin):
    __tablename__ = "resources"
    __table_args__ = (
        Index("ix_resources_created_by_created_at", "created_by", "created_at"),
        Index("ix_resources_course_id_created_at", "course_id", "created_at"),
        Index("ix_resources_folder_id_created_at", "folder_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    file_type: Mapped[str] = mapped_column(String(64), nullable=False, default="", server_default=text("''"))
    content_type: Mapped[str] = mapped_column(String(255), nullable=False, default="", server_default=text("''"))
    size: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    created_by: Mapped[str] = mapped_column(String(128), nullable=False, default="", server_default=text("''"), index=True)
    course_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    folder_id: Mapped[str | None] = mapped_column(String(64), nullable=True)


class AttachmentORM(Base, TimestampVersionMixin):
    __tablename__ = "attachments"
    __table_args__ = (
        Index("ix_attachments_experiment_created_at", "experiment_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    experiment_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("experiments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    content_type: Mapped[str] = mapped_column(String(255), nullable=False, default="", server_default=text("''"))
    size: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))


class OperationLogORM(Base):
    __tablename__ = "operation_logs"
    __table_args__ = (
        Index("ix_operation_logs_operator_created_at", "operator", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    operator: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    target: Mapped[str] = mapped_column(String(255), nullable=False, default="", server_default=text("''"))
    detail: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default=text("''"))
    success: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)


class AIInvocationLogORM(Base):
    __tablename__ = "ai_invocation_logs"
    __table_args__ = (
        Index("ix_ai_invocation_logs_source_created_at", "source", "created_at"),
        Index("ix_ai_invocation_logs_username_created_at", "username", "created_at"),
        Index("ix_ai_invocation_logs_endpoint_created_at", "endpoint", "created_at"),
        Index("ix_ai_invocation_logs_success_created_at", "success", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source: Mapped[str] = mapped_column(String(64), nullable=False, default="", server_default=text("''"), index=True)
    endpoint: Mapped[str] = mapped_column(String(128), nullable=False, default="", server_default=text("''"), index=True)
    username: Mapped[str] = mapped_column(String(128), nullable=False, default="", server_default=text("''"), index=True)
    role: Mapped[str] = mapped_column(String(32), nullable=False, default="", server_default=text("''"))
    model: Mapped[str] = mapped_column(String(128), nullable=False, default="", server_default=text("''"))
    provider: Mapped[str] = mapped_column(String(128), nullable=False, default="", server_default=text("''"))
    success: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("true"), index=True)
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    prompt_chars: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    response_chars: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    history_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    used_search: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"), index=True)
    search_provider: Mapped[str] = mapped_column(String(128), nullable=False, default="", server_default=text("''"))
    search_depth: Mapped[str] = mapped_column(String(32), nullable=False, default="", server_default=text("''"))
    search_cached: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
    search_result_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    cache_hit_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    error: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default=text("''"))
    request_id: Mapped[str] = mapped_column(String(128), nullable=False, default="", server_default=text("''"), index=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)


class AppKVStoreORM(Base):
    __tablename__ = "app_kv_store"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
