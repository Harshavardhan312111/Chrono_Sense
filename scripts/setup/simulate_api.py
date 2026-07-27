#!/usr/bin/env python3

import sqlite3
from datetime import datetime, timedelta

db_path = "/private/tmp/ChronoSenseWeb-clean/backend/profiles.db"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# This is exactly what the API endpoint does
print("="*70)
print("SIMULATING API DEDUPLICATION LOGIC")
print("="*70)

# Get data for last 24 hours
query = """
    SELECT 
        COALESCE(profile_id, unknown_face_id) as person_id,
        location,
        activity,
        timestamp
    FROM activity_log
    WHERE timestamp > datetime('now', '-1 day')
    AND location IS NOT NULL
    AND activity != 'Unknown'
    ORDER BY person_id, location, timestamp DESC
"""

cursor.execute(query)
all_records = cursor.fetchall()

print(f"\nTotal records in last 24h: {len(all_records)}")

# Apply deduplication logic (same as API)
person_activities = {}
activity_counts = {}

for person_id, location, activity, timestamp in all_records:
    key = (person_id, location)
    # Only record first occurrence (most recent due to DESC sort)
    if key not in person_activities:
        person_activities[key] = activity
        
        if location not in activity_counts:
            activity_counts[location] = {}
        if activity not in activity_counts[location]:
            activity_counts[location][activity] = 0
        activity_counts[location][activity] += 1

print(f"Unique person-activity pairs: {len(person_activities)}")

print("\n" + "="*70)
print("DEDUPLICATION RESULTS:")
print("="*70)

for location, activities in activity_counts.items():
    total = sum(activities.values())
    print(f"\n📍 {location}: {total} unique people")
    for activity, count in sorted(activities.items(), key=lambda x: -x[1]):
        pct = (count / total * 100) if total > 0 else 0
        print(f"  {activity}: {count} ({pct:.1f}%)")

conn.close()
