from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base
from .mixins import TimestampVersionMixin, json_dict, json_list


class StudentExperimentORM(Base, TimestampVersionMixin):
    __tablename__ = "submissions"
    __table_args__ = (
        UniqueConstraint("student_id", "experiment_id", name="uq_submissions_student_experiment"),
        Index("ix_submissions_student_status", "student_id", "status"),
        Index("ix_submissions_experiment_status", "experiment_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    experiment_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("experiments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    student_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="", server_default=text("''"), index=True)
    start_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    submit_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notebook_content: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default=text("''"))
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    ai_feedback: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default=text("''"))
    teacher_comment: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default=text("''"))
    extra: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=json_dict, server_default=text("'{}'::jsonb"))


# Keep backward-compatible import/usage name.
SubmissionORM = StudentExperimentORM


class SubmissionPdfORM(Base, TimestampVersionMixin):
    __tablename__ = "submission_pdfs"
    __table_args__ = (
        Index("ix_submission_pdfs_submission_created", "submission_id", "created_at"),
        Index("ix_submission_pdfs_experiment_student", "experiment_id", "student_id"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    submission_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("submissions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    experiment_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    student_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    content_type: Mapped[str] = mapped_column(String(255), nullable=False, default="", server_default=text("''"))
    size: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    viewed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
    viewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    viewed_by: Mapped[str] = mapped_column(String(128), nullable=False, default="", server_default=text("''"))
    reviewed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewed_by: Mapped[str] = mapped_column(String(128), nullable=False, default="", server_default=text("''"))
    annotations: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=json_list, server_default=text("'[]'::jsonb"))
