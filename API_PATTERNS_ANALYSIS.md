# AirQ API Backend Analysis - Patterns for Metrics Endpoint

## Overview
The airq-api is a Flask/GraphQL backend application for the Hudson Air Quality monitoring system. It provides a comprehensive GraphQL API for sensor management and air quality data aggregation.

---

## 1. Directory Structure

```
/home/copayne/dev/airq/airq-api/
├── app/                          # Main application code
│   ├── __init__.py              # Flask app factory and initialization
│   ├── schema.py                # GraphQL schema definitions (1088 lines)
│   ├── models.py                # SQLAlchemy database models (417 lines)
│   ├── auth.py                  # Authentication and authorization
│   ├── validation.py            # Data validation logic
│   ├── email_service.py         # Email notification service
│   ├── graphql_security.py      # GraphQL security middleware
│   └── logging_config.py        # Structured logging configuration
├── tests/
│   ├── unit/                    # Unit tests for models and business logic
│   ├── integration/             # Integration tests for GraphQL endpoints
│   └── conftest.py              # Pytest configuration and fixtures
├── config.py                    # Configuration management (environment-based)
├── run.py                       # Application entry point
├── requirements.txt             # Python dependencies
├── init_db.py                   # Database initialization script
├── db-dummy-data.py            # Test data population script
├── airq2/                       # Virtual environment (Python 3.12)
└── docs/                        # API documentation
```

---

## 2. Virtual Environment

**Location**: `/home/copayne/dev/airq/airq-api/airq2/`
**Python Version**: 3.12
**Activation**: `source airq2/bin/activate`

---

## 3. Core Dependencies

Key packages from `requirements.txt`:
```
Flask==2.1.0
Flask-SQLAlchemy==2.5.1
Flask-Cors==4.0.1
graphene==2.1.9
graphene-sqlalchemy==2.3.0
Flask-GraphQL==2.0.1
psycopg2-binary==2.9.3
PyJWT==2.8.0
passlib==1.7.4
bcrypt==4.0.1
```

---

## 4. Database Layer & ORM

### Database Configuration
- **ORM**: SQLAlchemy (Flask-SQLAlchemy wrapper)
- **Database**: PostgreSQL (primary), SQLite in-memory (testing)
- **Connection Pooling**: Configured with pool_size=10, max_overflow=20
- **Environment Variable**: `DATABASE_URL`

### Model Structure Pattern
Database models are defined in `/home/copayne/dev/airq/airq-api/app/models.py`:

```python
# Base model pattern with relationships
class Sensor(db.Model):
    __tablename__ = 'sensors'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    model = db.Column(db.String(100), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    
    # Relationships for eager loading
    readings = relationship("SensorReading", back_populates="sensor", lazy="select")
    sensor_locations = relationship("SensorLocation", back_populates="sensor", lazy="select")

# Specific measurement tables (normalized schema)
class HumidityReading(db.Model):
    __tablename__ = 'humidity_readings'
    id = db.Column(db.Integer, primary_key=True)
    reading_id = db.Column(db.Integer, db.ForeignKey('sensor_readings.id'), nullable=False, index=True)
    humidity_percentage = db.Column(db.Float, nullable=False)
    sensor_reading = relationship("SensorReading", back_populates="humidity_reading")

class TemperatureReading(db.Model):
    __tablename__ = 'temperature_readings'
    id = db.Column(db.Integer, primary_key=True)
    reading_id = db.Column(db.Integer, db.ForeignKey('sensor_readings.id'), nullable=False, index=True)
    temperature_celsius = db.Column(db.Float, nullable=False)
    sensor_reading = relationship("SensorReading", back_populates="temperature_reading")

class CO2Reading(db.Model):
    __tablename__ = 'co2_readings'
    id = db.Column(db.Integer, primary_key=True)
    reading_id = db.Column(db.Integer, db.ForeignKey('sensor_readings.id'), nullable=False, index=True)
    co2_ppm = db.Column(db.Integer, nullable=False)
    sensor_reading = relationship("SensorReading", back_populates="co2_reading")
```

### Query Optimization Patterns

#### Pattern 1: Eager Loading with selectinload and joinedload
```python
# From schema.py line 933-938
query = SensorReadingModel.query.options(
    joinedload(SensorReadingModel.sensor).selectinload(Sensor.sensor_locations)
        .selectinload(SensorLocation.location),
    joinedload(SensorReadingModel.humidity_reading),
    joinedload(SensorReadingModel.temperature_reading),
    joinedload(SensorReadingModel.co2_reading)
).order_by(desc(SensorReadingModel.reading_time)).limit(1000).all()
```

#### Pattern 2: Filtering with Outer Joins
```python
# From schema.py lines 1002-1028 (filtered_sensor_readings)
if filters.min_co2_ppm or filters.max_co2_ppm:
    query = query.outerjoin(CO2Reading)
    if filters.min_co2_ppm:
        measurement_filters.append(CO2Reading.co2_ppm >= filters.min_co2_ppm)
    if filters.max_co2_ppm:
        measurement_filters.append(CO2Reading.co2_ppm <= filters.max_co2_ppm)

# Apply all filters together with 'and'
if measurement_filters:
    query = query.filter(and_(*measurement_filters))
```

#### Pattern 3: Time-Based Location Resolution
```python
# From schema.py lines 83-92 (resolve_location in SensorReadingObject)
sensor_location = SensorLocation.query.filter(
    SensorLocation.sensor_id == self.sensor_id,
    SensorLocation.start_time <= self.reading_time,
    or_(
        SensorLocation.end_time.is_(None),
        SensorLocation.end_time >= self.reading_time
    )
).options(joinedload(SensorLocation.location)).first()
```

### Performance Indexes
From models.py lines 407-417:
```python
# Composite indexes for critical query performance
db.Index('idx_sensor_readings_sensor_time', SensorReading.sensor_id, SensorReading.reading_time)
db.Index('idx_sensor_locations_sensor_time_range', SensorLocation.sensor_id, 
         SensorLocation.start_time, SensorLocation.end_time)
db.Index('idx_sensor_locations_location_current', SensorLocation.location_id, 
         SensorLocation.is_current)
db.Index('idx_application_error_logs_timestamp_level', ApplicationErrorLog.timestamp, 
         ApplicationErrorLog.level)
```

---

## 5. Aggregation/Calculations - Current Patterns

**Important**: The current codebase does NOT include any aggregation functions (averages, running totals, etc.). All aggregations would need to be implemented NEW for the metrics endpoint.

However, the filtering patterns provide a foundation:

### Available Filtering Input Type (from schema.py lines 134-149)
```python
class SensorDataFilterInput(graphene.InputObjectType):
    start_date = graphene.DateTime()
    end_date = graphene.DateTime()
    min_co2_ppm = graphene.Float()
    max_co2_ppm = graphene.Float()
    min_temperature_celsius = graphene.Float()
    max_temperature_celsius = graphene.Float()
    min_humidity_percentage = graphene.Float()
    max_humidity_percentage = graphene.Float()
    sensor_ids = graphene.List(graphene.ID)
    location_ids = graphene.List(graphene.ID)
    limit = graphene.Int(description="Maximum number of records to return")
    offset = graphene.Int(description="Number of records to skip")
    order_by = graphene.String(description="Field to order by")
    order_direction = graphene.String(description="Direction of ordering (asc or desc)")
```

---

## 6. GraphQL Schema Structure

### File Location
`/home/copayne/dev/airq/airq-api/app/schema.py` (1088 lines)

### Core Components

#### 6.1 GraphQL Object Types (SQLAlchemy Wrappers)
Pattern for creating GraphQL types from SQLAlchemy models (lines 55-92):

```python
class SensorReadingObject(SQLAlchemyObjectType):
    class Meta:
        model = SensorReadingModel
    
    sensor = graphene.Field(lambda: SensorObject)
    humidity_reading = graphene.Field(lambda: HumidityReadingObject)
    temperature_reading = graphene.Field(lambda: TemperatureReadingObject)
    co2_reading = graphene.Field(lambda: CO2ReadingObject)
    location = graphene.Field(lambda: LocationObject)

    def resolve_sensor(self, info: Any) -> Sensor:
        return self.sensor

    def resolve_humidity_reading(self, info: Any) -> Optional[HumidityReading]:
        return self.humidity_reading
    
    def resolve_location(self, info: Any) -> Optional[Location]:
        """Get the location where this sensor reading was taken."""
        sensor_location = SensorLocation.query.filter(
            SensorLocation.sensor_id == self.sensor_id,
            SensorLocation.start_time <= self.reading_time,
            or_(SensorLocation.end_time.is_(None), SensorLocation.end_time >= self.reading_time)
        ).options(joinedload(SensorLocation.location)).first()
        
        return sensor_location.location if sensor_location else None
```

#### 6.2 Input Types for Mutations
Pattern (lines 152-157):

```python
class CreateSensorReadingInput(graphene.InputObjectType):
    sensor_id = graphene.Int(required=True)
    humidity_percentage = graphene.Float()
    temperature_celsius = graphene.Float()
    co2_ppm = graphene.Int()
```

#### 6.3 Mutations
Pattern for mutations (lines 158-250):

```python
class CreateSensorReading(graphene.Mutation):
    class Arguments:
        input = CreateSensorReadingInput(required=True)

    sensor_reading = graphene.Field(lambda: SensorReadingObject)
    success = graphene.Boolean()
    message = graphene.String()
    errors = graphene.List(graphene.String)

    @staticmethod
    def mutate(root: Any, info: Any, input: CreateSensorReadingInput) -> 'CreateSensorReading':
        # Validation
        validator = SensorDataValidator()
        validation_result = validator.validate_sensor_reading_input(...)
        
        if not validation_result.is_valid:
            return CreateSensorReading(
                sensor_reading=None,
                success=False,
                message="Validation failed",
                errors=validation_result.error_messages
            )
        
        # Database operations
        try:
            sensor_reading = SensorReadingModel(sensor_id=input.sensor_id)
            db.session.add(sensor_reading)
            db.session.flush()
            
            # Create specific readings
            if input.humidity_percentage is not None:
                humidity_reading = HumidityReading(...)
                db.session.add(humidity_reading)
            
            db.session.commit()
            
            logger.info("Sensor reading created successfully", extra={...})
            return CreateSensorReading(
                sensor_reading=sensor_reading,
                success=True,
                message="Reading created",
                errors=[]
            )
        except Exception as e:
            db.session.rollback()
            return CreateSensorReading(
                sensor_reading=None,
                success=False,
                message=str(e),
                errors=[str(e)]
            )
```

#### 6.4 Query Class (lines 886-1080)
Main query root type with field resolvers:

```python
class Query(graphene.ObjectType):
    sensors = graphene.List(SensorObject)
    locations = graphene.List(LocationObject)
    sensor_locations = graphene.List(SensorLocationObject)
    sensor_readings = graphene.List(SensorReadingObject)
    humidity_readings = graphene.List(HumidityReadingObject)
    temperature_readings = graphene.List(TemperatureReadingObject)
    co2_readings = graphene.List(CO2ReadingObject)
    error_logs = graphene.List(ErrorLogObject)
    
    # User queries with authentication
    users = graphene.List(UserObject)
    me = graphene.Field(UserObject)

    # Single entity queries
    sensor = graphene.Field(SensorObject, id=graphene.Int(required=True))
    location = graphene.Field(LocationObject, id=graphene.Int(required=True))
    user = graphene.Field(UserObject, id=graphene.Int(required=True))

    def resolve_sensors(self, info: Any) -> List[Sensor]:
        return Sensor.query.options(...).all()
    
    filtered_sensor_readings = graphene.List(
        SensorReadingObject, 
        filters=SensorDataFilterInput(required=True)
    )

    def resolve_filtered_sensor_readings(self, info: Any, 
                                        filters: SensorDataFilterInput) -> List[SensorReadingModel]:
        # Complex filtering with optimized queries (lines 987-1080)
        ...
```

---

## 7. JSON Response Formats

### Standard Query Response Structure
All GraphQL responses follow the standard GraphQL pattern:

```json
{
  "data": {
    "queryName": [
      {
        "id": "1",
        "field1": "value1",
        "field2": "value2",
        "nestedObject": {
          "nestedId": "1",
          "nestedField": "value"
        }
      }
    ]
  }
}
```

### Sensor Reading Response Example (from integration tests)
```json
{
  "data": {
    "sensorReadings": [
      {
        "id": "1",
        "readingTime": "2024-10-29T14:30:00",
        "isSuccess": true,
        "sensor": {
          "id": "1",
          "name": "Sensor 1"
        },
        "humidityReading": {
          "humidityPercentage": 45.5
        },
        "temperatureReading": {
          "temperatureCelsius": 22.3
        },
        "co2Reading": {
          "co2Ppm": 450
        }
      }
    ]
  }
}
```

### Mutation Response Structure (Create patterns)
```json
{
  "data": {
    "createSensorReading": {
      "sensorReading": {
        "id": "1",
        "readingTime": "2024-10-29T14:30:00"
      },
      "success": true,
      "message": "Reading created",
      "errors": []
    }
  }
}
```

### Error Response
```json
{
  "data": {
    "createSensorReading": {
      "sensorReading": null,
      "success": false,
      "message": "Validation failed",
      "errors": ["humidity_percentage must be between 0 and 100"]
    }
  }
}
```

---

## 8. Authentication & Authorization

### File Location
`/home/copayne/dev/airq/airq-api/app/auth.py`

### Authentication Patterns

#### JWT Token Generation (User model, lines 53-78)
```python
def generate_jwt_token(self, expires_in: int = 3600) -> str:
    """Generate JWT token for user authentication."""
    jti = self._generate_secure_token()  # Unique token ID for blacklisting
    exp_time = datetime.utcnow() + timedelta(seconds=expires_in)
    
    payload = {
        'user_id': self.id,
        'username': self.username,
        'role': self.role,
        'jti': jti,
        'exp': exp_time,
        'iat': datetime.utcnow()
    }
    
    secret_key = os.environ.get('SECRET_KEY')
    return jwt.encode(payload, secret_key, algorithm='HS256')
```

### Authorization Decorators Pattern
From auth.py:
```python
@require_admin  # Only admin users can access
def resolve_users(self, info: Any) -> List[User]:
    """Get all users (admin only)."""
    return User.query.all()

@require_user   # Authenticated users required
def resolve_me(self, info: Any) -> Optional[User]:
    """Get current authenticated user."""
    return get_user_from_context(info)
```

### Role-Based Access Control
User model (lines 23-24, 114-137):
```python
role = db.Column(db.String(20), nullable=False, default='viewer', index=True)
# Roles: admin, user, viewer

def has_permission(self, required_role: str) -> bool:
    """Check if user has required permission level."""
    # Permission hierarchy: admin > user > viewer
    role_hierarchy = {
        'viewer': 1,
        'user': 2,
        'admin': 3
    }
    
    user_level = role_hierarchy.get(self.role, 0)
    required_level = role_hierarchy.get(required_role, 0)
    
    return user_level >= required_level
```

---

## 9. Validation Patterns

### File Location
`/home/copayne/dev/airq/airq-api/app/validation.py`

### Validation Pattern in Mutations
```python
# From schema.py lines 175-203
from app.validation import SensorDataValidator

validator = SensorDataValidator()
validation_result = validator.validate_sensor_reading_input(
    sensor_id=input.sensor_id,
    humidity_percentage=input.humidity_percentage,
    temperature_celsius=input.temperature_celsius,
    co2_ppm=input.co2_ppm
)

if not validation_result.is_valid:
    logger.warning("Sensor reading validation failed", extra={
        'extra_context': {
            'sensor_id': input.sensor_id,
            'validation_errors': validation_result.error_messages,
            'operation': 'create_sensor_reading_validation'
        }
    })
    return CreateSensorReading(
        sensor_reading=None,
        success=False,
        message="Validation failed",
        errors=validation_result.error_messages
    )
```

---

## 10. Logging Configuration

### File Location
`/home/copayne/dev/airq/airq-api/app/logging_config.py`

### Logging Pattern in Operations
```python
logger.info(
    "Sensor reading created successfully",
    extra={
        'extra_context': {
            'sensor_id': input.sensor_id,
            'reading_id': sensor_reading.id,
            'has_humidity': input.humidity_percentage is not None,
            'has_temperature': input.temperature_celsius is not None,
            'has_co2': input.co2_ppm is not None,
            'operation': 'create_sensor_reading_success'
        }
    }
)
```

---

## 11. GraphQL Security Configuration

### File Location
`/home/copayne/dev/airq/airq-api/app/graphql_security.py`

### Security Features
- Query depth limiting (default: 8 in production, 15 in dev)
- Query complexity analysis (default: 150 in production, 200 in dev)
- Rate limiting (100 requests/minute by default)
- Query timeout (30 seconds)
- Introspection control (disabled in production)

### Configuration in app/__init__.py (lines 46-59)
```python
security_middleware = GraphQLSecurityMiddleware(
    app=app,
    requests_per_minute=app.config.get('GRAPHQL_RATE_LIMIT_PER_MINUTE', 100)
)

graphql_view = GraphQLView.as_view(
    'graphql',
    schema=schema,
    graphiql=app.config.get('GRAPHQL_GRAPHIQL_ENABLED', False),
    introspection=app.config.get('GRAPHQL_INTROSPECTION_ENABLED', False)
)

app.add_url_rule('/graphql', view_func=graphql_view)
```

---

## 12. Testing Patterns

### File Structure
```
tests/
├── conftest.py              # Shared fixtures and configuration
├── unit/
│   ├── test_models.py
│   ├── test_validation.py
│   ├── test_authentication.py
│   └── test_auth_security.py
└── integration/
    ├── test_graphql_api.py
    ├── test_validation_graphql.py
    └── test_auth_graphql.py
```

### GraphQL Query Test Pattern (from test_graphql_api.py)
```python
@pytest.mark.integration
class TestGraphQLQueries:
    """Test GraphQL query endpoints."""
    
    def test_sensor_readings_query(self, client, session, sample_reading_with_data):
        """Test sensor readings query with measurements."""
        query = """
        query {
            sensorReadings {
                id
                readingTime
                isSuccess
                sensor {
                    id
                    name
                }
                humidityReading {
                    humidityPercentage
                }
                temperatureReading {
                    temperatureCelsius
                }
                co2Reading {
                    co2Ppm
                }
            }
        }
        """
        
        response = client.post('/graphql',
                             json={'query': query},
                             headers={'Content-Type': 'application/json'})
        
        assert response.status_code == 200
        data = response.get_json()
        
        assert 'data' in data
        assert 'sensorReadings' in data['data']
        assert len(data['data']['sensorReadings']) >= 1
```

### Filtered Query Test Pattern
```python
def test_filtered_sensor_readings_query(self, client, session, sample_reading_with_data):
    """Test filtered sensor readings query."""
    query = """
    query FilteredReadings($filters: SensorDataFilterInput!) {
        filteredSensorReadings(filters: $filters) {
            id
            readingTime
            sensor {
                id
                name
            }
            humidityReading {
                humidityPercentage
            }
        }
    }
    """
    
    variables = {
        "filters": {
            "limit": 10,
            "orderDirection": "desc"
        }
    }
    
    response = client.post('/graphql',
                         json={'query': query, 'variables': variables},
                         headers={'Content-Type': 'application/json'})
    
    assert response.status_code == 200
    data = response.get_json()
    assert 'data' in data
    assert 'filteredSensorReadings' in data['data']
```

---

## 13. Implementation Recommendations for Metrics Endpoint

### 13.1 Where to Add Code

**New GraphQL Types** (add to schema.py):
```python
# Example: AverageMetric type
class AverageMetricObject(graphene.ObjectType):
    """Aggregated metric data for a location/sensor."""
    sensor_id = graphene.Int()
    sensor_name = graphene.String()
    location_id = graphene.Int()
    location_name = graphene.String()
    start_time = graphene.DateTime()
    end_time = graphene.DateTime()
    avg_co2_ppm = graphene.Float()
    avg_humidity_percentage = graphene.Float()
    avg_temperature_celsius = graphene.Float()
    min_co2_ppm = graphene.Float()
    max_co2_ppm = graphene.Float()
    reading_count = graphene.Int()
```

**New Input Type** (add to schema.py):
```python
class MetricsFilterInput(graphene.InputObjectType):
    sensor_ids = graphene.List(graphene.ID)
    location_ids = graphene.List(graphene.ID)
    start_date = graphene.DateTime(required=True)
    end_date = graphene.DateTime(required=True)
    interval = graphene.String()  # 'hourly', 'daily', 'weekly', 'monthly'
```

**New Query Field** (add to Query class in schema.py around line 980):
```python
metrics = graphene.List(
    AverageMetricObject,
    filters=MetricsFilterInput(required=True)
)

def resolve_metrics(self, info: Any, filters: MetricsFilterInput) -> List[AverageMetricObject]:
    # Implementation with aggregations
    pass
```

**Database Query Pattern**:
Use SQLAlchemy's `func` module from sqlalchemy for aggregations:
```python
from sqlalchemy import func

# Pattern:
result = db.session.query(
    SensorReading.sensor_id,
    func.avg(HumidityReading.humidity_percentage).label('avg_humidity'),
    func.min(CO2Reading.co2_ppm).label('min_co2'),
    func.max(CO2Reading.co2_ppm).label('max_co2'),
    func.count(SensorReading.id).label('reading_count')
).join(HumidityReading).join(CO2Reading).filter(
    SensorReading.reading_time >= start_time,
    SensorReading.reading_time <= end_time
).group_by(SensorReading.sensor_id).all()
```

### 13.2 Validation Pattern to Follow
```python
# Validate filters
if not filters.start_date or not filters.end_date:
    logger.warning("Metrics query missing required dates")
    return []

if filters.end_date <= filters.start_date:
    logger.warning("Metrics query invalid date range")
    return []
```

### 13.3 Logging Pattern
```python
logger.info(
    "Metrics query executed",
    extra={
        'extra_context': {
            'sensor_ids': filters.sensor_ids,
            'location_ids': filters.location_ids,
            'start_date': str(filters.start_date),
            'end_date': str(filters.end_date),
            'interval': filters.interval,
            'operation': 'metrics_query_success'
        }
    }
)
```

### 13.4 Testing Pattern
```python
def test_metrics_query(self, client, session, sample_reading_with_data):
    """Test metrics aggregation query."""
    query = """
    query MetricsQuery($filters: MetricsFilterInput!) {
        metrics(filters: $filters) {
            sensorId
            sensorName
            avgCo2Ppm
            avgHumidityPercentage
            avgTemperatureCelsius
            minCo2Ppm
            maxCo2Ppm
            readingCount
        }
    }
    """
    
    yesterday = datetime.utcnow() - timedelta(days=1)
    tomorrow = datetime.utcnow() + timedelta(days=1)
    
    variables = {
        "filters": {
            "startDate": yesterday.isoformat(),
            "endDate": tomorrow.isoformat()
        }
    }
    
    response = client.post('/graphql',
                         json={'query': query, 'variables': variables},
                         headers={'Content-Type': 'application/json'})
    
    assert response.status_code == 200
    data = response.get_json()
    assert 'data' in data
    assert 'metrics' in data['data']
```

---

## 14. Configuration & Environment

### Config File Location
`/home/copayne/dev/airq/airq-api/config.py`

### Key Environment Variables Required
```bash
# Database
DATABASE_URL=postgresql://postgres:1883@localhost/airq

# Security
SECRET_KEY=<generated-with-python-c-import-secrets-print(secrets.token_hex(32))>

# GraphQL Security
GRAPHQL_INTROSPECTION=false  # true in dev, false in prod
GRAPHQL_GRAPHIQL=false        # true in dev, false in prod
GRAPHQL_MAX_DEPTH=8
GRAPHQL_MAX_COMPLEXITY=150
GRAPHQL_RATE_LIMIT_PER_MINUTE=100

# Environment
FLASK_ENV=production          # or development
FLASK_DEBUG=false

# CORS
CORS_ORIGINS=http://localhost:3000
CORS_CREDENTIALS=false
```

---

## 15. Key Takeaways for Metrics Endpoint Implementation

1. **Use the filtering pattern**: Build on `SensorDataFilterInput` and `resolve_filtered_sensor_readings` logic
2. **Eager loading is critical**: Always use `joinedload` and `selectinload` to prevent N+1 queries
3. **Outer joins for optional data**: Use `outerjoin` when measurement data might be missing
4. **Composite indexes exist**: Leverage `idx_sensor_readings_sensor_time` for time-based queries
5. **GraphQL Object types wrap models**: Create new `SQLAlchemyObjectType` subclasses for metric responses
6. **Validation first**: Always validate date ranges and input parameters before querying
7. **Structured logging**: Include operation context in log extras for debugging
8. **Test with fixtures**: Use pytest fixtures for sample data in integration tests
9. **Transaction handling**: Use `db.session.add()`, `db.session.flush()`, and `db.session.commit()` patterns
10. **No aggregations currently exist**: The metrics endpoint will be the first aggregation feature

