-- scripts/init_timescaledb.sql
-- SkyGuard AI / DataMend — TimescaleDB Initialization & Hypertables DDL

CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;

-- 1. Stations Metadata Table
CREATE TABLE IF NOT EXISTS stations (
    id SERIAL PRIMARY KEY,
    station_id VARCHAR(64) UNIQUE NOT NULL,
    name VARCHAR(255),
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    elevation DOUBLE PRECISION,
    status VARCHAR(32) NOT NULL DEFAULT 'ACTIVE',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 2. Raw Observations Table (Hypertable)
CREATE TABLE IF NOT EXISTS observations (
    id BIGSERIAL,
    station_id VARCHAR(64) NOT NULL REFERENCES stations(station_id) ON DELETE CASCADE,
    timestamp TIMESTAMPTZ NOT NULL,
    temperature DOUBLE PRECISION,
    pressure DOUBLE PRECISION,
    humidity DOUBLE PRECISION,
    validation_status VARCHAR(32) NOT NULL DEFAULT 'VALID',
    tier0_flag VARCHAR(32) NOT NULL DEFAULT 'PASS',
    source_type VARCHAR(32) DEFAULT 'SIMULATED',
    source_id VARCHAR(64),
    provider VARCHAR(64),
    device_id VARCHAR(64),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (id, timestamp)
);

-- Convert observations to Timescale hypertable partitioned by timestamp (1-day chunks)
SELECT create_hypertable('observations', 'timestamp', chunk_time_interval => INTERVAL '1 day', if_not_exists => TRUE);

-- Compound indexes for rapid temporal and spatial querying
CREATE INDEX IF NOT EXISTS idx_obs_station_timestamp ON observations (station_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_obs_timestamp_station ON observations (timestamp DESC, station_id);

-- 3. Anomaly Events Table
CREATE TABLE IF NOT EXISTS anomaly_events (
    id BIGSERIAL PRIMARY KEY,
    observation_id BIGINT,
    station_id VARCHAR(64) NOT NULL REFERENCES stations(station_id) ON DELETE CASCADE,
    timestamp TIMESTAMPTZ NOT NULL,
    is_anomaly BOOLEAN NOT NULL DEFAULT TRUE,
    anomaly_score DOUBLE PRECISION NOT NULL,
    confidence DOUBLE PRECISION NOT NULL,
    severity VARCHAR(32) NOT NULL,
    anomaly_type VARCHAR(64),
    classification VARCHAR(64) NOT NULL DEFAULT 'ANOMALY',
    is_fault BOOLEAN NOT NULL DEFAULT TRUE,
    source_type VARCHAR(32) DEFAULT 'SIMULATED',
    source_id VARCHAR(64),
    reason TEXT,
    explanation JSONB,
    tier_scores JSONB,
    recommended_action TEXT,
    raw_values JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_anom_station_timestamp ON anomaly_events (station_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_anom_timestamp ON anomaly_events (timestamp DESC);

CREATE TABLE IF NOT EXISTS sensor_health (
    id BIGSERIAL,
    station_id VARCHAR(64) NOT NULL REFERENCES stations(station_id) ON DELETE CASCADE,
    timestamp TIMESTAMPTZ NOT NULL,
    health_score DOUBLE PRECISION NOT NULL,
    health_status VARCHAR(32) NOT NULL DEFAULT 'EXCELLENT',
    anomaly_rate DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    drift_score DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    data_quality_score DOUBLE PRECISION NOT NULL DEFAULT 100.0,
    degradation_risk VARCHAR(32) NOT NULL DEFAULT 'STABLE',
    estimated_hours_to_failure DOUBLE PRECISION,
    recommended_action TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (id, timestamp)
);

SELECT create_hypertable('sensor_health', 'timestamp', chunk_time_interval => INTERVAL '7 days', if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS idx_health_station_timestamp ON sensor_health (station_id, timestamp DESC);

-- 5. Operator Feedback Table (Human-in-the-Loop Active Learning)
CREATE TABLE IF NOT EXISTS operator_feedback (
    id BIGSERIAL PRIMARY KEY,
    event_id BIGINT REFERENCES anomaly_events(id) ON DELETE SET NULL,
    station_id VARCHAR(64) NOT NULL REFERENCES stations(station_id) ON DELETE CASCADE,
    timestamp TIMESTAMPTZ NOT NULL,
    operator_id VARCHAR(64) NOT NULL,
    verification_status VARCHAR(32) NOT NULL, -- CONFIRMED_FAULT, FALSE_ALARM, CONFIRMED_WEATHER_EVENT
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_feedback_station ON operator_feedback (station_id, timestamp DESC);

-- 6. Seed Default Reference Weather Stations
INSERT INTO stations (station_id, name, latitude, longitude, elevation, status)
VALUES
    ('AWS-001', 'Central Meteorological Observatory (New Delhi)', 28.6139, 77.2090, 216.0, 'ACTIVE'),
    ('AWS-002', 'Coastal Marine Weather Tower (Mumbai)', 18.9220, 72.8347, 14.0, 'ACTIVE'),
    ('AWS-003', 'Plateau Highland Station (Dharamshala)', 32.2190, 76.3234, 1457.0, 'ACTIVE'),
    ('AWS-004', 'Arid Subtropical Outpost (Jaisalmer)', 26.9124, 70.9022, 225.0, 'ACTIVE'),
    ('PUNE-EXT-001', 'Pune Meteorological Center (Open-Meteo)', 18.5204, 73.8567, 560.0, 'ACTIVE'),
    ('DELHI-EXT-001', 'New Delhi Safdarjung Synoptic Site', 28.6139, 77.2090, 216.0, 'ACTIVE'),
    ('AWS-ESP32-001', 'Hardware AWS Microstation (ESP32 + BME280)', 28.5355, 77.3910, 200.0, 'ACTIVE')
ON CONFLICT (station_id) DO NOTHING;
