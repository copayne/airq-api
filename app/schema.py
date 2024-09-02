import graphene
from graphene_sqlalchemy import SQLAlchemyObjectType
from app.models import CO2Reading, ErrorLog, HumidityReading, Location, Sensor, SensorLocation, SensorReading as SensorReadingModel, TemperatureReading
from app import db
from sqlalchemy import and_, desc
from datetime import datetime

class LocationObject(SQLAlchemyObjectType):
    class Meta:
        model = Location

    readings = graphene.List(lambda: SensorReadingObject)
    current_sensors = graphene.List(lambda: SensorObject)

    def resolve_readings(self, info):
        return SensorReadingModel.query.filter(SensorReadingModel.location_id == self.id).all()

    def resolve_current_sensors(self, info):
        current_sensor_locations = SensorLocation.query.filter(SensorLocation.location_id == self.id, SensorLocation.is_current == True).all()
        sensor_ids = [sl.sensor_id for sl in current_sensor_locations]
        return Sensor.query.filter(Sensor.id.in_(sensor_ids)).all()

class SensorLocationObject(SQLAlchemyObjectType):
    class Meta:
        model = SensorLocation

    sensor = graphene.Field(lambda: SensorObject)
    location = graphene.Field(lambda: LocationObject)

    def resolve_sensor(self, info):
        return Sensor.query.get(self.sensor_id)

    def resolve_location(self, info):
        return Location.query.get(self.location_id)

class SensorReadingObject(SQLAlchemyObjectType):
    class Meta:
        model = SensorReadingModel
    
    sensor = graphene.Field(lambda: SensorObject)
    location = graphene.Field(lambda: LocationObject)
    humidity_reading = graphene.Field(lambda: HumidityReadingObject)
    temperature_reading = graphene.Field(lambda: TemperatureReadingObject)
    co2_reading = graphene.Field(lambda: CO2ReadingObject)

    def resolve_sensor(self, info):
        return Sensor.query.get(self.sensor_id)

    def resolve_location(self, info):
        return Location.query.get(self.location_id)

    def resolve_humidity_reading(self, info):
        return HumidityReading.query.filter(HumidityReading.reading_id == self.id).first()

    def resolve_temperature_reading(self, info):
        return TemperatureReading.query.filter(TemperatureReading.reading_id == self.id).first()

    def resolve_co2_reading(self, info):
        return CO2Reading.query.filter(CO2Reading.reading_id == self.id).first()
    
class SensorObject(SQLAlchemyObjectType):
    class Meta:
        model = Sensor

    readings = graphene.List(lambda: SensorReadingObject)
    current_location = graphene.Field(lambda: LocationObject)
    last_reading = graphene.Field(SensorReadingObject)

    def resolve_readings(self, info):
        return SensorReadingModel.query.filter(SensorReadingModel.sensor_id == self.id).all()

    def resolve_current_location(self, info):
        current_sensor_location = SensorLocation.query.filter(SensorLocation.sensor_id == self.id, SensorLocation.is_current == True).first()
        if current_sensor_location:
            return Location.query.get(current_sensor_location.location_id)
        return None
    
    def resolve_last_reading(self, info):
        return SensorReadingModel.query.filter(SensorReadingModel.sensor_id == self.id).order_by(desc(SensorReadingModel.reading_time)).first()

    
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
    
class CreateSensorReadingInput(graphene.InputObjectType):
    sensor_id = graphene.Int(required=True)
    location_id = graphene.Int(required=True)
    humidity_percentage = graphene.Float()
    temperature_celsius = graphene.Float()
    co2_ppm = graphene.Int()

class CreateSensorReading(graphene.Mutation):
    class Arguments:
        input = CreateSensorReadingInput(required=True)

    sensor_reading = graphene.Field(lambda: SensorReadingObject)

    @staticmethod
    def mutate(root, info, input):
        sensor_reading = SensorReadingModel(
            sensor_id=input.sensor_id,
            location_id=input.location_id,
        )
        db.session.add(sensor_reading)
        db.session.flush()  # This assigns an ID to sensor_reading

        if input.humidity_percentage is not None:
            humidity_reading = HumidityReading(reading_id=sensor_reading.id, humidity_percentage=input.humidity_percentage)
            db.session.add(humidity_reading)

        if input.temperature_celsius is not None:
            temperature_reading = TemperatureReading(reading_id=sensor_reading.id, temperature_celsius=input.temperature_celsius)
            db.session.add(temperature_reading)

        if input.co2_ppm is not None:
            co2_reading = CO2Reading(reading_id=sensor_reading.id, co2_ppm=input.co2_ppm)
            db.session.add(co2_reading)

        db.session.commit()
        return CreateSensorReading(sensor_reading=sensor_reading)

class HumidityReadingObject(SQLAlchemyObjectType):
    class Meta:
        model = HumidityReading

    sensor_reading = graphene.Field(lambda: SensorReadingObject)

    def resolve_sensor_reading(self, info):
        return SensorReadingModel.query.get(self.reading_id)

class TemperatureReadingObject(SQLAlchemyObjectType):
    class Meta:
        model = TemperatureReading

    sensor_reading = graphene.Field(lambda: SensorReadingObject)

    def resolve_sensor_reading(self, info):
        return SensorReadingModel.query.get(self.reading_id)

class CO2ReadingObject(SQLAlchemyObjectType):
    class Meta:
        model = CO2Reading

    sensor_reading = graphene.Field(lambda: SensorReadingObject)

    def resolve_sensor_reading(self, info):
        return SensorReadingModel.query.get(self.reading_id)

class ErrorLogObject(SQLAlchemyObjectType):
    class Meta:
        model = ErrorLog

    sensor_reading = graphene.Field(lambda: SensorReadingObject)

    def resolve_sensor_reading(self, info):
        return SensorReadingModel.query.get(self.reading_id)
    
class Mutation(graphene.ObjectType):
    create_sensor_reading = CreateSensorReading.Field()

class Query(graphene.ObjectType):
    sensors = graphene.List(SensorObject)
    locations = graphene.List(LocationObject)
    sensor_locations = graphene.List(SensorLocationObject)
    sensor_readings = graphene.List(SensorReadingObject)
    humidity_readings = graphene.List(HumidityReadingObject)
    temperature_readings = graphene.List(TemperatureReadingObject)
    co2_readings = graphene.List(CO2ReadingObject)
    error_logs = graphene.List(ErrorLogObject)

    sensor = graphene.Field(SensorObject, id=graphene.Int(required=True))
    location = graphene.Field(LocationObject, id=graphene.Int(required=True))

    def resolve_sensors(self, info):
        return Sensor.query.all()

    def resolve_locations(self, info):
        return Location.query.all()

    def resolve_sensor_locations(self, info):
        return SensorLocation.query.all()

    def resolve_sensor_readings(self, info):
        return SensorReadingModel.query.all()

    def resolve_humidity_readings(self, info):
        return HumidityReading.query.all()

    def resolve_temperature_readings(self, info):
        return TemperatureReading.query.all()

    def resolve_co2_readings(self, info):
        return CO2Reading.query.all()

    def resolve_error_logs(self, info):
        return ErrorLog.query.all()

    def resolve_sensor(self, info, id):
        return Sensor.query.get(id)

    def resolve_location(self, info, id):
        return Location.query.get(id)
    
    filtered_sensor_readings = graphene.List(SensorReadingObject, filters=SensorDataFilterInput(required=True))

    def resolve_filtered_sensor_readings(self, info, filters):
        query = SensorReadingModel.query

        if filters.start_date:
            query = query.filter(SensorReadingModel.reading_time >= filters.start_date)
        if filters.end_date:
            query = query.filter(SensorReadingModel.reading_time <= filters.end_date)
        if filters.min_co2_ppm or filters.max_co2_ppm:
            query = query.join(CO2Reading)
            if filters.min_co2_ppm:
                query = query.filter(CO2Reading.co2_ppm >= filters.min_co2_ppm)
            if filters.max_co2_ppm:
                query = query.filter(CO2Reading.co2_ppm <= filters.max_co2_ppm)
        if filters.min_temperature_celsius or filters.max_temperature_celsius:
            query = query.join(TemperatureReading)
            if filters.min_temperature_celsius:
                query = query.filter(TemperatureReading.temperature_celsius >= filters.min_temperature_celsius)
            if filters.max_temperature_celsius:
                query = query.filter(TemperatureReading.temperature_celsius <= filters.max_temperature_celsius)
        if filters.min_humidity_percentage or filters.max_humidity_percentage:
            query = query.join(HumidityReading)
            if filters.min_humidity_percentage:
                query = query.filter(HumidityReading.humidity_percentage >= filters.min_humidity_percentage)
            if filters.max_humidity_percentage:
                query = query.filter(HumidityReading.humidity_percentage <= filters.max_humidity_percentage)
        if filters.sensor_ids:
            query = query.filter(SensorReadingModel.sensor_id.in_(filters.sensor_ids))
        if filters.location_ids:
            query = query.filter(SensorReadingModel.location_id.in_(filters.location_ids))

        return query.all()

schema = graphene.Schema(query=Query, mutation=Mutation, types=[CreateSensorReadingInput])
