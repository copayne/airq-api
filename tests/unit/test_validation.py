"""
Unit tests for validation utilities.

Tests comprehensive validation logic for sensor readings and user inputs
including range checks, type validation, and error handling.
"""

import pytest
import math
from unittest.mock import patch, MagicMock
from app.validation import (
    SensorDataValidator, 
    UserInputValidator, 
    ValidationError, 
    ValidationResult,
    create_validation_error_response
)
from app.models import Sensor


@pytest.mark.validation
class TestValidationError:
    """Test ValidationError data class."""
    
    def test_validation_error_creation(self):
        """Test creating validation error with all fields."""
        error = ValidationError(
            field="test_field",
            message="Test error message",
            code="TEST_CODE",
            value="test_value"
        )
        
        assert error.field == "test_field"
        assert error.message == "Test error message"
        assert error.code == "TEST_CODE"
        assert error.value == "test_value"
    
    def test_validation_error_minimal(self):
        """Test creating validation error with minimal fields."""
        error = ValidationError(
            field="field",
            message="message",
            code="CODE"
        )
        
        assert error.field == "field"
        assert error.message == "message"
        assert error.code == "CODE"
        assert error.value is None


@pytest.mark.validation
class TestValidationResult:
    """Test ValidationResult data class."""
    
    def test_validation_result_valid(self):
        """Test validation result for valid input."""
        result = ValidationResult(is_valid=True, errors=[])
        
        assert result.is_valid is True
        assert len(result.errors) == 0
        assert len(result.error_messages) == 0
        assert len(result.errors_by_field) == 0
    
    def test_validation_result_invalid(self):
        """Test validation result for invalid input."""
        errors = [
            ValidationError("field1", "Error 1", "CODE1"),
            ValidationError("field2", "Error 2", "CODE2"),
            ValidationError("field1", "Error 3", "CODE3")
        ]
        
        result = ValidationResult(is_valid=False, errors=errors)
        
        assert result.is_valid is False
        assert len(result.errors) == 3
        assert result.error_messages == ["Error 1", "Error 2", "Error 3"]
        
        grouped = result.errors_by_field
        assert len(grouped["field1"]) == 2
        assert len(grouped["field2"]) == 1


@pytest.mark.validation
class TestSensorDataValidator:
    """Test sensor data validation logic."""
    
    def test_valid_sensor_reading(self, session):
        """Test validation of valid sensor reading."""
        # Create test sensor
        sensor = Sensor(name="Test Sensor", model="TestModel", is_active=True)
        session.add(sensor)
        session.commit()
        
        validator = SensorDataValidator()
        result = validator.validate_sensor_reading_input(
            sensor_id=sensor.id,
            humidity_percentage=50.5,
            temperature_celsius=23.2,
            co2_ppm=1200
        )
        
        assert result.is_valid is True
        assert len(result.errors) == 0
    
    def test_invalid_sensor_id_nonexistent(self):
        """Test validation with non-existent sensor ID."""
        validator = SensorDataValidator()
        result = validator.validate_sensor_reading_input(
            sensor_id=99999,  # Non-existent sensor
            humidity_percentage=50.0
        )
        
        assert result.is_valid is False
        assert len(result.errors) >= 1
        assert any("does not exist" in error.message for error in result.errors)
    
    def test_invalid_sensor_id_inactive(self, session):
        """Test validation with inactive sensor."""
        # Create inactive sensor
        sensor = Sensor(name="Inactive Sensor", model="TestModel", is_active=False)
        session.add(sensor)
        session.commit()
        
        validator = SensorDataValidator()
        result = validator.validate_sensor_reading_input(
            sensor_id=sensor.id,
            humidity_percentage=50.0
        )
        
        assert result.is_valid is False
        assert any("not active" in error.message for error in result.errors)
    
    def test_invalid_sensor_id_type(self):
        """Test validation with invalid sensor ID type."""
        validator = SensorDataValidator()
        result = validator.validate_sensor_reading_input(
            sensor_id="not_an_int",
            humidity_percentage=50.0
        )
        
        assert result.is_valid is False
        assert any("must be an integer" in error.message for error in result.errors)
    
    def test_invalid_sensor_id_negative(self):
        """Test validation with negative sensor ID."""
        validator = SensorDataValidator()
        result = validator.validate_sensor_reading_input(
            sensor_id=-1,
            humidity_percentage=50.0
        )
        
        assert result.is_valid is False
        assert any("must be positive" in error.message for error in result.errors)
    
    def test_humidity_range_validation(self, session):
        """Test humidity range validation."""
        # Create test sensor
        sensor = Sensor(name="Test Sensor", model="TestModel", is_active=True)
        session.add(sensor)
        session.commit()
        
        validator = SensorDataValidator()
        
        # Test below minimum
        result = validator.validate_sensor_reading_input(
            sensor_id=sensor.id,
            humidity_percentage=-5.0
        )
        assert result.is_valid is False
        assert any("between 0.0% and 100.0%" in error.message for error in result.errors)
        
        # Test above maximum
        result = validator.validate_sensor_reading_input(
            sensor_id=sensor.id,
            humidity_percentage=105.0
        )
        assert result.is_valid is False
        assert any("between 0.0% and 100.0%" in error.message for error in result.errors)
        
        # Test valid values
        for value in [0.0, 50.5, 100.0]:
            result = validator.validate_sensor_reading_input(
                sensor_id=sensor.id,
                humidity_percentage=value
            )
            assert result.is_valid is True
    
    def test_temperature_range_validation(self, session):
        """Test temperature range validation."""
        # Create test sensor
        sensor = Sensor(name="Test Sensor", model="TestModel", is_active=True)
        session.add(sensor)
        session.commit()
        
        validator = SensorDataValidator()
        
        # Test below minimum
        result = validator.validate_sensor_reading_input(
            sensor_id=sensor.id,
            temperature_celsius=-50.0
        )
        assert result.is_valid is False
        assert any("between -40.0°C and 85.0°C" in error.message for error in result.errors)
        
        # Test above maximum
        result = validator.validate_sensor_reading_input(
            sensor_id=sensor.id,
            temperature_celsius=100.0
        )
        assert result.is_valid is False
        assert any("between -40.0°C and 85.0°C" in error.message for error in result.errors)
        
        # Test valid values
        for value in [-40.0, 23.2, 85.0]:
            result = validator.validate_sensor_reading_input(
                sensor_id=sensor.id,
                temperature_celsius=value
            )
            assert result.is_valid is True
    
    def test_co2_range_validation(self, session):
        """Test CO2 range validation."""
        # Create test sensor
        sensor = Sensor(name="Test Sensor", model="TestModel", is_active=True)
        session.add(sensor)
        session.commit()
        
        validator = SensorDataValidator()
        
        # Test below minimum
        result = validator.validate_sensor_reading_input(
            sensor_id=sensor.id,
            co2_ppm=-100
        )
        assert result.is_valid is False
        assert any("between 0 and 50000 ppm" in error.message for error in result.errors)
        
        # Test above maximum
        result = validator.validate_sensor_reading_input(
            sensor_id=sensor.id,
            co2_ppm=60000
        )
        assert result.is_valid is False
        assert any("between 0 and 50000 ppm" in error.message for error in result.errors)
        
        # Test valid values
        for value in [0, 1200, 50000]:
            result = validator.validate_sensor_reading_input(
                sensor_id=sensor.id,
                co2_ppm=value
            )
            assert result.is_valid is True
    
    def test_invalid_number_types(self, session):
        """Test validation with invalid number types."""
        # Create test sensor
        sensor = Sensor(name="Test Sensor", model="TestModel", is_active=True)
        session.add(sensor)
        session.commit()
        
        validator = SensorDataValidator()
        
        # Test NaN
        result = validator.validate_sensor_reading_input(
            sensor_id=sensor.id,
            humidity_percentage=float('nan')
        )
        assert result.is_valid is False
        assert any("valid number" in error.message for error in result.errors)
        
        # Test infinity
        result = validator.validate_sensor_reading_input(
            sensor_id=sensor.id,
            temperature_celsius=float('inf')
        )
        assert result.is_valid is False
        assert any("valid number" in error.message for error in result.errors)
        
        # Test string
        result = validator.validate_sensor_reading_input(
            sensor_id=sensor.id,
            co2_ppm="not_a_number"
        )
        assert result.is_valid is False
        assert any("must be a number" in error.message for error in result.errors)
    
    def test_precision_validation(self, session):
        """Test decimal precision validation."""
        # Create test sensor
        sensor = Sensor(name="Test Sensor", model="TestModel", is_active=True)
        session.add(sensor)
        session.commit()
        
        validator = SensorDataValidator()
        
        # Test excessive precision
        result = validator.validate_sensor_reading_input(
            sensor_id=sensor.id,
            humidity_percentage=50.123456  # Too many decimal places
        )
        assert result.is_valid is False
        assert any("precision cannot exceed" in error.message for error in result.errors)
        
        # Test acceptable precision
        result = validator.validate_sensor_reading_input(
            sensor_id=sensor.id,
            humidity_percentage=50.12  # Acceptable precision
        )
        assert result.is_valid is True
    
    def test_no_readings_provided(self, session):
        """Test validation when no readings are provided."""
        # Create test sensor
        sensor = Sensor(name="Test Sensor", model="TestModel", is_active=True)
        session.add(sensor)
        session.commit()
        
        validator = SensorDataValidator()
        result = validator.validate_sensor_reading_input(sensor_id=sensor.id)
        
        assert result.is_valid is False
        assert any("At least one sensor reading must be provided" in error.message for error in result.errors)
    
    def test_co2_float_to_int_validation(self, session):
        """Test CO2 validation with float input."""
        # Create test sensor
        sensor = Sensor(name="Test Sensor", model="TestModel", is_active=True)
        session.add(sensor)
        session.commit()
        
        validator = SensorDataValidator()
        
        # Test float that's actually an integer
        result = validator.validate_sensor_reading_input(
            sensor_id=sensor.id,
            co2_ppm=1200.0
        )
        assert result.is_valid is True
        
        # Test float with decimal places
        result = validator.validate_sensor_reading_input(
            sensor_id=sensor.id,
            co2_ppm=1200.5
        )
        assert result.is_valid is False
        assert any("whole number" in error.message for error in result.errors)


@pytest.mark.validation
class TestUserInputValidator:
    """Test user input validation logic."""
    
    def test_valid_registration_input(self):
        """Test validation of valid registration data."""
        validator = UserInputValidator()
        result = validator.validate_registration_input(
            username="testuser",
            email="test@example.com",
            password="securepassword123",
            first_name="John",
            last_name="Doe"
        )
        
        assert result.is_valid is True
        assert len(result.errors) == 0
    
    def test_username_validation(self):
        """Test username validation rules."""
        validator = UserInputValidator()
        
        # Test too short
        result = validator.validate_registration_input(
            username="ab",
            email="test@example.com",
            password="password123"
        )
        assert result.is_valid is False
        assert any("at least 3 characters" in error.message for error in result.errors)
        
        # Test too long
        result = validator.validate_registration_input(
            username="a" * 51,
            email="test@example.com", 
            password="password123"
        )
        assert result.is_valid is False
        assert any("cannot exceed 50 characters" in error.message for error in result.errors)
        
        # Test invalid characters
        result = validator.validate_registration_input(
            username="user@name",
            email="test@example.com",
            password="password123"
        )
        assert result.is_valid is False
        assert any("only contain letters, numbers" in error.message for error in result.errors)
        
        # Test valid usernames
        for username in ["user123", "test_user", "user-name", "User123"]:
            result = validator.validate_registration_input(
                username=username,
                email="test@example.com",
                password="password123"
            )
            assert result.is_valid is True
    
    def test_email_validation(self):
        """Test email validation rules."""
        validator = UserInputValidator()
        
        # Test invalid format
        invalid_emails = ["invalid", "no@domain", "@domain.com", "user@", "user@.com"]
        for email in invalid_emails:
            result = validator.validate_registration_input(
                username="testuser",
                email=email,
                password="password123"
            )
            assert result.is_valid is False
            assert any("format is invalid" in error.message for error in result.errors)
        
        # Test valid emails
        valid_emails = ["test@example.com", "user.name@domain.co.uk", "123@test.org"]
        for email in valid_emails:
            result = validator.validate_registration_input(
                username="testuser",
                email=email,
                password="password123"
            )
            assert result.is_valid is True
    
    def test_password_validation(self):
        """Test password validation rules."""
        validator = UserInputValidator()
        
        # Test too short
        result = validator.validate_registration_input(
            username="testuser",
            email="test@example.com",
            password="short"
        )
        assert result.is_valid is False
        assert any("at least 8 characters" in error.message for error in result.errors)
        
        # Test too long
        result = validator.validate_registration_input(
            username="testuser",
            email="test@example.com",
            password="a" * 129
        )
        assert result.is_valid is False
        assert any("cannot exceed 128 characters" in error.message for error in result.errors)
        
        # Test valid passwords
        valid_passwords = ["password123", "securepass", "a" * 8, "a" * 128]
        for password in valid_passwords:
            result = validator.validate_registration_input(
                username="testuser",
                email="test@example.com",
                password=password
            )
            assert result.is_valid is True
    
    def test_name_validation(self):
        """Test first and last name validation."""
        validator = UserInputValidator()
        
        # Test too long names
        long_name = "a" * 51
        result = validator.validate_registration_input(
            username="testuser",
            email="test@example.com",
            password="password123",
            first_name=long_name
        )
        assert result.is_valid is False
        assert any("First name cannot exceed 50 characters" in error.message for error in result.errors)
        
        result = validator.validate_registration_input(
            username="testuser",
            email="test@example.com",
            password="password123",
            last_name=long_name
        )
        assert result.is_valid is False
        assert any("Last name cannot exceed 50 characters" in error.message for error in result.errors)
        
        # Test valid names
        result = validator.validate_registration_input(
            username="testuser",
            email="test@example.com",
            password="password123",
            first_name="John",
            last_name="Doe"
        )
        assert result.is_valid is True
    
    def test_type_validation(self):
        """Test validation of invalid input types."""
        validator = UserInputValidator()
        
        # Test non-string username
        result = validator.validate_registration_input(
            username=123,
            email="test@example.com",
            password="password123"
        )
        assert result.is_valid is False
        assert any("must be a string" in error.message for error in result.errors)
        
        # Test non-string email
        result = validator.validate_registration_input(
            username="testuser",
            email=123,
            password="password123"
        )
        assert result.is_valid is False
        assert any("must be a string" in error.message for error in result.errors)
        
        # Test non-string password
        result = validator.validate_registration_input(
            username="testuser",
            email="test@example.com",
            password=123
        )
        assert result.is_valid is False
        assert any("must be a string" in error.message for error in result.errors)


@pytest.mark.validation
class TestValidationHelpers:
    """Test validation helper functions."""
    
    def test_create_validation_error_response(self):
        """Test creation of standardized error response."""
        errors = [
            ValidationError("field1", "Error 1", "CODE1", "value1"),
            ValidationError("field2", "Error 2", "CODE2")
        ]
        
        result = ValidationResult(is_valid=False, errors=errors)
        response = create_validation_error_response(result)
        
        assert response["success"] is False
        assert response["message"] == "Validation failed"
        assert response["error_count"] == 2
        assert len(response["errors"]) == 2
        
        assert response["errors"][0]["field"] == "field1"
        assert response["errors"][0]["message"] == "Error 1"
        assert response["errors"][0]["code"] == "CODE1"
        assert response["errors"][0]["value"] == "value1"
        
        assert response["errors"][1]["field"] == "field2"
        assert response["errors"][1]["message"] == "Error 2"
        assert response["errors"][1]["code"] == "CODE2"
        assert response["errors"][1]["value"] is None