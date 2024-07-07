from app import create_app, db
from app.models import CO2Reading, ErrorLog, HumidityReading, Location, Sensor, SensorLocation, SensorReading, TemperatureReading

def init_db():
    app = create_app()
    with app.app_context():
        # This will create all tables for us
        db.create_all()
        print("Database tables created.")

if __name__ == '__main__':
    init_db()