"""Background health monitor for detecting offline sensors.

Runs as a background thread via socketio.start_background_task().
Checks sensor health timestamps and sends offline alerts when
sensors stop reporting.
"""

import logging
from datetime import datetime, timedelta

from sqlalchemy import or_

from app import db
from app.models import (
    Sensor, AlertThreshold, AlertHistory, User
)
from app.alert_service import is_in_cooldown, upsert_cooldown, get_location_label

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
    newly_offline = []

    for sensor in sensors:
        # Determine the most recent sign of life from this sensor
        last_seen = max(
            filter(None, [sensor.last_health_check, sensor.last_reading_time]),
            default=None,
        )

        if not last_seen:
            continue

        if last_seen >= cutoff:
            # Sensor is alive — if it was marked offline, clear that
            if sensor.last_health_status == 'offline':
                sensor.last_health_status = 'healthy'
            continue

        # Already marked offline — don't re-alert
        if sensor.last_health_status == 'offline':
            continue

        # Sensor has gone offline
        sensor.last_health_status = 'offline'
        minutes_offline = int(
            (datetime.utcnow() - last_seen).total_seconds() / 60
        )
        newly_offline.append((sensor, minutes_offline))

        logger.warning(
            f"Sensor {sensor.name} (ID {sensor.id}) detected offline "
            f"({minutes_offline} minutes since last activity)",
            extra={'extra_context': {
                'sensor_id': sensor.id,
                'minutes_offline': minutes_offline,
                'operation': 'sensor_offline_detected',
            }}
        )

    # Batch-commit all status changes
    db.session.commit()

    for sensor, minutes_offline in newly_offline:
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

    location_label = get_location_label(sensor.id)

    # Find all users with enabled thresholds for this sensor (or global)
    thresholds = AlertThreshold.query.filter(
        AlertThreshold.is_enabled == True,  # noqa: E712
        or_(
            AlertThreshold.sensor_id == sensor.id,
            AlertThreshold.sensor_id.is_(None),
        )
    ).all()

    alerted_user_ids = set()
    for threshold in thresholds:
        user_id = threshold.user_id
        if user_id in alerted_user_ids:
            continue

        # Check cooldown
        if is_in_cooldown(user_id, sensor.id, OFFLINE_COOLDOWN_MINUTES, 'critical', allow_escalation=False):
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
        upsert_cooldown(user_id, sensor.id, 'critical')

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


