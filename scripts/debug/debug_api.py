#!/usr/bin/env python3
"""
Debug script to test the activity API response
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

from server import app
from fastapi.testclient import TestClient
import json

client = TestClient(app)

print("=== Testing /api/activities/by-location without date (last 24h) ===")
response = client.get("/api/activities/by-location")
if response.status_code == 401:
    print("Requires authentication - this is expected in test mode")
    # Let's simulate the database query directly instead
    import sqlite3
    
    db_path = "backend/profiles.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    print("\n=== Direct database query simulation ===")
    
    # Get all activities from last 24 hours
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
    
    print(f"Activity query returned {len(results)} rows:")
    locations_dict = {}
    
    for location, activity, unique_people in results:
        if location not in locations_dict:
            locations_dict[location] = {'activities': {}}
        locations_dict[location]['activities'][activity] = unique_people
        print(f"  {location} | {activity}: {unique_people} unique people")
    
    # Calculate total unique people per location
    for location in locations_dict:
        query = """
            SELECT COUNT(DISTINCT name) FROM activity_log
            WHERE location = ? AND activity != 'Unknown' AND timestamp > datetime('now', '-1 day')
        """
        cursor.execute(query, (location,))
        unique_count = cursor.fetchone()[0]
        locations_dict[location]['total_detections'] = unique_count
        print(f"\nLocation '{location}':")
        print(f"  Activities: {locations_dict[location]['activities']}")
        print(f"  Total unique people (total_detections): {unique_count}")
    
    conn.close()
    
    # Now simulate frontend aggregation
    print("\n=== Frontend Aggregation ===")
    activity_counts = {}
    total_detections = 0
    
    for loc_name, loc_data in locations_dict.items():
        activities = loc_data.get('activities', {})
        total_detections += loc_data.get('total_detections', 0)
        print(f"Adding from {loc_name}: total_detections={loc_data.get('total_detections', 0)}")
        
        for activity, count in activities.items():
            activity_counts[activity] = activity_counts.get(activity, 0) + count
    
    print(f"\nFinal totals:")
    print(f"  totalDetections = {total_detections}")
    print(f"  activityCounts = {activity_counts}")
    
    print(f"\n=== Displayed on Dashboard ===")
    for activity, count in sorted(activity_counts.items(), key=lambda x: x[1], reverse=True):
        percentage = (count / total_detections * 100) if total_detections > 0 else 0
        print(f"  {activity}: {count} ({percentage:.1f}%)")
        
else:
    print(json.dumps(response.json(), indent=2))
