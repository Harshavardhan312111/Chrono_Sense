# ChronoSenseWeb Demo - Quick Start Guide

## ✅ System Status

✅ **Server Running**: http://localhost:8000
✅ **5 Cameras Configured**: Ready to stream
✅ **All AI Models Loaded**: Face recognition, emotion detection, activity detection
✅ **Database**: 15 profiles loaded

## 🎥 Camera Pages

### Primary Page (Fixed)
- **URL**: http://localhost:8000/camera-stream.html
- **Features**: 
  - Sidebar camera list for switching between cameras
  - Detailed stream information
  - Professional UI with gradient background
  - **NEW**: MJPEG streaming fixed - no longer refreshes timestamp every 100ms

### Backup Test Page  
- **URL**: http://localhost:8000/camera-test.html
- **Features**:
  - Simple, clean interface
  - Quick camera switching
  - Refresh button for each stream
  - Good for quick testing

## 📹 Available Cameras

1. **Camera 4**: CP IP Camera - Chronosphere (RTSP Stream)
   - Status: Enabled  
   - Type: RTSP
   - URL: rtsp://admin:admin%40123@192.168.4.136:554/cam/realmonitor?channel=1&subtype=0

2. **Camera 5**: Petals 306 F (RTSP Stream)
   - Status: Enabled
   - Type: RTSP

3. **Camera 7**: Chronosphere Lab 1 - Fa (RTSP Stream)
   - Status: Enabled
   - Type: RTSP

4. **Camera 8**: Chronosphere Lab 2 - F (RTSP Stream)
   - Status: Enabled
   - Type: RTSP

5. **Camera 9**: Local Webcam (Built-in Webcam)
   - Status: Enabled
   - Type: LOCAL_WEBCAM
   - Best for testing since it's always available

## 🔧 What Was Fixed

The original `camera-stream.html` had a critical issue:
- **Problem**: The code was changing the `<img>` src URL every 100ms with a timestamp query parameter
- **Impact**: Browser couldn't establish continuous MJPEG stream connection
- **Solution**: 
  - Removed timestamp from stream URL
  - Stopped the setInterval that was constantly refreshing src
  - Now img tag receives continuous MJPEG frames properly

## 🧪 Testing

### Direct Stream Test
```bash
# Test local webcam stream (camera 9)
curl http://localhost:8000/api/cameras/9/stream | xxd | head -20

# Test CP IP Camera (camera 4)  
curl http://localhost:8000/api/cameras/4/stream | xxd | head -20
```

### API Test
```bash
# Get all cameras
curl http://localhost:8000/api/cameras

# Get single camera stream
curl http://localhost:8000/api/cameras/9/stream
```

## 🎬 Demo Flow

1. Open http://localhost:8000/camera-stream.html in browser
2. Select **Camera 9** (Local Webcam) from the sidebar
3. Click **Start Stream** button
4. Live video feed should display in the center panel
5. You can switch to other cameras (4, 5, 7, 8) - some may fail if those RTSP streams are offline, which is normal
6. Observed data will include:
   - Face detection (if faces present)
   - Emotion recognition (Neutral, Happy, Sad, etc.)
   - Activity detection (Reading, Writing, Raising Hand, etc.)
   - Identity recognition (if person is in database)

## 🚀 Backend API Endpoints

### Streaming
- `GET /api/cameras` - Get all cameras list
- `GET /api/cameras/{camera_id}/stream` - Get MJPEG stream for camera

### Recognition/Analytics
- `GET /api/cameras/{camera_id}/detections` - Get current detections for camera
- `POST /api/recognition/start/{camera_id}` - Start recognition on camera
- `POST /api/recognition/stop/{camera_id}` - Stop recognition on camera

### Attendance
- `GET /api/attendance/logs` - Get attendance records
- `GET /api/attendance/emotions` - Get emotion analytics
- `GET /api/attendance/activities` - Get activity tracking data

## 📊 Server Logs

View real-time server activity:
```bash
tail -f server.log
```

You'll see:
- Face detection and recognition events
- Emotion detection results
- Activity classification
- Person identification
- Frame processing statistics

## 💡 Notes for Demo

- **Local Webcam (Camera 9)** is recommended for demo as it's always available
- RTSP cameras may be offline - don't worry, the demo focus is on the streaming tech
- The system processes faces in real-time and logs all detections to database
- Emotion detection works best with clear facial expressions
- Activity detection analyzes pose and body language

---

**Last Updated**: 2026-05-14
**Status**: ✅ Ready for Demo
