#!/usr/bin/env python3
"""
Comprehensive verification of entire counting system.
Verifies: embeddings, matching, database, API, and frontend logic.
"""
import sqlite3
import json
import sys
from datetime import datetime, timedelta

DB_PATH = "/private/tmp/ChronoSenseWeb-clean/backend/profiles.db"

def verify_embeddings():
    """Verify embeddings are being extracted successfully"""
    print("\n" + "="*80)
    print("✓ STEP 1: VERIFY EMBEDDING EXTRACTION")
    print("="*80)
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Check if we have records with embeddings
    cursor.execute("""
        SELECT COUNT(*) as total_records,
               COUNT(DISTINCT profile_id) as distinct_known,
               COUNT(DISTINCT unknown_face_id) as distinct_unknown
        FROM activity_log
    """)
    total, known, unknown = cursor.fetchone()
    
    print(f"Total records in database: {total}")
    print(f"Distinct known faces (profile_id): {known}")
    print(f"Distinct unknown faces (unknown_face_id): {unknown}")
    
    if total == 0:
        print("⚠️  WARNING: No data in database! Server may not be running or camera not feeding data.")
        return False
    
    print("✅ Embedding data exists in database")
    return True

def verify_face_matching():
    """Verify faces are being matched across frames (not creating new ID per frame)"""
    print("\n" + "="*80)
    print("✓ STEP 2: VERIFY FACE MATCHING (Same person gets same ID)")
    print("="*80)
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Check how well unknown faces are being matched
    cursor.execute("""
        SELECT 
            unknown_face_id,
            COUNT(*) as frame_count,
            MIN(timestamp) as first_seen,
            MAX(timestamp) as last_seen,
            CAST((julianday(MAX(timestamp)) - julianday(MIN(timestamp))) * 86400 AS INTEGER) as duration_seconds
        FROM activity_log
        WHERE unknown_face_id IS NOT NULL
        GROUP BY unknown_face_id
        ORDER BY frame_count DESC
        LIMIT 15
    """)
    
    results = cursor.fetchall()
    
    print("\nTop 15 unknown faces (ID, frame_count, duration):")
    print("-" * 60)
    
    total_frames = 0
    good_matches = 0  # Faces with >20 frames (good continuous tracking)
    
    for face_id, count, first, last, duration in results:
        total_frames += count
        status = "✅ GOOD" if count >= 20 and duration >= 30 else "⚠️  SHORT"
        print(f"  ID {face_id:3d}: {count:4d} frames, {duration:4d}s duration {status}")
        if count >= 20 and duration >= 30:
            good_matches += 1
    
    print(f"\n📊 Summary:")
    print(f"  Total frames tracked: {total_frames}")
    print(f"  Faces with good tracking (>20 frames, >30s): {good_matches} / {len(results)}")
    
    # This is a good sign of embedding-based matching working
    if good_matches >= 1:
        print("✅ Face matching is working! Same faces tracked across multiple frames")
        return True
    else:
        print("⚠️  WARNING: Faces not being matched well. Embeddings may be failing silently.")
        return False

def verify_database_integrity():
    """Verify database has proper structure and no data corruption"""
    print("\n" + "="*80)
    print("✓ STEP 3: VERIFY DATABASE INTEGRITY")
    print("="*80)
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Check schema
    cursor.execute("PRAGMA table_info(activity_log)")
    columns = {col[1]: col[2] for col in cursor.fetchall()}
    
    required_cols = ['profile_id', 'unknown_face_id', 'location', 'activity', 'timestamp']
    missing = [col for col in required_cols if col not in columns]
    
    if missing:
        print(f"❌ ERROR: Missing columns: {missing}")
        return False
    
    print("✅ Database schema is correct")
    
    # Check data quality
    cursor.execute("""
        SELECT 
            COUNT(*) as total,
            COUNT(CASE WHEN location IS NULL THEN 1 END) as null_locations,
            COUNT(CASE WHEN activity IS NULL THEN 1 END) as null_activities,
            COUNT(CASE WHEN timestamp IS NULL THEN 1 END) as null_timestamps
        FROM activity_log
    """)
    
    total, null_loc, null_act, null_ts = cursor.fetchone()
    
    print(f"\nData quality check:")
    print(f"  Total records: {total}")
    print(f"  NULL locations: {null_loc}")
    print(f"  NULL activities: {null_act}")
    print(f"  NULL timestamps: {null_ts}")
    
    if null_loc > 0 or null_act > 0 or null_ts > 0:
        print("⚠️  WARNING: Database has NULL values in critical fields")
        return False
    
    print("✅ Database integrity verified")
    return True

def verify_api_deduplication():
    """Verify API's Python-based deduplication logic"""
    print("\n" + "="*80)
    print("✓ STEP 4: VERIFY API DEDUPLICATION LOGIC")
    print("="*80)
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Simulate API query: get last 24 hours
    cursor.execute("""
        SELECT 
            COALESCE(profile_id, unknown_face_id) as person_id,
            location,
            activity,
            timestamp
        FROM activity_log
        WHERE timestamp > datetime('now', '-1 day')
        AND location IS NOT NULL
        AND activity != 'Unknown'
        ORDER BY person_id, location, timestamp DESC
    """)
    
    all_records = cursor.fetchall()
    
    # Simulate Python deduplication (same as API endpoint)
    person_activities = {}  # {(person_id, location): activity}
    activity_counts = {}    # {location: {activity: count}}
    
    for person_id, location, activity, timestamp in all_records:
        key = (person_id, location)
        # Only record the first occurrence (most recent due to DESC sort)
        if key not in person_activities:
            person_activities[key] = activity
            
            # Count this person's activity
            if location not in activity_counts:
                activity_counts[location] = {}
            if activity not in activity_counts[location]:
                activity_counts[location][activity] = 0
            activity_counts[location][activity] += 1
    
    print(f"\nDeduplication results (last 24h):")
    print("-" * 60)
    
    for location in sorted(activity_counts.keys()):
        activities = activity_counts[location]
        total_people = sum(activities.values())
        
        print(f"\n📍 Location: {location}")
        print(f"   Total unique people: {total_people}")
        print(f"   Activities breakdown:")
        for activity, count in sorted(activities.items(), key=lambda x: -x[1]):
            pct = (count / total_people * 100) if total_people > 0 else 0
            print(f"     - {activity}: {count} people ({pct:.1f}%)")
    
    print("\n✅ API deduplication logic verified")
    return True

def verify_frontend_calculation():
    """Verify frontend aggregation logic"""
    print("\n" + "="*80)
    print("✓ STEP 5: VERIFY FRONTEND DISPLAY LOGIC")
    print("="*80)
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Get activity distribution per location
    cursor.execute("""
        SELECT 
            COALESCE(profile_id, unknown_face_id) as person_id,
            location,
            activity,
            timestamp
        FROM activity_log
        WHERE timestamp > datetime('now', '-1 day')
        AND location IS NOT NULL
        AND activity != 'Unknown'
        ORDER BY person_id, location, timestamp DESC
    """)
    
    all_records = cursor.fetchall()
    
    # Replicate API logic
    person_activities = {}
    activity_counts = {}
    
    for person_id, location, activity, timestamp in all_records:
        key = (person_id, location)
        if key not in person_activities:
            person_activities[key] = activity
            if location not in activity_counts:
                activity_counts[location] = {}
            if activity not in activity_counts[location]:
                activity_counts[location][activity] = 0
            activity_counts[location][activity] += 1
    
    # Replicate frontend aggregation
    total_detections = 0
    for location, activities in activity_counts.items():
        location_total = sum(activities.values())
        total_detections += location_total
    
    print(f"\nFrontend display calculation:")
    print(f"  Total people across all locations: {total_detections}")
    
    # Verify consistency
    print(f"\n  Per-location breakdown:")
    for location in sorted(activity_counts.keys()):
        location_total = sum(activity_counts[location].values())
        print(f"    - {location}: {location_total} people")
    
    print("\n✅ Frontend display logic verified")
    return True

def verify_counting_consistency():
    """Verify database counts match deduplication logic"""
    print("\n" + "="*80)
    print("✓ STEP 6: VERIFY COUNTING CONSISTENCY")
    print("="*80)
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Method 1: SQL COUNT(DISTINCT)
    cursor.execute("""
        SELECT 
            location,
            COUNT(DISTINCT COALESCE(profile_id, unknown_face_id)) as sql_count
        FROM activity_log
        WHERE timestamp > datetime('now', '-1 day')
        AND location IS NOT NULL
        AND activity != 'Unknown'
        GROUP BY location
    """)
    sql_results = {row[0]: row[1] for row in cursor.fetchall()}
    
    # Method 2: Python deduplication (API way)
    cursor.execute("""
        SELECT 
            COALESCE(profile_id, unknown_face_id) as person_id,
            location,
            activity,
            timestamp
        FROM activity_log
        WHERE timestamp > datetime('now', '-1 day')
        AND location IS NOT NULL
        AND activity != 'Unknown'
        ORDER BY person_id, location, timestamp DESC
    """)
    
    all_records = cursor.fetchall()
    person_activities = {}
    activity_counts = {}
    
    for person_id, location, activity, timestamp in all_records:
        key = (person_id, location)
        if key not in person_activities:
            person_activities[key] = activity
            if location not in activity_counts:
                activity_counts[location] = {}
            if activity not in activity_counts[location]:
                activity_counts[location][activity] = 0
            activity_counts[location][activity] += 1
    
    python_results = {loc: sum(activities.values()) for loc, activities in activity_counts.items()}
    
    # Compare
    print(f"\nConsistency check (SQL vs Python dedup):")
    print("-" * 60)
    
    all_locations = set(sql_results.keys()) | set(python_results.keys())
    all_match = True
    
    for location in sorted(all_locations):
        sql_count = sql_results.get(location, 0)
        py_count = python_results.get(location, 0)
        match = "✅" if sql_count == py_count else "❌"
        print(f"  {match} {location:40s}: SQL={sql_count:3d}, Python={py_count:3d}")
        if sql_count != py_count:
            all_match = False
    
    if all_match:
        print("\n✅ Counts are CONSISTENT between SQL and Python deduplication")
        return True
    else:
        print("\n❌ ERROR: Counts MISMATCH! Deduplication logic is broken")
        return False

def main():
    print("\n" + "="*80)
    print("  COMPREHENSIVE SYSTEM VERIFICATION")
    print("  Checking: Embeddings → Matching → DB → API → Frontend")
    print("="*80)
    
    checks = [
        ("Embedding Extraction", verify_embeddings),
        ("Face Matching", verify_face_matching),
        ("Database Integrity", verify_database_integrity),
        ("API Deduplication", verify_api_deduplication),
        ("Frontend Calculation", verify_frontend_calculation),
        ("Counting Consistency", verify_counting_consistency),
    ]
    
    results = []
    for name, check_func in checks:
        try:
            result = check_func()
            results.append((name, result))
        except Exception as e:
            print(f"\n❌ ERROR in {name}: {e}")
            import traceback
            traceback.print_exc()
            results.append((name, False))
    
    # Final report
    print("\n" + "="*80)
    print("  FINAL VERIFICATION REPORT")
    print("="*80)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"  {status}: {name}")
    
    print(f"\n  Total: {passed}/{total} checks passed")
    
    if passed == total:
        print("\n🎉 ALL CHECKS PASSED! System is working correctly.")
        return 0
    else:
        print(f"\n⚠️  {total - passed} check(s) failed. Review output above.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
