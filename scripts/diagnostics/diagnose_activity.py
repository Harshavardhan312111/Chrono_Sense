#!/usr/bin/env python3
"""
Diagnose activity detection pipeline
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

import cv2
import numpy as np
from lite_pose_detector import LitePoseDetector
from cctv_recognition import CCTVRecognitionEngine
from ai_engine import ChronoEngine
from database import ProfileDatabase
from attendance import AttendanceTracker

print("=" * 80)
print("ACTIVITY DETECTION PIPELINE DIAGNOSTICS")
print("=" * 80)
print()

# Step 1: Test LitePoseDetector directly
print("1. Testing LitePoseDetector...")
try:
    detector = LitePoseDetector()
    print("   ✓ LitePoseDetector initialized")
    
    # Check methods exist
    print(f"   ✓ Has update_student_count: {hasattr(detector, 'update_student_count')}")
    print(f"   ✓ Has detect_activity: {hasattr(detector, 'detect_activity')}")
    print(f"   ✓ Has detect_group_activities: {hasattr(detector, 'detect_group_activities')}")
    
    # Test on synthetic frame
    frame = np.full((480, 640, 3), (120, 120, 120), dtype=np.uint8)
    activity, conf = detector.detect_activity(frame, (300, 250, 100, 150))
    print(f"   ✓ Detects activity: {activity} (conf: {conf:.2f})")
except Exception as e:
    print(f"   ✗ Error: {e}")
    import traceback
    traceback.print_exc()

print()
print("2. Testing CCTV Recognition Engine...")
try:
    profile_db = ProfileDatabase()
    engine = ChronoEngine(recognition_threshold=0.30)
    attendance_tracker = AttendanceTracker(profile_db.db_path)
    cctv_engine = CCTVRecognitionEngine(
        db_path=profile_db.db_path,
        ai_engine=engine,
        attendance_tracker=attendance_tracker,
        profile_db=profile_db
    )
    
    print(f"   ✓ CCTV Engine initialized")
    print(f"   ✓ Activity detector loaded: {cctv_engine.activity_detector is not None}")
    print(f"   ✓ Activity detector type: {type(cctv_engine.activity_detector).__name__}")
    
    # Test if activity detector has the methods
    if cctv_engine.activity_detector:
        try:
            cctv_engine.activity_detector.update_student_count(2)
            print(f"   ✓ update_student_count() works")
        except Exception as e:
            print(f"   ✗ update_student_count() failed: {e}")
        
        try:
            result = cctv_engine.activity_detector.detect_group_activities([])
            print(f"   ✓ detect_group_activities() works")
        except Exception as e:
            print(f"   ✗ detect_group_activities() failed: {e}")
            
except Exception as e:
    print(f"   ✗ Error: {e}")
    import traceback
    traceback.print_exc()

print()
print("3. Checking activity_log table...")
try:
    import sqlite3
    conn = sqlite3.connect(profile_db.db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM activity_log")
    count = cursor.fetchone()[0]
    print(f"   ✓ activity_log has {count} records")
    
    if count > 0:
        cursor.execute("SELECT activity, COUNT(*) FROM activity_log GROUP BY activity")
        for act, ac in cursor.fetchall():
            print(f"     - {act}: {ac}")
    conn.close()
except Exception as e:
    print(f"   ✗ Error: {e}")

print()
print("=" * 80)
print("DIAGNOSIS COMPLETE")
print("=" * 80)
