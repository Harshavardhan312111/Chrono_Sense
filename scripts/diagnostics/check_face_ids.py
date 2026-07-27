#!/usr/bin/env python3

import sqlite3
from datetime import datetime, timedelta

db_path = "/private/tmp/ChronoSenseWeb-clean/backend/profiles.db"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Check unknown_face_id distribution
print("📊 Checking unknown_face_id assignment patterns...")
print("="*70)

cursor.execute("""
    SELECT unknown_face_id, COUNT(*) as frames 
    FROM activity_log
    WHERE location = 'CP IP Camera - Chronosphere'
    AND unknown_face_id IS NOT NULL
    AND timestamp > datetime('now', '-24 hours')
    GROUP BY unknown_face_id
    ORDER BY frames DESC
    LIMIT 20
""")

results = cursor.fetchall()
print(f"\nTop 20 unknown_face_id by frame count (out of {len(results)} unique IDs):")
for face_id, frames in results:
    print(f"  {face_id}: {frames} frames")

if len(results) > 0 and results[0][1] < 5:
    print("\n⚠️ PROBLEM DETECTED: Each face only appears 1-5 times!")
    print("   This means each frame is getting a NEW unknown_face_id")
    print("   The embedding-based matching is NOT working!")

# Check registered faces
print("\n" + "="*70)
print("Registered faces (profile_id):")
cursor.execute("""
    SELECT profile_id, COUNT(*) as frames 
    FROM activity_log
    WHERE location = 'CP IP Camera - Chronosphere'
    AND profile_id IS NOT NULL
    AND timestamp > datetime('now', '-24 hours')
    GROUP BY profile_id
    ORDER BY frames DESC
""")

for profile_id, frames in cursor.fetchall():
    print(f"  {profile_id}: {frames} frames")

conn.close()
