"""
Integration tests for GraphQL mutations with validation.

Tests the complete validation flow through GraphQL mutations including
sensor reading creation and user registration with comprehensive validation.
"""

import pytest
import json
from app.models import Sensor, User


@pytest.mark.integration
class TestSensorReadingValidation:
    """Test sensor reading validation through GraphQL mutations."""
    
    def test_create_sensor_reading_success(self, client, session):
        """Test successful sensor reading creation with valid data."""
        # Create test sensor
        sensor = Sensor(name="Test Sensor", model="TestModel", is_active=True)
        session.add(sensor)
        session.commit()
        
        mutation = """
        mutation CreateReading($input: CreateSensorReadingInput!) {
            createSensorReading(input: $input) {
                success
                message
                errors
                sensorReading {
                    id
                    sensorId
                    humidityReading {
                        humidityPercentage
                    }
                    temperatureReading {
                        temperatureCelsius
                    }
                    co2Reading {
                        co2Ppm
                    }
                }
            }
        }
        """
        
        variables = {
            "input": {
                "sensorId": sensor.id,
                "humidityPercentage": 65.5,
                "temperatureCelsius": 23.2,
                "co2Ppm": 1200
            }
        }
        
        response = client.post('/graphql',
                             json={'query': mutation, 'variables': variables},
                             headers={'Content-Type': 'application/json'})
        
        assert response.status_code == 200
        data = response.get_json()
        
        assert 'data' in data
        result = data['data']['createSensorReading']
        assert result['success'] is True
        assert result['message'] == "Sensor reading created successfully"
        assert result['errors'] == []
        
        # Verify reading data
        reading = result['sensorReading']
        assert reading['sensorId'] == sensor.id
        assert reading['humidityReading']['humidityPercentage'] == 65.5
        assert reading['temperatureReading']['temperatureCelsius'] == 23.2
        assert reading['co2Reading']['co2Ppm'] == 1200
    
    def test_create_sensor_reading_nonexistent_sensor(self, client):
        """Test sensor reading creation with non-existent sensor."""
        mutation = """
        mutation CreateReading($input: CreateSensorReadingInput!) {
            createSensorReading(input: $input) {
                success
                message
                errors
                sensorReading {
                    id
                }
            }
        }
        """
        
        variables = {
            "input": {
                "sensorId": 99999,  # Non-existent sensor
                "humidityPercentage": 50.0
            }
        }
        
        response = client.post('/graphql',
                             json={'query': mutation, 'variables': variables},
                             headers={'Content-Type': 'application/json'})
        
        assert response.status_code == 200
        data = response.get_json()
        
        result = data['data']['createSensorReading']
        assert result['success'] is False
        assert result['message'] == "Validation failed"
        assert result['sensorReading'] is None
        assert any("does not exist" in error for error in result['errors'])
    
    def test_create_sensor_reading_inactive_sensor(self, client, session):
        """Test sensor reading creation with inactive sensor."""
        # Create inactive sensor
        sensor = Sensor(name="Inactive Sensor", model="TestModel", is_active=False)
        session.add(sensor)
        session.commit()
        
        mutation = """
        mutation CreateReading($input: CreateSensorReadingInput!) {
            createSensorReading(input: $input) {
                success
                message
                errors
            }
        }
        """
        
        variables = {
            "input": {
                "sensorId": sensor.id,
                "humidityPercentage": 50.0
            }
        }
        
        response = client.post('/graphql',
                             json={'query': mutation, 'variables': variables},
                             headers={'Content-Type': 'application/json'})
        
        assert response.status_code == 200
        data = response.get_json()
        
        result = data['data']['createSensorReading']
        assert result['success'] is False
        assert any("not active" in error for error in result['errors'])
    
    def test_create_sensor_reading_invalid_humidity_range(self, client, session):
        """Test sensor reading creation with out-of-range humidity."""
        # Create test sensor
        sensor = Sensor(name="Test Sensor", model="TestModel", is_active=True)
        session.add(sensor)
        session.commit()
        
        mutation = """
        mutation CreateReading($input: CreateSensorReadingInput!) {
            createSensorReading(input: $input) {
                success
                message
                errors
            }
        }
        """
        
        # Test humidity above 100%
        variables = {
            "input": {
                "sensorId": sensor.id,
                "humidityPercentage": 105.0
            }
        }
        
        response = client.post('/graphql',
                             json={'query': mutation, 'variables': variables},
                             headers={'Content-Type': 'application/json'})
        
        assert response.status_code == 200
        data = response.get_json()
        
        result = data['data']['createSensorReading']
        assert result['success'] is False
        assert any("between 0.0% and 100.0%" in error for error in result['errors'])
    
    def test_create_sensor_reading_invalid_temperature_range(self, client, session):
        """Test sensor reading creation with out-of-range temperature."""
        # Create test sensor
        sensor = Sensor(name="Test Sensor", model="TestModel", is_active=True)
        session.add(sensor)
        session.commit()
        
        mutation = """
        mutation CreateReading($input: CreateSensorReadingInput!) {
            createSensorReading(input: $input) {
                success
                errors
            }
        }
        """
        
        # Test temperature below minimum
        variables = {
            "input": {
                "sensorId": sensor.id,
                "temperatureCelsius": -50.0
            }
        }
        
        response = client.post('/graphql',
                             json={'query': mutation, 'variables': variables},
                             headers={'Content-Type': 'application/json'})
        
        assert response.status_code == 200
        data = response.get_json()
        
        result = data['data']['createSensorReading']
        assert result['success'] is False
        assert any("between -40.0°C and 85.0°C" in error for error in result['errors'])
    
    def test_create_sensor_reading_invalid_co2_range(self, client, session):
        """Test sensor reading creation with out-of-range CO2."""
        # Create test sensor
        sensor = Sensor(name="Test Sensor", model="TestModel", is_active=True)
        session.add(sensor)
        session.commit()
        
        mutation = """
        mutation CreateReading($input: CreateSensorReadingInput!) {
            createSensorReading(input: $input) {
                success
                errors
            }
        }
        """
        
        # Test CO2 above maximum
        variables = {
            "input": {
                "sensorId": sensor.id,
                "co2Ppm": 60000
            }
        }
        
        response = client.post('/graphql',
                             json={'query': mutation, 'variables': variables},
                             headers={'Content-Type': 'application/json'})
        
        assert response.status_code == 200
        data = response.get_json()
        
        result = data['data']['createSensorReading']
        assert result['success'] is False
        assert any("between 0 and 50000 ppm" in error for error in result['errors'])
    
    def test_create_sensor_reading_no_measurements(self, client, session):
        """Test sensor reading creation with no measurement data."""
        # Create test sensor
        sensor = Sensor(name="Test Sensor", model="TestModel", is_active=True)
        session.add(sensor)
        session.commit()
        
        mutation = """
        mutation CreateReading($input: CreateSensorReadingInput!) {
            createSensorReading(input: $input) {
                success
                errors
            }
        }
        """
        
        variables = {
            "input": {
                "sensorId": sensor.id
                # No measurement data provided
            }
        }
        
        response = client.post('/graphql',
                             json={'query': mutation, 'variables': variables},
                             headers={'Content-Type': 'application/json'})
        
        assert response.status_code == 200
        data = response.get_json()
        
        result = data['data']['createSensorReading']
        assert result['success'] is False
        assert any("At least one sensor reading must be provided" in error for error in result['errors'])
    
    def test_create_sensor_reading_partial_measurements(self, client, session):
        """Test sensor reading creation with only some measurements."""
        # Create test sensor
        sensor = Sensor(name="Test Sensor", model="TestModel", is_active=True)
        session.add(sensor)
        session.commit()
        
        mutation = """
        mutation CreateReading($input: CreateSensorReadingInput!) {
            createSensorReading(input: $input) {
                success
                sensorReading {
                    humidityReading {
                        humidityPercentage
                    }
                    temperatureReading {
                        temperatureCelsius
                    }
                    co2Reading {
                        co2Ppm
                    }
                }
            }
        }
        """
        
        # Test with only humidity
        variables = {
            "input": {
                "sensorId": sensor.id,
                "humidityPercentage": 65.5
            }
        }
        
        response = client.post('/graphql',
                             json={'query': mutation, 'variables': variables},
                             headers={'Content-Type': 'application/json'})
        
        assert response.status_code == 200
        data = response.get_json()
        
        result = data['data']['createSensorReading']
        assert result['success'] is True
        
        reading = result['sensorReading']
        assert reading['humidityReading']['humidityPercentage'] == 65.5
        assert reading['temperatureReading'] is None
        assert reading['co2Reading'] is None


@pytest.mark.integration
class TestUserRegistrationValidation:
    """Test user registration validation through GraphQL mutations."""
    
    def test_register_user_success_with_validation(self, client):
        """Test successful user registration with valid data."""
        mutation = """
        mutation RegisterUser($input: RegisterInput!) {
            registerUser(input: $input) {
                success
                message
                user {
                    username
                    email
                    fullName
                }
                token
            }
        }
        """
        
        variables = {
            "input": {
                "username": "validuser",
                "email": "valid@example.com",
                "password": "securepassword123",
                "firstName": "John",
                "lastName": "Doe"
            }
        }
        
        response = client.post('/graphql',
                             json={'query': mutation, 'variables': variables},
                             headers={'Content-Type': 'application/json'})
        
        assert response.status_code == 200
        data = response.get_json()
        
        result = data['data']['registerUser']
        assert result['success'] is True
        assert result['message'] == "Registration successful"
        assert result['token'] is not None
        
        user_data = result['user']
        assert user_data['username'] == "validuser"
        assert user_data['email'] == "valid@example.com"
        assert user_data['fullName'] == "John Doe"
    
    def test_register_user_username_too_short(self, client):
        """Test user registration with username too short."""
        mutation = """
        mutation RegisterUser($input: RegisterInput!) {
            registerUser(input: $input) {
                success
                message
            }
        }
        """
        
        variables = {
            "input": {
                "username": "ab",  # Too short
                "email": "test@example.com",
                "password": "password123"
            }
        }
        
        response = client.post('/graphql',
                             json={'query': mutation, 'variables': variables},
                             headers={'Content-Type': 'application/json'})
        
        assert response.status_code == 200
        data = response.get_json()
        
        result = data['data']['registerUser']
        assert result['success'] is False
        assert "at least 3 characters" in result['message']
    
    def test_register_user_invalid_email(self, client):
        """Test user registration with invalid email format."""
        mutation = """
        mutation RegisterUser($input: RegisterInput!) {
            registerUser(input: $input) {
                success
                message
            }
        }
        """
        
        variables = {
            "input": {
                "username": "testuser",
                "email": "invalid-email",  # Invalid format
                "password": "password123"
            }
        }
        
        response = client.post('/graphql',
                             json={'query': mutation, 'variables': variables},
                             headers={'Content-Type': 'application/json'})
        
        assert response.status_code == 200
        data = response.get_json()
        
        result = data['data']['registerUser']
        assert result['success'] is False
        assert "format is invalid" in result['message']
    
    def test_register_user_password_too_short(self, client):
        """Test user registration with password too short."""
        mutation = """
        mutation RegisterUser($input: RegisterInput!) {
            registerUser(input: $input) {
                success
                message
            }
        }
        """
        
        variables = {
            "input": {
                "username": "testuser",
                "email": "test@example.com",
                "password": "short"  # Too short
            }
        }
        
        response = client.post('/graphql',
                             json={'query': mutation, 'variables': variables},
                             headers={'Content-Type': 'application/json'})
        
        assert response.status_code == 200
        data = response.get_json()
        
        result = data['data']['registerUser']
        assert result['success'] is False
        assert "at least 8 characters" in result['message']
    
    def test_register_user_username_invalid_characters(self, client):
        """Test user registration with invalid username characters."""
        mutation = """
        mutation RegisterUser($input: RegisterInput!) {
            registerUser(input: $input) {
                success
                message
            }
        }
        """
        
        variables = {
            "input": {
                "username": "user@name",  # Invalid characters
                "email": "test@example.com",
                "password": "password123"
            }
        }
        
        response = client.post('/graphql',
                             json={'query': mutation, 'variables': variables},
                             headers={'Content-Type': 'application/json'})
        
        assert response.status_code == 200
        data = response.get_json()
        
        result = data['data']['registerUser']
        assert result['success'] is False
        assert "only contain letters, numbers" in result['message']
    
    def test_register_user_duplicate_username_still_works(self, client, session):
        """Test that duplicate username validation still works after our changes."""
        # Create existing user
        existing_user = User(username="existing", email="existing@example.com")
        existing_user.set_password("password123")
        session.add(existing_user)
        session.commit()
        
        mutation = """
        mutation RegisterUser($input: RegisterInput!) {
            registerUser(input: $input) {
                success
                message
            }
        }
        """
        
        variables = {
            "input": {
                "username": "existing",  # Duplicate username
                "email": "newemail@example.com",
                "password": "password123"
            }
        }
        
        response = client.post('/graphql',
                             json={'query': mutation, 'variables': variables},
                             headers={'Content-Type': 'application/json'})
        
        assert response.status_code == 200
        data = response.get_json()
        
        result = data['data']['registerUser']
        assert result['success'] is False
        assert "Username already exists" in result['message']
    
    def test_register_user_data_trimming(self, client):
        """Test that user registration trims whitespace from inputs."""
        mutation = """
        mutation RegisterUser($input: RegisterInput!) {
            registerUser(input: $input) {
                success
                user {
                    username
                    email
                    firstName
                    lastName
                }
            }
        }
        """
        
        variables = {
            "input": {
                "username": "  testuser  ",  # Whitespace around username
                "email": "  TEST@EXAMPLE.COM  ",  # Whitespace and uppercase
                "password": "password123",
                "firstName": "  John  ",
                "lastName": "  Doe  "
            }
        }
        
        response = client.post('/graphql',
                             json={'query': mutation, 'variables': variables},
                             headers={'Content-Type': 'application/json'})
        
        assert response.status_code == 200
        data = response.get_json()
        
        result = data['data']['registerUser']
        assert result['success'] is True
        
        user_data = result['user']
        assert user_data['username'] == "testuser"  # Trimmed
        assert user_data['email'] == "test@example.com"  # Trimmed and lowercased
        assert user_data['firstName'] == "John"  # Trimmed
        assert user_data['lastName'] == "Doe"  # Trimmed