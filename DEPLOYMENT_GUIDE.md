# AirQ API Enhanced Authentication Deployment Guide

## Overview

This guide covers deploying the enhanced authentication system with all new security features including email verification, password reset, account locking, and token blacklisting.

## Pre-Deployment Checklist

### 1. Database Migration
Run the database migration to add new security fields:

```bash
python migrate_add_auth_security_fields.py
```

This adds:
- Email verification fields to users table
- Password reset fields to users table  
- Account locking fields to users table
- Token blacklist table
- Performance indexes

### 2. Environment Variables
Update your environment configuration:

```bash
# Required for JWT tokens
export SECRET_KEY="your-super-secure-secret-key-here"

# Database connection
export DATABASE_URL="postgresql://user:password@host:port/database"

# Email configuration (production)
export MOCK_EMAIL="false"
export SMTP_SERVER="smtp.your-email-provider.com"
export SMTP_PORT="587"
export SMTP_USERNAME="your-smtp-username"
export SMTP_PASSWORD="your-smtp-password"
export SMTP_USE_TLS="true"
export FROM_EMAIL="noreply@yourdomain.com"
export BASE_URL="https://yourdomain.com"

# Security settings
export FLASK_ENV="production"
export GRAPHQL_INTROSPECTION="false"
export GRAPHQL_GRAPHIQL="false"
export CORS_ORIGINS="https://yourdomain.com,https://www.yourdomain.com"
```

### 3. Dependency Installation
Ensure all required packages are installed:

```bash
pip install -r requirements.txt
```

No new dependencies were added - all features use existing packages.

## Step-by-Step Deployment

### Step 1: Backup Current Database
```bash
pg_dump your_database > backup_before_auth_upgrade.sql
```

### Step 2: Deploy Code Updates
```bash
git pull origin main  # or your deployment branch
```

### Step 3: Run Database Migration
```bash
python migrate_add_auth_security_fields.py
```

Expected output:
```
🔧 Starting authentication security fields migration...
  📝 Executing: ALTER TABLE users ADD COLUMN email_verified...
  ✅ Success
  📝 Executing: ALTER TABLE users ADD COLUMN email_verification_token...
  ✅ Success
  [... other migrations ...]
  
✅ Authentication security fields migration completed successfully!
```

### Step 4: Test Email Configuration
Run a quick test to verify email settings:

```python
from app.email_service import EmailService

# Test in Python shell
app = create_app()
with app.app_context():
    from app.email_service import email_service
    # Test will use mock mode if MOCK_EMAIL=true
    result = email_service.send_email_verification(
        "test@example.com", "testuser", "test_token_123"
    )
    print(f"Email test result: {result}")
```

### Step 5: Restart Application
```bash
# If using systemd
sudo systemctl restart airq-api

# If using PM2
pm2 restart airq-api

# If using Docker
docker-compose restart api
```

### Step 6: Verify Deployment
Test the new endpoints:

```bash
# Test registration with email verification
curl -X POST http://your-api-url/graphql \
  -H "Content-Type: application/json" \
  -d '{
    "query": "mutation { registerUser(input: {username: \"testuser\", email: \"test@example.com\", password: \"password123\"}) { success message } }"
  }'

# Test password reset request
curl -X POST http://your-api-url/graphql \
  -H "Content-Type: application/json" \
  -d '{
    "query": "mutation { requestPasswordReset(input: {email: \"test@example.com\"}) { success message } }"
  }'
```

## Production Configuration

### Email Service Setup

#### Using Gmail SMTP
```bash
export SMTP_SERVER="smtp.gmail.com"
export SMTP_PORT="587"
export SMTP_USERNAME="your-gmail@gmail.com"
export SMTP_PASSWORD="your-app-password"  # Use app password, not regular password
export SMTP_USE_TLS="true"
```

#### Using SendGrid
```bash
export SMTP_SERVER="smtp.sendgrid.net"
export SMTP_PORT="587"
export SMTP_USERNAME="apikey"
export SMTP_PASSWORD="your-sendgrid-api-key"
export SMTP_USE_TLS="true"
```

#### Using AWS SES
```bash
export SMTP_SERVER="email-smtp.us-east-1.amazonaws.com"
export SMTP_PORT="587"
export SMTP_USERNAME="your-aws-access-key"
export SMTP_PASSWORD="your-aws-secret-key"
export SMTP_USE_TLS="true"
```

### Security Hardening

#### 1. Generate Strong Secret Key
```python
import secrets
secret_key = secrets.token_hex(32)
print(f"SECRET_KEY={secret_key}")
```

#### 2. Configure CORS Properly
```bash
# Only allow your frontend domains
export CORS_ORIGINS="https://yourdomain.com,https://app.yourdomain.com"
export CORS_CREDENTIALS="true"
```

#### 3. Set Security Headers
The application automatically sets security headers:
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `X-XSS-Protection: 1; mode=block`

#### 4. Rate Limiting Configuration
```bash
# Adjust based on your needs
export GRAPHQL_RATE_LIMIT_PER_MINUTE="60"  # More restrictive for production
export GRAPHQL_MAX_COMPLEXITY="100"       # Lower complexity limit
export GRAPHQL_MAX_DEPTH="6"              # Reduce max depth
```

## Monitoring and Maintenance

### 1. Database Maintenance
Add these to your regular maintenance tasks:

```sql
-- Clean up expired tokens weekly
DELETE FROM token_blacklist WHERE expires_at < NOW();

-- Monitor failed login attempts
SELECT username, failed_login_attempts, account_locked_until 
FROM users 
WHERE failed_login_attempts > 0 OR account_locked_until IS NOT NULL;

-- Check email verification rates
SELECT 
  COUNT(*) as total_users,
  COUNT(CASE WHEN email_verified = true THEN 1 END) as verified_users,
  ROUND(COUNT(CASE WHEN email_verified = true THEN 1 END) * 100.0 / COUNT(*), 2) as verification_rate
FROM users;
```

### 2. Log Monitoring
Monitor these log patterns:

```bash
# Failed login attempts
grep "Failed login attempt" /var/log/airq-api.log

# Account lockouts
grep "Login attempt on locked account" /var/log/airq-api.log

# Email verification
grep "Email verified successfully" /var/log/airq-api.log

# Password resets
grep "Password reset" /var/log/airq-api.log
```

### 3. Automated Token Cleanup
Add this to your cron jobs:

```bash
# Run token cleanup daily at 2 AM
0 2 * * * cd /path/to/airq-api && python -c "from app.models import TokenBlacklist; from app import create_app, db; app = create_app(); app.app_context().push(); TokenBlacklist.cleanup_expired_tokens()"
```

## Troubleshooting

### Email Issues

#### Problem: Emails not sending in production
```bash
# Check email configuration
python -c "
from app import create_app
app = create_app()
print('MOCK_EMAIL:', app.config.get('MOCK_EMAIL'))
print('SMTP_SERVER:', app.config.get('SMTP_SERVER'))
print('FROM_EMAIL:', app.config.get('FROM_EMAIL'))
"
```

#### Problem: Email verification links not working
- Check BASE_URL configuration
- Verify frontend routing for verification pages
- Check token expiration (24 hours for email verification)

### Authentication Issues

#### Problem: Users can't login after deployment
- Check if account is locked: `SELECT account_locked_until FROM users WHERE username = 'username'`
- Verify JWT secret key hasn't changed
- Check database migration completed successfully

#### Problem: Token blacklisting not working
- Verify token_blacklist table exists
- Check JTI is being set in JWT tokens
- Ensure blacklist check is working in token verification

### Performance Issues

#### Problem: Slow authentication responses
- Check database indexes are created
- Monitor token_blacklist table size
- Consider implementing Redis for token blacklisting in high-traffic scenarios

## Rollback Plan

If issues occur, you can rollback:

### 1. Code Rollback
```bash
git checkout previous-stable-commit
# Restart application
```

### 2. Database Rollback (if needed)
```sql
-- Remove new columns (data will be lost)
ALTER TABLE users DROP COLUMN IF EXISTS email_verified;
ALTER TABLE users DROP COLUMN IF EXISTS email_verification_token;
ALTER TABLE users DROP COLUMN IF EXISTS email_verification_expires;
ALTER TABLE users DROP COLUMN IF EXISTS password_reset_token;
ALTER TABLE users DROP COLUMN IF EXISTS password_reset_expires;
ALTER TABLE users DROP COLUMN IF EXISTS failed_login_attempts;
ALTER TABLE users DROP COLUMN IF EXISTS account_locked_until;

-- Remove token blacklist table
DROP TABLE IF EXISTS token_blacklist;
```

### 3. Restore from Backup
```bash
# If major issues occur
psql your_database < backup_before_auth_upgrade.sql
```

## Performance Optimization

### 1. Database Indexing
The migration script creates these indexes automatically:
- `idx_users_email_verification_token`
- `idx_users_password_reset_token`
- `idx_token_blacklist_jti`
- `idx_token_blacklist_user_id`
- `idx_token_blacklist_expires_at`

### 2. Token Blacklist Scaling
For high-traffic applications, consider:

```python
# Redis-based token blacklisting (future enhancement)
import redis

class RedisTokenBlacklist:
    def __init__(self):
        self.redis_client = redis.Redis(host='localhost', port=6379, db=0)
    
    def blacklist_token(self, jti, expires_at):
        # Store with automatic expiration
        ttl = int((expires_at - datetime.utcnow()).total_seconds())
        self.redis_client.setex(f"blacklist:{jti}", ttl, "1")
    
    def is_blacklisted(self, jti):
        return self.redis_client.exists(f"blacklist:{jti}")
```

## Success Metrics

Track these metrics to verify successful deployment:

1. **Email Verification Rate:** >80% of new users verify email
2. **Account Security:** Zero successful brute force attacks
3. **Password Reset Usage:** <5% of users need password reset monthly
4. **API Response Time:** <200ms for authentication endpoints
5. **Error Rate:** <1% error rate for authentication operations

## Support and Documentation

- **API Documentation:** `/docs/api-reference.md`
- **Frontend Integration:** `/FRONTEND_API_REQUIREMENTS.md`
- **Security Analysis:** `/SECURITY_ANALYSIS.md`
- **Test Coverage:** Run `pytest tests/` to verify all tests pass

The enhanced authentication system is now production-ready with enterprise-level security features!