"""
Data validation utilities for sensor readings and API inputs.

Provides comprehensive validation for sensor data including range checks,
type validation, and sensor existence verification.
"""

from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
import math
from app.models import Sensor


@dataclass
class ValidationError:
    """Represents a single validation error with field context."""
    field: str
    message: str
    code: str
    value: Any = None


@dataclass
class ValidationResult:
    """Result of validation operation."""
    is_valid: bool
    errors: List[ValidationError]
    
    @property
    def error_messages(self) -> List[str]:
        """Get list of error messages."""
        return [error.message for error in self.errors]
    
    @property
    def errors_by_field(self) -> Dict[str, List[ValidationError]]:
        """Group errors by field name."""
        grouped = {}
        for error in self.errors:
            if error.field not in grouped:
                grouped[error.field] = []
            grouped[error.field].append(error)
        return grouped


class SensorDataValidator:
    """Validates sensor reading data against reasonable ranges and constraints."""
    
    # Reasonable ranges for air quality sensor readings
    HUMIDITY_MIN = 0.0
    HUMIDITY_MAX = 100.0
    TEMPERATURE_MIN = -40.0  # Typical sensor range minimum
    TEMPERATURE_MAX = 85.0   # Typical sensor range maximum
    CO2_MIN = 0
    CO2_MAX = 50000  # Safety limit for CO2 sensors
    
    # Precision limits
    MAX_DECIMAL_PLACES = 2
    
    def __init__(self):
        """Initialize sensor data validator."""
        self.errors = []
    
    def validate_sensor_reading_input(self, sensor_id: int, 
                                    humidity_percentage: Optional[float] = None,
                                    temperature_celsius: Optional[float] = None,
                                    co2_ppm: Optional[int] = None) -> ValidationResult:
        """
        Validate complete sensor reading input data.
        
        Args:
            sensor_id: ID of the sensor taking the reading
            humidity_percentage: Humidity reading (0-100%)
            temperature_celsius: Temperature reading (-40 to 85°C)
            co2_ppm: CO2 reading (0-50000 ppm)
            
        Returns:
            ValidationResult with validation status and any errors
        """
        self.errors = []
        
        # Validate sensor exists and is active
        self._validate_sensor_exists(sensor_id)
        
        # Validate individual sensor readings
        if humidity_percentage is not None:
            self._validate_humidity(humidity_percentage)
        
        if temperature_celsius is not None:
            self._validate_temperature(temperature_celsius)
        
        if co2_ppm is not None:
            self._validate_co2(co2_ppm)
        
        # Validate at least one reading is provided
        if all(reading is None for reading in [humidity_percentage, temperature_celsius, co2_ppm]):
            self.errors.append(ValidationError(
                field="readings",
                message="At least one sensor reading must be provided",
                code="MISSING_READINGS"
            ))
        
        return ValidationResult(
            is_valid=len(self.errors) == 0,
            errors=self.errors.copy()
        )
    
    def _validate_sensor_exists(self, sensor_id: int) -> None:
        """Validate that sensor exists and is active."""
        if not isinstance(sensor_id, int):
            self.errors.append(ValidationError(
                field="sensor_id",
                message="Sensor ID must be an integer",
                code="INVALID_TYPE",
                value=sensor_id
            ))
            return
        
        if sensor_id <= 0:
            self.errors.append(ValidationError(
                field="sensor_id",
                message="Sensor ID must be positive",
                code="INVALID_RANGE",
                value=sensor_id
            ))
            return
        
        # Check if sensor exists in database
        sensor = Sensor.query.get(sensor_id)
        if not sensor:
            self.errors.append(ValidationError(
                field="sensor_id",
                message=f"Sensor with ID {sensor_id} does not exist",
                code="SENSOR_NOT_FOUND",
                value=sensor_id
            ))
            return
        
        # Check if sensor is active
        if not sensor.is_active:
            self.errors.append(ValidationError(
                field="sensor_id",
                message=f"Sensor {sensor_id} is not active",
                code="SENSOR_INACTIVE",
                value=sensor_id
            ))
    
    def _validate_humidity(self, humidity: float) -> None:
        """Validate humidity reading."""
        if not self._is_valid_number(humidity):
            self.errors.append(ValidationError(
                field="humidity_percentage",
                message="Humidity must be a valid number",
                code="INVALID_NUMBER",
                value=humidity
            ))
            return
        
        if not (self.HUMIDITY_MIN <= humidity <= self.HUMIDITY_MAX):
            self.errors.append(ValidationError(
                field="humidity_percentage",
                message=f"Humidity must be between {self.HUMIDITY_MIN}% and {self.HUMIDITY_MAX}%",
                code="OUT_OF_RANGE",
                value=humidity
            ))
        
        if not self._has_valid_precision(humidity):
            self.errors.append(ValidationError(
                field="humidity_percentage",
                message=f"Humidity precision cannot exceed {self.MAX_DECIMAL_PLACES} decimal places",
                code="EXCESSIVE_PRECISION",
                value=humidity
            ))
    
    def _validate_temperature(self, temperature: float) -> None:
        """Validate temperature reading."""
        if not self._is_valid_number(temperature):
            self.errors.append(ValidationError(
                field="temperature_celsius",
                message="Temperature must be a valid number",
                code="INVALID_NUMBER",
                value=temperature
            ))
            return
        
        if not (self.TEMPERATURE_MIN <= temperature <= self.TEMPERATURE_MAX):
            self.errors.append(ValidationError(
                field="temperature_celsius",
                message=f"Temperature must be between {self.TEMPERATURE_MIN}°C and {self.TEMPERATURE_MAX}°C",
                code="OUT_OF_RANGE",
                value=temperature
            ))
        
        if not self._has_valid_precision(temperature):
            self.errors.append(ValidationError(
                field="temperature_celsius",
                message=f"Temperature precision cannot exceed {self.MAX_DECIMAL_PLACES} decimal places",
                code="EXCESSIVE_PRECISION",
                value=temperature
            ))
    
    def _validate_co2(self, co2: int) -> None:
        """Validate CO2 reading."""
        if not isinstance(co2, (int, float)):
            self.errors.append(ValidationError(
                field="co2_ppm",
                message="CO2 reading must be a number",
                code="INVALID_TYPE",
                value=co2
            ))
            return
        
        # Convert to int if float
        if isinstance(co2, float):
            if not co2.is_integer():
                self.errors.append(ValidationError(
                    field="co2_ppm",
                    message="CO2 reading must be a whole number",
                    code="INVALID_PRECISION",
                    value=co2
                ))
                return
            co2 = int(co2)
        
        if not (self.CO2_MIN <= co2 <= self.CO2_MAX):
            self.errors.append(ValidationError(
                field="co2_ppm",
                message=f"CO2 reading must be between {self.CO2_MIN} and {self.CO2_MAX} ppm",
                code="OUT_OF_RANGE",
                value=co2
            ))
    
    def _is_valid_number(self, value: Any) -> bool:
        """Check if value is a valid, finite number."""
        if not isinstance(value, (int, float)):
            return False
        
        if isinstance(value, float):
            return not (math.isnan(value) or math.isinf(value))
        
        return True
    
    def _has_valid_precision(self, value: float) -> bool:
        """Check if float has acceptable decimal precision."""
        decimal_places = len(str(value).split('.')[-1]) if '.' in str(value) else 0
        return decimal_places <= self.MAX_DECIMAL_PLACES


class UserInputValidator:
    """Validates user registration and authentication inputs."""
    
    MIN_PASSWORD_LENGTH = 8
    MAX_PASSWORD_LENGTH = 128
    MIN_USERNAME_LENGTH = 3
    MAX_USERNAME_LENGTH = 50
    
    def __init__(self):
        """Initialize user input validator."""
        self.errors = []
    
    def validate_registration_input(self, username: str, email: str, password: str,
                                  first_name: Optional[str] = None,
                                  last_name: Optional[str] = None) -> ValidationResult:
        """
        Validate user registration input data.
        
        Args:
            username: User's chosen username
            email: User's email address
            password: User's password
            first_name: Optional first name
            last_name: Optional last name
            
        Returns:
            ValidationResult with validation status and any errors
        """
        self.errors = []
        
        self._validate_username(username)
        self._validate_email(email)
        self._validate_password(password)
        
        if first_name is not None:
            self._validate_name_field(first_name, "first_name")
        
        if last_name is not None:
            self._validate_name_field(last_name, "last_name")
        
        return ValidationResult(
            is_valid=len(self.errors) == 0,
            errors=self.errors.copy()
        )
    
    def _validate_username(self, username: str) -> None:
        """Validate username format and length."""
        if not isinstance(username, str):
            self.errors.append(ValidationError(
                field="username",
                message="Username must be a string",
                code="INVALID_TYPE",
                value=username
            ))
            return
        
        username = username.strip()
        
        if not username:
            self.errors.append(ValidationError(
                field="username",
                message="Username is required",
                code="REQUIRED_FIELD"
            ))
            return
        
        if len(username) < self.MIN_USERNAME_LENGTH:
            self.errors.append(ValidationError(
                field="username",
                message=f"Username must be at least {self.MIN_USERNAME_LENGTH} characters long",
                code="TOO_SHORT",
                value=username
            ))
        
        if len(username) > self.MAX_USERNAME_LENGTH:
            self.errors.append(ValidationError(
                field="username",
                message=f"Username cannot exceed {self.MAX_USERNAME_LENGTH} characters",
                code="TOO_LONG",
                value=username
            ))
        
        # Basic character validation
        if not username.replace('_', '').replace('-', '').isalnum():
            self.errors.append(ValidationError(
                field="username",
                message="Username can only contain letters, numbers, hyphens, and underscores",
                code="INVALID_CHARACTERS",
                value=username
            ))
    
    def _validate_email(self, email: str) -> None:
        """Validate email format."""
        if not isinstance(email, str):
            self.errors.append(ValidationError(
                field="email",
                message="Email must be a string",
                code="INVALID_TYPE",
                value=email
            ))
            return
        
        email = email.strip().lower()
        
        if not email:
            self.errors.append(ValidationError(
                field="email",
                message="Email is required",
                code="REQUIRED_FIELD"
            ))
            return
        
        # Basic email validation
        if '@' not in email:
            self.errors.append(ValidationError(
                field="email",
                message="Email format is invalid",
                code="INVALID_FORMAT",
                value=email
            ))
            return
        
        parts = email.split('@')
        if len(parts) != 2 or not parts[0] or not parts[1]:
            self.errors.append(ValidationError(
                field="email",
                message="Email format is invalid",
                code="INVALID_FORMAT",
                value=email
            ))
            return
        
        domain = parts[1]
        if '.' not in domain or domain.startswith('.') or domain.endswith('.'):
            self.errors.append(ValidationError(
                field="email",
                message="Email format is invalid",
                code="INVALID_FORMAT",
                value=email
            ))
    
    def _validate_password(self, password: str) -> None:
        """Validate password strength and format."""
        if not isinstance(password, str):
            self.errors.append(ValidationError(
                field="password",
                message="Password must be a string",
                code="INVALID_TYPE"
            ))
            return
        
        if not password:
            self.errors.append(ValidationError(
                field="password",
                message="Password is required",
                code="REQUIRED_FIELD"
            ))
            return
        
        if len(password) < self.MIN_PASSWORD_LENGTH:
            self.errors.append(ValidationError(
                field="password",
                message=f"Password must be at least {self.MIN_PASSWORD_LENGTH} characters long",
                code="TOO_SHORT"
            ))
        
        if len(password) > self.MAX_PASSWORD_LENGTH:
            self.errors.append(ValidationError(
                field="password",
                message=f"Password cannot exceed {self.MAX_PASSWORD_LENGTH} characters",
                code="TOO_LONG"
            ))
    
    def _validate_name_field(self, name: str, field_name: str) -> None:
        """Validate name fields (first_name, last_name)."""
        if not isinstance(name, str):
            display_name = field_name.replace('_', ' ')
            self.errors.append(ValidationError(
                field=field_name,
                message=f"{display_name.capitalize()} must be a string",
                code="INVALID_TYPE",
                value=name
            ))
            return
        
        name = name.strip()
        
        if len(name) > 50:
            display_name = field_name.replace('_', ' ')
            self.errors.append(ValidationError(
                field=field_name,
                message=f"{display_name.capitalize()} cannot exceed 50 characters",
                code="TOO_LONG",
                value=name
            ))


def create_validation_error_response(validation_result: ValidationResult) -> Dict[str, Any]:
    """
    Create a standardized error response from validation result.
    
    Args:
        validation_result: Result from validation operation
        
    Returns:
        Standardized error response dictionary
    """
    return {
        "success": False,
        "message": "Validation failed",
        "errors": [
            {
                "field": error.field,
                "message": error.message,
                "code": error.code,
                "value": error.value
            }
            for error in validation_result.errors
        ],
        "error_count": len(validation_result.errors)
    }