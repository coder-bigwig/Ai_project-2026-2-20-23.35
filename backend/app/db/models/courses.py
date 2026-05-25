from sqlalchemy import Index, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base
from .mixins import TimestampVersionMixin


class CourseORM(Base, TimestampVersionMixin):
    __tablename__ = "courses"
    __table_args__ = (
        UniqueConstraint("created_by", "name", name="uq_courses_created_by_name"),
        Index("ix_courses_created_by_updated_at", "created_by", "updated_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default=text("''"))
    created_by: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
