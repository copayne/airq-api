#!/usr/bin/env python3
"""
Migration script to add Cameras table and update RingSnapshot relationship.

This migration:
1. Creates the cameras table
2. Seeds the initial Front Porch camera (device_id: 59852574)
3. Migrates existing ring_snapshots to use camera_id foreign key
4. Removes device_id and device_name columns from ring_snapshots

Run with: python3 migrate_cameras.py
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from app import create_app, db
from app.models import Camera, RingSnapshot
from datetime import datetime
from sqlalchemy import text, inspect


def migrate_cameras():
    """Perform the cameras table migration."""
    app = create_app()

    with app.app_context():
        inspector = inspect(db.engine)
        existing_tables = inspector.get_table_names()

        print("Starting cameras migration...")

        # Step 1: Create cameras table if it doesn't exist
        if 'cameras' not in existing_tables:
            print("Creating cameras table...")
            db.engine.execute(text("""
                CREATE TABLE cameras (
                    id SERIAL PRIMARY KEY,
                    device_id VARCHAR(100) NOT NULL UNIQUE,
                    name VARCHAR(255) NOT NULL,
                    location VARCHAR(255),
                    model VARCHAR(100),
                    is_active BOOLEAN NOT NULL DEFAULT true,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """))

            db.engine.execute(text("""
                CREATE INDEX idx_cameras_device_id ON cameras(device_id)
            """))
            print("✓ Cameras table created")
        else:
            print("✓ Cameras table already exists")

        # Step 2: Insert initial Front Porch camera
        existing_camera = db.session.execute(
            text("SELECT id FROM cameras WHERE device_id = '59852574'")
        ).fetchone()

        if not existing_camera:
            print("Seeding initial Front Porch camera...")
            db.engine.execute(text("""
                INSERT INTO cameras (device_id, name, location, model, is_active, created_at, updated_at)
                VALUES ('59852574', 'Front Porch', 'Front Porch', 'Ring Camera', true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """))
            print("✓ Front Porch camera created")
        else:
            print("✓ Front Porch camera already exists")

        # Step 3: Check if ring_snapshots needs migration
        ring_snapshots_columns = [col['name'] for col in inspector.get_columns('ring_snapshots')]

        if 'camera_id' not in ring_snapshots_columns:
            print("Migrating ring_snapshots table...")

            # Add camera_id column (nullable temporarily)
            db.engine.execute(text("""
                ALTER TABLE ring_snapshots
                ADD COLUMN camera_id INTEGER
            """))
            print("✓ Added camera_id column")

            # Update existing snapshots to reference Front Porch camera
            db.engine.execute(text("""
                UPDATE ring_snapshots
                SET camera_id = (SELECT id FROM cameras WHERE device_id = '59852574')
                WHERE device_id = '59852574'
            """))
            print("✓ Updated existing snapshots with camera_id")

            # Make camera_id NOT NULL and add foreign key
            db.engine.execute(text("""
                ALTER TABLE ring_snapshots
                ALTER COLUMN camera_id SET NOT NULL
            """))

            db.engine.execute(text("""
                ALTER TABLE ring_snapshots
                ADD CONSTRAINT fk_ring_snapshots_camera_id
                FOREIGN KEY (camera_id) REFERENCES cameras(id)
            """))
            print("✓ Added foreign key constraint")

            # Add index on camera_id
            db.engine.execute(text("""
                CREATE INDEX idx_ring_snapshots_camera_id ON ring_snapshots(camera_id)
            """))
            print("✓ Added camera_id index")

            # Drop old columns
            if 'device_id' in ring_snapshots_columns:
                db.engine.execute(text("""
                    ALTER TABLE ring_snapshots
                    DROP COLUMN device_id
                """))
                print("✓ Dropped device_id column")

            if 'device_name' in ring_snapshots_columns:
                db.engine.execute(text("""
                    ALTER TABLE ring_snapshots
                    DROP COLUMN device_name
                """))
                print("✓ Dropped device_name column")
        else:
            print("✓ ring_snapshots already migrated")

        # Step 4: Verify migration
        print("\nVerifying migration...")

        camera_count = db.session.execute(text("SELECT COUNT(*) FROM cameras")).scalar()
        print(f"✓ Cameras in database: {camera_count}")

        snapshot_count = db.session.execute(text("SELECT COUNT(*) FROM ring_snapshots")).scalar()
        print(f"✓ Snapshots in database: {snapshot_count}")

        if snapshot_count > 0:
            snapshot_with_camera = db.session.execute(
                text("SELECT COUNT(*) FROM ring_snapshots WHERE camera_id IS NOT NULL")
            ).scalar()
            print(f"✓ Snapshots with camera reference: {snapshot_with_camera}")

        print("\n✓ Migration completed successfully!")
        return 0


if __name__ == '__main__':
    try:
        sys.exit(migrate_cameras())
    except Exception as e:
        print(f"\n✗ Migration failed: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
