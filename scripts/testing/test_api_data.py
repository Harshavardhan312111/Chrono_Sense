#!/usr/bin/env python3
import sqlite3
import json

conn = sqlite3.connect('backend/profiles.db')
cursor = conn.cursor()

query = '''
    SELECT location, emotion, COUNT(*) as count
    FROM attendance_log
    WHERE emotion IS NOT NULL 
    AND location IS NOT NULL
    GROUP BY location, emotion
    ORDER BY location, count DESC
'''
cursor.execute(query)
results = cursor.fetchall()

locations = {}
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

print(json.dumps(locations, indent=2))
conn.close()
