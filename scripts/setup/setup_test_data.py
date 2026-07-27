#!/usr/bin/env python3

import sqlite3
from datetime import datetime, timedelta

db_path = "/private/tmp/ChronoSenseWeb-clean/backend/profiles.db"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Clear all activity data
cursor.execute("DELETE FROM activity_log")
cursor.execute("DELETE FROM activity_summary")
conn.commit()

print("✓ Database cleared")

# Add test data - 7 people, 3 frames each
locations = ["CP IP Camera - Chronosphere"]
activities = ["Writing", "Reading", "Writing", "Listening", "Reading", "Writing", "Collaboration"]
now = datetime.now()

for i, activity in enumerate(activities):
    person_id = f"unknown_face_id_{i}"
    person_name = f"Unknown Student {i}"
    # Add 3 frames per person (all same activity for simplicity)
    for frame_offset in range(3):
        timestamp = (now - timedelta(seconds=frame_offset * 10)).isoformat()
        cursor.execute("""
            INSERT INTO activity_log 
            (unknown_face_id, name, location, activity, activity_confidence, emotion, emotion_confidence, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (person_id, person_name, locations[0], activity, 0.95, "Neutral", 0.8, timestamp))

conn.commit()
print(f"✓ Added 21 test records (7 people × 3 frames)")

# Verify
cursor.execute("SELECT COUNT(*) FROM activity_log")
count = cursor.fetchone()[0]
print(f"✓ Total records: {count}")

conn.close()
