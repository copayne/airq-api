import graphene
from graphene_sqlalchemy import SQLAlchemyObjectType
from typing import Optional, List, Any, Dict
from app.models import CO2Reading, ErrorLog, HumidityReading, Location, Sensor, SensorLocation, SensorReading as SensorReadingModel, TemperatureReading, User, RingSnapshot, Camera, RingDevice
from app import db
from sqlalchemy import and_, or_, desc, asc
from sqlalchemy.orm import joinedload, selectinload
from datetime import datetime, timedelta
import logging
from app.auth import require_admin, require_user, get_user_from_context

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
        
        Uses optimized database query to find the location based on reading timestamp.
        """
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
            sensor_reading = SensorReadingModel(
                sensor_id=input.sensor_id
            )
            
            db.session.add(sensor_reading)
            db.session.flush()  # This assigns an ID without committing
            
            # Create the specific readings with validated data
            if input.humidity_percentage is not None:
                humidity_reading = HumidityReading(
                    reading_id=sensor_reading.id, 
                    humidity_percentage=input.humidity_percentage
                )
                db.session.add(humidity_reading)

            if input.temperature_celsius is not None:
                temperature_reading = TemperatureReading(
                    reading_id=sensor_reading.id, 
                    temperature_celsius=input.temperature_celsius
                )
                db.session.add(temperature_reading)

            if input.co2_ppm is not None:
                co2_reading = CO2Reading(
                    reading_id=sensor_reading.id, 
                    co2_ppm=input.co2_ppm
                )
                db.session.add(co2_reading)
            
            db.session.commit()
            
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

class ErrorLogObject(SQLAlchemyObjectType):
    class Meta:
        model = ErrorLog

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
            validation_result = validator.validate_registration_input(
                username="dummy",  # Not used for password validation
                email="dummy@example.com",  # Not used for password validation
                password=input.new_password
            )
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


class CameraObject(SQLAlchemyObjectType):
    """GraphQL object for Ring cameras."""
    class Meta:
        model = Camera

    latest_snapshot = graphene.Field(lambda: RingSnapshotObject)

    def resolve_latest_snapshot(self, info: Any) -> Optional[RingSnapshot]:
        """Get the most recent snapshot for this camera."""
        return self.snapshots.order_by(desc(RingSnapshot.capture_timestamp)).first()


class RingSnapshotObject(SQLAlchemyObjectType):
    """GraphQL object for Ring camera snapshots."""
    class Meta:
        model = RingSnapshot

    image_url = graphene.String()
    camera = graphene.Field(CameraObject)

    def resolve_image_url(self, info: Any) -> str:
        """Generate URL for accessing the snapshot image."""
        return f"/api/ring-snapshots/{self.id}"

    def resolve_camera(self, info: Any) -> Optional[Camera]:
        """Get the camera for this snapshot."""
        return self.camera


class RingDeviceObject(SQLAlchemyObjectType):
    """GraphQL object for Ring alarm devices (contact sensors, motion detectors, etc.)."""
    class Meta:
        model = RingDevice


class CreateRingSnapshotInput(graphene.InputObjectType):
    """Input for manually creating a ring snapshot record."""
    camera_id = graphene.Int(required=True)
    image_path = graphene.String(required=True)
    capture_timestamp = graphene.DateTime(required=True)
    file_size = graphene.Int()


class CreateRingSnapshot(graphene.Mutation):
    """Create a new Ring snapshot record."""
    class Arguments:
        input = CreateRingSnapshotInput(required=True)

    snapshot = graphene.Field(RingSnapshotObject)
    success = graphene.Boolean()
    message = graphene.String()

    @staticmethod
    def mutate(root: Any, info: Any, input: CreateRingSnapshotInput) -> 'CreateRingSnapshot':
        """Create a new Ring snapshot database record."""
        try:
            snapshot = RingSnapshot(
                camera_id=input.camera_id,
                image_path=input.image_path,
                capture_timestamp=input.capture_timestamp,
                file_size=input.file_size
            )

            db.session.add(snapshot)
            db.session.commit()

            logger.info(
                "Ring snapshot created successfully",
                extra={
                    'extra_context': {
                        'camera_id': input.camera_id,
                        'snapshot_id': snapshot.id,
                        'operation': 'create_ring_snapshot_success'
                    }
                }
            )

            return CreateRingSnapshot(
                snapshot=snapshot,
                success=True,
                message="Snapshot created successfully"
            )

        except Exception as e:
            db.session.rollback()
            logger.error(
                "Failed to create Ring snapshot",
                exc_info=True,
                extra={
                    'extra_context': {
                        'device_id': input.device_id,
                        'operation': 'create_ring_snapshot_error'
                    }
                }
            )

            return CreateRingSnapshot(
                snapshot=None,
                success=False,
                message="Failed to create snapshot record"
            )


class CaptureRingSnapshot(graphene.Mutation):
    """Capture a new Ring snapshot synchronously."""
    class Arguments:
        camera_id = graphene.Int()

    snapshot = graphene.Field(RingSnapshotObject)
    success = graphene.Boolean()
    message = graphene.String()

    @staticmethod
    def mutate(root: Any, info: Any, camera_id: Optional[int] = None) -> 'CaptureRingSnapshot':
        """Capture a Ring snapshot by running the capture script synchronously."""
        import subprocess
        import os
        import sys

        try:
            # Look up camera if camera_id provided, otherwise use default
            camera = None
            if camera_id:
                camera = Camera.query.get(camera_id)
                if not camera:
                    return CaptureRingSnapshot(
                        snapshot=None,
                        success=False,
                        message=f"Camera with ID {camera_id} not found"
                    )

            script_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                'scripts',
                'capture_ring_snapshot.py'
            )

            if not os.path.exists(script_path):
                return CaptureRingSnapshot(
                    snapshot=None,
                    success=False,
                    message="Capture script not found"
                )

            logger.info(
                "Starting Ring snapshot capture",
                extra={
                    'extra_context': {
                        'camera_id': camera_id,
                        'device_id': camera.device_id if camera else None,
                        'operation': 'capture_ring_snapshot_start'
                    }
                }
            )

            # Build command with optional device_id argument
            cmd = [sys.executable, script_path]
            if camera:
                cmd.extend(['--device-id', camera.device_id])

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60
            )

            if result.returncode != 0:
                logger.error(
                    "Capture script failed",
                    extra={
                        'extra_context': {
                            'return_code': result.returncode,
                            'stderr': result.stderr,
                            'operation': 'capture_ring_snapshot_script_error'
                        }
                    }
                )
                return CaptureRingSnapshot(
                    snapshot=None,
                    success=False,
                    message=f"Capture failed: {result.stderr}"
                )

            latest_snapshot = RingSnapshot.query.order_by(
                desc(RingSnapshot.created_at)
            ).first()

            if latest_snapshot:
                logger.info(
                    "Ring snapshot captured successfully",
                    extra={
                        'extra_context': {
                            'snapshot_id': latest_snapshot.id,
                            'device_id': latest_snapshot.device_id,
                            'operation': 'capture_ring_snapshot_success'
                        }
                    }
                )
                return CaptureRingSnapshot(
                    snapshot=latest_snapshot,
                    success=True,
                    message="Snapshot captured successfully"
                )
            else:
                return CaptureRingSnapshot(
                    snapshot=None,
                    success=False,
                    message="Capture completed but snapshot not found in database"
                )

        except subprocess.TimeoutExpired:
            logger.error(
                "Capture script timeout",
                extra={'extra_context': {'operation': 'capture_ring_snapshot_timeout'}}
            )
            return CaptureRingSnapshot(
                snapshot=None,
                success=False,
                message="Capture timeout after 60 seconds"
            )
        except Exception as e:
            logger.error(
                "Failed to capture Ring snapshot",
                exc_info=True,
                extra={
                    'extra_context': {
                        'error_type': type(e).__name__,
                        'operation': 'capture_ring_snapshot_error'
                    }
                }
            )
            return CaptureRingSnapshot(
                snapshot=None,
                success=False,
                message=f"Capture failed: {str(e)}"
            )


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


class Mutation(graphene.ObjectType):
    create_sensor_reading = CreateSensorReading.Field()
    register_user = RegisterUser.Field()
    login_user = LoginUser.Field()
    verify_email = VerifyEmail.Field()
    request_password_reset = RequestPasswordReset.Field()
    reset_password = ResetPassword.Field()
    logout_user = LogoutUser.Field()
    create_ring_snapshot = CreateRingSnapshot.Field()
    capture_ring_snapshot = CaptureRingSnapshot.Field()
    batch_update_ring_devices = BatchUpdateRingDevices.Field()

class Query(graphene.ObjectType):
    sensors = graphene.List(SensorObject)
    locations = graphene.List(LocationObject)
    sensor_locations = graphene.List(SensorLocationObject)
    sensor_readings = graphene.List(SensorReadingObject)
    humidity_readings = graphene.List(HumidityReadingObject)
    temperature_readings = graphene.List(TemperatureReadingObject)
    co2_readings = graphene.List(CO2ReadingObject)
    error_logs = graphene.List(ErrorLogObject)

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

    # Camera queries
    cameras = graphene.List(CameraObject)
    camera = graphene.Field(CameraObject, id=graphene.Int(), device_id=graphene.String())

    # Ring snapshot queries
    ring_snapshots = graphene.List(
        RingSnapshotObject,
        camera_id=graphene.Int(),
        limit=graphene.Int()
    )
    latest_ring_snapshot = graphene.Field(
        RingSnapshotObject,
        camera_id=graphene.Int()
    )

    # Ring device queries
    ring_devices = graphene.List(RingDeviceObject)
    ring_device = graphene.Field(RingDeviceObject, id=graphene.Int(), device_id=graphene.String())

    sensor = graphene.Field(SensorObject, id=graphene.Int(required=True))
    location = graphene.Field(LocationObject, id=graphene.Int(required=True))
    user = graphene.Field(UserObject, id=graphene.Int(required=True))

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

    def resolve_humidity_readings(self, info: Any) -> List[HumidityReading]:
        return HumidityReading.query.limit(1000).all()

    def resolve_temperature_readings(self, info: Any) -> List[TemperatureReading]:
        return TemperatureReading.query.limit(1000).all()

    def resolve_co2_readings(self, info: Any) -> List[CO2Reading]:
        return CO2Reading.query.limit(1000).all()

    def resolve_error_logs(self, info: Any) -> List[ErrorLog]:
        return ErrorLog.query.order_by(desc(ErrorLog.created_at)).limit(1000).all()

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

    def resolve_cameras(self, info: Any) -> List[Camera]:
        """Get all cameras."""
        return Camera.query.all()

    def resolve_camera(
        self,
        info: Any,
        id: Optional[int] = None,
        device_id: Optional[str] = None
    ) -> Optional[Camera]:
        """Get a camera by ID or device_id."""
        if id:
            return Camera.query.get(id)
        elif device_id:
            return Camera.query.filter_by(device_id=device_id).first()
        return None

    def resolve_ring_snapshots(
        self,
        info: Any,
        camera_id: Optional[int] = None,
        limit: Optional[int] = 100
    ) -> List[RingSnapshot]:
        """Get Ring camera snapshots with optional filtering."""
        query = RingSnapshot.query

        if camera_id:
            query = query.filter_by(camera_id=camera_id)

        query = query.order_by(desc(RingSnapshot.capture_timestamp))

        if limit:
            query = query.limit(limit)

        return query.all()

    def resolve_latest_ring_snapshot(
        self,
        info: Any,
        camera_id: Optional[int] = None
    ) -> Optional[RingSnapshot]:
        """Get the most recent Ring camera snapshot."""
        query = RingSnapshot.query

        if camera_id:
            query = query.filter_by(camera_id=camera_id)

        return query.order_by(desc(RingSnapshot.capture_timestamp)).first()

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

    def resolve_filtered_sensor_readings(self, info: Any, filters: SensorDataFilterInput) -> List[SensorReadingModel]:
        """Get sensor readings filtered by various criteria.
        
        Supports filtering by date range, measurement values, sensors, locations,
        with pagination and ordering. Uses optimized queries to prevent N+1 issues.
        """
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
    types=[
        CreateSensorReadingInput,
        RegisterInput,
        LoginInput,
        EmailVerificationInput,
        PasswordResetRequestInput,
        PasswordResetInput,
        LogoutInput,
        CreateRingSnapshotInput
    ],
    max_depth=8,
    max_complexity=150,
    timeout_seconds=30,
    enable_security_logging=True
)
