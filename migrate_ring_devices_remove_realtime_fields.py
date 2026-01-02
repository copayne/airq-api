#!/usr/bin/env python3
"""
Migration script to remove real-time fields from ring_devices table.

These fields (battery_level, status, last_update) are now managed
in real-time via websocket and don't need to be stored in the database.

This migration:
1. Drops battery_level column
2. Drops status column
3. Drops last_update column and its index

Run with: python3 migrate_ring_devices_remove_realtime_fields.py
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from app import create_app, db
from sqlalchemy import text, inspect


def migrate_remove_realtime_fields():
    """Remove real-time fields from ring_devices table."""
    app = create_app()

    with app.app_context():
        inspector = inspect(db.engine)

        print("Starting ring_devices schema migration...")
        print("Removing real-time fields (battery_level, status, last_update)...\n")

        # Check if table exists
        if 'ring_devices' not in inspector.get_table_names():
            print("✗ ring_devices table does not exist!")
            return 1

        # Get current columns
        columns = {col['name'] for col in inspector.get_columns('ring_devices')}

        # Drop last_update index if it exists
        indexes = inspector.get_indexes('ring_devices')
        if any(idx['name'] == 'idx_ring_devices_last_update' for idx in indexes):
            print("Dropping index idx_ring_devices_last_update...")
            db.engine.execute(text("""
                DROP INDEX IF EXISTS idx_ring_devices_last_update
            """))
            print("✓ Index dropped")

        # Drop columns if they exist
        columns_to_drop = ['battery_level', 'status', 'last_update']

        for column in columns_to_drop:
            if column in columns:
                print(f"Dropping column {column}...")
                db.engine.execute(text(f"""
                    ALTER TABLE ring_devices DROP COLUMN IF EXISTS {column}
                """))
                print(f"✓ Column {column} dropped")
            else:
                print(f"  Column {column} already removed")

        print("\nVerifying migration...")
        remaining_columns = {col['name'] for col in inspector.get_columns('ring_devices')}
        print(f"✓ Remaining columns: {', '.join(sorted(remaining_columns))}")

        # Verify none of the dropped columns remain
        removed = set(columns_to_drop)
        still_present = removed & remaining_columns

        if still_present:
            print(f"\n✗ Migration incomplete: {still_present} still present")
            return 1

        device_count = db.session.execute(text("SELECT COUNT(*) FROM ring_devices")).scalar()
        print(f"✓ Ring devices in database: {device_count}")

        print("\n✓ Migration completed successfully!")
        print("\nDatabase now stores only static device info.")
        print("Real-time data (battery, status) managed via websocket.\n")
        return 0


if __name__ == '__main__':
    try:
        sys.exit(migrate_remove_realtime_fields())
    except Exception as e:
        print(f"\n✗ Migration failed: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
