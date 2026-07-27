#!/usr/bin/env python3
"""Restore profiles, cameras, and attendance from checkpoint DB"""
import sqlite3, os, shutil

SRC = '/private/tmp/ChronoSenseWeb-checkpoints/checkpoint-2026-04-03-working/backend/profiles.db'
DST = '/private/tmp/ChronoSenseWeb-clean/backend/profiles.db'

# Backup current (empty) DB just in case
if os.path.exists(DST):
    shutil.copyfile(DST, DST + '.empty_bak')
    print(f'Backed up current DB to {DST}.empty_bak')

src = sqlite3.connect(SRC)
dst = sqlite3.connect(DST)
sc = src.cursor()
dc = dst.cursor()

# 1. Restore profiles (15 rows)
sc.execute('SELECT id, name, embedding, email, department, check_in_time, check_out_time, created_at, image_path FROM profiles')
profiles = sc.fetchall()
print(f'\nRestoring {len(profiles)} profiles...')
for p in profiles:
    try:
        dc.execute('INSERT OR REPLACE INTO profiles (id, name, embedding, email, department, check_in_time, check_out_time, created_at, image_path) VALUES (?,?,?,?,?,?,?,?,?)', p)
        print(f'  + {p[1]}')
    except Exception as e:
        print(f'  ERROR {p[1]}: {e}')

# 2. Restore cameras
sc.execute('SELECT name FROM sqlite_master WHERE name=?', ('cctv_cameras',))
if sc.fetchone():
    sc.execute('SELECT * FROM cctv_cameras')
    cameras = sc.fetchall()
    col_names = [d[0] for d in sc.description]
    print(f'\nRestoring {len(cameras)} cameras...')
    for cam in cameras:
        try:
            placeholders = ','.join(['?'] * len(cam))
            cols = ','.join(col_names)
            dc.execute(f'INSERT OR REPLACE INTO cctv_cameras ({cols}) VALUES ({placeholders})', cam)
            print(f'  + Camera {cam[1]}')
        except Exception as e:
            print(f'  ERROR camera {cam}: {e}')

# 3. Restore attendance_log
sc.execute('SELECT name FROM sqlite_master WHERE name=?', ('attendance_log',))
if sc.fetchone():
    # Get column names from source
    sc.execute('PRAGMA table_info(attendance_log)')
    src_cols = [r[1] for r in sc.fetchall()]
    # Get column names from destination
    dc.execute('PRAGMA table_info(attendance_log)')
    dst_cols = [r[1] for r in dc.fetchall()]
    # Use only columns that exist in both
    common_cols = [c for c in src_cols if c in dst_cols]
    cols_str = ','.join(common_cols)
    
    sc.execute(f'SELECT {cols_str} FROM attendance_log')
    rows = sc.fetchall()
    print(f'\nRestoring {len(rows)} attendance records (columns: {common_cols})...')
    placeholders = ','.join(['?'] * len(common_cols))
    inserted = 0
    for r in rows:
        try:
            dc.execute(f'INSERT OR REPLACE INTO attendance_log ({cols_str}) VALUES ({placeholders})', r)
            inserted += 1
        except Exception as e:
            if inserted < 3:
                print(f'  ERROR: {e}')
    print(f'  Inserted {inserted}/{len(rows)} attendance records')

dst.commit()
src.close()
dst.close()

# Verify
print('\n--- VERIFICATION ---')
conn = sqlite3.connect(DST)
c = conn.cursor()
for t in ['profiles', 'cctv_cameras', 'attendance_log']:
    c.execute(f'SELECT COUNT(*) FROM {t}')
    print(f'{t}: {c.fetchone()[0]} rows')
c.execute('SELECT id, name FROM profiles')
print(f'Profile names: {[r[1] for r in c.fetchall()]}')
c.execute('SELECT id, name FROM cctv_cameras')
print(f'Cameras: {c.fetchall()}')
conn.close()
print('\nDone!')
