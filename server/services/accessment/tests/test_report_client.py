"""Verify batched report roster transport, strict names and safe service failures.

Author: Shuohui Liu
Date: 24 Oct 2026
"""

from uuid import uuid4

import pytest
import report_client
import user_client


def test_minimal_roster_uses_one_authenticated_post_and_keeps_duplicate_names(
    monkeypatch,
):
    """
    Verify that minimal roster uses one authenticated post and keeps duplicate names.
    """
    first, second = uuid4(), uuid4()
    calls = []

    def request(method, path, authorization, body):
        """
        Send a REQUEST request through the test client with the supplied scenario data.
        """
        calls.append((method, path, authorization, body))
        return 200, [
            {
                "id": str(i),
                "first_name": "Māia",
                "family_name": "Test",
                "contact": "private",
            }
            for i in (first, second)
        ]

    monkeypatch.setattr(user_client, "_request", request)
    names = report_client.report_names("Bearer coordinator", {first})
    assert names == {first: "Māia Test", second: "Māia Test"}
    assert calls == [
        (
            "POST",
            "/reports/attendance/learners",
            "Bearer coordinator",
            {"learner_ids": [str(first)]},
        )
    ]


@pytest.mark.parametrize("status", [401, 403, 404, 409, 500, 503])
def test_http_errors_never_become_empty_report(monkeypatch, status):
    """
    Verify that http errors never become empty report.
    """
    monkeypatch.setattr(user_client, "_request", lambda *args: (status, {}))
    with pytest.raises(
        user_client.LoginRequiredError
        if status == 401
        else user_client.UserServiceError
    ):
        report_client.report_names("Bearer coordinator", set())


@pytest.mark.parametrize(
    "body",
    [
        None,
        {},
        "wrong",
        [{}],
        [{"id": "wrong", "first_name": "A", "family_name": "B"}],
        [{"id": str(uuid4()), "first_name": None, "family_name": "B"}],
        [{"id": str(uuid4()), "first_name": " ", "family_name": "B"}],
    ],
)
def test_malformed_rosters_fail_closed(monkeypatch, body):
    """
    Verify that malformed rosters fail closed.
    """
    monkeypatch.setattr(user_client, "_request", lambda *args: (200, body))
    with pytest.raises(user_client.UserServiceError):
        report_client.report_names("Bearer coordinator", set())


def test_duplicate_uuid_or_missing_historical_name_is_rejected(monkeypatch):
    """
    Verify that duplicate uuid or missing historical name is rejected.
    """
    identifier = uuid4()
    row = {"id": str(identifier), "first_name": "A", "family_name": "B"}
    for body in ([row, row], []):
        monkeypatch.setattr(user_client, "_request", lambda *args: (200, body))
        with pytest.raises(user_client.UserServiceError):
            report_client.report_names("Bearer coordinator", {identifier})


def test_transport_failure_is_not_swallowed(monkeypatch):
    """
    Verify that transport failure is not swallowed.
    """
    def fail(*args):
        """
        Simulate an unavailable dependency or failing operation for the surrounding
        test.
        """
        raise user_client.UserServiceError()

    monkeypatch.setattr(user_client, "_request", fail)
    with pytest.raises(user_client.UserServiceError):
        report_client.report_names("Bearer coordinator", set())
