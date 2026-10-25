"""Apply the additive US-006 schema upgrade without deleting existing records.

Author: Sandhya Tiwari
Date: 25 Oct 2026
"""

from models import Base
from sqlalchemy import inspect, text


def prepare_schema(engine):
    with engine.begin() as connection:
        if connection.dialect.name == "postgresql":
            connection.execute(text("SELECT pg_advisory_xact_lock(800006)"))
        Base.metadata.create_all(connection)
        columns = {
            column["name"]
            for column in inspect(connection).get_columns("lesson_materials")
        }
        if "share_with_learners" not in columns:
            connection.execute(
                text(
                    "ALTER TABLE lesson_materials ADD COLUMN share_with_learners "
                    "BOOLEAN NOT NULL DEFAULT false"
                )
            )

        lesson_columns = {
            column["name"] for column in inspect(connection).get_columns("lessons")
        }
        for name, sql_type in {
            "reviewer_name": "VARCHAR(150)",
            "review_date": "DATE",
        }.items():
            if name not in lesson_columns:
                connection.execute(
                    text(f"ALTER TABLE lessons ADD COLUMN {name} {sql_type}")
                )
