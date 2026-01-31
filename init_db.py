from app import create_app, db
from app.models import CO2Reading, ErrorLog, HumidityReading, Location, Sensor, SensorLocation, SensorReading, TemperatureReading, ApplicationErrorLog, DashboardLayout
import logging

def init_db():
    app = create_app()
    with app.app_context():
        logger = logging.getLogger(__name__)
        try:
            # This will create all tables for us
            db.create_all()
            logger.info("Database tables created successfully")
        except Exception as e:
            logger.error(
                "Failed to create database tables",
                exc_info=True,
                extra={
                    'extra_context': {
                        'operation': 'database_initialization'
                    }
                }
            )
            raise

if __name__ == '__main__':
    init_db()