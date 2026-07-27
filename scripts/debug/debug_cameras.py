#!/usr/bin/env python3
import sqlite3

conn = sqlite3.connect('backend/profiles.db')
cursor = conn.cursor()

# Exactly replicate what the API does
cameras_query = 'SELECT DISTINCT name FROM cctv_cameras WHERE enabled = 1 ORDER BY name'
cursor.execute(cameras_query)
cameras = [row[0] for row in cursor.fetchall()]

print('=== ENABLED CAMERAS (from cctv_cameras) ===')
for cam in cameras:
    print(f'  - {cam}')
print()

# Now check what's in emotion data
query = '''
    SELECT DISTINCT location FROM attendance_log
    WHERE emotion IS NOT NULL 
    AND timestamp > datetime('now', '-1 day')
    AND location IS NOT NULL
    ORDER BY location
'''
cursor.execute(query)
locations_in_data = [row[0] for row in cursor.fetchall()]

print('=== LOCATIONS IN EMOTION DATA (last 24hrs) ===')
for loc in locations_in_data:
    print(f'  - {loc}')
print()

print('=== FINAL COMBINED LIST ===')
locations = {}
for camera_name in cameras:
    locations[camera_name] = {}

for location in locations_in_data:
    if location not in locations:
        locations[location] = {}

final_list = sorted(locations.keys())
for loc in final_list:
    print(f'  - {loc}')

conn.close()
