"""
Unit tests for GraphQL resolvers.
"""

import pytest
from datetime import datetime, timedelta
from app.schema import LocationObject, SensorObject, SensorReadingObject


@pytest.mark.unit
class TestLocationResolvers:
    """Test Location GraphQL resolvers."""
    
    def test_resolve_current_sensors(self, session, sample_sensor_location):
        """Test resolving current sensors for a location."""
        location = sample_sensor_location.location
        location_obj = LocationObject(location)
        
        current_sensors = location_obj.resolve_current_sensors(None)
        
        assert len(current_sensors) == 1
        assert current_sensors[0].id == sample_sensor_location.sensor.id
        assert current_sensors[0].name == sample_sensor_location.sensor.name
    
    def test_resolve_readings(self, session, sample_reading_with_data, sample_sensor_location):
        """Test resolving readings for a location."""
        # Set up: make sure the reading is associated with the sensor location
        reading = sample_reading_with_data['reading']
        reading.sensor = sample_sensor_location.sensor
        reading.reading_time = sample_sensor_location.start_time + timedelta(hours=1)
        session.commit()
        
        location = sample_sensor_location.location
        location_obj = LocationObject(location)
        
        readings = location_obj.resolve_readings(None)
        
        assert len(readings) >= 1
        assert any(r.id == reading.id for r in readings)


@pytest.mark.unit
class TestSensorResolvers:
    """Test Sensor GraphQL resolvers."""
    
    def test_resolve_current_location(self, session, sample_sensor_location):
        """Test resolving current location for a sensor."""
        sensor = sample_sensor_location.sensor
        sensor_obj = SensorObject(sensor)
        
        current_location = sensor_obj.resolve_current_location(None)
        
        assert current_location is not None
        assert current_location.id == sample_sensor_location.location.id
        assert current_location.name == sample_sensor_location.location.name
    
    def test_resolve_last_reading(self, session, sample_reading_with_data):
        """Test resolving last reading for a sensor."""
        reading = sample_reading_with_data['reading']
        sensor = reading.sensor
        sensor_obj = SensorObject(sensor)
        
        last_reading = sensor_obj.resolve_last_reading(None)
        
        assert last_reading is not None
        assert last_reading.id == reading.id
        assert last_reading.sensor_id == sensor.id
    
    def test_resolve_readings(self, session, sample_reading_with_data):
        """Test resolving all readings for a sensor."""
        reading = sample_reading_with_data['reading']
        sensor = reading.sensor
        sensor_obj = SensorObject(sensor)
        
        readings = sensor_obj.resolve_readings(None)
        
        assert len(readings) >= 1
        assert any(r.id == reading.id for r in readings)
        assert all(r.sensor_id == sensor.id for r in readings)


@pytest.mark.unit
class TestSensorReadingResolvers:
    """Test SensorReading GraphQL resolvers."""
    
    def test_resolve_sensor(self, session, sample_reading_with_data):
        """Test resolving sensor for a reading."""
        reading = sample_reading_with_data['reading']
        reading_obj = SensorReadingObject(reading)
        
        sensor = reading_obj.resolve_sensor(None)
        
        assert sensor is not None
        assert sensor.id == reading.sensor_id
        assert sensor.name == reading.sensor.name
    
    def test_resolve_humidity_reading(self, session, sample_reading_with_data):
        """Test resolving humidity reading."""
        reading = sample_reading_with_data['reading']
        reading_obj = SensorReadingObject(reading)
        
        humidity = reading_obj.resolve_humidity_reading(None)
        
        assert humidity is not None
        assert humidity.reading_id == reading.id
        assert 0 <= humidity.humidity_percentage <= 100
    
    def test_resolve_temperature_reading(self, session, sample_reading_with_data):
        """Test resolving temperature reading."""
        reading = sample_reading_with_data['reading']
        reading_obj = SensorReadingObject(reading)
        
        temperature = reading_obj.resolve_temperature_reading(None)
        
        assert temperature is not None
        assert temperature.reading_id == reading.id
        assert -40 <= temperature.temperature_celsius <= 60
    
    def test_resolve_co2_reading(self, session, sample_reading_with_data):
        """Test resolving CO2 reading."""
        reading = sample_reading_with_data['reading']
        reading_obj = SensorReadingObject(reading)
        
        co2 = reading_obj.resolve_co2_reading(None)
        
        assert co2 is not None
        assert co2.reading_id == reading.id
        assert 300 <= co2.co2_ppm <= 5000
    
    def test_resolve_location(self, session, sample_reading_with_data, sample_sensor_location):
        """Test resolving location for a reading."""
        reading = sample_reading_with_data['reading']
        reading.sensor = sample_sensor_location.sensor
        reading.reading_time = sample_sensor_location.start_time + timedelta(hours=1)
        session.commit()
        
        reading_obj = SensorReadingObject(reading)
        
        location = reading_obj.resolve_location(None)
        
        assert location is not None
        assert location.id == sample_sensor_location.location.id
        assert location.name == sample_sensor_location.location.name