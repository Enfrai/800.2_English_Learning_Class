"""Regression coverage for dev APIs using the merged US-001 session dependency."""

import pytest

from test_postgres import PgContext


def test_me_contract_and_passive_read(pg: PgContext) -> None:
    """
    Verify that me contract and passive read.
    """
    token = pg.login().json()["sessionid"]
    before = pg.session_rows()
    response = pg.clients[1].get("/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json() == {
        "id": str(pg.user_id),
        "display_name": "Integration Teacher",
        "role": "teacher",
    }
    assert response.headers["cache-control"] == "no-store"
    assert pg.session_rows() == before


@pytest.mark.parametrize("cookie", [False, True])
def test_learner_round_trip_preserves_dev_contract(pg: PgContext, cookie: bool) -> None:
    """
    Verify that learner round trip preserves dev contract.
    """
    token = pg.login().json()["sessionid"]
    client = pg.clients[1]
    headers = {"Origin": "http://testserver"}
    if cookie:
        client.cookies.set("ako_session", token)
    else:
        headers["Authorization"] = f"Bearer {token}"
    payload = {"first_name": "Merge", "family_name": pg.user_id.hex}
    response = client.post("/learners", json=payload, headers=headers)
    assert response.status_code == 201
    learner_id = response.json()["id"]
    response = client.put(
        f"/learners/{learner_id}",
        json=payload | {"first_language": "English"},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["first_language"] == "English"
    assert client.get(f"/learners/{learner_id}", headers=headers).status_code == 200
    response = client.get(
        "/learners", params={"search": pg.user_id.hex}, headers=headers
    )
    assert any(row["id"] == learner_id for row in response.json())


def test_learner_cookie_write_requires_origin(pg: PgContext) -> None:
    """
    Verify that learner cookie write requires origin.
    """
    pg.login()
    response = pg.clients[0].post(
        "/learners", json={"first_name": "Blocked", "family_name": "Test"}
    )
    assert response.status_code == 403


def test_revoked_session_denied_by_me_and_learners(pg: PgContext) -> None:
    """
    Verify that revoked session denied by me and learners.
    """
    token = pg.login().json()["sessionid"]
    assert (
        pg.clients[0]
        .post("/logout", headers={"Origin": "http://testserver"})
        .status_code
        == 204
    )
    for path in ("/me", "/learners"):
        assert (
            pg.clients[1]
            .get(path, headers={"Authorization": f"Bearer {token}"})
            .status_code
            == 401
        )
