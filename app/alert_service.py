"""
CO2 threshold alert service.

Checks sensor readings against user-configured thresholds and dispatches
notifications via email, browser (recorded for polling), and ntfy.sh.
Alert failures never break reading ingestion.
"""

import logging
import requests as http_requests
from datetime import datetime, timedelta
from typing import List, Optional

from app import db
from app.models import (
    AlertThreshold, AlertHistory, AlertCooldown, Sensor, SensorLocation, User
)
from sqlalchemy import or_

logger = logging.getLogger(__name__)

SEVERITY_RANK = {'warning': 1, 'critical': 2}


def check_and_send_alerts(sensor_id: int, reading_id: int, co2_ppm: int) -> None:
    """Check all enabled thresholds for a sensor reading and send alerts.

    This function is called inline after a sensor reading is committed.
    All exceptions are caught internally so alert failures never break
    reading ingestion.
    """
    try:
        _process_alerts(sensor_id, reading_id, co2_ppm)
    except Exception:
        logger.error(
            "Alert processing failed",
            exc_info=True,
            extra={'extra_context': {
                'sensor_id': sensor_id,
                'reading_id': reading_id,
                'co2_ppm': co2_ppm,
                'operation': 'check_and_send_alerts_error',
            }}
        )


def _process_alerts(sensor_id: int, reading_id: int, co2_ppm: int) -> None:
    """Internal alert processing logic."""
    # Query all enabled thresholds matching this sensor or global (sensor_id IS NULL)
    thresholds: List[AlertThreshold] = AlertThreshold.query.filter(
        AlertThreshold.is_enabled == True,  # noqa: E712
        or_(
            AlertThreshold.sensor_id == sensor_id,
            AlertThreshold.sensor_id.is_(None),
        )
    ).all()

    if not thresholds:
        return

    # Resolve current location name for this sensor
    current_assignment = SensorLocation.query.filter_by(
        sensor_id=sensor_id, is_current=True
    ).first()
    if current_assignment and current_assignment.location:
        location_label = current_assignment.location.name
    else:
        sensor = Sensor.query.get(sensor_id)
        location_label = sensor.name if sensor else f"Sensor {sensor_id}"

    for threshold in thresholds:
        severity = _determine_severity(co2_ppm, threshold)
        if severity is None:
            continue

        if _is_in_cooldown(threshold.user_id, sensor_id, threshold.cooldown_minutes, severity):
            continue

        channels = _send_notifications(threshold, location_label, co2_ppm, severity)
        if not channels:
            continue

        # Record alert history
        alert = AlertHistory(
            user_id=threshold.user_id,
            sensor_id=sensor_id,
            reading_id=reading_id,
            threshold_id=threshold.id,
            co2_ppm=co2_ppm,
            severity=severity,
            channels_sent=','.join(channels),
        )
        db.session.add(alert)

        # Upsert cooldown
        _upsert_cooldown(threshold.user_id, sensor_id, severity)

    db.session.commit()


def _determine_severity(co2_ppm: int, threshold: AlertThreshold) -> Optional[str]:
    """Return 'critical', 'warning', or None based on threshold levels."""
    if co2_ppm >= threshold.critical_ppm:
        return 'critical'
    if co2_ppm >= threshold.warning_ppm:
        return 'warning'
    return None


def _is_in_cooldown(
    user_id: int, sensor_id: int, cooldown_minutes: int, current_severity: str
) -> bool:
    """Check if alert should be suppressed due to cooldown.

    Allows escalation: if last alert was 'warning' and current is 'critical',
    the cooldown is bypassed.
    """
    cooldown = AlertCooldown.query.filter_by(
        user_id=user_id, sensor_id=sensor_id
    ).first()

    if cooldown is None:
        return False

    elapsed = datetime.utcnow() - cooldown.last_alert_time
    if elapsed >= timedelta(minutes=cooldown_minutes):
        return False

    # Allow escalation from warning → critical
    if (SEVERITY_RANK.get(current_severity, 0)
            > SEVERITY_RANK.get(cooldown.last_severity, 0)):
        return False

    return True


def _upsert_cooldown(user_id: int, sensor_id: int, severity: str) -> None:
    """Insert or update cooldown record."""
    cooldown = AlertCooldown.query.filter_by(
        user_id=user_id, sensor_id=sensor_id
    ).first()

    if cooldown:
        cooldown.last_alert_time = datetime.utcnow()
        cooldown.last_severity = severity
    else:
        cooldown = AlertCooldown(
            user_id=user_id,
            sensor_id=sensor_id,
            last_alert_time=datetime.utcnow(),
            last_severity=severity,
        )
        db.session.add(cooldown)


def _send_notifications(
    threshold: AlertThreshold,
    location_label: str,
    co2_ppm: int,
    severity: str,
) -> List[str]:
    """Send alerts via all enabled channels. Returns list of channels sent."""
    channels: List[str] = []

    if threshold.email_enabled:
        if _send_email_alert(threshold.user_id, location_label, co2_ppm, severity):
            channels.append('email')

    if threshold.browser_enabled:
        # Browser alerts are recorded in alert_history for frontend polling.
        # No server push needed.
        channels.append('browser')

    if threshold.ntfy_enabled and threshold.ntfy_topic:
        if _send_ntfy_alert(threshold, location_label, co2_ppm, severity):
            channels.append('ntfy')

    return channels


def _send_email_alert(
    user_id: int, location_label: str, co2_ppm: int, severity: str
) -> bool:
    """Send CO2 alert email to user."""
    try:
        from app.email_service import email_service

        user = User.query.get(user_id)
        if not user or not user.email:
            return False

        return email_service.send_co2_alert(
            user_email=user.email,
            username=user.username,
            location_label=location_label,
            co2_ppm=co2_ppm,
            severity=severity,
        )
    except Exception:
        logger.error(
            "Failed to send CO2 alert email",
            exc_info=True,
            extra={'extra_context': {
                'user_id': user_id,
                'location_label': location_label,
                'co2_ppm': co2_ppm,
                'operation': 'send_email_alert_error',
            }}
        )
        return False


def _send_ntfy_alert(
    threshold: AlertThreshold,
    location_label: str,
    co2_ppm: int,
    severity: str,
) -> bool:
    """Send CO2 alert via ntfy.sh push notification."""
    try:
        server = (threshold.ntfy_server or 'https://ntfy.sh').rstrip('/')
        url = f"{server}/{threshold.ntfy_topic}"

        title = f"AirQ CO2 Alert - {severity.upper()}"
        body = f"{location_label}: CO2 at {co2_ppm} ppm ({severity})"
        priority = '5' if severity == 'critical' else '3'

        response = http_requests.post(
            url,
            data=body.encode('utf-8'),
            headers={
                'Title': title,
                'Priority': priority,
                'Tags': 'warning' if severity == 'warning' else 'rotating_light',
            },
            timeout=10,
        )
        response.raise_for_status()

        logger.info(
            "ntfy alert sent",
            extra={'extra_context': {
                'user_id': threshold.user_id,
                'location_label': location_label,
                'co2_ppm': co2_ppm,
                'severity': severity,
                'operation': 'send_ntfy_alert_success',
            }}
        )
        return True

    except Exception:
        logger.error(
            "Failed to send ntfy alert",
            exc_info=True,
            extra={'extra_context': {
                'user_id': threshold.user_id,
                'ntfy_topic': threshold.ntfy_topic,
                'operation': 'send_ntfy_alert_error',
            }}
        )
        return False
