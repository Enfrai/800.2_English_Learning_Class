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


users = Table("users", Base.metadata,
    id_col(), value("username",String(100),unique=True), value("password_hash",String(255)), value("display_name",String(150)), value("email",String(255),nullable=True,unique=True), value("role",String(20)), Column("is_active",Boolean,nullable=False,server_default=text("true")), Column("failed_login_attempts",SmallInteger,nullable=False,server_default=text("0")), value("locked_until",DateTime(timezone=True),nullable=True), value("last_login_at",DateTime(timezone=True),nullable=True), *timestamps(), CheckConstraint("role IN ('coordinator','teacher')"), CheckConstraint("failed_login_attempts >= 0"), Index("ix_users_role_active","role","is_active")
)

user_sessions = Table("user_sessions", Base.metadata,
    id_col(), ref("user_id","users.id"), value("token_hash",String(255),unique=True), Column("created_at",DateTime(timezone=True),nullable=False,server_default=func.now()), Column("last_activity_at",DateTime(timezone=True),nullable=False,server_default=func.now()), value("expires_at",DateTime(timezone=True)), value("revoked_at",DateTime(timezone=True),nullable=True), CheckConstraint("expires_at > created_at"), Index("ix_user_sessions_user_expiry","user_id","expires_at"), Index("uq_active_user_session","user_id",unique=True,postgresql_where=text("revoked_at IS NULL"))
)

learners = Table("learners", Base.metadata,
    id_col(), value("full_name",String(150)), value("contact",String(255),nullable=True), value("first_language",String(100),nullable=True), Column("is_active",Boolean,nullable=False,server_default=text("true")), ref("created_by","users.id"), ref("updated_by","users.id",nullable=True), *timestamps(), Index("ix_learners_full_name","full_name")
)
