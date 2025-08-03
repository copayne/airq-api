# Hudson Air Quality API

## About
The Hudson Air Quality API is a Flask/GraphQL server built to store and serve air quality sensor readings to the Hudson Air Quality App. It features comprehensive authentication, data validation, and a robust GraphQL API for both historical and real-time air quality data.

## 📚 Documentation

- **[Quick Start Guide](docs/quick-start.md)** - Get started with the API in minutes
- **[API Reference](docs/api-reference.md)** - Complete GraphQL schema and endpoint documentation
- **[Data Model](docs/data-model.md)** - Database schema and relationships
- **[Postman Collection](docs/AirQ-API.postman_collection.json)** - Ready-to-use API testing collection

## ✨ Features

- **GraphQL API** with comprehensive queries and mutations
- **JWT Authentication** with role-based access control (Admin, User, Viewer)
- **Data Validation** with range checking and error handling
- **Time-Series Data** with historical sensor location tracking
- **Security Features** including rate limiting and query complexity analysis
- **Comprehensive Testing** with 41+ test cases and coverage reports


## Initialize API on a new machine

## Create Database
Install postgres

```sudo apt-get install postgresql```

Enter postgres and create database
```
sudo -u postgres psql
CREATE DATABASE sensor_readings;
```

If needed, updated password for db user
```
ALTER USER postgres WITH PASSWORD {{new_password}};
```
Exit postgres

```\q```


## Setup API
### Setup SSH key with github on machine
Run ```ssh-keygen``` on machine

Navigate to file (/.ssh by default)

Run ```cat id_rsa.pub``` and copy contents

Create new key under settings/SSH and GPG Keys

Copy contens to github key and save

### Clone repository on machine
```git clone git@github.com:copayne/airq-api.git```

### Create virtual environment
Ensure python3 is installed

```
sudo apt-get update
sudo apt-get install python3 python3-pip
```

Install virtualenv

```pip install virtualenv```

Navigate to app folder and create environment
```
python3 -m venv {{env_name}}
source {{env_name}/bin/activate
```

### Install dependencies
```pip install -r requirements.txt```

### Initialize database
Run the following command to initialize the database

```python3 init_db.py```

(Optional) Run dummy data script to see database

```python3 db-dummy-data.py```

### Start app
```python3 run.py```

### Check status
- Open browser and navigate to http://127.0.0.1:5000/graphql
- Should open to graphql utility tool.

## Testing

The project includes comprehensive test coverage with unit tests, integration tests, and security tests.

### Prerequisites
Make sure you have activated your virtual environment and installed all dependencies:
```bash
source {{env_name}}/bin/activate
pip install -r requirements.txt
```

### Running Tests

#### Run All Tests
```bash
pytest
```

#### Run Tests with Coverage Report
```bash
pytest --cov=app --cov-report=term-missing --cov-report=html
```

#### Run Specific Test Categories
```bash
# Unit tests only
pytest -m unit

# Integration tests only  
pytest -m integration

# Run tests in a specific file
pytest tests/unit/test_models.py

# Run a specific test
pytest tests/integration/test_graphql_api.py::TestGraphQLQueries::test_sensors_query
```

#### Run Tests in Verbose Mode
```bash
pytest -v
```

### Test Structure

- **`tests/unit/`** - Unit tests for database models and business logic
- **`tests/integration/`** - Integration tests for GraphQL API endpoints
- **`tests/conftest.py`** - Test configuration and fixtures

### Test Database

Tests use an in-memory SQLite database that is automatically created and destroyed for each test session. This ensures tests are fast and isolated.

### Coverage Reports

After running tests with coverage, you can view the HTML coverage report:
```bash
open htmlcov/index.html  # On macOS
xdg-open htmlcov/index.html  # On Linux
```

The project maintains a minimum coverage threshold of 80%.

### Test Fixtures

The test suite includes comprehensive fixtures for:
- Sample sensors, locations, and sensor readings
- Complete measurement data (humidity, temperature, CO2)
- GraphQL query execution helpers
- Database session management with automatic rollback

### Security Testing

Integration tests include security verification for:
- GraphQL query depth limiting
- Query complexity analysis
- Malformed query handling
- Missing parameter validation