CREATE EXTENSION IF NOT EXISTS "uuid-ossp";


-- ============================================================
-- RAW EVENTS
-- Everything coming from Apple Watch, WHOOP, or future sources
-- is preserved here before analytics/ML processing.
-- ============================================================

CREATE TABLE IF NOT EXISTS raw_events (
    id BIGSERIAL PRIMARY KEY,

    event_uuid UUID NOT NULL DEFAULT uuid_generate_v4(),

    source VARCHAR(50) NOT NULL,
    event_type VARCHAR(100) NOT NULL,

    external_id VARCHAR(255),

    recorded_at TIMESTAMPTZ,

    received_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    payload JSONB NOT NULL,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


CREATE INDEX IF NOT EXISTS idx_raw_events_source
    ON raw_events(source);


CREATE INDEX IF NOT EXISTS idx_raw_events_event_type
    ON raw_events(event_type);


CREATE INDEX IF NOT EXISTS idx_raw_events_recorded_at
    ON raw_events(recorded_at);


CREATE INDEX IF NOT EXISTS idx_raw_events_received_at
    ON raw_events(received_at);


CREATE INDEX IF NOT EXISTS idx_raw_events_payload
    ON raw_events USING GIN(payload);


-- ============================================================
-- NORMALIZED HEALTH METRICS
-- This is what analytics/ML will eventually consume.
-- ============================================================

CREATE TABLE IF NOT EXISTS health_metrics (
    id BIGSERIAL PRIMARY KEY,

    event_uuid UUID,

    source VARCHAR(50) NOT NULL,

    metric_type VARCHAR(100) NOT NULL,

    metric_value DOUBLE PRECISION,

    unit VARCHAR(50),

    recorded_at TIMESTAMPTZ NOT NULL,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


CREATE INDEX IF NOT EXISTS idx_health_metrics_source
    ON health_metrics(source);


CREATE INDEX IF NOT EXISTS idx_health_metrics_type
    ON health_metrics(metric_type);


CREATE INDEX IF NOT EXISTS idx_health_metrics_recorded_at
    ON health_metrics(recorded_at);


-- ============================================================
-- ML / ANOMALY DETECTION
-- Stores model-generated insights rather than modifying
-- the original health data.
-- ============================================================

CREATE TABLE IF NOT EXISTS anomalies (
    id BIGSERIAL PRIMARY KEY,

    metric_id BIGINT REFERENCES health_metrics(id)
        ON DELETE SET NULL,

    model_name VARCHAR(100) NOT NULL,

    model_version VARCHAR(50),

    anomaly_score DOUBLE PRECISION,

    severity VARCHAR(20),

    detected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    explanation JSONB,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


CREATE INDEX IF NOT EXISTS idx_anomalies_detected_at
    ON anomalies(detected_at);


CREATE INDEX IF NOT EXISTS idx_anomalies_severity
    ON anomalies(severity);


-- ============================================================
-- ALERTS
-- Separates ML detection from notification delivery.
-- ============================================================

CREATE TABLE IF NOT EXISTS alerts (
    id BIGSERIAL PRIMARY KEY,

    anomaly_id BIGINT REFERENCES anomalies(id)
        ON DELETE SET NULL,

    alert_type VARCHAR(100) NOT NULL,

    channel VARCHAR(50) NOT NULL,

    status VARCHAR(30) NOT NULL DEFAULT 'pending',

    message TEXT,

    triggered_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    delivered_at TIMESTAMPTZ,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


CREATE INDEX IF NOT EXISTS idx_alerts_status
    ON alerts(status);


CREATE INDEX IF NOT EXISTS idx_alerts_triggered_at
    ON alerts(triggered_at);


-- ============================================================
-- INGESTION SOURCES
-- Tracks connected external systems.
-- ============================================================

CREATE TABLE IF NOT EXISTS data_sources (
    id SERIAL PRIMARY KEY,

    name VARCHAR(100) UNIQUE NOT NULL,

    source_type VARCHAR(50) NOT NULL,

    enabled BOOLEAN NOT NULL DEFAULT TRUE,

    last_successful_sync TIMESTAMPTZ,

    last_error TEXT,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


INSERT INTO data_sources
    (name, source_type)
VALUES
    ('apple', 'wearable'),
    ('whoop', 'wearable')
ON CONFLICT (name) DO NOTHING;