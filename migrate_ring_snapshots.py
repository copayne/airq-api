#!/usr/bin/env python3
"""
Migration script to create RingSnapshot table
Run this script to add the Ring camera snapshot storage table to the database
"""

from app import create_app, db
from app.models import RingSnapshot
from sqlalchemy import inspect
from datetime import datetime

def create_ring_snapshots_table():
    """Create the RingSnapshot table if it doesn't exist"""
    app = create_app()

    with app.app_context():
        try:
            inspector = inspect(db.engine)
            if not inspector.has_table('ring_snapshots'):
                db.create_all()
                print("✓ RingSnapshot table created successfully")

                test_snapshot = RingSnapshot(
                    device_id='test_device',
                    device_name='Test Camera',
                    image_path='/test/path/test.jpg',
                    capture_timestamp=datetime.utcnow(),
                    file_size=1024
                )
                db.session.add(test_snapshot)
                db.session.commit()
                print("✓ Test snapshot entry created successfully")

                db.session.delete(test_snapshot)
                db.session.commit()
                print("✓ Test snapshot entry cleaned up")

            else:
                print("RingSnapshot table already exists")

        except Exception as e:
            print(f"Error creating RingSnapshot table: {e}")
            raise

if __name__ == '__main__':
    create_ring_snapshots_table()
