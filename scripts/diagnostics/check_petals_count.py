import requests, json

r = requests.post('http://localhost:8000/api/auth/login', json={'username':'admin','password':'admin123'})
token = r.json().get('token','')
headers = {'Authorization': f'Bearer {token}'}

# Get detailed real-time detections for all cameras
r1 = requests.get('http://localhost:8000/api/activities/by-location', headers=headers)
data = r1.json()
locs = data.get('locations', {})
print('=== ACTIVITIES (real-time face count) ===')
for loc, info in locs.items():
    print(f'  {loc}: total_people={info["total_people"]}, activities={info["activities"]}')

# Check camera list
r2 = requests.get('http://localhost:8000/api/cameras', headers=headers)
cameras = r2.json()
print()
print('=== CAMERAS ===')
if isinstance(cameras, list):
    for cam in cameras:
        print(f'  id={cam.get("id")}, name={cam.get("name")}, enabled={cam.get("enabled")}, url={cam.get("url","")[:60]}')
elif isinstance(cameras, dict):
    for k,v in cameras.items():
        print(f'  {k}: {v}')

# Get per-person detail for Petals
r3 = requests.get('http://localhost:8000/api/activities/by-person?location=Petals 306 F', headers=headers)
print()
print('=== PERSONS AT PETALS 306 F ===')
pdata = r3.json()
people = pdata.get('people', [])
print(f'Total people entries: {len(people)}')
for p in people[:25]:
    print(f'  {p.get("name")}: activity={p.get("activity")}')

# Get raw detections from debug endpoint
r4 = requests.get('http://localhost:8000/api/debug/activity-log', headers=headers)
print()
print('=== DEBUG ACTIVITY LOG (last entries) ===')
ddata = r4.json()
if isinstance(ddata, dict):
    for k,v in list(ddata.items())[:3]:
        print(f'  {k}: {v}')
elif isinstance(ddata, list):
    print(f'  Total entries: {len(ddata)}')
    for entry in ddata[:5]:
        print(f'  {entry}')

# Check CCTV recognition status
r5 = requests.get('http://localhost:8000/api/cctv/status', headers=headers)
print()
print('=== CCTV STATUS ===')
status = r5.json()
if isinstance(status, dict):
    for cam_id, cam_data in status.items():
        if isinstance(cam_data, dict):
            name = cam_data.get('name', cam_id)
            known = cam_data.get('known_faces', cam_data.get('known_count', '?'))
            unknown = cam_data.get('unknown_faces', cam_data.get('unknown_count', '?'))
            total = cam_data.get('total_faces', cam_data.get('total', '?'))
            print(f'  {name}: known={known}, unknown={unknown}, total={total}')
        else:
            print(f'  {cam_id}: {cam_data}')
