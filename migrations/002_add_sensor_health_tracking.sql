-- Migration: Add sensor health tracking fields
-- Version: 002
-- Description: Adds health monitoring capabilities to sensors

-- Add health tracking columns to sensors table
ALTER TABLE sensors ADD COLUMN IF NOT EXISTS ip_address VARCHAR(45);
ALTER TABLE sensors ADD COLUMN IF NOT EXISTS health_check_port INTEGER DEFAULT 8080;
ALTER TABLE sensors ADD COLUMN IF NOT EXISTS last_reading_time TIMESTAMP;
ALTER TABLE sensors ADD COLUMN IF NOT EXISTS last_successful_reading_time TIMESTAMP;
ALTER TABLE sensors ADD COLUMN IF NOT EXISTS consecutive_failures INTEGER DEFAULT 0;
ALTER TABLE sensors ADD COLUMN IF NOT EXISTS total_readings INTEGER DEFAULT 0;
ALTER TABLE sensors ADD COLUMN IF NOT EXISTS total_failures INTEGER DEFAULT 0;
ALTER TABLE sensors ADD COLUMN IF NOT EXISTS last_health_check TIMESTAMP;
ALTER TABLE sensors ADD COLUMN IF NOT EXISTS last_health_status VARCHAR(20);

-- Create sensor_health_reports table for detailed health data
CREATE TABLE IF NOT EXISTS sensor_health_reports (
    id SERIAL PRIMARY KEY,
    sensor_id INTEGER NOT NULL REFERENCES sensors(id) ON DELETE CASCADE,
    report_time TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- Service status
    service_running BOOLEAN,
    service_uptime_seconds INTEGER,

    -- Sensor hardware status
    sensor_connected BOOLEAN,
    sensor_data_ready BOOLEAN,
    sensor_serial_number VARCHAR(50),

    -- Last reading info
    last_co2_ppm INTEGER,
    last_temperature_celsius FLOAT,
    last_humidity_percentage FLOAT,
    last_reading_time TIMESTAMP,

    -- System metrics
    system_uptime_seconds INTEGER,
    disk_usage_percent FLOAT,
    memory_usage_percent FLOAT,
    cpu_temperature_celsius FLOAT,

    -- Network info
    api_reachable BOOLEAN,
    api_response_time_ms INTEGER,

    -- Error info
    error_message TEXT,
    consecutive_failures INTEGER
);

-- Create index for efficient health report queries
CREATE INDEX IF NOT EXISTS idx_sensor_health_reports_sensor_time
ON sensor_health_reports(sensor_id, report_time DESC);

-- Add comment for documentation
COMMENT ON TABLE sensor_health_reports IS 'Stores detailed health reports from sensor diagnostic pings';
COMMENT ON COLUMN sensors.ip_address IS 'IP address of the sensor Pi for health checks';
COMMENT ON COLUMN sensors.health_check_port IS 'Port number for health check HTTP endpoint (default 8080)';
COMMENT ON COLUMN sensors.last_health_status IS 'Current health status: healthy, degraded, offline, unknown, inactive';
