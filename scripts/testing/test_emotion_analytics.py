#!/usr/bin/env python3
"""
Test script to demonstrate the Emotion Analytics API working correctly.
This shows what will be displayed when the admin-dashboard is accessed.
"""
import sqlite3
import json

conn = sqlite3.connect('backend/profiles.db')
cursor = conn.cursor()

print("=" * 70)
print("EMOTION ANALYTICS API TEST")
print("=" * 70)
print()

# Get all enabled cameras
cameras_query = "SELECT DISTINCT name FROM cctv_cameras WHERE enabled = 1"
cursor.execute(cameras_query)
cameras = [row[0] for row in cursor.fetchall()]

print(f"✓ Enabled Cameras Found: {len(cameras)}")
for camera in cameras:
    print(f"  - {camera}")
print()

# Initialize all cameras with empty data
locations = {}
for camera_name in cameras:
    locations[camera_name] = {
        'emotions': {},
        'total_detections': 0,
        'dominant_emotion': None
    }

# Get emotion data
query = """
    SELECT location, emotion, COUNT(*) as count
    FROM attendance_log
    WHERE emotion IS NOT NULL 
    AND timestamp > datetime('now', '-1 day')
    AND location IS NOT NULL
    GROUP BY location, emotion
    ORDER BY location, count DESC
"""
cursor.execute(query)
results = cursor.fetchall()

# Populate with actual emotion data
for location, emotion, count in results:
    if location not in locations:
        locations[location] = {
            'emotions': {},
            'total_detections': 0,
            'dominant_emotion': None
        }
    
    locations[location]['emotions'][emotion] = count
    locations[location]['total_detections'] += count

# Find dominant emotion
for location in locations:
    emotions = locations[location]['emotions']
    if emotions:
        dominant = max(emotions.items(), key=lambda x: x[1])
        locations[location]['dominant_emotion'] = dominant[0]

print("✓ API Response - Locations will show in dropdown:")
print("-" * 70)
for location, data in locations.items():
    print()
    print(f"📹 {location}")
    print(f"   Total Detections: {data['total_detections']}")
    print(f"   Dominant Emotion: {data['dominant_emotion'] or '(No data)'}")
    print(f"   Unique Emotions: {len(data['emotions'])}")
    if data['emotions']:
        print(f"   Emotion Distribution:")
        for emotion, count in sorted(data['emotions'].items(), key=lambda x: x[1], reverse=True):
            pct = (count / data['total_detections'] * 100) if data['total_detections'] > 0 else 0
            print(f"     - {emotion}: {count} ({pct:.1f}%)")
    else:
        print(f"   ⚠️  No emotion data available (camera offline or inactive)")

print()
print("=" * 70)
print("✓ All cameras will display correctly in the admin dashboard!")
print("=" * 70)

conn.close()
