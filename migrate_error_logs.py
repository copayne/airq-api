#!/usr/bin/env python3
"""
Migration script to create ApplicationErrorLog table
Run this script to add the new error logging table to the database
"""

from app import create_app, db
from app.models import ApplicationErrorLog
from sqlalchemy import inspect

def create_error_logs_table():
    """Create the ApplicationErrorLog table if it doesn't exist"""
    app = create_app()
    
    with app.app_context():
        try:
            # Check if table already exists
            inspector = inspect(db.engine)
            if not inspector.has_table('application_error_logs'):
                # Create the table
                db.create_all()
                print("✓ ApplicationErrorLog table created successfully")
                
                # Create test entry to verify table works
                test_log = ApplicationErrorLog(
                    level='INFO',
                    message='Test log entry - migration successful',
                    context={'migration': True, 'version': '1.0'}
                )
                db.session.add(test_log)
                db.session.commit()
                print("✓ Test log entry created successfully")
                
                # Clean up test entry
                db.session.delete(test_log)
                db.session.commit()
                print("✓ Test log entry cleaned up")
                
            else:
                print("ApplicationErrorLog table already exists")
                
        except Exception as e:
            print(f"Error creating ApplicationErrorLog table: {e}")
            raise

if __name__ == '__main__':
    create_error_logs_table()