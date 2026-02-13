from flask import Flask, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_graphql import GraphQLView
from flask_cors import CORS
from typing import Optional, Type
from config import get_config, Config
from app.graphql_security import GraphQLSecurityMiddleware
from app.logging_config import setup_logging
from datetime import datetime
from sqlalchemy import text
import logging
import os

db = SQLAlchemy()

def create_app(config_class: Optional[Type[Config]] = None) -> Flask:
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
                 origins=['http://mini:3000'], 
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
    
    # Initialize authentication system
    from app.auth import init_auth
    init_auth(app)
    
    # Initialize email service
    from app.email_service import init_email_service
    init_email_service(app)
    
    # Health check endpoints for monitoring and load balancers
    @app.route('/health')
    def health_check():
        """Comprehensive health check with database connectivity and pool metrics."""
        health = {
            'status': 'healthy',
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'version': '1.0.0',
            'checks': {}
        }

        # Check database connectivity and get pool metrics
        try:
            db.session.execute(text('SELECT 1'))

            # Get connection pool metrics
            pool = db.engine.pool
            pool_status = {
                'status': 'healthy',
                'size': pool.size(),
                'checked_in': pool.checkedin(),
                'checked_out': pool.checkedout(),
                'overflow': pool.overflow(),
                'invalid': pool.invalidatedcount() if hasattr(pool, 'invalidatedcount') else 0,
            }

            # Warn if pool is nearly exhausted
            max_connections = pool.size() + (getattr(pool, '_max_overflow', 10))
            if pool.checkedout() >= max_connections * 0.8:
                pool_status['warning'] = 'Connection pool nearly exhausted'
                health['status'] = 'degraded'

            health['checks']['database'] = pool_status
        except Exception as e:
            health['status'] = 'unhealthy'
            health['checks']['database'] = {
                'status': 'unhealthy',
                'error': str(e)
            }
            return jsonify(health), 503

        return jsonify(health), 200

    @app.route('/readiness')
    def readiness_check():
        """Readiness probe - can the app serve traffic?"""
        try:
            db.session.execute(text('SELECT 1'))
            return jsonify({'ready': True}), 200
        except Exception:
            return jsonify({'ready': False}), 503

    @app.route('/liveness')
    def liveness_check():
        """Liveness probe - is the app process alive?"""
        return jsonify({'alive': True}), 200

    # Automatic transaction cleanup on request end
    @app.teardown_appcontext
    def cleanup_db_session(exception=None):
        """Roll back uncommitted transactions on error, always remove session."""
        if exception:
            try:
                db.session.rollback()
                app.logger.warning(f"Rolled back transaction due to: {exception}")
            except Exception as e:
                app.logger.error(f"Error during rollback: {e}")
        db.session.remove()

    # Initialize WebSocket support
    from app.events import init_socketio
    init_socketio(app)

    # Log application startup
    if not app.debug:
        app.logger.info('AirQ API startup - GraphQL security enabled with query protection')
    else:
        app.logger.debug('AirQ API startup - Development mode with full GraphQL security')

    return app