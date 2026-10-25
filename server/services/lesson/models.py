"""Ako database models.

Author: Sandhya Tiwari
Date: 25 Oct 2026
"""

from uuid import uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    String,
    Table,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


def id_col():
    return Column("id", UUID(as_uuid=True), primary_key=True, default=uuid4)


def timestamps():
    return [
        Column(
            "created_at",
            DateTime(timezone=True),
            nullable=False,
            server_default=func.now(),
        ),
        Column(
            "updated_at",
            DateTime(timezone=True),
            nullable=False,
            server_default=func.now(),
        ),
    ]


def ref(name, target=None, nullable=False):
    return (
        Column(name, UUID(as_uuid=True), ForeignKey(target), nullable=nullable)
        if target
        else Column(name, UUID(as_uuid=True), nullable=nullable)
    )


def value(name, typ, nullable=False, unique=False):
    return Column(name, typ, nullable=nullable, unique=unique)


lessons = Table(
    "lessons",
    Base.metadata,
    id_col(),
    value("title", String(255)),
    value("description", Text, nullable=True),
    value("lesson_date", Date),
    ref("created_by"),
    ref("source_lesson_id", "lessons.id", nullable=True),
    Column("has_maori_content", Boolean, nullable=False, server_default=text("false")),
    Column(
        "review_status",
        String(20),
        nullable=False,
        server_default=text("'not_required'"),
    ),
    ref("reviewed_by", nullable=True),
    value("reviewed_at", DateTime(timezone=True), nullable=True),
    value("reviewer_name", String(150), nullable=True),
    value("review_date", Date, nullable=True),
    *timestamps(),
    value("deleted_at", DateTime(timezone=True), nullable=True),
    CheckConstraint(
        "review_status IN ('not_required','pending','reviewed','rejected')"
    ),
    CheckConstraint("has_maori_content OR review_status = 'not_required'"),
    Index("ix_lessons_date", "lesson_date"),
    Index("ix_lessons_creator", "created_by"),
)

tags = Table(
    "tags",
    Base.metadata,
    id_col(),
    value("name", String(100), unique=True),
    Column(
        "created_at", DateTime(timezone=True), nullable=False, server_default=func.now()
    ),
)

lesson_tags = Table(
    "lesson_tags",
    Base.metadata,
    Column("lesson_id", UUID(as_uuid=True), ForeignKey("lessons.id"), primary_key=True),
    Column("tag_id", UUID(as_uuid=True), ForeignKey("tags.id"), primary_key=True),
    Index("ix_lesson_tags_tag", "tag_id"),
)

lesson_materials = Table(
    "lesson_materials",
    Base.metadata,
    id_col(),
    ref("lesson_id", "lessons.id"),
    value("file_name", String(255)),
    value("storage_key", String(500)),
    value("mime_type", String(100)),
    value("file_size", BigInteger),
    Column(
        "share_with_learners", Boolean, nullable=False, server_default=text("false")
    ),
    ref("uploaded_by"),
    Column(
        "created_at", DateTime(timezone=True), nullable=False, server_default=func.now()
    ),
    value("deleted_at", DateTime(timezone=True), nullable=True),
    CheckConstraint("file_size >= 0"),
    Index("ix_material_lesson", "lesson_id"),
)

lesson_review_logs = Table(
    "lesson_review_logs",
    Base.metadata,
    id_col(),
    ref("lesson_id", "lessons.id"),
    value("review_status", String(20)),
    ref("reviewed_by"),
    value("comment", Text, nullable=True),
    Column(
        "created_at", DateTime(timezone=True), nullable=False, server_default=func.now()
    ),
    CheckConstraint("review_status IN ('pending','reviewed','rejected')"),
    Index("ix_review_log", "lesson_id", "created_at"),
)
