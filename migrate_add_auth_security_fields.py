#!/usr/bin/env python3
"""
Database migration script to add authentication security fields.
Adds new columns for email verification, password reset, and account locking.
"""

import os
import sys
from sqlalchemy import text

# Add the current directory to Python path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app, db
from config import get_config

def migrate_add_auth_security_fields():
    """Add authentication security fields to the users table."""
    
    app = create_app()
    
    with app.app_context():
        try:
            print("🔧 Starting authentication security fields migration...")
            
            # List of new columns to add
            migrations = [
                # Email verification fields
                "ALTER TABLE users ADD COLUMN email_verified BOOLEAN NOT NULL DEFAULT FALSE",
                "ALTER TABLE users ADD COLUMN email_verification_token VARCHAR(255)",
                "ALTER TABLE users ADD COLUMN email_verification_expires TIMESTAMP",
                
                # Password reset fields
                "ALTER TABLE users ADD COLUMN password_reset_token VARCHAR(255)",
                "ALTER TABLE users ADD COLUMN password_reset_expires TIMESTAMP",
                
                # Account security fields
                "ALTER TABLE users ADD COLUMN failed_login_attempts INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE users ADD COLUMN account_locked_until TIMESTAMP",
            ]
            
            # Create indexes for performance
            indexes = [
                "CREATE INDEX IF NOT EXISTS idx_users_email_verification_token ON users(email_verification_token)",
                "CREATE INDEX IF NOT EXISTS idx_users_password_reset_token ON users(password_reset_token)",
            ]
            
            # Execute column additions
            for migration_sql in migrations:
                try:
                    print(f"  📝 Executing: {migration_sql[:50]}...")
                    db.session.execute(text(migration_sql))
                    db.session.commit()
                    print("  ✅ Success")
                except Exception as e:
                    # Column might already exist, check if it's that error
                    if "already exists" in str(e).lower() or "duplicate column" in str(e).lower():
                        print(f"  ⚠️  Column already exists, skipping: {str(e)}")
                        db.session.rollback()
                    else:
                        print(f"  ❌ Error: {str(e)}")
                        db.session.rollback()
                        raise
            
            # Execute index creation
            for index_sql in indexes:
                try:
                    print(f"  📝 Creating index: {index_sql[:50]}...")
                    db.session.execute(text(index_sql))
                    db.session.commit()
                    print("  ✅ Success")
                except Exception as e:
                    if "already exists" in str(e).lower():
                        print(f"  ⚠️  Index already exists, skipping")
                        db.session.rollback()
                    else:
                        print(f"  ❌ Error: {str(e)}")
                        db.session.rollback()
                        raise
            
            print("\n🔧 Creating token_blacklist table...")
            
            # Create token blacklist table
            token_blacklist_sql = """
            CREATE TABLE IF NOT EXISTS token_blacklist (
                id SERIAL PRIMARY KEY,
                jti VARCHAR(255) NOT NULL UNIQUE,
                token_type VARCHAR(20) NOT NULL,
                user_id INTEGER NOT NULL REFERENCES users(id),
                revoked_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP NOT NULL
            )
            """
            
            db.session.execute(text(token_blacklist_sql))
            db.session.commit()
            print("  ✅ token_blacklist table created")
            
            # Create indexes for token_blacklist
            blacklist_indexes = [
                "CREATE INDEX IF NOT EXISTS idx_token_blacklist_jti ON token_blacklist(jti)",
                "CREATE INDEX IF NOT EXISTS idx_token_blacklist_user_id ON token_blacklist(user_id)",
                "CREATE INDEX IF NOT EXISTS idx_token_blacklist_revoked_at ON token_blacklist(revoked_at)",
                "CREATE INDEX IF NOT EXISTS idx_token_blacklist_expires_at ON token_blacklist(expires_at)",
            ]
            
            for index_sql in blacklist_indexes:
                try:
                    print(f"  📝 Creating index: {index_sql.split('ON')[1].strip()}")
                    db.session.execute(text(index_sql))
                    db.session.commit()
                    print("  ✅ Success")
                except Exception as e:
                    if "already exists" in str(e).lower():
                        print(f"  ⚠️  Index already exists, skipping")
                        db.session.rollback()
                    else:
                        print(f"  ❌ Error: {str(e)}")
                        db.session.rollback()
                        raise
            
            print("\n✅ Authentication security fields migration completed successfully!")
            print("\n📋 Summary of changes:")
            print("   • Added email verification fields to users table")
            print("   • Added password reset fields to users table")
            print("   • Added account locking fields to users table")
            print("   • Created token_blacklist table for logout functionality")
            print("   • Created performance indexes")
            print("\n🔒 Security enhancements now available:")
            print("   • Email verification for new accounts")
            print("   • Secure password reset functionality")
            print("   • Account locking after failed login attempts")
            print("   • Token blacklisting for secure logout")
            
        except Exception as e:
            print(f"\n❌ Migration failed: {str(e)}")
            db.session.rollback()
            sys.exit(1)

if __name__ == "__main__":
    migrate_add_auth_security_fields()