"""Verify authenticated lesson lookups and safe cross-service failures.

Author: Shuohui Liu
Date: 24 Oct 2026
"""

import io
import json
from urllib.error import HTTPError, URLError
from uuid import uuid4

import lesson_client
import pytest


class Reply:
    def __init__(self, body: object) -> None:
        """
        Initialize Reply and retain the supplied constructor state.
        """
        self.body = io.BytesIO(json.dumps(body).encode())

    def __enter__(self) -> io.BytesIO:
        """
        Enter the test resource context and return the object used by the scenario.
        """
        return self.body

    def __exit__(self, *args: object) -> None:
        """
        Finalize the test resource context according to the simulated cleanup policy.
        """
        self.body.close()


def test_lesson_title_forwards_staff_authorization_to_fixed_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Verify that lesson title forwards staff authorization to fixed service.
    """
    identifier = uuid4()

    def open_request(request, timeout):
        """
        Prepare or exercise open request in the test lesson client test scenario.
        """
        assert request.full_url == f"http://lesson-test/lessons/{identifier}"
        assert request.get_header("Authorization") == "Bearer staff-token"
        assert timeout == 5
        return Reply({"id": str(identifier), "title": "Te reo Māori"})

    monkeypatch.setenv("LESSON_API_URL", "http://lesson-test/")
    monkeypatch.setattr(lesson_client, "urlopen", open_request)
    assert (
        lesson_client.lesson_title(identifier, "Bearer staff-token") == "Te reo Māori"
    )


def test_lesson_list_returns_only_ids_and_titles(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Verify that lesson list returns only ids and titles.
    """
    identifier = uuid4()
    monkeypatch.setattr(
        lesson_client,
        "request_lessons",
        lambda *args: [
            {
                "id": str(identifier),
                "title": "Health",
                "materials": ["private metadata"],
            }
        ],
    )
    assert lesson_client.lesson_titles("Bearer staff") == {identifier: "Health"}


@pytest.mark.parametrize(
    "body",
    [
        None,
        [],
        {},
        {"id": "bad", "title": "Title"},
        {"id": str(uuid4()), "title": "Wrong id"},
        {"id": str(uuid4()), "title": 4},
    ],
)
def test_invalid_single_lesson_fails_closed(
    monkeypatch: pytest.MonkeyPatch, body: object
) -> None:
    """
    Verify that invalid single lesson fails closed.
    """
    monkeypatch.setattr(lesson_client, "request_lessons", lambda *args: body)
    with pytest.raises(lesson_client.LessonServiceError):
        lesson_client.lesson_title(uuid4(), "Bearer staff")


@pytest.mark.parametrize(
    "body",
    [
        None,
        {},
        [None],
        [{"id": "bad", "title": "Title"}],
        [{"id": str(uuid4()), "title": 3}],
    ],
)
def test_invalid_list_fails_closed(
    monkeypatch: pytest.MonkeyPatch, body: object
) -> None:
    """
    Verify that invalid list fails closed.
    """
    monkeypatch.setattr(lesson_client, "request_lessons", lambda *args: body)
    with pytest.raises(lesson_client.LessonServiceError):
        lesson_client.lesson_titles("Bearer staff")


@pytest.mark.parametrize("code", [401, 403, 404, 500])
def test_http_errors_do_not_reveal_service_response_bodies(
    monkeypatch: pytest.MonkeyPatch, code: int
) -> None:
    """
    Verify that http errors do not reveal service response bodies.
    """
    def unavailable(*args, **kwargs):
        """
        Simulate an unavailable dependency or failing operation for the surrounding
        test.
        """
        raise HTTPError(
            "http://test", code, "error", {}, io.BytesIO(b"sensitive backend detail")
        )

    monkeypatch.setattr(lesson_client, "urlopen", unavailable)
    error = (
        lesson_client.LessonUnavailableError
        if code == 404
        else lesson_client.LessonServiceError
    )
    with pytest.raises(error) as result:
        lesson_client.request_lessons("/lessons/id", "Bearer staff")
    assert "sensitive" not in str(result.value)


@pytest.mark.parametrize(
    "error",
    [
        URLError("offline"),
        TimeoutError(),
        OSError("connection lost"),
        ValueError("invalid json"),
    ],
)
def test_transport_and_json_failures_are_service_errors(
    monkeypatch: pytest.MonkeyPatch, error: Exception
) -> None:
    """
    Verify that transport and json failures are service errors.
    """
    def unavailable(*args, **kwargs):
        """
        Simulate an unavailable dependency or failing operation for the surrounding
        test.
        """
        raise error

    monkeypatch.setattr(lesson_client, "urlopen", unavailable)
    with pytest.raises(lesson_client.LessonServiceError):
        lesson_client.request_lessons("/lessons", "Bearer staff")


def test_missing_collection_is_unavailable_not_an_empty_library(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Verify that missing collection is unavailable not an empty library.
    """
    def unavailable(*args):
        """
        Simulate an unavailable dependency or failing operation for the surrounding
        test.
        """
        raise lesson_client.LessonUnavailableError()

    monkeypatch.setattr(lesson_client, "request_lessons", unavailable)
    with pytest.raises(lesson_client.LessonServiceError):
        lesson_client.lesson_titles("Bearer staff")
