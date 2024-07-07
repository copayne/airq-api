from app import db
from datetime import datetime

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
    

class Location(db.Model):
    __tablename__ = 'locations'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)

class SensorLocation(db.Model):
    __tablename__ = 'sensor_locations'
    id = db.Column(db.Integer, primary_key=True)
    sensor_id = db.Column(db.Integer, db.ForeignKey('sensors.id'), nullable=False)
    location_id = db.Column(db.Integer, db.ForeignKey('locations.id'), nullable=False)
    start_time = db.Column(db.DateTime, nullable=False)
    end_time = db.Column(db.DateTime)
    is_current = db.Column(db.Boolean, default=True)

class SensorReading(db.Model):
    __tablename__ = 'sensor_readings'
    id = db.Column(db.Integer, primary_key=True)
    sensor_id = db.Column(db.Integer, db.ForeignKey('sensors.id'), nullable=False)
    location_id = db.Column(db.Integer, db.ForeignKey('locations.id'), nullable=False)
    reading_time = db.Column(db.DateTime,
        nullable=False, unique=False, index=False,
        default=datetime.utcnow
    )
    is_success = db.Column(db.Boolean, default=True)

class HumidityReading(db.Model):
    __tablename__ = 'humidity_readings'
    id = db.Column(db.Integer, primary_key=True)
    reading_id = db.Column(db.Integer, db.ForeignKey('sensor_readings.id'), nullable=False)
    humidity_percentage = db.Column(db.Float, nullable=False)

class TemperatureReading(db.Model):
    __tablename__ = 'temperature_readings'
    id = db.Column(db.Integer, primary_key=True)
    reading_id = db.Column(db.Integer, db.ForeignKey('sensor_readings.id'), nullable=False)
    temperature_celsius = db.Column(db.Float, nullable=False)

class CO2Reading(db.Model):
    __tablename__ = 'co2_readings'
    id = db.Column(db.Integer, primary_key=True)
    reading_id = db.Column(db.Integer, db.ForeignKey('sensor_readings.id'), nullable=False)
    co2_ppm = db.Column(db.Integer, nullable=False)

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