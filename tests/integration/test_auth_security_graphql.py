"""
Integration tests for enhanced authentication GraphQL mutations.
Tests email verification, password reset, logout, and security features.
"""

import pytest
import json
from unittest.mock import patch
from app.models import User, TokenBlacklist


@pytest.mark.integration
class TestEmailVerificationMutations:
    """Test email verification GraphQL mutations."""
    
    @patch('app.email_service.email_service.send_email_verification')
    def test_register_user_sends_verification_email(self, mock_send_email, client, session):
        """Test that user registration sends verification email."""
        mock_send_email.return_value = True
        
        mutation = """
        mutation RegisterUser($input: RegisterInput!) {
            registerUser(input: $input) {
                success
                message
                user {
                    id
                    username
                    email
                    emailVerified
                }
                token
            }
        }
        """
        
        variables = {
            "input": {
                "username": "newuser",
                "email": "newuser@example.com",
                "password": "password123",
                "firstName": "John",
                "lastName": "Doe"
            }
        }
        
        response = client.post('/graphql',
                             json={'query': mutation, 'variables': variables},
                             headers={'Content-Type': 'application/json'})
        
        assert response.status_code == 200
        data = response.get_json()
        
        result = data['data']['registerUser']
        assert result['success'] is True
        assert "Please check your email" in result['message']
        assert result['user']['emailVerified'] is False
        
        # Verify email service was called
        mock_send_email.assert_called_once()
        
        # Verify user was created with verification token
        user = User.query.filter_by(username="newuser").first()
        assert user is not None
        assert user.email_verified is False
        assert user.email_verification_token is not None
    
    def test_verify_email_success(self, client, session):
        """Test successful email verification."""
        # Create user with verification token
        user = User(username="testuser", email="test@example.com")
        user.set_password("password123")
        token = user.generate_email_verification_token()
        session.add(user)
        session.commit()
        
        mutation = """
        mutation VerifyEmail($input: EmailVerificationInput!) {
            verifyEmail(input: $input) {
                success
                message
            }
        }
        """
        
        variables = {
            "input": {
                "token": token
            }
        }
        
        response = client.post('/graphql',
                             json={'query': mutation, 'variables': variables},
                             headers={'Content-Type': 'application/json'})
        
        assert response.status_code == 200
        data = response.get_json()
        
        result = data['data']['verifyEmail']
        assert result['success'] is True
        assert result['message'] == "Email verified successfully"
        
        # Verify user email is now verified
        user = User.query.filter_by(username="testuser").first()
        assert user.email_verified is True
        assert user.email_verification_token is None
    
    def test_verify_email_invalid_token(self, client):
        """Test email verification with invalid token."""
        mutation = """
        mutation VerifyEmail($input: EmailVerificationInput!) {
            verifyEmail(input: $input) {
                success
                message
            }
        }
        """
        
        variables = {
            "input": {
                "token": "invalid_token_123"
            }
        }
        
        response = client.post('/graphql',
                             json={'query': mutation, 'variables': variables},
                             headers={'Content-Type': 'application/json'})
        
        assert response.status_code == 200
        data = response.get_json()
        
        result = data['data']['verifyEmail']
        assert result['success'] is False
        assert "Invalid or expired" in result['message']


@pytest.mark.integration
class TestPasswordResetMutations:
    """Test password reset GraphQL mutations."""
    
    @patch('app.email_service.email_service.send_password_reset')
    def test_request_password_reset_success(self, mock_send_email, client, session):
        """Test successful password reset request."""
        mock_send_email.return_value = True
        
        # Create test user
        user = User(username="testuser", email="test@example.com")
        user.set_password("old_password")
        session.add(user)
        session.commit()
        
        mutation = """
        mutation RequestPasswordReset($input: PasswordResetRequestInput!) {
            requestPasswordReset(input: $input) {
                success
                message
            }
        }
        """
        
        variables = {
            "input": {
                "email": "test@example.com"
            }
        }
        
        response = client.post('/graphql',
                             json={'query': mutation, 'variables': variables},
                             headers={'Content-Type': 'application/json'})
        
        assert response.status_code == 200
        data = response.get_json()
        
        result = data['data']['requestPasswordReset']
        assert result['success'] is True
        assert "password reset link has been sent" in result['message']
        
        # Verify email service was called
        mock_send_email.assert_called_once()
        
        # Verify user has reset token
        user = User.query.filter_by(email="test@example.com").first()
        assert user.password_reset_token is not None
        assert user.password_reset_expires is not None
    
    @patch('app.email_service.email_service.send_password_reset')
    def test_request_password_reset_nonexistent_email(self, mock_send_email, client):
        """Test password reset request for non-existent email."""
        mock_send_email.return_value = True
        
        mutation = """
        mutation RequestPasswordReset($input: PasswordResetRequestInput!) {
            requestPasswordReset(input: $input) {
                success
                message
            }
        }
        """
        
        variables = {
            "input": {
                "email": "nonexistent@example.com"
            }
        }
        
        response = client.post('/graphql',
                             json={'query': mutation, 'variables': variables},
                             headers={'Content-Type': 'application/json'})
        
        assert response.status_code == 200
        data = response.get_json()
        
        # Should still return success to prevent email enumeration
        result = data['data']['requestPasswordReset']
        assert result['success'] is True
        assert "password reset link has been sent" in result['message']
        
        # Email service should not be called
        mock_send_email.assert_not_called()
    
    def test_reset_password_success(self, client, session):
        """Test successful password reset."""
        # Create user with reset token
        user = User(username="testuser", email="test@example.com")
        user.set_password("old_password")
        reset_token = user.generate_password_reset_token()
        session.add(user)
        session.commit()
        
        mutation = """
        mutation ResetPassword($input: PasswordResetInput!) {
            resetPassword(input: $input) {
                success
                message
            }
        }
        """
        
        variables = {
            "input": {
                "token": reset_token,
                "newPassword": "new_password123"
            }
        }
        
        response = client.post('/graphql',
                             json={'query': mutation, 'variables': variables},
                             headers={'Content-Type': 'application/json'})
        
        assert response.status_code == 200
        data = response.get_json()
        
        result = data['data']['resetPassword']
        assert result['success'] is True
        assert result['message'] == "Password reset successfully"
        
        # Verify password was changed
        user = User.query.filter_by(username="testuser").first()
        assert user.check_password("new_password123") is True
        assert user.check_password("old_password") is False
        assert user.password_reset_token is None
    
    def test_reset_password_invalid_token(self, client):
        """Test password reset with invalid token."""
        mutation = """
        mutation ResetPassword($input: PasswordResetInput!) {
            resetPassword(input: $input) {
                success
                message
            }
        }
        """
        
        variables = {
            "input": {
                "token": "invalid_token_123",
                "newPassword": "new_password123"
            }
        }
        
        response = client.post('/graphql',
                             json={'query': mutation, 'variables': variables},
                             headers={'Content-Type': 'application/json'})
        
        assert response.status_code == 200
        data = response.get_json()
        
        result = data['data']['resetPassword']
        assert result['success'] is False
        assert "Invalid or expired" in result['message']
    
    def test_reset_password_weak_password(self, client, session):
        """Test password reset with weak password."""
        # Create user with reset token
        user = User(username="testuser", email="test@example.com")
        user.set_password("old_password")
        reset_token = user.generate_password_reset_token()
        session.add(user)
        session.commit()
        
        mutation = """
        mutation ResetPassword($input: PasswordResetInput!) {
            resetPassword(input: $input) {
                success
                message
            }
        }
        """
        
        variables = {
            "input": {
                "token": reset_token,
                "newPassword": "weak"  # Too short
            }
        }
        
        response = client.post('/graphql',
                             json={'query': mutation, 'variables': variables},
                             headers={'Content-Type': 'application/json'})
        
        assert response.status_code == 200
        data = response.get_json()
        
        result = data['data']['resetPassword']
        assert result['success'] is False
        assert "at least 8 characters" in result['message']


@pytest.mark.integration
class TestLogoutMutation:
    """Test logout GraphQL mutation."""
    
    def test_logout_success(self, client, session):
        """Test successful logout."""
        # Create and login user
        user = User(username="testuser", email="test@example.com")
        user.set_password("password123")
        session.add(user)
        session.commit()
        
        token = user.generate_jwt_token()
        
        mutation = """
        mutation LogoutUser($input: LogoutInput!) {
            logoutUser(input: $input) {
                success
                message
            }
        }
        """
        
        variables = {
            "input": {
                "token": token
            }
        }
        
        response = client.post('/graphql',
                             json={'query': mutation, 'variables': variables},
                             headers={'Content-Type': 'application/json'})
        
        assert response.status_code == 200
        data = response.get_json()
        
        result = data['data']['logoutUser']
        assert result['success'] is True
        assert result['message'] == "Logout successful"
        
        # Verify token is blacklisted
        blacklisted_tokens = TokenBlacklist.query.filter_by(user_id=user.id).all()
        assert len(blacklisted_tokens) == 1
        
        # Verify token no longer works
        verified_user = User.verify_jwt_token(token)
        assert verified_user is None
    
    def test_logout_invalid_token(self, client):
        """Test logout with invalid token."""
        mutation = """
        mutation LogoutUser($input: LogoutInput!) {
            logoutUser(input: $input) {
                success
                message
            }
        }
        """
        
        variables = {
            "input": {
                "token": "invalid_token_123"
            }
        }
        
        response = client.post('/graphql',
                             json={'query': mutation, 'variables': variables},
                             headers={'Content-Type': 'application/json'})
        
        assert response.status_code == 200
        data = response.get_json()
        
        result = data['data']['logoutUser']
        assert result['success'] is False
        assert result['message'] == "Invalid token"


@pytest.mark.integration
class TestEnhancedLoginSecurity:
    """Test enhanced login security features."""
    
    def test_login_with_account_locking(self, client, session):
        """Test login with account locking after failed attempts."""
        # Create test user
        user = User(username="testuser", email="test@example.com")
        user.set_password("correct_password")
        session.add(user)
        session.commit()
        
        mutation = """
        mutation LoginUser($input: LoginInput!) {
            loginUser(input: $input) {
                success
                message
                user {
                    username
                }
            }
        }
        """
        
        # Make 5 failed login attempts
        for i in range(5):
            variables = {
                "input": {
                    "usernameOrEmail": "testuser",
                    "password": "wrong_password"
                }
            }
            
            response = client.post('/graphql',
                                 json={'query': mutation, 'variables': variables},
                                 headers={'Content-Type': 'application/json'})
            
            assert response.status_code == 200
            data = response.get_json()
            result = data['data']['loginUser']
            assert result['success'] is False
            assert result['message'] == "Invalid credentials"
        
        # Account should now be locked
        user = User.query.filter_by(username="testuser").first()
        assert user.is_account_locked() is True
        
        # Try to login with correct password - should fail due to lock
        variables = {
            "input": {
                "usernameOrEmail": "testuser",
                "password": "correct_password"
            }
        }
        
        response = client.post('/graphql',
                             json={'query': mutation, 'variables': variables},
                             headers={'Content-Type': 'application/json'})
        
        assert response.status_code == 200
        data = response.get_json()
        result = data['data']['loginUser']
        assert result['success'] is False
        assert "temporarily locked" in result['message']
    
    def test_login_success_resets_failed_attempts(self, client, session):
        """Test that successful login resets failed attempt counter."""
        # Create test user
        user = User(username="testuser", email="test@example.com")
        user.set_password("correct_password")
        user.failed_login_attempts = 3  # Set some failed attempts
        session.add(user)
        session.commit()
        
        mutation = """
        mutation LoginUser($input: LoginInput!) {
            loginUser(input: $input) {
                success
                message
                user {
                    username
                }
            }
        }
        """
        
        variables = {
            "input": {
                "usernameOrEmail": "testuser",
                "password": "correct_password"
            }
        }
        
        response = client.post('/graphql',
                             json={'query': mutation, 'variables': variables},
                             headers={'Content-Type': 'application/json'})
        
        assert response.status_code == 200
        data = response.get_json()
        
        result = data['data']['loginUser']
        assert result['success'] is True
        
        # Verify failed attempts were reset
        user = User.query.filter_by(username="testuser").first()
        assert user.failed_login_attempts == 0
    
    def test_login_with_unverified_email(self, client, session):
        """Test login with unverified email shows warning."""
        # Create test user with unverified email
        user = User(username="testuser", email="test@example.com", email_verified=False)
        user.set_password("password123")
        session.add(user)
        session.commit()
        
        mutation = """
        mutation LoginUser($input: LoginInput!) {
            loginUser(input: $input) {
                success
                message
                user {
                    username
                    emailVerified
                }
            }
        }
        """
        
        variables = {
            "input": {
                "usernameOrEmail": "testuser",
                "password": "password123"
            }
        }
        
        response = client.post('/graphql',
                             json={'query': mutation, 'variables': variables},
                             headers={'Content-Type': 'application/json'})
        
        assert response.status_code == 200
        data = response.get_json()
        
        result = data['data']['loginUser']
        assert result['success'] is True
        assert "verify your email" in result['message']
        assert result['user']['emailVerified'] is False


@pytest.mark.integration
class TestUserQuerySecurity:
    """Test user query security with new fields."""
    
    def test_me_query_excludes_sensitive_fields(self, client, session):
        """Test that 'me' query excludes sensitive security fields."""
        # Create test user
        user = User(username="testuser", email="test@example.com")
        user.set_password("password123")
        # Set some sensitive fields
        user.email_verification_token = "secret_token"
        user.password_reset_token = "reset_token"
        user.failed_login_attempts = 3
        session.add(user)
        session.commit()
        
        # Generate JWT token
        token = user.generate_jwt_token()
        
        query = """
        query {
            me {
                id
                username
                email
                emailVerified
                role
                isActive
                createdAt
                lastLogin
            }
        }
        """
        
        response = client.post('/graphql',
                             json={'query': query},
                             headers={
                                 'Content-Type': 'application/json',
                                 'Authorization': f'Bearer {token}'
                             })
        
        assert response.status_code == 200
        data = response.get_json()
        
        assert 'data' in data
        assert 'me' in data['data']
        
        me_data = data['data']['me']
        assert me_data['username'] == "testuser"
        assert me_data['email'] == "test@example.com"
        assert 'emailVerified' in me_data
        
        # Sensitive fields should not be present
        assert 'emailVerificationToken' not in me_data
        assert 'passwordResetToken' not in me_data
        assert 'failedLoginAttempts' not in me_data
        assert 'accountLockedUntil' not in me_data
        assert 'passwordHash' not in me_data