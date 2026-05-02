from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base
from .mixins import TimestampVersionMixin, json_dict, json_list


class ExperimentORM(Base, TimestampVersionMixin):
    __tablename__ = "experiments"
    __table_args__ = (
        Index("ix_experiments_course_created_by", "course_id", "created_by"),
        Index("ix_experiments_published_deadline", "published", "deadline"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    course_id: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey("courses.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    course_name: Mapped[str] = mapped_column(String(255), nullable=False, default="", server_default=text("''"))
    title: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default=text("''"))
    difficulty: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="",
        server_default=text("''"),
        index=True,
    )
    tags: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=json_list, server_default=text("'[]'::jsonb"))
    notebook_path: Mapped[str] = mapped_column(String(500), nullable=False, default="", server_default=text("''"))
    resources: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=json_dict,
        server_default=text("'{}'::jsonb"),
    )
    deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    created_by: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    published: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("true"), index=True)
    publish_scope: Mapped[str] = mapped_column(String(32), nullable=False, default="all", server_default=text("'all'"))
    target_class_names: Mapped[list[Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=json_list,
        server_default=text("'[]'::jsonb"),
    )
    target_student_ids: Mapped[list[Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=json_list,
        server_default=text("'[]'::jsonb"),
    )
    extra: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=json_dict,
        server_default=text("'{}'::jsonb"),
    )
