# Frontend API Requirements for AirQ Authentication System

## Overview

This document outlines all the backend API endpoints and functionality available for frontend integration with the AirQ authentication system. The backend provides a complete, production-ready authentication system with security best practices.

## Available Authentication Endpoints

### 1. User Registration
**Mutation:** `registerUser`
- **Purpose:** Create new user account with email verification
- **Security:** Password validation, duplicate checking, email verification required
- **Response:** Returns user object and initial JWT token
- **Email:** Sends verification email (mock mode in development)

### 2. Email Verification
**Mutation:** `verifyEmail`
- **Purpose:** Verify user email address with token from email
- **Security:** Time-limited tokens (24 hours), secure token generation
- **Frontend Need:** Email verification page/component

### 3. User Login
**Mutation:** `loginUser`
- **Purpose:** Authenticate user and return JWT token
- **Security:** Account locking (5 attempts = 30min lock), failed attempt tracking
- **Features:** Accepts username or email, returns email verification status

### 4. User Logout
**Mutation:** `logoutUser`
- **Purpose:** Securely logout by blacklisting JWT token
- **Security:** Server-side token invalidation, immediate effect
- **Frontend Need:** Logout functionality in header/menu

### 5. Password Reset Request
**Mutation:** `requestPasswordReset`
- **Purpose:** Request password reset email
- **Security:** Email enumeration prevention, time-limited tokens (1 hour)
- **Frontend Need:** "Forgot Password" link/page

### 6. Password Reset
**Mutation:** `resetPassword`
- **Purpose:** Reset password with token from email
- **Security:** Password validation, account unlock, token expiration
- **Frontend Need:** Password reset page/component

### 7. Current User Query
**Query:** `me`
- **Purpose:** Get current authenticated user information
- **Security:** JWT token required, excludes sensitive fields
- **Frontend Need:** User profile, authentication state

## Required Frontend Components

### 1. Authentication State Management
- **JWT Token Storage:** Local storage or secure cookies
- **Token Refresh:** Handle token expiration (1-hour default)
- **Authentication Context:** Global state for user authentication
- **Auto-logout:** Handle token blacklisting/expiration

### 2. Registration Flow
- **Registration Form:** Username, email, password, optional names
- **Email Verification Notice:** Inform user to check email
- **Verification Success Page:** Handle email verification links
- **Resend Verification:** Option to resend verification email

### 3. Login Flow
- **Login Form:** Username/email and password fields
- **Account Locked Warning:** Display when account is temporarily locked
- **Email Verification Warning:** Prompt unverified users
- **"Remember Me" Option:** Extended session management

### 4. Password Management
- **Forgot Password Link:** Link to password reset request
- **Password Reset Request Form:** Email input form
- **Password Reset Form:** New password with confirmation
- **Password Strength Indicator:** Client-side validation

### 5. User Profile Management
- **Profile Display:** Show user information and verification status
- **Email Verification Badge:** Visual indicator of verification status
- **Account Settings:** Password change, profile updates
- **Logout Button:** Secure logout functionality

## Frontend Integration Examples

### Authentication Hook (React)
```javascript
const useAuth = () => {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  
  const login = async (credentials) => {
    const result = await apolloClient.mutate({
      mutation: LOGIN_USER,
      variables: { input: credentials }
    });
    
    if (result.data.loginUser.success) {
      const { user, token } = result.data.loginUser;
      localStorage.setItem('jwt_token', token);
      setUser(user);
      return { success: true, user };
    }
    
    return { success: false, message: result.data.loginUser.message };
  };
  
  const logout = async () => {
    const token = localStorage.getItem('jwt_token');
    if (token) {
      await apolloClient.mutate({
        mutation: LOGOUT_USER,
        variables: { input: { token } }
      });
      localStorage.removeItem('jwt_token');
    }
    setUser(null);
  };
  
  return { user, login, logout, loading };
};
```

### GraphQL Client Configuration
```javascript
const authLink = setContext((_, { headers }) => {
  const token = localStorage.getItem('jwt_token');
  return {
    headers: {
      ...headers,
      authorization: token ? `Bearer ${token}` : "",
    }
  };
});

const apolloClient = new ApolloClient({
  link: authLink.concat(httpLink),
  cache: new InMemoryCache(),
  errorPolicy: 'all'
});
```

## Error Handling Requirements

### 1. Authentication Errors
- **401 Unauthorized:** Redirect to login page
- **Token Expired:** Auto-logout and redirect
- **Account Locked:** Show lockout message with retry time
- **Email Not Verified:** Show verification prompt

### 2. Validation Errors
- **Form Validation:** Client-side validation matching backend rules
- **Server Validation:** Display server-side validation errors
- **Network Errors:** Graceful handling of connection issues

### 3. User Feedback
- **Loading States:** Show loading indicators during API calls
- **Success Messages:** Confirm successful operations
- **Error Messages:** Clear, user-friendly error descriptions
- **Progress Indicators:** Multi-step flows (registration, password reset)

## Security Considerations for Frontend

### 1. Token Management
- **Secure Storage:** Consider httpOnly cookies for production
- **Token Expiration:** Handle automatic logout on expiration
- **XSS Protection:** Sanitize user inputs and outputs
- **CSRF Protection:** Implement CSRF tokens for mutations

### 2. Password Security
- **Client Validation:** Match backend password requirements
- **Secure Transmission:** Always use HTTPS in production
- **No Storage:** Never store passwords client-side
- **Strength Indicators:** Help users create strong passwords

### 3. Email Verification
- **Deep Links:** Handle email verification URLs
- **State Management:** Track verification status
- **Resend Logic:** Prevent spam with rate limiting
- **Expired Tokens:** Handle expired verification links

## Environment Configuration

### Development
```javascript
const config = {
  apiUrl: 'http://localhost:5000/graphql',
  mockEmail: true,
  tokenStorage: 'localStorage'
};
```

### Production
```javascript
const config = {
  apiUrl: 'https://api.airq.com/graphql',
  mockEmail: false,
  tokenStorage: 'httpOnlyCookies'
};
```

## API Response Examples

### Successful Registration
```json
{
  "data": {
    "registerUser": {
      "success": true,
      "message": "Registration successful! Please check your email to verify your account.",
      "user": {
        "id": "123",
        "username": "johndoe",
        "email": "john@example.com",
        "emailVerified": false,
        "role": "user"
      },
      "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
    }
  }
}
```

### Account Locked Error
```json
{
  "data": {
    "loginUser": {
      "success": false,
      "message": "Account is temporarily locked due to multiple failed login attempts. Please try again later or reset your password.",
      "user": null,
      "token": null
    }
  }
}
```

### Email Verification Success
```json
{
  "data": {
    "verifyEmail": {
      "success": true,
      "message": "Email verified successfully"
    }
  }
}
```

## Testing Considerations

### 1. Mock Email Service
- Development uses mock email service
- Email content logged to console
- Option to save emails to files
- Test email templates and links

### 2. Account Locking Testing
- Test failed login attempt counting
- Test account unlock timing
- Test password reset unlocking account

### 3. Token Management Testing
- Test token expiration handling
- Test logout token blacklisting
- Test concurrent session management

## Production Deployment Checklist

### Backend Configuration
- [ ] Set MOCK_EMAIL=false
- [ ] Configure SMTP settings
- [ ] Set strong SECRET_KEY
- [ ] Configure BASE_URL for email links
- [ ] Enable production security settings

### Frontend Configuration
- [ ] Use HTTPS for all API calls
- [ ] Implement secure token storage
- [ ] Add CSRF protection
- [ ] Configure error tracking
- [ ] Test email verification flow

### Security Verification
- [ ] Test all authentication flows
- [ ] Verify email delivery
- [ ] Test account locking mechanism
- [ ] Verify token blacklisting works
- [ ] Test password reset security

This comprehensive authentication system provides all the security features needed for a production application while maintaining ease of use for developers.