# ChronoSense Emotion & Activity Recognition Execution Flow

## Current Execution Order (VERIFIED ✓)

### Step 1: Face Detection & Student Count
```
Frame Input → InsightFace Detection → Extract Faces with Landmarks
                                   ↓
                         Update Student Count
                    (stored in: activity_detector.student_count)
```
**Code Location:** `cctv_recognition.py` Line 127-135
- Calls: `self.ai_engine.detect_faces_with_landmarks(frame)`
- Returns: List of detected faces with 106-point landmarks
- Counts: `self.activity_detector.update_student_count(len(detected_faces))`

---

### Step 2: For Each Detected Face - Recognition & Emotion Detection
```
For Each Face:
    ├─ Crop Face Region
    ├─ Recognize Face (match against registered students)
    ├─ Detect Emotion (from facial expression)
    └─ Detect Activity (from head pose landmarks)
```
**Code Location:** `cctv_recognition.py` Line 149-352
- Face recognition: `self._recognize_face(face_crop, frame, face_bbox, landmarks)`
- Emotion detection: `emotion_detector.detect_emotion(frame_for_emotion, face_bbox)`
- Activity detection: `activity_detector.detect_activity(original_frame, face_bbox, landmarks)`

**Output per face:**
```
{
    'profile_id': int,
    'name': str,
    'confidence': float,
    'emotion': str,              # ← From Step 2A
    'emotion_confidence': float,
    'emotion_intensity': str,
    'all_emotions': dict,
    'activity': str,             # ← From Step 2B
    'activity_confidence': float,
    'frame_path': str
}
```

---

### Step 3: Log to Database
```
Detected Results → Log to Attendance & Activity Tables
                   ├─ attendance_log (face, emotion, location, timestamp)
                   └─ activity_log (activity, activity_confidence, emotion)
```
**Code Location:** `server.py` Line 2722-2723
- Calls: `attendance_tracker.log_stream_detections(detections, location=camera_name)`
- Logs to: Database tables

---

### Step 4: Aggregate & Display Results

#### 4A: List Activities Detected
**Endpoint:** `GET /api/classroom/activities` or `/api/activities/by-location`

Returns all unique activities detected grouped by camera/location:
```json
{
    "location": "Petals 306 F",
    "activities": {
        "Listening": 15,
        "Distracted": 8,
        "Reading": 4,
        "Playing": 2,
        "Unknown": 0
    },
    "total_detections": 29,
    "dominant_activity": "Listening"
}
```

#### 4B: Calculate & Display Engagement Ratio
**Endpoint:** `GET /api/activities/engagement/{location}`

High engagement activities: `['Listening', 'Writing', 'Raised_Hand', 'Collaboration']`

Returns:
```json
{
    "location": "Petals 306 F",
    "high_engagement": 25,
    "medium_engagement": 2,
    "low_engagement": 2,
    "engagement_percentage": 86.2
}
```

---

## Data Flow Summary

```
┌─────────────────────────────────────────────────────────┐
│  CCTV Camera Stream (Petals 306 F)                      │
└──────────────────┬──────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────┐
│  STEP 1: FACE DETECTION & COUNTING                      │
│  └─ DetectedFaces: 35-40 students (with landmarks)      │
│  └─ StudentCount: 38 (smoothed over 10 frames)          │
└──────────────────┬──────────────────────────────────────┘
                   │
        ┌──────────▼──────────┐
        │                     │
        ▼                     ▼
  ┌─────────────────┐  ┌─────────────────┐
  │  REGISTERED     │  │  UNREGISTERED   │
  │  STUDENTS (25)  │  │  STUDENTS (13)  │
  └────┬────────────┘  └────┬────────────┘
       │                     │
       ▼                     ▼
┌─────────────────────────────────────────────────────────┐
│  STEP 2: EMOTION + ACTIVITY DETECTION (per face)       │
│  ├─ Emotion Detection (from facial expression)          │
│  │  └─ Happy, Sad, Neutral, Angry, Surprised, etc.    │
│  └─ Activity Detection (from head pose landmarks)       │
│     └─ Listening, Distracted, Reading, Playing, etc.   │
└──────────────────┬──────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────┐
│  STEP 3: DATABASE LOGGING                              │
│  ├─ attendance_log: face recognition + emotion         │
│  └─ activity_log: activity + emotion (per entry)       │
└──────────────────┬──────────────────────────────────────┘
                   │
        ┌──────────▼──────────┐
        │                     │
        ▼                     ▼
┌──────────────────────┐  ┌──────────────────────┐
│  STEP 4A: ACTIVITIES │  │  STEP 4B: ENGAGEMENT │
│  List all detected   │  │  Calculate ratio of  │
│  activities & count  │  │  high engagement vs  │
│                      │  │  low engagement      │
│  Listening:     15   │  │  Engagement: 86.2%   │
│  Distracted:     8   │  │  High: 25            │
│  Reading:        4   │  │  Medium: 2           │
│  Playing:        2   │  │  Low: 2              │
└──────────────────────┘  └──────────────────────┘
        │                     │
        └──────────┬──────────┘
                   │
                   ▼
        ┌──────────────────────┐
        │  DASHBOARD DISPLAY   │
        │  Shows: Student Count│
        │         Activities   │
        │         Engagement %  │
        └──────────────────────┘
```

---

## Verification Checklist

- [x] **Step 1:** Face detection & student counting (smoothed over 10 frames)
- [x] **Step 2:** Emotion detection (facial expression analysis)
- [x] **Step 2:** Activity detection (head pose from landmarks)
- [x] **Step 3:** Database logging (attendance_log + activity_log)
- [x] **Step 4:** Activity aggregation by location
- [x] **Step 4:** Engagement ratio calculation

All steps execute in order! ✓

---

## API Endpoints for Display

| Step | Endpoint | Purpose |
|------|----------|---------|
| 1 | Via stream logs | Display student count |
| 2 | Via stream logs | Show emotion/activity per person |
| 4A | `GET /api/classroom/activities` | List activities & counts |
| 4A | `GET /api/activities/by-location` | Activities grouped by camera |
| 4B | `GET /api/activities/engagement/{location}` | Engagement percentage |
| Dashboard | `http://localhost:8000/` | Full analytics view |

