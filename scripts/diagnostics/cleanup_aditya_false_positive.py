#!/usr/bin/env python3
"""Clean up false positive Aditya Mewati detections from database"""

import sqlite3

db_path = "/private/tmp/ChronoSenseWeb-clean/backend/profiles.db"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

print("\n" + "="*80)
print("ADITYA MEWATI FALSE POSITIVE CLEANUP")
print("="*80 + "\n")

# Show records before deletion
print("RECORDS ON 2026-04-04:")
print("-"*80)
cursor.execute('''
    SELECT id, timestamp, confidence, emotion 
    FROM attendance_log 
    WHERE name LIKE '%Aditya%' AND DATE(timestamp) = '2026-04-04'
    ORDER BY timestamp ASC
''')

records = cursor.fetchall()
print(f"Found {len(records)} record(s)\n")

if records:
    for rid, ts, conf, emotion in records:
        status = "❌ BORDERLINE (delete)" if conf < 0.36 else "✅ VALID (keep)"
        print(f"  ID {rid}: {ts} | Conf: {conf:.4f} | {status}")
    
    # Delete borderline records
    print("\n" + "="*80)
    print("DELETING BORDERLINE RECORDS (confidence < 0.36)...")
    print("="*80 + "\n")
    
    cursor.execute('''
        DELETE FROM attendance_log
        WHERE name LIKE '%Aditya%' 
        AND DATE(timestamp) = '2026-04-04' 
        AND confidence < 0.36
    ''')
    
    deleted_count = cursor.rowcount
    conn.commit()
    
    print(f"✅ DELETED: {deleted_count} false positive record(s)\n")
    
    # Show remaining records
    print("-"*80)
    cursor.execute('''
        SELECT id, timestamp, confidence, emotion 
        FROM attendance_log 
        WHERE name LIKE '%Aditya%' AND DATE(timestamp) = '2026-04-04'
        ORDER BY timestamp ASC
    ''')
    
    remaining = cursor.fetchall()
    print(f"REMAINING RECORDS: {len(remaining)}\n")
    
    if remaining:
        for rid, ts, conf, emotion in remaining:
            print(f"  ID {rid}: {ts} | Conf: {conf:.4f} | ✅ VALID | {emotion}")
    else:
        print("  (none - all false positives removed)")
    
    print("\n" + "="*80)
    print(f"SUMMARY: Deleted {deleted_count} false positives, {len(remaining)} valid records remain")
    print("="*80 + "\n")
else:
    print("No records found\n")

conn.close()
