"""Ako database models.

Author: Shuohui Liu
Date: 19 Oct 2026
"""
from uuid import uuid4
from sqlalchemy import Table, Column, String, Boolean, Integer, SmallInteger, BigInteger, Date, Time, DateTime, Text, ForeignKey, CheckConstraint, UniqueConstraint, Index, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    pass

def id_col():
    return Column("id", UUID(as_uuid=True), primary_key=True, default=uuid4)

def timestamps():
    return [Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()), Column("updated_at", DateTime(timezone=True), nullable=False, server_default=func.now())]

def ref(name, target=None, nullable=False):
    return Column(name, UUID(as_uuid=True), ForeignKey(target), nullable=nullable) if target else Column(name, UUID(as_uuid=True), nullable=nullable)

def value(name, typ, nullable=False, unique=False):
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
