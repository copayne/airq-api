"""
Unit tests for enhanced authentication security features.
Tests email verification, password reset, account locking, and token blacklisting.
"""

import pytest
import jwt
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock
from app.models import User, TokenBlacklist
from app.email_service import EmailService


@pytest.mark.unit
class TestEmailVerification:
    """Test email verification functionality."""
    
    def test_generate_email_verification_token(self, session):
        """Test generating email verification token."""
        user = User(username="testuser", email="test@example.com")
        session.add(user)
        session.commit()
        
        token = user.generate_email_verification_token()
        
        assert token is not None
        assert len(token) == 32
        assert user.email_verification_token == token
        assert user.email_verification_expires is not None
        assert user.email_verification_expires > datetime.utcnow()
    
    def test_verify_email_with_valid_token(self, session):
        """Test email verification with valid token."""
        user = User(username="testuser", email="test@example.com")
        session.add(user)
        session.commit()
        
        token = user.generate_email_verification_token()
        session.commit()
        
        assert user.email_verified is False
        
        result = user.verify_email_with_token(token)
        
        assert result is True
        assert user.email_verified is True
        assert user.email_verification_token is None
        assert user.email_verification_expires is None
    
    def test_verify_email_with_invalid_token(self, session):
        """Test email verification with invalid token."""
        user = User(username="testuser", email="test@example.com")
        session.add(user)
        session.commit()
        
        user.generate_email_verification_token()
        session.commit()
        
        result = user.verify_email_with_token("invalid_token")
        
        assert result is False
        assert user.email_verified is False
    
    def test_verify_email_with_expired_token(self, session):
        """Test email verification with expired token."""
        user = User(username="testuser", email="test@example.com")
        session.add(user)
        session.commit()
        
        token = user.generate_email_verification_token()
        # Manually set expiration to past
        user.email_verification_expires = datetime.utcnow() - timedelta(hours=1)
        session.commit()
        
        result = user.verify_email_with_token(token)
        
        assert result is False
        assert user.email_verified is False


@pytest.mark.unit
class TestPasswordReset:
    """Test password reset functionality."""
    
    def test_generate_password_reset_token(self, session):
        """Test generating password reset token."""
        user = User(username="testuser", email="test@example.com")
        session.add(user)
        session.commit()
        
        token = user.generate_password_reset_token()
        
        assert token is not None
        assert len(token) == 32
        assert user.password_reset_token == token
        assert user.password_reset_expires is not None
        assert user.password_reset_expires > datetime.utcnow()
    
    def test_reset_password_with_valid_token(self, session):
        """Test password reset with valid token."""
        user = User(username="testuser", email="test@example.com")
        user.set_password("old_password")
        user.failed_login_attempts = 3
        user.account_locked_until = datetime.utcnow() + timedelta(minutes=30)
        session.add(user)
        session.commit()
        
        token = user.generate_password_reset_token()
        session.commit()
        
        result = user.reset_password_with_token(token, "new_password")
        
        assert result is True
        assert user.check_password("new_password") is True
        assert user.check_password("old_password") is False
        assert user.password_reset_token is None
        assert user.password_reset_expires is None
        # Should reset security counters
        assert user.failed_login_attempts == 0
        assert user.account_locked_until is None
    
    def test_reset_password_with_invalid_token(self, session):
        """Test password reset with invalid token."""
        user = User(username="testuser", email="test@example.com")
        user.set_password("old_password")
        session.add(user)
        session.commit()
        
        user.generate_password_reset_token()
        session.commit()
        
        result = user.reset_password_with_token("invalid_token", "new_password")
        
        assert result is False
        assert user.check_password("old_password") is True
        assert user.check_password("new_password") is False
    
    def test_reset_password_with_expired_token(self, session):
        """Test password reset with expired token."""
        user = User(username="testuser", email="test@example.com")
        user.set_password("old_password")
        session.add(user)
        session.commit()
        
        token = user.generate_password_reset_token()
        # Manually set expiration to past
        user.password_reset_expires = datetime.utcnow() - timedelta(hours=1)
        session.commit()
        
        result = user.reset_password_with_token(token, "new_password")
        
        assert result is False
        assert user.check_password("old_password") is True


@pytest.mark.unit
class TestAccountLocking:
    """Test account locking functionality."""
    
    def test_account_not_locked_initially(self, session):
        """Test that new accounts are not locked."""
        user = User(username="testuser", email="test@example.com")
        session.add(user)
        session.commit()
        
        assert user.is_account_locked() is False
        assert user.failed_login_attempts == 0
    
    def test_record_failed_login_attempts(self, session):
        """Test recording failed login attempts."""
        user = User(username="testuser", email="test@example.com")
        session.add(user)
        session.commit()
        
        # Record 3 failed attempts
        for i in range(3):
            user.record_failed_login()
            assert user.failed_login_attempts == i + 1
            assert user.is_account_locked() is False
    
    def test_account_locked_after_max_attempts(self, session):
        """Test account gets locked after max failed attempts."""
        user = User(username="testuser", email="test@example.com")
        session.add(user)
        session.commit()
        
        # Record 5 failed attempts (trigger lock)
        for i in range(5):
            user.record_failed_login()
        
        assert user.failed_login_attempts == 5
        assert user.is_account_locked() is True
        assert user.account_locked_until is not None
        assert user.account_locked_until > datetime.utcnow()
    
    def test_successful_login_resets_counters(self, session):
        """Test successful login resets security counters."""
        user = User(username="testuser", email="test@example.com")
        user.failed_login_attempts = 3
        user.account_locked_until = datetime.utcnow() + timedelta(minutes=30)
        session.add(user)
        session.commit()
        
        user.record_successful_login()
        
        assert user.failed_login_attempts == 0
        assert user.account_locked_until is None
    
    def test_account_lock_expires(self, session):
        """Test that account lock expires automatically."""
        user = User(username="testuser", email="test@example.com")
        user.failed_login_attempts = 5
        # Set lock to have expired 1 minute ago
        user.account_locked_until = datetime.utcnow() - timedelta(minutes=1)
        session.add(user)
        session.commit()
        
        # Should detect expired lock and reset
        is_locked = user.is_account_locked()
        
        assert is_locked is False
        assert user.failed_login_attempts == 0
        assert user.account_locked_until is None


@pytest.mark.unit
class TestTokenBlacklist:
    """Test JWT token blacklisting functionality."""
    
    def test_blacklist_token(self, session):
        """Test blacklisting a token."""
        user = User(username="testuser", email="test@example.com")
        session.add(user)
        session.commit()
        
        token = user.generate_jwt_token()
        result = user.blacklist_token(token)
        
        assert result is True
        
        # Check that token is in blacklist
        blacklisted_tokens = TokenBlacklist.query.filter_by(user_id=user.id).all()
        assert len(blacklisted_tokens) == 1
    
    def test_is_token_blacklisted(self, session):
        """Test checking if token is blacklisted."""
        user = User(username="testuser", email="test@example.com")
        session.add(user)
        session.commit()
        
        token = user.generate_jwt_token()
        
        # Decode token to get JTI
        import os
        secret_key = os.environ.get('SECRET_KEY', 'test-secret-key')
        payload = jwt.decode(token, secret_key, algorithms=['HS256'])
        jti = payload.get('jti')
        
        # Should not be blacklisted initially
        assert TokenBlacklist.is_token_blacklisted(jti) is False
        
        # Blacklist the token
        user.blacklist_token(token)
        
        # Should now be blacklisted
        assert TokenBlacklist.is_token_blacklisted(jti) is True
    
    def test_verify_blacklisted_token_fails(self, session):
        """Test that blacklisted tokens fail verification."""
        user = User(username="testuser", email="test@example.com")
        session.add(user)
        session.commit()
        
        token = user.generate_jwt_token()
        
        # Should verify initially
        verified_user = User.verify_jwt_token(token)
        assert verified_user is not None
        assert verified_user.id == user.id
        
        # Blacklist the token
        user.blacklist_token(token)
        
        # Should fail verification now
        verified_user = User.verify_jwt_token(token)
        assert verified_user is None
    
    def test_cleanup_expired_tokens(self, session):
        """Test cleanup of expired blacklisted tokens."""
        user = User(username="testuser", email="test@example.com")
        session.add(user)
        session.commit()
        
        # Create expired token in blacklist
        expired_token = TokenBlacklist(
            jti="expired_token_123",
            token_type="access",
            user_id=user.id,
            expires_at=datetime.utcnow() - timedelta(hours=1)
        )
        
        # Create valid token in blacklist
        valid_token = TokenBlacklist(
            jti="valid_token_456",
            token_type="access",
            user_id=user.id,
            expires_at=datetime.utcnow() + timedelta(hours=1)
        )
        
        session.add_all([expired_token, valid_token])
        session.commit()
        
        # Should have 2 tokens initially
        assert TokenBlacklist.query.count() == 2
        
        # Cleanup expired tokens
        cleaned_count = TokenBlacklist.cleanup_expired_tokens()
        
        assert cleaned_count == 1
        assert TokenBlacklist.query.count() == 1
        
        # Only the valid token should remain
        remaining_token = TokenBlacklist.query.first()
        assert remaining_token.jti == "valid_token_456"


@pytest.mark.unit
class TestEmailService:
    """Test email service functionality."""
    
    def test_email_service_initialization(self):
        """Test email service initialization."""
        mock_app = MagicMock()
        mock_app.config = {
            'SMTP_SERVER': 'smtp.example.com',
            'SMTP_PORT': '587',
            'SMTP_USERNAME': 'user@example.com',
            'SMTP_PASSWORD': 'password',
            'SMTP_USE_TLS': 'true',
            'FROM_EMAIL': 'noreply@example.com',
            'BASE_URL': 'https://example.com',
            'MOCK_EMAIL': 'true'
        }
        
        email_service = EmailService()
        email_service.init_app(mock_app)
        
        assert email_service.smtp_server == 'smtp.example.com'
        assert email_service.smtp_port == 587
        assert email_service.smtp_username == 'user@example.com'
        assert email_service.from_email == 'noreply@example.com'
        assert email_service.mock_email is True
    
    def test_send_verification_email_mock(self):
        """Test sending verification email in mock mode."""
        mock_app = MagicMock()
        mock_app.config = {'MOCK_EMAIL': 'true', 'BASE_URL': 'https://example.com'}
        
        email_service = EmailService()
        email_service.init_app(mock_app)
        
        result = email_service.send_email_verification(
            "user@example.com", "testuser", "verification_token_123"
        )
        
        assert result is True
    
    def test_send_password_reset_email_mock(self):
        """Test sending password reset email in mock mode."""
        mock_app = MagicMock()
        mock_app.config = {'MOCK_EMAIL': 'true', 'BASE_URL': 'https://example.com'}
        
        email_service = EmailService()
        email_service.init_app(mock_app)
        
        result = email_service.send_password_reset(
            "user@example.com", "testuser", "reset_token_456"
        )
        
        assert result is True


@pytest.mark.unit
class TestSecureTokenGeneration:
    """Test secure token generation."""
    
    def test_generate_secure_token(self, session):
        """Test secure token generation."""
        user = User(username="testuser", email="test@example.com")
        session.add(user)
        session.commit()
        
        token1 = user._generate_secure_token()
        token2 = user._generate_secure_token()
        
        # Should be 32 characters long
        assert len(token1) == 32
        assert len(token2) == 32
        
        # Should be different each time
        assert token1 != token2
        
        # Should only contain alphanumeric characters
        assert token1.isalnum()
        assert token2.isalnum()
    
    def test_jwt_token_includes_jti(self, session):
        """Test that JWT tokens include JTI for blacklisting."""
        user = User(username="testuser", email="test@example.com")
        session.add(user)
        session.commit()
        
        token = user.generate_jwt_token()
        
        # Decode token to verify JTI is present
        import os
        secret_key = os.environ.get('SECRET_KEY', 'test-secret-key')
        payload = jwt.decode(token, secret_key, algorithms=['HS256'])
        
        assert 'jti' in payload
        assert payload['jti'] is not None
        assert len(payload['jti']) == 32


@pytest.mark.unit
class TestEnhancedUserModel:
    """Test enhanced user model functionality."""
    
    def test_user_model_new_fields(self, session):
        """Test that new security fields are available."""
        user = User(username="testuser", email="test@example.com")
        session.add(user)
        session.commit()
        
        # Test default values
        assert user.email_verified is False
        assert user.email_verification_token is None
        assert user.email_verification_expires is None
        assert user.password_reset_token is None
        assert user.password_reset_expires is None
        assert user.failed_login_attempts == 0
        assert user.account_locked_until is None
    
    def test_jwt_verification_with_locked_account(self, session):
        """Test JWT verification fails for locked accounts."""
        user = User(username="testuser", email="test@example.com")
        user.account_locked_until = datetime.utcnow() + timedelta(minutes=30)
        session.add(user)
        session.commit()
        
        token = user.generate_jwt_token()
        
        # Should fail verification due to locked account
        verified_user = User.verify_jwt_token(token)
        assert verified_user is None
    
    def test_jwt_verification_with_inactive_account(self, session):
        """Test JWT verification fails for inactive accounts."""
        user = User(username="testuser", email="test@example.com", is_active=False)
        session.add(user)
        session.commit()
        
        token = user.generate_jwt_token()
        
        # Should fail verification due to inactive account
        verified_user = User.verify_jwt_token(token)
        assert verified_user is None