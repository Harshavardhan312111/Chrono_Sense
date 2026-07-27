#!/usr/bin/env python3
import sqlite3
import json

conn = sqlite3.connect('backend/profiles.db')
cursor = conn.cursor()

# First, get all enabled cameras
cameras_query = "SELECT DISTINCT name FROM cctv_cameras WHERE enabled = 1"
cursor.execute(cameras_query)
cameras = [row[0] for row in cursor.fetchall()]

# Initialize all cameras with empty data
locations = {}
for camera_name in cameras:
    locations[camera_name] = {
        'emotions': {},
        'total_detections': 0,
        'dominant_emotion': None
    }

# Get emotion data for last 24 hours
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

# Find dominant emotion for each location
for location in locations:
    emotions = locations[location]['emotions']
    if emotions:
        dominant = max(emotions.items(), key=lambda x: x[1])
        locations[location]['dominant_emotion'] = dominant[0]

print(json.dumps({'locations': locations}, indent=2))
conn.close()
