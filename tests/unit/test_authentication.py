"""
Unit tests for authentication system.
"""

import pytest
import jwt
from datetime import datetime, timedelta
from app.models import User
from app.auth import get_current_user, require_auth
from unittest.mock import patch, MagicMock


@pytest.mark.unit
class TestUserModel:
    """Test User model authentication methods."""
    
    def test_user_creation(self, session):
        """Test creating a user with proper defaults."""
        user = User(
            username="testuser",
            email="test@example.com"
        )
        user.set_password("password123")
        
        session.add(user)
        session.commit()
        
        assert user.id is not None
        assert user.username == "testuser"
        assert user.email == "test@example.com"
        assert user.role == "viewer"  # Default role
        assert user.is_active is True
        assert user.password_hash is not None
        assert user.password_hash != "password123"  # Should be hashed
    
    def test_password_hashing(self, session):
        """Test password hashing and verification."""
        user = User(username="testuser", email="test@example.com")
        user.set_password("mysecretpassword")
        
        session.add(user)
        session.commit()
        
        # Correct password should verify
        assert user.check_password("mysecretpassword") is True
        
        # Wrong password should not verify
        assert user.check_password("wrongpassword") is False
        assert user.check_password("") is False
    
    def test_jwt_token_generation(self, session):
        """Test JWT token generation and verification."""
        user = User(
            username="testuser",
            email="test@example.com",
            role="user"
        )
        session.add(user)
        session.commit()
        
        # Generate token
        token = user.generate_jwt_token(expires_in=3600)
        assert isinstance(token, str)
        assert len(token) > 0
        
        # Verify token
        verified_user = User.verify_jwt_token(token)
        assert verified_user is not None
        assert verified_user.id == user.id
        assert verified_user.username == user.username
    
    def test_jwt_token_expiration(self, session):
        """Test JWT token expiration."""
        user = User(username="testuser", email="test@example.com")
        session.add(user)
        session.commit()
        
        # Generate expired token (expires in past)
        with patch('app.models.datetime') as mock_datetime:
            # Mock current time for token generation
            mock_datetime.utcnow.return_value = datetime.utcnow() - timedelta(hours=2)
            
            token = user.generate_jwt_token(expires_in=3600)  # 1 hour, but generated 2 hours ago
        
        # Token should be invalid
        verified_user = User.verify_jwt_token(token)
        assert verified_user is None
    
    def test_invalid_jwt_token(self):
        """Test verification of invalid JWT tokens."""
        # Test various invalid tokens
        assert User.verify_jwt_token("invalid_token") is None
        assert User.verify_jwt_token("") is None
        assert User.verify_jwt_token(None) is None
        
        # Test malformed JWT
        fake_jwt = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.invalid.payload"
        assert User.verify_jwt_token(fake_jwt) is None
    
    def test_permission_hierarchy(self, session):
        """Test role-based permission system."""
        # Create users with different roles
        viewer = User(username="viewer", email="viewer@test.com", role="viewer")
        user = User(username="user", email="user@test.com", role="user")
        admin = User(username="admin", email="admin@test.com", role="admin")
        
        session.add_all([viewer, user, admin])
        session.commit()
        
        # Test viewer permissions
        assert viewer.has_permission("viewer") is True
        assert viewer.has_permission("user") is False
        assert viewer.has_permission("admin") is False
        
        # Test user permissions
        assert user.has_permission("viewer") is True
        assert user.has_permission("user") is True
        assert user.has_permission("admin") is False
        
        # Test admin permissions
        assert admin.has_permission("viewer") is True
        assert admin.has_permission("user") is True
        assert admin.has_permission("admin") is True
    
    def test_inactive_user_permissions(self, session):
        """Test that inactive users have no permissions."""
        user = User(
            username="inactive",
            email="inactive@test.com",
            role="admin",
            is_active=False
        )
        session.add(user)
        session.commit()
        
        # Inactive users should have no permissions regardless of role
        assert user.has_permission("viewer") is False
        assert user.has_permission("user") is False
        assert user.has_permission("admin") is False
    
    def test_user_repr(self, session):
        """Test user string representation."""
        user = User(username="testuser", email="test@example.com", role="admin")
        session.add(user)
        session.commit()
        
        repr_str = repr(user)
        assert "testuser" in repr_str
        assert "admin" in repr_str


@pytest.mark.unit 
class TestAuthenticationMethods:
    """Test authentication helper methods."""
    
    @patch('app.auth.request')
    def test_get_jwt_token_from_request(self, mock_request):
        """Test extracting JWT token from request headers."""
        from app.auth import get_jwt_token_from_request
        
        # Test with valid Bearer token
        mock_request.headers.get.return_value = "Bearer abc123token"
        token = get_jwt_token_from_request()
        assert token == "abc123token"
        
        # Test with no Authorization header
        mock_request.headers.get.return_value = None
        token = get_jwt_token_from_request()
        assert token is None
        
        # Test with malformed header
        mock_request.headers.get.return_value = "InvalidHeader"
        token = get_jwt_token_from_request()
        assert token is None
        
        # Test with empty Bearer
        mock_request.headers.get.return_value = "Bearer "
        token = get_jwt_token_from_request()
        assert token == ""
    
    @patch('app.auth.get_jwt_token_from_request')
    @patch('app.models.User.verify_jwt_token')
    def test_get_current_user(self, mock_verify, mock_get_token):
        """Test getting current user from request."""
        from app.auth import get_current_user
        
        # Test with valid token
        mock_user = MagicMock()
        mock_get_token.return_value = "valid_token"
        mock_verify.return_value = mock_user
        
        user = get_current_user()
        assert user == mock_user
        mock_verify.assert_called_once_with("valid_token")
        
        # Test with no token
        mock_get_token.return_value = None
        user = get_current_user()
        assert user is None
    
    def test_require_auth_decorator(self):
        """Test the require_auth decorator."""
        # Mock resolver function
        mock_resolver = MagicMock(return_value="resolver_result")
        
        # Mock info object with context
        mock_info = MagicMock()
        mock_info.context = MagicMock()
        
        # Mock authenticated user with sufficient permissions
        mock_user = MagicMock()
        mock_user.has_permission.return_value = True
        
        with patch('app.auth.get_current_user', return_value=mock_user):
            # Apply decorator
            decorated_resolver = require_auth('user')(mock_resolver)
            
            # Call decorated resolver
            result = decorated_resolver("self", mock_info, "arg1")
            
            # Check that resolver was called and user was added to context
            mock_resolver.assert_called_once_with("self", mock_info, "arg1")
            assert mock_info.context.user == mock_user
            assert result == "resolver_result"
    
    def test_require_auth_no_user(self):
        """Test require_auth decorator with no authenticated user."""
        mock_resolver = MagicMock()
        
        with patch('app.auth.get_current_user', return_value=None):
            decorated_resolver = require_auth('user')(mock_resolver)
            
            with pytest.raises(Exception) as exc_info:
                decorated_resolver("self", "info")
            
            assert "Authentication required" in str(exc_info.value)
            mock_resolver.assert_not_called()
    
    def test_require_auth_insufficient_permissions(self):
        """Test require_auth decorator with insufficient permissions."""
        mock_resolver = MagicMock()
        
        # Mock user without sufficient permissions
        mock_user = MagicMock()
        mock_user.has_permission.return_value = False
        
        with patch('app.auth.get_current_user', return_value=mock_user):
            decorated_resolver = require_auth('admin')(mock_resolver)
            
            with pytest.raises(Exception) as exc_info:
                decorated_resolver("self", "info")
            
            assert "Insufficient permissions" in str(exc_info.value)
            assert "Admin role required" in str(exc_info.value)
            mock_resolver.assert_not_called()


@pytest.mark.unit
class TestAuthenticationMiddleware:
    """Test authentication middleware."""
    
    @patch('app.auth.get_current_user')
    @patch('flask.g')
    @patch('flask.request')
    def test_authentication_middleware(self, mock_request, mock_g, mock_get_current_user):
        """Test authentication middleware sets up user context."""
        from app.auth import AuthenticationMiddleware
        
        # Mock GraphQL request
        mock_request.endpoint = 'graphql'
        mock_user = MagicMock()
        mock_get_current_user.return_value = mock_user
        
        # Create middleware and call before_request
        middleware = AuthenticationMiddleware()
        middleware._before_request()
        
        # Check that user was set in context
        assert mock_g.current_user == mock_user
        mock_get_current_user.assert_called_once()
    
    @patch('app.auth.get_current_user')
    @patch('flask.g')
    @patch('flask.request')
    def test_middleware_non_graphql_request(self, mock_request, mock_g, mock_get_current_user):
        """Test middleware ignores non-GraphQL requests."""
        from app.auth import AuthenticationMiddleware
        
        # Mock non-GraphQL request
        mock_request.endpoint = 'some_other_endpoint'
        
        middleware = AuthenticationMiddleware()
        middleware._before_request()
        
        # Should not try to get current user for non-GraphQL requests
        mock_get_current_user.assert_not_called()