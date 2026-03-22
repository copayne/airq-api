#!/usr/bin/env python3
"""
Migration script to add security tables for Hudson Security.

This migration:
1. Creates the security_devices table
2. Creates the security_events table
3. Creates the security_automations table
4. Creates the security_daily_summaries table
5. Creates the security_settings table

Run with: python3 migrate_security.py
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from app import create_app, db
from app.models import SecurityDevice, SecurityEvent, SecurityAutomation, SecurityDailySummary, SecuritySettings
from sqlalchemy import text, inspect


def migrate_security():
    """Perform the security tables migration."""
    app = create_app()

    with app.app_context():
        inspector = inspect(db.engine)
        existing_tables = inspector.get_table_names()

        print("Starting security tables migration...")

        # 1. Create security_devices table
        if 'security_devices' not in existing_tables:
            print("Creating security_devices table...")
            db.engine.execute(text("""
                CREATE TABLE IF NOT EXISTS security_devices (
                    id SERIAL PRIMARY KEY,
                    device_id VARCHAR(100) NOT NULL UNIQUE,
                    device_type VARCHAR(50) NOT NULL,
                    name VARCHAR(200) NOT NULL,
                    location VARCHAR(200),
                    provider VARCHAR(50) NOT NULL DEFAULT 'ring',
                    is_active BOOLEAN DEFAULT true,
                    battery_level INTEGER,
                    status VARCHAR(50),
                    last_status_change TIMESTAMP,
                    metadata JSON,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """))

            db.engine.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_security_devices_device_id ON security_devices(device_id)
            """))

            db.engine.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_security_devices_device_type ON security_devices(device_type)
            """))

            print("✓ security_devices table created")
        else:
            print("✓ security_devices table already exists")

        # 2. Create security_events table
        if 'security_events' not in existing_tables:
            print("Creating security_events table...")
            db.engine.execute(text("""
                CREATE TABLE IF NOT EXISTS security_events (
                    id SERIAL PRIMARY KEY,
                    device_id INTEGER NOT NULL REFERENCES security_devices(id),
                    event_type VARCHAR(50) NOT NULL,
                    severity VARCHAR(20) NOT NULL DEFAULT 'info',
                    message VARCHAR(500),
                    metadata JSON,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """))

            db.engine.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_security_events_device_id ON security_events(device_id)
            """))

            db.engine.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_security_events_event_type ON security_events(event_type)
            """))

            db.engine.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_security_events_created_at ON security_events(created_at)
            """))

            db.engine.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_security_events_device_created ON security_events(device_id, created_at)
            """))

            print("✓ security_events table created")
        else:
            print("✓ security_events table already exists")

        # 3. Create security_automations table
        if 'security_automations' not in existing_tables:
            print("Creating security_automations table...")
            db.engine.execute(text("""
                CREATE TABLE IF NOT EXISTS security_automations (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    name VARCHAR(200) NOT NULL,
                    trigger_type VARCHAR(50) NOT NULL,
                    trigger_config JSON NOT NULL,
                    action_type VARCHAR(50) NOT NULL,
                    action_config JSON NOT NULL,
                    is_enabled BOOLEAN DEFAULT true,
                    last_triggered TIMESTAMP,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """))

            db.engine.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_security_automations_user_id ON security_automations(user_id)
            """))

            print("✓ security_automations table created")
        else:
            print("✓ security_automations table already exists")

        # 4. Create security_daily_summaries table
        if 'security_daily_summaries' not in existing_tables:
            print("Creating security_daily_summaries table...")
            db.engine.execute(text("""
                CREATE TABLE IF NOT EXISTS security_daily_summaries (
                    id SERIAL PRIMARY KEY,
                    summary_date DATE NOT NULL UNIQUE,
                    total_events INTEGER NOT NULL DEFAULT 0,
                    door_opens INTEGER NOT NULL DEFAULT 0,
                    motion_events INTEGER NOT NULL DEFAULT 0,
                    alarm_state_changes INTEGER NOT NULL DEFAULT 0,
                    alerts_triggered INTEGER NOT NULL DEFAULT 0,
                    summary_data JSON,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """))

            db.engine.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_security_daily_summaries_date ON security_daily_summaries(summary_date)
            """))

            print("✓ security_daily_summaries table created")
        else:
            print("✓ security_daily_summaries table already exists")

        # 5. Create security_settings table
        if 'security_settings' not in existing_tables:
            print("Creating security_settings table...")
            db.engine.execute(text("""
                CREATE TABLE IF NOT EXISTS security_settings (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
                    email_digest_enabled BOOLEAN NOT NULL DEFAULT false,
                    email_digest_time VARCHAR(5) NOT NULL DEFAULT '08:00',
                    door_open_alert_minutes INTEGER NOT NULL DEFAULT 5,
                    preferences JSON,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """))

            db.engine.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_security_settings_user_id ON security_settings(user_id)
            """))

            print("✓ security_settings table created")
        else:
            print("✓ security_settings table already exists")

        print("\nVerifying migration...")
        for table_name in ['security_devices', 'security_events', 'security_automations',
                           'security_daily_summaries', 'security_settings']:
            count = db.session.execute(text(f"SELECT COUNT(*) FROM {table_name}")).scalar()
            print(f"✓ {table_name}: {count} rows")

        print("\n✓ Migration completed successfully!")
        return 0


if __name__ == '__main__':
    try:
        sys.exit(migrate_security())
    except Exception as e:
        print(f"\n✗ Migration failed: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
