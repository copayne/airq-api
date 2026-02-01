"""
Email service for sending authentication-related emails.

Provides functionality for sending email verification and password reset emails.
Supports both SMTP and mock email backends for development/testing.
"""

import os
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional
from datetime import datetime
from flask import current_app

logger = logging.getLogger(__name__)


class EmailService:
    """Service for sending authentication emails."""
    
    def __init__(self, app=None):
        """Initialize email service."""
        self.app = app
        if app is not None:
            self.init_app(app)
    
    def init_app(self, app):
        """Initialize email service with Flask app."""
        self.smtp_server = app.config.get('SMTP_SERVER', 'localhost')
        self.smtp_port = int(app.config.get('SMTP_PORT', '587'))
        self.smtp_username = app.config.get('SMTP_USERNAME')
        self.smtp_password = app.config.get('SMTP_PASSWORD')
        self.smtp_use_tls = app.config.get('SMTP_USE_TLS', True)
        self.from_email = app.config.get('FROM_EMAIL', 'noreply@airq.local')
        self.base_url = app.config.get('BASE_URL', 'http://localhost:3000')
        self.mock_email = app.config.get('MOCK_EMAIL', True)
        
        if self.mock_email:
            logger.info("Email service initialized in mock mode")
        else:
            logger.info(f"Email service initialized with SMTP: {self.smtp_server}:{self.smtp_port}")
    
    def send_email_verification(self, user_email: str, username: str, token: str) -> bool:
        """Send email verification message."""
        subject = "AirQ - Verify Your Email Address"
        verification_url = f"{self.base_url}/verify-email?token={token}"
        
        html_body = f"""
        <html>
        <body>
            <h2>Welcome to AirQ!</h2>
            <p>Hi {username},</p>
            <p>Thank you for registering with AirQ. Please click the link below to verify your email address:</p>
            <p><a href="{verification_url}" style="background-color: #4CAF50; color: white; padding: 10px 20px; text-decoration: none; border-radius: 4px;">Verify Email Address</a></p>
            <p>Or copy and paste this link into your browser:</p>
            <p>{verification_url}</p>
            <p>This link will expire in 24 hours.</p>
            <p>If you did not create an account with AirQ, please ignore this email.</p>
            <p>Best regards,<br>The AirQ Team</p>
        </body>
        </html>
        """
        
        text_body = f"""
        Welcome to AirQ!
        
        Hi {username},
        
        Thank you for registering with AirQ. Please visit the following link to verify your email address:
        
        {verification_url}
        
        This link will expire in 24 hours.
        
        If you did not create an account with AirQ, please ignore this email.
        
        Best regards,
        The AirQ Team
        """
        
        return self._send_email(user_email, subject, text_body, html_body)
    
    def send_password_reset(self, user_email: str, username: str, token: str) -> bool:
        """Send password reset message."""
        subject = "AirQ - Password Reset Request"
        reset_url = f"{self.base_url}/reset-password?token={token}"
        
        html_body = f"""
        <html>
        <body>
            <h2>Password Reset Request</h2>
            <p>Hi {username},</p>
            <p>We received a request to reset your password for your AirQ account. Click the link below to reset your password:</p>
            <p><a href="{reset_url}" style="background-color: #FF6B6B; color: white; padding: 10px 20px; text-decoration: none; border-radius: 4px;">Reset Password</a></p>
            <p>Or copy and paste this link into your browser:</p>
            <p>{reset_url}</p>
            <p>This link will expire in 1 hour.</p>
            <p>If you did not request a password reset, please ignore this email. Your password will remain unchanged.</p>
            <p>Best regards,<br>The AirQ Team</p>
        </body>
        </html>
        """
        
        text_body = f"""
        Password Reset Request
        
        Hi {username},
        
        We received a request to reset your password for your AirQ account. Please visit the following link to reset your password:
        
        {reset_url}
        
        This link will expire in 1 hour.
        
        If you did not request a password reset, please ignore this email. Your password will remain unchanged.
        
        Best regards,
        The AirQ Team
        """
        
        return self._send_email(user_email, subject, text_body, html_body)
    
    def send_co2_alert(self, user_email: str, username: str, location_label: str, co2_ppm: int, severity: str) -> bool:
        """Send CO2 threshold alert email."""
        severity_upper = severity.upper()
        color = '#FF0000' if severity == 'critical' else '#FFA500'

        subject = f"CO2 {severity_upper}: {co2_ppm}ppm - {location_label}"

        html_body = f"""
        <html>
        </html>
        """

        text_body = f"""
        CO2 {severity_upper}

        {location_label} has a CO2 level of {co2_ppm} ppm.

        Consider ventilating the area to improve air quality.

        View dashboard: {self.base_url}/dash
        """

        return self._send_email(user_email, subject, text_body, html_body)

    def _send_email(self, to_email: str, subject: str, text_body: str, html_body: str) -> bool:
        """Send email using configured backend."""
        if self.mock_email:
            return self._mock_send_email(to_email, subject, text_body)
        else:
            return self._smtp_send_email(to_email, subject, text_body, html_body)
    
    def _mock_send_email(self, to_email: str, subject: str, text_body: str) -> bool:
        """Mock email sending for development/testing."""
        logger.info(f"MOCK EMAIL - To: {to_email}, Subject: {subject}")
        logger.info(f"MOCK EMAIL - Body: {text_body[:200]}...")
        
        # In development, you might want to save emails to a file
        if current_app.config.get('SAVE_MOCK_EMAILS', False):
            try:
                filename = f"mock_emails_{to_email.replace('@', '_at_')}.txt"
                with open(filename, 'a') as f:
                    f.write(f"\n{'='*50}\n")
                    f.write(f"To: {to_email}\n")
                    f.write(f"Subject: {subject}\n")
                    f.write(f"Time: {datetime.utcnow()}\n")
                    f.write(f"\n{text_body}\n")
                logger.info(f"Mock email saved to {filename}")
            except Exception as e:
                logger.error(f"Failed to save mock email: {e}")
        
        return True
    
    def _smtp_send_email(self, to_email: str, subject: str, text_body: str, html_body: str) -> bool:
        """Send email via SMTP."""
        try:
            # Create message
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = f'AirQ <{self.from_email}>'
            msg['To'] = to_email
            
            # Create text and HTML parts
            text_part = MIMEText(text_body, 'plain')
            html_part = MIMEText(html_body, 'html')
            
            msg.attach(text_part)
            msg.attach(html_part)
            
            # Send email
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                if self.smtp_use_tls:
                    server.starttls()
                
                if self.smtp_username and self.smtp_password:
                    server.login(self.smtp_username, self.smtp_password)
                
                server.send_message(msg)
            
            logger.info(f"Email sent successfully to {to_email}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send email to {to_email}: {str(e)}")
            return False


# Global email service instance
email_service = EmailService()


def init_email_service(app):
    """Initialize email service with Flask app."""
    email_service.init_app(app)
    return email_service