"""
Unit tests for database models.
"""

import pytest
from datetime import datetime, timedelta
from app.models import Sensor, Location, SensorLocation, SensorReading, HumidityReading, TemperatureReading, CO2Reading


@pytest.mark.unit
class TestSensorModel:
    """Test the Sensor model."""
    
    def test_sensor_creation(self, session):
        """Test creating a sensor."""
        sensor = Sensor(
            name="Test Sensor",
            model="TestModel-1",
            installation_date=datetime.utcnow(),
            is_active=True
        )
        session.add(sensor)
        session.commit()
        
        assert sensor.id is not None
        assert sensor.name == "Test Sensor"
        assert sensor.model == "TestModel-1"
        assert sensor.is_active is True
    
    def test_sensor_repr(self, session):
        """Test sensor string representation."""
        sensor = Sensor(name="Test Sensor", model="TestModel-1")
        session.add(sensor)
        session.commit()
        
        # Test that repr doesn't raise an error
        repr_str = str(sensor)
        assert isinstance(repr_str, str)


@pytest.mark.unit
class TestLocationModel:
    """Test the Location model."""
    
    def test_location_creation(self, session):
        """Test creating a location."""
        location = Location(
            name="Test Location",
            description="A test location for unit testing"
        )
        session.add(location)
        session.commit()
        
        assert location.id is not None
        assert location.name == "Test Location"
        assert location.description == "A test location for unit testing"


@pytest.mark.unit
class TestSensorLocationModel:
    """Test the SensorLocation model."""
    
    def test_sensor_location_creation(self, session, sample_sensor, sample_location):
        """Test creating a sensor location relationship."""
        sensor_location = SensorLocation(
            sensor_id=sample_sensor.id,
            location_id=sample_location.id,
            start_time=datetime.utcnow(),
            is_current=True
        )
        session.add(sensor_location)
        session.commit()
        
        assert sensor_location.id is not None
        assert sensor_location.sensor_id == sample_sensor.id
        assert sensor_location.location_id == sample_location.id
        assert sensor_location.is_current is True
        assert sensor_location.end_time is None
    
    def test_sensor_location_relationships(self, session, sample_sensor_location):
        """Test sensor location relationships."""
        assert sample_sensor_location.sensor is not None
        assert sample_sensor_location.location is not None
        assert sample_sensor_location.sensor.name is not None
        assert sample_sensor_location.location.name is not None


@pytest.mark.unit
class TestSensorReadingModel:
    """Test the SensorReading model."""
    
    def test_sensor_reading_creation(self, session, sample_sensor):
        """Test creating a sensor reading."""
        reading = SensorReading(
            sensor_id=sample_sensor.id,
            reading_time=datetime.utcnow(),
            is_success=True
        )
        session.add(reading)
        session.commit()
        
        assert reading.id is not None
        assert reading.sensor_id == sample_sensor.id
        assert reading.is_success is True
    
    def test_sensor_reading_with_measurements(self, session, sample_reading_with_data):
        """Test sensor reading with all measurement types."""
        data = sample_reading_with_data
        reading = data['reading']
        
        assert reading.humidity_reading is not None
        assert reading.temperature_reading is not None
        assert reading.co2_reading is not None
        
        assert reading.humidity_reading.humidity_percentage >= 0
        assert reading.humidity_reading.humidity_percentage <= 100
        assert reading.temperature_reading.temperature_celsius >= -40
        assert reading.temperature_reading.temperature_celsius <= 60
        assert reading.co2_reading.co2_ppm >= 300
        assert reading.co2_reading.co2_ppm <= 5000


@pytest.mark.unit
class TestMeasurementModels:
    """Test measurement model classes."""
    
    def test_humidity_reading(self, session, sample_sensor):
        """Test humidity reading creation."""
        reading = SensorReading(sensor_id=sample_sensor.id)
        session.add(reading)
        session.flush()
        
        humidity = HumidityReading(
            reading_id=reading.id,
            humidity_percentage=65.5
        )
        session.add(humidity)
        session.commit()
        
        assert humidity.id is not None
        assert humidity.reading_id == reading.id
        assert humidity.humidity_percentage == 65.5
    
    def test_temperature_reading(self, session, sample_sensor):
        """Test temperature reading creation."""
        reading = SensorReading(sensor_id=sample_sensor.id)
        session.add(reading)
        session.flush()
        
        temperature = TemperatureReading(
            reading_id=reading.id,
            temperature_celsius=23.4
        )
        session.add(temperature)
        session.commit()
        
        assert temperature.id is not None
        assert temperature.reading_id == reading.id
        assert temperature.temperature_celsius == 23.4
    
    def test_co2_reading(self, session, sample_sensor):
        """Test CO2 reading creation."""
        reading = SensorReading(sensor_id=sample_sensor.id)
        session.add(reading)
        session.flush()
        
        co2 = CO2Reading(
            reading_id=reading.id,
            co2_ppm=1200
        )
        session.add(co2)
        session.commit()
        
        assert co2.id is not None
        assert co2.reading_id == reading.id
        assert co2.co2_ppm == 1200