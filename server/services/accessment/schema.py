"""Initialize session tables and enforce one class per date without deleting data.

Author: Shuohui Liu
Date: 24 Oct 2026
"""

from models import Base, class_sessions, unique_session_date
from sqlalchemy import Engine, MetaData, func, select, text


def prepare_schema(engine: Engine, metadata: MetaData | None = None) -> None:
    """Serialize replicas and add the date index to pre-US-014 databases."""
    with engine.begin() as connection:
        if connection.dialect.name == "postgresql":
            connection.execute(text("SELECT pg_advisory_xact_lock(800014)"))
        (metadata if metadata is not None else Base.metadata).create_all(connection)
        duplicates = (
            connection.execute(
                select(class_sessions.c.session_date)
                .group_by(class_sessions.c.session_date)
                .having(func.count() > 1)
            )
            .scalars()
            .all()
        )
        if duplicates:
            raise RuntimeError(
                "Duplicate class dates prevent the US-014 upgrade: "
                + ", ".join(day.isoformat() for day in duplicates)
                + ". Resolve duplicate sessions while preserving attendance, then restart. No records were deleted."
            )
        unique_session_date.create(connection, checkfirst=True)
