from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_graphql import GraphQLView
from flask_cors import CORS
from config import Config
from app.graphql_security import GraphQLSecurityMiddleware
import logging

db = SQLAlchemy()

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)
    CORS(app)

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

    # Configure logging
    if not app.debug:
        logging.basicConfig(level=logging.INFO)
        app.logger.info('AirQ API startup - GraphQL security enabled with query protection')
    else:
        logging.basicConfig(level=logging.DEBUG)
        app.logger.debug('AirQ API startup - Development mode with full GraphQL security')

    return app