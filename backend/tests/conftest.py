import os
import tempfile
from pathlib import Path

import pytest
from app.config import settings

from .database_safety import validate_test_target

TEST_ROOT = Path(tempfile.mkdtemp(prefix="docverify-tests-"))
external_url = os.environ.get("TEST_DATABASE_URL")
if external_url:
    validate_test_target(
        external_url,
        settings().database_url,
        os.environ.get("DOCVERIFY_ALLOW_EXTERNAL_TEST_DB") == "1",
    )
os.environ["DATABASE_URL"] = external_url or f"sqlite:///{TEST_ROOT}/test.db"
os.environ["STORAGE_DIR"] = str(TEST_ROOT / "uploads")
os.environ["DEMO_MODE"] = "true"
os.environ["ANTHROPIC_API_KEY"] = ""
os.environ["SEMANTIC_ENABLED"] = "false"
settings.cache_clear()

from app.db import Base, engine  # noqa: E402
from app.main import app, attempts  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture
def client():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    attempts.clear()
    with TestClient(app) as client:
        yield client


def register(client, email="reviewer@example.test"):
    response = client.post(
        "/api/auth/register", json={"email": email, "password": "long-test-password"}
    )
    assert response.status_code == 201, response.text
    client.headers["X-CSRF-Token"] = response.json()["csrf"]
    return response.json()


@pytest.fixture
def account(client):
    return register(client)


@pytest.fixture
def case(client, account):
    response = client.post("/api/cases", json={"name": "Test procurement"})
    assert response.status_code == 201
    return response.json()
