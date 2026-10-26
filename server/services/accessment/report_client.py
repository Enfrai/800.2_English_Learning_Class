"""Fetch a minimal report roster in one authenticated User Service request.

Author: Shuohui Liu
Date: 24 Oct 2026
"""

from uuid import UUID

import user_client


def report_names(authorization: str, recorded_ids: set[UUID]) -> dict[UUID, str]:
    status, body = user_client._request(
        "POST",
        "/reports/attendance/learners",
        authorization,
        {"learner_ids": sorted(str(identifier) for identifier in recorded_ids)},
    )
    if status == 401:
        raise user_client.LoginRequiredError("Login required")
    if status != 200 or not isinstance(body, list):
        raise user_client.UserServiceError("Learner information is unavailable")
    try:
        names = {}
        for row in body:
            identifier = UUID(row["id"])
            first, family = row["first_name"], row["family_name"]
            if not isinstance(first, str) or not isinstance(family, str):
                raise ValueError("Invalid name")
            if not first.strip() or not family.strip() or identifier in names:
                raise ValueError("Invalid roster")
            names[identifier] = f"{first} {family}"
        if recorded_ids - names.keys():
            raise ValueError("Missing historical learner")
        return names
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        raise user_client.UserServiceError(
            "Learner information is unavailable"
        ) from exc
