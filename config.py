import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        'postgresql://postgres:1883@localhost/airq'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'your-secret-key'
    
    # GraphQL Security Configuration
    GRAPHQL_INTROSPECTION_ENABLED = os.getenv('GRAPHQL_INTROSPECTION', 'false').lower() == 'true'
    GRAPHQL_GRAPHIQL_ENABLED = os.getenv('GRAPHQL_GRAPHIQL', 'false').lower() == 'true'
    GRAPHQL_MAX_DEPTH = int(os.getenv('GRAPHQL_MAX_DEPTH', '8'))
    GRAPHQL_MAX_COMPLEXITY = int(os.getenv('GRAPHQL_MAX_COMPLEXITY', '150'))
    GRAPHQL_TIMEOUT_SECONDS = int(os.getenv('GRAPHQL_TIMEOUT', '30'))
    GRAPHQL_RATE_LIMIT_PER_MINUTE = int(os.getenv('GRAPHQL_RATE_LIMIT_PER_MINUTE', '100'))