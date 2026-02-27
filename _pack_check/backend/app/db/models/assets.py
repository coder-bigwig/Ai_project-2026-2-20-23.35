from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base
from .mixins import TimestampVersionMixin


class ResourceORM(Base, TimestampVersionMixin):
    __tablename__ = "resources"
    __table_args__ = (
        Index("ix_resources_created_by_created_at", "created_by", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    file_type: Mapped[str] = mapped_column(String(64), nullable=False, default="", server_default=text("''"))
    content_type: Mapped[str] = mapped_column(String(255), nullable=False, default="", server_default=text("''"))
    size: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    created_by: Mapped[str] = mapped_column(String(128), nullable=False, default="", server_default=text("''"), index=True)


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
