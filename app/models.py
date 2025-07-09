from app import db
from datetime import datetime
from sqlalchemy.orm import relationship

class Sensor(db.Model):
    __tablename__ = 'sensors'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    model = db.Column(db.String(100), nullable=False)
    installation_date = db.Column(db.DateTime,
        nullable=False, unique=False, index=False,
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
    sensor_id = db.Column(db.Integer, db.ForeignKey('sensors.id'), nullable=False)
    location_id = db.Column(db.Integer, db.ForeignKey('locations.id'), nullable=False)
    start_time = db.Column(db.DateTime, nullable=False)
    end_time = db.Column(db.DateTime)
    is_current = db.Column(db.Boolean, default=True)
    
    # Relationships
    sensor = relationship("Sensor", back_populates="sensor_locations")
    location = relationship("Location", back_populates="sensor_locations")

class SensorReading(db.Model):
    __tablename__ = 'sensor_readings'
    id = db.Column(db.Integer, primary_key=True)
    sensor_id = db.Column(db.Integer, db.ForeignKey('sensors.id'), nullable=False)
    reading_time = db.Column(db.DateTime,
        nullable=False, unique=False, index=False,
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
    reading_id = db.Column(db.Integer, db.ForeignKey('sensor_readings.id'), nullable=False)
    humidity_percentage = db.Column(db.Float, nullable=False)
    
    # Relationships
    sensor_reading = relationship("SensorReading", back_populates="humidity_reading")

class TemperatureReading(db.Model):
    __tablename__ = 'temperature_readings'
    id = db.Column(db.Integer, primary_key=True)
    reading_id = db.Column(db.Integer, db.ForeignKey('sensor_readings.id'), nullable=False)
    temperature_celsius = db.Column(db.Float, nullable=False)
    
    # Relationships
    sensor_reading = relationship("SensorReading", back_populates="temperature_reading")

class CO2Reading(db.Model):
    __tablename__ = 'co2_readings'
    id = db.Column(db.Integer, primary_key=True)
    reading_id = db.Column(db.Integer, db.ForeignKey('sensor_readings.id'), nullable=False)
    co2_ppm = db.Column(db.Integer, nullable=False)
    
    # Relationships
    sensor_reading = relationship("SensorReading", back_populates="co2_reading")

class ErrorLog(db.Model):
    __tablename__ = 'error_logs'
    created_at = db.Column(db.DateTime,
        nullable=False, unique=False, index=False,
        default=datetime.utcnow
    )
    id = db.Column(db.Integer, primary_key=True)
    reading_id = db.Column(db.Integer, db.ForeignKey('sensor_readings.id'), nullable=False)
    request_data = db.Column(db.Text)
    response_data = db.Column(db.Text)
    error_message = db.Column(db.Text)
    
    # Relationships
    sensor_reading = relationship("SensorReading", back_populates="error_logs")

class ApplicationErrorLog(db.Model):
    __tablename__ = 'application_error_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, nullable=False, index=True, default=datetime.utcnow)
    level = db.Column(db.String(20), nullable=False, index=True)  # ERROR, WARNING, INFO, DEBUG
    message = db.Column(db.Text, nullable=False)
    context = db.Column(db.JSON)  # JSON field for structured context data
    request_id = db.Column(db.String(50), index=True)
    user_id = db.Column(db.Integer, index=True)  # For future authentication
    stack_trace = db.Column(db.Text)
    source_file = db.Column(db.String(255))
    source_function = db.Column(db.String(100))
    source_line = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, nullable=False, index=True, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<ApplicationErrorLog {self.level}: {self.message[:50]}...>'

# Database index for error log queries (timestamp + level)
db.Index('idx_application_error_logs_timestamp_level', ApplicationErrorLog.timestamp, ApplicationErrorLog.level)