"""Teacher account operations; callers own transaction boundaries."""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import RowMapping, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from auth import AuthenticatedUser, authenticate_session, require_coordinator
from models import user_sessions, users

# US-002 AC5; wording from Test Plan UT-12.
LAST_COORDINATOR = "At least one coordinator must stay active"

STAFF_COLUMNS = (
    users.c.id,
    users.c.username,
    users.c.display_name,
    users.c.role,
    users.c.is_active,
)


def list_staff(db: Session) -> list[RowMapping]:
    """Return only fields needed for staff management, including inactive staff."""
    return list(
        db.execute(select(*STAFF_COLUMNS).order_by(users.c.username, users.c.id))
        .mappings()
        .all()
    )


def lock_staff_operation(
    db: Session,
    actor: AuthenticatedUser,
    token: str,
    target_id: UUID | None = None,
    *,
    coordinator_target_allowed: bool = False,
) -> RowMapping | None:
    """Lock users in UUID order, then recheck the actor's live session and role.

    Login/activity/logout lock users before session writes. Holding the actor and
    target user locks prevents concurrent deactivation from bypassing this check.
    Only deactivation passes ``coordinator_target_allowed``; it may target a
    Coordinator while another active Coordinator remains (AC5).
    """
    ids = {actor.user_id}
    if target_id is not None:
        ids.add(target_id)
    locked = users.c.id.in_(ids)
    if coordinator_target_allowed:
        # Lock every active Coordinator as well, so two Coordinators deactivating
        # each other at once cannot both pass the "another one stays" check.
        locked = locked | ((users.c.role == "coordinator") & users.c.is_active)
    rows = {
        row["id"]: row
        for row in db.execute(
            select(users).where(locked).order_by(users.c.id).with_for_update()
        ).mappings()
    }
    current = require_coordinator(authenticate_session(token, db))
    if current.user_id != actor.user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    if target_id is None:
        return None
    target = rows.get(target_id)
    if target is None:
        raise HTTPException(status_code=404, detail="Staff account not found")
    if target["role"] != "teacher":
        if not coordinator_target_allowed:
            raise HTTPException(
                status_code=403, detail="Only Teacher accounts can be modified"
            )
        others_active = any(
            row["role"] == "coordinator" and row["is_active"] and row["id"] != target_id
            for row in rows.values()
        )
        if target["is_active"] and not others_active:
            raise HTTPException(status_code=409, detail=LAST_COORDINATOR)
    return target


def create_teacher(
    db: Session, username: str, display_name: str, password_hash: str
) -> RowMapping:
    """Insert a Teacher; the database unique constraint arbitrates duplicates."""
    return (
        db.execute(
            users.insert()
            .values(
                username=username,
                display_name=display_name,
                password_hash=password_hash,
                role="teacher",
                is_active=True,
            )
            .returning(*STAFF_COLUMNS)
        )
        .mappings()
        .one()
    )


def username_conflict(error: IntegrityError) -> bool:
    """Translate only the username constraint, not unrelated integrity failures."""
    original = error.orig
    return (
        getattr(original, "sqlstate", None) == "23505"
        and getattr(getattr(original, "diag", None), "constraint_name", None)
        == "users_username_key"
    ) or str(original) == "UNIQUE constraint failed: users.username"


def rename_teacher(db: Session, user_id: UUID, display_name: str) -> RowMapping:
    """Change only the display name and update timestamp of a locked Teacher."""
    return (
        db.execute(
            users.update()
            .where(users.c.id == user_id)
            .values(display_name=display_name, updated_at=datetime.now(UTC))
            .returning(*STAFF_COLUMNS)
        )
        .mappings()
        .one()
    )


def deactivate_teacher(db: Session, user_id: UUID) -> RowMapping:
    """Soft-deactivate a locked account and revoke sessions in the same transaction.

    The account is a Teacher, or a Coordinator that lock_staff_operation allowed.
    """
    now = datetime.now(UTC)
    row = (
        db.execute(
            users.update()
            .where(users.c.id == user_id)
            .values(is_active=False, updated_at=now)
            .returning(*STAFF_COLUMNS)
        )
        .mappings()
        .one()
    )
    db.execute(
        user_sessions.update()
        .where(
            user_sessions.c.user_id == user_id,
            user_sessions.c.revoked_at.is_(None),
        )
        .values(revoked_at=now)
    )
    return row
