#!/usr/bin/env python3
"""
Ring Camera Snapshot Capture Script

This script captures a snapshot from a Ring camera using the RingSnapshotDownload tool
and stores the metadata in the database.

Usage:
    python3 capture_ring_snapshot.py

Exit Codes:
    0 - Success
    1 - Error occurred during capture
"""

import os
import sys
import subprocess
import json
from datetime import datetime
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app import create_app, db
from app.models import RingSnapshot


def capture_ring_snapshot():
    """Capture a Ring camera snapshot and save metadata to database."""

    ring_capture_binary = "/home/copayne/dev/airq/ring-capture/RingSnapshotDownload"
    output_directory = "/home/copayne/dev/airq/ring-snapshots"
    settings_file = "/home/copayne/dev/airq/ring-capture/Settings.json"

    if not os.path.exists(ring_capture_binary):
        print(f"Error: Ring capture binary not found at {ring_capture_binary}", file=sys.stderr)
        return 1

    if not os.path.exists(output_directory):
        print(f"Error: Output directory not found at {output_directory}", file=sys.stderr)
        return 1

    if not os.path.exists(settings_file):
        print(f"Error: Settings file not found at {settings_file}", file=sys.stderr)
        return 1

    try:
        with open(settings_file, 'r') as f:
            settings = json.load(f)
    except Exception as e:
        print(f"Error reading settings file: {e}", file=sys.stderr)
        return 1

    device_id = settings.get('RingDeviceId')
    if not device_id:
        print("Error: RingDeviceId not configured in Settings.json", file=sys.stderr)
        return 1

    capture_timestamp = datetime.utcnow()

    try:
        result = subprocess.run(
            [
                ring_capture_binary,
                '-out', output_directory,
                '-deviceid', device_id,
                '-force'
            ],
            capture_output=True,
            text=True,
            timeout=55,
            cwd=os.path.dirname(ring_capture_binary)
        )

        if result.returncode != 0:
            print(f"Ring capture failed: {result.stderr}", file=sys.stderr)
            return 1

        print(f"Ring capture successful: {result.stdout}")

    except subprocess.TimeoutExpired:
        print("Error: Ring capture timed out after 55 seconds", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Error running Ring capture: {e}", file=sys.stderr)
        return 1

    latest_image = None
    latest_mtime = 0

    try:
        for filename in os.listdir(output_directory):
            if filename.endswith('.jpg') or filename.endswith('.jpeg'):
                filepath = os.path.join(output_directory, filename)
                mtime = os.path.getmtime(filepath)
                if mtime > latest_mtime:
                    latest_mtime = mtime
                    latest_image = filepath
    except Exception as e:
        print(f"Error finding latest image: {e}", file=sys.stderr)
        return 1

    if not latest_image:
        print("Error: No snapshot image found in output directory", file=sys.stderr)
        return 1

    try:
        file_size = os.path.getsize(latest_image)
    except Exception as e:
        print(f"Error getting file size: {e}", file=sys.stderr)
        file_size = None

    device_name = f"Ring Camera {device_id}"

    app = create_app()
    with app.app_context():
        try:
            snapshot = RingSnapshot(
                device_id=device_id,
                device_name=device_name,
                image_path=latest_image,
                capture_timestamp=capture_timestamp,
                file_size=file_size
            )

            db.session.add(snapshot)
            db.session.commit()

            print(f"Snapshot record created: ID={snapshot.id}, Path={latest_image}, Size={file_size} bytes")
            return 0

        except Exception as e:
            db.session.rollback()
            print(f"Error saving snapshot to database: {e}", file=sys.stderr)
            return 1


if __name__ == '__main__':
    sys.exit(capture_ring_snapshot())
