"""
GraphQL Security Middleware and Validation
Implements query depth limiting, complexity analysis, and timeout protection
"""

import graphene
import signal
import time
from typing import Optional, Dict, Any, List, Callable, Type
from graphql import GraphQLError, parse, validate
from graphql.validation.rules.base import ValidationRule
from graphql.language import ast
from flask import Flask
import logging

logger = logging.getLogger(__name__)


def create_depth_limit_validator(max_depth: int) -> Type[ValidationRule]:
    """
    Creates a depth limiting validation rule for older GraphQL versions.
    """
    class DepthLimitValidationRule(ValidationRule):
        def __init__(self, validation_context):
            super().__init__(validation_context)
            self.max_depth = max_depth
            self.current_depth = 0
            
        def enter_field(self, node, *_args):
            self.current_depth += 1
            if self.current_depth > self.max_depth:
                self.report_error(
                    GraphQLError(
                        f"Query depth {self.current_depth} exceeds maximum allowed depth of {self.max_depth}",
                        nodes=[node]
                    )
                )
        
        def leave_field(self, node, *_args):
            self.current_depth -= 1
    
    return DepthLimitValidationRule


class QueryComplexityValidationRule(ValidationRule):
    """
    Validates GraphQL query complexity to prevent resource exhaustion attacks.
    Assigns complexity scores to fields and rejects queries exceeding limits.
    """
    
    def __init__(self, validation_context, max_complexity: int = 100):
        super().__init__(validation_context)
        self.max_complexity = max_complexity
        self.current_complexity = 0
        self.field_complexity_map = {
            # Basic fields
            'id': 1,
            'name': 1,
            'reading_time': 1,
            'installation_date': 1,
            
            # Relationship fields (more expensive)
            'sensor': 3,
            'location': 3,
            'readings': 5,
            'sensors': 5,
            'locations': 5,
            'current_sensors': 5,
            'last_reading': 3,
            
            # Measurement fields
            'humidity_reading': 2,
            'temperature_reading': 2,
            'co2_reading': 2,
            
            # High-cost operations
            'filtered_sensor_readings': 10,
            'sensor_readings': 8,
            'humidity_readings': 8,
            'temperature_readings': 8,
            'co2_readings': 8,
            'error_logs': 5,
        }
    
    def enter_field(self, node, *_args):
        field_name = node.name.value
        field_complexity = self.field_complexity_map.get(field_name, 1)
        
        # Increase complexity based on arguments
        if hasattr(node, 'arguments') and node.arguments:
            for arg in node.arguments:
                if arg.name.value == 'limit':
                    # Higher limits increase complexity
                    try:
                        limit_value = int(arg.value.value) if hasattr(arg.value, 'value') else 100
                        # Apply complexity multiplier based on limit
                        multiplier = min(limit_value / 10, 5)  # Cap at 5x multiplier
                        field_complexity = int(field_complexity * multiplier)
                    except (ValueError, AttributeError):
                        pass
        
        self.current_complexity += field_complexity
        
        if self.current_complexity > self.max_complexity:
            self.report_error(
                GraphQLError(
                    f"Query complexity {self.current_complexity} exceeds maximum allowed complexity of {self.max_complexity}",
                    nodes=[node]
                )
            )


class QueryTimeoutHandler:
    """
    Handles query execution timeouts to prevent long-running queries from blocking the server.
    Uses signal-based timeout for synchronous execution.
    """
    
    def __init__(self, timeout_seconds: int = 30):
        """Initialize timeout handler with specified timeout duration.
        
        Args:
            timeout_seconds: Maximum execution time before timeout
        """
        self.timeout_seconds = timeout_seconds
        self.original_handler = None
    
    def __enter__(self):
        """Enter context manager and set up timeout alarm."""
        def timeout_handler(signum, frame):
            raise GraphQLError(f"Query execution timed out after {self.timeout_seconds} seconds")
        
        self.original_handler = signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(self.timeout_seconds)
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit context manager and clean up timeout alarm."""
        signal.alarm(0)  # Cancel the alarm
        if self.original_handler is not None:
            signal.signal(signal.SIGALRM, self.original_handler)


class SecureGraphQLSchema(graphene.Schema):
    """
    Enhanced GraphQL Schema with built-in security protections:
    - Query depth limiting
    - Query complexity analysis
    - Execution timeout protection
    - Security logging
    """
    
    def __init__(self, *args, **kwargs):
        # Extract security configuration
        self.max_depth = kwargs.pop('max_depth', 10)
        self.max_complexity = kwargs.pop('max_complexity', 100)
        self.timeout_seconds = kwargs.pop('timeout_seconds', 30)
        self.enable_logging = kwargs.pop('enable_security_logging', True)
        
        super().__init__(*args, **kwargs)
        
        if self.enable_logging:
            logger.info(f"SecureGraphQLSchema initialized with max_depth={self.max_depth}, "
                       f"max_complexity={self.max_complexity}, timeout={self.timeout_seconds}s")
    
    def execute(self, *args, **kwargs):
        """
        Enhanced execute method with security validations and monitoring.
        """
        start_time = time.time()
        
        # Skip validation for introspection queries or when no source provided
        if "source" not in kwargs or not kwargs["source"]:
            return super().execute(*args, **kwargs)
        
        query_source = kwargs["source"]
        
        # Log query attempt if logging enabled
        if self.enable_logging:
            logger.debug(f"Executing GraphQL query: {query_source[:200]}{'...' if len(query_source) > 200 else ''}")
        
        # Parse the query
        try:
            document = parse(query_source)
        except Exception as error:
            if self.enable_logging:
                logger.warning(f"Query parsing failed: {str(error)}")
            # Return error in format compatible with older GraphQL version
            return {"data": None, "errors": [{"message": f"Query parsing error: {str(error)}"}]}
        
        # Apply security validations
        validation_errors = self._validate_query_security(document)
        
        if validation_errors:
            if self.enable_logging:
                logger.warning(f"Query validation failed: {[str(e) for e in validation_errors]}")
            # Return error in format compatible with older GraphQL version
            return {"data": None, "errors": [{"message": str(e)} for e in validation_errors]}
        
        # Execute with timeout protection
        try:
            with QueryTimeoutHandler(self.timeout_seconds):
                result = super().execute(*args, **kwargs)
        except GraphQLError as error:
            if self.enable_logging:
                logger.warning(f"Query execution failed: {str(error)}")
            return {"data": None, "errors": [{"message": str(error)}]}
        except Exception as error:
            if self.enable_logging:
                logger.error(f"Unexpected query execution error: {str(error)}")
            return {"data": None, "errors": [{"message": "Internal server error"}]}
        
        # Log successful execution
        if self.enable_logging:
            execution_time = time.time() - start_time
            logger.info(f"Query executed successfully in {execution_time:.3f}s")
        
        return result
    
    def _validate_query_security(self, document) -> list:
        """
        Apply all security validation rules to the parsed query document.
        """
        validation_rules = []
        
        # Add depth limiting validation
        if self.max_depth > 0:
            validation_rules.append(create_depth_limit_validator(max_depth=self.max_depth))
        
        # Add complexity validation
        if self.max_complexity > 0:
            def complexity_rule_factory(validation_context):
                return QueryComplexityValidationRule(validation_context, self.max_complexity)
            validation_rules.append(complexity_rule_factory)
        
        # Run all validations
        try:
            validation_errors = validate(
                schema=self.graphql_schema,
                document_ast=document,
                rules=validation_rules
            )
        except Exception as e:
            # If validation fails, return error
            logger.error(f"Validation error: {str(e)}")
            return [GraphQLError(f"Query validation failed: {str(e)}")]
        
        return validation_errors


class GraphQLSecurityMiddleware:
    """
    Flask middleware for additional GraphQL security features:
    - Request rate limiting
    - Query logging and monitoring
    - Security headers
    """
    
    def __init__(self, app=None, requests_per_minute: int = 100):
        self.requests_per_minute = requests_per_minute
        self.request_counts: Dict[str, Dict[str, Any]] = {}
        
        if app is not None:
            self.init_app(app)
    
    def init_app(self, app):
        """Initialize the middleware with Flask app."""
        app.before_request(self._before_request)
        app.after_request(self._after_request)
    
    def _before_request(self):
        """Pre-request processing for rate limiting and logging."""
        from flask import request, abort, g
        
        # Only apply to GraphQL endpoints
        if not request.endpoint or 'graphql' not in request.endpoint:
            return
        
        # Simple rate limiting by IP
        client_ip = request.remote_addr
        current_time = time.time()
        current_minute = int(current_time // 60)
        
        if client_ip not in self.request_counts:
            self.request_counts[client_ip] = {}
        
        # Clean old entries
        for minute in list(self.request_counts[client_ip].keys()):
            if minute < current_minute - 1:
                del self.request_counts[client_ip][minute]
        
        # Count current requests
        if current_minute not in self.request_counts[client_ip]:
            self.request_counts[client_ip][current_minute] = 0
        
        self.request_counts[client_ip][current_minute] += 1
        
        # Check rate limit
        total_requests = sum(self.request_counts[client_ip].values())
        if total_requests > self.requests_per_minute:
            logger.warning(f"Rate limit exceeded for IP {client_ip}: {total_requests} requests")
            abort(429)  # Too Many Requests
        
        # Store request start time for monitoring
        g.request_start_time = current_time
    
    def _after_request(self, response):
        """Post-request processing for logging and security headers."""
        from flask import request, g
        
        # Only apply to GraphQL endpoints
        if not request.endpoint or 'graphql' not in request.endpoint:
            return response
        
        # Add security headers
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        
        # Log request completion
        if hasattr(g, 'request_start_time'):
            duration = time.time() - g.request_start_time
            logger.info(f"GraphQL request completed in {duration:.3f}s - Status: {response.status_code}")
        
        return response