import requests, sqlite3

base = 'http://localhost:8000'
r = requests.post(f'{base}/api/auth/login', json={'username':'admin','password':'admin123'})
token = r.json().get('token','')
h = {'Authorization': f'Bearer {token}'}

# Check today's attendance
r = requests.get(f'{base}/api/attendance/today', headers=h)
data = r.json()
print('=== TODAY ATTENDANCE ===')
if isinstance(data, dict):
    present = data.get('present', [])
    absent = data.get('absent', [])
    print(f'Present: {len(present)}')
    for p in present[:10]:
        print(f'  {p.get("name","?")} - {p.get("location","?")} at {p.get("first_seen","?")}')
    print(f'Absent: {len(absent)}')
    for a in absent[:5]:
        print(f'  {a.get("name","?")}')
else:
    print(data)

# Check last attendance logs from local webcam
conn = sqlite3.connect('/private/tmp/ChronoSenseWeb-clean/backend/profiles.db')
c = conn.cursor()
c.execute("SELECT name, location, emotion, timestamp FROM attendance_log WHERE location = 'Local Webcam' ORDER BY timestamp DESC LIMIT 10")
rows = c.fetchall()
print()
print('=== RECENT LOCAL WEBCAM LOGS ===')
for row in rows:
    print(f'  {row[0]} @ {row[1]} - emotion={row[2]} - {row[3]}')
if not rows:
    print('  (no local webcam logs)')

c.execute("SELECT COUNT(*) FROM attendance_log WHERE location = 'Local Webcam'")
total = c.fetchone()[0]
print(f'  Total local webcam records: {total}')

# Check all locations in attendance_log
c.execute("SELECT DISTINCT location, COUNT(*) FROM attendance_log GROUP BY location")
print()
print('=== ALL LOCATIONS IN ATTENDANCE LOG ===')
for row in c.fetchall():
    print(f'  {row[0]}: {row[1]} records')

conn.close()
