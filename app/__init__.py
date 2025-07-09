from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_graphql import GraphQLView
from flask_cors import CORS
from config import get_config
from app.graphql_security import GraphQLSecurityMiddleware
from app.logging_config import setup_logging
import logging
import os

db = SQLAlchemy()

def create_app(config_class=None):
    app = Flask(__name__)
    
    # Use environment-based configuration if no config class provided
    if config_class is None:
        config_class = get_config()
    
    app.config.from_object(config_class)

    db.init_app(app)
    
    # Configure CORS with environment-based settings
    cors_origins = app.config.get('CORS_ORIGINS', [])
    cors_credentials = app.config.get('CORS_SUPPORTS_CREDENTIALS', False)
    
    if cors_origins:
        CORS(app, 
             origins=cors_origins, 
             supports_credentials=cors_credentials,
             allow_headers=['Content-Type', 'Authorization'],
             methods=['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'])
    else:
        # Default to localhost for development, no CORS for production
        flask_env = app.config.get('FLASK_ENV', 'production')
        if flask_env == 'development':
            CORS(app, 
                 origins=['http://mini.local:3000'], 
                 supports_credentials=False,
                 allow_headers=['Content-Type', 'Authorization'],
                 methods=['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'])
        # No CORS configuration for production - must be explicitly configured

    # Initialize GraphQL security middleware
    security_middleware = GraphQLSecurityMiddleware(
        app=app,
        requests_per_minute=app.config.get('GRAPHQL_RATE_LIMIT_PER_MINUTE', 100)
    )

    from app.schema import schema
    
    # Configure GraphQL endpoint with security settings
    graphql_view = GraphQLView.as_view(
        'graphql',
        schema=schema,
        graphiql=app.config.get('GRAPHQL_GRAPHIQL_ENABLED', False),
        introspection=app.config.get('GRAPHQL_INTROSPECTION_ENABLED', False)
    )
    
    app.add_url_rule('/graphql', view_func=graphql_view)

    # Configure structured logging with database persistence
    setup_logging(app, db)
    
    # Log application startup
    if not app.debug:
        app.logger.info('AirQ API startup - GraphQL security enabled with query protection')
    else:
        app.logger.debug('AirQ API startup - Development mode with full GraphQL security')

    return app