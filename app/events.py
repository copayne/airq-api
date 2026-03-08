"""WebSocket event handling via Flask-SocketIO.

Provides real-time push events for sensor readings and alerts.
JWT authentication is enforced on connection.
"""

import logging
from typing import Any, Dict

from flask import Flask
from flask_socketio import SocketIO, disconnect, join_room

from app.models import User

logger = logging.getLogger(__name__)

socketio = SocketIO()


def init_socketio(app: Flask) -> SocketIO:
    """Initialize SocketIO with the Flask app."""
    cors_origins = app.config.get('CORS_ORIGINS', [])
    socketio.init_app(
        app,
        cors_allowed_origins=cors_origins or '*',
        async_mode=app.config.get('SOCKETIO_ASYNC_MODE', 'threading'),
        logger=False,
        engineio_logger=False,
    )
    app.extensions['socketio'] = socketio

    @socketio.on('connect')
    def handle_connect(auth=None):
        """Authenticate WebSocket connections using JWT."""
        if not auth or 'token' not in auth:
            logger.warning("WebSocket connection rejected: no auth token")
            disconnect()
            return False

        user = User.verify_jwt_token(auth['token'])
        if not user:
            logger.warning("WebSocket connection rejected: invalid or expired token")
            disconnect()
            return False

        join_room(f'user_{user.id}')
        logger.info(
            "WebSocket client connected",
            extra={'extra_context': {
                'user_id': user.id,
                'operation': 'websocket_connect',
            }}
        )
        return True

    @socketio.on('disconnect')
    def handle_disconnect():
        logger.debug("WebSocket client disconnected")

    return socketio


def publish_sensor_reading(data: Dict[str, Any]) -> None:
    """Emit a sensor_reading event to all connected clients."""
    try:
        socketio.emit('sensor_reading', data)
    except Exception:
        logger.error(
            "Failed to publish sensor reading event",
            exc_info=True,
            extra={'extra_context': {'operation': 'publish_sensor_reading_error'}}
        )


def publish_sensor_health(data: Dict[str, Any]) -> None:
    """Emit a sensor_health event to all connected clients."""
    try:
        socketio.emit('sensor_health', data)
    except Exception:
        logger.error(
            "Failed to publish sensor health event",
            exc_info=True,
            extra={'extra_context': {'operation': 'publish_sensor_health_error'}}
        )


def publish_alert(user_id: int, data: Dict[str, Any]) -> None:
    """Emit an alert event to a specific user's room."""
    try:
        socketio.emit('alert', data, to=f'user_{user_id}')
    except Exception:
        logger.error(
            "Failed to publish alert event",
            exc_info=True,
            extra={'extra_context': {
                'user_id': user_id,
                'operation': 'publish_alert_error',
            }}
        )
