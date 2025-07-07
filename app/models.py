from app import db
from datetime import datetime
from sqlalchemy.orm import relationship

class Sensor(db.Model):
    __tablename__ = 'sensors'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    model = db.Column(db.String(100), nullable=False)
    installation_date = db.Column(db.DateTime,
        nullable=False, unique=False, index=True,
        default=datetime.utcnow
    )
    is_active = db.Column(db.Boolean, default=True)
    
    # Relationships
    readings = relationship("SensorReading", back_populates="sensor", lazy="select")
    sensor_locations = relationship("SensorLocation", back_populates="sensor", lazy="select")
    

class Location(db.Model):
    __tablename__ = 'locations'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    
    # Relationships
    sensor_locations = relationship("SensorLocation", back_populates="location", lazy="select")

class SensorLocation(db.Model):
    __tablename__ = 'sensor_locations'
    id = db.Column(db.Integer, primary_key=True)
    sensor_id = db.Column(db.Integer, db.ForeignKey('sensors.id'), nullable=False, index=True)
    location_id = db.Column(db.Integer, db.ForeignKey('locations.id'), nullable=False, index=True)
    start_time = db.Column(db.DateTime, nullable=False, index=True)
    end_time = db.Column(db.DateTime, index=True)
    is_current = db.Column(db.Boolean, default=True)
    
    # Relationships
    sensor = relationship("Sensor", back_populates="sensor_locations")
    location = relationship("Location", back_populates="sensor_locations")

class SensorReading(db.Model):
    __tablename__ = 'sensor_readings'
    id = db.Column(db.Integer, primary_key=True)
    sensor_id = db.Column(db.Integer, db.ForeignKey('sensors.id'), nullable=False, index=True)
    reading_time = db.Column(db.DateTime,
        nullable=False, unique=False, index=True,
        default=datetime.utcnow
    )
    is_success = db.Column(db.Boolean, default=True)
    
    # Relationships
    sensor = relationship("Sensor", back_populates="readings")
    humidity_reading = relationship("HumidityReading", back_populates="sensor_reading", uselist=False)
    temperature_reading = relationship("TemperatureReading", back_populates="sensor_reading", uselist=False)
    co2_reading = relationship("CO2Reading", back_populates="sensor_reading", uselist=False)
    error_logs = relationship("ErrorLog", back_populates="sensor_reading")

class HumidityReading(db.Model):
    __tablename__ = 'humidity_readings'
    id = db.Column(db.Integer, primary_key=True)
    reading_id = db.Column(db.Integer, db.ForeignKey('sensor_readings.id'), nullable=False, index=True)
    humidity_percentage = db.Column(db.Float, nullable=False)
    
    # Relationships
    sensor_reading = relationship("SensorReading", back_populates="humidity_reading")

class TemperatureReading(db.Model):
    __tablename__ = 'temperature_readings'
    id = db.Column(db.Integer, primary_key=True)
    reading_id = db.Column(db.Integer, db.ForeignKey('sensor_readings.id'), nullable=False, index=True)
    temperature_celsius = db.Column(db.Float, nullable=False)
    
    # Relationships
    sensor_reading = relationship("SensorReading", back_populates="temperature_reading")

class CO2Reading(db.Model):
    __tablename__ = 'co2_readings'
    id = db.Column(db.Integer, primary_key=True)
    reading_id = db.Column(db.Integer, db.ForeignKey('sensor_readings.id'), nullable=False, index=True)
    co2_ppm = db.Column(db.Integer, nullable=False)
    
    # Relationships
    sensor_reading = relationship("SensorReading", back_populates="co2_reading")

class ErrorLog(db.Model):
    __tablename__ = 'error_logs'
    created_at = db.Column(db.DateTime,
        nullable=False, unique=False, index=True,
        default=datetime.utcnow
    )
    id = db.Column(db.Integer, primary_key=True)
    reading_id = db.Column(db.Integer, db.ForeignKey('sensor_readings.id'), nullable=False, index=True)
    request_data = db.Column(db.Text)
    response_data = db.Column(db.Text)
    error_message = db.Column(db.Text)
    
    # Relationships
    sensor_reading = relationship("SensorReading", back_populates="error_logs")

# Composite indexes for critical query performance
# These indexes optimize the most frequent query patterns identified in OPTIMIZE.md

# Index for time-series queries on sensor readings (sensor_id + reading_time)
db.Index('idx_sensor_readings_sensor_time', SensorReading.sensor_id, SensorReading.reading_time)

# Index for location resolution queries (sensor_id + time range)
db.Index('idx_sensor_locations_sensor_time_range', SensorLocation.sensor_id, SensorLocation.start_time, SensorLocation.end_time)

# Index for current location lookups (location_id + is_current)
db.Index('idx_sensor_locations_location_current', SensorLocation.location_id, SensorLocation.is_current)