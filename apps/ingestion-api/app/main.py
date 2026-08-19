
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
# Configuration
#
# DO NOT put passwords, API keys, OAuth secrets, or tokens here.
#
# Local development:
#   export DATABASE_URL="postgresql://..."
#
# Kubernetes:
#   Inject DATABASE_URL from a Kubernetes Secret.
#
# Production AWS:
#   Kubernetes can retrieve the secret from AWS Secrets Manager.
# ============================================================

def get_connection() -> psycopg.Connection:
    database_url = os.getenv("DATABASE_URL")            

    if not database_url:
        raise RuntimeError(
            "DATABASE_URL environment variable is not configured"
        )

    return psycopg.connect(database_url)


# Optional external integration configuration.
#
# These are intentionally read from environment variables so
# secrets never need to be committed to Git.

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

    return {
        "status": "ok"
    }


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
# Generic ingestion
# ============================================================

@app.post("/ingest/event")
def ingest_event(event: Event):

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

            conn.commit()

        return {
            "status": "accepted",
            "event_id": event_id,
        }

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

    if event.source.lower() != "apple":
        raise HTTPException(
            status_code=400,
            detail="source must be 'apple'",
        )

    return ingest_event(event)


# ============================================================
# Configuration status
#
# IMPORTANT:
# This endpoint NEVER returns secret values.
# It only tells us whether required configuration exists.
# ============================================================

@app.get("/config/status")
def config_status():

    return {
        "database_configured": bool(os.getenv("DATABASE_URL")),

        "whoop": {
            "client_id_configured": bool(WHOOP_CLIENT_ID),
            "client_secret_configured": bool(WHOOP_CLIENT_SECRET),
        },

        "apple": {
            "client_id_configured": bool(APPLE_CLIENT_ID),
            "client_secret_configured": bool(APPLE_CLIENT_SECRET),
        },
    }

