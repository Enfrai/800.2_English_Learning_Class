"""Verify startup, private response headers and the removal of the unsafe demo API.

Author: Sandhya Tiwari
Date: 25 Oct 2026
"""

import importlib.util
from pathlib import Path

from fastapi.testclient import TestClient


def test_app_startup_and_private_headers(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'app.sqlite'}")
    monkeypatch.setenv("MATERIALS_DIR", str(tmp_path / "materials"))
    spec = importlib.util.spec_from_file_location(
        "us006_app_test", Path(__file__).resolve().parents[1] / "app.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    try:
        with TestClient(module.app) as client:
            assert client.get("/health").status_code == 200
            response = client.get("/lessons")
            assert response.status_code == 401
            assert response.headers["cache-control"] == "no-store"
            assert response.headers["x-content-type-options"] == "nosniff"
            assert (
                client.post("/create", json={"created_by": "forged"}).status_code == 404
            )
    finally:
        module.engine.dispose()
