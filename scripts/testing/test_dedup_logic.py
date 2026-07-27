#!/usr/bin/env python3
"""Direct test of the deduplication logic without API auth"""

import sqlite3
from datetime import datetime, timedelta

# Test the new Python-based deduplication logic
db_path = "/private/tmp/ChronoSenseWeb-clean/backend/profiles.db"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

print("=" * 70)
print("🧪 TESTING DEDUPLICATION LOGIC")
print("=" * 70)

# Check the raw data (only string-based unknown_face_ids from test data)
print("\n📊 Raw data in activity_log (test data unknown faces only):")
cursor.execute("""
    SELECT unknown_face_id,
           location,
           activity,
           timestamp
    FROM activity_log
    WHERE unknown_face_id LIKE 'unknown_face_id_%'
    AND location IS NOT NULL
    AND activity != 'Unknown'
    ORDER BY unknown_face_id, location, timestamp DESC
""")

all_records = cursor.fetchall()
print(f"Total records: {len(all_records)}")
for i, (unknown_id, location, activity, timestamp) in enumerate(all_records[:21]):
    print(f"  {i+1}. {unknown_id} @ {location}: {activity}")

# NOW apply the deduplication logic
print("\n🔍 Applying Python-based deduplication...")

# Track primary activity per person per location (most recent = first in sort order)
person_activities = {}  # {(unknown_face_id, location): activity}
activity_counts = {}    # {location: {activity: count}}

for unknown_id, location, activity, timestamp in all_records:
    key = (unknown_id, location)
    # Only record the first occurrence (most recent due to DESC sort)
    if key not in person_activities:
        person_activities[key] = activity
        
        # Track this person's activity count at this location
        if location not in activity_counts:
            activity_counts[location] = {}
        if activity not in activity_counts[location]:
            activity_counts[location][activity] = 0
        activity_counts[location][activity] += 1

print(f"\n✓ Unique person-activity pairs: {len(person_activities)}")
print(f"✓ Locations with activities: {list(activity_counts.keys())}")

# Print results
print("\n📈 RESULTS:")
for location, activities in activity_counts.items():
    print(f"\n{location}:")
    total = sum(activities.values())
    for activity, count in sorted(activities.items()):
        print(f"  {activity}: {count} people")
    print(f"  TOTAL: {total} unique people")
    
    if total == 7:
        print(f"  ✅ PASS: Correct count (7 people, not frame detections)")
    else:
        print(f"  ❌ FAIL: Expected 7 people, got {total}")

conn.close()
