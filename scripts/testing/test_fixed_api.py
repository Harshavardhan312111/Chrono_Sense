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

print("✓ Test user ready")

# Login
time.sleep(2)
print("\n🔐 Logging in...")
auth_response = requests.post(f"{BASE_URL}/api/auth/login", 
    json={"username": "testuser", "password": "test"},
    timeout=5
)

print(f"Login status: {auth_response.status_code}")
if auth_response.status_code == 200:
    data = auth_response.json()
    token = data.get("access_token")
    print(f"✓ Got token")
    
    # Now test activities endpoint
    time.sleep(1)
    print(f"\n📊 Calling /api/activities/by-location...")
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(f"{BASE_URL}/api/activities/by-location", headers=headers, timeout=10)
    
    print(f"✓ API status: {resp.status_code}")
    
    if resp.status_code == 200:
        activity_data = resp.json()
        
        # Verify the counts
        if "CP IP Camera - Chronosphere" in activity_data:
            location_data = activity_data["CP IP Camera - Chronosphere"]
            total = location_data.get("total_people", 0)
            activities = location_data.get("activities", {})
            
            print(f"\n✅ RESULT:")
            print(f"  Total people: {total}")
            print(f"  Activities: {activities}")
            print(f"\n  Full response:")
            print(json.dumps(activity_data, indent=2))
            
            if total == 7:
                print(f"\n✅✅✅ SUCCESS! Counting unique people correctly!")
            else:
                print(f"\n⚠️ Count: {total} (expected 7)")
        else:
            print("No CP IP Camera data")
            print(json.dumps(activity_data, indent=2))
    else:
        print(f"❌ Error: {resp.status_code}")
        print(f"Response: {resp.text}")
else:
    print(f"❌ Login failed: {auth_response.text}")
