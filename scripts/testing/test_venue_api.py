import requests
from datetime import date

r = requests.post('http://localhost:8000/api/auth/login', json={'username':'admin','password':'admin123'})
token = r.json().get('token','')
headers = {'Authorization': f'Bearer {token}'}

print('=== ACTIVITIES BY LOCATION (real-time) ===')
r1 = requests.get('http://localhost:8000/api/activities/by-location', headers=headers)
data1 = r1.json()
for loc, info in data1.get('locations', {}).items():
    print(f'  {loc}:')
    print(f'    total_people: {info.get("total_people", 0)}')
    print(f'    activities: {info.get("activities", {})}')
    print(f'    engagement: {info.get("engagement_percentage", 0)}% ({info.get("engagement_category", "N/A")})')
    print(f'    dominant_activity: {info.get("dominant_activity", "N/A")}')
if not data1.get('locations'):
    print('  (no locations returned)')

print()
print('=== EMOTIONS BY LOCATION (last 24h) ===')
r2 = requests.get('http://localhost:8000/api/emotions/by-location', headers=headers)
data2 = r2.json()
for loc, info in data2.get('locations', {}).items():
    print(f'  {loc}:')
    print(f'    total_detections: {info.get("total_detections", 0)}')
    print(f'    emotions: {info.get("emotions", {})}')
    print(f'    dominant_emotion: {info.get("dominant_emotion", "N/A")}')
if not data2.get('locations'):
    print('  (no locations returned)')

print()
today = date.today().isoformat()
print(f'=== EMOTIONS BY LOCATION (date={today}) ===')
r3 = requests.get(f'http://localhost:8000/api/emotions/by-location?date={today}', headers=headers)
data3 = r3.json()
for loc, info in data3.get('locations', {}).items():
    emotions = info.get('emotions', {})
    total = info.get('total_detections', 0)
    print(f'  {loc}: total={total}, emotions={emotions}')
if not data3.get('locations'):
    print('  (no locations returned)')

print()
print('=== COMPARISON: Are the two cameras returning DIFFERENT data? ===')
locs1 = data1.get('locations', {})
locs2 = data2.get('locations', {})
all_cameras = set(list(locs1.keys()) + list(locs2.keys()))
for cam in sorted(all_cameras):
    a = locs1.get(cam, {})
    e = locs2.get(cam, {})
    print(f'  {cam}:')
    print(f'    Activities: {a.get("activities", "N/A")} ({a.get("total_people", 0)} people)')
    print(f'    Emotions: {e.get("emotions", "N/A")} ({e.get("total_detections", 0)} detections)')
