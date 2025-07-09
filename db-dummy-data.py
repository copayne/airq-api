import random
from datetime import datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import SQLAlchemyError
from app import db
from app.models import CO2Reading, ErrorLog, HumidityReading, Location, Sensor, SensorLocation, SensorReading, TemperatureReading

# Replace with your actual database URI
DATABASE_URI = 'postgresql://postgres:1883@localhost/airq'

engine = create_engine(DATABASE_URI)
Session = sessionmaker(bind=engine)
session = Session()

def create_sensors(num_sensors=5):
    sensors = []
    for i in range(num_sensors):
        sensor = Sensor(
            name=f"Sensor {i+1}",
            model=f"Model-{random.choice(['A', 'B', 'C'])}{random.randint(100, 999)}",
            installation_date=datetime.now() - timedelta(days=random.randint(1, 365)),
            is_active=random.choice([True, False])
        )
        sensors.append(sensor)
    session.add_all(sensors)
    session.flush()  # This will assign IDs to the new objects
    return sensors

def create_locations(num_locations=3):
    locations = []
    for i in range(num_locations):
        location = Location(
            name=f"Room {i+1}",
            description=f"Description for Room {i+1}"
        )
        locations.append(location)
    session.add_all(locations)
    session.flush()  # This will assign IDs to the new objects
    return locations

def create_sensor_locations(sensors, locations):
    sensor_locations = []
    for sensor in sensors:
        for location in locations:
            start_time = datetime.now() - timedelta(days=random.randint(1, 30))
            end_time = start_time + timedelta(days=random.randint(1, 7)) if random.choice([True, False]) else None
            sensor_location = SensorLocation(
                sensor_id=sensor.id,
                location_id=location.id,
                start_time=start_time,
                end_time=end_time,
                is_current=random.choice([True, False])
            )
            sensor_locations.append(sensor_location)
    session.add_all(sensor_locations)
    session.flush()  # This will assign IDs to the new objects
    return sensor_locations

def create_sensor_readings(sensors, locations, num_readings_per_sensor=50):
    readings = []
    for sensor in sensors:
        for _ in range(num_readings_per_sensor):
            reading_time = datetime.now() - timedelta(minutes=random.randint(1, 10000))
            reading = SensorReading(
                sensor_id=sensor.id,
                location_id=random.choice(locations).id,
                reading_time=reading_time,
                is_success=random.choice([True, True, True, False])  # 75% success rate
            )
            readings.append(reading)
    session.add_all(readings)
    session.flush()  # This will assign IDs to the new objects
    return readings

def create_specific_readings(readings, ReadingClass, value_generator):
    specific_readings = []
    for reading in readings:
        if reading.is_success:
            try:
                specific_reading = ReadingClass(
                    reading_id=reading.id,
                    **value_generator()
                )
                specific_readings.append(specific_reading)
            except Exception as e:
                import logging
                logger = logging.getLogger(__name__)
                logger.error(
                    f"Error creating {ReadingClass.__name__} for reading_id {reading.id}",
                    exc_info=True,
                    extra={
                        'extra_context': {
                            'reading_class': ReadingClass.__name__,
                            'reading_id': reading.id,
                            'operation': 'create_specific_reading'
                        }
                    }
                )
    
    try:
        session.add_all(specific_readings)
        session.flush()
    except SQLAlchemyError as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(
            f"Error flushing {ReadingClass.__name__}s to database",
            exc_info=True,
            extra={
                'extra_context': {
                    'reading_class': ReadingClass.__name__,
                    'count': len(specific_readings),
                    'operation': 'flush_readings'
                }
            }
        )
        session.rollback()
    return specific_readings

def create_humidity_readings(readings):
    return create_specific_readings(
        readings, 
        HumidityReading, 
        lambda: {"humidity_percentage": random.uniform(30.0, 70.0)}
    )

def create_temperature_readings(readings):
    return create_specific_readings(
        readings, 
        TemperatureReading, 
        lambda: {"temperature_celsius": random.uniform(18.0, 30.0)}
    )

def create_co2_readings(readings):
    return create_specific_readings(
        readings, 
        CO2Reading, 
        lambda: {"co2_ppm": random.randint(400, 2000)}
    )

def create_error_logs(readings):
    error_logs = []
    for reading in readings:
        if not reading.is_success:
            error_log = ErrorLog(
                reading_id=reading.id,
                request_data="Sample request data",
                response_data="Sample error response",
                error_message=random.choice(["Sensor offline", "Reading out of range", "Communication error"])
            )
            error_logs.append(error_log)
    session.add_all(error_logs)

def main():
    try:
        # Clear existing data
        for table in [ErrorLog, CO2Reading, TemperatureReading, HumidityReading, SensorReading, SensorLocation, Sensor, Location]:
            session.query(table).delete()
        
        import logging
        logger = logging.getLogger(__name__)
        
        logger.info("Starting database seeding process")
        logger.info("Creating sensors...")
        sensors = create_sensors()
        logger.info("Creating locations...")
        locations = create_locations()
        logger.info("Creating sensor locations...")
        create_sensor_locations(sensors, locations)
        logger.info("Creating sensor readings...")
        readings = create_sensor_readings(sensors, locations)
        logger.info("Creating humidity readings...")
        create_humidity_readings(readings)
        logger.info("Creating temperature readings...")
        create_temperature_readings(readings)
        logger.info("Creating CO2 readings...")
        create_co2_readings(readings)
        logger.info("Creating error logs...")
        create_error_logs(readings)
        
        session.commit()
        logger.info("Database seeded successfully!")
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(
            "An error occurred while seeding the database",
            exc_info=True,
            extra={
                'extra_context': {
                    'operation': 'database_seeding',
                    'step': 'main_seeding_process'
                }
            }
        )
        session.rollback()
    finally:
        session.close()

if __name__ == "__main__":
    main()