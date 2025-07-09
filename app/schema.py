import graphene
from graphene_sqlalchemy import SQLAlchemyObjectType
from app.models import CO2Reading, ErrorLog, HumidityReading, Location, Sensor, SensorLocation, SensorReading as SensorReadingModel, TemperatureReading
from app import db
from sqlalchemy import and_, or_, desc, asc
from sqlalchemy.orm import joinedload, selectinload
from datetime import datetime

class LocationObject(SQLAlchemyObjectType):
    class Meta:
        model = Location

    readings = graphene.List(lambda: SensorReadingObject)
    current_sensors = graphene.List(lambda: SensorObject)

    def resolve_readings(self, info):
        # Get all readings from sensors at this location via relationships
        readings = []
        for sensor_location in self.sensor_locations:
            for reading in sensor_location.sensor.readings:
                # Check if reading was taken when sensor was at this location
                if (sensor_location.start_time <= reading.reading_time and 
                    (sensor_location.end_time is None or sensor_location.end_time >= reading.reading_time)):
                    readings.append(reading)
        return readings

    def resolve_current_sensors(self, info):
        return [sl.sensor for sl in self.sensor_locations if sl.is_current]

class SensorLocationObject(SQLAlchemyObjectType):
    class Meta:
        model = SensorLocation

    sensor = graphene.Field(lambda: SensorObject)
    location = graphene.Field(lambda: LocationObject)

    def resolve_sensor(self, info):
        return self.sensor

    def resolve_location(self, info):
        return self.location

class SensorReadingObject(SQLAlchemyObjectType):
    class Meta:
        model = SensorReadingModel
    
    sensor = graphene.Field(lambda: SensorObject)
    humidity_reading = graphene.Field(lambda: HumidityReadingObject)
    temperature_reading = graphene.Field(lambda: TemperatureReadingObject)
    co2_reading = graphene.Field(lambda: CO2ReadingObject)
    location = graphene.Field(lambda: LocationObject)

    def resolve_sensor(self, info):
        return self.sensor

    def resolve_humidity_reading(self, info):
        return self.humidity_reading

    def resolve_temperature_reading(self, info):
        return self.temperature_reading

    def resolve_co2_reading(self, info):
        return self.co2_reading
    
    def resolve_location(self, info):
        # Optimized database query instead of Python loop
        sensor_location = SensorLocation.query.filter(
            SensorLocation.sensor_id == self.sensor_id,
            SensorLocation.start_time <= self.reading_time,
            or_(
                SensorLocation.end_time.is_(None),
                SensorLocation.end_time >= self.reading_time
            )
        ).options(joinedload(SensorLocation.location)).first()
        
        return sensor_location.location if sensor_location else None
    
class SensorObject(SQLAlchemyObjectType):
    class Meta:
        model = Sensor

    readings = graphene.List(lambda: SensorReadingObject)
    current_location = graphene.Field(lambda: LocationObject)
    last_reading = graphene.Field(SensorReadingObject)

    def resolve_readings(self, info):
        # Optimized lazy loading - only fetch when specifically requested
        return SensorReadingModel.query.filter_by(sensor_id=self.id).options(
            joinedload(SensorReadingModel.humidity_reading),
            joinedload(SensorReadingModel.temperature_reading),
            joinedload(SensorReadingModel.co2_reading)
        ).order_by(desc(SensorReadingModel.reading_time)).all()

    def resolve_current_location(self, info):
        for sensor_location in self.sensor_locations:
            if sensor_location.is_current:
                return sensor_location.location
        return None
    
    def resolve_last_reading(self, info):
        # Optimized query - get only the latest reading without loading all readings
        return SensorReadingModel.query.filter_by(sensor_id=self.id).options(
            joinedload(SensorReadingModel.humidity_reading),
            joinedload(SensorReadingModel.temperature_reading),
            joinedload(SensorReadingModel.co2_reading)
        ).order_by(desc(SensorReadingModel.reading_time)).first()

    
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
    # New fields for pagination and ordering
    limit = graphene.Int(description="Maximum number of records to return")
    offset = graphene.Int(description="Number of records to skip")
    order_by = graphene.String(description="Field to order by")
    order_direction = graphene.String(description="Direction of ordering (asc or desc)")

    
class CreateSensorReadingInput(graphene.InputObjectType):
    sensor_id = graphene.Int(required=True)
    humidity_percentage = graphene.Float()
    temperature_celsius = graphene.Float()
    co2_ppm = graphene.Int()

class CreateSensorReading(graphene.Mutation):
    class Arguments:
        input = CreateSensorReadingInput(required=True)

    sensor_reading = graphene.Field(lambda: SensorReadingObject)

    @staticmethod
    def mutate(root, info, input):
        # Create the sensor reading with just the sensor_id
        sensor_reading = SensorReadingModel(
            sensor_id=input.sensor_id
        )
        
        db.session.add(sensor_reading)
        db.session.flush()  # This assigns an ID without committing
        
        # Create the specific readings as before
        if input.humidity_percentage is not None:
            humidity_reading = HumidityReading(reading_id=sensor_reading.id, humidity_percentage=input.humidity_percentage)
            db.session.add(humidity_reading)

        if input.temperature_celsius is not None:
            temperature_reading = TemperatureReading(reading_id=sensor_reading.id, temperature_celsius=input.temperature_celsius)
            db.session.add(temperature_reading)

        if input.co2_ppm is not None:
            co2_reading = CO2Reading(reading_id=sensor_reading.id, co2_ppm=input.co2_ppm)
            db.session.add(co2_reading)
        
        try:
            db.session.commit()
            return CreateSensorReading(sensor_reading=sensor_reading)
        except Exception as e:
            db.session.rollback()
            # TODO: Replace with proper logging
            raise Exception(f"Failed to save sensor reading: {str(e)}")

class HumidityReadingObject(SQLAlchemyObjectType):
    class Meta:
        model = HumidityReading

    sensor_reading = graphene.Field(lambda: SensorReadingObject)

    def resolve_sensor_reading(self, info):
        return self.sensor_reading

class TemperatureReadingObject(SQLAlchemyObjectType):
    class Meta:
        model = TemperatureReading

    sensor_reading = graphene.Field(lambda: SensorReadingObject)

    def resolve_sensor_reading(self, info):
        return self.sensor_reading

class CO2ReadingObject(SQLAlchemyObjectType):
    class Meta:
        model = CO2Reading

    sensor_reading = graphene.Field(lambda: SensorReadingObject)

    def resolve_sensor_reading(self, info):
        return self.sensor_reading

class ErrorLogObject(SQLAlchemyObjectType):
    class Meta:
        model = ErrorLog

    sensor_reading = graphene.Field(lambda: SensorReadingObject)

    def resolve_sensor_reading(self, info):
        return self.sensor_reading
    
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
        # Light query - only load basic sensor info and current locations
        # Individual resolvers will handle readings data when actually requested
        return Sensor.query.options(
            selectinload(Sensor.sensor_locations).selectinload(SensorLocation.location)
        ).all()

    def resolve_locations(self, info):
        return Location.query.options(
            selectinload(Location.sensor_locations).selectinload(SensorLocation.sensor)
        ).all()

    def resolve_sensor_locations(self, info):
        return SensorLocation.query.options(
            joinedload(SensorLocation.sensor),
            joinedload(SensorLocation.location)
        ).all()

    def resolve_sensor_readings(self, info):
        return SensorReadingModel.query.options(
            joinedload(SensorReadingModel.sensor).selectinload(Sensor.sensor_locations).selectinload(SensorLocation.location),
            joinedload(SensorReadingModel.humidity_reading),
            joinedload(SensorReadingModel.temperature_reading),
            joinedload(SensorReadingModel.co2_reading)
        ).order_by(desc(SensorReadingModel.reading_time)).limit(1000).all()

    def resolve_humidity_readings(self, info):
        return HumidityReading.query.limit(1000).all()

    def resolve_temperature_readings(self, info):
        return TemperatureReading.query.limit(1000).all()

    def resolve_co2_readings(self, info):
        return CO2Reading.query.limit(1000).all()

    def resolve_error_logs(self, info):
        return ErrorLog.query.order_by(desc(ErrorLog.created_at)).limit(1000).all()

    def resolve_sensor(self, info, id):
        return Sensor.query.options(
            selectinload(Sensor.readings).selectinload(SensorReadingModel.humidity_reading),
            selectinload(Sensor.readings).selectinload(SensorReadingModel.temperature_reading),
            selectinload(Sensor.readings).selectinload(SensorReadingModel.co2_reading),
            selectinload(Sensor.sensor_locations).selectinload(SensorLocation.location)
        ).get(id)

    def resolve_location(self, info, id):
        return Location.query.options(
            selectinload(Location.sensor_locations).selectinload(SensorLocation.sensor)
        ).get(id)
    
    filtered_sensor_readings = graphene.List(SensorReadingObject, filters=SensorDataFilterInput(required=True))

    def resolve_filtered_sensor_readings(self, info, filters):
        # Start with optimized eager loading
        query = SensorReadingModel.query.options(
            joinedload(SensorReadingModel.sensor).selectinload(Sensor.sensor_locations).selectinload(SensorLocation.location),
            joinedload(SensorReadingModel.humidity_reading),
            joinedload(SensorReadingModel.temperature_reading),
            joinedload(SensorReadingModel.co2_reading)
        )

        if filters.start_date:
            query = query.filter(SensorReadingModel.reading_time >= filters.start_date)
        if filters.end_date:
            query = query.filter(SensorReadingModel.reading_time <= filters.end_date)
        # Optimized joins - combine measurement filters into single query with outer joins
        measurement_filters = []
        
        # CO2 filtering
        if filters.min_co2_ppm or filters.max_co2_ppm:
            query = query.outerjoin(CO2Reading)
            if filters.min_co2_ppm:
                measurement_filters.append(CO2Reading.co2_ppm >= filters.min_co2_ppm)
            if filters.max_co2_ppm:
                measurement_filters.append(CO2Reading.co2_ppm <= filters.max_co2_ppm)
        
        # Temperature filtering
        if filters.min_temperature_celsius or filters.max_temperature_celsius:
            query = query.outerjoin(TemperatureReading)
            if filters.min_temperature_celsius:
                measurement_filters.append(TemperatureReading.temperature_celsius >= filters.min_temperature_celsius)
            if filters.max_temperature_celsius:
                measurement_filters.append(TemperatureReading.temperature_celsius <= filters.max_temperature_celsius)
        
        # Humidity filtering
        if filters.min_humidity_percentage or filters.max_humidity_percentage:
            query = query.outerjoin(HumidityReading)
            if filters.min_humidity_percentage:
                measurement_filters.append(HumidityReading.humidity_percentage >= filters.min_humidity_percentage)
            if filters.max_humidity_percentage:
                measurement_filters.append(HumidityReading.humidity_percentage <= filters.max_humidity_percentage)
        
        # Apply all measurement filters together
        if measurement_filters:
            query = query.filter(and_(*measurement_filters))
        if filters.sensor_ids:
            query = query.filter(SensorReadingModel.sensor_id.in_(filters.sensor_ids))
        if filters.location_ids:
            # Fix: Filter by location through sensor_locations relationship
            query = query.join(Sensor).join(SensorLocation).filter(
                SensorLocation.location_id.in_(filters.location_ids),
                SensorLocation.start_time <= SensorReadingModel.reading_time,
                or_(SensorLocation.end_time.is_(None), SensorLocation.end_time >= SensorReadingModel.reading_time)
            )

        # Default ordering is by reading_time descending
        order_column = SensorReadingModel.reading_time
        order_direction = desc
        
        # Optimized ordering - reuse joins if already present, otherwise add outer joins
        if hasattr(filters, 'order_by') and filters.order_by:
            if filters.order_by == 'co2_ppm':
                # Only join if not already joined for filtering
                if not (filters.min_co2_ppm or filters.max_co2_ppm):
                    query = query.outerjoin(CO2Reading)
                order_column = CO2Reading.co2_ppm
            elif filters.order_by == 'temperature_celsius':
                # Only join if not already joined for filtering
                if not (filters.min_temperature_celsius or filters.max_temperature_celsius):
                    query = query.outerjoin(TemperatureReading)
                order_column = TemperatureReading.temperature_celsius
            elif filters.order_by == 'humidity_percentage':
                # Only join if not already joined for filtering
                if not (filters.min_humidity_percentage or filters.max_humidity_percentage):
                    query = query.outerjoin(HumidityReading)
                order_column = HumidityReading.humidity_percentage
            elif filters.order_by in ['reading_time', 'id']:
                order_column = getattr(SensorReadingModel, filters.order_by)
        
        # Set sort direction
        if hasattr(filters, 'order_direction') and filters.order_direction and filters.order_direction.lower() == 'asc':
            order_direction = asc
        
        query = query.order_by(order_direction(order_column))
        
        # Apply pagination - default to limit of 100 if not specified
        limit = 100
        if hasattr(filters, 'limit') and filters.limit is not None:
            limit = filters.limit
        
        offset = 0
        if hasattr(filters, 'offset') and filters.offset is not None:
            offset = filters.offset
        
        query = query.limit(limit).offset(offset)

        return query.all()

from app.graphql_security import SecureGraphQLSchema

schema = SecureGraphQLSchema(
    query=Query, 
    mutation=Mutation, 
    types=[CreateSensorReadingInput],
    max_depth=8,  # Appropriate for our schema depth
    max_complexity=150,  # Allows filtered queries but prevents abuse
    timeout_seconds=30,  # Reasonable timeout for database operations
    enable_security_logging=True
)
