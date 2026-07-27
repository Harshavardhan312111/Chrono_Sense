#!/usr/bin/env python3

import requests
import json
import sqlite3
import time
from datetime import datetime, timedelta

BASE_URL = "http://localhost:8000"

# First, add some test data to the database
print("📝 Setting up test data...")
conn = sqlite3.connect("/private/tmp/ChronoSenseWeb-clean/backend/profiles.db")
cursor = conn.cursor()

# Clear old data
cursor.execute("DELETE FROM activity_log")
conn.commit()

# Add test activities for 7 people in CP IP Camera location
# Each person should have exactly one primary activity

locations = ["CP IP Camera - Chronosphere"]
activities = ["Writing", "Reading", "Writing", "Listening", "Reading", "Writing", "Collaboration"]
now = datetime.now()

for i, activity in enumerate(activities):
    person_id = f"unknown_face_id_{i}"
    person_name = f"Unknown Student {i}"
    # Add 3 detections per person (frames), but they should count as 1 person
    for frame_offset in range(3):
        timestamp = (now - timedelta(seconds=frame_offset)).isoformat()
        cursor.execute("""
            INSERT INTO activity_log 
            (unknown_face_id, name, location, activity, activity_confidence, emotion, emotion_confidence, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (person_id, person_name, locations[0], activity, 0.95, "Neutral", 0.8, timestamp))
        conn.commit()

# Print what we added
cursor.execute("SELECT COUNT(*) FROM activity_log")
total_records = cursor.fetchone()[0]
print(f"✓ Added {total_records} activity records (7 people × 3 frames each)")

# Check what's in DB
cursor.execute("""
    SELECT COALESCE(profile_id, unknown_face_id), activity, COUNT(*) 
    FROM activity_log 
    GROUP BY COALESCE(profile_id, unknown_face_id), activity
""")
print("\n📊 Database content by person:")
for person, activity, count in cursor.fetchall():
    print(f"  {person}: {activity} ({count} frames)")

conn.close()

# Now test the API
print("\n🔍 Testing API endpoint...")
time.sleep(2)

try:
    # Login first
    auth_response = requests.post(f"{BASE_URL}/api/auth/login", 
        json={"username": "testuser", "password": "test"},
        timeout=5
    )
    
    if auth_response.status_code == 200:
        token = auth_response.json().get("access_token")
        print(f"✓ Got auth token")
    else:
        print(f"⚠ Login failed (status {auth_response.status_code}), using default token")
        token = "test_token"
    
    # Call the activities endpoint
    headers = {"Authorization": f"Bearer {token}"}
    api_response = requests.get(f"{BASE_URL}/api/activities/by-location", 
        headers=headers,
        timeout=10
    )
    
    print(f"✓ API status: {api_response.status_code}")
    
    if api_response.status_code == 200:
        data = api_response.json()
        print(f"\n📈 API Response:")
        print(json.dumps(data, indent=2))
        
        # Verify counts
        print(f"\n✅ VERIFICATION:")
        if "CP IP Camera - Chronosphere" in data:
            location_data = data["CP IP Camera - Chronosphere"]
            total = location_data.get("total_people", 0)
            activities_dict = location_data.get("activities", {})
            
            print(f"  Total people reported: {total}")
            print(f"  Expected: 7")
            print(f"  Activities breakdown: {activities_dict}")
            
            # Count activities
            activity_sum = sum(activities_dict.values())
            print(f"  Sum of activities: {activity_sum}")
            
            if total == 7 and activity_sum == 7:
                print(f"\n✅ PASS: Correct counting (7 people, not frame counts)")
            else:
                print(f"\n❌ FAIL: Still counting frames? (got {total} people total, {activity_sum} sum of activities)")
    else:
        print(f"❌ API error: {api_response.text}")
        
except requests.exceptions.RequestException as e:
    print(f"❌ Request failed: {e}")
