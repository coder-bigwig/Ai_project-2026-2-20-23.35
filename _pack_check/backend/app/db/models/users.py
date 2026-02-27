from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import Boolean, DateTime, Enum as SAEnum, Index, String, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base
from .mixins import TimestampVersionMixin, json_dict


class ClassroomORM(Base):
    __tablename__ = "classes"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    created_by: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class AuthUserRole(str, PyEnum):
    student = "student"
    teacher = "teacher"
    admin = "admin"


class AuthUserORM(Base):
    __tablename__ = "auth_users"
    __table_args__ = (
        Index("ix_auth_users_email_unique", "email", unique=True),
        Index("ix_auth_users_username", "username"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    username: Mapped[str | None] = mapped_column(String(128), nullable=True)
    role: Mapped[AuthUserRole] = mapped_column(
        SAEnum(AuthUserRole, name="auth_user_role", native_enum=False),
        nullable=False,
        default=AuthUserRole.student,
        server_default=text("'student'"),
    )
    password_hash: Mapped[str] = mapped_column(String(128), nullable=False, default="", server_default=text("''"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class UserORM(Base, TimestampVersionMixin):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("username", name="uq_users_username"),
        UniqueConstraint("student_id", name="uq_users_student_id"),
        Index("ix_users_role_username", "role", "username"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    username: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    real_name: Mapped[str] = mapped_column(String(255), nullable=False, default="", server_default=text("''"))
    student_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    class_name: Mapped[str] = mapped_column(String(255), nullable=False, default="", server_default=text("''"))
    admission_year: Mapped[str] = mapped_column(String(32), nullable=False, default="", server_default=text("''"))
    organization: Mapped[str] = mapped_column(String(255), nullable=False, default="", server_default=text("''"))
    phone: Mapped[str] = mapped_column(String(64), nullable=False, default="", server_default=text("''"))
    password_hash: Mapped[str] = mapped_column(String(128), nullable=False, default="", server_default=text("''"))
    security_question: Mapped[str] = mapped_column(String(255), nullable=False, default="", server_default=text("''"))
    security_answer_hash: Mapped[str] = mapped_column(String(128), nullable=False, default="", server_default=text("''"))
    created_by: Mapped[str] = mapped_column(String(128), nullable=False, default="", server_default=text("''"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("true"))
    extra: Mapped[dict] = mapped_column(JSONB, nullable=False, default=json_dict, server_default=text("'{}'::jsonb"))


class SecurityQuestionORM(Base, TimestampVersionMixin):
    __tablename__ = "security_questions"
    __table_args__ = (
        UniqueConstraint("username", name="uq_security_questions_username"),
        Index("ix_security_questions_role", "role"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    username: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(32), nullable=False, default="", server_default=text("''"))
    question: Mapped[str] = mapped_column(String(255), nullable=False, default="", server_default=text("''"))
    answer_hash: Mapped[str] = mapped_column(String(128), nullable=False, default="", server_default=text("''"))


class PasswordHashORM(Base, TimestampVersionMixin):
    __tablename__ = "password_hashes"
    __table_args__ = (
        UniqueConstraint("username", name="uq_password_hashes_username"),
        Index("ix_password_hashes_role", "role"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    username: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(32), nullable=False, default="", server_default=text("''"))
    password_hash: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default=text("''"))
