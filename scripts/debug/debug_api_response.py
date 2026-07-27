#!/usr/bin/env python3

import requests
import json
import sqlite3
import hashlib
import time

BASE_URL = "http://localhost:8000"
db_path = "/private/tmp/ChronoSenseWeb-clean/backend/profiles.db"

# Create test user
password_hash = hashlib.sha256("test".encode()).hexdigest()
conn = sqlite3.connect(db_path)
cursor = conn.cursor()
cursor.execute("INSERT OR REPLACE INTO users (username, email, password_hash, role, first_name, last_name, is_active) VALUES (?, ?, ?, ?, ?, ?, ?)", 
    ("testuser", "test@test.com", password_hash, "admin", "Test", "User", 1))
conn.commit()
conn.close()

time.sleep(3)

# Login
print("🔐 Logging in...")
auth_response = requests.post(f"{BASE_URL}/api/auth/login", 
    json={"username": "testuser", "password": "test"},
    timeout=5
)

if auth_response.status_code != 200:
    print(f"❌ Login failed: {auth_response.text}")
    exit(1)

token = auth_response.json().get("access_token")
print(f"✓ Got token")

# Test API WITHOUT date filter (last 24 hours)
print(f"\n📊 Testing /api/activities/by-location (last 24 hours)...")
headers = {"Authorization": f"Bearer {token}"}
resp = requests.get(f"{BASE_URL}/api/activities/by-location", headers=headers, timeout=10)

if resp.status_code == 200:
    data = resp.json()
    print(f"\n📈 API Response for CP IP Camera - Chronosphere:")
    
    if "CP IP Camera - Chronosphere" in data['locations']:
        cp_data = data['locations']["CP IP Camera - Chronosphere"]
        print(f"  total_people: {cp_data.get('total_people')}")
        print(f"  activities: {cp_data.get('activities')}")
        print(f"  engagement_percentage: {cp_data.get('engagement_percentage')}")
        print(f"  Full response:")
        print(json.dumps(cp_data, indent=2))
    else:
        print(f"  No CP IP Camera data")
        print(f"  Available locations: {list(data['locations'].keys())}")
        
        # Show first location data as sample
        if data['locations']:
            first_location = list(data['locations'].keys())[0]
            print(f"\n  Sample data (first location: {first_location}):")
            print(json.dumps(data['locations'][first_location], indent=2))
else:
    print(f"❌ Error: {resp.status_code}")
    print(f"Response: {resp.text}")

# Also test with today's date
print(f"\n\n📊 Testing /api/activities/by-location with today's date...")
from datetime import datetime
today = datetime.now().strftime("%Y-%m-%d")
resp2 = requests.get(f"{BASE_URL}/api/activities/by-location?date={today}", headers=headers, timeout=10)

if resp2.status_code == 200:
    data2 = resp2.json()
    if "CP IP Camera - Chronosphere" in data2['locations']:
        cp_data2 = data2['locations']["CP IP Camera - Chronosphere"]
        print(f"  total_people: {cp_data2.get('total_people')}")
        print(f"  activities: {cp_data2.get('activities')}")
    else:
        print(f"  No CP IP Camera data for today")
