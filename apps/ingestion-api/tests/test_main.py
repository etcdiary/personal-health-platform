from unittest.mock import MagicMock

import psycopg
import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://test:test@localhost:5432/test",
    )

    return TestClient(app)


def test_health(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
    }


def test_config_status(client):
    response = client.get("/config/status")

    assert response.status_code == 200

    data = response.json()

    assert "database_configured" in data
    assert "whoop" in data
    assert "apple" in data


def test_whoop_rejects_wrong_source(client):
    response = client.post(
        "/ingest/whoop",
        json={
            "source": "apple",
            "event_type": "test",
            "payload": {},
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "source must be 'whoop'"


def test_apple_rejects_wrong_source(client):
    response = client.post(
        "/ingest/apple",
        json={
            "source": "whoop",
            "event_type": "test",
            "payload": {},
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "source must be 'apple'"


def test_duplicate_event_returns_409(client, monkeypatch):
    fake_connection = MagicMock()
    fake_cursor = MagicMock()

    fake_connection.__enter__.return_value = fake_connection
    fake_connection.cursor.return_value.__enter__.return_value = fake_cursor

    fake_cursor.execute.side_effect = psycopg.errors.UniqueViolation(
        "duplicate key value violates unique constraint"
    )

    monkeypatch.setattr(
        "app.main.get_connection",
        lambda: fake_connection,
    )

    response = client.post(
        "/ingest/event",
        json={
            "source": "apple",
            "event_type": "heart_rate",
            "external_id": "apple-test-001",
            "payload": {
                "heart_rate": 68,
            },
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "event already exists"
