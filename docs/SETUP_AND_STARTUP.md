# ChronoSense Web - Setup & Startup Guide

## Overview
ChronoSenseWeb is a comprehensive attendance and emotion tracking system with real-time camera integration and analytics.

### Key Features
- **Attendance Tracking**: Real-time face recognition for registered students
- **Emotion Analytics**: Separate emotion detection system for all faces (registered and unregistered)
- **Multi-Camera Support**: Support for multiple RTSP streams (CP IP Camera, Petals 306 F, Local Webcam)
- **Dashboard**: Real-time visualization of attendance and emotion data
- **Video Streaming**: Live camera feed viewing

---

## System Architecture

### Registered Attendance (Attendance Dashboard)
- **Only shows**: Registered students (profile_id > 0)
- **Purpose**: Track student presence for attendance records
- **Query Filter**: `WHERE profile_id > 0`
- **Data**: Check-in/check-out times, duration, detection count

### Emotion Analytics (Emotion Dashboard)
- **Tracks**: All faces including unregistered attendees (profile_id = -1)
- **Purpose**: Analyze emotional patterns for research/testing
- **Storage**: Separate `attendance_log` records with emotion data
- **Registered faces**: Full frame path for attendance validation
- **Unregistered faces**: Logged as "Unregistered Attendee" with emotions only (no frame path for privacy)

---

## Getting Started

### 1. First-Time Setup
```bash
cd /private/tmp/ChronoSenseWeb-clean

# Create virtual environment (if needed)
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements_clean.txt
```

### 2. Start the Server

#### Option A: Using Startup Script (Recommended - Fresh Start Daily)
```bash
cd /private/tmp/ChronoSenseWeb-clean
./start-server.sh
```

**What this script does:**
- Kills any existing server processes
- Cleans Python bytecode cache (__pycache__, *.pyc)
- Prevents bytecode caching (PYTHONDONTWRITEBYTECODE=1)
- Starts server fresh with new code
- Verifies server is responding

#### Option B: Manual Startup
```bash
cd /private/tmp/ChronoSenseWeb-clean
PYTHONDONTWRITEBYTECODE=1 ./.venv/bin/python backend/server.py
```

### 3. Verify Server is Running
```bash
# Check server is responding
curl http://localhost:8000/api/cameras

# Check server logs
cat /private/tmp/ChronoSenseWeb-clean/server.log | tail -20
```

---

## Accessing the Application

### Web Interface
- **Main Dashboard**: http://localhost:8000
- **Attendance Tab**: Check-in/check-out times for registered students
- **Emotion Analytics Tab**: Emotional distribution across locations
- **Camera Streams**: Live video from connected cameras

### Default Credentials
- **Username**: admin
- **Password**: admin123

---

## Database

### Location
```
/private/tmp/ChronoSenseWeb-clean/backend/profiles.db
```

### Key Tables

#### `profiles` (Registered Students)
```sql
id (INTEGER) - Profile ID (auto-increment, > 0)
name (TEXT) - Student name
embedding (TEXT) - Face embedding (JSON)
check_in_time (TEXT) - Expected check-in (HH:MM)
check_out_time (TEXT) - Expected check-out (HH:MM)
```

#### `attendance_log` (Emotion & Attendance Events)
```sql
profile_id (INTEGER) - -1 for unregistered, > 0 for registered
name (TEXT) - Student name or "Unregistered Attendee"
timestamp (DATETIME) - Detection time
status (TEXT) - 'present' / 'absent'
emotion (TEXT) - Emotion type (Neutral, Happy, Sad, etc.)
emotion_confidence (REAL) - Confidence score
location (TEXT) - Camera name
frame_path (TEXT) - Snapshot path (NULL for unregistered)
```

#### `cctv_cameras` (Connected Cameras)
```sql
id (INTEGER) - Camera ID
name (TEXT) - Camera name
source (TEXT) - RTSP URL
enabled (BOOLEAN) - Is camera active
fps (INTEGER) - Frames per second
resolution (TEXT) - Video resolution
```

---

## API Endpoints

### Attendance (Registered Students Only)
```
GET /api/attendance/check-in-out?date=2026-04-06
GET /api/attendance/continuous-presence
GET /api/attendance/absent-members?date=2026-04-06
GET /api/attendance/late-arrivals?date=2026-04-06
```

### Emotion Analytics (All Faces)
```
GET /api/emotions/by-location (requires auth)
GET /api/emotions/by-student/{student_id} (requires auth)
GET /api/emotions/distribution (requires auth)
```

### Cameras
```
GET /api/cameras (list all cameras)
GET /cctv/{camera_id}/stream (video stream)
```

### Authentication
```
POST /api/auth/login
  Body: {"username": "admin", "password": "admin123"}
  Returns: {"token": "..."}

# Use token with:
Authorization: Bearer <token>
```

---

## Cameras Configuration

### Currently Connected
1. **CP IP Camera - Chronosphere** (ID: 4)
   - RTSP: `rtsp://admin:admin%40123@192.168.4.136:554/cam/realmonitor?channel=1&subtype=0`
   - Resolution: 1280x720
   - FPS: 28
   
2. **Petals 306 F** (ID: 9)
   - RTSP: `rtsp://admin:123456@192.168.3.92:554`
   - Resolution: 1280x720
   - FPS: 40

3. **Local Webcam** (ID: 1)
   - Source: System webcam
   - For testing/development

---

## Registered Students (15 Total)

1. Dr. Manojkumar K
2. Harsha vardhan
3. Payal Rawtole
4. Avni Kapoor
5. Mr. Aditya Mewati
6. Ms. Srushti Jangde
7. Chandrika Vabbina
8. Mr. Jay Khatri
9. Mr. Durgesh Pandey
10. Mr. Nitin Paliwal
11. Ms. Sharda Bari
12. Vardhani Jadiya
13. Mrs Stuti Agrawal
14. Avika Landge
15. Mrs. Tanishka Dodwani

---

## Important Notes

### Why Module Separation?
- **Attendance Dashboard**: Only registered students for official attendance records
- **Emotion Analytics**: All faces (including unregistered) for research and emotion testing
- **Privacy**: Unregistered faces logged without frame paths to attendance table

### Fresh Start Daily
Use `./start-server.sh` to:
1. Clean all Python bytecode that might cache old code
2. Kill existing processes
3. Start fresh with latest code
4. Automatically verify startup

### Troubleshooting

If "Unregistered Attendee" appears in attendance:
```bash
# Clean cache and restart
cd /private/tmp/ChronoSenseWeb-clean
./start-server.sh
```

If server won't start:
```bash
# Kill all Python processes and check logs
pkill -9 python
tail -50 server.log
```

If camera not detecting:
1. Check camera is enabled in database: `SELECT id, name, enabled FROM cctv_cameras`
2. Verify RTSP URL is correct and camera is online
3. Check network connectivity
4. Restart server: `./start-server.sh`

---

## Recent Updates (April 6, 2026)

✅ **Emotion Detection Working**: Both cameras (CP IP Camera, Petals 306 F) actively logging emotions
✅ **Attendance Module Fixed**: Unregistered attendees excluded from dashboard
✅ **Modules Separated**: Emotion analytics independent from attendance tracking
✅ **Startup Script**: Fresh server restart without stale bytecode

---

## Support

For issues or questions, check:
1. Server logs: `cat server.log | tail -50`
2. Database queries for debugging
3. Browser console for frontend errors (F12)
4. API response with: `curl http://localhost:8000/api/cameras`
