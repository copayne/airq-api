# CLAUDE.md

## Specific Project Information

### Development Setup
- **Create virtual environment**: `python3 -m venv airq` then `source airq/bin/activate`
- **Install dependencies**: `pip install -r requirements.txt`
- **Initialize database**: `python3 init_db.py`
- **Add dummy data**: `python3 db-dummy-data.py`

### Running the Application
- **Start development server**: `python3 run.py`
- **Access GraphQL playground**: http://127.0.0.1:5000/graphql

### Database Setup
- **Create PostgreSQL database**: `sudo -u postgres psql` then `CREATE DATABASE airq;`
- **Database URI**: `postgresql://postgres:1883@localhost/airq`

## Architecture

### Core Components
- **Flask app factory**: `app/__init__.py` creates the Flask app with SQLAlchemy, CORS, and GraphQL endpoint
- **Database models**: `app/models.py` defines normalized schema for sensor readings with separate tables for each measurement type
- **GraphQL schema**: `app/schema.py` provides GraphQL interface with complex filtering and relationship resolution
- **Configuration**: `config.py` handles database connection and environment variables

### Database Schema
The schema is normalized to support multiple sensor types and flexible location tracking:

- **Sensors**: Physical devices with model info and active status
- **Locations**: Named locations where sensors can be placed
- **SensorLocation**: Junction table tracking sensor movements over time with start/end timestamps
- **SensorReading**: Base reading record with sensor_id and timestamp
- **Specific readings**: Separate tables for HumidityReading, TemperatureReading, CO2Reading linked to base reading
- **ErrorLog**: Tracks failed sensor readings with request/response data

### Key Features
- **Time-based sensor location tracking**: Sensors can move between locations with historical tracking
- **Flexible measurement types**: Easy to add new sensor reading types
- **GraphQL filtering**: Complex filtering by date ranges, measurement values, sensors, and locations
- **Relationship resolution**: GraphQL automatically resolves sensor locations at reading time
- **Mutation support**: Create new sensor readings via GraphQL mutations

### GraphQL Endpoints
- **Query**: All entity types with filtering, relationships, and pagination
- **Mutation**: `createSensorReading` for adding new measurements
- **Filtering**: `filteredSensorReadings` supports date ranges, measurement thresholds, sensor/location filtering, ordering, and pagination

The API serves as the backend for the Hudson Air Quality App, providing both historical data storage and real-time sensor reading ingestion.
