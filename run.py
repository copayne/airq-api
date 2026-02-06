import os
import signal
import sys
from app import create_app, db

app = create_app()

# Graceful shutdown state
shutdown_in_progress = False


def graceful_shutdown(signum, frame):
    """Handle SIGTERM and SIGINT for graceful shutdown."""
    global shutdown_in_progress

    if shutdown_in_progress:
        return
    shutdown_in_progress = True

    sig_name = signal.Signals(signum).name
    app.logger.info(f"Received {sig_name}, initiating graceful shutdown...")

    try:
        # Close database connections
        with app.app_context():
            db.session.remove()
            db.engine.dispose()
            app.logger.info("Database connections closed")
    except Exception as e:
        app.logger.error(f"Error during database cleanup: {e}")

    # Stop SocketIO if running
    socketio = app.extensions.get('socketio')
    if socketio:
        try:
            socketio.stop()
            app.logger.info("SocketIO server stopped")
        except Exception as e:
            app.logger.error(f"Error stopping SocketIO: {e}")

    app.logger.info("Shutdown complete")
    sys.exit(0)


if __name__ == '__main__':
    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGTERM, graceful_shutdown)
    signal.signal(signal.SIGINT, graceful_shutdown)

    with app.app_context():
        db.create_all()

    # Environment-based configuration
    debug_mode = os.getenv('FLASK_DEBUG', 'false').lower() == 'true'
    host = os.getenv('FLASK_HOST', '0.0.0.0')  # Default to all interfaces for network access
    port = int(os.getenv('FLASK_PORT', '5000'))

    if debug_mode:
        app.logger.info(f"Starting development server on {host}:{port}")
    else:
        app.logger.info(f"Starting production server on {host}:{port}")

    # Use SocketIO server to handle both HTTP and WebSocket connections
    socketio = app.extensions.get('socketio')
    if socketio:
        socketio.run(app, host=host, port=port, debug=debug_mode)
    else:
        app.run(host=host, port=port, debug=debug_mode)