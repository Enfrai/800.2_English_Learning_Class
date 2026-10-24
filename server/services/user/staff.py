"""Coordinator-only Staff API; no role assignment or Coordinator mutations."""

import secrets
from collections.abc import Callable, Iterator
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from auth import AuthenticatedUser, get_db, get_session_token, require_coordinator
from staff_service import (
    create_teacher,
    deactivate_teacher,
    list_staff,
    lock_staff_operation,
    rename_teacher,
    username_conflict,
)

MIN_PASSWORD_LENGTH = 8


class TeacherCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str = Field(min_length=1, max_length=150)
    username: str = Field(min_length=1, max_length=100)
    temporary_password: SecretStr

    @field_validator("display_name", "username")
    @classmethod
    def not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Must not be blank")
        return value


class TeacherRename(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str = Field(min_length=1, max_length=150)

    @field_validator("display_name")
    @classmethod
    def not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Must not be blank")
        return value


class EmptyAction(BaseModel):
    model_config = ConfigDict(extra="forbid")


class StaffAccount(BaseModel):
    id: UUID
    username: str
    display_name: str
    role: Literal["teacher", "coordinator"]
    is_active: bool


def get_staff_db(request: Request) -> Iterator[Session]:
    """Reuse get_db's injectable factory with a separate operation Session.

    require_coordinator owns its read-only authentication Session. Keeping the
    operation Session separate allows explicit begin/commit/rollback without
    committing or nesting the transaction implicitly opened by authentication.
    """
    yield from get_db(request)


def create_staff_router(hash_password: Callable[[str, bytes], str]) -> APIRouter:
    """Inject the existing password hasher without importing the app entry point."""
    router = APIRouter(prefix="/staff", tags=["staff"])

    @router.get("", response_model=list[StaffAccount])
    def staff_list(
        actor: Annotated[AuthenticatedUser, Depends(require_coordinator)],
        db: Annotated[Session, Depends(get_staff_db)],
    ) -> list[StaffAccount]:
        return [StaffAccount.model_validate(row) for row in list_staff(db)]

    @router.post("", response_model=StaffAccount, status_code=201)
    def staff_create(
        payload: TeacherCreate,
        actor: Annotated[AuthenticatedUser, Depends(require_coordinator)],
        token: Annotated[str, Depends(get_session_token)],
        db: Annotated[Session, Depends(get_staff_db)],
    ) -> StaffAccount:
        password = payload.temporary_password.get_secret_value()
        if len(password) < MIN_PASSWORD_LENGTH:
            raise HTTPException(
                status_code=422, detail="Password must be at least 8 characters"
            )
        # Hash before acquiring row locks to keep transactions short.
        encoded = hash_password(password, secrets.token_bytes(16))
        try:
            with db.begin():
                lock_staff_operation(db, actor, token)
                row = create_teacher(
                    db, payload.username, payload.display_name, encoded
                )
                result = StaffAccount.model_validate(row)
        except IntegrityError as exc:
            if username_conflict(exc):
                raise HTTPException(
                    status_code=409, detail="Username already taken"
                ) from exc
            raise
        return result

    @router.patch("/{user_id}", response_model=StaffAccount)
    def staff_rename(
        user_id: UUID,
        payload: TeacherRename,
        actor: Annotated[AuthenticatedUser, Depends(require_coordinator)],
        token: Annotated[str, Depends(get_session_token)],
        db: Annotated[Session, Depends(get_staff_db)],
    ) -> StaffAccount:
        with db.begin():
            lock_staff_operation(db, actor, token, user_id)
            result = StaffAccount.model_validate(
                rename_teacher(db, user_id, payload.display_name)
            )
        return result

    @router.post("/{user_id}/deactivate", response_model=StaffAccount)
    def staff_deactivate(
        user_id: UUID,
        actor: Annotated[AuthenticatedUser, Depends(require_coordinator)],
        token: Annotated[str, Depends(get_session_token)],
        db: Annotated[Session, Depends(get_staff_db)],
        payload: Annotated[EmptyAction | None, Body()] = None,
    ) -> StaffAccount:
        with db.begin():
            lock_staff_operation(
                db, actor, token, user_id, coordinator_target_allowed=True
            )
            result = StaffAccount.model_validate(deactivate_teacher(db, user_id))
        return result

    return router
