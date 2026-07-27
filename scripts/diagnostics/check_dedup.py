#!/usr/bin/env python3

import sqlite3
from datetime import datetime, timedelta

db_path = "/private/tmp/ChronoSenseWeb-clean/backend/profiles.db"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Check total records
cursor.execute("SELECT COUNT(*) FROM activity_log")
total = cursor.fetchone()[0]
print(f"Total activity_log records: {total}")

# Check CP IP Camera records in last 24 hours
now = datetime.now()
day_ago = now - timedelta(days=1)

cursor.execute("""
    SELECT COUNT(*) FROM activity_log
    WHERE location = 'CP IP Camera - Chronosphere'
    AND timestamp > ?
""", (day_ago.isoformat(),))
cp_24h = cursor.fetchone()[0]
print(f"CP IP Camera (last 24h): {cp_24h} records")

# Check activities breakdown in raw frames
cursor.execute("""
    SELECT activity, COUNT(*) FROM activity_log
    WHERE location = 'CP IP Camera - Chronosphere'
    AND timestamp > ?
    GROUP BY activity
    ORDER BY COUNT(*) DESC
""", (day_ago.isoformat(),))

print("\n📊 RAW FRAME COUNT (last 24h, CP IP Camera):")
for activity, count in cursor.fetchall():
    print(f"  {activity}: {count} frames")

# Now test the deduplication logic
print("\n" + "="*70)
print("TESTING DEDUPLICATION LOGIC")
print("="*70)

cursor.execute("""
    SELECT 
        COALESCE(profile_id, unknown_face_id) as person_id,
        location,
        activity,
        timestamp
    FROM activity_log
    WHERE location = 'CP IP Camera - Chronosphere'
    AND timestamp > ?
    AND activity != 'Unknown'
    ORDER BY person_id, location, timestamp DESC
""", (day_ago.isoformat(),))

all_records = cursor.fetchall()
print(f"\nRecords to process: {len(all_records)}")

# Apply deduplication
person_activities = {}
activity_counts = {}

for person_id, location, activity, timestamp in all_records:
    key = (person_id, location)
    if key not in person_activities:
        person_activities[key] = activity
        
        if location not in activity_counts:
            activity_counts[location] = {}
        if activity not in activity_counts[location]:
            activity_counts[location][activity] = 0
        activity_counts[location][activity] += 1

print(f"\n✓ Unique person-activity pairs: {len(person_activities)}")
print(f"\n👥 ACTIVITY BREAKDOWN (DEDUPLICATED, unique people):")

for location, activities in activity_counts.items():
    total_people = sum(activities.values())
    for activity, count in sorted(activities.items(), key=lambda x: -x[1]):
        print(f"  {activity}: {count} people")
    print(f"  TOTAL: {total_people} unique people")

conn.close()
