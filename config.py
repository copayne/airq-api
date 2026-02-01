import os
import secrets
from typing import Type, Union
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Database Configuration - Required environment variable
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL')
    if not SQLALCHEMY_DATABASE_URI:
        raise ValueError("DATABASE_URL environment variable is required")
    
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Connection Pooling Configuration for Performance
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_pre_ping': True,          # Verify connections before use
        'pool_recycle': 300,            # Recycle connections after 5 minutes
        'pool_timeout': 20,             # Connection timeout in seconds
        'pool_size': 10,                # Number of connections to maintain
        'max_overflow': 20              # Additional connections allowed
    }
    
    # Security Configuration - Required environment variable
    SECRET_KEY = os.environ.get('SECRET_KEY')
    if not SECRET_KEY:
        raise ValueError("SECRET_KEY environment variable is required. Generate with: python -c 'import secrets; print(secrets.token_hex(32))'")
    
    # Environment Configuration
    FLASK_ENV = os.getenv('FLASK_ENV', 'production')
    
    # CORS Configuration
    CORS_ORIGINS = os.getenv('CORS_ORIGINS', '').split(',') if os.getenv('CORS_ORIGINS') else []
    CORS_SUPPORTS_CREDENTIALS = os.getenv('CORS_CREDENTIALS', 'false').lower() == 'true'
    
    # GraphQL Security Configuration
    GRAPHQL_INTROSPECTION_ENABLED = os.getenv('GRAPHQL_INTROSPECTION', 'false').lower() == 'true'
    GRAPHQL_GRAPHIQL_ENABLED = os.getenv('GRAPHQL_GRAPHIQL', 'false').lower() == 'true'
    GRAPHQL_MAX_DEPTH = int(os.getenv('GRAPHQL_MAX_DEPTH', '8'))
    GRAPHQL_MAX_COMPLEXITY = int(os.getenv('GRAPHQL_MAX_COMPLEXITY', '150'))
    GRAPHQL_TIMEOUT_SECONDS = int(os.getenv('GRAPHQL_TIMEOUT', '30'))
    GRAPHQL_RATE_LIMIT_PER_MINUTE = int(os.getenv('GRAPHQL_RATE_LIMIT_PER_MINUTE', '100'))
    
    # Email Configuration
    SMTP_SERVER = os.getenv('SMTP_SERVER', 'localhost')
    SMTP_PORT = int(os.getenv('SMTP_PORT', '587'))
    SMTP_USERNAME = os.getenv('SMTP_USERNAME')
    SMTP_PASSWORD = os.getenv('SMTP_PASSWORD')
    SMTP_USE_TLS = os.getenv('SMTP_USE_TLS', 'true').lower() == 'true'
    FROM_EMAIL = os.getenv('FROM_EMAIL', 'noreply@airq.local')
    BASE_URL = os.getenv('BASE_URL', 'http://localhost:3000')
    MOCK_EMAIL = os.getenv('MOCK_EMAIL', 'true').lower() == 'true'
    SAVE_MOCK_EMAILS = os.getenv('SAVE_MOCK_EMAILS', 'false').lower() == 'true'

    # WebSocket Configuration
    SOCKETIO_ASYNC_MODE = os.getenv('SOCKETIO_ASYNC_MODE', 'threading')

class DevelopmentConfig(Config):
    """Development environment configuration with relaxed security for testing."""
    # Override for development - allow more permissive settings
    GRAPHQL_INTROSPECTION_ENABLED = os.getenv('GRAPHQL_INTROSPECTION', 'true').lower() == 'true'
    GRAPHQL_GRAPHIQL_ENABLED = os.getenv('GRAPHQL_GRAPHIQL', 'true').lower() == 'true'
    GRAPHQL_MAX_DEPTH = int(os.getenv('GRAPHQL_MAX_DEPTH', '15'))
    GRAPHQL_MAX_COMPLEXITY = int(os.getenv('GRAPHQL_MAX_COMPLEXITY', '200'))
    
class ProductionConfig(Config):
    """Production environment configuration with strict security."""
    # Enforce strict production settings
    GRAPHQL_INTROSPECTION_ENABLED = False
    GRAPHQL_GRAPHIQL_ENABLED = False

class TestingConfig(Config):
    """Testing environment configuration with in-memory database."""
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    WTF_CSRF_ENABLED = False
    
    # SQLite doesn't support connection pooling - remove those options
    SQLALCHEMY_ENGINE_OPTIONS = {}
    
    # Enable GraphQL introspection and GraphiQL for testing
    GRAPHQL_INTROSPECTION_ENABLED = True
    GRAPHQL_GRAPHIQL_ENABLED = True
    
    # Relaxed security settings for testing
    GRAPHQL_MAX_DEPTH = 20
    GRAPHQL_MAX_COMPLEXITY = 500
    GRAPHQL_TIMEOUT_SECONDS = 60
    
    # Override secret key for testing
    SECRET_KEY = 'test-secret-key-not-for-production'
    
# Configuration mapping
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': Config
}

def get_config() -> Type[Config]:
    """Get configuration class based on FLASK_ENV."""
    env = os.getenv('FLASK_ENV', 'production')
    return config.get(env, config['default'])