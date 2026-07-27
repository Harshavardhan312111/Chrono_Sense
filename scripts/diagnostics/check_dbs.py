#!/usr/bin/env python3
"""Check all found profiles.db files"""
import sqlite3, os, time

paths = [
    '/Users/chiefaiofficer/ChronoSenseWeb/backend/profiles.db',
    '/Users/chiefaiofficer/ChronoSenseWeb/.git-rewrite/t/backend/profiles.db',
    '/private/tmp/ChronoSenseWeb-checkpoints/checkpoint-2026-04-03-working/backend/profiles.db',
    '/private/tmp/ChronoSenseWeb-clean/backend/profiles.db',
]

for path in paths:
    print(f'\n=== {path} ===')
    if not os.path.exists(path):
        print('  NOT FOUND')
        continue
    print(f'  modified: {time.ctime(os.path.getmtime(path))}')
    conn = sqlite3.connect(path)
    c = conn.cursor()
    for t in ['profiles', 'cctv_cameras', 'attendance_log', 'activity_log']:
        try:
            c.execute(f'SELECT COUNT(*) FROM {t}')
            cnt = c.fetchone()[0]
            print(f'  {t}: {cnt} rows')
            if t == 'profiles' and cnt > 0:
                c.execute('SELECT id, name FROM profiles')
                print(f'    names: {[r[1] for r in c.fetchall()]}')
            if t == 'cctv_cameras' and cnt > 0:
                c.execute('SELECT id, name, source FROM cctv_cameras')
                print(f'    cameras: {c.fetchall()}')
        except Exception as e:
            print(f'  {t}: table missing ({e})')
    conn.close()
