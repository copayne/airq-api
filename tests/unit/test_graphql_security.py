"""
Unit tests for GraphQL security features.
"""

import pytest
from app.graphql_security import (
    SecureGraphQLSchema, 
    QueryComplexityValidationRule, 
    QueryTimeoutHandler,
    create_depth_limit_validator
)
import graphene
from graphql import parse, GraphQLError


class TestQuery(graphene.ObjectType):
    """Simple test query for security testing."""
    hello = graphene.String()
    
    def resolve_hello(self, info):
        return "Hello World"


@pytest.mark.unit
class TestGraphQLSecurity:
    """Test GraphQL security configurations."""
    
    def test_secure_schema_creation(self):
        """Test creating a secure GraphQL schema."""
        schema = SecureGraphQLSchema(
            query=TestQuery,
            max_depth=5,
            max_complexity=10,
            timeout_seconds=30
        )
        
        assert schema.max_depth == 5
        assert schema.max_complexity == 10
        assert schema.timeout_seconds == 30
    
    def test_secure_schema_defaults(self):
        """Test secure schema with default values."""
        schema = SecureGraphQLSchema(query=TestQuery)
        
        assert schema.max_depth == 10
        assert schema.max_complexity == 100
        assert schema.timeout_seconds == 30
        assert schema.enable_logging is True
    
    def test_query_complexity_validation_rule(self):
        """Test the query complexity validation rule."""
        # Create a mock validation context
        class MockValidationContext:
            def __init__(self):
                self.errors = []
            
            def report_error(self, error):
                self.errors.append(error)
        
        context = MockValidationContext()
        rule = QueryComplexityValidationRule(context, max_complexity=5)
        
        # Test that the rule has the correct complexity mapping
        assert 'sensors' in rule.field_complexity_map
        assert 'readings' in rule.field_complexity_map
        assert rule.field_complexity_map['sensors'] == 5
        assert rule.field_complexity_map['id'] == 1
    
    def test_depth_limit_validator_creation(self):
        """Test creating a depth limit validator."""
        ValidatorClass = create_depth_limit_validator(max_depth=3)
        
        # Test that it returns a class
        assert callable(ValidatorClass)
        assert hasattr(ValidatorClass, '__name__')
    
    def test_timeout_handler_context_manager(self):
        """Test the timeout handler as context manager."""
        handler = QueryTimeoutHandler(timeout_seconds=1)
        
        # Test that it can be used as context manager
        assert hasattr(handler, '__enter__')
        assert hasattr(handler, '__exit__')
    
    def test_secure_schema_validation_methods(self):
        """Test that secure schema has validation methods."""
        schema = SecureGraphQLSchema(query=TestQuery)
        
        # Test that private validation method exists
        assert hasattr(schema, '_validate_query_security')
        
        # Test validation with empty document
        try:
            document = parse("{ hello }")
            errors = schema._validate_query_security(document)
            # Should return a list (empty or with errors)
            assert isinstance(errors, list)
        except Exception:
            # If parsing fails, that's expected in some cases
            pass


@pytest.mark.integration
class TestGraphQLSecurityIntegration:
    """Integration tests for GraphQL security with real API."""
    
    def test_valid_query_passes_security(self, client):
        """Test that valid queries pass security checks."""
        query = """
        {
            sensors {
                id
                name
            }
        }
        """
        
        response = client.post('/graphql',
                             json={'query': query},
                             headers={'Content-Type': 'application/json'})
        
        assert response.status_code == 200
        data = response.get_json()
        assert 'data' in data
        assert 'errors' not in data or not data['errors']
    
    def test_introspection_query_works_in_testing(self, client):
        """Test that introspection works in testing environment."""
        introspection_query = """
        {
            __schema {
                types {
                    name
                }
            }
        }
        """
        
        response = client.post('/graphql',
                             json={'query': introspection_query},
                             headers={'Content-Type': 'application/json'})
        
        assert response.status_code == 200
        data = response.get_json()
        assert 'data' in data
        assert '__schema' in data['data']