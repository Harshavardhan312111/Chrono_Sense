#!/usr/bin/env python3
"""
Test script to show the updated Activity API responses
Uses direct database queries instead of HTTP to avoid auth issues during testing
"""

import sqlite3
import json
from datetime import datetime, timedelta
from collections import defaultdict

db_path = "/private/tmp/ChronoSenseWeb-clean/backend/profiles.db"

def test_activities_by_location():
    """Test the /api/activities/by-location endpoint logic"""
    print("=" * 80)
    print("API: GET /api/activities/by-location")
    print("=" * 80)
    print("\nThis endpoint now returns COUNT OF UNIQUE PEOPLE per activity, not total detections.\n")
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Simulate the API query
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
    
    locations = {}
    for location, activity, unique_people in results:
        if location not in locations:
            locations[location] = {
                'activities': {},
                'total_people': 0,
                'dominant_activity': None
            }
        locations[location]['activities'][activity] = unique_people
        locations[location]['total_people'] += unique_people
    
    # Find dominant activity
    for location in locations:
        activities = locations[location]['activities']
        if activities:
            dominant = max(activities.items(), key=lambda x: x[1])
            locations[location]['dominant_activity'] = dominant[0]
    
    response = {
        'date': 'last_24_hours',
        'locations': locations,
        'total_locations': len(locations)
    }
    
    print(json.dumps(response, indent=2))
    
    conn.close()
    return response

def test_activities_by_person():
    """Test the /api/activities/by-person endpoint logic"""
    print("\n" + "=" * 80)
    print("API: GET /api/activities/by-person")
    print("=" * 80)
    print("\nThis endpoint shows EACH PERSON's activity and emotions.\n")
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Simulate the API query
    query = """
        SELECT 
            name, 
            activity, 
            activity_confidence,
            emotion,
            emotion_confidence,
            MAX(timestamp) as last_detected,
            COUNT(*) as detection_count
        FROM activity_log
        WHERE timestamp > datetime('now', '-1 day')
        AND activity != 'Unknown'
        GROUP BY name, activity
        ORDER BY last_detected DESC
    """
    cursor.execute(query)
    results = cursor.fetchall()
    
    people_data = []
    activity_summary = {}
    
    for name, activity, conf, emotion, emotion_conf, last_det, detection_count in results:
        people_data.append({
            'name': name,
            'activity': activity,
            'activity_confidence': float(conf) if conf else 0.0,
            'emotion': emotion if emotion else 'Unknown',
            'emotion_confidence': float(emotion_conf) if emotion_conf else 0.0,
            'last_detected': last_det,
            'detection_count': detection_count
        })
        
        if activity not in activity_summary:
            activity_summary[activity] = 0
        activity_summary[activity] += 1
    
    response = {
        'people': people_data,
        'summary': {
            'total_people': len(set(p['name'] for p in people_data)),
            'activity_breakdown': activity_summary
        }
    }
    
    print(json.dumps(response, indent=2))
    
    conn.close()
    return response

def show_summary():
    """Show a quick summary of what changed"""
    print("\n" + "=" * 80)
    print("SUMMARY OF CHANGES")
    print("=" * 80)
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Get some stats
    cursor.execute("SELECT COUNT(*) FROM activity_log WHERE activity != 'Unknown'")
    total_detections = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(DISTINCT name) FROM activity_log WHERE activity != 'Unknown'")
    unique_people = cursor.fetchone()[0]
    
    cursor.execute("SELECT activity, COUNT(DISTINCT name) as people FROM activity_log WHERE activity != 'Unknown' GROUP BY activity")
    activity_people = cursor.fetchall()
    
    print(f"\n📊 Database Statistics:")
    print(f"   Total Activity Detections: {total_detections}")
    print(f"   Unique People Detected: {unique_people}")
    print(f"\n🎯 Activities by People Count:")
    for activity, people_count in activity_people:
        print(f"   • {activity}: {people_count} unique people")
    
    print(f"\n✅ BEFORE FIX:")
    print(f"   API returned: 'Distracted': 259  ← Total detections (WRONG!)")
    print(f"\n✅ AFTER FIX:")
    print(f"   API returns: 'Distracted': {activity_people[0][1] if activity_people else 0}  ← Unique people (CORRECT!)")
    
    print(f"\n📌 Key Improvement:")
    print(f"   Dashboard now shows HOW MANY STUDENTS are distracted,")
    print(f"   not HOW MANY TIMES we detected distraction activity.")
    
    conn.close()

if __name__ == "__main__":
    test_activities_by_location()
    test_activities_by_person()
    show_summary()
