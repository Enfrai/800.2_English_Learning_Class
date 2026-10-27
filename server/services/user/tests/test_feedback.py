"""Verify public feedback validation, SMTP settings, delivery and safe failures.

Author: Shuohui Liu
Date: 24 Oct 2026
"""

import importlib
import smtplib
import socketserver
import threading
from email import policy
from email.parser import BytesParser
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import feedback
from security import SessionSecurity


@pytest.fixture
def api(monkeypatch):
    for key in list(feedback.os.environ):
        if key.startswith("FEEDBACK_"):
            monkeypatch.delenv(key)
    for key, value in {
        "FEEDBACK_SMTP_HOST": "smtp.example.test",
        "FEEDBACK_SMTP_USERNAME": "sender@example.test",
        "FEEDBACK_SMTP_PASSWORD": "private-password",
    }.items():
        monkeypatch.setenv(key, value)
    app = FastAPI()
    app.state.session_security = SessionSecurity()
    app.include_router(feedback.create_feedback_router())
    return TestClient(app)


@pytest.fixture
def smtp(monkeypatch):
    client = MagicMock()
    client.__enter__.return_value = client
    client.send_message.return_value = {}
    normal, secure = MagicMock(return_value=client), MagicMock(return_value=client)
    monkeypatch.setattr(feedback.smtplib, "SMTP", normal)
    monkeypatch.setattr(feedback.smtplib, "SMTP_SSL", secure)
    return client, normal, secure


def payload(**changes):
    return {
        "title": "Calendar problem",
        "email": "visitor@example.test",
        "description": "The date picker did not open. Māori text is preserved.",
        **changes,
    }


def post(api, data=None, origin="http://testserver"):
    return api.post(
        "/feedback",
        json=payload() if data is None else data,
        headers={"Origin": origin} if origin else {},
    )


def test_default_recipient_headers_tls_order_and_success(api, smtp):
    result = post(api)
    assert result.status_code == 200 and result.json() == {"message": feedback.SUCCESS}
    assert result.headers["cache-control"] == "no-store"
    client, normal, secure = smtp
    normal.assert_called_once_with(host="smtp.example.test", port=587, timeout=10)
    secure.assert_not_called()
    assert [call[0] for call in client.method_calls] == [
        "starttls",
        "login",
        "send_message",
    ]
    assert client.starttls.call_args.kwargs["context"].check_hostname
    assert (
        client.starttls.call_args.kwargs["context"].verify_mode
        == feedback.ssl.CERT_REQUIRED
    )
    client.login.assert_called_once_with("sender@example.test", "private-password")
    call = client.send_message.call_args
    assert call.kwargs == {
        "from_addr": "sender@example.test",
        "to_addrs": [feedback.DEFAULT_RECIPIENT],
    }
    message = call.args[0]
    assert message["From"] == "sender@example.test"
    assert message["Reply-To"] == "visitor@example.test"
    assert message["To"] == "undisclosed-recipients:;"
    assert message["Subject"] == "[Ako feedback] Calendar problem"
    assert payload()["description"] in message.get_content()


def test_semicolon_recipient_parsing(api, smtp, monkeypatch):
    monkeypatch.setenv(
        "FEEDBACK_RECIPIENTS", " one@example.test ;two@example.test;;one@example.test; "
    )
    assert post(api).status_code == 200
    assert smtp[0].send_message.call_args.kwargs["to_addrs"] == [
        "one@example.test",
        "two@example.test",
    ]


@pytest.mark.parametrize(
    "field,value",
    [
        ("title", ""),
        ("title", "   "),
        ("title", "x" * 201),
        ("title", "test\r\nBcc: victim@example.test"),
        ("email", ""),
        ("email", "invalid"),
        ("email", "Name <x@example.test>"),
        ("email", "a@example.test;victim@example.test"),
        ("email", "a@example.test\r\nBcc: victim@example.test"),
        ("email", ".a@example.test"),
        ("email", "a..b@example.test"),
        ("email", "a@localhost"),
        ("email", "a@-bad.test"),
        ("email", "a" * 65 + "@example.test"),
        ("description", ""),
        ("description", "  "),
        ("description", "x" * 5001),
        ("description", "bad\x00text"),
    ],
)
def test_invalid_input_never_sends(api, smtp, field, value):
    assert post(api, payload(**{field: value})).status_code == 422
    smtp[1].assert_not_called()


@pytest.mark.parametrize("missing", ["title", "email", "description"])
def test_required_fields(api, smtp, missing):
    data = payload()
    del data[missing]
    assert post(api, data).status_code == 422
    smtp[1].assert_not_called()


def test_no_recipient_override(api, smtp):
    assert post(api, payload(recipients=["victim@example.test"])).status_code == 422
    smtp[1].assert_not_called()


def test_exact_lengths_unicode_and_trimming(api, smtp):
    data = payload(title="ā" * 200, description="中" * 5000)
    assert post(api, data).status_code == 200
    assert data["description"] in smtp[0].send_message.call_args.args[0].get_content()
    assert (
        post(api, payload(title=" title ", email=" visitor@example.test ")).status_code
        == 200
    )
    assert smtp[0].send_message.call_args.args[0]["Subject"] == "[Ako feedback] title"


@pytest.mark.parametrize(
    "origin", [None, "https://evil.example", "null", "http://testserver/path"]
)
def test_origin_required(api, smtp, origin):
    assert post(api, origin=origin).status_code == 403
    smtp[1].assert_not_called()


def test_pinned_origin_and_duplicate_origin(api, smtp):
    api.app.state.session_security = SessionSecurity(
        public_origin="https://ako.example.test"
    )
    assert post(api, origin="https://ako.example.test").status_code == 200
    assert (
        api.post(
            "/feedback",
            json=payload(),
            headers=[
                ("Origin", "https://ako.example.test"),
                ("Origin", "https://evil.example"),
            ],
        ).status_code
        == 403
    )


@pytest.mark.parametrize(
    "setting,value",
    [
        ("FEEDBACK_RECIPIENTS", ""),
        ("FEEDBACK_RECIPIENTS", "bad-address"),
        ("FEEDBACK_RECIPIENTS", ";".join(f"u{i}@example.test" for i in range(21))),
        ("FEEDBACK_SMTP_HOST", ""),
        ("FEEDBACK_SMTP_HOST", "smtp host"),
        ("FEEDBACK_SMTP_PORT", "bad"),
        ("FEEDBACK_SMTP_PORT", "0"),
        ("FEEDBACK_SMTP_PORT", "65536"),
        ("FEEDBACK_SMTP_SECURITY", "invalid"),
        ("FEEDBACK_SMTP_FROM", "invalid"),
        ("FEEDBACK_SMTP_PASSWORD", ""),
        ("FEEDBACK_SMTP_USERNAME", ""),
    ],
)
def test_bad_configuration_is_private(api, smtp, monkeypatch, setting, value):
    monkeypatch.setenv(setting, value)
    result = post(api)
    assert result.status_code == 503 and result.json()["detail"] == feedback.UNAVAILABLE
    assert "private-password" not in result.text
    smtp[1].assert_not_called()
    smtp[2].assert_not_called()


def test_ssl_with_explicit_from(api, smtp, monkeypatch):
    monkeypatch.setenv("FEEDBACK_SMTP_SECURITY", "ssl")
    monkeypatch.setenv("FEEDBACK_SMTP_FROM", "noreply@example.test")
    assert post(api).status_code == 200
    smtp[1].assert_not_called()
    assert smtp[2].call_args.kwargs["port"] == 465
    smtp[0].starttls.assert_not_called()
    assert smtp[0].send_message.call_args.kwargs["from_addr"] == "noreply@example.test"


def test_no_auth_local_relay(api, smtp, monkeypatch):
    for key, value in {
        "FEEDBACK_SMTP_SECURITY": "none",
        "FEEDBACK_SMTP_FROM": "noreply@example.test",
        "FEEDBACK_SMTP_USERNAME": "",
        "FEEDBACK_SMTP_PASSWORD": "",
    }.items():
        monkeypatch.setenv(key, value)
    assert post(api).status_code == 200
    smtp[0].login.assert_not_called()
    smtp[0].starttls.assert_not_called()


@pytest.mark.parametrize("operation", ["connect", "starttls", "login", "send_message"])
def test_delivery_failure_never_claims_success_or_leaks_data(
    api, smtp, operation, caplog
):
    error = smtplib.SMTPException("private-password visitor@example.test")
    (
        smtp[1] if operation == "connect" else getattr(smtp[0], operation)
    ).side_effect = error
    response = post(api)
    assert (
        response.status_code == 502
        and response.json()["detail"] == feedback.UNCONFIRMED
    )
    assert "private-password" not in response.text + caplog.text
    assert "visitor@example.test" not in response.text + caplog.text


def test_timeout_no_retry(api, smtp):
    smtp[1].side_effect = TimeoutError("timed out")
    assert post(api).status_code == 502 and smtp[1].call_count == 1


def test_partial_refusal_is_not_complete(api, smtp):
    smtp[0].send_message.return_value = {"one@example.test": (550, b"refused")}
    assert post(api).status_code == 502 and smtp[0].send_message.call_count == 1


def test_app_registration_and_error_cache(api, smtp, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    client = TestClient(importlib.import_module("app").app)
    assert post(client).status_code == 200
    response = post(client, payload(title=""))
    assert response.status_code == 422
    assert response.headers["cache-control"] == "no-store"


def test_real_smtp_on_loopback_only(api, monkeypatch):
    captured = []

    class Relay(socketserver.StreamRequestHandler):
        def handle(self):
            self.wfile.write(b"220 local test relay\r\n")
            data, lines = False, []
            while line := self.rfile.readline():
                if data:
                    if line == b".\r\n":
                        captured.append(b"".join(lines))
                        self.wfile.write(b"250 accepted\r\n")
                        data = False
                    else:
                        lines.append(line)
                    continue
                command = line.split(b" ", 1)[0].strip().upper()
                if command == b"DATA":
                    data = True
                    self.wfile.write(b"354 send data\r\n")
                elif command == b"QUIT":
                    self.wfile.write(b"221 bye\r\n")
                    break
                else:
                    self.wfile.write(b"250 OK\r\n")

    with socketserver.TCPServer(("127.0.0.1", 0), Relay) as relay:
        worker = threading.Thread(target=relay.serve_forever, daemon=True)
        worker.start()
        for key, value in {
            "FEEDBACK_SMTP_HOST": "127.0.0.1",
            "FEEDBACK_SMTP_PORT": str(relay.server_address[1]),
            "FEEDBACK_SMTP_SECURITY": "none",
            "FEEDBACK_SMTP_USERNAME": "",
            "FEEDBACK_SMTP_PASSWORD": "",
            "FEEDBACK_SMTP_FROM": "test@example.test",
        }.items():
            monkeypatch.setenv(key, value)
        try:
            assert post(api).status_code == 200
        finally:
            relay.shutdown()
            worker.join(timeout=3)
    assert len(captured) == 1
    assert (
        payload()["description"]
        in BytesParser(policy=policy.default).parsebytes(captured[0]).get_content()
    )
