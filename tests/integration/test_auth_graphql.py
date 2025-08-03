"""
Integration tests for authentication GraphQL mutations and queries.
"""

import pytest
import json
from app.models import User


@pytest.mark.integration
class TestAuthenticationMutations:
    """Test authentication GraphQL mutations."""
    
    def test_register_user_success(self, client, session):
        """Test successful user registration."""
        mutation = """
        mutation RegisterUser($input: RegisterInput!) {
            registerUser(input: $input) {
                success
                message
                user {
                    id
                    username
                    email
                    role
                    fullName
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
        
        assert 'data' in data
        assert 'registerUser' in data['data']
        
        result = data['data']['registerUser']
        assert result['success'] is True
        assert result['message'] == "Registration successful"
        assert result['token'] is not None
        assert len(result['token']) > 0
        
        user_data = result['user']
        assert user_data['username'] == "newuser"
        assert user_data['email'] == "newuser@example.com"
        assert user_data['role'] == "user"
        assert user_data['fullName'] == "John Doe"
        
        # Verify user was created in database
        user = User.query.filter_by(username="newuser").first()
        assert user is not None
        assert user.email == "newuser@example.com"
        assert user.check_password("password123") is True
    
    def test_register_user_duplicate_username(self, client, session):
        """Test registration with duplicate username."""
        # Create existing user
        existing_user = User(username="existing", email="existing@example.com")
        existing_user.set_password("password123")
        session.add(existing_user)
        session.commit()
        
        mutation = """
        mutation RegisterUser($input: RegisterInput!) {
            registerUser(input: $input) {
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
                "username": "existing",
                "email": "newemail@example.com",
                "password": "password123"
            }
        }
        
        response = client.post('/graphql',
                             json={'query': mutation, 'variables': variables},
                             headers={'Content-Type': 'application/json'})
        
        assert response.status_code == 200
        data = response.get_json()
        
        result = data['data']['registerUser']
        assert result['success'] is False
        assert "Username already exists" in result['message']
        assert result['user'] is None
    
    def test_register_user_weak_password(self, client):
        """Test registration with weak password."""
        mutation = """
        mutation RegisterUser($input: RegisterInput!) {
            registerUser(input: $input) {
                success
                message
            }
        }
        """
        
        variables = {
            "input": {
                "username": "newuser",
                "email": "newuser@example.com",
                "password": "weak"  # Too short
            }
        }
        
        response = client.post('/graphql',
                             json={'query': mutation, 'variables': variables},
                             headers={'Content-Type': 'application/json'})
        
        assert response.status_code == 200
        data = response.get_json()
        
        result = data['data']['registerUser']
        assert result['success'] is False
        assert "at least 8 characters" in result['message']
    
    def test_login_user_success(self, client, session):
        """Test successful user login."""
        # Create test user
        user = User(username="testuser", email="test@example.com")
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
                    email
                    role
                }
                token
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
        assert result['message'] == "Login successful"
        assert result['token'] is not None
        assert len(result['token']) > 0
        
        user_data = result['user']
        assert user_data['username'] == "testuser"
        assert user_data['email'] == "test@example.com"
    
    def test_login_user_with_email(self, client, session):
        """Test login using email instead of username."""
        # Create test user
        user = User(username="testuser", email="test@example.com")
        user.set_password("password123")
        session.add(user)
        session.commit()
        
        mutation = """
        mutation LoginUser($input: LoginInput!) {
            loginUser(input: $input) {
                success
                user {
                    username
                }
            }
        }
        """
        
        variables = {
            "input": {
                "usernameOrEmail": "test@example.com",  # Using email
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
        assert result['user']['username'] == "testuser"
    
    def test_login_invalid_credentials(self, client, session):
        """Test login with invalid credentials."""
        # Create test user
        user = User(username="testuser", email="test@example.com")
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
                }
            }
        }
        """
        
        # Test wrong password
        variables = {
            "input": {
                "usernameOrEmail": "testuser",
                "password": "wrongpassword"
            }
        }
        
        response = client.post('/graphql',
                             json={'query': mutation, 'variables': variables},
                             headers={'Content-Type': 'application/json'})
        
        assert response.status_code == 200
        data = response.get_json()
        
        result = data['data']['loginUser']
        assert result['success'] is False
        assert "Invalid credentials" in result['message']
        assert result['user'] is None
    
    def test_login_nonexistent_user(self, client):
        """Test login with non-existent user."""
        mutation = """
        mutation LoginUser($input: LoginInput!) {
            loginUser(input: $input) {
                success
                message
            }
        }
        """
        
        variables = {
            "input": {
                "usernameOrEmail": "nonexistent",
                "password": "password123"
            }
        }
        
        response = client.post('/graphql',
                             json={'query': mutation, 'variables': variables},
                             headers={'Content-Type': 'application/json'})
        
        assert response.status_code == 200
        data = response.get_json()
        
        result = data['data']['loginUser']
        assert result['success'] is False
        assert "Invalid credentials" in result['message']
    
    def test_login_inactive_user(self, client, session):
        """Test login with inactive user account."""
        # Create inactive user
        user = User(username="inactive", email="inactive@example.com", is_active=False)
        user.set_password("password123")
        session.add(user)
        session.commit()
        
        mutation = """
        mutation LoginUser($input: LoginInput!) {
            loginUser(input: $input) {
                success
                message
            }
        }
        """
        
        variables = {
            "input": {
                "usernameOrEmail": "inactive",
                "password": "password123"
            }
        }
        
        response = client.post('/graphql',
                             json={'query': mutation, 'variables': variables},
                             headers={'Content-Type': 'application/json'})
        
        assert response.status_code == 200
        data = response.get_json()
        
        result = data['data']['loginUser']
        assert result['success'] is False
        assert "Account is deactivated" in result['message']


@pytest.mark.integration
class TestAuthenticatedQueries:
    """Test authenticated GraphQL queries."""
    
    def test_me_query_authenticated(self, client, session):
        """Test 'me' query with valid authentication."""
        # Create test user
        user = User(username="testuser", email="test@example.com")
        user.set_password("password123")
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
                role
                fullName
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
    
    def test_me_query_unauthenticated(self, client):
        """Test 'me' query without authentication."""
        query = """
        query {
            me {
                username
            }
        }
        """
        
        response = client.post('/graphql',
                             json={'query': query},
                             headers={'Content-Type': 'application/json'})
        
        assert response.status_code == 200
        data = response.get_json()
        
        # Should return null for unauthenticated user
        assert data['data']['me'] is None
    
    def test_users_query_admin_access(self, client, session):
        """Test users query with admin access."""
        # Create admin user
        admin = User(username="admin", email="admin@example.com", role="admin")
        admin.set_password("password123")
        session.add(admin)
        session.commit()
        
        # Generate admin JWT token
        token = admin.generate_jwt_token()
        
        query = """
        query {
            users {
                id
                username
                email
                role
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
        assert 'users' in data['data']
        assert len(data['data']['users']) >= 1
    
    def test_users_query_non_admin_access(self, client, session):
        """Test users query with non-admin user (should fail)."""
        # Create regular user
        user = User(username="user", email="user@example.com", role="user")
        user.set_password("password123")
        session.add(user)
        session.commit()
        
        # Generate user JWT token
        token = user.generate_jwt_token()
        
        query = """
        query {
            users {
                username
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
        
        # Should return error for insufficient permissions
        assert 'errors' in data
        assert "Insufficient permissions" in data['errors'][0]['message']