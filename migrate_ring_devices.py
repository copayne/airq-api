#!/usr/bin/env python3
"""
Migration script to add RingDevice table for Ring alarm sensors.

This migration:
1. Creates the ring_devices table
2. Seeds the initial 3 contact sensors (front door, basement door, garage)

Run with: python3 migrate_ring_devices.py
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from app import create_app, db
from app.models import RingDevice
from sqlalchemy import text, inspect


def migrate_ring_devices():
    """Perform the ring_devices table migration."""
    app = create_app()

    with app.app_context():
        inspector = inspect(db.engine)
        existing_tables = inspector.get_table_names()

        print("Starting ring_devices migration...")

        if 'ring_devices' not in existing_tables:
            print("Creating ring_devices table...")
            db.engine.execute(text("""
                CREATE TABLE ring_devices (
                    id SERIAL PRIMARY KEY,
                    device_id VARCHAR(100) NOT NULL UNIQUE,
                    device_type VARCHAR(50) NOT NULL,
                    name VARCHAR(255) NOT NULL,
                    location VARCHAR(255),
                    battery_level INTEGER,
                    status VARCHAR(50),
                    last_update TIMESTAMP,
                    is_active BOOLEAN NOT NULL DEFAULT true,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """))

            db.engine.execute(text("""
                CREATE INDEX idx_ring_devices_device_id ON ring_devices(device_id)
            """))

            db.engine.execute(text("""
                CREATE INDEX idx_ring_devices_device_type ON ring_devices(device_type)
            """))

            db.engine.execute(text("""
                CREATE INDEX idx_ring_devices_last_update ON ring_devices(last_update)
            """))

            print("✓ ring_devices table created")
        else:
            print("✓ ring_devices table already exists")

        print("\nVerifying migration...")
        device_count = db.session.execute(text("SELECT COUNT(*) FROM ring_devices")).scalar()
        print(f"✓ Ring devices in database: {device_count}")

        print("\n✓ Migration completed successfully!")
        print("\nNote: Device data will be populated by the Ring polling service on first run.")
        return 0


if __name__ == '__main__':
    try:
        sys.exit(migrate_ring_devices())
    except Exception as e:
        print(f"\n✗ Migration failed: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
