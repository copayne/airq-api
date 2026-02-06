#!/bin/bash
#
# AirQ Database Backup Script
#
# Creates timestamped PostgreSQL backups with rotation policy:
# - Keeps 7 daily backups
# - Keeps 4 weekly backups (Sundays)
#
# Usage: ./backup_database.sh [backup_dir]
#
# Cron example (daily at 2 AM):
#   0 2 * * * /path/to/backup_database.sh /path/to/backups
#

set -e

# Configuration
BACKUP_DIR="${1:-$HOME/airq-backups}"
DB_NAME="${AIRQ_DB_NAME:-airq}"
DB_USER="${AIRQ_DB_USER:-postgres}"
DB_HOST="${AIRQ_DB_HOST:-localhost}"
DAILY_KEEP=7
WEEKLY_KEEP=4

# Create backup directory if it doesn't exist
mkdir -p "$BACKUP_DIR/daily"
mkdir -p "$BACKUP_DIR/weekly"

# Generate timestamp
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
DAY_OF_WEEK=$(date +%u)  # 1=Monday, 7=Sunday

# Backup filename
BACKUP_FILE="airq_backup_${TIMESTAMP}.sql.gz"

echo "Starting backup of database '$DB_NAME'..."

# Create compressed backup
pg_dump -h "$DB_HOST" -U "$DB_USER" "$DB_NAME" | gzip > "$BACKUP_DIR/daily/$BACKUP_FILE"

if [ $? -eq 0 ]; then
    echo "Backup created: $BACKUP_DIR/daily/$BACKUP_FILE"

    # If it's Sunday, also save as weekly backup
    if [ "$DAY_OF_WEEK" -eq 7 ]; then
        cp "$BACKUP_DIR/daily/$BACKUP_FILE" "$BACKUP_DIR/weekly/$BACKUP_FILE"
        echo "Weekly backup created: $BACKUP_DIR/weekly/$BACKUP_FILE"
    fi
else
    echo "ERROR: Backup failed!"
    exit 1
fi

# Rotate daily backups (keep last N)
echo "Rotating daily backups (keeping last $DAILY_KEEP)..."
ls -t "$BACKUP_DIR/daily/"*.sql.gz 2>/dev/null | tail -n +$((DAILY_KEEP + 1)) | xargs -r rm -f

# Rotate weekly backups (keep last N)
echo "Rotating weekly backups (keeping last $WEEKLY_KEEP)..."
ls -t "$BACKUP_DIR/weekly/"*.sql.gz 2>/dev/null | tail -n +$((WEEKLY_KEEP + 1)) | xargs -r rm -f

# Show current backups
echo ""
echo "Current backups:"
echo "Daily:"
ls -lh "$BACKUP_DIR/daily/"*.sql.gz 2>/dev/null || echo "  (none)"
echo "Weekly:"
ls -lh "$BACKUP_DIR/weekly/"*.sql.gz 2>/dev/null || echo "  (none)"

echo ""
echo "Backup complete!"
