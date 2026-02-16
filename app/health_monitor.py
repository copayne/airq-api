"""Background health monitor for detecting offline sensors.

Runs as a background thread via socketio.start_background_task().
Checks sensor health timestamps and sends offline alerts when
sensors stop reporting.
"""

import logging
from datetime import datetime, timedelta

from app import db
from app.models import (
    Sensor, SensorLocation, AlertThreshold, AlertHistory, AlertCooldown, User
)

logger = logging.getLogger(__name__)

OFFLINE_THRESHOLD_MINUTES = 15
CHECK_INTERVAL_SECONDS = 300
OFFLINE_COOLDOWN_MINUTES = 60


def start_health_monitor(socketio, app):
    """Start the background health monitor thread."""
    socketio.start_background_task(target=_monitor_loop, socketio=socketio, app=app)
    logger.info("Health monitor background thread started")


def _monitor_loop(socketio, app):
    """Main monitor loop — runs every CHECK_INTERVAL_SECONDS."""
    while True:
        socketio.sleep(CHECK_INTERVAL_SECONDS)
        try:
            with app.app_context():
                _check_offline_sensors(app)
        except Exception:
            logger.error(
                "Health monitor check failed",
                exc_info=True,
                extra={'extra_context': {'operation': 'health_monitor_error'}}
            )


def _check_offline_sensors(app):
    """Check all active sensors for offline status and send alerts.

    A sensor is considered online if EITHER of these is recent:
      - last_health_check (health report timestamp)
      - last_reading_time (sensor data timestamp)

    This prevents false offline alerts for sensors that are actively
    sending readings but haven't pushed a health report yet.
    """
    cutoff = datetime.utcnow() - timedelta(minutes=OFFLINE_THRESHOLD_MINUTES)

    sensors = Sensor.query.filter_by(is_active=True).all()

    for sensor in sensors:
        # Determine the most recent sign of life from this sensor
        last_seen = None
        if sensor.last_health_check and sensor.last_reading_time:
            last_seen = max(sensor.last_health_check, sensor.last_reading_time)
        elif sensor.last_health_check:
            last_seen = sensor.last_health_check
        elif sensor.last_reading_time:
            last_seen = sensor.last_reading_time

        if not last_seen:
            continue

        if last_seen >= cutoff:
            # Sensor is alive — if it was marked offline, clear that
            if sensor.last_health_status == 'offline':
                sensor.last_health_status = 'healthy'
                db.session.commit()
            continue

        # Already marked offline — don't re-alert
        if sensor.last_health_status == 'offline':
            continue

        # Sensor has gone offline
        sensor.last_health_status = 'offline'
        db.session.commit()

        minutes_offline = int(
            (datetime.utcnow() - last_seen).total_seconds() / 60
        )

        logger.warning(
            f"Sensor {sensor.name} (ID {sensor.id}) detected offline "
            f"({minutes_offline} minutes since last activity)",
            extra={'extra_context': {
                'sensor_id': sensor.id,
                'minutes_offline': minutes_offline,
                'operation': 'sensor_offline_detected',
            }}
        )

        _send_offline_alerts(sensor, minutes_offline)

        # Publish WebSocket event
        try:
            from app.events import publish_sensor_health
            publish_sensor_health({
                'sensor_id': sensor.id,
                'health_status': 'offline',
                'report_time': datetime.utcnow().isoformat(),
            })
        except Exception:
            pass


def _send_offline_alerts(sensor, minutes_offline):
    """Send offline alert to all users with enabled alert thresholds."""
    from app.email_service import email_service

    # Get location label
    location_label = "Unknown Location"
    current_location = SensorLocation.query.filter_by(
        sensor_id=sensor.id, is_current=True
    ).first()
    if current_location and current_location.location:
        location_label = current_location.location.name

    # Find all users with enabled thresholds for this sensor (or global)
    thresholds = AlertThreshold.query.filter(
        AlertThreshold.is_enabled == True,  # noqa: E712
    ).all()

    alerted_user_ids = set()
    for threshold in thresholds:
        if threshold.sensor_id is not None and threshold.sensor_id != sensor.id:
            continue

        user_id = threshold.user_id
        if user_id in alerted_user_ids:
            continue

        # Check cooldown
        if _is_offline_in_cooldown(user_id, sensor.id):
            continue

        user = User.query.get(user_id)
        if not user:
            continue

        # Send email
        try:
            email_service.send_offline_alert(
                user_email=user.email,
                username=user.username,
                sensor_name=sensor.name,
                location_label=location_label,
                minutes_offline=minutes_offline,
                severity='critical',
            )
            email_status = 'sent'
        except Exception:
            logger.error("Failed to send offline alert email", exc_info=True)
            email_status = 'failed'

        # Record alert history
        alert = AlertHistory(
            user_id=user_id,
            sensor_id=sensor.id,
            co2_ppm=0,
            severity='critical',
            channels_sent='email,browser',
            email_status=email_status,
        )
        db.session.add(alert)

        # Update cooldown
        _upsert_offline_cooldown(user_id, sensor.id)

        alerted_user_ids.add(user_id)

        # Publish per-user WebSocket alert
        try:
            from app.events import publish_alert
            publish_alert(user_id, {
                'sensor_id': sensor.id,
                'co2_ppm': 0,
                'severity': 'critical',
                'location': location_label,
                'message': f'{sensor.name} has been offline for {minutes_offline} minutes',
            })
        except Exception:
            pass

    if alerted_user_ids:
        db.session.commit()


def _is_offline_in_cooldown(user_id, sensor_id):
    """Check if an offline alert is in cooldown for this user+sensor."""
    cooldown = AlertCooldown.query.filter_by(
        user_id=user_id, sensor_id=sensor_id
    ).first()

    if not cooldown:
        return False

    elapsed = (datetime.utcnow() - cooldown.last_alert_time).total_seconds() / 60
    return elapsed < OFFLINE_COOLDOWN_MINUTES


def _upsert_offline_cooldown(user_id, sensor_id):
    """Update or create cooldown record for offline alerts."""
    cooldown = AlertCooldown.query.filter_by(
        user_id=user_id, sensor_id=sensor_id
    ).first()

    if cooldown:
        cooldown.last_alert_time = datetime.utcnow()
        cooldown.last_severity = 'critical'
    else:
        cooldown = AlertCooldown(
            user_id=user_id,
            sensor_id=sensor_id,
            last_alert_time=datetime.utcnow(),
            last_severity='critical',
        )
        db.session.add(cooldown)
