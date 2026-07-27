#!/usr/bin/env python3
"""
Investigation script for Aditya Mewati false positive detection
Date: 2026-04-04 (incident at ~8:54)
"""
import sqlite3
import json
from datetime import datetime, timedelta
from pathlib import Path

DB_PATH = "/private/tmp/ChronoSenseWeb-clean/backend/profiles.db"

def investigate():
    """Run investigation queries"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    print("\n" + "="*80)
    print("INVESTIGATION: Aditya Mewati False Positive - 2026-04-04 ~8:54")
    print("="*80 + "\n")
    
    # Query 1: All Aditya detections on 2026-04-04
    print("1️⃣  ALL ADITYA DETECTIONS ON 2026-04-04")
    print("-" * 80)
    cursor.execute('''
        SELECT id, timestamp, confidence, emotion, frame_path, status, location
        FROM attendance_log
        WHERE DATE(timestamp) = '2026-04-04' 
          AND name LIKE '%Aditya%'
        ORDER BY timestamp ASC
    ''')
    
    aditya_records = cursor.fetchall()
    if not aditya_records:
        print("❌ No Aditya records found on 2026-04-04")
    else:
        print(f"Found {len(aditya_records)} detection(s):\n")
        for idx, (rid, ts, conf, emotion, frame, status, location) in enumerate(aditya_records, 1):
            frame_status = "✅ SAVED" if frame else "❌ NULL (MISSING)"
            print(f"  [{idx}] Time: {ts}")
            print(f"      Confidence: {conf if conf else 'N/A'}")
            print(f"      Emotion: {emotion or 'N/A'}")
            print(f"      Frame: {frame_status}")
            if frame:
                print(f"      Path: {frame}")
            print(f"      Status: {status}")
            print(f"      Location: {location or 'N/A'}")
            print()
    
    # Query 2: Look for potential false positive around 8:54
    print("2️⃣  POTENTIAL FALSE POSITIVE (~8:54 window)")
    print("-" * 80)
    cursor.execute('''
        SELECT id, name, timestamp, confidence, frame_path, emotion, status
        FROM attendance_log
        WHERE DATE(timestamp) = '2026-04-04'
          AND TIME(timestamp) BETWEEN '08:50:00' AND '09:00:00'
        ORDER BY timestamp ASC
    ''')
    
    records_in_window = cursor.fetchall()
    print(f"Detections in 8:50-9:00 window: {len(records_in_window)}\n")
    for rid, name, ts, conf, frame, emotion, status in records_in_window:
        frame_status = "✅ SAVED" if frame else "❌ MISSING"
        print(f"  {ts} | {name:20} | Conf: {conf:6} | Frame: {frame_status} | {emotion}")
    
    # Query 3: Confidence analysis (looking for borderline matches)
    print("\n3️⃣  ADITYA CONFIDENCE ANALYSIS (Borderline Matches ≤ 0.40)")
    print("-" * 80)
    cursor.execute('''
        SELECT timestamp, confidence, emotion, frame_path, status
        FROM attendance_log
        WHERE DATE(timestamp) = '2026-04-04'
          AND name LIKE '%Aditya%'
          AND (confidence <= 0.40 OR confidence IS NULL)
        ORDER BY timestamp ASC
    ''')
    
    borderline = cursor.fetchall()
    if borderline:
        print(f"⚠️  FOUND {len(borderline)} BORDERLINE MATCH(ES):\n")
        for ts, conf, emotion, frame, status in borderline:
            print(f"  {ts} | Confidence: {conf} | Frame: {'✅' if frame else '❌'}")
    else:
        print("✅ No borderline matches found (all Aditya detections have confidence > 0.40)")
    
    # Query 4: Frame capture failures (NULL frame_path for Aditya)
    print("\n4️⃣  FRAME CAPTURE FAILURES (NULL frame_path)")
    print("-" * 80)
    cursor.execute('''
        SELECT COUNT(*), COUNT(CASE WHEN frame_path IS NULL THEN 1 END) as null_frames
        FROM attendance_log
        WHERE DATE(timestamp) = '2026-04-04'
          AND name LIKE '%Aditya%'
    ''')
    
    total, null_count = cursor.fetchone()
    print(f"Total Aditya detections: {total}")
    print(f"Missing frames (NULL): {null_count}")
    if null_count and null_count > 0:
        print(f"⚠️  CRITICAL: {null_count} detection(s) without frame capture!")
        print("\n   Detailed NULL frame records:")
        cursor.execute('''
            SELECT id, timestamp, confidence, emotion
            FROM attendance_log
            WHERE DATE(timestamp) = '2026-04-04'
              AND name LIKE '%Aditya%'
              AND frame_path IS NULL
            ORDER BY timestamp ASC
        ''')
        for rid, ts, conf, emotion in cursor.fetchall():
            print(f"   - {ts} | Confidence: {conf} | Emotion: {emotion}")
    
    # Query 5: Surrounding detections (other people detected nearby in time)
    print("\n5️⃣  SURROUNDING DETECTIONS (Same time window)")
    print("-" * 80)
    cursor.execute('''
        SELECT DISTINCT name, COUNT(*) as count, 
               GROUP_CONCAT(DISTINCT emotion) as emotions,
               COUNT(CASE WHEN frame_path IS NOT NULL THEN 1 END) as frames_saved
        FROM attendance_log
        WHERE DATE(timestamp) = '2026-04-04'
          AND TIME(timestamp) BETWEEN '08:45:00' AND '09:05:00'
          AND name NOT LIKE '%Aditya%'
        GROUP BY name
        ORDER BY count DESC
    ''')
    
    others = cursor.fetchall()
    print(f"Other people detected in 8:45-9:05 window:\n")
    for name, count, emotions, frames in others:
        print(f"  {name:20} | Detections: {count:2} | Frames: {frames:2} | Emotions: {emotions}")
    
    # Query 6: Root cause assessment
    print("\n6️⃣  ROOT CAUSE ASSESSMENT")
    print("-" * 80)
    
    cursor.execute('''
        SELECT COUNT(*)
        FROM attendance_log
        WHERE DATE(timestamp) = '2026-04-04'
          AND name LIKE '%Aditya%'
          AND frame_path IS NULL
    ''')
    null_frames_aditya = cursor.fetchone()[0]
    
    cursor.execute('''
        SELECT COUNT(*)
        FROM attendance_log
        WHERE DATE(timestamp) = '2026-04-04'
          AND name LIKE '%Aditya%'
          AND confidence <= 0.40
    ''')
    borderline_aditya = cursor.fetchone()[0]
    
    print("Root Cause Analysis:\n")
    
    if null_frames_aditya > 0:
        print(f"❌ FRAME CAPTURE FAILURE: {null_frames_aditya} detection(s) without frame")
        print("   → Hypothesis A: Frame saving function failed (_save_face_snapshot failed)")
        print("   → No validation: System logged attendance despite missing frame")
        print("   → Remediation: Mandatory frame validation before log_detection()")
    
    if borderline_aditya > 0:
        print(f"\n⚠️  BORDERLINE MATCHES: {borderline_aditya} detection(s) with confidence ≤ 0.40")
        print("   → Hypothesis B: Recognition threshold too permissive")
        print("   → Threshold 0.32 may match unrelated faces in crowded staff room")
        print("   → Remediation: Raise threshold to 0.35 OR stricter gap (0.05 → 0.10)")
    
    if null_frames_aditya == 0 and borderline_aditya == 0:
        print("✅ NO ISSUES FOUND: All Aditya detections have frames + confidence > 0.40")
        print("   → Possible explanation: Similar person detected (not Aditya)")
        print("   → Or: Embedding collision in staff room environment")
        print("   → Remediation: Review face validation dashboard for 8:54 frame")
    
    print("\n" + "="*80 + "\n")
    conn.close()

if __name__ == "__main__":
    investigate()
