# Data Model & Schema Documentation

Complete documentation of the Hudson Air Quality API data model, relationships, and validation rules.

## Table of Contents
- [Overview](#overview)
- [Entity Relationship Diagram](#entity-relationship-diagram)
- [Core Entities](#core-entities)
- [Relationships](#relationships)
- [Validation Rules](#validation-rules)
- [Time-Series Data Structure](#time-series-data-structure)
- [Data Flow](#data-flow)

## Overview

The AirQ API uses a normalized relational database schema designed for efficient storage and querying of environmental sensor data. The schema supports:

- **Multi-sensor tracking** with flexible location assignment
- **Time-based location tracking** for mobile sensors
- **Normalized measurement storage** for efficient querying
- **Historical data preservation** with full audit trail
- **User management** with role-based access control

## Entity Relationship Diagram

```
┌─────────────┐    ┌─────────────────┐    ┌─────────────┐
│    User     │    │  SensorLocation │    │  Location   │
├─────────────┤    ├─────────────────┤    ├─────────────┤
│ id (PK)     │    │ id (PK)         │    │ id (PK)     │
│ username    │    │ sensor_id (FK)  │───►│ name        │
│ email       │    │ location_id (FK)│◄───│ description │
│ password_hash│    │ start_time      │    └─────────────┘
│ role        │    │ end_time        │
│ first_name  │    │ is_current      │
│ last_name   │    └─────────────────┘
│ is_active   │             │
│ created_at  │             │
│ updated_at  │             ▼
│ last_login  │    ┌─────────────────┐
└─────────────┘    │     Sensor      │
                   ├─────────────────┤
                   │ id (PK)         │
                   │ name            │
                   │ model           │
                   │ is_active       │
                   │ created_at      │
                   │ updated_at      │
                   └─────────────────┘
                            │
                            │ 1:N
                            ▼
                   ┌─────────────────┐
                   │ SensorReading   │
                   ├─────────────────┤
                   │ id (PK)         │
                   │ sensor_id (FK)  │
                   │ reading_time    │
                   │ created_at      │
                   └─────────────────┘
                            │
                            │ 1:1 (optional)
                   ┌────────┼────────┐
                   ▼        ▼        ▼
        ┌─────────────┐ ┌──────────────┐ ┌─────────────┐
        │HumidityReading│ │TemperatureReading│ │ CO2Reading  │
        ├─────────────┤ ├──────────────┤ ├─────────────┤
        │ id (PK)     │ │ id (PK)      │ │ id (PK)     │
        │ reading_id  │ │ reading_id   │ │ reading_id  │
        │ humidity_%  │ │ temperature_C│ │ co2_ppm     │
        └─────────────┘ └──────────────┘ └─────────────┘

                   ┌─────────────────┐
                   │   ErrorLog      │
                   ├─────────────────┤
                   │ id (PK)         │
                   │ reading_id (FK) │
                   │ error_message   │
                   │ request_data    │
                   │ response_data   │
                   │ created_at      │
                   └─────────────────┘
```

## Core Entities

### User
Represents system users with role-based access control.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | INTEGER | PRIMARY KEY, AUTO_INCREMENT | Unique user identifier |
| `username` | VARCHAR(50) | UNIQUE, NOT NULL | User's login name |
| `email` | VARCHAR(100) | UNIQUE, NOT NULL | User's email address |
| `password_hash` | VARCHAR(255) | NOT NULL | Bcrypt hashed password |
| `role` | VARCHAR(20) | NOT NULL, DEFAULT 'viewer' | User role (admin, user, viewer) |
| `first_name` | VARCHAR(50) | NULLABLE | User's first name |
| `last_name` | VARCHAR(50) | NULLABLE | User's last name |
| `is_active` | BOOLEAN | NOT NULL, DEFAULT TRUE | Account active status |
| `created_at` | TIMESTAMP | NOT NULL, DEFAULT NOW() | Account creation time |
| `updated_at` | TIMESTAMP | NOT NULL, DEFAULT NOW() | Last update time |
| `last_login` | TIMESTAMP | NULLABLE | Last successful login |

**Indexes:**
- `idx_user_username` on `username`
- `idx_user_email` on `email`
- `idx_user_role` on `role`

### Sensor
Represents physical sensor devices that collect environmental data.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | INTEGER | PRIMARY KEY, AUTO_INCREMENT | Unique sensor identifier |
| `name` | VARCHAR(100) | NOT NULL | Human-readable sensor name |
| `model` | VARCHAR(100) | NULLABLE | Sensor model/type information |
| `is_active` | BOOLEAN | NOT NULL, DEFAULT TRUE | Whether sensor is operational |
| `created_at` | TIMESTAMP | NOT NULL, DEFAULT NOW() | Sensor registration time |
| `updated_at` | TIMESTAMP | NOT NULL, DEFAULT NOW() | Last update time |

**Indexes:**
- `idx_sensor_active` on `is_active`
- `idx_sensor_name` on `name`

### Location
Represents physical locations where sensors can be placed.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | INTEGER | PRIMARY KEY, AUTO_INCREMENT | Unique location identifier |
| `name` | VARCHAR(100) | NOT NULL | Location name |
| `description` | TEXT | NULLABLE | Detailed location description |
| `created_at` | TIMESTAMP | NOT NULL, DEFAULT NOW() | Location creation time |
| `updated_at` | TIMESTAMP | NOT NULL, DEFAULT NOW() | Last update time |

**Indexes:**
- `idx_location_name` on `name`

### SensorLocation
Junction table tracking sensor placement over time with temporal relationships.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | INTEGER | PRIMARY KEY, AUTO_INCREMENT | Unique assignment identifier |
| `sensor_id` | INTEGER | NOT NULL, FOREIGN KEY | Reference to sensor |
| `location_id` | INTEGER | NOT NULL, FOREIGN KEY | Reference to location |
| `start_time` | TIMESTAMP | NOT NULL, DEFAULT NOW() | Assignment start time |
| `end_time` | TIMESTAMP | NULLABLE | Assignment end time (NULL = current) |
| `is_current` | BOOLEAN | COMPUTED | Whether this is the current assignment |

**Indexes:**
- `idx_sensor_location_sensor` on `sensor_id`
- `idx_sensor_location_location` on `location_id`
- `idx_sensor_location_current` on `is_current`
- `idx_sensor_location_time` on `start_time, end_time`

**Constraints:**
- Only one current assignment per sensor (`is_current = TRUE`)
- `end_time` must be greater than `start_time` when not NULL

### SensorReading
Base record for all sensor readings with timestamp and sensor reference.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | INTEGER | PRIMARY KEY, AUTO_INCREMENT | Unique reading identifier |
| `sensor_id` | INTEGER | NOT NULL, FOREIGN KEY | Reference to sensor |
| `reading_time` | TIMESTAMP | NOT NULL, DEFAULT NOW() | When reading was taken |
| `created_at` | TIMESTAMP | NOT NULL, DEFAULT NOW() | When record was created |

**Indexes:**
- `idx_sensor_reading_sensor` on `sensor_id`
- `idx_sensor_reading_time` on `reading_time`
- `idx_sensor_reading_sensor_time` on `sensor_id, reading_time`

### Measurement Tables

#### HumidityReading
Stores humidity measurement data.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | INTEGER | PRIMARY KEY, AUTO_INCREMENT | Unique measurement identifier |
| `reading_id` | INTEGER | NOT NULL, FOREIGN KEY, UNIQUE | Reference to base reading |
| `humidity_percentage` | DECIMAL(5,2) | NOT NULL, CHECK 0-100 | Humidity percentage (0.00-100.00%) |

#### TemperatureReading
Stores temperature measurement data.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | INTEGER | PRIMARY KEY, AUTO_INCREMENT | Unique measurement identifier |
| `reading_id` | INTEGER | NOT NULL, FOREIGN KEY, UNIQUE | Reference to base reading |
| `temperature_celsius` | DECIMAL(5,2) | NOT NULL, CHECK -40 to 85 | Temperature in Celsius (-40.00 to 85.00°C) |

#### CO2Reading
Stores CO2 measurement data.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | INTEGER | PRIMARY KEY, AUTO_INCREMENT | Unique measurement identifier |
| `reading_id` | INTEGER | NOT NULL, FOREIGN KEY, UNIQUE | Reference to base reading |
| `co2_ppm` | INTEGER | NOT NULL, CHECK 0-50000 | CO2 concentration in parts per million |

### ErrorLog
Tracks failed sensor reading attempts for debugging and monitoring.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | INTEGER | PRIMARY KEY, AUTO_INCREMENT | Unique error identifier |
| `reading_id` | INTEGER | NULLABLE, FOREIGN KEY | Reference to failed reading (if created) |
| `error_message` | TEXT | NOT NULL | Error description |
| `request_data` | JSON | NULLABLE | Original request data |
| `response_data` | JSON | NULLABLE | Error response data |
| `created_at` | TIMESTAMP | NOT NULL, DEFAULT NOW() | When error occurred |

## Relationships

### One-to-Many Relationships

1. **Sensor → SensorReading** (1:N)
   - One sensor can have many readings
   - Foreign key: `sensor_reading.sensor_id → sensor.id`

2. **SensorReading → Measurement Tables** (1:0..1)
   - One reading can have zero or one of each measurement type
   - Foreign keys: `*_reading.reading_id → sensor_reading.id`

3. **SensorReading → ErrorLog** (1:0..N)
   - One reading can have multiple error logs
   - Foreign key: `error_log.reading_id → sensor_reading.id`

### Many-to-Many Relationships

1. **Sensor ↔ Location** (M:N through SensorLocation)
   - Sensors can be moved between locations over time
   - Junction table: `SensorLocation` with temporal tracking
   - Supports historical location tracking

### Temporal Relationships

The `SensorLocation` table implements temporal relationships:

```sql
-- Current sensor location
WHERE sensor_location.is_current = TRUE

-- Sensor location at specific time
WHERE sensor_location.start_time <= :timestamp 
  AND (sensor_location.end_time IS NULL OR sensor_location.end_time >= :timestamp)

-- Sensor location during time range
WHERE sensor_location.start_time < :end_time 
  AND (sensor_location.end_time IS NULL OR sensor_location.end_time > :start_time)
```

## Validation Rules

### Application-Level Validation

#### Sensor Reading Validation
- **Humidity**: 0.00% - 100.00% (2 decimal places max)
- **Temperature**: -40.00°C - 85.00°C (2 decimal places max)
- **CO2**: 0 - 50,000 ppm (integers only)
- **Sensor**: Must exist and be active
- **Required**: At least one measurement type per reading

#### User Validation
- **Username**: 3-50 characters, alphanumeric + underscore + hyphen
- **Email**: Valid email format with @ and domain
- **Password**: 8-128 characters
- **Names**: Max 50 characters each

### Database-Level Constraints

#### Check Constraints
```sql
-- Humidity validation
ALTER TABLE humidity_reading ADD CONSTRAINT chk_humidity_range 
CHECK (humidity_percentage >= 0 AND humidity_percentage <= 100);

-- Temperature validation
ALTER TABLE temperature_reading ADD CONSTRAINT chk_temperature_range 
CHECK (temperature_celsius >= -40 AND temperature_celsius <= 85);

-- CO2 validation
ALTER TABLE co2_reading ADD CONSTRAINT chk_co2_range 
CHECK (co2_ppm >= 0 AND co2_ppm <= 50000);

-- SensorLocation temporal constraint
ALTER TABLE sensor_location ADD CONSTRAINT chk_time_order 
CHECK (end_time IS NULL OR end_time > start_time);
```

#### Unique Constraints
```sql
-- Only one current location per sensor
CREATE UNIQUE INDEX idx_sensor_current_location 
ON sensor_location (sensor_id) 
WHERE is_current = TRUE;

-- One measurement per reading per type
ALTER TABLE humidity_reading ADD CONSTRAINT uk_humidity_reading 
UNIQUE (reading_id);
```

## Time-Series Data Structure

### Reading Timestamps
- **reading_time**: When the measurement was actually taken
- **created_at**: When the record was inserted into the database
- **Timezone**: All timestamps stored in UTC

### Historical Data Access
```sql
-- Readings from last 24 hours
WHERE reading_time >= NOW() - INTERVAL '24 hours'

-- Readings from specific date range
WHERE reading_time BETWEEN '2024-01-01' AND '2024-01-31'

-- Latest reading per sensor
SELECT DISTINCT ON (sensor_id) 
  sensor_id, reading_time, ...
FROM sensor_reading 
ORDER BY sensor_id, reading_time DESC;
```

### Data Retention
- **Sensor readings**: Indefinite retention
- **Error logs**: Configurable retention (default: 90 days)
- **User sessions**: JWT token expiration (default: 1 hour)

## Data Flow

### Sensor Reading Creation Flow

1. **Input Validation**
   - Validate sensor exists and is active
   - Validate measurement ranges
   - Validate data types and precision

2. **Database Transaction**
   ```sql
   BEGIN;
   INSERT INTO sensor_reading (sensor_id, reading_time) VALUES (...);
   INSERT INTO humidity_reading (reading_id, humidity_percentage) VALUES (...);
   INSERT INTO temperature_reading (reading_id, temperature_celsius) VALUES (...);
   INSERT INTO co2_reading (reading_id, co2_ppm) VALUES (...);
   COMMIT;
   ```

3. **Location Resolution**
   - Determine sensor location at reading time
   - Use temporal SensorLocation relationships

4. **Error Handling**
   - Log validation errors to ErrorLog
   - Rollback transaction on database errors
   - Return structured error responses

### Query Optimization Patterns

#### Efficient Reading Queries
```sql
-- Optimized query with proper indexes
SELECT sr.*, hr.humidity_percentage, tr.temperature_celsius, cr.co2_ppm
FROM sensor_reading sr
LEFT JOIN humidity_reading hr ON sr.id = hr.reading_id
LEFT JOIN temperature_reading tr ON sr.id = tr.reading_id
LEFT JOIN co2_reading cr ON sr.id = cr.reading_id
WHERE sr.sensor_id = ? 
  AND sr.reading_time >= ?
ORDER BY sr.reading_time DESC
LIMIT 100;
```

#### Location-Based Queries
```sql
-- Readings from specific location with temporal join
SELECT sr.*, l.name as location_name
FROM sensor_reading sr
JOIN sensor_location sl ON sr.sensor_id = sl.sensor_id
JOIN location l ON sl.location_id = l.id
WHERE l.id = ?
  AND sl.start_time <= sr.reading_time
  AND (sl.end_time IS NULL OR sl.end_time >= sr.reading_time)
ORDER BY sr.reading_time DESC;
```

### Performance Considerations

#### Indexes for Common Queries
- **Time-based queries**: `idx_sensor_reading_time`
- **Sensor-specific queries**: `idx_sensor_reading_sensor_time`
- **Location queries**: `idx_sensor_location_time`
- **User queries**: `idx_user_username`, `idx_user_email`

#### Query Patterns
- Use `LIMIT` for pagination
- Use date range filters to limit time-series data
- Use `LEFT JOIN` for optional measurements
- Use `DISTINCT ON` for latest-per-group queries

This normalized schema design provides flexibility for sensor management while maintaining query performance and data integrity.