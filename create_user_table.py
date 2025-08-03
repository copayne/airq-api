#!/usr/bin/env python3
"""
Create User table for authentication system.
Run this script to add the User table to the existing database.
"""

from app import create_app, db
from app.models import User
from config import get_config

def create_user_table():
    """Create User table in the database."""
    app = create_app()
    
    with app.app_context():
        try:
            # Create User table
            db.create_all()
            print("✓ User table created successfully")
            
            # Create default admin user
            admin_user = User.query.filter_by(username='admin').first()
            if not admin_user:
                admin_user = User(
                    username='admin',
                    email='admin@airq.local',
                    first_name='AirQ',
                    last_name='Administrator',
                    role='admin'
                )
                admin_user.set_password('admin123')  # Default password - should be changed
                
                db.session.add(admin_user)
                db.session.commit()
                print("✓ Default admin user created (username: admin, password: admin123)")
                print("⚠️  IMPORTANT: Change the default admin password immediately!")
            else:
                print("✓ Admin user already exists")
                
        except Exception as e:
            print(f"❌ Error creating User table: {e}")
            raise

if __name__ == "__main__":
    create_user_table()