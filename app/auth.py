"""
Authentication middleware and decorators for JWT-based authentication.
"""

from functools import wraps
from typing import Optional, Callable, Any
from flask import request, g
from app.models import User
import logging

logger = logging.getLogger(__name__)


def get_jwt_token_from_request() -> Optional[str]:
    """Extract JWT token from request headers.
    
    Looks for token in Authorization header with Bearer prefix.
    
    Returns:
        JWT token string if found, None otherwise
    """
    auth_header = request.headers.get('Authorization')
    if auth_header and auth_header.startswith('Bearer '):
        return auth_header.split(' ')[1]
    return None


def get_current_user() -> Optional[User]:
    """Get current authenticated user from JWT token.
    
    Returns:
        User instance if token is valid, None otherwise
    """
    token = get_jwt_token_from_request()
    if not token:
        return None
    
    return User.verify_jwt_token(token)


def require_auth(required_role: str = 'viewer') -> Callable:
    """Decorator to require authentication for GraphQL resolvers.
    
    Args:
        required_role: Minimum role required (viewer, user, admin)
        
    Returns:
        Decorator function
    """
    def decorator(resolver_func: Callable) -> Callable:
        @wraps(resolver_func)
        def wrapper(*args, **kwargs):
            # Get current user
            current_user = get_current_user()
            
            if not current_user:
                raise Exception("Authentication required")
            
            if not current_user.has_permission(required_role):
                raise Exception(f"Insufficient permissions. {required_role.title()} role required.")
            
            # Add user to context for resolver
            if len(args) >= 2:  # self, info, ...
                info = args[1]
                if hasattr(info, 'context'):
                    info.context.user = current_user
            
            return resolver_func(*args, **kwargs)
        
        return wrapper
    return decorator


def require_admin(resolver_func: Callable) -> Callable:
    """Decorator to require admin role for GraphQL resolvers."""
    return require_auth('admin')(resolver_func)


def require_user(resolver_func: Callable) -> Callable:
    """Decorator to require user role or higher for GraphQL resolvers."""
    return require_auth('user')(resolver_func)


def get_user_from_context(info: Any) -> Optional[User]:
    """Extract user from GraphQL context.
    
    Args:
        info: GraphQL resolver info object
        
    Returns:
        User instance if authenticated, None otherwise
    """
    if hasattr(info, 'context') and hasattr(info.context, 'user'):
        return info.context.user
    
    # Fallback: try to get user from JWT token
    return get_current_user()


class AuthenticationMiddleware:
    """Flask middleware for JWT authentication."""
    
    def __init__(self, app=None):
        if app is not None:
            self.init_app(app)
    
    def init_app(self, app):
        """Initialize middleware with Flask app."""
        app.before_request(self._before_request)
    
    def _before_request(self):
        """Pre-request processing to set up authentication context."""
        # Set up user context for GraphQL requests
        if request.endpoint and 'graphql' in request.endpoint:
            user = get_current_user()
            g.current_user = user
            
            if user:
                logger.debug(f"Authenticated request from user: {user.username}")
            else:
                logger.debug("Unauthenticated request")


def init_auth(app):
    """Initialize authentication system with Flask app.
    
    Args:
        app: Flask application instance
    """
    # Initialize authentication middleware
    auth_middleware = AuthenticationMiddleware(app)
    
    logger.info("Authentication system initialized")
    
    return auth_middleware