from app import db
from datetime import datetime, timedelta
from sqlalchemy.orm import relationship
from passlib.hash import bcrypt
from typing import Optional
import jwt
import os
import secrets
import string


class User(db.Model):
    """User model for authentication and authorization."""
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    first_name = db.Column(db.String(100))
    last_name = db.Column(db.String(100))
    
    # Role-based access control
    role = db.Column(db.String(20), nullable=False, default='viewer', index=True)  # admin, user, viewer
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    
    # Account security fields
    email_verified = db.Column(db.Boolean, default=False, nullable=False)
    email_verification_token = db.Column(db.String(255), nullable=True, index=True)
    email_verification_expires = db.Column(db.DateTime, nullable=True)
    
    # Password reset fields
    password_reset_token = db.Column(db.String(255), nullable=True, index=True)
    password_reset_expires = db.Column(db.DateTime, nullable=True)
    
    # Account security
    failed_login_attempts = db.Column(db.Integer, default=0, nullable=False)
    account_locked_until = db.Column(db.DateTime, nullable=True)
    
    # Timestamps
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_login = db.Column(db.DateTime, index=True)
    
    def set_password(self, password: str) -> None:
        """Hash and set user password."""
        self.password_hash = bcrypt.hash(password)
    
    def check_password(self, password: str) -> bool:
        """Check if provided password matches hash."""
        return bcrypt.verify(password, self.password_hash)
    
    def generate_jwt_token(self, expires_in: int = 3600) -> str:
        """Generate JWT token for user authentication.
        
        Args:
            expires_in: Token expiration time in seconds (default 1 hour)
            
        Returns:
            JWT token string
        """
        jti = self._generate_secure_token()  # Unique token ID for blacklisting
        exp_time = datetime.utcnow() + timedelta(seconds=expires_in)
        
        payload = {
            'user_id': self.id,
            'username': self.username,
            'role': self.role,
            'jti': jti,
            'exp': exp_time,
            'iat': datetime.utcnow()
        }
        
        secret_key = os.environ.get('SECRET_KEY')
        if not secret_key:
            raise ValueError("SECRET_KEY environment variable is required for JWT generation")
            
        return jwt.encode(payload, secret_key, algorithm='HS256')
    
    @staticmethod
    def verify_jwt_token(token: str) -> Optional['User']:
        """Verify JWT token and return user if valid.
        
        Args:
            token: JWT token string
            
        Returns:
            User instance if token is valid, None otherwise
        """
        try:
            secret_key = os.environ.get('SECRET_KEY')
            if not secret_key:
                return None
                
            payload = jwt.decode(token, secret_key, algorithms=['HS256'])
            user_id = payload.get('user_id')
            jti = payload.get('jti')
            
            # Check if token is blacklisted
            if jti and TokenBlacklist.is_token_blacklisted(jti):
                return None
            
            if user_id:
                user = User.query.get(user_id)
                # Additional security: check if user is still active
                if user and user.is_active and not user.is_account_locked():
                    return user
                
        except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
            pass
            
        return None
    
    def has_permission(self, required_role: str) -> bool:
        """Check if user has required permission level.
        
        Permission hierarchy: admin > user > viewer
        
        Args:
            required_role: Required role level
            
        Returns:
            True if user has permission, False otherwise
        """
        if not self.is_active:
            return False
            
        role_hierarchy = {
            'viewer': 1,
            'user': 2,
            'admin': 3
        }
        
        user_level = role_hierarchy.get(self.role, 0)
        required_level = role_hierarchy.get(required_role, 0)
        
        return user_level >= required_level
    
    def update_last_login(self) -> None:
        """Update user's last login timestamp."""
        self.last_login = datetime.utcnow()
        db.session.commit()
    
    def generate_email_verification_token(self) -> str:
        """Generate email verification token."""
        token = self._generate_secure_token()
        self.email_verification_token = token
        self.email_verification_expires = datetime.utcnow() + timedelta(hours=24)
        return token
    
    def verify_email_with_token(self, token: str) -> bool:
        """Verify email with provided token."""
        if (self.email_verification_token == token and 
            self.email_verification_expires and
            datetime.utcnow() < self.email_verification_expires):
            self.email_verified = True
            self.email_verification_token = None
            self.email_verification_expires = None
            return True
        return False
    
    def generate_password_reset_token(self) -> str:
        """Generate password reset token."""
        token = self._generate_secure_token()
        self.password_reset_token = token
        self.password_reset_expires = datetime.utcnow() + timedelta(hours=1)
        return token
    
    def reset_password_with_token(self, token: str, new_password: str) -> bool:
        """Reset password with provided token."""
        if (self.password_reset_token == token and 
            self.password_reset_expires and
            datetime.utcnow() < self.password_reset_expires):
            self.set_password(new_password)
            self.password_reset_token = None
            self.password_reset_expires = None
            self.failed_login_attempts = 0  # Reset failed attempts
            self.account_locked_until = None  # Unlock account
            return True
        return False
    
    def is_account_locked(self) -> bool:
        """Check if account is currently locked."""
        if self.account_locked_until:
            if datetime.utcnow() < self.account_locked_until:
                return True
            else:
                # Lock has expired, reset
                self.account_locked_until = None
                self.failed_login_attempts = 0
        return False
    
    def record_failed_login(self) -> None:
        """Record a failed login attempt and lock account if necessary."""
        self.failed_login_attempts += 1
        
        # Lock account after 5 failed attempts for 30 minutes
        if self.failed_login_attempts >= 5:
            self.account_locked_until = datetime.utcnow() + timedelta(minutes=30)
    
    def record_successful_login(self) -> None:
        """Record successful login and reset security counters."""
        self.failed_login_attempts = 0
        self.account_locked_until = None
        self.update_last_login()
    
    def blacklist_token(self, token: str) -> bool:
        """Blacklist a JWT token (for logout)."""
        try:
            secret_key = os.environ.get('SECRET_KEY')
            if not secret_key:
                return False
                
            payload = jwt.decode(token, secret_key, algorithms=['HS256'])
            jti = payload.get('jti')
            exp = payload.get('exp')
            
            if jti and exp:
                expires_at = datetime.fromtimestamp(exp)
                TokenBlacklist.blacklist_token(jti, 'access', self.id, expires_at)
                return True
                
        except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
            pass
            
        return False
    
    def _generate_secure_token(self) -> str:
        """Generate cryptographically secure random token."""
        alphabet = string.ascii_letters + string.digits
        return ''.join(secrets.choice(alphabet) for _ in range(32))
    
    def __repr__(self) -> str:
        """Return string representation of User instance."""
        return f'<User {self.username} ({self.role})>'


class TokenBlacklist(db.Model):
    """Model for tracking blacklisted JWT tokens."""
    __tablename__ = 'token_blacklist'
    
    id = db.Column(db.Integer, primary_key=True)
    jti = db.Column(db.String(255), nullable=False, unique=True, index=True)  # JWT ID
    token_type = db.Column(db.String(20), nullable=False)  # access, refresh
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    revoked_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)
    expires_at = db.Column(db.DateTime, nullable=False, index=True)
    
    # Relationship
    user = relationship("User", backref="blacklisted_tokens")
    
    @staticmethod
    def is_token_blacklisted(jti: str) -> bool:
        """Check if a token is blacklisted."""
        token = TokenBlacklist.query.filter_by(jti=jti).first()
        return token is not None
    
    @staticmethod
    def blacklist_token(jti: str, token_type: str, user_id: int, expires_at: datetime) -> None:
        """Add a token to the blacklist."""
        blacklisted_token = TokenBlacklist(
            jti=jti,
            token_type=token_type,
            user_id=user_id,
            expires_at=expires_at
        )
        db.session.add(blacklisted_token)
        db.session.commit()
    
    @staticmethod
    def cleanup_expired_tokens() -> int:
        """Remove expired tokens from blacklist and return count removed."""
        current_time = datetime.utcnow()
        expired_tokens = TokenBlacklist.query.filter(TokenBlacklist.expires_at < current_time).all()
        count = len(expired_tokens)
        
        for token in expired_tokens:
            db.session.delete(token)
        
        db.session.commit()
        return count
    
    def __repr__(self) -> str:
        return f'<TokenBlacklist {self.jti[:8]}... (User: {self.user_id})>'


class Sensor(db.Model):
    __tablename__ = 'sensors'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    model = db.Column(db.String(100), nullable=False)
    installation_date = db.Column(db.DateTime,
        nullable=False, unique=False, index=True,
        default=datetime.utcnow
    )
    is_active = db.Column(db.Boolean, default=True)
    
    # Relationships
    readings = relationship("SensorReading", back_populates="sensor", lazy="select")
    sensor_locations = relationship("SensorLocation", back_populates="sensor", lazy="select")
    

class Location(db.Model):
    __tablename__ = 'locations'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    
    # Relationships
    sensor_locations = relationship("SensorLocation", back_populates="location", lazy="select")

class SensorLocation(db.Model):
    __tablename__ = 'sensor_locations'
    id = db.Column(db.Integer, primary_key=True)
    sensor_id = db.Column(db.Integer, db.ForeignKey('sensors.id'), nullable=False, index=True)
    location_id = db.Column(db.Integer, db.ForeignKey('locations.id'), nullable=False, index=True)
    start_time = db.Column(db.DateTime, nullable=False, index=True)
    end_time = db.Column(db.DateTime, index=True)
    is_current = db.Column(db.Boolean, default=True)
    
    # Relationships
    sensor = relationship("Sensor", back_populates="sensor_locations")
    location = relationship("Location", back_populates="sensor_locations")

class SensorReading(db.Model):
    __tablename__ = 'sensor_readings'
    id = db.Column(db.Integer, primary_key=True)
    sensor_id = db.Column(db.Integer, db.ForeignKey('sensors.id'), nullable=False, index=True)
    reading_time = db.Column(db.DateTime,
        nullable=False, unique=False, index=True,
        default=datetime.utcnow
    )
    is_success = db.Column(db.Boolean, default=True)
    
    # Relationships
    sensor = relationship("Sensor", back_populates="readings")
    humidity_reading = relationship("HumidityReading", back_populates="sensor_reading", uselist=False)
    temperature_reading = relationship("TemperatureReading", back_populates="sensor_reading", uselist=False)
    co2_reading = relationship("CO2Reading", back_populates="sensor_reading", uselist=False)
    error_logs = relationship("ErrorLog", back_populates="sensor_reading")

class HumidityReading(db.Model):
    __tablename__ = 'humidity_readings'
    id = db.Column(db.Integer, primary_key=True)
    reading_id = db.Column(db.Integer, db.ForeignKey('sensor_readings.id'), nullable=False, index=True)
    humidity_percentage = db.Column(db.Float, nullable=False)
    
    # Relationships
    sensor_reading = relationship("SensorReading", back_populates="humidity_reading")

class TemperatureReading(db.Model):
    __tablename__ = 'temperature_readings'
    id = db.Column(db.Integer, primary_key=True)
    reading_id = db.Column(db.Integer, db.ForeignKey('sensor_readings.id'), nullable=False, index=True)
    temperature_celsius = db.Column(db.Float, nullable=False)
    
    # Relationships
    sensor_reading = relationship("SensorReading", back_populates="temperature_reading")

class CO2Reading(db.Model):
    __tablename__ = 'co2_readings'
    id = db.Column(db.Integer, primary_key=True)
    reading_id = db.Column(db.Integer, db.ForeignKey('sensor_readings.id'), nullable=False, index=True)
    co2_ppm = db.Column(db.Integer, nullable=False)
    
    # Relationships
    sensor_reading = relationship("SensorReading", back_populates="co2_reading")

class ErrorLog(db.Model):
    __tablename__ = 'error_logs'
    created_at = db.Column(db.DateTime,
        nullable=False, unique=False, index=True,
        default=datetime.utcnow
    )
    id = db.Column(db.Integer, primary_key=True)
    reading_id = db.Column(db.Integer, db.ForeignKey('sensor_readings.id'), nullable=False, index=True)
    request_data = db.Column(db.Text)
    response_data = db.Column(db.Text)
    error_message = db.Column(db.Text)
    
    # Relationships
    sensor_reading = relationship("SensorReading", back_populates="error_logs")

class ApplicationErrorLog(db.Model):
    __tablename__ = 'application_error_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, nullable=False, index=True, default=datetime.utcnow)
    level = db.Column(db.String(20), nullable=False, index=True)  # ERROR, WARNING, INFO, DEBUG
    message = db.Column(db.Text, nullable=False)
    context = db.Column(db.JSON)  # JSON field for structured context data
    request_id = db.Column(db.String(50), index=True)
    user_id = db.Column(db.Integer, index=True)  # For future authentication
    stack_trace = db.Column(db.Text)
    source_file = db.Column(db.String(255))
    source_function = db.Column(db.String(100))
    source_line = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, nullable=False, index=True, default=datetime.utcnow)
    
    def __repr__(self) -> str:
        """Return string representation of ApplicationErrorLog instance."""
        return f'<ApplicationErrorLog {self.level}: {self.message[:50]}...>'

class Camera(db.Model):
    """Model for storing Ring camera device information."""
    __tablename__ = 'cameras'

    id = db.Column(db.Integer, primary_key=True)
    device_id = db.Column(db.String(100), nullable=False, unique=True, index=True)
    name = db.Column(db.String(255), nullable=False)
    location = db.Column(db.String(255))
    model = db.Column(db.String(100))
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationship to snapshots
    snapshots = db.relationship('RingSnapshot', back_populates='camera', lazy='dynamic')

    def __repr__(self) -> str:
        """Return string representation of Camera instance."""
        return f'<Camera {self.name} ({self.device_id})>'


class RingSnapshot(db.Model):
    """Model for storing Ring camera snapshot metadata."""
    __tablename__ = 'ring_snapshots'

    id = db.Column(db.Integer, primary_key=True)
    camera_id = db.Column(db.Integer, db.ForeignKey('cameras.id'), nullable=False, index=True)
    image_path = db.Column(db.String(500), nullable=False)
    capture_timestamp = db.Column(db.DateTime, nullable=False, index=True)
    file_size = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)

    # Relationship to camera
    camera = db.relationship('Camera', back_populates='snapshots')

    def __repr__(self) -> str:
        """Return string representation of RingSnapshot instance."""
        return f'<RingSnapshot camera_id={self.camera_id} at {self.capture_timestamp}>'


class RingDevice(db.Model):
    """
    Model for storing Ring device metadata (sensors, cameras, etc.).

    Stores static device information only. Real-time data (battery, status)
    is managed via websocket and not persisted to database.
    """
    __tablename__ = 'ring_devices'

    id = db.Column(db.Integer, primary_key=True)
    device_id = db.Column(db.String(100), nullable=False, unique=True, index=True)
    device_type = db.Column(db.String(50), nullable=False, index=True)
    name = db.Column(db.String(255), nullable=False)
    location = db.Column(db.String(255))
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self) -> str:
        """Return string representation of RingDevice instance."""
        return f'<RingDevice {self.name} ({self.device_type})>'


# Composite indexes for critical query performance
# These indexes optimize the most frequent query patterns identified in OPTIMIZE.md

# Index for time-series queries on sensor readings (sensor_id + reading_time)
db.Index('idx_sensor_readings_sensor_time', SensorReading.sensor_id, SensorReading.reading_time)

# Index for location resolution queries (sensor_id + time range)
db.Index('idx_sensor_locations_sensor_time_range', SensorLocation.sensor_id, SensorLocation.start_time, SensorLocation.end_time)

# Index for current location lookups (location_id + is_current)
db.Index('idx_sensor_locations_location_current', SensorLocation.location_id, SensorLocation.is_current)

# Index for error log queries (timestamp + level)
db.Index('idx_application_error_logs_timestamp_level', ApplicationErrorLog.timestamp, ApplicationErrorLog.level)

# Index for ring snapshot queries (camera_id + capture_timestamp)
db.Index('idx_ring_snapshots_camera_time', RingSnapshot.camera_id, RingSnapshot.capture_timestamp)
