from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_graphql import GraphQLView
from flask_cors import CORS
from typing import Optional, Type
from config import get_config, Config
from app.graphql_security import GraphQLSecurityMiddleware
from app.logging_config import setup_logging
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
    
    # Image serving route for Ring snapshots
    from flask import send_file, abort
    from app.models import RingSnapshot

    @app.route('/api/ring-snapshots/<int:snapshot_id>')
    def serve_ring_snapshot(snapshot_id: int):
        """Serve Ring camera snapshot image by ID."""
        snapshot = RingSnapshot.query.get(snapshot_id)

        if not snapshot:
            abort(404, description="Snapshot not found")

        if not os.path.exists(snapshot.image_path):
            app.logger.error(
                f"Ring snapshot image file not found",
                extra={
                    'extra_context': {
                        'snapshot_id': snapshot_id,
                        'image_path': snapshot.image_path,
                        'operation': 'serve_ring_snapshot_missing_file'
                    }
                }
            )
            abort(404, description="Snapshot image file not found")

        try:
            return send_file(
                snapshot.image_path,
                mimetype='image/jpeg',
                as_attachment=False,
                download_name=f"ring_snapshot_{snapshot_id}.jpg"
            )
        except Exception as e:
            app.logger.error(
                f"Failed to serve Ring snapshot",
                exc_info=True,
                extra={
                    'extra_context': {
                        'snapshot_id': snapshot_id,
                        'error_type': type(e).__name__,
                        'operation': 'serve_ring_snapshot_error'
                    }
                }
            )
            abort(500, description="Failed to serve snapshot image")

    # Initialize WebSocket support
    from app.events import init_socketio
    init_socketio(app)

    # Log application startup
    if not app.debug:
        app.logger.info('AirQ API startup - GraphQL security enabled with query protection')
    else:
        app.logger.debug('AirQ API startup - Development mode with full GraphQL security')

    return app