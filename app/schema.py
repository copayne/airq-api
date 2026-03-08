import graphene
from graphene_sqlalchemy import SQLAlchemyObjectType
from typing import Optional, List, Any, Dict
from app.models import CO2Reading, HumidityReading, Location, Sensor, SensorLocation, SensorReading as SensorReadingModel, TemperatureReading, User, RingDevice, DashboardLayout, SensorHealthReport, AlertThreshold, AlertHistory
import requests
from app import db
from sqlalchemy import and_, or_, desc, asc
from sqlalchemy.orm import joinedload, selectinload
from datetime import datetime, timedelta
import logging
from app.auth import require_admin, require_user, get_user_from_context
from app.cache import cached_query

logger = logging.getLogger(__name__)

class LocationObject(SQLAlchemyObjectType):
    class Meta:
        model = Location

    readings = graphene.List(lambda: SensorReadingObject)
    current_sensors = graphene.List(lambda: SensorObject)

    def resolve_readings(self, info: Any) -> List[SensorReadingModel]:
        """Get all sensor readings taken at this location.
        
        Filters readings by checking if they were taken when sensors were active at this location.
        """
        # Get all readings from sensors at this location via relationships
        readings = []
        for sensor_location in self.sensor_locations:
            for reading in sensor_location.sensor.readings:
                # Check if reading was taken when sensor was at this location
                if (sensor_location.start_time <= reading.reading_time and 
                    (sensor_location.end_time is None or sensor_location.end_time >= reading.reading_time)):
                    readings.append(reading)
        return readings

    def resolve_current_sensors(self, info: Any) -> List[Sensor]:
        """Get all sensors currently active at this location."""
        return [sl.sensor for sl in self.sensor_locations if sl.is_current]

class SensorLocationObject(SQLAlchemyObjectType):
    class Meta:
        model = SensorLocation

    sensor = graphene.Field(lambda: SensorObject)
    location = graphene.Field(lambda: LocationObject)

    def resolve_sensor(self, info: Any) -> Sensor:
        """Get the sensor associated with this location assignment."""
        return self.sensor

    def resolve_location(self, info: Any) -> Location:
        """Get the location associated with this sensor assignment."""
        return self.location

class SensorReadingObject(SQLAlchemyObjectType):
    class Meta:
        model = SensorReadingModel
    
    sensor = graphene.Field(lambda: SensorObject)
    humidity_reading = graphene.Field(lambda: HumidityReadingObject)
    temperature_reading = graphene.Field(lambda: TemperatureReadingObject)
    co2_reading = graphene.Field(lambda: CO2ReadingObject)
    location = graphene.Field(lambda: LocationObject)

    def resolve_sensor(self, info: Any) -> Sensor:
        return self.sensor

    def resolve_humidity_reading(self, info: Any) -> Optional[HumidityReading]:
        return self.humidity_reading

    def resolve_temperature_reading(self, info: Any) -> Optional[TemperatureReading]:
        return self.temperature_reading

    def resolve_co2_reading(self, info: Any) -> Optional[CO2Reading]:
        return self.co2_reading
    
    def resolve_location(self, info: Any) -> Optional[Location]:
        """Get the location where this sensor reading was taken.

        Uses pre-loaded sensor_locations data to avoid N+1 queries.
        The sensor_locations are eagerly loaded in the main query.
        """
        # Use pre-loaded sensor_locations from the sensor relationship
        # This avoids N+1 queries since the data is already loaded
        if hasattr(self, 'sensor') and self.sensor and hasattr(self.sensor, 'sensor_locations'):
            for sensor_location in self.sensor.sensor_locations:
                if (sensor_location.start_time <= self.reading_time and
                    (sensor_location.end_time is None or sensor_location.end_time >= self.reading_time)):
                    return sensor_location.location

        # Fallback to database query only if sensor_locations not pre-loaded
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

    def resolve_readings(self, info: Any) -> List[SensorReadingModel]:
        """Get all readings from this sensor with optimized loading.
        
        Uses eager loading for measurement data to prevent N+1 queries.
        """
        # Optimized lazy loading - only fetch when specifically requested
        return SensorReadingModel.query.filter_by(sensor_id=self.id).options(
            joinedload(SensorReadingModel.humidity_reading),
            joinedload(SensorReadingModel.temperature_reading),
            joinedload(SensorReadingModel.co2_reading)
        ).order_by(desc(SensorReadingModel.reading_time)).all()

    def resolve_current_location(self, info: Any) -> Optional[Location]:
        """Get the current location of this sensor."""
        for sensor_location in self.sensor_locations:
            if sensor_location.is_current:
                return sensor_location.location
        return None
    
    def resolve_last_reading(self, info: Any) -> Optional[SensorReadingModel]:
        """Get the most recent reading from this sensor.
        
        Uses optimized query to fetch only the latest reading with measurements.
        """
        # Optimized query - get only the latest reading without loading all readings
        return SensorReadingModel.query.filter_by(sensor_id=self.id).options(
            joinedload(SensorReadingModel.humidity_reading),
            joinedload(SensorReadingModel.temperature_reading),
            joinedload(SensorReadingModel.co2_reading)
        ).order_by(desc(SensorReadingModel.reading_time)).first()


class SensorHealthReportObject(SQLAlchemyObjectType):
    """GraphQL type for detailed sensor health reports."""
    class Meta:
        model = SensorHealthReport


class SensorHealthObject(graphene.ObjectType):
    """GraphQL type for sensor health summary."""
    sensor_id = graphene.Int(required=True)
    sensor_name = graphene.String()
    health_status = graphene.String(required=True)  # healthy, degraded, offline, unknown, inactive
    is_active = graphene.Boolean()

    # Timing info
    last_reading_time = graphene.DateTime()
    last_successful_reading_time = graphene.DateTime()
    minutes_since_last_reading = graphene.Int()

    # Failure tracking
    consecutive_failures = graphene.Int()
    total_readings = graphene.Int()
    total_failures = graphene.Int()
    success_rate = graphene.Float()

    # Network info
    ip_address = graphene.String()
    health_check_port = graphene.Int()
    is_reachable = graphene.Boolean()

    # Latest reading values (for quick diagnostics)
    latest_co2_ppm = graphene.Int()
    latest_temperature_celsius = graphene.Float()
    latest_humidity_percentage = graphene.Float()

    # Last health check
    last_health_check = graphene.DateTime()
    last_health_report = graphene.Field(SensorHealthReportObject)


class PingSensorResult(graphene.ObjectType):
    """Result of pinging a sensor for health status."""
    success = graphene.Boolean(required=True)
    message = graphene.String()
    sensor_id = graphene.Int()

    # Service status
    service_running = graphene.Boolean()
    service_uptime_seconds = graphene.Int()

    # Sensor hardware status
    sensor_connected = graphene.Boolean()
    sensor_data_ready = graphene.Boolean()
    sensor_serial_number = graphene.String()

    # Last reading values
    last_co2_ppm = graphene.Int()
    last_temperature_celsius = graphene.Float()
    last_humidity_percentage = graphene.Float()
    last_reading_time = graphene.DateTime()

    # System metrics
    system_uptime_seconds = graphene.Int()
    disk_usage_percent = graphene.Float()
    memory_usage_percent = graphene.Float()
    cpu_temperature_celsius = graphene.Float()

    # API connectivity
    api_reachable = graphene.Boolean()
    api_response_time_ms = graphene.Int()

    # Error info
    error_message = graphene.String()
    consecutive_failures = graphene.Int()

    # Response time for this ping
    ping_response_time_ms = graphene.Int()


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
    reading_time = graphene.DateTime(description="Original reading timestamp. Defaults to now if omitted.")

class CreateSensorReading(graphene.Mutation):
    class Arguments:
        input = CreateSensorReadingInput(required=True)

    sensor_reading = graphene.Field(lambda: SensorReadingObject)
    success = graphene.Boolean()
    message = graphene.String()
    errors = graphene.List(graphene.String)

    @staticmethod
    def mutate(root: Any, info: Any, input: CreateSensorReadingInput) -> 'CreateSensorReading':
        """Create a new sensor reading with comprehensive validation.
        
        Validates input data against reasonable sensor ranges and constraints
        before creating database records. Returns detailed error information
        for validation failures.
        """
        from app.validation import SensorDataValidator
        
        # Validate input data
        validator = SensorDataValidator()
        validation_result = validator.validate_sensor_reading_input(
            sensor_id=input.sensor_id,
            humidity_percentage=input.humidity_percentage,
            temperature_celsius=input.temperature_celsius,
            co2_ppm=input.co2_ppm
        )
        
        # Return validation errors if any
        if not validation_result.is_valid:
            logger.warning(
                "Sensor reading validation failed",
                extra={
                    'extra_context': {
                        'sensor_id': input.sensor_id,
                        'validation_errors': validation_result.error_messages,
                        'operation': 'create_sensor_reading_validation'
                    }
                }
            )
            return CreateSensorReading(
                sensor_reading=None,
                success=False,
                message="Validation failed",
                errors=validation_result.error_messages
            )
        
        try:
            # Create the sensor reading with validated data
            reading_kwargs = {'sensor_id': input.sensor_id}
            if input.reading_time is not None:
                reading_kwargs['reading_time'] = input.reading_time
            sensor_reading = SensorReadingModel(**reading_kwargs)
            
            db.session.add(sensor_reading)
            db.session.flush()  # This assigns an ID without committing
            
            # Fetch sensor for offset correction and health tracking
            sensor = Sensor.query.get(input.sensor_id)

            # Create the specific readings with validated data
            if input.humidity_percentage is not None:
                humidity_reading = HumidityReading(
                    reading_id=sensor_reading.id,
                    humidity_percentage=input.humidity_percentage
                )
                db.session.add(humidity_reading)

            if input.temperature_celsius is not None:
                corrected_temp = input.temperature_celsius + (sensor.temperature_offset or 0.0)
                temperature_reading = TemperatureReading(
                    reading_id=sensor_reading.id,
                    temperature_celsius=corrected_temp
                )
                db.session.add(temperature_reading)

            if input.co2_ppm is not None:
                co2_reading = CO2Reading(
                    reading_id=sensor_reading.id, 
                    co2_ppm=input.co2_ppm
                )
                db.session.add(co2_reading)
            
            # Update sensor health tracking
            if sensor:
                sensor.update_health_on_reading(success=True)
                db.session.add(sensor)

            db.session.commit()

            # Publish real-time WebSocket event (failures never break ingestion)
            try:
                from app.events import publish_sensor_reading
                publish_sensor_reading({
                    'reading_id': sensor_reading.id,
                    'sensor_id': input.sensor_id,
                    'humidity_percentage': input.humidity_percentage,
                    'temperature_celsius': input.temperature_celsius,
                    'co2_ppm': input.co2_ppm,
                    'timestamp': str(sensor_reading.reading_time),
                })
            except Exception:
                logger.error(
                    "WebSocket publish failed after sensor reading commit",
                    exc_info=True,
                    extra={'extra_context': {
                        'sensor_id': input.sensor_id,
                        'reading_id': sensor_reading.id,
                        'operation': 'ws_publish_reading_error',
                    }}
                )

            # Check CO2 thresholds and send alerts (failures never break ingestion)
            if input.co2_ppm is not None:
                try:
                    from app.alert_service import check_and_send_alerts
                    check_and_send_alerts(input.sensor_id, sensor_reading.id, input.co2_ppm)
                except Exception:
                    logger.error(
                        "Alert check failed after sensor reading commit",
                        exc_info=True,
                        extra={'extra_context': {
                            'sensor_id': input.sensor_id,
                            'reading_id': sensor_reading.id,
                            'operation': 'alert_check_post_commit_error',
                        }}
                    )

            logger.info(
                "Sensor reading created successfully",
                extra={
                    'extra_context': {
                        'sensor_id': input.sensor_id,
                        'reading_id': sensor_reading.id,
                        'has_humidity': input.humidity_percentage is not None,
                        'has_temperature': input.temperature_celsius is not None,
                        'has_co2': input.co2_ppm is not None,
                        'operation': 'create_sensor_reading_success'
                    }
                }
            )

            return CreateSensorReading(
                sensor_reading=sensor_reading,
                success=True,
                message="Sensor reading created successfully",
                errors=[]
            )
            
        except Exception as e:
            db.session.rollback()
            logger.error(
                "Failed to save sensor reading",
                exc_info=True,
                extra={
                    'extra_context': {
                        'sensor_id': input.sensor_id,
                        'has_humidity': input.humidity_percentage is not None,
                        'has_temperature': input.temperature_celsius is not None,
                        'has_co2': input.co2_ppm is not None,
                        'operation': 'create_sensor_reading_database_error'
                    }
                }
            )
            
            return CreateSensorReading(
                sensor_reading=None,
                success=False,
                message="Failed to save sensor reading. Please try again.",
                errors=["Database operation failed"]
            )

class HumidityReadingObject(SQLAlchemyObjectType):
    class Meta:
        model = HumidityReading

    sensor_reading = graphene.Field(lambda: SensorReadingObject)

    def resolve_sensor_reading(self, info: Any) -> SensorReadingModel:
        return self.sensor_reading

class TemperatureReadingObject(SQLAlchemyObjectType):
    class Meta:
        model = TemperatureReading

    sensor_reading = graphene.Field(lambda: SensorReadingObject)

    def resolve_sensor_reading(self, info: Any) -> SensorReadingModel:
        return self.sensor_reading

class CO2ReadingObject(SQLAlchemyObjectType):
    class Meta:
        model = CO2Reading

    sensor_reading = graphene.Field(lambda: SensorReadingObject)

    def resolve_sensor_reading(self, info: Any) -> SensorReadingModel:
        return self.sensor_reading


class MetricsObject(graphene.ObjectType):
    """Metrics object for dashboard statistics."""
    co2_1day_avg = graphene.Float()
    co2_30day_avg = graphene.Float()
    temp_1day_avg = graphene.Float()
    temp_30day_avg = graphene.Float()
    temp_highest_all_time = graphene.Float()
    temp_lowest_all_time = graphene.Float()
    co2_highest_all_time = graphene.Int()
    co2_lowest_all_time = graphene.Int()


class AirQualityDistribution(graphene.ObjectType):
    """Air quality condition distribution across sensor readings."""
    good = graphene.Int(description="Number of readings with good air quality conditions")
    moderate = graphene.Int(description="Number of readings with moderate air quality conditions")
    poor = graphene.Int(description="Number of readings with poor air quality conditions")
    total = graphene.Int(description="Total number of readings analyzed")


class AirQualityDistributionsByPeriod(graphene.ObjectType):
    """Air quality distributions across multiple time periods."""
    one_day = graphene.Field(AirQualityDistribution, description="Distribution for last 24 hours")
    thirty_days = graphene.Field(AirQualityDistribution, description="Distribution for last 30 days")
    all_time = graphene.Field(AirQualityDistribution, description="Distribution for all historical data")


class DailyAirQualityScore(graphene.ObjectType):
    """Air quality score for a single day."""
    date = graphene.String(required=True, description="Date in YYYY-MM-DD format")
    score = graphene.Float(description="Air quality score (0-100, 100 = best). Null if no data.")
    reading_count = graphene.Int(required=True, description="Number of readings for this day")


class UserObject(SQLAlchemyObjectType):
    """GraphQL object for User model."""
    class Meta:
        model = User
        exclude_fields = (
            'password_hash', 
            'email_verification_token', 
            'password_reset_token',
            'failed_login_attempts',
            'account_locked_until'
        )  # Never expose sensitive security fields
    
    full_name = graphene.String()
    
    def resolve_full_name(self, info: Any) -> Optional[str]:
        """Get user's full name."""
        if self.first_name and self.last_name:
            return f"{self.first_name} {self.last_name}"
        return self.first_name or self.last_name


class AuthPayload(graphene.ObjectType):
    """Authentication response payload."""
    user = graphene.Field(UserObject)
    token = graphene.String()
    success = graphene.Boolean()
    message = graphene.String()


class RegisterInput(graphene.InputObjectType):
    """Input for user registration."""
    username = graphene.String(required=True)
    email = graphene.String(required=True)
    password = graphene.String(required=True)
    first_name = graphene.String()
    last_name = graphene.String()


class LoginInput(graphene.InputObjectType):
    """Input for user login."""
    username_or_email = graphene.String(required=True)
    password = graphene.String(required=True)


class RegisterUser(graphene.Mutation):
    """User registration mutation."""
    class Arguments:
        input = RegisterInput(required=True)

    Output = AuthPayload

    @staticmethod
    def mutate(root: Any, info: Any, input: RegisterInput) -> AuthPayload:
        """Register a new user account with comprehensive validation.
        
        Validates input data and creates a new user with hashed password
        and authentication token.
        """
        from app.validation import UserInputValidator
        
        try:
            # Validate input data
            validator = UserInputValidator()
            validation_result = validator.validate_registration_input(
                username=input.username,
                email=input.email,
                password=input.password,
                first_name=input.first_name,
                last_name=input.last_name
            )
            
            # Return validation errors if any
            if not validation_result.is_valid:
                logger.warning(
                    "User registration validation failed",
                    extra={
                        'extra_context': {
                            'username': input.username,
                            'email': input.email,
                            'validation_errors': validation_result.error_messages,
                            'operation': 'register_user_validation'
                        }
                    }
                )
                # Return first validation error message for user-friendly response
                return AuthPayload(
                    success=False,
                    message=validation_result.errors[0].message
                )
            
            # Check if username already exists
            if User.query.filter_by(username=input.username).first():
                return AuthPayload(
                    success=False,
                    message="Username already exists"
                )
            
            # Check if email already exists
            if User.query.filter_by(email=input.email).first():
                return AuthPayload(
                    success=False,
                    message="Email already registered"
                )
            
            # Create new user with validated data (email verification required)
            user = User(
                username=input.username.strip(),
                email=input.email.strip().lower(),
                first_name=input.first_name.strip() if input.first_name else None,
                last_name=input.last_name.strip() if input.last_name else None,
                role='user',  # Default role for new registrations
                email_verified=False  # Require email verification
            )
            user.set_password(input.password)
            
            # Generate email verification token
            verification_token = user.generate_email_verification_token()
            
            db.session.add(user)
            db.session.commit()
            
            # Send verification email
            from app.email_service import email_service
            email_sent = email_service.send_email_verification(
                user.email, user.username, verification_token
            )
            
            # Generate JWT token for initial login (but require email verification for full access)
            token = user.generate_jwt_token()
            user.update_last_login()
            
            logger.info(
                "New user registered successfully",
                extra={
                    'extra_context': {
                        'username': user.username,
                        'email': user.email,
                        'email_sent': email_sent,
                        'operation': 'register_user_success'
                    }
                }
            )
            
            message = "Registration successful! Please check your email to verify your account."
            if not email_sent:
                message = "Registration successful! Note: Verification email could not be sent. Please contact support."
            
            return AuthPayload(
                user=user,
                token=token,
                success=True,
                message=message
            )
            
        except Exception as e:
            db.session.rollback()
            error_message = "Registration failed. Please try again."
            
            # Provide more specific error messages for common issues
            error_str = str(e).lower()
            if 'duplicate key' in error_str or 'unique constraint' in error_str:
                if 'username' in error_str:
                    error_message = "Username already exists. Please choose a different username."
                elif 'email' in error_str:
                    error_message = "Email already registered. Please use a different email or try logging in."
                else:
                    error_message = "An account with this information already exists."
            elif 'connection' in error_str or 'database' in error_str:
                error_message = "Database connection error. Please try again later."
            elif 'column' in error_str and 'does not exist' in error_str:
                error_message = "Database schema error. Please contact support."
            
            logger.error(
                "User registration failed",
                exc_info=True,
                extra={
                    'extra_context': {
                        'username': input.username,
                        'email': input.email,
                        'error_type': type(e).__name__,
                        'error_message': str(e),
                        'operation': 'register_user_database_error'
                    }
                }
            )
            return AuthPayload(
                success=False,
                message=error_message
            )


class LoginUser(graphene.Mutation):
    """User login mutation."""
    class Arguments:
        input = LoginInput(required=True)

    Output = AuthPayload

    @staticmethod
    def mutate(root: Any, info: Any, input: LoginInput) -> AuthPayload:
        """Authenticate user and return JWT token.
        
        Accepts either username or email for login.
        """
        try:
            # Find user by username or email
            user = User.query.filter(
                or_(
                    User.username == input.username_or_email,
                    User.email == input.username_or_email
                )
            ).first()
            
            if not user:
                # Log failed login attempt for security monitoring
                logger.warning(
                    f"Login attempt with non-existent user: {input.username_or_email}",
                    extra={'extra_context': {'operation': 'login_nonexistent_user'}}
                )
                return AuthPayload(
                    success=False,
                    message="Invalid credentials"
                )
            
            # Check if account is locked
            if user.is_account_locked():
                logger.warning(
                    f"Login attempt on locked account: {user.username}",
                    extra={'extra_context': {'user_id': user.id, 'operation': 'login_locked_account'}}
                )
                return AuthPayload(
                    success=False,
                    message="Account is temporarily locked due to multiple failed login attempts. Please try again later or reset your password."
                )
            
            if not user.is_active:
                return AuthPayload(
                    success=False,
                    message="Account is deactivated. Please contact support."
                )
            
            # Check password
            if not user.check_password(input.password):
                # Record failed login attempt
                user.record_failed_login()
                db.session.commit()
                
                logger.warning(
                    f"Failed login attempt for user: {user.username}",
                    extra={
                        'extra_context': {
                            'user_id': user.id,
                            'failed_attempts': user.failed_login_attempts,
                            'operation': 'login_failed_password'
                        }
                    }
                )
                
                return AuthPayload(
                    success=False,
                    message="Invalid credentials"
                )
            
            # Successful login - reset security counters and generate token
            user.record_successful_login()
            token = user.generate_jwt_token()
            db.session.commit()
            
            logger.info(
                f"User logged in successfully: {user.username}",
                extra={
                    'extra_context': {
                        'user_id': user.id,
                        'email_verified': user.email_verified,
                        'operation': 'login_success'
                    }
                }
            )
            
            # Include email verification status in response
            message = "Login successful"
            if not user.email_verified:
                message = "Login successful. Please verify your email address for full account access."
            
            return AuthPayload(
                user=user,
                token=token,
                success=True,
                message=message
            )
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Login failed: {str(e)}")
            return AuthPayload(
                success=False,
                message="Login failed. Please try again."
            )


class EmailVerificationInput(graphene.InputObjectType):
    """Input for email verification."""
    token = graphene.String(required=True)


class PasswordResetRequestInput(graphene.InputObjectType):
    """Input for password reset request."""
    email = graphene.String(required=True)


class PasswordResetInput(graphene.InputObjectType):
    """Input for password reset."""
    token = graphene.String(required=True)
    new_password = graphene.String(required=True)


class LogoutInput(graphene.InputObjectType):
    """Input for logout."""
    token = graphene.String(required=True)


class VerifyEmail(graphene.Mutation):
    """Email verification mutation."""
    class Arguments:
        input = EmailVerificationInput(required=True)

    success = graphene.Boolean()
    message = graphene.String()

    @staticmethod
    def mutate(root: Any, info: Any, input: EmailVerificationInput) -> 'VerifyEmail':
        """Verify user email with token."""
        try:
            # Find user with verification token
            user = User.query.filter_by(email_verification_token=input.token).first()
            
            if not user:
                return VerifyEmail(
                    success=False,
                    message="Invalid or expired verification token"
                )
            
            # Verify email with token
            if user.verify_email_with_token(input.token):
                db.session.commit()
                
                logger.info(
                    f"Email verified successfully for user: {user.username}",
                    extra={
                        'extra_context': {
                            'user_id': user.id,
                            'email': user.email,
                            'operation': 'email_verification_success'
                        }
                    }
                )
                
                return VerifyEmail(
                    success=True,
                    message="Email verified successfully"
                )
            else:
                return VerifyEmail(
                    success=False,
                    message="Invalid or expired verification token"
                )
                
        except Exception as e:
            db.session.rollback()
            logger.error(f"Email verification failed: {str(e)}")
            return VerifyEmail(
                success=False,
                message="Email verification failed. Please try again."
            )


class RequestPasswordReset(graphene.Mutation):
    """Password reset request mutation."""
    class Arguments:
        input = PasswordResetRequestInput(required=True)

    success = graphene.Boolean()
    message = graphene.String()

    @staticmethod
    def mutate(root: Any, info: Any, input: PasswordResetRequestInput) -> 'RequestPasswordReset':
        """Send password reset email."""
        try:
            # Find user by email
            user = User.query.filter_by(email=input.email.strip().lower()).first()
            
            # Always return success to prevent email enumeration
            # But only send email if user exists
            if user and user.is_active:
                # Generate password reset token
                reset_token = user.generate_password_reset_token()
                db.session.commit()
                
                # Send password reset email
                from app.email_service import email_service
                email_sent = email_service.send_password_reset(
                    user.email, user.username, reset_token
                )
                
                logger.info(
                    f"Password reset requested for user: {user.username}",
                    extra={
                        'extra_context': {
                            'user_id': user.id,
                            'email': user.email,
                            'email_sent': email_sent,
                            'operation': 'password_reset_request'
                        }
                    }
                )
            else:
                # Log potential security issue
                logger.warning(
                    f"Password reset requested for non-existent/inactive email: {input.email}",
                    extra={'extra_context': {'operation': 'password_reset_invalid_email'}}
                )
            
            # Always return success message to prevent email enumeration
            return RequestPasswordReset(
                success=True,
                message="If an account with that email exists, a password reset link has been sent."
            )
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Password reset request failed: {str(e)}")
            return RequestPasswordReset(
                success=False,
                message="Password reset request failed. Please try again."
            )


class ResetPassword(graphene.Mutation):
    """Password reset mutation."""
    class Arguments:
        input = PasswordResetInput(required=True)

    success = graphene.Boolean()
    message = graphene.String()

    @staticmethod
    def mutate(root: Any, info: Any, input: PasswordResetInput) -> 'ResetPassword':
        """Reset password with token."""
        from app.validation import UserInputValidator
        
        try:
            # Validate new password
            validator = UserInputValidator()
            validation_result = validator.validate_password(input.new_password)
            if not validation_result.is_valid:
                return ResetPassword(
                    success=False,
                    message="Password must be at least 8 characters long"
                )
            
            # Find user with reset token
            user = User.query.filter_by(password_reset_token=input.token).first()
            
            if not user:
                return ResetPassword(
                    success=False,
                    message="Invalid or expired reset token"
                )
            
            # Reset password with token
            if user.reset_password_with_token(input.token, input.new_password):
                db.session.commit()
                
                logger.info(
                    f"Password reset successfully for user: {user.username}",
                    extra={
                        'extra_context': {
                            'user_id': user.id,
                            'operation': 'password_reset_success'
                        }
                    }
                )
                
                return ResetPassword(
                    success=True,
                    message="Password reset successfully"
                )
            else:
                return ResetPassword(
                    success=False,
                    message="Invalid or expired reset token"
                )
                
        except Exception as e:
            db.session.rollback()
            logger.error(f"Password reset failed: {str(e)}")
            return ResetPassword(
                success=False,
                message="Password reset failed. Please try again."
            )


class UpdateProfileInput(graphene.InputObjectType):
    """Input for updating user profile."""
    first_name = graphene.String()
    last_name = graphene.String()
    email = graphene.String()


class UpdateProfile(graphene.Mutation):
    """Update authenticated user's profile."""
    class Arguments:
        input = UpdateProfileInput(required=True)

    Output = AuthPayload

    @staticmethod
    @require_user
    def mutate(root: Any, info: Any, input: UpdateProfileInput) -> AuthPayload:
        """Update the current user's profile fields."""
        try:
            user = get_user_from_context(info.context)
            if not user:
                return AuthPayload(success=False, message="Authentication required")

            if input.email is not None:
                email = input.email.strip().lower()
                if not email:
                    return AuthPayload(success=False, message="Email cannot be empty")
                existing = User.query.filter(User.email == email, User.id != user.id).first()
                if existing:
                    return AuthPayload(success=False, message="Email already registered")
                if user.email != email:
                    user.email = email
                    user.email_verified = False

            if input.first_name is not None:
                name = input.first_name.strip()
                if len(name) > 100:
                    return AuthPayload(success=False, message="First name must be no more than 100 characters")
                user.first_name = name or None

            if input.last_name is not None:
                name = input.last_name.strip()
                if len(name) > 100:
                    return AuthPayload(success=False, message="Last name must be no more than 100 characters")
                user.last_name = name or None

            db.session.commit()

            logger.info(
                f"Profile updated for user: {user.username}",
                extra={'extra_context': {'user_id': user.id, 'operation': 'update_profile'}}
            )

            return AuthPayload(success=True, message="Profile updated successfully", user=user)

        except Exception as e:
            db.session.rollback()
            logger.error(f"Profile update failed: {str(e)}")
            return AuthPayload(success=False, message="Profile update failed. Please try again.")


class ChangePasswordInput(graphene.InputObjectType):
    """Input for changing password."""
    current_password = graphene.String(required=True)
    new_password = graphene.String(required=True)


class ChangePassword(graphene.Mutation):
    """Change authenticated user's password."""
    class Arguments:
        input = ChangePasswordInput(required=True)

    success = graphene.Boolean()
    message = graphene.String()

    @staticmethod
    @require_user
    def mutate(root: Any, info: Any, input: ChangePasswordInput) -> 'ChangePassword':
        """Change the current user's password."""
        from app.validation import UserInputValidator

        try:
            user = get_user_from_context(info.context)
            if not user:
                return ChangePassword(success=False, message="Authentication required")

            if not user.check_password(input.current_password):
                return ChangePassword(success=False, message="Current password is incorrect")

            validator = UserInputValidator()
            validation_result = validator.validate_password(input.new_password)
            if not validation_result.is_valid:
                return ChangePassword(success=False, message=validation_result.error_messages[0])

            user.set_password(input.new_password)
            db.session.commit()

            logger.info(
                f"Password changed for user: {user.username}",
                extra={'extra_context': {'user_id': user.id, 'operation': 'change_password'}}
            )

            return ChangePassword(success=True, message="Password changed successfully")

        except Exception as e:
            db.session.rollback()
            logger.error(f"Password change failed: {str(e)}")
            return ChangePassword(success=False, message="Password change failed. Please try again.")


class LogoutUser(graphene.Mutation):
    """User logout mutation."""
    class Arguments:
        input = LogoutInput(required=True)

    success = graphene.Boolean()
    message = graphene.String()

    @staticmethod
    def mutate(root: Any, info: Any, input: LogoutInput) -> 'LogoutUser':
        """Logout user by blacklisting token."""
        try:
            # Get current user from token
            user = User.verify_jwt_token(input.token)

            if not user:
                return LogoutUser(
                    success=False,
                    message="Invalid token"
                )

            # Blacklist the token
            if user.blacklist_token(input.token):
                logger.info(
                    f"User logged out: {user.username}",
                    extra={
                        'extra_context': {
                            'user_id': user.id,
                            'operation': 'logout_success'
                        }
                    }
                )

                return LogoutUser(
                    success=True,
                    message="Logout successful"
                )
            else:
                return LogoutUser(
                    success=False,
                    message="Logout failed"
                )

        except Exception as e:
            db.session.rollback()
            logger.error(f"Logout failed: {str(e)}")
            return LogoutUser(
                success=False,
                message="Logout failed. Please try again."
            )


class RingDeviceObject(SQLAlchemyObjectType):
    """GraphQL object for Ring alarm devices (contact sensors, motion detectors, etc.)."""
    class Meta:
        model = RingDevice


class RingDeviceInput(graphene.InputObjectType):
    """Input for updating/creating a Ring device (static info only)."""
    device_id = graphene.String(required=True)
    device_type = graphene.String(required=True)
    name = graphene.String(required=True)
    location = graphene.String()


class BatchUpdateRingDevices(graphene.Mutation):
    """Batch update Ring devices from frontend Ring API data."""
    class Arguments:
        devices = graphene.List(RingDeviceInput, required=True)

    success = graphene.Boolean()
    message = graphene.String()
    devices_updated = graphene.Int()
    devices_created = graphene.Int()

    @staticmethod
    def mutate(root: Any, info: Any, devices: list) -> 'BatchUpdateRingDevices':
        """
        Batch update or create Ring devices from frontend.

        Only updates static device info (name, type, location).
        Real-time data (battery, status) managed via websocket.
        """
        try:
            devices_updated = 0
            devices_created = 0

            for device_data in devices:
                device_id = device_data.device_id

                device = RingDevice.query.filter_by(device_id=device_id).first()

                if device:
                    # Update static device info only
                    device.device_type = device_data.device_type
                    device.name = device_data.name
                    device.location = device_data.get('location', device.location)
                    device.is_active = True
                    device.updated_at = datetime.utcnow()
                    devices_updated += 1
                else:
                    # Create new device with static info only
                    device = RingDevice(
                        device_id=device_id,
                        device_type=device_data.device_type,
                        name=device_data.name,
                        location=device_data.get('location', ''),
                        is_active=True
                    )
                    db.session.add(device)
                    devices_created += 1

            db.session.commit()

            logger.info(f"Batch updated Ring devices: {devices_updated} updated, {devices_created} created")

            return BatchUpdateRingDevices(
                success=True,
                message=f"Successfully updated {devices_updated + devices_created} devices",
                devices_updated=devices_updated,
                devices_created=devices_created
            )

        except Exception as e:
            db.session.rollback()
            logger.error(f"Batch update Ring devices failed: {e}")
            return BatchUpdateRingDevices(
                success=False,
                message=f"Batch update failed: {str(e)}",
                devices_updated=0,
                devices_created=0
            )


# ============================================================================
# Location Management Mutations
# ============================================================================

class CreateLocationInput(graphene.InputObjectType):
    """Input for creating a new location."""
    name = graphene.String(required=True, description="Location name (required, max 100 chars)")
    description = graphene.String(description="Location description (optional, max 500 chars)")


class UpdateLocationInput(graphene.InputObjectType):
    """Input for updating an existing location."""
    id = graphene.Int(required=True, description="Location ID to update")
    name = graphene.String(description="New location name")
    description = graphene.String(description="New location description")


class LocationPayload(graphene.ObjectType):
    """Response payload for location mutations."""
    location = graphene.Field(LocationObject)
    success = graphene.Boolean(required=True)
    message = graphene.String()
    errors = graphene.List(graphene.String)


class DeletePayload(graphene.ObjectType):
    """Response payload for delete mutations."""
    success = graphene.Boolean(required=True)
    message = graphene.String()
    errors = graphene.List(graphene.String)


class CreateLocation(graphene.Mutation):
    """Create a new location."""
    class Arguments:
        input = CreateLocationInput(required=True)

    Output = LocationPayload

    @staticmethod
    @require_user
    def mutate(root: Any, info: Any, input: CreateLocationInput) -> LocationPayload:
        """Create a new location with validation."""
        from app.validation import LocationInputValidator

        validator = LocationInputValidator()
        validation_result = validator.validate_create_input(
            name=input.name,
            description=input.description
        )

        if not validation_result.is_valid:
            logger.warning(
                "Location creation validation failed",
                extra={
                    'extra_context': {
                        'name': input.name,
                        'validation_errors': validation_result.error_messages,
                        'operation': 'create_location_validation'
                    }
                }
            )
            return LocationPayload(
                location=None,
                success=False,
                message="Validation failed",
                errors=validation_result.error_messages
            )

        try:
            location = Location(
                name=input.name.strip(),
                description=input.description.strip() if input.description else None
            )

            db.session.add(location)
            db.session.commit()

            logger.info(
                "Location created successfully",
                extra={
                    'extra_context': {
                        'location_id': location.id,
                        'name': location.name,
                        'operation': 'create_location_success'
                    }
                }
            )

            return LocationPayload(
                location=location,
                success=True,
                message="Location created successfully",
                errors=[]
            )

        except Exception as e:
            db.session.rollback()
            logger.error(
                "Failed to create location",
                exc_info=True,
                extra={
                    'extra_context': {
                        'name': input.name,
                        'operation': 'create_location_error'
                    }
                }
            )
            return LocationPayload(
                location=None,
                success=False,
                message="Failed to create location",
                errors=["Database operation failed"]
            )


class UpdateLocation(graphene.Mutation):
    """Update an existing location."""
    class Arguments:
        input = UpdateLocationInput(required=True)

    Output = LocationPayload

    @staticmethod
    @require_user
    def mutate(root: Any, info: Any, input: UpdateLocationInput) -> LocationPayload:
        """Update an existing location with validation."""
        from app.validation import LocationInputValidator

        validator = LocationInputValidator()
        validation_result = validator.validate_update_input(
            location_id=input.id,
            name=input.name,
            description=input.description
        )

        if not validation_result.is_valid:
            logger.warning(
                "Location update validation failed",
                extra={
                    'extra_context': {
                        'location_id': input.id,
                        'validation_errors': validation_result.error_messages,
                        'operation': 'update_location_validation'
                    }
                }
            )
            return LocationPayload(
                location=None,
                success=False,
                message="Validation failed",
                errors=validation_result.error_messages
            )

        try:
            location = Location.query.get(input.id)

            if input.name is not None:
                location.name = input.name.strip()
            if input.description is not None:
                location.description = input.description.strip() if input.description else None

            db.session.commit()

            logger.info(
                "Location updated successfully",
                extra={
                    'extra_context': {
                        'location_id': location.id,
                        'name': location.name,
                        'operation': 'update_location_success'
                    }
                }
            )

            return LocationPayload(
                location=location,
                success=True,
                message="Location updated successfully",
                errors=[]
            )

        except Exception as e:
            db.session.rollback()
            logger.error(
                "Failed to update location",
                exc_info=True,
                extra={
                    'extra_context': {
                        'location_id': input.id,
                        'operation': 'update_location_error'
                    }
                }
            )
            return LocationPayload(
                location=None,
                success=False,
                message="Failed to update location",
                errors=["Database operation failed"]
            )


class DeleteLocation(graphene.Mutation):
    """Delete a location."""
    class Arguments:
        id = graphene.Int(required=True, description="Location ID to delete")

    Output = DeletePayload

    @staticmethod
    @require_user
    def mutate(root: Any, info: Any, id: int) -> DeletePayload:
        """Delete a location with validation."""
        from app.validation import LocationInputValidator

        validator = LocationInputValidator()
        validation_result = validator.validate_delete(location_id=id)

        if not validation_result.is_valid:
            logger.warning(
                "Location deletion validation failed",
                extra={
                    'extra_context': {
                        'location_id': id,
                        'validation_errors': validation_result.error_messages,
                        'operation': 'delete_location_validation'
                    }
                }
            )
            return DeletePayload(
                success=False,
                message="Validation failed",
                errors=validation_result.error_messages
            )

        try:
            location = Location.query.get(id)
            location_name = location.name

            db.session.delete(location)
            db.session.commit()

            logger.info(
                "Location deleted successfully",
                extra={
                    'extra_context': {
                        'location_id': id,
                        'name': location_name,
                        'operation': 'delete_location_success'
                    }
                }
            )

            return DeletePayload(
                success=True,
                message=f"Location '{location_name}' deleted successfully",
                errors=[]
            )

        except Exception as e:
            db.session.rollback()
            logger.error(
                "Failed to delete location",
                exc_info=True,
                extra={
                    'extra_context': {
                        'location_id': id,
                        'operation': 'delete_location_error'
                    }
                }
            )
            return DeletePayload(
                success=False,
                message="Failed to delete location",
                errors=["Database operation failed"]
            )


# ============================================================================
# Sensor Management Mutations
# ============================================================================

class CreateSensorInput(graphene.InputObjectType):
    """Input for creating a new sensor."""
    name = graphene.String(required=True, description="Sensor name (required, max 100 chars)")
    hostname = graphene.String(required=True, description="Sensor hostname (required, max 100 chars)")
    installation_date = graphene.DateTime(description="Installation date (defaults to now)")


class UpdateSensorInput(graphene.InputObjectType):
    """Input for updating an existing sensor."""
    id = graphene.Int(required=True, description="Sensor ID to update")
    name = graphene.String(description="New sensor name")
    hostname = graphene.String(description="New sensor hostname")
    is_active = graphene.Boolean(description="Sensor active status")


class SensorPayload(graphene.ObjectType):
    """Response payload for sensor mutations."""
    sensor = graphene.Field(SensorObject)
    success = graphene.Boolean(required=True)
    message = graphene.String()
    errors = graphene.List(graphene.String)


class CreateSensor(graphene.Mutation):
    """Create a new sensor."""
    class Arguments:
        input = CreateSensorInput(required=True)

    Output = SensorPayload

    @staticmethod
    @require_user
    def mutate(root: Any, info: Any, input: CreateSensorInput) -> SensorPayload:
        """Create a new sensor with validation."""
        from app.validation import SensorInputValidator

        validator = SensorInputValidator()
        validation_result = validator.validate_create_input(
            name=input.name,
            hostname=input.hostname,
            installation_date=input.installation_date
        )

        if not validation_result.is_valid:
            logger.warning(
                "Sensor creation validation failed",
                extra={
                    'extra_context': {
                        'name': input.name,
                        'hostname': input.hostname,
                        'validation_errors': validation_result.error_messages,
                        'operation': 'create_sensor_validation'
                    }
                }
            )
            return SensorPayload(
                sensor=None,
                success=False,
                message="Validation failed",
                errors=validation_result.error_messages
            )

        try:
            sensor = Sensor(
                name=input.name.strip(),
                hostname=input.hostname.strip(),
                installation_date=input.installation_date if input.installation_date else datetime.utcnow(),
                is_active=True
            )

            db.session.add(sensor)
            db.session.commit()

            logger.info(
                "Sensor created successfully",
                extra={
                    'extra_context': {
                        'sensor_id': sensor.id,
                        'name': sensor.name,
                        'hostname': sensor.hostname,
                        'operation': 'create_sensor_success'
                    }
                }
            )

            return SensorPayload(
                sensor=sensor,
                success=True,
                message="Sensor created successfully",
                errors=[]
            )

        except Exception as e:
            db.session.rollback()
            logger.error(
                "Failed to create sensor",
                exc_info=True,
                extra={
                    'extra_context': {
                        'name': input.name,
                        'hostname': input.hostname,
                        'operation': 'create_sensor_error'
                    }
                }
            )
            return SensorPayload(
                sensor=None,
                success=False,
                message="Failed to create sensor",
                errors=["Database operation failed"]
            )


class UpdateSensor(graphene.Mutation):
    """Update an existing sensor."""
    class Arguments:
        input = UpdateSensorInput(required=True)

    Output = SensorPayload

    @staticmethod
    @require_user
    def mutate(root: Any, info: Any, input: UpdateSensorInput) -> SensorPayload:
        """Update an existing sensor with validation."""
        from app.validation import SensorInputValidator

        validator = SensorInputValidator()
        validation_result = validator.validate_update_input(
            sensor_id=input.id,
            name=input.name,
            hostname=input.hostname,
            is_active=input.is_active
        )

        if not validation_result.is_valid:
            logger.warning(
                "Sensor update validation failed",
                extra={
                    'extra_context': {
                        'sensor_id': input.id,
                        'validation_errors': validation_result.error_messages,
                        'operation': 'update_sensor_validation'
                    }
                }
            )
            return SensorPayload(
                sensor=None,
                success=False,
                message="Validation failed",
                errors=validation_result.error_messages
            )

        try:
            sensor = Sensor.query.get(input.id)

            if input.name is not None:
                sensor.name = input.name.strip()
            if input.hostname is not None:
                sensor.hostname = input.hostname.strip()
            if input.is_active is not None:
                sensor.is_active = input.is_active

            db.session.commit()

            logger.info(
                "Sensor updated successfully",
                extra={
                    'extra_context': {
                        'sensor_id': sensor.id,
                        'name': sensor.name,
                        'is_active': sensor.is_active,
                        'operation': 'update_sensor_success'
                    }
                }
            )

            return SensorPayload(
                sensor=sensor,
                success=True,
                message="Sensor updated successfully",
                errors=[]
            )

        except Exception as e:
            db.session.rollback()
            logger.error(
                "Failed to update sensor",
                exc_info=True,
                extra={
                    'extra_context': {
                        'sensor_id': input.id,
                        'operation': 'update_sensor_error'
                    }
                }
            )
            return SensorPayload(
                sensor=None,
                success=False,
                message="Failed to update sensor",
                errors=["Database operation failed"]
            )


class DeleteSensor(graphene.Mutation):
    """Delete a sensor (only if no readings exist)."""
    class Arguments:
        id = graphene.Int(required=True, description="Sensor ID to delete")

    Output = DeletePayload

    @staticmethod
    @require_user
    def mutate(root: Any, info: Any, id: int) -> DeletePayload:
        """Delete a sensor with validation."""
        from app.validation import SensorInputValidator

        validator = SensorInputValidator()
        validation_result = validator.validate_delete(sensor_id=id)

        if not validation_result.is_valid:
            logger.warning(
                "Sensor deletion validation failed",
                extra={
                    'extra_context': {
                        'sensor_id': id,
                        'validation_errors': validation_result.error_messages,
                        'operation': 'delete_sensor_validation'
                    }
                }
            )
            return DeletePayload(
                success=False,
                message="Validation failed",
                errors=validation_result.error_messages
            )

        try:
            sensor = Sensor.query.get(id)
            sensor_name = sensor.name

            # Also delete any sensor_location records
            SensorLocation.query.filter_by(sensor_id=id).delete()

            db.session.delete(sensor)
            db.session.commit()

            logger.info(
                "Sensor deleted successfully",
                extra={
                    'extra_context': {
                        'sensor_id': id,
                        'name': sensor_name,
                        'operation': 'delete_sensor_success'
                    }
                }
            )

            return DeletePayload(
                success=True,
                message=f"Sensor '{sensor_name}' deleted successfully",
                errors=[]
            )

        except Exception as e:
            db.session.rollback()
            logger.error(
                "Failed to delete sensor",
                exc_info=True,
                extra={
                    'extra_context': {
                        'sensor_id': id,
                        'operation': 'delete_sensor_error'
                    }
                }
            )
            return DeletePayload(
                success=False,
                message="Failed to delete sensor",
                errors=["Database operation failed"]
            )


class ToggleSensorActive(graphene.Mutation):
    """Toggle sensor active status."""
    class Arguments:
        id = graphene.Int(required=True, description="Sensor ID")
        is_active = graphene.Boolean(required=True, description="New active status")

    Output = SensorPayload

    @staticmethod
    @require_user
    def mutate(root: Any, info: Any, id: int, is_active: bool) -> SensorPayload:
        """Toggle sensor active status."""
        sensor = Sensor.query.get(id)

        if not sensor:
            return SensorPayload(
                sensor=None,
                success=False,
                message=f"Sensor with ID {id} does not exist",
                errors=["Sensor not found"]
            )

        try:
            sensor.is_active = is_active
            db.session.commit()

            status = "activated" if is_active else "deactivated"
            logger.info(
                f"Sensor {status} successfully",
                extra={
                    'extra_context': {
                        'sensor_id': sensor.id,
                        'name': sensor.name,
                        'is_active': is_active,
                        'operation': 'toggle_sensor_active_success'
                    }
                }
            )

            return SensorPayload(
                sensor=sensor,
                success=True,
                message=f"Sensor {status} successfully",
                errors=[]
            )

        except Exception as e:
            db.session.rollback()
            logger.error(
                "Failed to toggle sensor active status",
                exc_info=True,
                extra={
                    'extra_context': {
                        'sensor_id': id,
                        'operation': 'toggle_sensor_active_error'
                    }
                }
            )
            return SensorPayload(
                sensor=None,
                success=False,
                message="Failed to update sensor",
                errors=["Database operation failed"]
            )


# ============================================================================
# Sensor-Location Assignment Mutations
# ============================================================================

class AssignSensorLocationInput(graphene.InputObjectType):
    """Input for assigning a sensor to a location."""
    sensor_id = graphene.Int(required=True, description="Sensor ID to assign")
    location_id = graphene.Int(required=True, description="Location ID to assign to")
    start_time = graphene.DateTime(description="Assignment start time (defaults to now)")


class MoveSensorInput(graphene.InputObjectType):
    """Input for moving a sensor to a new location."""
    sensor_id = graphene.Int(required=True, description="Sensor ID to move")
    new_location_id = graphene.Int(required=True, description="New location ID")
    move_time = graphene.DateTime(description="Move time (defaults to now)")


class SensorLocationPayload(graphene.ObjectType):
    """Response payload for sensor-location mutations."""
    sensor_location = graphene.Field(SensorLocationObject)
    success = graphene.Boolean(required=True)
    message = graphene.String()
    errors = graphene.List(graphene.String)


class AssignSensorToLocation(graphene.Mutation):
    """Assign an unassigned sensor to a location."""
    class Arguments:
        input = AssignSensorLocationInput(required=True)

    Output = SensorLocationPayload

    @staticmethod
    @require_user
    def mutate(root: Any, info: Any, input: AssignSensorLocationInput) -> SensorLocationPayload:
        """Assign a sensor to a location."""
        from app.validation import SensorLocationValidator

        validator = SensorLocationValidator()
        validation_result = validator.validate_assign(
            sensor_id=input.sensor_id,
            location_id=input.location_id
        )

        if not validation_result.is_valid:
            logger.warning(
                "Sensor assignment validation failed",
                extra={
                    'extra_context': {
                        'sensor_id': input.sensor_id,
                        'location_id': input.location_id,
                        'validation_errors': validation_result.error_messages,
                        'operation': 'assign_sensor_validation'
                    }
                }
            )
            return SensorLocationPayload(
                sensor_location=None,
                success=False,
                message="Validation failed",
                errors=validation_result.error_messages
            )

        try:
            start_time = input.start_time if input.start_time else datetime.utcnow()

            sensor_location = SensorLocation(
                sensor_id=input.sensor_id,
                location_id=input.location_id,
                start_time=start_time,
                end_time=None,
                is_current=True
            )

            db.session.add(sensor_location)
            db.session.commit()

            logger.info(
                "Sensor assigned to location successfully",
                extra={
                    'extra_context': {
                        'sensor_location_id': sensor_location.id,
                        'sensor_id': input.sensor_id,
                        'location_id': input.location_id,
                        'operation': 'assign_sensor_success'
                    }
                }
            )

            return SensorLocationPayload(
                sensor_location=sensor_location,
                success=True,
                message="Sensor assigned to location successfully",
                errors=[]
            )

        except Exception as e:
            db.session.rollback()
            logger.error(
                "Failed to assign sensor to location",
                exc_info=True,
                extra={
                    'extra_context': {
                        'sensor_id': input.sensor_id,
                        'location_id': input.location_id,
                        'operation': 'assign_sensor_error'
                    }
                }
            )
            return SensorLocationPayload(
                sensor_location=None,
                success=False,
                message="Failed to assign sensor to location",
                errors=["Database operation failed"]
            )


class MoveSensorToLocation(graphene.Mutation):
    """Move a sensor from its current location to a new location."""
    class Arguments:
        input = MoveSensorInput(required=True)

    Output = SensorLocationPayload

    @staticmethod
    @require_user
    def mutate(root: Any, info: Any, input: MoveSensorInput) -> SensorLocationPayload:
        """Move a sensor to a new location (atomic operation)."""
        from app.validation import SensorLocationValidator

        validator = SensorLocationValidator()
        validation_result = validator.validate_move(
            sensor_id=input.sensor_id,
            new_location_id=input.new_location_id
        )

        if not validation_result.is_valid:
            logger.warning(
                "Sensor move validation failed",
                extra={
                    'extra_context': {
                        'sensor_id': input.sensor_id,
                        'new_location_id': input.new_location_id,
                        'validation_errors': validation_result.error_messages,
                        'operation': 'move_sensor_validation'
                    }
                }
            )
            return SensorLocationPayload(
                sensor_location=None,
                success=False,
                message="Validation failed",
                errors=validation_result.error_messages
            )

        try:
            move_time = input.move_time if input.move_time else datetime.utcnow()

            # Find and close current assignment
            current_assignment = SensorLocation.query.filter_by(
                sensor_id=input.sensor_id,
                is_current=True
            ).first()

            old_location_id = current_assignment.location_id
            current_assignment.end_time = move_time
            current_assignment.is_current = False

            # Create new assignment
            new_assignment = SensorLocation(
                sensor_id=input.sensor_id,
                location_id=input.new_location_id,
                start_time=move_time,
                end_time=None,
                is_current=True
            )

            db.session.add(new_assignment)
            db.session.commit()

            logger.info(
                "Sensor moved to new location successfully",
                extra={
                    'extra_context': {
                        'sensor_location_id': new_assignment.id,
                        'sensor_id': input.sensor_id,
                        'old_location_id': old_location_id,
                        'new_location_id': input.new_location_id,
                        'operation': 'move_sensor_success'
                    }
                }
            )

            return SensorLocationPayload(
                sensor_location=new_assignment,
                success=True,
                message="Sensor moved to new location successfully",
                errors=[]
            )

        except Exception as e:
            db.session.rollback()
            logger.error(
                "Failed to move sensor to new location",
                exc_info=True,
                extra={
                    'extra_context': {
                        'sensor_id': input.sensor_id,
                        'new_location_id': input.new_location_id,
                        'operation': 'move_sensor_error'
                    }
                }
            )
            return SensorLocationPayload(
                sensor_location=None,
                success=False,
                message="Failed to move sensor to new location",
                errors=["Database operation failed"]
            )


class RemoveSensorFromLocation(graphene.Mutation):
    """Remove a sensor from its current location (unassign)."""
    class Arguments:
        sensor_id = graphene.Int(required=True, description="Sensor ID to unassign")

    Output = SensorLocationPayload

    @staticmethod
    @require_user
    def mutate(root: Any, info: Any, sensor_id: int) -> SensorLocationPayload:
        """Remove a sensor from its current location."""
        from app.validation import SensorLocationValidator

        validator = SensorLocationValidator()
        validation_result = validator.validate_remove(sensor_id=sensor_id)

        if not validation_result.is_valid:
            logger.warning(
                "Sensor removal validation failed",
                extra={
                    'extra_context': {
                        'sensor_id': sensor_id,
                        'validation_errors': validation_result.error_messages,
                        'operation': 'remove_sensor_validation'
                    }
                }
            )
            return SensorLocationPayload(
                sensor_location=None,
                success=False,
                message="Validation failed",
                errors=validation_result.error_messages
            )

        try:
            current_assignment = SensorLocation.query.filter_by(
                sensor_id=sensor_id,
                is_current=True
            ).first()

            location_id = current_assignment.location_id
            current_assignment.end_time = datetime.utcnow()
            current_assignment.is_current = False

            db.session.commit()

            logger.info(
                "Sensor removed from location successfully",
                extra={
                    'extra_context': {
                        'sensor_location_id': current_assignment.id,
                        'sensor_id': sensor_id,
                        'location_id': location_id,
                        'operation': 'remove_sensor_success'
                    }
                }
            )

            return SensorLocationPayload(
                sensor_location=current_assignment,
                success=True,
                message="Sensor removed from location successfully",
                errors=[]
            )

        except Exception as e:
            db.session.rollback()
            logger.error(
                "Failed to remove sensor from location",
                exc_info=True,
                extra={
                    'extra_context': {
                        'sensor_id': sensor_id,
                        'operation': 'remove_sensor_error'
                    }
                }
            )
            return SensorLocationPayload(
                sensor_location=None,
                success=False,
                message="Failed to remove sensor from location",
                errors=["Database operation failed"]
            )


# Dashboard Layout Types and Mutations

class DashboardLayoutObject(SQLAlchemyObjectType):
    """GraphQL type for dashboard layouts."""
    class Meta:
        model = DashboardLayout
        exclude_fields = ('user',)

    layout_data = graphene.JSONString()

    def resolve_layout_data(self, info: Any) -> str:
        """Return layout data as JSON string."""
        import json
        return json.dumps(self.layout_data) if self.layout_data else None


class CreateDashboardLayoutInput(graphene.InputObjectType):
    """Input type for creating a dashboard layout."""
    name = graphene.String(required=True)
    layout_data = graphene.JSONString(required=True)


class UpdateDashboardLayoutInput(graphene.InputObjectType):
    """Input type for updating a dashboard layout."""
    id = graphene.ID(required=True)
    name = graphene.String()
    layout_data = graphene.JSONString()


class DashboardLayoutMutationResponse(graphene.ObjectType):
    """Response type for dashboard layout mutations."""
    success = graphene.Boolean()
    message = graphene.String()
    errors = graphene.List(graphene.String)
    layout = graphene.Field(DashboardLayoutObject)


class CreateDashboardLayout(graphene.Mutation):
    """Create a new dashboard layout."""
    class Arguments:
        input = CreateDashboardLayoutInput(required=True)

    Output = DashboardLayoutMutationResponse

    @staticmethod
    @require_user
    def mutate(root: Any, info: Any, input: CreateDashboardLayoutInput) -> DashboardLayoutMutationResponse:
        """Create a new dashboard layout for the authenticated user."""
        from app.validation import DashboardLayoutValidator
        import json

        user = get_user_from_context(info)
        if not user:
            return DashboardLayoutMutationResponse(
                success=False,
                message="Authentication required",
                errors=["You must be logged in to create a layout"]
            )

        # Parse layout data from JSON string
        try:
            layout_data = json.loads(input.layout_data) if isinstance(input.layout_data, str) else input.layout_data
        except json.JSONDecodeError as e:
            return DashboardLayoutMutationResponse(
                success=False,
                message="Invalid JSON in layout_data",
                errors=[str(e)]
            )

        # Validate input
        validator = DashboardLayoutValidator()
        validation_result = validator.validate_create_input(
            user_id=user.id,
            name=input.name,
            layout_data=layout_data
        )

        if not validation_result.is_valid:
            logger.warning(
                "Dashboard layout validation failed",
                extra={
                    'extra_context': {
                        'user_id': user.id,
                        'validation_errors': validation_result.error_messages,
                        'operation': 'create_dashboard_layout_validation'
                    }
                }
            )
            return DashboardLayoutMutationResponse(
                success=False,
                message="Validation failed",
                errors=validation_result.error_messages
            )

        try:
            # Create the layout
            layout = DashboardLayout(
                user_id=user.id,
                name=input.name.strip(),
                layout_data=layout_data,
                is_last_used=True
            )

            # Clear is_last_used from other layouts
            DashboardLayout.query.filter_by(user_id=user.id).update({'is_last_used': False})

            db.session.add(layout)
            db.session.commit()

            logger.info(
                "Dashboard layout created successfully",
                extra={
                    'extra_context': {
                        'user_id': user.id,
                        'layout_id': layout.id,
                        'layout_name': layout.name,
                        'operation': 'create_dashboard_layout_success'
                    }
                }
            )

            return DashboardLayoutMutationResponse(
                success=True,
                message="Layout saved successfully",
                layout=layout
            )

        except Exception as e:
            db.session.rollback()
            logger.error(
                "Failed to create dashboard layout",
                exc_info=True,
                extra={
                    'extra_context': {
                        'user_id': user.id,
                        'operation': 'create_dashboard_layout_error'
                    }
                }
            )
            return DashboardLayoutMutationResponse(
                success=False,
                message="Failed to save layout",
                errors=[str(e)]
            )


class UpdateDashboardLayout(graphene.Mutation):
    """Update an existing dashboard layout."""
    class Arguments:
        input = UpdateDashboardLayoutInput(required=True)

    Output = DashboardLayoutMutationResponse

    @staticmethod
    @require_user
    def mutate(root: Any, info: Any, input: UpdateDashboardLayoutInput) -> DashboardLayoutMutationResponse:
        """Update a dashboard layout for the authenticated user."""
        from app.validation import DashboardLayoutValidator
        import json

        user = get_user_from_context(info)
        if not user:
            return DashboardLayoutMutationResponse(
                success=False,
                message="Authentication required",
                errors=["You must be logged in to update a layout"]
            )

        # Parse layout data if provided
        layout_data = None
        if input.layout_data:
            try:
                layout_data = json.loads(input.layout_data) if isinstance(input.layout_data, str) else input.layout_data
            except json.JSONDecodeError as e:
                return DashboardLayoutMutationResponse(
                    success=False,
                    message="Invalid JSON in layout_data",
                    errors=[str(e)]
                )

        # Validate input
        validator = DashboardLayoutValidator()
        validation_result = validator.validate_update_input(
            user_id=user.id,
            layout_id=int(input.id),
            name=input.name,
            layout_data=layout_data
        )

        if not validation_result.is_valid:
            return DashboardLayoutMutationResponse(
                success=False,
                message="Validation failed",
                errors=validation_result.error_messages
            )

        try:
            layout = DashboardLayout.query.filter_by(id=int(input.id), user_id=user.id).first()

            if input.name is not None:
                layout.name = input.name.strip()
            if layout_data is not None:
                layout.layout_data = layout_data

            db.session.commit()

            logger.info(
                "Dashboard layout updated successfully",
                extra={
                    'extra_context': {
                        'user_id': user.id,
                        'layout_id': layout.id,
                        'operation': 'update_dashboard_layout_success'
                    }
                }
            )

            return DashboardLayoutMutationResponse(
                success=True,
                message="Layout updated successfully",
                layout=layout
            )

        except Exception as e:
            db.session.rollback()
            logger.error(
                "Failed to update dashboard layout",
                exc_info=True,
                extra={
                    'extra_context': {
                        'user_id': user.id,
                        'layout_id': input.id,
                        'operation': 'update_dashboard_layout_error'
                    }
                }
            )
            return DashboardLayoutMutationResponse(
                success=False,
                message="Failed to update layout",
                errors=[str(e)]
            )


class DeleteDashboardLayout(graphene.Mutation):
    """Delete a dashboard layout."""
    class Arguments:
        id = graphene.ID(required=True)

    Output = DashboardLayoutMutationResponse

    @staticmethod
    @require_user
    def mutate(root: Any, info: Any, id: str) -> DashboardLayoutMutationResponse:
        """Delete a dashboard layout for the authenticated user."""
        from app.validation import DashboardLayoutValidator

        user = get_user_from_context(info)
        if not user:
            return DashboardLayoutMutationResponse(
                success=False,
                message="Authentication required",
                errors=["You must be logged in to delete a layout"]
            )

        # Validate deletion
        validator = DashboardLayoutValidator()
        validation_result = validator.validate_delete(
            user_id=user.id,
            layout_id=int(id)
        )

        if not validation_result.is_valid:
            return DashboardLayoutMutationResponse(
                success=False,
                message="Validation failed",
                errors=validation_result.error_messages
            )

        try:
            layout = DashboardLayout.query.filter_by(id=int(id), user_id=user.id).first()
            was_last_used = layout.is_last_used
            layout_name = layout.name

            db.session.delete(layout)
            db.session.commit()

            # If deleted layout was last used, mark oldest remaining as last used
            if was_last_used:
                oldest_layout = DashboardLayout.query.filter_by(
                    user_id=user.id
                ).order_by(DashboardLayout.created_at.asc()).first()
                if oldest_layout:
                    oldest_layout.is_last_used = True
                    db.session.commit()

            logger.info(
                "Dashboard layout deleted successfully",
                extra={
                    'extra_context': {
                        'user_id': user.id,
                        'layout_id': id,
                        'layout_name': layout_name,
                        'operation': 'delete_dashboard_layout_success'
                    }
                }
            )

            return DashboardLayoutMutationResponse(
                success=True,
                message="Layout deleted successfully"
            )

        except Exception as e:
            db.session.rollback()
            logger.error(
                "Failed to delete dashboard layout",
                exc_info=True,
                extra={
                    'extra_context': {
                        'user_id': user.id,
                        'layout_id': id,
                        'operation': 'delete_dashboard_layout_error'
                    }
                }
            )
            return DashboardLayoutMutationResponse(
                success=False,
                message="Failed to delete layout",
                errors=[str(e)]
            )


class SetLastUsedLayout(graphene.Mutation):
    """Set a layout as the last used layout."""
    class Arguments:
        id = graphene.ID(required=True)

    Output = DashboardLayoutMutationResponse

    @staticmethod
    @require_user
    def mutate(root: Any, info: Any, id: str) -> DashboardLayoutMutationResponse:
        """Set a layout as the last used for the authenticated user."""
        user = get_user_from_context(info)
        if not user:
            return DashboardLayoutMutationResponse(
                success=False,
                message="Authentication required",
                errors=["You must be logged in"]
            )

        try:
            layout = DashboardLayout.query.filter_by(id=int(id), user_id=user.id).first()
            if not layout:
                return DashboardLayoutMutationResponse(
                    success=False,
                    message="Layout not found",
                    errors=["Layout does not exist or does not belong to you"]
                )

            # Clear all is_last_used flags for this user
            DashboardLayout.query.filter_by(user_id=user.id).update({'is_last_used': False})

            # Set this layout as last used
            layout.is_last_used = True
            db.session.commit()

            return DashboardLayoutMutationResponse(
                success=True,
                message="Layout set as last used",
                layout=layout
            )

        except Exception as e:
            db.session.rollback()
            logger.error(
                "Failed to set last used layout",
                exc_info=True,
                extra={
                    'extra_context': {
                        'user_id': user.id,
                        'layout_id': id,
                        'operation': 'set_last_used_layout_error'
                    }
                }
            )
            return DashboardLayoutMutationResponse(
                success=False,
                message="Failed to set last used layout",
                errors=[str(e)]
            )


class DuplicateDashboardLayout(graphene.Mutation):
    """Duplicate an existing dashboard layout with a new name."""
    class Arguments:
        id = graphene.ID(required=True)
        new_name = graphene.String(required=True)

    Output = DashboardLayoutMutationResponse

    @staticmethod
    @require_user
    def mutate(root: Any, info: Any, id: str, new_name: str) -> DashboardLayoutMutationResponse:
        """Duplicate a dashboard layout for the authenticated user."""
        from app.validation import DashboardLayoutValidator

        user = get_user_from_context(info)
        if not user:
            return DashboardLayoutMutationResponse(
                success=False,
                message="Authentication required",
                errors=["You must be logged in to duplicate a layout"]
            )

        # Validate duplication
        validator = DashboardLayoutValidator()
        validation_result = validator.validate_duplicate(
            user_id=user.id,
            layout_id=int(id),
            new_name=new_name
        )

        if not validation_result.is_valid:
            return DashboardLayoutMutationResponse(
                success=False,
                message="Validation failed",
                errors=validation_result.error_messages
            )

        try:
            source_layout = DashboardLayout.query.filter_by(id=int(id), user_id=user.id).first()

            # Create duplicate
            new_layout = DashboardLayout(
                user_id=user.id,
                name=new_name.strip(),
                layout_data=source_layout.layout_data,
                is_last_used=False
            )

            db.session.add(new_layout)
            db.session.commit()

            logger.info(
                "Dashboard layout duplicated successfully",
                extra={
                    'extra_context': {
                        'user_id': user.id,
                        'source_layout_id': id,
                        'new_layout_id': new_layout.id,
                        'new_layout_name': new_layout.name,
                        'operation': 'duplicate_dashboard_layout_success'
                    }
                }
            )

            return DashboardLayoutMutationResponse(
                success=True,
                message="Layout duplicated successfully",
                layout=new_layout
            )

        except Exception as e:
            db.session.rollback()
            logger.error(
                "Failed to duplicate dashboard layout",
                exc_info=True,
                extra={
                    'extra_context': {
                        'user_id': user.id,
                        'source_layout_id': id,
                        'operation': 'duplicate_dashboard_layout_error'
                    }
                }
            )
            return DashboardLayoutMutationResponse(
                success=False,
                message="Failed to duplicate layout",
                errors=[str(e)]
            )


class PingSensor(graphene.Mutation):
    """Ping a sensor to check its health status."""
    class Arguments:
        sensor_id = graphene.Int(required=True)

    Output = PingSensorResult

    @staticmethod
    def mutate(root: Any, info: Any, sensor_id: int) -> 'PingSensorResult':
        """Ping a sensor and return its health status."""
        import time

        sensor = Sensor.query.get(sensor_id)
        if not sensor:
            return PingSensorResult(
                success=False,
                message=f"Sensor with ID {sensor_id} not found",
                sensor_id=sensor_id
            )

        if not sensor.ip_address:
            return PingSensorResult(
                success=False,
                message=f"Sensor {sensor.name} has no IP address configured",
                sensor_id=sensor_id
            )

        # Build health check URL
        port = sensor.health_check_port or 8080
        health_url = f"http://{sensor.ip_address}:{port}/health"

        start_time = time.time()

        try:
            response = requests.get(health_url, timeout=10)
            ping_time_ms = int((time.time() - start_time) * 1000)

            if response.status_code == 200:
                health_data = response.json()

                # Store health report
                report = SensorHealthReport(
                    sensor_id=sensor_id,
                    service_running=health_data.get('service_running'),
                    service_uptime_seconds=health_data.get('service_uptime_seconds'),
                    sensor_connected=health_data.get('sensor_connected'),
                    sensor_data_ready=health_data.get('sensor_data_ready'),
                    sensor_serial_number=health_data.get('sensor_serial_number'),
                    last_co2_ppm=health_data.get('last_co2_ppm'),
                    last_temperature_celsius=health_data.get('last_temperature_celsius'),
                    last_humidity_percentage=health_data.get('last_humidity_percentage'),
                    last_reading_time=datetime.fromisoformat(health_data['last_reading_time']) if health_data.get('last_reading_time') else None,
                    system_uptime_seconds=health_data.get('system_uptime_seconds'),
                    disk_usage_percent=health_data.get('disk_usage_percent'),
                    memory_usage_percent=health_data.get('memory_usage_percent'),
                    cpu_temperature_celsius=health_data.get('cpu_temperature_celsius'),
                    api_reachable=health_data.get('api_reachable'),
                    api_response_time_ms=health_data.get('api_response_time_ms'),
                    consecutive_failures=health_data.get('consecutive_failures')
                )
                db.session.add(report)

                # Update sensor health check timestamp
                sensor.last_health_check = datetime.utcnow()
                sensor.last_health_status = 'healthy' if health_data.get('sensor_connected') else 'degraded'
                db.session.commit()

                return PingSensorResult(
                    success=True,
                    message="Sensor is reachable and responding",
                    sensor_id=sensor_id,
                    service_running=health_data.get('service_running'),
                    service_uptime_seconds=health_data.get('service_uptime_seconds'),
                    sensor_connected=health_data.get('sensor_connected'),
                    sensor_data_ready=health_data.get('sensor_data_ready'),
                    sensor_serial_number=health_data.get('sensor_serial_number'),
                    last_co2_ppm=health_data.get('last_co2_ppm'),
                    last_temperature_celsius=health_data.get('last_temperature_celsius'),
                    last_humidity_percentage=health_data.get('last_humidity_percentage'),
                    last_reading_time=datetime.fromisoformat(health_data['last_reading_time']) if health_data.get('last_reading_time') else None,
                    system_uptime_seconds=health_data.get('system_uptime_seconds'),
                    disk_usage_percent=health_data.get('disk_usage_percent'),
                    memory_usage_percent=health_data.get('memory_usage_percent'),
                    cpu_temperature_celsius=health_data.get('cpu_temperature_celsius'),
                    api_reachable=health_data.get('api_reachable'),
                    api_response_time_ms=health_data.get('api_response_time_ms'),
                    consecutive_failures=health_data.get('consecutive_failures'),
                    ping_response_time_ms=ping_time_ms
                )
            else:
                # Sensor reachable but returned error
                sensor.last_health_check = datetime.utcnow()
                sensor.last_health_status = 'degraded'
                db.session.commit()

                return PingSensorResult(
                    success=False,
                    message=f"Sensor responded with status {response.status_code}",
                    sensor_id=sensor_id,
                    error_message=response.text[:500] if response.text else None,
                    ping_response_time_ms=ping_time_ms
                )

        except requests.exceptions.Timeout:
            sensor.last_health_check = datetime.utcnow()
            sensor.last_health_status = 'offline'
            db.session.commit()

            return PingSensorResult(
                success=False,
                message="Sensor did not respond within 10 seconds",
                sensor_id=sensor_id,
                error_message="Connection timeout"
            )

        except requests.exceptions.ConnectionError as e:
            sensor.last_health_check = datetime.utcnow()
            sensor.last_health_status = 'offline'
            db.session.commit()

            return PingSensorResult(
                success=False,
                message="Could not connect to sensor",
                sensor_id=sensor_id,
                error_message=str(e)
            )

        except Exception as e:
            logger.error(f"Error pinging sensor {sensor_id}: {e}", exc_info=True)
            return PingSensorResult(
                success=False,
                message="Error while pinging sensor",
                sensor_id=sensor_id,
                error_message=str(e)
            )


class UpdateSensorNetwork(graphene.Mutation):
    """Update sensor network configuration for health checks."""
    class Arguments:
        sensor_id = graphene.Int(required=True)
        ip_address = graphene.String()
        health_check_port = graphene.Int()

    success = graphene.Boolean()
    message = graphene.String()
    sensor = graphene.Field(SensorObject)

    @staticmethod
    def mutate(root: Any, info: Any, sensor_id: int, ip_address: str = None, health_check_port: int = None):
        sensor = Sensor.query.get(sensor_id)
        if not sensor:
            return UpdateSensorNetwork(
                success=False,
                message=f"Sensor with ID {sensor_id} not found"
            )

        if ip_address is not None:
            sensor.ip_address = ip_address
        if health_check_port is not None:
            sensor.health_check_port = health_check_port

        db.session.commit()

        return UpdateSensorNetwork(
            success=True,
            message="Sensor network configuration updated",
            sensor=sensor
        )


# ---- Sensor Calibration Mutations ----

class CalibrationResult(graphene.ObjectType):
    """Result of a calibration operation."""
    success = graphene.Boolean(required=True)
    message = graphene.String()
    error = graphene.String()
    pre_calibration_co2 = graphene.Int()
    post_calibration_co2 = graphene.Int()
    correction = graphene.Int()
    reference_co2 = graphene.Int()


class CalibrationStatus(graphene.ObjectType):
    """Current calibration status of a sensor."""
    serial_number = graphene.List(graphene.String)
    asc_enabled = graphene.Boolean()
    temperature_offset = graphene.Float()
    current_co2 = graphene.Int()
    current_temperature = graphene.Float()
    current_humidity = graphene.Float()


class CalibrateSensorFRC(graphene.Mutation):
    """Perform Forced Recalibration on a sensor.

    The sensor should be exposed to the reference CO2 concentration
    (typically fresh outdoor air at ~420 ppm) for at least 3 minutes
    before triggering this mutation.
    """
    class Arguments:
        sensor_id = graphene.Int(required=True, description="ID of the sensor to calibrate")
        reference_co2 = graphene.Int(
            default_value=420,
            description="Reference CO2 concentration in ppm (default: 420 for fresh outdoor air)"
        )

    success = graphene.Boolean()
    message = graphene.String()
    result = graphene.Field(CalibrationResult)
    sensor = graphene.Field(SensorObject)

    @staticmethod
    def mutate(root: Any, info: Any, sensor_id: int, reference_co2: int = 420):
        import requests
        from datetime import datetime

        sensor = Sensor.query.get(sensor_id)
        if not sensor:
            return CalibrateSensorFRC(
                success=False,
                message=f"Sensor with ID {sensor_id} not found"
            )

        if not sensor.ip_address:
            return CalibrateSensorFRC(
                success=False,
                message="Sensor IP address not configured"
            )

        calibration_port = sensor.calibration_port or 5001
        url = f"http://{sensor.ip_address}:{calibration_port}/calibrate/frc"

        try:
            response = requests.post(
                url,
                json={"reference_co2": reference_co2},
                timeout=120  # Calibration can take time
            )
            data = response.json()

            if data.get('success'):
                # Update sensor calibration tracking
                sensor.last_calibration_time = datetime.utcnow()
                sensor.last_calibration_reference_co2 = reference_co2
                db.session.commit()

                result = CalibrationResult(
                    success=True,
                    message=data.get('message'),
                    pre_calibration_co2=data.get('pre_calibration_co2'),
                    post_calibration_co2=data.get('post_calibration_co2'),
                    correction=data.get('correction'),
                    reference_co2=reference_co2
                )

                return CalibrateSensorFRC(
                    success=True,
                    message="Calibration successful",
                    result=result,
                    sensor=sensor
                )
            else:
                return CalibrateSensorFRC(
                    success=False,
                    message=data.get('message', 'Calibration failed'),
                    result=CalibrationResult(
                        success=False,
                        error=data.get('error')
                    )
                )

        except requests.exceptions.Timeout:
            return CalibrateSensorFRC(
                success=False,
                message="Calibration request timed out"
            )
        except requests.exceptions.ConnectionError:
            return CalibrateSensorFRC(
                success=False,
                message=f"Cannot connect to sensor at {sensor.ip_address}:{calibration_port}"
            )
        except Exception as e:
            return CalibrateSensorFRC(
                success=False,
                message=f"Calibration failed: {str(e)}"
            )


class SetSensorASC(graphene.Mutation):
    """Enable or disable Automatic Self-Calibration on a sensor."""
    class Arguments:
        sensor_id = graphene.Int(required=True)
        enabled = graphene.Boolean(required=True, description="True to enable ASC, False to disable")

    success = graphene.Boolean()
    message = graphene.String()
    sensor = graphene.Field(SensorObject)

    @staticmethod
    def mutate(root: Any, info: Any, sensor_id: int, enabled: bool):
        import requests

        sensor = Sensor.query.get(sensor_id)
        if not sensor:
            return SetSensorASC(
                success=False,
                message=f"Sensor with ID {sensor_id} not found"
            )

        if not sensor.ip_address:
            return SetSensorASC(
                success=False,
                message="Sensor IP address not configured"
            )

        calibration_port = sensor.calibration_port or 5001
        url = f"http://{sensor.ip_address}:{calibration_port}/calibrate/asc"

        try:
            response = requests.post(
                url,
                json={"enabled": enabled},
                timeout=30
            )
            data = response.json()

            if data.get('success'):
                sensor.auto_calibration_enabled = enabled
                db.session.commit()

                return SetSensorASC(
                    success=True,
                    message=f"ASC {'enabled' if enabled else 'disabled'} successfully",
                    sensor=sensor
                )
            else:
                return SetSensorASC(
                    success=False,
                    message=data.get('message', 'Failed to set ASC')
                )

        except Exception as e:
            return SetSensorASC(
                success=False,
                message=f"Failed to set ASC: {str(e)}"
            )


class SetSensorTemperatureOffset(graphene.Mutation):
    """Set temperature offset compensation for a sensor."""
    class Arguments:
        sensor_id = graphene.Int(required=True)
        offset = graphene.Float(required=True, description="Temperature offset in Celsius (can be negative)")

    success = graphene.Boolean()
    message = graphene.String()
    sensor = graphene.Field(SensorObject)

    @staticmethod
    def mutate(root: Any, info: Any, sensor_id: int, offset: float):
        import requests

        sensor = Sensor.query.get(sensor_id)
        if not sensor:
            return SetSensorTemperatureOffset(
                success=False,
                message=f"Sensor with ID {sensor_id} not found"
            )

        if not sensor.ip_address:
            return SetSensorTemperatureOffset(
                success=False,
                message="Sensor IP address not configured"
            )

        calibration_port = sensor.calibration_port or 5001
        url = f"http://{sensor.ip_address}:{calibration_port}/calibrate/temp"

        try:
            response = requests.post(
                url,
                json={"offset": offset},
                timeout=30
            )
            data = response.json()

            if data.get('success'):
                sensor.temperature_offset = offset
                db.session.commit()

                return SetSensorTemperatureOffset(
                    success=True,
                    message=f"Temperature offset set to {offset}°C",
                    sensor=sensor
                )
            else:
                return SetSensorTemperatureOffset(
                    success=False,
                    message=data.get('message', 'Failed to set temperature offset')
                )

        except Exception as e:
            return SetSensorTemperatureOffset(
                success=False,
                message=f"Failed to set temperature offset: {str(e)}"
            )


class FactoryResetSensor(graphene.Mutation):
    """Reset sensor calibration to factory defaults."""
    class Arguments:
        sensor_id = graphene.Int(required=True)

    success = graphene.Boolean()
    message = graphene.String()
    sensor = graphene.Field(SensorObject)

    @staticmethod
    def mutate(root: Any, info: Any, sensor_id: int):
        import requests

        sensor = Sensor.query.get(sensor_id)
        if not sensor:
            return FactoryResetSensor(
                success=False,
                message=f"Sensor with ID {sensor_id} not found"
            )

        if not sensor.ip_address:
            return FactoryResetSensor(
                success=False,
                message="Sensor IP address not configured"
            )

        calibration_port = sensor.calibration_port or 5001
        url = f"http://{sensor.ip_address}:{calibration_port}/calibrate/reset"

        try:
            response = requests.post(url, json={}, timeout=30)
            data = response.json()

            if data.get('success'):
                # Clear local calibration tracking
                sensor.last_calibration_time = None
                sensor.last_calibration_reference_co2 = None
                sensor.auto_calibration_enabled = True
                sensor.temperature_offset = 0.0
                db.session.commit()

                return FactoryResetSensor(
                    success=True,
                    message="Sensor reset to factory defaults",
                    sensor=sensor
                )
            else:
                return FactoryResetSensor(
                    success=False,
                    message=data.get('message', 'Factory reset failed')
                )

        except Exception as e:
            return FactoryResetSensor(
                success=False,
                message=f"Factory reset failed: {str(e)}"
            )


class GetSensorCalibrationStatus(graphene.Mutation):
    """Get current calibration status from a sensor."""
    class Arguments:
        sensor_id = graphene.Int(required=True)

    success = graphene.Boolean()
    message = graphene.String()
    status = graphene.Field(CalibrationStatus)

    @staticmethod
    def mutate(root: Any, info: Any, sensor_id: int):
        import requests

        sensor = Sensor.query.get(sensor_id)
        if not sensor:
            return GetSensorCalibrationStatus(
                success=False,
                message=f"Sensor with ID {sensor_id} not found"
            )

        if not sensor.ip_address:
            return GetSensorCalibrationStatus(
                success=False,
                message="Sensor IP address not configured"
            )

        calibration_port = sensor.calibration_port or 5001
        url = f"http://{sensor.ip_address}:{calibration_port}/status"

        try:
            response = requests.get(url, timeout=60)
            data = response.json()

            if data.get('success'):
                status_data = data.get('status', {})
                reading = status_data.get('current_reading', {})

                status = CalibrationStatus(
                    serial_number=status_data.get('serial_number'),
                    asc_enabled=status_data.get('asc_enabled'),
                    temperature_offset=status_data.get('temperature_offset'),
                    current_co2=reading.get('co2'),
                    current_temperature=reading.get('temperature'),
                    current_humidity=reading.get('humidity')
                )

                return GetSensorCalibrationStatus(
                    success=True,
                    message="Status retrieved successfully",
                    status=status
                )
            else:
                return GetSensorCalibrationStatus(
                    success=False,
                    message=data.get('message', 'Failed to get status')
                )

        except Exception as e:
            return GetSensorCalibrationStatus(
                success=False,
                message=f"Failed to get status: {str(e)}"
            )


# ---- Alert System Types, Inputs, and Mutations ----

class AlertThresholdObject(SQLAlchemyObjectType):
    """GraphQL type for alert threshold configuration."""
    class Meta:
        model = AlertThreshold

    sensor = graphene.Field(lambda: SensorObject)

    def resolve_sensor(self, info: Any):
        if self.sensor_id:
            return Sensor.query.get(self.sensor_id)
        return None


class AlertHistoryObject(SQLAlchemyObjectType):
    """GraphQL type for alert history entries."""
    class Meta:
        model = AlertHistory

    sensor = graphene.Field(lambda: SensorObject)

    def resolve_sensor(self, info: Any):
        return Sensor.query.get(self.sensor_id)


class UpsertAlertThresholdInput(graphene.InputObjectType):
    """Input for creating or updating an alert threshold."""
    sensor_id = graphene.Int(description="Sensor ID, or omit for global default")
    warning_ppm = graphene.Int(default_value=1000)
    critical_ppm = graphene.Int(default_value=1500)
    cooldown_minutes = graphene.Int(default_value=30)
    is_enabled = graphene.Boolean(default_value=True)


class UpsertAlertThreshold(graphene.Mutation):
    """Create or update an alert threshold for the current user."""
    class Arguments:
        input = UpsertAlertThresholdInput(required=True)

    success = graphene.Boolean()
    message = graphene.String()
    errors = graphene.List(graphene.String)
    alert_threshold = graphene.Field(AlertThresholdObject)

    @staticmethod
    @require_user
    def mutate(root: Any, info: Any, input: UpsertAlertThresholdInput) -> 'UpsertAlertThreshold':
        user = get_user_from_context(info)
        if not user:
            return UpsertAlertThreshold(success=False, message="Authentication required", errors=["Not authenticated"])

        # Validate PPM values
        if input.warning_ppm < 0 or input.critical_ppm < 0:
            return UpsertAlertThreshold(success=False, message="PPM values must be positive", errors=["Invalid PPM"])
        if input.warning_ppm >= input.critical_ppm:
            return UpsertAlertThreshold(success=False, message="Warning PPM must be less than critical PPM", errors=["warning_ppm must be < critical_ppm"])
        if input.cooldown_minutes < 1:
            return UpsertAlertThreshold(success=False, message="Cooldown must be at least 1 minute", errors=["Invalid cooldown"])

        try:
            threshold = AlertThreshold.query.filter_by(
                user_id=user.id, sensor_id=input.sensor_id
            ).first()

            if threshold:
                threshold.warning_ppm = input.warning_ppm
                threshold.critical_ppm = input.critical_ppm
                threshold.cooldown_minutes = input.cooldown_minutes
                threshold.is_enabled = input.is_enabled
            else:
                threshold = AlertThreshold(
                    user_id=user.id,
                    sensor_id=input.sensor_id,
                    warning_ppm=input.warning_ppm,
                    critical_ppm=input.critical_ppm,
                    cooldown_minutes=input.cooldown_minutes,
                    is_enabled=input.is_enabled,
                )
                db.session.add(threshold)

            db.session.commit()

            logger.info(
                "Alert threshold upserted",
                extra={'extra_context': {
                    'user_id': user.id,
                    'sensor_id': input.sensor_id,
                    'threshold_id': threshold.id,
                    'operation': 'upsert_alert_threshold_success',
                }}
            )
            return UpsertAlertThreshold(success=True, message="Alert threshold saved", errors=[], alert_threshold=threshold)

        except Exception as e:
            db.session.rollback()
            logger.error("Failed to upsert alert threshold", exc_info=True,
                         extra={'extra_context': {'user_id': user.id, 'operation': 'upsert_alert_threshold_error'}})
            return UpsertAlertThreshold(success=False, message="Failed to save alert threshold", errors=["Database error"])


class DeleteAlertThreshold(graphene.Mutation):
    """Delete an alert threshold owned by the current user."""
    class Arguments:
        id = graphene.ID(required=True)

    success = graphene.Boolean()
    message = graphene.String()

    @staticmethod
    @require_user
    def mutate(root: Any, info: Any, id: str) -> 'DeleteAlertThreshold':
        user = get_user_from_context(info)
        if not user:
            return DeleteAlertThreshold(success=False, message="Authentication required")

        threshold = AlertThreshold.query.get(int(id))
        if not threshold or threshold.user_id != user.id:
            return DeleteAlertThreshold(success=False, message="Threshold not found")

        db.session.delete(threshold)
        db.session.commit()

        logger.info("Alert threshold deleted",
                     extra={'extra_context': {'threshold_id': id, 'user_id': user.id, 'operation': 'delete_alert_threshold'}})
        return DeleteAlertThreshold(success=True, message="Alert threshold deleted")


class AcknowledgeAlert(graphene.Mutation):
    """Acknowledge a single alert."""
    class Arguments:
        id = graphene.ID(required=True)

    success = graphene.Boolean()
    message = graphene.String()

    @staticmethod
    @require_user
    def mutate(root: Any, info: Any, id: str) -> 'AcknowledgeAlert':
        user = get_user_from_context(info)
        if not user:
            return AcknowledgeAlert(success=False, message="Authentication required")

        alert = AlertHistory.query.get(int(id))
        if not alert or alert.user_id != user.id:
            return AcknowledgeAlert(success=False, message="Alert not found")

        alert.acknowledged = True
        alert.acknowledged_at = datetime.utcnow()
        db.session.commit()

        return AcknowledgeAlert(success=True, message="Alert acknowledged")


class AcknowledgeAllAlerts(graphene.Mutation):
    """Acknowledge all unacknowledged alerts for the current user."""
    class Arguments:
        pass

    success = graphene.Boolean()
    message = graphene.String()
    count = graphene.Int()

    @staticmethod
    @require_user
    def mutate(root: Any, info: Any) -> 'AcknowledgeAllAlerts':
        user = get_user_from_context(info)
        if not user:
            return AcknowledgeAllAlerts(success=False, message="Authentication required", count=0)

        now = datetime.utcnow()
        count = AlertHistory.query.filter_by(
            user_id=user.id, acknowledged=False
        ).update({'acknowledged': True, 'acknowledged_at': now})
        db.session.commit()

        logger.info("All alerts acknowledged",
                     extra={'extra_context': {'user_id': user.id, 'count': count, 'operation': 'acknowledge_all_alerts'}})
        return AcknowledgeAllAlerts(success=True, message=f"{count} alerts acknowledged", count=count)


class SendTestAlert(graphene.Mutation):
    """Send a test alert email to verify delivery works."""
    class Arguments:
        pass

    success = graphene.Boolean()
    message = graphene.String()

    @staticmethod
    @require_user
    def mutate(root: Any, info: Any) -> 'SendTestAlert':
        user = get_user_from_context(info)
        if not user:
            return SendTestAlert(success=False, message="Authentication required")

        try:
            from app.email_service import email_service
            sent = email_service.send_co2_alert(
                user_email=user.email,
                username=user.username,
                location_label="Test Location",
                co2_ppm=9999,
                severity="warning",
            )
            if sent:
                return SendTestAlert(success=True, message="Test alert email sent")
            return SendTestAlert(success=False, message="Failed to send test alert email")
        except Exception:
            logger.error("SendTestAlert failed", exc_info=True,
                         extra={'extra_context': {'user_id': user.id, 'operation': 'send_test_alert_error'}})
            return SendTestAlert(success=False, message="Failed to send test alert email")


class SensorHealthReportInput(graphene.InputObjectType):
    """Input for push-based sensor health reports from Pi devices."""
    sensor_id = graphene.Int(required=True)
    service_running = graphene.Boolean()
    service_uptime_seconds = graphene.Int()
    sensor_connected = graphene.Boolean()
    sensor_data_ready = graphene.Boolean()
    sensor_serial_number = graphene.String()
    last_co2_ppm = graphene.Int()
    last_temperature_celsius = graphene.Float()
    last_humidity_percentage = graphene.Float()
    last_reading_time = graphene.String()
    system_uptime_seconds = graphene.Int()
    disk_usage_percent = graphene.Float()
    memory_usage_percent = graphene.Float()
    cpu_temperature_celsius = graphene.Float()
    api_reachable = graphene.Boolean()
    api_response_time_ms = graphene.Int()
    consecutive_failures = graphene.Int()
    error_message = graphene.String()


class ReportSensorHealth(graphene.Mutation):
    """Accept a push-based health report from a Pi sensor device."""
    class Arguments:
        input = SensorHealthReportInput(required=True)

    success = graphene.Boolean()
    message = graphene.String()

    @staticmethod
    def mutate(root: Any, info: Any, input: 'SensorHealthReportInput') -> 'ReportSensorHealth':
        """Store a health report pushed from a sensor device."""
        sensor = Sensor.query.get(input.sensor_id)
        if not sensor:
            return ReportSensorHealth(
                success=False,
                message=f"Sensor with ID {input.sensor_id} not found"
            )

        try:
            # Parse last_reading_time if provided
            last_reading = None
            if input.last_reading_time:
                try:
                    last_reading = datetime.fromisoformat(input.last_reading_time)
                except (ValueError, TypeError):
                    pass

            report = SensorHealthReport(
                sensor_id=input.sensor_id,
                service_running=input.service_running,
                service_uptime_seconds=input.service_uptime_seconds,
                sensor_connected=input.sensor_connected,
                sensor_data_ready=input.sensor_data_ready,
                sensor_serial_number=input.sensor_serial_number,
                last_co2_ppm=input.last_co2_ppm,
                last_temperature_celsius=input.last_temperature_celsius,
                last_humidity_percentage=input.last_humidity_percentage,
                last_reading_time=last_reading,
                system_uptime_seconds=input.system_uptime_seconds,
                disk_usage_percent=input.disk_usage_percent,
                memory_usage_percent=input.memory_usage_percent,
                cpu_temperature_celsius=input.cpu_temperature_celsius,
                api_reachable=input.api_reachable,
                api_response_time_ms=input.api_response_time_ms,
                consecutive_failures=input.consecutive_failures,
                error_message=input.error_message,
            )
            db.session.add(report)

            # Update sensor health tracking
            sensor.last_health_check = datetime.utcnow()
            sensor.last_health_status = 'healthy' if input.sensor_connected else 'degraded'

            db.session.commit()

            # Publish real-time event
            try:
                from app.events import publish_sensor_health
                publish_sensor_health({
                    'sensor_id': input.sensor_id,
                    'health_status': sensor.last_health_status,
                    'report_time': report.report_time.isoformat() if report.report_time else None,
                })
            except Exception:
                pass

            logger.info(
                "Health report received",
                extra={'extra_context': {
                    'sensor_id': input.sensor_id,
                    'health_status': sensor.last_health_status,
                    'operation': 'report_sensor_health',
                }}
            )

            return ReportSensorHealth(success=True, message="Health report recorded")

        except Exception as e:
            db.session.rollback()
            logger.error(
                "Failed to store health report",
                exc_info=True,
                extra={'extra_context': {
                    'sensor_id': input.sensor_id,
                    'operation': 'report_sensor_health_error',
                }}
            )
            return ReportSensorHealth(success=False, message="Failed to store health report")


class Mutation(graphene.ObjectType):
    create_sensor_reading = CreateSensorReading.Field()
    register_user = RegisterUser.Field()
    login_user = LoginUser.Field()
    verify_email = VerifyEmail.Field()
    request_password_reset = RequestPasswordReset.Field()
    reset_password = ResetPassword.Field()
    logout_user = LogoutUser.Field()
    update_profile = UpdateProfile.Field()
    change_password = ChangePassword.Field()
    batch_update_ring_devices = BatchUpdateRingDevices.Field()

    # Location Management
    create_location = CreateLocation.Field()
    update_location = UpdateLocation.Field()
    delete_location = DeleteLocation.Field()

    # Sensor Management
    create_sensor = CreateSensor.Field()
    update_sensor = UpdateSensor.Field()
    delete_sensor = DeleteSensor.Field()
    toggle_sensor_active = ToggleSensorActive.Field()

    # Sensor Health Monitoring
    ping_sensor = PingSensor.Field()
    update_sensor_network = UpdateSensorNetwork.Field()

    # Sensor Calibration
    calibrate_sensor_frc = CalibrateSensorFRC.Field()
    set_sensor_asc = SetSensorASC.Field()
    set_sensor_temperature_offset = SetSensorTemperatureOffset.Field()
    factory_reset_sensor = FactoryResetSensor.Field()
    get_sensor_calibration_status = GetSensorCalibrationStatus.Field()

    # Sensor-Location Assignment
    assign_sensor_to_location = AssignSensorToLocation.Field()
    move_sensor_to_location = MoveSensorToLocation.Field()
    remove_sensor_from_location = RemoveSensorFromLocation.Field()

    # Dashboard Layouts
    create_dashboard_layout = CreateDashboardLayout.Field()
    update_dashboard_layout = UpdateDashboardLayout.Field()
    delete_dashboard_layout = DeleteDashboardLayout.Field()
    set_last_used_layout = SetLastUsedLayout.Field()
    duplicate_dashboard_layout = DuplicateDashboardLayout.Field()

    # Alert System
    upsert_alert_threshold = UpsertAlertThreshold.Field()
    delete_alert_threshold = DeleteAlertThreshold.Field()
    acknowledge_alert = AcknowledgeAlert.Field()
    acknowledge_all_alerts = AcknowledgeAllAlerts.Field()
    send_test_alert = SendTestAlert.Field()

    # Push-based health reporting
    report_sensor_health = ReportSensorHealth.Field()

class Query(graphene.ObjectType):
    sensors = graphene.List(SensorObject)
    locations = graphene.List(LocationObject)
    sensor_locations = graphene.List(SensorLocationObject)
    sensor_readings = graphene.List(SensorReadingObject)
    # User queries
    users = graphene.List(UserObject)
    me = graphene.Field(UserObject)

    # Metrics query
    metrics = graphene.Field(MetricsObject)

    # Air quality distribution queries
    air_quality_distribution = graphene.Field(AirQualityDistribution)
    air_quality_distributions_by_period = graphene.Field(AirQualityDistributionsByPeriod)
    daily_air_quality_scores = graphene.List(
        DailyAirQualityScore,
        days=graphene.Int(default_value=365, description="Number of days to include (default 365)")
    )

    # Ring device queries
    ring_devices = graphene.List(RingDeviceObject)
    ring_device = graphene.Field(RingDeviceObject, id=graphene.Int(), device_id=graphene.String())

    sensor = graphene.Field(SensorObject, id=graphene.Int(required=True))
    location = graphene.Field(LocationObject, id=graphene.Int(required=True))
    user = graphene.Field(UserObject, id=graphene.Int(required=True))

    # Dashboard layout queries
    dashboard_layouts = graphene.List(DashboardLayoutObject)
    dashboard_layout = graphene.Field(DashboardLayoutObject, id=graphene.ID(required=True))
    last_used_dashboard_layout = graphene.Field(DashboardLayoutObject)

    # Sensor health monitoring queries
    sensor_health = graphene.Field(
        SensorHealthObject,
        sensor_id=graphene.Int(required=True),
        description="Get health status for a specific sensor"
    )
    all_sensor_health = graphene.List(
        SensorHealthObject,
        description="Get health status for all sensors"
    )
    sensor_health_reports = graphene.List(
        SensorHealthReportObject,
        sensor_id=graphene.Int(required=True),
        limit=graphene.Int(default_value=10),
        description="Get recent health reports for a sensor"
    )

    # Alert system queries
    alert_thresholds = graphene.List(
        AlertThresholdObject,
        description="Get current user's alert thresholds"
    )
    alert_history = graphene.List(
        AlertHistoryObject,
        limit=graphene.Int(default_value=50),
        offset=graphene.Int(default_value=0),
        description="Get paginated alert history for current user"
    )
    unacknowledged_alert_count = graphene.Int(
        description="Count of unacknowledged alerts for current user"
    )

    def resolve_sensors(self, info: Any) -> List[Sensor]:
        """Get all sensors with optimized loading.
        
        Loads basic sensor info and current locations. Individual resolvers
        handle readings data when specifically requested to avoid over-fetching.
        """
        # Light query - only load basic sensor info and current locations
        # Individual resolvers will handle readings data when actually requested
        return Sensor.query.options(
            selectinload(Sensor.sensor_locations).selectinload(SensorLocation.location)
        ).all()

    def resolve_locations(self, info: Any) -> List[Location]:
        """Get all locations with their associated sensors."""
        return Location.query.options(
            selectinload(Location.sensor_locations).selectinload(SensorLocation.sensor)
        ).all()

    def resolve_sensor_locations(self, info: Any) -> List[SensorLocation]:
        return SensorLocation.query.options(
            joinedload(SensorLocation.sensor),
            joinedload(SensorLocation.location)
        ).all()

    def resolve_sensor_readings(self, info: Any) -> List[SensorReadingModel]:
        """Get recent sensor readings with all measurement data.
        
        Limited to 1000 most recent readings with eager loading for performance.
        """
        return SensorReadingModel.query.options(
            joinedload(SensorReadingModel.sensor).selectinload(Sensor.sensor_locations).selectinload(SensorLocation.location),
            joinedload(SensorReadingModel.humidity_reading),
            joinedload(SensorReadingModel.temperature_reading),
            joinedload(SensorReadingModel.co2_reading)
        ).order_by(desc(SensorReadingModel.reading_time)).limit(1000).all()

    def resolve_sensor(self, info: Any, id: int) -> Optional[Sensor]:
        return Sensor.query.options(
            selectinload(Sensor.readings).selectinload(SensorReadingModel.humidity_reading),
            selectinload(Sensor.readings).selectinload(SensorReadingModel.temperature_reading),
            selectinload(Sensor.readings).selectinload(SensorReadingModel.co2_reading),
            selectinload(Sensor.sensor_locations).selectinload(SensorLocation.location)
        ).get(id)

    def resolve_location(self, info: Any, id: int) -> Optional[Location]:
        return Location.query.options(
            selectinload(Location.sensor_locations).selectinload(SensorLocation.sensor)
        ).get(id)
    
    @require_admin
    def resolve_users(self, info: Any) -> List[User]:
        """Get all users (admin only)."""
        return User.query.all()
    
    def resolve_me(self, info: Any) -> Optional[User]:
        """Get current authenticated user."""
        return get_user_from_context(info)
    
    @require_admin
    def resolve_user(self, info: Any, id: int) -> Optional[User]:
        """Get user by ID (admin only)."""
        return User.query.get(id)

    @require_user
    def resolve_dashboard_layouts(self, info: Any) -> List[DashboardLayout]:
        """Get all dashboard layouts for the authenticated user."""
        user = get_user_from_context(info)
        if not user:
            return []
        return DashboardLayout.query.filter_by(
            user_id=user.id
        ).order_by(desc(DashboardLayout.updated_at)).all()

    @require_user
    def resolve_dashboard_layout(self, info: Any, id: str) -> Optional[DashboardLayout]:
        """Get a specific dashboard layout by ID."""
        user = get_user_from_context(info)
        if not user:
            return None
        return DashboardLayout.query.filter_by(
            id=int(id),
            user_id=user.id
        ).first()

    @require_user
    def resolve_last_used_dashboard_layout(self, info: Any) -> Optional[DashboardLayout]:
        """Get the last used dashboard layout for the authenticated user."""
        user = get_user_from_context(info)
        if not user:
            return None
        return DashboardLayout.query.filter_by(
            user_id=user.id,
            is_last_used=True
        ).first()

    def resolve_ring_devices(self, info: Any) -> List[RingDevice]:
        """Get all Ring alarm devices."""
        return RingDevice.query.filter_by(is_active=True).order_by(RingDevice.name).all()

    def resolve_ring_device(
        self,
        info: Any,
        id: Optional[int] = None,
        device_id: Optional[str] = None
    ) -> Optional[RingDevice]:
        """Get a Ring device by ID or device_id."""
        if id:
            return RingDevice.query.get(id)
        elif device_id:
            return RingDevice.query.filter_by(device_id=device_id).first()
        return None

    def resolve_metrics(self, info: Any) -> Optional[MetricsObject]:
        """Get dashboard metrics including running averages and all-time extremes.

        Computes:
        - 1-day and 30-day running averages for CO2 and temperature
        - All-time highest and lowest values for both metrics

        Uses optimized aggregation queries to minimize database load.
        """
        from sqlalchemy import func

        # Calculate time boundaries
        now = datetime.utcnow()
        one_day_ago = now - timedelta(days=1)
        thirty_days_ago = now - timedelta(days=30)

        try:
            # CO2 metrics - 1-day average
            co2_1day = db.session.query(
                func.avg(CO2Reading.co2_ppm)
            ).join(SensorReadingModel).filter(
                SensorReadingModel.reading_time >= one_day_ago
            ).scalar()

            # CO2 metrics - 30-day average
            co2_30day = db.session.query(
                func.avg(CO2Reading.co2_ppm)
            ).join(SensorReadingModel).filter(
                SensorReadingModel.reading_time >= thirty_days_ago
            ).scalar()

            # CO2 all-time extremes
            co2_max = db.session.query(
                func.max(CO2Reading.co2_ppm)
            ).scalar()

            co2_min = db.session.query(
                func.min(CO2Reading.co2_ppm)
            ).scalar()

            # Temperature metrics - 1-day average
            temp_1day = db.session.query(
                func.avg(TemperatureReading.temperature_celsius)
            ).join(SensorReadingModel).filter(
                SensorReadingModel.reading_time >= one_day_ago
            ).scalar()

            # Temperature metrics - 30-day average
            temp_30day = db.session.query(
                func.avg(TemperatureReading.temperature_celsius)
            ).join(SensorReadingModel).filter(
                SensorReadingModel.reading_time >= thirty_days_ago
            ).scalar()

            # Temperature all-time extremes
            temp_max = db.session.query(
                func.max(TemperatureReading.temperature_celsius)
            ).scalar()

            temp_min = db.session.query(
                func.min(TemperatureReading.temperature_celsius)
            ).scalar()

            logger.info(
                "Metrics calculated successfully",
                extra={
                    'extra_context': {
                        'operation': 'resolve_metrics_success',
                        'has_co2_data': co2_1day is not None,
                        'has_temp_data': temp_1day is not None
                    }
                }
            )

            return MetricsObject(
                co2_1day_avg=float(co2_1day) if co2_1day is not None else None,
                co2_30day_avg=float(co2_30day) if co2_30day is not None else None,
                temp_1day_avg=float(temp_1day) if temp_1day is not None else None,
                temp_30day_avg=float(temp_30day) if temp_30day is not None else None,
                temp_highest_all_time=float(temp_max) if temp_max is not None else None,
                temp_lowest_all_time=float(temp_min) if temp_min is not None else None,
                co2_highest_all_time=int(co2_max) if co2_max is not None else None,
                co2_lowest_all_time=int(co2_min) if co2_min is not None else None
            )

        except Exception as e:
            logger.error(
                "Failed to calculate metrics",
                exc_info=True,
                extra={
                    'extra_context': {
                        'operation': 'resolve_metrics_error',
                        'error_type': type(e).__name__
                    }
                }
            )
            return None

    def resolve_air_quality_distribution(self, info: Any) -> Optional[AirQualityDistribution]:
        """Calculate air quality condition distribution across all current sensor readings.

        Analyzes sensor readings from the currently active date range (based on context filters)
        and returns the count of readings in each condition category (good, moderate, poor).

        Business logic for condition assessment is handled server-side using centralized
        threshold definitions.
        """
        from app.air_quality import calculate_distribution

        try:
            # Get filtered readings (respects the same filters as the dashboard)
            # Use the context's sensor data criteria if available
            context = info.context

            # Default to last 90 days if no specific filters
            query = SensorReadingModel.query.options(
                joinedload(SensorReadingModel.co2_reading),
                joinedload(SensorReadingModel.temperature_reading),
                joinedload(SensorReadingModel.humidity_reading)
            )

            # Apply default date filter (last 90 days)
            ninety_days_ago = datetime.utcnow() - timedelta(days=90)
            query = query.filter(SensorReadingModel.reading_time >= ninety_days_ago)

            # Get readings
            readings = query.all()

            if not readings:
                return AirQualityDistribution(
                    good=0,
                    moderate=0,
                    poor=0,
                    total=0
                )

            # Calculate distribution using business logic
            distribution = calculate_distribution(readings)

            logger.info(
                "Air quality distribution calculated",
                extra={
                    'extra_context': {
                        'operation': 'resolve_air_quality_distribution',
                        'total_readings': distribution['total'],
                        'good_count': distribution['good'],
                        'moderate_count': distribution['moderate'],
                        'poor_count': distribution['poor']
                    }
                }
            )

            return AirQualityDistribution(
                good=distribution['good'],
                moderate=distribution['moderate'],
                poor=distribution['poor'],
                total=distribution['total']
            )

        except Exception as e:
            logger.error(
                "Failed to calculate air quality distribution",
                exc_info=True,
                extra={
                    'extra_context': {
                        'operation': 'resolve_air_quality_distribution_error',
                        'error_type': type(e).__name__
                    }
                }
            )
            return None

    def resolve_air_quality_distributions_by_period(self, info: Any) -> Optional[AirQualityDistributionsByPeriod]:
        """Calculate air quality distributions for multiple time periods.

        Returns distributions for:
        - Last 24 hours (1 day)
        - Last 30 days
        - All time (all historical data)

        Business logic for condition assessment is handled server-side using centralized
        threshold definitions and weighted scoring.
        """
        from app.air_quality import calculate_distribution

        try:
            # Calculate time boundaries
            now = datetime.utcnow()
            one_day_ago = now - timedelta(days=1)
            thirty_days_ago = now - timedelta(days=30)

            # Base query with eager loading
            base_query = SensorReadingModel.query.options(
                joinedload(SensorReadingModel.co2_reading),
                joinedload(SensorReadingModel.temperature_reading),
                joinedload(SensorReadingModel.humidity_reading)
            )

            # Get readings for each time period
            one_day_readings = base_query.filter(
                SensorReadingModel.reading_time >= one_day_ago
            ).all()

            thirty_day_readings = base_query.filter(
                SensorReadingModel.reading_time >= thirty_days_ago
            ).all()

            all_time_readings = base_query.all()

            # Calculate distributions
            one_day_dist = calculate_distribution(one_day_readings)
            thirty_day_dist = calculate_distribution(thirty_day_readings)
            all_time_dist = calculate_distribution(all_time_readings)

            logger.info(
                "Air quality distributions by period calculated",
                extra={
                    'extra_context': {
                        'operation': 'resolve_air_quality_distributions_by_period',
                        'one_day_total': one_day_dist['total'],
                        'thirty_day_total': thirty_day_dist['total'],
                        'all_time_total': all_time_dist['total']
                    }
                }
            )

            return AirQualityDistributionsByPeriod(
                one_day=AirQualityDistribution(
                    good=one_day_dist['good'],
                    moderate=one_day_dist['moderate'],
                    poor=one_day_dist['poor'],
                    total=one_day_dist['total']
                ),
                thirty_days=AirQualityDistribution(
                    good=thirty_day_dist['good'],
                    moderate=thirty_day_dist['moderate'],
                    poor=thirty_day_dist['poor'],
                    total=thirty_day_dist['total']
                ),
                all_time=AirQualityDistribution(
                    good=all_time_dist['good'],
                    moderate=all_time_dist['moderate'],
                    poor=all_time_dist['poor'],
                    total=all_time_dist['total']
                )
            )

        except Exception as e:
            logger.error(
                "Failed to calculate air quality distributions by period",
                exc_info=True,
                extra={
                    'extra_context': {
                        'operation': 'resolve_air_quality_distributions_by_period_error',
                        'error_type': type(e).__name__
                    }
                }
            )
            return None

    def resolve_daily_air_quality_scores(self, info: Any, days: int = 365) -> Optional[List[DailyAirQualityScore]]:
        """Calculate daily air quality scores for heatmap visualization.

        Returns a list of daily scores for the specified number of days,
        with each score representing the average air quality for that day.
        Score ranges from 0-100 where 100 is best air quality.
        """
        from app.air_quality import calculate_daily_scores

        try:
            # Get readings for the requested time period
            start_date = datetime.utcnow() - timedelta(days=days)
            query = SensorReadingModel.query.options(
                joinedload(SensorReadingModel.co2_reading),
                joinedload(SensorReadingModel.temperature_reading),
                joinedload(SensorReadingModel.humidity_reading)
            ).filter(SensorReadingModel.reading_time >= start_date)

            readings = query.all()

            # Calculate daily scores
            daily_scores = calculate_daily_scores(readings, days)

            logger.info(
                "Daily air quality scores calculated",
                extra={
                    'extra_context': {
                        'operation': 'resolve_daily_air_quality_scores',
                        'days_requested': days,
                        'total_readings': len(readings),
                        'days_with_data': sum(1 for d in daily_scores if d['score'] is not None)
                    }
                }
            )

            return [
                DailyAirQualityScore(
                    date=score['date'],
                    score=score['score'],
                    reading_count=score['readingCount']
                )
                for score in daily_scores
            ]

        except Exception as e:
            logger.error(
                "Failed to calculate daily air quality scores",
                exc_info=True,
                extra={
                    'extra_context': {
                        'operation': 'resolve_daily_air_quality_scores_error',
                        'error_type': type(e).__name__
                    }
                }
            )
            return None

    filtered_sensor_readings = graphene.List(SensorReadingObject, filters=SensorDataFilterInput(required=True))

    @cached_query(ttl=60)  # Cache for 60 seconds - sensor data updates every ~10 minutes
    def resolve_filtered_sensor_readings(self, info: Any, filters: SensorDataFilterInput) -> List[SensorReadingModel]:
        """Get sensor readings filtered by various criteria.

        Supports filtering by date range, measurement values, sensors, locations,
        with pagination and ordering. Uses optimized queries to prevent N+1 issues.
        Results are cached for 60 seconds to improve performance for dashboard widgets.
        """
        # Start with optimized eager loading
        # Always load measurement readings (lightweight one-to-one joins)
        # Always load sensor with sensor_locations to prevent N+1 queries in resolve_location
        query = SensorReadingModel.query.options(
            joinedload(SensorReadingModel.humidity_reading),
            joinedload(SensorReadingModel.temperature_reading),
            joinedload(SensorReadingModel.co2_reading),
            # Always load sensor_locations to prevent N+1 queries when resolving location
            joinedload(SensorReadingModel.sensor).selectinload(Sensor.sensor_locations).joinedload(SensorLocation.location)
        )

        # Handle date filtering - convert timezone-aware datetimes to naive UTC
        # The database stores naive datetimes (in UTC), so we must strip tzinfo for comparison
        if filters.start_date:
            start_date = filters.start_date
            if hasattr(start_date, 'tzinfo') and start_date.tzinfo is not None:
                start_date = start_date.replace(tzinfo=None)
            query = query.filter(SensorReadingModel.reading_time >= start_date)
        if filters.end_date:
            end_date = filters.end_date
            if hasattr(end_date, 'tzinfo') and end_date.tzinfo is not None:
                end_date = end_date.replace(tzinfo=None)
            query = query.filter(SensorReadingModel.reading_time <= end_date)
        # Optimized joins - combine measurement filters into single query with outer joins
        measurement_filters = []
        
        # CO2 filtering
        if filters.min_co2_ppm is not None or filters.max_co2_ppm is not None:
            query = query.outerjoin(CO2Reading)
            if filters.min_co2_ppm is not None:
                measurement_filters.append(CO2Reading.co2_ppm >= filters.min_co2_ppm)
            if filters.max_co2_ppm is not None:
                measurement_filters.append(CO2Reading.co2_ppm <= filters.max_co2_ppm)

        # Temperature filtering
        if filters.min_temperature_celsius is not None or filters.max_temperature_celsius is not None:
            query = query.outerjoin(TemperatureReading)
            if filters.min_temperature_celsius is not None:
                measurement_filters.append(TemperatureReading.temperature_celsius >= filters.min_temperature_celsius)
            if filters.max_temperature_celsius is not None:
                measurement_filters.append(TemperatureReading.temperature_celsius <= filters.max_temperature_celsius)

        # Humidity filtering
        if filters.min_humidity_percentage is not None or filters.max_humidity_percentage is not None:
            query = query.outerjoin(HumidityReading)
            if filters.min_humidity_percentage is not None:
                measurement_filters.append(HumidityReading.humidity_percentage >= filters.min_humidity_percentage)
            if filters.max_humidity_percentage is not None:
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

        # Apply pagination - only apply limit if explicitly specified
        # Charts need all data points within their time range, not an arbitrary limit
        if hasattr(filters, 'limit') and filters.limit is not None:
            query = query.limit(filters.limit)

        if hasattr(filters, 'offset') and filters.offset is not None:
            query = query.offset(filters.offset)

        return query.all()

    def resolve_sensor_health(self, info: Any, sensor_id: int) -> Optional[Dict[str, Any]]:
        """Get health status for a specific sensor."""
        sensor = Sensor.query.get(sensor_id)
        if not sensor:
            return None

        return _build_sensor_health_object(sensor)

    def resolve_all_sensor_health(self, info: Any) -> List[Dict[str, Any]]:
        """Get health status for all sensors."""
        sensors = Sensor.query.all()
        return [_build_sensor_health_object(sensor) for sensor in sensors]

    def resolve_sensor_health_reports(
        self, info: Any, sensor_id: int, limit: int = 10
    ) -> List[SensorHealthReport]:
        """Get recent health reports for a sensor."""
        return SensorHealthReport.query.filter_by(
            sensor_id=sensor_id
        ).order_by(desc(SensorHealthReport.report_time)).limit(limit).all()

    def resolve_alert_thresholds(self, info: Any) -> List[AlertThreshold]:
        """Get current user's alert thresholds."""
        user = get_user_from_context(info)
        if not user:
            return []
        return AlertThreshold.query.filter_by(user_id=user.id).all()

    def resolve_alert_history(self, info: Any, limit: int = 50, offset: int = 0) -> List[AlertHistory]:
        """Get paginated alert history for current user."""
        user = get_user_from_context(info)
        if not user:
            return []
        return AlertHistory.query.filter_by(
            user_id=user.id
        ).order_by(desc(AlertHistory.created_at)).offset(offset).limit(limit).all()

    def resolve_unacknowledged_alert_count(self, info: Any) -> int:
        """Count unacknowledged alerts for the current user."""
        user = get_user_from_context(info)
        if not user:
            return 0
        return AlertHistory.query.filter_by(user_id=user.id, acknowledged=False).count()


def _build_sensor_health_object(sensor: Sensor) -> Dict[str, Any]:
    """Build a SensorHealthObject from a Sensor model."""
    # Get latest reading for this sensor
    latest_reading = SensorReadingModel.query.filter_by(
        sensor_id=sensor.id
    ).options(
        joinedload(SensorReadingModel.co2_reading),
        joinedload(SensorReadingModel.temperature_reading),
        joinedload(SensorReadingModel.humidity_reading)
    ).order_by(desc(SensorReadingModel.reading_time)).first()

    # Calculate minutes since last reading
    minutes_since = None
    if sensor.last_reading_time:
        delta = datetime.utcnow() - sensor.last_reading_time
        minutes_since = int(delta.total_seconds() / 60)

    # Get latest health report
    latest_report = SensorHealthReport.query.filter_by(
        sensor_id=sensor.id
    ).order_by(desc(SensorHealthReport.report_time)).first()

    return {
        'sensor_id': sensor.id,
        'sensor_name': sensor.name,
        'health_status': sensor.health_status,
        'is_active': sensor.is_active,
        'last_reading_time': sensor.last_reading_time,
        'last_successful_reading_time': sensor.last_successful_reading_time,
        'minutes_since_last_reading': minutes_since,
        'consecutive_failures': sensor.consecutive_failures or 0,
        'total_readings': sensor.total_readings or 0,
        'total_failures': sensor.total_failures or 0,
        'success_rate': sensor.success_rate,
        'ip_address': sensor.ip_address,
        'health_check_port': sensor.health_check_port,
        'is_reachable': None,  # Will be set by ping
        'latest_co2_ppm': latest_reading.co2_reading.co2_ppm if latest_reading and latest_reading.co2_reading else None,
        'latest_temperature_celsius': latest_reading.temperature_reading.temperature_celsius if latest_reading and latest_reading.temperature_reading else None,
        'latest_humidity_percentage': latest_reading.humidity_reading.humidity_percentage if latest_reading and latest_reading.humidity_reading else None,
        'last_health_check': sensor.last_health_check,
        'last_health_report': latest_report,
    }


from app.graphql_security import SecureGraphQLSchema

schema = SecureGraphQLSchema(
    query=Query,
    mutation=Mutation,
    types=[
        CreateSensorReadingInput,
        RegisterInput,
        LoginInput,
        EmailVerificationInput,
        PasswordResetRequestInput,
        PasswordResetInput,
        LogoutInput,
        # Location Management
        CreateLocationInput,
        UpdateLocationInput,
        # Sensor Management
        CreateSensorInput,
        UpdateSensorInput,
        # Sensor-Location Assignment
        AssignSensorLocationInput,
        MoveSensorInput,
        # Alert System
        UpsertAlertThresholdInput,
        AlertThresholdObject,
        AlertHistoryObject,
    ],
    max_depth=8,
    max_complexity=150,
    timeout_seconds=30,
    enable_security_logging=True
)
