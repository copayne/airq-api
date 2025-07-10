"""
Integration tests for GraphQL API endpoints.
"""

import pytest
import json
from datetime import datetime, timedelta


@pytest.mark.integration
class TestGraphQLQueries:
    """Test GraphQL query endpoints."""
    
    def test_sensors_query(self, client, session, sample_sensor):
        """Test basic sensors query."""
        query = """
        query {
            sensors {
                id
                name
                model
                isActive
            }
        }
        """
        
        response = client.post('/graphql', 
                             json={'query': query},
                             headers={'Content-Type': 'application/json'})
        
        assert response.status_code == 200
        data = response.get_json()
        
        assert 'data' in data
        assert 'sensors' in data['data']
        assert len(data['data']['sensors']) >= 1
        
        sensor_data = data['data']['sensors'][0]
        assert 'id' in sensor_data
        assert 'name' in sensor_data
        assert 'model' in sensor_data
        assert 'isActive' in sensor_data
    
    def test_locations_query(self, client, session, sample_location):
        """Test basic locations query."""
        query = """
        query {
            locations {
                id
                name
                description
            }
        }
        """
        
        response = client.post('/graphql',
                             json={'query': query},
                             headers={'Content-Type': 'application/json'})
        
        assert response.status_code == 200
        data = response.get_json()
        
        assert 'data' in data
        assert 'locations' in data['data']
        assert len(data['data']['locations']) >= 1
        
        location_data = data['data']['locations'][0]
        assert 'id' in location_data
        assert 'name' in location_data
    
    def test_sensor_readings_query(self, client, session, sample_reading_with_data):
        """Test sensor readings query with measurements."""
        query = """
        query {
            sensorReadings {
                id
                readingTime
                isSuccess
                sensor {
                    id
                    name
                }
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
        """
        
        response = client.post('/graphql',
                             json={'query': query},
                             headers={'Content-Type': 'application/json'})
        
        assert response.status_code == 200
        data = response.get_json()
        
        assert 'data' in data
        assert 'sensorReadings' in data['data']
        assert len(data['data']['sensorReadings']) >= 1
        
        reading_data = data['data']['sensorReadings'][0]
        assert 'id' in reading_data
        assert 'sensor' in reading_data
        assert 'humidityReading' in reading_data
        assert 'temperatureReading' in reading_data
        assert 'co2Reading' in reading_data
    
    def test_filtered_sensor_readings_query(self, client, session, sample_reading_with_data):
        """Test filtered sensor readings query."""
        query = """
        query FilteredReadings($filters: SensorDataFilterInput!) {
            filteredSensorReadings(filters: $filters) {
                id
                readingTime
                sensor {
                    id
                    name
                }
                humidityReading {
                    humidityPercentage
                }
            }
        }
        """
        
        variables = {
            "filters": {
                "limit": 10,
                "orderDirection": "desc"
            }
        }
        
        response = client.post('/graphql',
                             json={'query': query, 'variables': variables},
                             headers={'Content-Type': 'application/json'})
        
        assert response.status_code == 200
        data = response.get_json()
        
        assert 'data' in data
        assert 'filteredSensorReadings' in data['data']
        assert len(data['data']['filteredSensorReadings']) >= 1
    
    def test_single_sensor_query(self, client, session, sample_sensor):
        """Test querying a single sensor by ID."""
        query = """
        query GetSensor($id: Int!) {
            sensor(id: $id) {
                id
                name
                model
                currentLocation {
                    id
                    name
                }
            }
        }
        """
        
        variables = {"id": sample_sensor.id}
        
        response = client.post('/graphql',
                             json={'query': query, 'variables': variables},
                             headers={'Content-Type': 'application/json'})
        
        assert response.status_code == 200
        data = response.get_json()
        
        assert 'data' in data
        assert 'sensor' in data['data']
        sensor_data = data['data']['sensor']
        assert sensor_data['id'] == str(sample_sensor.id)
        assert sensor_data['name'] == sample_sensor.name


@pytest.mark.integration
class TestGraphQLMutations:
    """Test GraphQL mutation endpoints."""
    
    def test_create_sensor_reading_mutation(self, client, session, sample_sensor):
        """Test creating a sensor reading via mutation."""
        mutation = """
        mutation CreateReading($input: CreateSensorReadingInput!) {
            createSensorReading(input: $input) {
                sensorReading {
                    id
                    sensor {
                        id
                        name
                    }
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
                "sensorId": sample_sensor.id,
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
        assert 'createSensorReading' in data['data']
        assert 'sensorReading' in data['data']['createSensorReading']
        
        reading_data = data['data']['createSensorReading']['sensorReading']
        assert reading_data['sensor']['id'] == str(sample_sensor.id)
        assert reading_data['humidityReading']['humidityPercentage'] == 65.5
        assert reading_data['temperatureReading']['temperatureCelsius'] == 23.2
        assert reading_data['co2Reading']['co2Ppm'] == 1200
    
    def test_create_partial_sensor_reading(self, client, session, sample_sensor):
        """Test creating a sensor reading with only some measurements."""
        mutation = """
        mutation CreateReading($input: CreateSensorReadingInput!) {
            createSensorReading(input: $input) {
                sensorReading {
                    id
                    sensor {
                        id
                    }
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
                "sensorId": sample_sensor.id,
                "temperatureCelsius": 24.1
            }
        }
        
        response = client.post('/graphql',
                             json={'query': mutation, 'variables': variables},
                             headers={'Content-Type': 'application/json'})
        
        assert response.status_code == 200
        data = response.get_json()
        
        assert 'data' in data
        reading_data = data['data']['createSensorReading']['sensorReading']
        assert reading_data['sensor']['id'] == str(sample_sensor.id)
        assert reading_data['temperatureReading']['temperatureCelsius'] == 24.1
        # Other readings should be null
        assert reading_data['humidityReading'] is None
        assert reading_data['co2Reading'] is None


@pytest.mark.integration
class TestGraphQLSecurity:
    """Test GraphQL security features."""
    
    def test_query_depth_limiting(self, client):
        """Test that excessively deep queries are rejected."""
        # Create a very deep query that should be rejected
        deep_query = """
        query {
            sensors {
                readings {
                    sensor {
                        readings {
                            sensor {
                                readings {
                                    sensor {
                                        readings {
                                            sensor {
                                                id
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
        """
        
        response = client.post('/graphql',
                             json={'query': deep_query},
                             headers={'Content-Type': 'application/json'})
        
        assert response.status_code == 200
        data = response.get_json()
        
        # Should return an error due to depth limiting
        assert 'errors' in data
        assert any('depth' in str(error).lower() for error in data['errors'])
    
    def test_malformed_query_handling(self, client):
        """Test that malformed queries are handled gracefully."""
        malformed_query = "query { sensors { invalid_field } }"
        
        response = client.post('/graphql',
                             json={'query': malformed_query},
                             headers={'Content-Type': 'application/json'})
        
        assert response.status_code == 200
        data = response.get_json()
        
        # Should return an error for invalid field
        assert 'errors' in data
    
    def test_missing_required_variables(self, client):
        """Test handling of missing required variables."""
        query = """
        query GetSensor($id: Int!) {
            sensor(id: $id) {
                id
                name
            }
        }
        """
        
        # Don't provide required $id variable
        response = client.post('/graphql',
                             json={'query': query},
                             headers={'Content-Type': 'application/json'})
        
        assert response.status_code == 200
        data = response.get_json()
        
        # Should return an error for missing variable
        assert 'errors' in data