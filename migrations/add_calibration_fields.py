#!/usr/bin/env python3
"""
Migration: Add calibration fields to sensors table.

Run with: python3 migrations/add_calibration_fields.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app, db
from sqlalchemy import text

def migrate():
    """Add calibration fields to sensors table."""
    app = create_app()

    with app.app_context():
        conn = db.engine.connect()
        trans = conn.begin()

        try:
            # Check if columns already exist
            result = conn.execute(text("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'sensors' AND column_name = 'calibration_port'
            """))

            if result.fetchone():
                print("Calibration fields already exist. Skipping migration.")
                return

            print("Adding calibration fields to sensors table...")

            # Add calibration_port
            conn.execute(text("""
                ALTER TABLE sensors
                ADD COLUMN IF NOT EXISTS calibration_port INTEGER DEFAULT 5001
            """))
            print("  - Added calibration_port")

            # Add last_calibration_time
            conn.execute(text("""
                ALTER TABLE sensors
                ADD COLUMN IF NOT EXISTS last_calibration_time TIMESTAMP
            """))
            print("  - Added last_calibration_time")

            # Add last_calibration_reference_co2
            conn.execute(text("""
                ALTER TABLE sensors
                ADD COLUMN IF NOT EXISTS last_calibration_reference_co2 INTEGER
            """))
            print("  - Added last_calibration_reference_co2")

            # Add auto_calibration_enabled
            conn.execute(text("""
                ALTER TABLE sensors
                ADD COLUMN IF NOT EXISTS auto_calibration_enabled BOOLEAN DEFAULT TRUE
            """))
            print("  - Added auto_calibration_enabled")

            # Add temperature_offset
            conn.execute(text("""
                ALTER TABLE sensors
                ADD COLUMN IF NOT EXISTS temperature_offset FLOAT DEFAULT 0.0
            """))
            print("  - Added temperature_offset")

            trans.commit()
            print("\nMigration complete!")

        except Exception as e:
            trans.rollback()
            print(f"Migration failed: {e}")
            raise
        finally:
            conn.close()


if __name__ == "__main__":
    migrate()
