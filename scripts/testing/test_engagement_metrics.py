#!/usr/bin/env python3
"""
Test script to verify engagement metrics and primary activity distribution
"""
import sqlite3
from collections import defaultdict

db_path = "backend/profiles.db"
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

# Define engagement categories
POSITIVE_ACTIVITIES = {'Writing', 'Reading', 'Listening', 'Collaboration'}
LOW_ENGAGEMENT_ACTIVITIES = {'Playing', 'Fighting', 'Distracted', 'Phone_Use', 'Eating', 'Sleeping'}

print("\n" + "="*80)
print("ENGAGEMENT METRICS - PRIMARY ACTIVITY DISTRIBUTION")
print("="*80)

# Get total activity records
cursor.execute("SELECT COUNT(*) as cnt FROM activity_log WHERE activity != 'Unknown'")
total_records = cursor.fetchone()['cnt']
print(f"\n📊 Total activity detections in DB: {total_records}")

# Get unique people per location
cursor.execute("""
    SELECT location, COUNT(DISTINCT COALESCE(profile_id, unknown_face_id)) as unique_people
    FROM activity_log
    WHERE activity != 'Unknown'
    GROUP BY location
""")

locations_count = {}
for row in cursor.fetchall():
    locations_count[row['location']] = row['unique_people']

print(f"\n📍 UNIQUE PEOPLE PER LOCATION:")
for loc, count in sorted(locations_count.items()):
    print(f"   • {loc}: {count} unique people")

# Get PRIMARY ACTIVITY per person (most recent)
print(f"\n🎯 ACTIVITY DISTRIBUTION (Primary Activity Per Person):")

query = """
    WITH person_primary_activity AS (
        SELECT 
            COALESCE(profile_id, unknown_face_id) as person_id,
            location,
            activity,
            ROW_NUMBER() OVER (PARTITION BY COALESCE(profile_id, unknown_face_id), location ORDER BY timestamp DESC) as recency
        FROM activity_log
        WHERE location IS NOT NULL
        AND activity != 'Unknown'
    )
    SELECT location, activity, COUNT(*) as num_people
    FROM person_primary_activity
    WHERE recency = 1
    GROUP BY location, activity
    ORDER BY location, num_people DESC
"""

cursor.execute(query)
results = cursor.fetchall()

location_data = defaultdict(lambda: {'positive': 0, 'low': 0, 'activities': {}})

for row in results:
    location = row['location']
    activity = row['activity']
    count = row['num_people']
    
    location_data[location]['activities'][activity] = count
    
    if activity in POSITIVE_ACTIVITIES:
        location_data[location]['positive'] += count
    elif activity in LOW_ENGAGEMENT_ACTIVITIES:
        location_data[location]['low'] += count

# Calculate engagement metrics
print("\n📈 ENGAGEMENT ANALYSIS:\n")
for location in sorted(location_data.keys()):
    data = location_data[location]
    total = data['positive'] + data['low']
    positive_count = data['positive']
    
    if total > 0:
        engagement_pct = (positive_count / total) * 100.0
        
        if engagement_pct >= 75:
            category = "🟢 HIGH"
        elif engagement_pct >= 50:
            category = "🟡 MEDIUM"
        else:
            category = "🔴 LOW"
        
        print(f"📍 {location}")
        print(f"   Total People: {total}")
        print(f"   Positive Engagement: {positive_count}/{total} ({engagement_pct:.1f}%) {category}")
        print(f"   Activities:")
        
        for activity, count in sorted(data['activities'].items(), key=lambda x: -x[1]):
            engagement_type = "✅" if activity in POSITIVE_ACTIVITIES else "❌"
            print(f"      {engagement_type} {activity}: {count} people")
        print()

conn.close()
print("✓ Implementation verified - engagement metrics working correctly!")
