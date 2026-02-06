#!/usr/bin/env python3
"""
Data Retention Script for AirQ

Purges sensor readings older than a specified retention period.
By default, keeps 90 days of data.

Usage:
    python purge_old_readings.py [--days N] [--dry-run]

Options:
    --days N      Keep readings from the last N days (default: 90)
    --dry-run     Show what would be deleted without actually deleting

Cron example (weekly on Sunday at 3 AM):
    0 3 * * 0 cd /path/to/airq-api && python scripts/purge_old_readings.py >> /var/log/airq-purge.log 2>&1
"""

import argparse
import sys
from datetime import datetime, timedelta

# Add parent directory to path for imports
sys.path.insert(0, '..')

from app import create_app, db
from app.models import SensorReading, HumidityReading, TemperatureReading, CO2Reading, ErrorLog


def purge_old_readings(retention_days: int, dry_run: bool = False) -> dict:
    """Purge readings older than retention_days.

    Returns dict with counts of deleted records.
    """
    cutoff_date = datetime.utcnow() - timedelta(days=retention_days)

    print(f"Retention policy: {retention_days} days")
    print(f"Cutoff date: {cutoff_date.isoformat()}")
    print(f"Dry run: {dry_run}")
    print("-" * 50)

    # Get IDs of readings to delete
    old_readings = SensorReading.query.filter(
        SensorReading.reading_time < cutoff_date
    ).all()

    reading_ids = [r.id for r in old_readings]

    if not reading_ids:
        print("No readings to purge.")
        return {'sensor_readings': 0, 'humidity': 0, 'temperature': 0, 'co2': 0, 'errors': 0}

    print(f"Found {len(reading_ids)} sensor readings to purge")

    # Count related records
    humidity_count = HumidityReading.query.filter(
        HumidityReading.reading_id.in_(reading_ids)
    ).count()

    temp_count = TemperatureReading.query.filter(
        TemperatureReading.reading_id.in_(reading_ids)
    ).count()

    co2_count = CO2Reading.query.filter(
        CO2Reading.reading_id.in_(reading_ids)
    ).count()

    error_count = ErrorLog.query.filter(
        ErrorLog.reading_id.in_(reading_ids)
    ).count()

    print(f"  - Humidity readings: {humidity_count}")
    print(f"  - Temperature readings: {temp_count}")
    print(f"  - CO2 readings: {co2_count}")
    print(f"  - Error logs: {error_count}")

    if dry_run:
        print("\nDry run - no records deleted.")
        return {
            'sensor_readings': len(reading_ids),
            'humidity': humidity_count,
            'temperature': temp_count,
            'co2': co2_count,
            'errors': error_count
        }

    # Delete in order (child tables first to respect foreign keys)
    print("\nDeleting records...")

    HumidityReading.query.filter(
        HumidityReading.reading_id.in_(reading_ids)
    ).delete(synchronize_session=False)

    TemperatureReading.query.filter(
        TemperatureReading.reading_id.in_(reading_ids)
    ).delete(synchronize_session=False)

    CO2Reading.query.filter(
        CO2Reading.reading_id.in_(reading_ids)
    ).delete(synchronize_session=False)

    ErrorLog.query.filter(
        ErrorLog.reading_id.in_(reading_ids)
    ).delete(synchronize_session=False)

    SensorReading.query.filter(
        SensorReading.id.in_(reading_ids)
    ).delete(synchronize_session=False)

    db.session.commit()

    print("Purge complete!")

    return {
        'sensor_readings': len(reading_ids),
        'humidity': humidity_count,
        'temperature': temp_count,
        'co2': co2_count,
        'errors': error_count
    }


def main():
    parser = argparse.ArgumentParser(description='Purge old sensor readings')
    parser.add_argument('--days', type=int, default=90,
                        help='Keep readings from the last N days (default: 90)')
    parser.add_argument('--dry-run', action='store_true',
                        help='Show what would be deleted without actually deleting')

    args = parser.parse_args()

    print("=" * 50)
    print("AirQ Data Retention - Purge Script")
    print(f"Started: {datetime.utcnow().isoformat()}")
    print("=" * 50)

    app = create_app()

    with app.app_context():
        results = purge_old_readings(args.days, args.dry_run)

    print("\nSummary:")
    print(f"  Sensor readings: {results['sensor_readings']}")
    print(f"  Humidity readings: {results['humidity']}")
    print(f"  Temperature readings: {results['temperature']}")
    print(f"  CO2 readings: {results['co2']}")
    print(f"  Error logs: {results['errors']}")
    print(f"\nFinished: {datetime.utcnow().isoformat()}")


if __name__ == '__main__':
    main()
