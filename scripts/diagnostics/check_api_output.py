#!/usr/bin/env python3
import requests
import json
import sqlite3
import hashlib
import time

BASE_URL = "http://localhost:8000"
db_path = "/private/tmp/ChronoSenseWeb-clean/backend/profiles.db"

# Create/update test user
password_hash = hashlib.sha256("test".encode()).hexdigest()
conn = sqlite3.connect(db_path)
cursor = conn.cursor()
cursor.execute("INSERT OR REPLACE INTO users (username, email, password_hash, role, first_name, last_name, is_active) VALUES (?, ?, ?, ?, ?, ?, ?)", 
    ("testuser", "test@test.com", password_hash, "admin", "Test", "User", 1))
conn.commit()
conn.close()

time.sleep(1)

# Login
print("🔐 Logging in...")
auth = requests.post(f"{BASE_URL}/api/auth/login", json={"username": "testuser", "password": "test"})
if auth.status_code != 200:
    print(f"Login failed: {auth.text}")
    exit(1)

token = auth.json().get("access_token", "")
print(f"✓ Got token")

# Get API response
print("\n📡 Querying /api/activities/by-location...")
headers = {"Authorization": f"Bearer {token}"}
resp = requests.get(f"{BASE_URL}/api/activities/by-location", headers=headers)

if resp.status_code == 200:
    data = resp.json()
    print("\n" + "="*70)
    print("API RESPONSE:")
    print("="*70)
    for location, loc_data in data.get('locations', {}).items():
        print(f"\n📍 {location}")
        print(f"  total_people: {loc_data.get('total_people')}")
        activities = loc_data.get('activities', {})
        print(f"  activities: {activities}")
        sum_of_activities = sum(activities.values())
        print(f"  Sum of activities: {sum_of_activities}")
        
        if sum_of_activities != loc_data.get('total_people'):
            print(f"  ⚠️ MISMATCH: total_people ({loc_data.get('total_people')}) != sum ({sum_of_activities})")
else:
    print(f"Error: {resp.status_code}")
    print(resp.text[:500])
