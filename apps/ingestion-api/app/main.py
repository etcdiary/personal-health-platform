import json
import os
from datetime import datetime
from typing import Any

import psycopg
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

app = FastAPI(
    title="Health Data Ingestion API",
    version="0.1.0",
)


# ============================================================
# Database connection
# ============================================================


def get_connection() -> psycopg.Connection:
    database_user = os.getenv("POSTGRES_USER")
    database_password = os.getenv("POSTGRES_PASSWORD")
    database_name = os.getenv("POSTGRES_DB")
    database_host = os.getenv(
        "POSTGRES_HOST",
        "postgres.data.svc.cluster.local",
    )
    database_port = os.getenv("POSTGRES_PORT", "5432")

    if not database_user or not database_password or not database_name:
        raise RuntimeError("PostgreSQL environment variables are not configured")

    return psycopg.connect(
        host=database_host,
        port=database_port,
        dbname=database_name,
        user=database_user,
        password=database_password,
    )


# ============================================================
# Optional external integration configuration
#
# Secrets are read from environment variables and are never
# returned by the API.
# ============================================================


WHOOP_CLIENT_ID = os.getenv("WHOOP_CLIENT_ID")
WHOOP_CLIENT_SECRET = os.getenv("WHOOP_CLIENT_SECRET")

APPLE_CLIENT_ID = os.getenv("APPLE_CLIENT_ID")
APPLE_CLIENT_SECRET = os.getenv("APPLE_CLIENT_SECRET")


# ============================================================
# Models
# ============================================================


class Event(BaseModel):
    source: str = Field(min_length=1, max_length=50)
    event_type: str = Field(min_length=1, max_length=100)
    external_id: str | None = None
    recorded_at: datetime | None = None
    payload: dict[str, Any]


# ============================================================
# Health / readiness
# ============================================================


@app.get("/health")
def health():
    """
    Kubernetes liveness endpoint.

    Does not require PostgreSQL to be available.
    """

    return {"status": "ok"}


@app.get("/ready")
def ready():
    """
    Kubernetes readiness endpoint.

    Verifies that PostgreSQL is reachable.
    """

    try:
        with get_connection() as conn:
            conn.execute("SELECT 1")

        return {
            "status": "ready",
            "database": "ok",
        }

    except psycopg.Error:
        raise HTTPException(
            status_code=503,
            detail="database unavailable",
        )


# ============================================================
# Apple normalization
# ============================================================


def normalize_apple_event(cur, event: Event):
    """
    Normalize supported Apple events into health_measurements.

    Raw events remain stored in raw_events as the source of truth.
    """

    if event.event_type != "heart_rate":
        return

    heart_rate = event.payload.get("heart_rate")
    unit = event.payload.get("unit")

    if heart_rate is None:
        raise HTTPException(
            status_code=400,
            detail="heart_rate is required",
        )

    if event.recorded_at is None:
        raise HTTPException(
            status_code=400,
            detail="recorded_at is required",
        )

    cur.execute(
        """
        INSERT INTO health_measurements
            (
                source,
                metric,
                value,
                unit,
                recorded_at
            )
        VALUES
            (%s, %s, %s, %s, %s)
        """,
        (
            event.source,
            "heart_rate",
            heart_rate,
            unit,
            event.recorded_at,
        ),
    )


# ============================================================
# Generic ingestion
# ============================================================


@app.post("/ingest/event")
def ingest_event(event: Event, normalize: bool = False):
    """
    Store an event in raw_events.

    If normalize=True, source-specific normalization is performed
    in the same PostgreSQL transaction.
    """

    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO raw_events
                        (
                            source,
                            event_type,
                            external_id,
                            recorded_at,
                            payload
                        )
                    VALUES
                        (%s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (
                        event.source,
                        event.event_type,
                        event.external_id,
                        event.recorded_at,
                        json.dumps(event.payload),
                    ),
                )

                event_id = cur.fetchone()[0]

                if normalize:
                    normalize_apple_event(cur, event)

            conn.commit()

        return {
            "status": "accepted",
            "event_id": event_id,
        }

    except psycopg.errors.UniqueViolation:
        raise HTTPException(
            status_code=409,
            detail="event already exists",
        )

    except psycopg.Error:
        raise HTTPException(
            status_code=500,
            detail="failed to store event",
        )


# ============================================================
# WHOOP ingestion
# ============================================================


@app.post("/ingest/whoop")
def ingest_whoop(event: Event):
    """
    WHOOP-specific ingestion endpoint.

    WHOOP events are currently stored as raw events only.
    """

    if event.source.lower() != "whoop":
        raise HTTPException(
            status_code=400,
            detail="source must be 'whoop'",
        )

    return ingest_event(event)


# ============================================================
# Apple ingestion
# ============================================================


@app.post("/ingest/apple")
def ingest_apple(event: Event):
    """
    Apple-specific ingestion endpoint.

    Apple events are stored in raw_events and supported events
    are normalized into health_measurements.
    """

    if event.source.lower() != "apple":
        raise HTTPException(
            status_code=400,
            detail="source must be 'apple'",
        )

    return ingest_event(event, normalize=True)


# ============================================================
# Configuration status
#
# IMPORTANT:
# This endpoint NEVER returns secret values.
# It only reports whether required configuration exists.
# ============================================================


@app.get("/config/status")
def config_status():
    database_configured = all(
        [
            os.getenv("POSTGRES_USER"),
            os.getenv("POSTGRES_PASSWORD"),
            os.getenv("POSTGRES_DB"),
        ]
    )

    return {
        "database_configured": database_configured,
        "whoop": {
            "client_id_configured": bool(WHOOP_CLIENT_ID),
            "client_secret_configured": bool(WHOOP_CLIENT_SECRET),
        },
        "apple": {
            "client_id_configured": bool(APPLE_CLIENT_ID),
            "client_secret_configured": bool(APPLE_CLIENT_SECRET),
        },
    }
