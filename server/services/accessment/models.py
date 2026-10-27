"""Define dated classes, attendance, lesson links and learner material grants.

Author: Shuohui Liu
Date: 19 Oct 2026
Updated: Sandhya Tiwari, 26 Oct 2026
"""
from uuid import uuid4

from sqlalchemy import (
    DDL,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    String,
    Table,
    Time,
    UniqueConstraint,
    event,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass

def id_col():
    """
    Define a UUID primary-key column with a generated UUID default.
    """
    return Column("id", UUID(as_uuid=True), primary_key=True, default=uuid4)

def timestamps():
    """
    Define database-managed creation and update timestamp columns.
    """
    return [Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()), Column("updated_at", DateTime(timezone=True), nullable=False, server_default=func.now())]

def ref(name, target=None, nullable=False):
    """
    Define a UUID reference column with an optional local foreign-key constraint.
    """
    return Column(name, UUID(as_uuid=True), ForeignKey(target), nullable=nullable) if target else Column(name, UUID(as_uuid=True), nullable=nullable)

def value(name, typ, nullable=False, unique=False):
    """
    Define a named SQLAlchemy value column with nullability and uniqueness options.
    """
    return Column(name, typ, nullable=nullable, unique=unique)


class_sessions = Table("class_sessions", Base.metadata,
    id_col(), value("session_date",Date), value("start_time",Time,nullable=True), value("end_time",Time,nullable=True), Column("status",String(20),nullable=False,server_default=text("'scheduled'")), ref("created_by"), *timestamps(), value("closed_at",DateTime(timezone=True),nullable=True), CheckConstraint("status IN ('scheduled','open','closed')"), CheckConstraint("start_time IS NULL OR end_time IS NULL OR end_time > start_time"), Index("ix_sessions_date","session_date")
)

attendance_records = Table("attendance_records", Base.metadata,
    id_col(), ref("session_id","class_sessions.id"), ref("learner_id"), value("status",String(20)), ref("recorded_by"), Column("recorded_at",DateTime(timezone=True),nullable=False,server_default=func.now()), ref("corrected_by",nullable=True), value("corrected_at",DateTime(timezone=True),nullable=True), UniqueConstraint("session_id","learner_id"), CheckConstraint("status IN ('present','absent')"), Index("ix_attendance_learner","learner_id")
)

attendance_audits = Table("attendance_audits", Base.metadata,
    id_col(), ref("attendance_id","attendance_records.id"), value("old_status",String(20)), value("new_status",String(20)), ref("corrected_by"), value("reason",String(500),nullable=True), Column("created_at",DateTime(timezone=True),nullable=False,server_default=func.now()), CheckConstraint("old_status IN ('present','absent')"), CheckConstraint("new_status IN ('present','absent')"), CheckConstraint("old_status <> new_status"), Index("ix_attendance_audit","attendance_id","created_at")
)

checkin_windows = Table("checkin_windows", Base.metadata,
    id_col(), ref("session_id","class_sessions.id"), value("token_hash",String(255),unique=True), ref("opened_by"), Column("opened_at",DateTime(timezone=True),nullable=False,server_default=func.now()), value("expires_at",DateTime(timezone=True)), value("closed_at",DateTime(timezone=True),nullable=True), CheckConstraint("expires_at > opened_at AND expires_at <= opened_at + INTERVAL '4 hours'"), Index("ix_checkin_session","session_id")
)

# US-012: wrong names typed at QR sign-in, for the 10-in-10-minutes limit.
# key_hash is an HMAC of the device's address, never the address itself, and
# rows older than an hour are deleted.
signin_failures = Table("signin_failures", Base.metadata,
    id_col(), value("key_hash",String(64)), Column("failed_at",DateTime(timezone=True),nullable=False), Index("ix_signin_failures_key","key_hash","failed_at")
)

# US-015: the change log is append-only (Test Plan UT-35). A trigger refuses
# UPDATE, DELETE and TRUNCATE on attendance_audits, so no code or person can
# rewrite history. It is added when the table is created; an existing
# database needs these statements once (database/database-schema.md).
APPEND_ONLY_AUDIT_SQL = (
    """CREATE OR REPLACE FUNCTION refuse_attendance_audit_change() RETURNS trigger
    LANGUAGE plpgsql AS $$
    BEGIN
        RAISE EXCEPTION 'attendance_audits is append-only';
    END
    $$""",
    "CREATE OR REPLACE TRIGGER attendance_audits_append_only "
    "BEFORE UPDATE OR DELETE ON attendance_audits "
    "FOR EACH ROW EXECUTE FUNCTION refuse_attendance_audit_change()",
    "CREATE OR REPLACE TRIGGER attendance_audits_no_truncate "
    "BEFORE TRUNCATE ON attendance_audits "
    "FOR EACH STATEMENT EXECUTE FUNCTION refuse_attendance_audit_change()",
)
# One statement per DDL: psycopg runs one statement per call.
for _statement in APPEND_ONLY_AUDIT_SQL:
    event.listen(attendance_audits, "after_create", DDL(_statement))

# US-014: one dated session, with at most one lesson stored in lessondb.
unique_session_date = Index(
    "uq_class_sessions_date", class_sessions.c.session_date, unique=True
)
session_lesson_links = Table(
    "session_lesson_links", Base.metadata,
    Column("session_id", UUID(as_uuid=True),
           ForeignKey("class_sessions.id"), primary_key=True),
    ref("lesson_id", nullable=True),
)

learner_material_grants = Table("learner_material_grants", Base.metadata,
    Column("token_hash", String(64), primary_key=True),
    ref("session_id", "class_sessions.id"),
    value("issued_at", DateTime(timezone=True)),
    value("expires_at", DateTime(timezone=True)),
    Index("ix_material_grants_expiry", "expires_at"),
)
