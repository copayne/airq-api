import os
from app import create_app, db

app = create_app()

if __name__ == '__main__':
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
    
    app.run(host=host, port=port, debug=debug_mode)