#!/usr/bin/env python3
"""Test script to see what /api/activities/by-location returns"""

import sqlite3
import json
from datetime import datetime

# Simulate the API endpoint
def get_activities_by_location(date=None):
    db_path = "backend/profiles.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    locations = {}
    
    # Query activity data by location
    if date:
        query = """
            SELECT location, activity, COUNT(DISTINCT name) as unique_people
            FROM activity_log
            WHERE DATE(timestamp) = ?
            AND location IS NOT NULL
            AND activity != 'Unknown'
            GROUP BY location, activity
            ORDER BY location, unique_people DESC
        """
        cursor.execute(query, (date,))
    else:
        query = """
            SELECT location, activity, COUNT(DISTINCT name) as unique_people
            FROM activity_log
            WHERE timestamp > datetime('now', '-1 day')
            AND location IS NOT NULL
            AND activity != 'Unknown'
            GROUP BY location, activity
            ORDER BY location, unique_people DESC
        """
        cursor.execute(query)
    
    results = cursor.fetchall()
    print(f"DEBUG: Results from activity query: {results}")
    
    # Populate locations with activity data
    for location, activity, unique_people in results:
        if location not in locations:
            locations[location] = {
                'activities': {},
                'total_people': 0,
                'total_detections': 0,
                'dominant_activity': None,
                'average_confidence': 0.0
            }
        
        locations[location]['activities'][activity] = unique_people
    
    # Calculate total UNIQUE people per location
    for location in locations:
        unique_query = """
            SELECT COUNT(DISTINCT name) as unique_count
            FROM activity_log
            WHERE location = ? AND activity != 'Unknown'
        """
        if date:
            unique_query += " AND DATE(timestamp) = ?"
            cursor.execute(unique_query, (location, date))
        else:
            unique_query += " AND timestamp > datetime('now', '-1 day')"
            cursor.execute(unique_query, (location,))
        
        unique_result = cursor.fetchone()
        unique_count = unique_result[0] if unique_result else 0
        print(f"DEBUG: Location={location}, unique_count={unique_count}")
        
        locations[location]['total_people'] = unique_count
        locations[location]['total_detections'] = unique_count
    
    conn.close()
    
    return {
        'date': date or 'last_24_hours',
        'locations': locations,
        'total_locations': len(locations)
    }

# Test it
response = get_activities_by_location('2024-04-06')
print("\n=== API RESPONSE ===")
print(json.dumps(response, indent=2))

# Now simulate what the frontend does
print("\n=== FRONTEND AGGREGATION ===")
locations = response['locations']
activityCounts = {}
totalDetections = 0

for locName, locData in locations.items():
    activities = locData.get('activities', {})
    total = locData.get('total_detections', 0)
    print(f"Location: {locName}")
    print(f"  Activities: {activities}")
    print(f"  total_detections: {total}")
    
    totalDetections += total
    
    for activity, count in activities.items():
        activityCounts[activity] = activityCounts.get(activity, 0) + count

print(f"\nFinal aggregation:")
print(f"activityCounts: {activityCounts}")
print(f"totalDetections: {totalDetections}")

print(f"\nDisplayed values:")
for activity, count in activityCounts.items():
    percentage = (count / totalDetections * 100) if totalDetections > 0 else 0
    print(f"  {activity}: count={count}, percentage={percentage:.1f}%")
