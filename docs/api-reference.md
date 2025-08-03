# AirQ API GraphQL Reference

Complete reference for the Hudson Air Quality API GraphQL endpoint.

## Table of Contents
- [Authentication](#authentication)
- [GraphQL Endpoint](#graphql-endpoint)
- [Queries](#queries)
- [Mutations](#mutations)
- [Input Types](#input-types)
- [Output Types](#output-types)
- [Error Handling](#error-handling)
- [Data Validation](#data-validation)

## Authentication

The API uses JWT (JSON Web Token) authentication. Include your token in the Authorization header:

```
Authorization: Bearer <your-jwt-token>
```

### Getting a Token

Use the `loginUser` or `registerUser` mutations to obtain a JWT token.

## GraphQL Endpoint

**URL:** `/graphql`  
**Method:** `POST`  
**Content-Type:** `application/json`

### Development Environment
```
http://127.0.0.1:5000/graphql
```

## Queries

### Basic Queries

#### `sensors`
Get all sensors in the system.

```graphql
query GetSensors {
  sensors {
    id
    name
    model
    isActive
    currentLocation {
      id
      name
    }
    lastReading {
      id
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
}
```

#### `locations`
Get all locations where sensors can be placed.

```graphql
query GetLocations {
  locations {
    id
    name
    description
    currentSensors {
      id
      name
      model
    }
  }
}
```

#### `sensorReadings`
Get recent sensor readings (limited to 1000 most recent).

```graphql
query GetRecentReadings {
  sensorReadings {
    id
    readingTime
    sensor {
      name
      model
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

### Advanced Queries

#### `filteredSensorReadings`
Get sensor readings with filtering, ordering, and pagination.

```graphql
query GetFilteredReadings($filters: SensorDataFilterInput!) {
  filteredSensorReadings(filters: $filters) {
    id
    readingTime
    sensor {
      name
      model
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

**Variables Example:**
```json
{
  "filters": {
    "startDate": "2024-01-01T00:00:00Z",
    "endDate": "2024-01-31T23:59:59Z",
    "minCo2Ppm": 400,
    "maxCo2Ppm": 2000,
    "sensorIds": [1, 2, 3],
    "orderBy": "reading_time",
    "orderDirection": "desc",
    "limit": 50,
    "offset": 0
  }
}
```

### Authentication Queries

#### `me`
Get current authenticated user information.

```graphql
query GetCurrentUser {
  me {
    id
    username
    email
    role
    fullName
    createdAt
    lastLogin
  }
}
```

#### `users` (Admin Only)
Get all users in the system (requires admin role).

```graphql
query GetAllUsers {
  users {
    id
    username
    email
    role
    fullName
    isActive
    createdAt
    lastLogin
  }
}
```

## Mutations

### Sensor Data Mutations

#### `createSensorReading`
Create a new sensor reading with validation.

```graphql
mutation CreateSensorReading($input: CreateSensorReadingInput!) {
  createSensorReading(input: $input) {
    success
    message
    errors
    sensorReading {
      id
      readingTime
      sensor {
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
```

**Variables Example:**
```json
{
  "input": {
    "sensorId": 1,
    "humidityPercentage": 65.5,
    "temperatureCelsius": 23.2,
    "co2Ppm": 1200
  }
}
```

### Authentication Mutations

#### `registerUser`
Register a new user account.

```graphql
mutation RegisterUser($input: RegisterInput!) {
  registerUser(input: $input) {
    success
    message
    user {
      id
      username
      email
      fullName
      role
    }
    token
  }
}
```

**Variables Example:**
```json
{
  "input": {
    "username": "newuser",
    "email": "user@example.com",
    "password": "securepassword123",
    "firstName": "John",
    "lastName": "Doe"
  }
}
```

#### `loginUser`
Authenticate and receive a JWT token.

```graphql
mutation LoginUser($input: LoginInput!) {
  loginUser(input: $input) {
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

**Variables Example:**
```json
{
  "input": {
    "usernameOrEmail": "newuser",
    "password": "securepassword123"
  }
}
```

#### `verifyEmail`
Verify user email address with verification token.

```graphql
mutation VerifyEmail($input: EmailVerificationInput!) {
  verifyEmail(input: $input) {
    success
    message
  }
}
```

**Variables Example:**
```json
{
  "input": {
    "token": "verification_token_from_email"
  }
}
```

#### `requestPasswordReset`
Request a password reset email.

```graphql
mutation RequestPasswordReset($input: PasswordResetRequestInput!) {
  requestPasswordReset(input: $input) {
    success
    message
  }
}
```

**Variables Example:**
```json
{
  "input": {
    "email": "user@example.com"
  }
}
```

#### `resetPassword`
Reset password with reset token.

```graphql
mutation ResetPassword($input: PasswordResetInput!) {
  resetPassword(input: $input) {
    success
    message
  }
}
```

**Variables Example:**
```json
{
  "input": {
    "token": "reset_token_from_email",
    "newPassword": "newSecurePassword123"
  }
}
```

#### `logoutUser`
Logout user by blacklisting their JWT token.

```graphql
mutation LogoutUser($input: LogoutInput!) {
  logoutUser(input: $input) {
    success
    message
  }
}
```

**Variables Example:**
```json
{
  "input": {
    "token": "jwt_token_to_blacklist"
  }
}
```

## Input Types

### `SensorDataFilterInput`
Filtering options for sensor readings.

| Field | Type | Description |
|-------|------|-------------|
| `startDate` | DateTime | Filter readings after this date |
| `endDate` | DateTime | Filter readings before this date |
| `minCo2Ppm` | Float | Minimum CO2 level (ppm) |
| `maxCo2Ppm` | Float | Maximum CO2 level (ppm) |
| `minTemperatureCelsius` | Float | Minimum temperature (°C) |
| `maxTemperatureCelsius` | Float | Maximum temperature (°C) |
| `minHumidityPercentage` | Float | Minimum humidity (%) |
| `maxHumidityPercentage` | Float | Maximum humidity (%) |
| `sensorIds` | [ID] | Filter by specific sensor IDs |
| `locationIds` | [ID] | Filter by specific location IDs |
| `orderBy` | String | Field to order by (reading_time, co2_ppm, etc.) |
| `orderDirection` | String | Order direction (asc, desc) |
| `limit` | Int | Maximum number of results |
| `offset` | Int | Number of results to skip |

### `CreateSensorReadingInput`
Input for creating sensor readings.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `sensorId` | Int | ✅ | ID of the sensor taking the reading |
| `humidityPercentage` | Float | ❌ | Humidity reading (0-100%) |
| `temperatureCelsius` | Float | ❌ | Temperature reading (-40-85°C) |
| `co2Ppm` | Int | ❌ | CO2 reading (0-50000 ppm) |

### `RegisterInput`
Input for user registration.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `username` | String | ✅ | Username (3-50 characters, alphanumeric + _ - only) |
| `email` | String | ✅ | Valid email address |
| `password` | String | ✅ | Password (8-128 characters) |
| `firstName` | String | ❌ | First name (max 50 characters) |
| `lastName` | String | ❌ | Last name (max 50 characters) |

### `LoginInput`
Input for user authentication.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `usernameOrEmail` | String | ✅ | Username or email address |
| `password` | String | ✅ | User password |

### `EmailVerificationInput`
Input for email verification.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `token` | String | ✅ | Email verification token from email |

### `PasswordResetRequestInput`
Input for password reset request.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `email` | String | ✅ | Email address to send reset link to |

### `PasswordResetInput`
Input for password reset.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `token` | String | ✅ | Password reset token from email |
| `newPassword` | String | ✅ | New password (8-128 characters) |

### `LogoutInput`
Input for user logout.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `token` | String | ✅ | JWT token to blacklist |

## Output Types

### `SensorReadingObject`
Represents a sensor reading with all measurement data.

| Field | Type | Description |
|-------|------|-------------|
| `id` | ID | Unique reading identifier |
| `readingTime` | DateTime | When the reading was taken |
| `sensor` | SensorObject | Sensor that took the reading |
| `location` | LocationObject | Location where reading was taken |
| `humidityReading` | HumidityReadingObject | Humidity measurement data |
| `temperatureReading` | TemperatureReadingObject | Temperature measurement data |
| `co2Reading` | CO2ReadingObject | CO2 measurement data |

### `SensorObject`
Represents a physical sensor device.

| Field | Type | Description |
|-------|------|-------------|
| `id` | ID | Unique sensor identifier |
| `name` | String | Sensor name |
| `model` | String | Sensor model information |
| `isActive` | Boolean | Whether sensor is currently active |
| `currentLocation` | LocationObject | Current sensor location |
| `lastReading` | SensorReadingObject | Most recent reading from sensor |

### `UserObject`
Represents a user account.

| Field | Type | Description |
|-------|------|-------------|
| `id` | ID | Unique user identifier |
| `username` | String | User's username |
| `email` | String | User's email address |
| `emailVerified` | Boolean | Whether email address is verified |
| `role` | String | User role (admin, user, viewer) |
| `fullName` | String | Computed full name |
| `firstName` | String | User's first name |
| `lastName` | String | User's last name |
| `isActive` | Boolean | Whether account is active |
| `createdAt` | DateTime | Account creation timestamp |
| `lastLogin` | DateTime | Last login timestamp |

### `AuthPayload`
Authentication response containing user info and token.

| Field | Type | Description |
|-------|------|-------------|
| `success` | Boolean | Whether operation succeeded |
| `message` | String | Success or error message |
| `user` | UserObject | User information (if successful) |
| `token` | String | JWT token (if successful) |

## Error Handling

### Authentication Errors
```json
{
  "errors": [
    {
      "message": "Authentication required",
      "locations": [{"line": 2, "column": 3}],
      "path": ["users"]
    }
  ]
}
```

### Validation Errors
Validation errors return structured information:

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

### Common Error Types
- **Authentication Required**: Missing or invalid JWT token
- **Insufficient Permissions**: User role lacks required permissions
- **Validation Failed**: Input data doesn't meet validation requirements
- **Resource Not Found**: Requested sensor, location, or user doesn't exist
- **Database Error**: Internal server error during data operation

## Data Validation

### Sensor Reading Validation

| Field | Valid Range | Notes |
|-------|-------------|-------|
| Humidity | 0.0% - 100.0% | Max 2 decimal places |
| Temperature | -40.0°C - 85.0°C | Max 2 decimal places |
| CO2 | 0 - 50,000 ppm | Whole numbers only |

### Requirements
- At least one measurement (humidity, temperature, or CO2) must be provided
- Sensor must exist and be active
- Values must be finite numbers (no NaN or infinity)

### User Validation

| Field | Validation Rules |
|-------|------------------|
| Username | 3-50 characters, alphanumeric + underscore + hyphen only |
| Email | Valid email format with @ and domain |
| Password | 8-128 characters |
| Names | Max 50 characters each |

## Rate Limiting

- **Default**: 100 requests per minute per IP address
- **GraphQL Complexity**: Max complexity of 150 points per query
- **Query Depth**: Maximum 8 levels of nesting
- **Timeout**: 30 seconds per request

## Security Features

### Authentication & Authorization
- JWT token authentication with expiration (1 hour default)
- Role-based access control (admin, user, viewer)
- Token blacklisting for secure logout
- Email verification for new accounts
- Account locking after failed login attempts (5 attempts = 30 minute lock)
- Secure password reset with time-limited tokens

### Data Protection
- Password hashing with bcrypt
- Sensitive security fields excluded from GraphQL responses
- Input validation and sanitization
- SQL injection prevention with parameterized queries

### API Security
- GraphQL query complexity analysis (max 150 points)
- Query depth limiting (max 8 levels)
- Request timeout protection (30 seconds)
- Rate limiting (100 requests/minute per IP)
- CORS policy enforcement
- Security headers (X-Content-Type-Options, X-Frame-Options, X-XSS-Protection)

### Email Security
- Mock email mode for development/testing
- Secure token generation for verification and reset links
- Email enumeration prevention (consistent responses)
- Time-limited verification tokens (24 hours for email, 1 hour for password reset)

### Production Security
- Environment-based configuration
- Required SECRET_KEY validation
- Introspection and GraphiQL disabled in production
- Comprehensive security logging and monitoring

## Email Configuration

The API supports both SMTP and mock email modes for different environments:

### Environment Variables
- `MOCK_EMAIL`: Set to "true" for development (default: true)
- `SMTP_SERVER`: SMTP server hostname
- `SMTP_PORT`: SMTP server port (default: 587)
- `SMTP_USERNAME`: SMTP authentication username
- `SMTP_PASSWORD`: SMTP authentication password
- `SMTP_USE_TLS`: Enable TLS encryption (default: true)
- `FROM_EMAIL`: From address for outgoing emails
- `BASE_URL`: Frontend base URL for email links

### Mock Email Mode
In development, emails are logged instead of sent. Set `SAVE_MOCK_EMAILS=true` to save emails to files for testing.

## Account Security Flow

### Registration Flow
1. User registers with email and password
2. Account created with `emailVerified=false`
3. Verification email sent with 24-hour token
4. User clicks email link to verify account
5. Account gains full access

### Password Reset Flow
1. User requests password reset with email
2. Reset email sent with 1-hour token (if account exists)
3. User clicks email link and sets new password
4. Failed login attempts reset, account unlocked
5. All existing tokens remain valid (user should re-login)

### Account Locking
- 5 failed login attempts trigger 30-minute account lock
- Lock automatically expires after timeout
- Successful login or password reset clears failed attempts
- Account lock status checked before password verification

### Token Management
- JWT tokens include unique JTI for blacklisting
- Logout mutation blacklists current token
- Token verification checks blacklist status
- Expired blacklisted tokens cleaned up automatically