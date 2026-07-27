#!/usr/bin/env python3
import sqlite3
import json

db_path = 'backend/profiles.db'
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

locations = {}

# Query for 2026-04-06
query = """
    SELECT location, activity, COUNT(DISTINCT name) as unique_people
    FROM activity_log
    WHERE DATE(timestamp) = '2026-04-06'
    AND location IS NOT NULL
    AND activity != 'Unknown'
    GROUP BY location, activity
    ORDER BY location, unique_people DESC
"""
cursor.execute(query)
results = cursor.fetchall()
print('Activity query results:', results)

# Populate locations
for location, activity, unique_people in results:
    if location not in locations:
        locations[location] = {
            'activities': {},
            'total_detections': 0
        }
    locations[location]['activities'][activity] = unique_people

# Calculate total_detections per location
for location in locations:
    unique_query = """
        SELECT COUNT(DISTINCT name) FROM activity_log 
        WHERE location = ? AND activity != 'Unknown' AND DATE(timestamp) = '2026-04-06'
    """
    cursor.execute(unique_query, (location,))
    unique_count = cursor.fetchone()[0]
    print(f'{location}: unique_count={unique_count}')
    locations[location]['total_detections'] = unique_count

conn.close()

# Show what frontend would receive
print('\n=== API RESPONSE FORMAT ===')
print(json.dumps({'locations': locations}, indent=2))

# Simulate frontend aggregation
activityCounts = {}
totalDetections = 0

print('\n=== FRONTEND AGGREGATION ===')
for locName, locData in locations.items():
    activities = locData['activities']
    total = locData['total_detections']
    print(f'Location: {locName}')
    print(f'  total_detections: {total}')
    totalDetections += total
    for activity, count in activities.items():
        print(f'  {activity}: {count}')
        activityCounts[activity] = activityCounts.get(activity, 0) + count

print(f'\nTotals: totalDetections={totalDetections}')
for activity, count in sorted(activityCounts.items(), key=lambda x: x[1], reverse=True):
    pct = (count / totalDetections * 100) if totalDetections > 0 else 0
    print(f'  {activity}: {count} ({pct:.1f}%)')
