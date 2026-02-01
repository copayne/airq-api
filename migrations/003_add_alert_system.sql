-- Migration: Add CO2 threshold alert system
-- Version: 003
-- Description: Adds configurable CO2 threshold alerts with per-user configuration,
--              alert history logging, and cooldown tracking for throttling.

-- Alert threshold configuration per user
CREATE TABLE IF NOT EXISTS alert_thresholds (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    sensor_id INTEGER REFERENCES sensors(id) ON DELETE CASCADE,  -- NULL = global default

    -- Threshold levels (PPM)
    warning_ppm INTEGER NOT NULL DEFAULT 1000,
    critical_ppm INTEGER NOT NULL DEFAULT 1500,

    -- Cooldown in minutes between alerts
    cooldown_minutes INTEGER NOT NULL DEFAULT 30,

    is_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- One threshold config per user per sensor (NULL sensor = global)
    CONSTRAINT unique_user_sensor_threshold UNIQUE (user_id, sensor_id)
);

-- Alert history log
CREATE TABLE IF NOT EXISTS alert_history (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    sensor_id INTEGER NOT NULL REFERENCES sensors(id) ON DELETE CASCADE,
    reading_id INTEGER NOT NULL REFERENCES sensor_readings(id) ON DELETE CASCADE,
    threshold_id INTEGER NOT NULL REFERENCES alert_thresholds(id) ON DELETE CASCADE,

    co2_ppm INTEGER NOT NULL,
    severity VARCHAR(20) NOT NULL,  -- 'warning' or 'critical'
    channels_sent VARCHAR(255) NOT NULL,  -- comma-separated: 'email,browser,ntfy'

    acknowledged BOOLEAN NOT NULL DEFAULT FALSE,
    acknowledged_at TIMESTAMP,

    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Cooldown tracking for throttling
CREATE TABLE IF NOT EXISTS alert_cooldowns (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    sensor_id INTEGER NOT NULL REFERENCES sensors(id) ON DELETE CASCADE,

    last_alert_time TIMESTAMP NOT NULL,
    last_severity VARCHAR(20) NOT NULL,  -- 'warning' or 'critical'

    CONSTRAINT unique_user_sensor_cooldown UNIQUE (user_id, sensor_id)
);

-- Indexes for efficient queries
CREATE INDEX IF NOT EXISTS idx_alert_thresholds_user ON alert_thresholds(user_id);
CREATE INDEX IF NOT EXISTS idx_alert_thresholds_sensor ON alert_thresholds(sensor_id);
CREATE INDEX IF NOT EXISTS idx_alert_history_user_created ON alert_history(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_alert_history_unacknowledged ON alert_history(user_id, acknowledged) WHERE acknowledged = FALSE;
CREATE INDEX IF NOT EXISTS idx_alert_cooldowns_user_sensor ON alert_cooldowns(user_id, sensor_id);

-- Documentation
COMMENT ON TABLE alert_thresholds IS 'Per-user CO2 threshold configuration for alert notifications';
COMMENT ON TABLE alert_history IS 'Log of triggered CO2 threshold alerts';
COMMENT ON TABLE alert_cooldowns IS 'Tracks last alert time per user/sensor for throttling';
