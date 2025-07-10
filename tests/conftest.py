"""
Test configuration and fixtures for the AirQ API.
"""

import pytest
from typing import Generator
from app import create_app, db
from app.models import Sensor, Location, SensorLocation, SensorReading, HumidityReading, TemperatureReading, CO2Reading
from config import TestingConfig
from datetime import datetime, timedelta
import factory
from factory.alchemy import SQLAlchemyModelFactory


@pytest.fixture(scope='session')
def app():
    """Create application for testing."""
    app = create_app(TestingConfig)
    
    # Ensure we're in testing mode
    app.config['TESTING'] = True
    
    # Create application context
    ctx = app.app_context()
    ctx.push()
    
    yield app
    
    ctx.pop()


@pytest.fixture(scope='session')
def _db(app):
    """Create database for testing."""
    db.create_all()
    yield db
    db.drop_all()


@pytest.fixture(scope='function')
def session(_db):
    """Create a database session for testing."""
    connection = _db.engine.connect()
    transaction = connection.begin()
    
    # Configure session to use connection
    _db.session.configure(bind=connection)
    
    yield _db.session
    
    transaction.rollback()
    connection.close()
    _db.session.remove()


@pytest.fixture
def client(app):
    """Create test client."""
    return app.test_client()


# Factory classes for test data
class LocationFactory(SQLAlchemyModelFactory):
    """Factory for creating Location instances."""
    class Meta:
        model = Location
        sqlalchemy_session_persistence = 'commit'
    
    name = factory.Sequence(lambda n: f"Test Location {n}")
    description = factory.Faker('text', max_nb_chars=100)


class SensorFactory(SQLAlchemyModelFactory):
    """Factory for creating Sensor instances."""
    class Meta:
        model = Sensor
        sqlalchemy_session_persistence = 'commit'
    
    name = factory.Sequence(lambda n: f"Test Sensor {n}")
    model = factory.Faker('word')
    installation_date = factory.Faker('date_time_this_year')
    is_active = True


class SensorLocationFactory(SQLAlchemyModelFactory):
    """Factory for creating SensorLocation instances."""
    class Meta:
        model = SensorLocation
        sqlalchemy_session_persistence = 'commit'
    
    sensor = factory.SubFactory(SensorFactory)
    location = factory.SubFactory(LocationFactory)
    start_time = factory.Faker('date_time_this_year')
    end_time = None
    is_current = True


class SensorReadingFactory(SQLAlchemyModelFactory):
    """Factory for creating SensorReading instances."""
    class Meta:
        model = SensorReading
        sqlalchemy_session_persistence = 'commit'
    
    sensor = factory.SubFactory(SensorFactory)
    reading_time = factory.Faker('date_time_this_year')
    is_success = True


class HumidityReadingFactory(SQLAlchemyModelFactory):
    """Factory for creating HumidityReading instances."""
    class Meta:
        model = HumidityReading
        sqlalchemy_session_persistence = 'commit'
    
    sensor_reading = factory.SubFactory(SensorReadingFactory)
    humidity_percentage = factory.Faker('pyfloat', min_value=0, max_value=100, right_digits=2)


class TemperatureReadingFactory(SQLAlchemyModelFactory):
    """Factory for creating TemperatureReading instances."""
    class Meta:
        model = TemperatureReading
        sqlalchemy_session_persistence = 'commit'
    
    sensor_reading = factory.SubFactory(SensorReadingFactory)
    temperature_celsius = factory.Faker('pyfloat', min_value=-40, max_value=60, right_digits=2)


class CO2ReadingFactory(SQLAlchemyModelFactory):
    """Factory for creating CO2Reading instances."""
    class Meta:
        model = CO2Reading
        sqlalchemy_session_persistence = 'commit'
    
    sensor_reading = factory.SubFactory(SensorReadingFactory)
    co2_ppm = factory.Faker('pyint', min_value=300, max_value=5000)


@pytest.fixture
def sample_location(session):
    """Create a sample location for testing."""
    LocationFactory._meta.sqlalchemy_session = session
    location = LocationFactory()
    session.commit()
    return location


@pytest.fixture
def sample_sensor(session):
    """Create a sample sensor for testing."""
    SensorFactory._meta.sqlalchemy_session = session
    sensor = SensorFactory()
    session.commit()
    return sensor


@pytest.fixture
def sample_sensor_location(session, sample_sensor, sample_location):
    """Create a sample sensor location for testing."""
    SensorLocationFactory._meta.sqlalchemy_session = session
    sensor_location = SensorLocationFactory(
        sensor=sample_sensor,
        location=sample_location
    )
    session.commit()
    return sensor_location


@pytest.fixture
def sample_reading_with_data(session, sample_sensor):
    """Create a complete sensor reading with all measurement types."""
    SensorReadingFactory._meta.sqlalchemy_session = session
    HumidityReadingFactory._meta.sqlalchemy_session = session
    TemperatureReadingFactory._meta.sqlalchemy_session = session
    CO2ReadingFactory._meta.sqlalchemy_session = session
    
    # Create the base reading
    reading = SensorReadingFactory(sensor=sample_sensor)
    session.flush()  # Get ID without committing
    
    # Create measurement readings
    humidity = HumidityReadingFactory(sensor_reading=reading)
    temperature = TemperatureReadingFactory(sensor_reading=reading)
    co2 = CO2ReadingFactory(sensor_reading=reading)
    
    session.commit()
    
    return {
        'reading': reading,
        'humidity': humidity,
        'temperature': temperature,
        'co2': co2
    }


@pytest.fixture
def graphql_query_executor(client):
    """Helper fixture for executing GraphQL queries."""
    def execute_query(query: str, variables: dict = None):
        """Execute a GraphQL query and return the response."""
        response = client.post(
            '/graphql',
            json={'query': query, 'variables': variables or {}},
            headers={'Content-Type': 'application/json'}
        )
        return response.get_json()
    
    return execute_query