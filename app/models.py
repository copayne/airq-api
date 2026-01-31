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


class DashboardLayout(db.Model):
    """Model for storing user dashboard layout configurations."""
    __tablename__ = 'dashboard_layouts'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False)
    layout_data = db.Column(db.JSON, nullable=False)
    is_last_used = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationship
    user = relationship("User", backref=db.backref("dashboard_layouts", lazy="dynamic", cascade="all, delete-orphan"))

    # Unique constraint for name per user
    __table_args__ = (
        db.UniqueConstraint('user_id', 'name', name='unique_layout_name_per_user'),
    )

    def __repr__(self) -> str:
        """Return string representation of DashboardLayout instance."""
        return f'<DashboardLayout {self.name} (User: {self.user_id})>'


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

    # Network configuration for health checks
    ip_address = db.Column(db.String(45))  # IPv4 or IPv6
    health_check_port = db.Column(db.Integer, default=8080)

    # Health tracking fields (updated automatically)
    last_reading_time = db.Column(db.DateTime)
    last_successful_reading_time = db.Column(db.DateTime)
    consecutive_failures = db.Column(db.Integer, default=0)
    total_readings = db.Column(db.Integer, default=0)
    total_failures = db.Column(db.Integer, default=0)
    last_health_check = db.Column(db.DateTime)
    last_health_status = db.Column(db.String(20))  # 'healthy', 'degraded', 'offline', 'unknown'

    # Relationships
    readings = relationship("SensorReading", back_populates="sensor", lazy="select")
    sensor_locations = relationship("SensorLocation", back_populates="sensor", lazy="select")
    health_reports = relationship("SensorHealthReport", back_populates="sensor", lazy="select")

    def update_health_on_reading(self, success: bool) -> None:
        """Update health tracking fields when a reading is received."""
        from datetime import datetime
        self.last_reading_time = datetime.utcnow()
        self.total_readings = (self.total_readings or 0) + 1

        if success:
            self.last_successful_reading_time = datetime.utcnow()
            self.consecutive_failures = 0
            self.last_health_status = 'healthy'
        else:
            self.consecutive_failures = (self.consecutive_failures or 0) + 1
            self.total_failures = (self.total_failures or 0) + 1
            if self.consecutive_failures >= 10:
                self.last_health_status = 'offline'
            elif self.consecutive_failures >= 3:
                self.last_health_status = 'degraded'

    @property
    def health_status(self) -> str:
        """Calculate current health status based on recent activity."""
        from datetime import datetime, timedelta

        if not self.is_active:
            return 'inactive'

        if not self.last_reading_time:
            return 'unknown'

        # Check if sensor has been silent too long (expected every 5-10 minutes)
        time_since_reading = datetime.utcnow() - self.last_reading_time
        if time_since_reading > timedelta(minutes=30):
            return 'offline'
        elif time_since_reading > timedelta(minutes=15):
            return 'degraded'

        # Check consecutive failures
        if (self.consecutive_failures or 0) >= 10:
            return 'offline'
        elif (self.consecutive_failures or 0) >= 3:
            return 'degraded'

        return 'healthy'

    @property
    def success_rate(self) -> float:
        """Calculate overall success rate as percentage."""
        if not self.total_readings:
            return 0.0
        failures = self.total_failures or 0
        return ((self.total_readings - failures) / self.total_readings) * 100


class SensorHealthReport(db.Model):
    """Stores detailed health reports from sensor diagnostics."""
    __tablename__ = 'sensor_health_reports'
    id = db.Column(db.Integer, primary_key=True)
    sensor_id = db.Column(db.Integer, db.ForeignKey('sensors.id'), nullable=False, index=True)
    report_time = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)

    # Service status
    service_running = db.Column(db.Boolean)
    service_uptime_seconds = db.Column(db.Integer)

    # Sensor hardware status
    sensor_connected = db.Column(db.Boolean)
    sensor_data_ready = db.Column(db.Boolean)
    sensor_serial_number = db.Column(db.String(50))

    # Last reading info
    last_co2_ppm = db.Column(db.Integer)
    last_temperature_celsius = db.Column(db.Float)
    last_humidity_percentage = db.Column(db.Float)
    last_reading_time = db.Column(db.DateTime)

    # System metrics
    system_uptime_seconds = db.Column(db.Integer)
    disk_usage_percent = db.Column(db.Float)
    memory_usage_percent = db.Column(db.Float)
    cpu_temperature_celsius = db.Column(db.Float)

    # Network info
    api_reachable = db.Column(db.Boolean)
    api_response_time_ms = db.Column(db.Integer)

    # Error info
    error_message = db.Column(db.Text)
    consecutive_failures = db.Column(db.Integer)

    # Relationships
    sensor = relationship("Sensor", back_populates="health_reports")
    

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


class AlertThreshold(db.Model):
    """Per-user CO2 threshold configuration for alert notifications."""
    __tablename__ = 'alert_thresholds'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    sensor_id = db.Column(db.Integer, db.ForeignKey('sensors.id', ondelete='CASCADE'), nullable=True, index=True)

    # Threshold levels (PPM)
    warning_ppm = db.Column(db.Integer, nullable=False, default=1000)
    critical_ppm = db.Column(db.Integer, nullable=False, default=1500)

    # Cooldown in minutes between alerts
    cooldown_minutes = db.Column(db.Integer, nullable=False, default=30)

    # Channel toggles
    email_enabled = db.Column(db.Boolean, nullable=False, default=True)
    browser_enabled = db.Column(db.Boolean, nullable=False, default=True)
    ntfy_enabled = db.Column(db.Boolean, nullable=False, default=False)

    # ntfy configuration
    ntfy_topic = db.Column(db.String(255))
    ntfy_server = db.Column(db.String(500), default='https://ntfy.sh')

    is_enabled = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = relationship("User", backref=db.backref("alert_thresholds", lazy="dynamic", cascade="all, delete-orphan"))
    sensor = relationship("Sensor", backref=db.backref("alert_thresholds", lazy="dynamic"))

    __table_args__ = (
        db.UniqueConstraint('user_id', 'sensor_id', name='unique_user_sensor_threshold'),
    )

    def __repr__(self) -> str:
        """Return string representation of AlertThreshold instance."""
        sensor_label = f"Sensor {self.sensor_id}" if self.sensor_id else "Global"
        return f'<AlertThreshold {sensor_label} (User: {self.user_id}, W:{self.warning_ppm}/C:{self.critical_ppm})>'


class AlertHistory(db.Model):
    """Log of triggered CO2 threshold alerts."""
    __tablename__ = 'alert_history'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    sensor_id = db.Column(db.Integer, db.ForeignKey('sensors.id', ondelete='CASCADE'), nullable=False, index=True)
    reading_id = db.Column(db.Integer, db.ForeignKey('sensor_readings.id', ondelete='CASCADE'), nullable=False)
    threshold_id = db.Column(db.Integer, db.ForeignKey('alert_thresholds.id', ondelete='CASCADE'), nullable=False)

    co2_ppm = db.Column(db.Integer, nullable=False)
    severity = db.Column(db.String(20), nullable=False)  # 'warning' or 'critical'
    channels_sent = db.Column(db.String(255), nullable=False)  # comma-separated

    acknowledged = db.Column(db.Boolean, nullable=False, default=False)
    acknowledged_at = db.Column(db.DateTime)

    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)

    # Relationships
    user = relationship("User", backref=db.backref("alert_history", lazy="dynamic"))
    sensor = relationship("Sensor", backref=db.backref("alert_history", lazy="dynamic"))
    reading = relationship("SensorReading", backref=db.backref("alert_history", lazy="dynamic"))
    threshold = relationship("AlertThreshold", backref=db.backref("alert_history", lazy="dynamic"))

    def __repr__(self) -> str:
        """Return string representation of AlertHistory instance."""
        return f'<AlertHistory {self.severity} CO2={self.co2_ppm}ppm (User: {self.user_id})>'


class AlertCooldown(db.Model):
    """Tracks last alert time per user/sensor for throttling."""
    __tablename__ = 'alert_cooldowns'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    sensor_id = db.Column(db.Integer, db.ForeignKey('sensors.id', ondelete='CASCADE'), nullable=False, index=True)

    last_alert_time = db.Column(db.DateTime, nullable=False)
    last_severity = db.Column(db.String(20), nullable=False)

    # Relationships
    user = relationship("User", backref=db.backref("alert_cooldowns", lazy="dynamic"))
    sensor = relationship("Sensor", backref=db.backref("alert_cooldowns", lazy="dynamic"))

    __table_args__ = (
        db.UniqueConstraint('user_id', 'sensor_id', name='unique_user_sensor_cooldown'),
    )

    def __repr__(self) -> str:
        """Return string representation of AlertCooldown instance."""
        return f'<AlertCooldown User:{self.user_id} Sensor:{self.sensor_id} Last:{self.last_alert_time}>'


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

# Index for dashboard layout queries (user_id + is_last_used)
db.Index('idx_dashboard_layouts_user_last_used', DashboardLayout.user_id, DashboardLayout.is_last_used)

# Index for sensor health report queries (sensor_id + report_time)
db.Index('idx_sensor_health_reports_sensor_time', SensorHealthReport.sensor_id, SensorHealthReport.report_time)
