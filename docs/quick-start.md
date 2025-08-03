# AirQ API Quick Start Guide

Get started with the Hudson Air Quality API in minutes.

## Table of Contents
- [Setup](#setup)
- [Authentication](#authentication)
- [Basic Operations](#basic-operations)
- [Common Use Cases](#common-use-cases)
- [Code Examples](#code-examples)
- [Next Steps](#next-steps)

## Setup

### 1. Base URL
```
Development: http://127.0.0.1:5000/graphql
Production: <your-production-url>/graphql
```

### 2. Required Headers
```
Content-Type: application/json
Authorization: Bearer <your-jwt-token>  // For authenticated requests
```

### 3. GraphQL Playground (Development)
Visit `http://127.0.0.1:5000/graphql` in your browser to access the interactive GraphQL playground.

## Authentication

### Step 1: Register a New User

**Request:**
```graphql
mutation RegisterUser {
  registerUser(input: {
    username: "myusername"
    email: "me@example.com"
    password: "securepassword123"
    firstName: "John"
    lastName: "Doe"
  }) {
    success
    message
    user {
      id
      username
      email
      role
    }
    token
  }
}
```

**Response:**
```json
{
  "data": {
    "registerUser": {
      "success": true,
      "message": "Registration successful",
      "user": {
        "id": "1",
        "username": "myusername",
        "email": "me@example.com",
        "role": "user"
      },
      "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
    }
  }
}
```

### Step 2: Login (Alternative)

**Request:**
```graphql
mutation LoginUser {
  loginUser(input: {
    usernameOrEmail: "myusername"
    password: "securepassword123"
  }) {
    success
    message
    user {
      id
      username
      role
    }
    token
  }
}
```

### Step 3: Save Your Token
Copy the token from the response and include it in subsequent requests:
```
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

## Basic Operations

### 1. View Available Sensors

**Request:**
```graphql
query GetSensors {
  sensors {
    id
    name
    model
    isActive
    currentLocation {
      name
    }
  }
}
```

### 2. Get Recent Sensor Readings

**Request:**
```graphql
query GetRecentReadings {
  sensorReadings {
    id
    readingTime
    sensor {
      name
    }
    location {
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
```

### 3. Submit a Sensor Reading

**Request:**
```graphql
mutation CreateReading {
  createSensorReading(input: {
    sensorId: 1
    humidityPercentage: 65.5
    temperatureCelsius: 23.2
    co2Ppm: 1200
  }) {
    success
    message
    errors
    sensorReading {
      id
      readingTime
    }
  }
}
```

## Common Use Cases

### Use Case 1: Get Air Quality for a Specific Location

**Request:**
```graphql
query GetLocationAirQuality($locationId: Int!) {
  filteredSensorReadings(filters: {
    locationIds: [$locationId]
    orderBy: "reading_time"
    orderDirection: "desc"
    limit: 10
  }) {
    readingTime
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
```

**Variables:**
```json
{
  "locationId": 1
}
```

### Use Case 2: Get Readings from Last 24 Hours

**Request:**
```graphql
query GetLast24Hours {
  filteredSensorReadings(filters: {
    startDate: "2024-01-15T00:00:00Z"
    endDate: "2024-01-16T00:00:00Z"
    orderBy: "reading_time"
    orderDirection: "desc"
  }) {
    readingTime
    sensor {
      name
    }
    location {
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
```

### Use Case 3: Monitor High CO2 Levels

**Request:**
```graphql
query GetHighCO2Readings {
  filteredSensorReadings(filters: {
    minCo2Ppm: 1000
    orderBy: "co2_ppm"
    orderDirection: "desc"
    limit: 50
  }) {
    readingTime
    sensor {
      name
    }
    location {
      name
    }
    co2Reading {
      co2Ppm
    }
  }
}
```

### Use Case 4: Get Current User Profile

**Request:**
```graphql
query GetMyProfile {
  me {
    username
    email
    fullName
    role
    createdAt
    lastLogin
  }
}
```

## Code Examples

### JavaScript/Node.js

```javascript
const axios = require('axios');

const API_URL = 'http://127.0.0.1:5000/graphql';
const JWT_TOKEN = 'your-jwt-token-here';

// Function to make GraphQL requests
async function graphqlRequest(query, variables = {}) {
  try {
    const response = await axios.post(API_URL, {
      query,
      variables
    }, {
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${JWT_TOKEN}`
      }
    });
    
    return response.data;
  } catch (error) {
    console.error('GraphQL Error:', error.response.data);
    throw error;
  }
}

// Example: Get recent readings
async function getRecentReadings() {
  const query = `
    query GetRecentReadings {
      sensorReadings {
        id
        readingTime
        sensor { name }
        humidityReading { humidityPercentage }
        temperatureReading { temperatureCelsius }
        co2Reading { co2Ppm }
      }
    }
  `;
  
  const result = await graphqlRequest(query);
  return result.data.sensorReadings;
}

// Example: Create sensor reading
async function createReading(sensorId, humidity, temperature, co2) {
  const mutation = `
    mutation CreateReading($input: CreateSensorReadingInput!) {
      createSensorReading(input: $input) {
        success
        message
        errors
        sensorReading {
          id
          readingTime
        }
      }
    }
  `;
  
  const variables = {
    input: {
      sensorId,
      humidityPercentage: humidity,
      temperatureCelsius: temperature,
      co2Ppm: co2
    }
  };
  
  const result = await graphqlRequest(mutation, variables);
  return result.data.createSensorReading;
}

// Usage
getRecentReadings().then(readings => {
  console.log('Recent readings:', readings);
});

createReading(1, 65.5, 23.2, 1200).then(result => {
  console.log('Created reading:', result);
});
```

### Python

```python
import requests
import json
from datetime import datetime

API_URL = 'http://127.0.0.1:5000/graphql'
JWT_TOKEN = 'your-jwt-token-here'

def graphql_request(query, variables=None):
    """Make a GraphQL request."""
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {JWT_TOKEN}'
    }
    
    payload = {
        'query': query,
        'variables': variables or {}
    }
    
    response = requests.post(API_URL, json=payload, headers=headers)
    response.raise_for_status()
    
    return response.json()

def get_sensors():
    """Get all available sensors."""
    query = """
    query GetSensors {
      sensors {
        id
        name
        model
        isActive
        currentLocation {
          name
        }
      }
    }
    """
    
    result = graphql_request(query)
    return result['data']['sensors']

def create_sensor_reading(sensor_id, humidity=None, temperature=None, co2=None):
    """Create a new sensor reading."""
    mutation = """
    mutation CreateReading($input: CreateSensorReadingInput!) {
      createSensorReading(input: $input) {
        success
        message
        errors
        sensorReading {
          id
          readingTime
        }
      }
    }
    """
    
    input_data = {'sensorId': sensor_id}
    if humidity is not None:
        input_data['humidityPercentage'] = humidity
    if temperature is not None:
        input_data['temperatureCelsius'] = temperature
    if co2 is not None:
        input_data['co2Ppm'] = co2
    
    variables = {'input': input_data}
    
    result = graphql_request(mutation, variables)
    return result['data']['createSensorReading']

def get_filtered_readings(start_date=None, end_date=None, location_ids=None, limit=100):
    """Get filtered sensor readings."""
    query = """
    query GetFilteredReadings($filters: SensorDataFilterInput!) {
      filteredSensorReadings(filters: $filters) {
        id
        readingTime
        sensor { name }
        location { name }
        humidityReading { humidityPercentage }
        temperatureReading { temperatureCelsius }
        co2Reading { co2Ppm }
      }
    }
    """
    
    filters = {'limit': limit}
    if start_date:
        filters['startDate'] = start_date
    if end_date:
        filters['endDate'] = end_date
    if location_ids:
        filters['locationIds'] = location_ids
    
    variables = {'filters': filters}
    
    result = graphql_request(query, variables)
    return result['data']['filteredSensorReadings']

# Usage examples
if __name__ == '__main__':
    # Get all sensors
    sensors = get_sensors()
    print(f"Found {len(sensors)} sensors")
    
    # Create a reading for the first sensor
    if sensors:
        reading_result = create_sensor_reading(
            sensor_id=sensors[0]['id'],
            humidity=65.5,
            temperature=23.2,
            co2=1200
        )
        print(f"Created reading: {reading_result}")
    
    # Get recent readings
    recent_readings = get_filtered_readings(limit=10)
    print(f"Found {len(recent_readings)} recent readings")
```

### cURL

```bash
#!/bin/bash

API_URL="http://127.0.0.1:5000/graphql"
JWT_TOKEN="your-jwt-token-here"

# Function to make GraphQL requests
graphql_request() {
    local query="$1"
    local variables="${2:-{}}"
    
    curl -X POST "$API_URL" \
        -H "Content-Type: application/json" \
        -H "Authorization: Bearer $JWT_TOKEN" \
        -d '{
            "query": "'"$query"'",
            "variables": '"$variables"'
        }'
}

# Get sensors
echo "Getting sensors..."
graphql_request '
query GetSensors {
  sensors {
    id
    name
    model
    isActive
  }
}'

echo -e "\n\nCreating sensor reading..."
# Create sensor reading
graphql_request '
mutation CreateReading($input: CreateSensorReadingInput!) {
  createSensorReading(input: $input) {
    success
    message
    sensorReading {
      id
      readingTime
    }
  }
}' '{
  "input": {
    "sensorId": 1,
    "humidityPercentage": 65.5,
    "temperatureCelsius": 23.2,
    "co2Ppm": 1200
  }
}'
```

## Error Handling Examples

### Validation Error Response
```json
{
  "data": {
    "createSensorReading": {
      "success": false,
      "message": "Validation failed",
      "errors": [
        "Sensor with ID 999 does not exist",
        "Humidity must be between 0.0% and 100.0%"
      ],
      "sensorReading": null
    }
  }
}
```

### Authentication Error Response
```json
{
  "errors": [
    {
      "message": "Authentication required",
      "locations": [{"line": 2, "column": 3}],
      "path": ["me"]
    }
  ]
}
```

### Handle Errors in JavaScript
```javascript
async function safeGraphQLRequest(query, variables) {
  try {
    const result = await graphqlRequest(query, variables);
    
    // Check for GraphQL errors
    if (result.errors) {
      console.error('GraphQL Errors:', result.errors);
      return { success: false, errors: result.errors };
    }
    
    // Check for mutation-specific errors
    const mutationResult = Object.values(result.data)[0];
    if (mutationResult && mutationResult.success === false) {
      console.error('Mutation failed:', mutationResult.message);
      return { success: false, errors: mutationResult.errors };
    }
    
    return { success: true, data: result.data };
  } catch (error) {
    console.error('Network error:', error);
    return { success: false, error: error.message };
  }
}
```

## Next Steps

### 1. Explore the Schema
- Use the GraphQL Playground to explore available queries and mutations
- Check out the [API Reference](api-reference.md) for complete documentation

### 2. Set Up Development Environment
- Follow the [README.md](../README.md) for local development setup
- Configure your database and run tests

### 3. Integration Patterns
- Set up error handling and retry logic
- Implement proper token refresh mechanisms
- Consider caching strategies for frequently accessed data

### 4. Production Considerations
- Use environment variables for API URLs and tokens
- Implement proper logging and monitoring
- Set up rate limiting and request timeout handling

### 5. Advanced Features
- Explore complex filtering and aggregation queries
- Set up real-time subscriptions (if available)
- Implement data visualization with the API data

## Support

- **Documentation**: See [docs/](../docs/) folder for complete API documentation
- **Issues**: Report bugs and feature requests in the project repository
- **Development**: Check [CLAUDE.md](../CLAUDE.md) for development guidelines

## Rate Limits

- **Default**: 100 requests per minute
- **GraphQL Complexity**: Max 150 points per query
- **Query Depth**: Maximum 8 levels
- **Timeout**: 30 seconds per request

For higher limits or production use, contact the API administrators.