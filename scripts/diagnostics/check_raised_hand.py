#!/usr/bin/env python3
"""
Check if Raised_Hand detections are real or false positives
"""
import sqlite3
from datetime import datetime

db_path = 'backend/profiles.db'
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

print("=" * 90)
print("RAISED_HAND DETECTION ANALYSIS")
print("=" * 90)

# Get all Raised_Hand records with detailed info
cursor.execute("""
SELECT 
    timestamp,
    location,
    activity,
    activity_confidence,
    emotion
FROM activity_log
WHERE activity = 'Raised_Hand'
ORDER BY timestamp DESC
LIMIT 50
""")

raised_hand_records = cursor.fetchall()
print(f"\nTotal Raised_Hand records: {len(raised_hand_records)}")
print("\nDetails of each Raised_Hand detection:")
print("-" * 90)
print(f"{'Timestamp':<25} | {'Location':<30} | {'Confidence':<12} | {'Emotion'}")
print("-" * 90)

raised_hand_by_time = {}
for ts, location, activity, confidence, emotion in raised_hand_records:
    print(f"{ts:<25} | {location:<30} | {confidence:<12.2f} | {emotion}")
    
    # Group by timestamp (to second) to see if multiple hands raised at same moment
    ts_key = ts[:19]  # YYYY-MM-DD HH:MM:SS
    if ts_key not in raised_hand_by_time:
        raised_hand_by_time[ts_key] = []
    raised_hand_by_time[ts_key].append({
        'location': location,
        'confidence': confidence,
        'emotion': emotion
    })

print("\n" + "=" * 90)
print("SIMULTANEOUS RAISED_HAND DETECTIONS (same second)")
print("=" * 90)

for ts, records in sorted(raised_hand_by_time.items()):
    if len(records) > 1:
        print(f"\n{ts}: {len(records)} hands raised at the SAME TIME")
        for i, rec in enumerate(records, 1):
            print(f"  {i}. {rec['location']} (confidence: {rec['confidence']:.2f}, emotion: {rec['emotion']})")

# Compare to other activities by location
print("\n" + "=" * 90)
print("ACTIVITY DISTRIBUTION BY LOCATION")
print("=" * 90)

cursor.execute("""
SELECT 
    location,
    activity,
    COUNT(*) as count,
    AVG(activity_confidence) as avg_confidence
FROM activity_log
GROUP BY location, activity
ORDER BY location, count DESC
""")

results = cursor.fetchall()
current_location = None
for location, activity, count, avg_conf in results:
    if location != current_location:
        print(f"\n{location}:")
        current_location = location
    print(f"  {activity:<20} | {count:4} records | avg confidence: {avg_conf:.2f}")

print("\n" + "=" * 90)
print("CONCLUSION")
print("=" * 90)

# Count students per location
cursor.execute("""
SELECT location FROM activity_log GROUP BY location
""")
locations = cursor.fetchall()

for location, in locations:
    cursor.execute("""
    SELECT COUNT(DISTINCT ROW_NUMBER() OVER (ORDER BY timestamp))
    FROM (
        SELECT DISTINCT timestamp, activity FROM activity_log WHERE location = ?
    )
    """, (location,))
    
    cursor.execute("""
    SELECT COUNT(*) FROM activity_log WHERE location = ? AND activity = 'Raised_Hand'
    """, (location,))
    
    raised_count = cursor.fetchone()[0]
    
    if raised_count > 5:
        print(f"\n⚠️  {location}: {raised_count} Raised_Hand detections")
        print(f"   Likelihood of {raised_count} students having hands raised at once: VERY LOW")
        print(f"   Probable cause: False positives from hand detection")
    else:
        print(f"\n✓ {location}: {raised_count} Raised_Hand detections (acceptable)")

conn.close()
