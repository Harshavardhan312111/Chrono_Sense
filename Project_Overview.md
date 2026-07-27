# ChronoSenseWeb Project Overview

## 1. Project Summary

ChronoSenseWeb is a computer-vision-based classroom monitoring platform built around face recognition, attendance logging, emotion analytics, and activity detection. It combines a Python/FastAPI backend, a React frontend served by FastAPI, MongoDB-backed runtime storage, and multiple camera inputs such as RTSP CCTV streams and a local webcam.

At a high level, the system is designed to:

- register people using facial embeddings
- identify registered people from live camera feeds
- log attendance and check-in/check-out behavior
- track emotion signals for classroom analytics
- detect posture/activity patterns for engagement analysis
- manage multiple camera sources from one server

## 2. Tech Stack

### Backend

- Python
- FastAPI
- Uvicorn
- MongoDB
- OpenCV
- InsightFace
- ONNX Runtime
- NumPy
- SciPy
- scikit-learn

### Frontend

- React 18
- Vite
- React Router
- FastAPI-served SPA build
- npm-based development workflow

### Data / Assets

- MongoDB runtime database via `MONGO_URI` and `MONGO_DB_NAME`
- ONNX emotion model: `backend/models/emotion-ferplus-8.onnx`
- Stored face snapshots: `backend/face_snapshots/`
- Runtime logs: `server.log`, `logs/`

## 3. Repository Layout

```text
ChronoSenseWeb-checkpoint-20260411_104154/
├── backend/                # FastAPI app, AI pipeline, database logic
├── frontend/react/         # React frontend source and build output
├── docs/                   # Setup notes, audits, phase summaries, deep dives
├── scripts/                # Setup, diagnostics, verification, testing helpers
├── logs/                   # Additional runtime/debug outputs
├── requirements.txt        # Python dependencies
├── start-server.sh         # Recommended local startup script
└── server.log              # Large runtime log artifact
```

## 4. Core Architecture

### 4.1 Web Application Layer

The main application entrypoint is [`backend/server.py`](/Users/mva357/Desktop/ChronoSenseWeb-checkpoint-20260411_104154/backend/server.py). It:

- creates the FastAPI app
- enables permissive CORS
- serves the React SPA and compatibility redirects for legacy frontend URLs
- initializes the recognition engine, database layer, attendance tracker, auth manager, and CCTV manager
- exposes HTML routes and API endpoints on port `8000`

The server loads all registered face embeddings into memory on startup so recognition can run without re-querying the datastore for each frame.

### 4.2 Recognition and Analytics Pipeline

The live-processing stack is centered around these modules:

- [`backend/ai_engine.py`](/Users/mva357/Desktop/ChronoSenseWeb-checkpoint-20260411_104154/backend/ai_engine.py): face recognition, embedding comparison, emotion wrapper, tracking helpers
- [`backend/cctv_recognition.py`](/Users/mva357/Desktop/ChronoSenseWeb-checkpoint-20260411_104154/backend/cctv_recognition.py): real-time multi-camera processing, face matching, snapshot capture, logging hooks
- [`backend/emotion_detector.py`](/Users/mva357/Desktop/ChronoSenseWeb-checkpoint-20260411_104154/backend/emotion_detector.py): FERPlus-based emotion detection
- [`backend/lite_pose_detector.py`](/Users/mva357/Desktop/ChronoSenseWeb-checkpoint-20260411_104154/backend/lite_pose_detector.py): lightweight activity/pose classification

Typical per-frame flow:

1. capture frame from webcam or CCTV stream
2. detect faces and landmarks
3. generate or reuse embeddings
4. match against registered profiles
5. detect emotion for each face
6. detect activity/pose where available
7. log results into attendance, emotion, and activity collections
8. expose current state through dashboard and API endpoints

### 4.3 Attendance vs Analytics Separation

A key project behavior is the separation between official attendance and broader analytics:

- attendance views are meant for registered people
- emotion/activity analytics can include broader classroom detections
- unknown or unregistered detections are tracked separately through unknown-face handling and analytics logging paths

This separation shows up throughout the codebase and documentation, especially in [`backend/attendance.py`](/Users/mva357/Desktop/ChronoSenseWeb-checkpoint-20260411_104154/backend/attendance.py) and the docs in `docs/`.

## 5. Key Backend Modules

### `backend/server.py`

Main API server. Important endpoint groups include:

- authentication
- profile registration and maintenance
- attendance reports and exports
- emotion analytics
- classroom activity analytics
- camera CRUD and health/status
- recognition start/stop/status per camera
- snapshot and stream access

### `backend/database.py`

Profile database layer. Manages:

- Mongo-backed `profiles` and `unknown_faces` collections
- profile insert/update/delete
- embedding serialization/deserialization

### `backend/attendance.py`

Attendance and analytics storage layer. Initializes and uses collections/tables such as:

- `attendance_log`
- `attendance_summary`
- `class_schedule`
- `emotion_analytics`
- `activity_log`
- `activity_summary`

It also includes deduplication caches to avoid over-logging repeated detections and activities.

### `backend/auth.py`

Authentication/session manager. It manages:

- `users`
- `sessions`

Mongo-backed runtime sessions use a TTL index on `expires_at`. The service also seeds default users:

- username: `admin`
- password: `admin123`

### `backend/cctv_manager.py`

Camera configuration manager for the `cctv_cameras` collection/table. It stores:

- camera name
- source URL
- camera type
- credentials
- FPS
- resolution
- enabled flag

## 6. Frontend Surface

The frontend lives in [`frontend/react/`](/Users/chiefaiofficer/Desktop/ChronoSenseWeb-checkpoint-20260411_104154/frontend/react). The React app is served by FastAPI at `/` and includes:

- login routes for admin and director access
- admin dashboard workflows
- director attendance review
- registration flow
- validation workflow
- camera settings and camera stream viewer

Legacy `.html` frontend URLs are kept only as temporary compatibility redirects into the React application.

## 7. Database Model Overview

The runtime datastore is MongoDB.

### Main collections

- `profiles`: registered people and their embeddings
- `users`: application users
- `sessions`: auth tokens and expiry
- `cctv_cameras`: configured camera sources
- `unknown_faces`: persistent unknown face tracking
- `attendance_log`: raw presence/emotion events
- `attendance_summary`: daily rollups
- `class_schedule`: expected class timings
- `emotion_analytics`: per-day emotion aggregates
- `activity_log`: raw activity events
- `activity_summary`: aggregated activity metrics

### Runtime configuration

- `MONGO_URI`: MongoDB connection string
- `MONGO_DB_NAME`: ChronoSense database name
- `MONGO_CONNECT_TIMEOUT_MS`: optional connection timeout, defaults to `5000`

## 8. API Overview

The server exposes a broad API surface. Representative groups include:

### Authentication

- `POST /api/auth/login`
- `GET /api/auth/verify`
- `POST /api/auth/logout`

### Attendance

- `GET /api/attendance`
- `GET /api/attendance/today`
- `GET /api/attendance/check-in-out`
- `GET /api/attendance/continuous-presence`
- `GET /api/attendance/late-arrivals`
- `GET /api/attendance/absent-members`
- `GET /api/attendance/export/csv`
- `GET /api/attendance/export/pdf`

### Emotions

- `GET /api/emotions/day-wise`
- `GET /api/emotions/session-wise`
- `GET /api/emotions/trends`
- `GET /api/emotions/by-location`
- `POST /api/emotions/log`
- `GET /api/classroom/emotions`

### Activities

- `GET /api/activities/by-location`
- `GET /api/activities/by-person`
- `GET /api/activities/timeline/{location}`
- `GET /api/activities/engagement/{location}`
- `GET /api/classroom/activities`

### Cameras and Recognition

- `POST /api/cameras/add`
- `GET /api/cameras`
- `GET /api/cameras/{camera_id}`
- `DELETE /api/cameras/{camera_id}`
- `POST /api/cameras/test`
- `POST /api/cameras/{camera_id}/recognition/start`
- `POST /api/cameras/{camera_id}/recognition/stop`
- `GET /api/cameras/{camera_id}/recognition/status`
- `GET /api/cameras/{camera_id}/stream`
- `GET /api/cameras/{camera_id}/snapshots`

## 9. Local Startup and Daily Use

The recommended startup path is npm-based development from the repo root.

Frontend development lives in `frontend/react/` and the repo root now exposes npm scripts for both surfaces:

- `npm run dev` from the repo root starts backend and frontend together
- `npm --prefix backend run dev` starts the FastAPI backend with uvicorn reload
- `npm --prefix frontend/react run dev` starts the React frontend
- [`start-server.sh`](/Users/chiefaiofficer/Desktop/ChronoSenseWeb-checkpoint-20260411_104154/start-server.sh) remains available as the shell-based fallback

Recommended usage:

```bash
cd /Users/chiefaiofficer/Desktop/ChronoSenseWeb-checkpoint-20260411_104154
npm install
npm run dev
```

The root `npm run dev` command bootstraps `frontend/react` dependencies automatically if Vite is not installed yet.

Fallback shell usage:

```bash
cd /Users/chiefaiofficer/Desktop/ChronoSenseWeb-checkpoint-20260411_104154
./start-server.sh
```

Manual alternative:

```bash
source .venv/bin/activate
PYTHONDONTWRITEBYTECODE=1 ./.venv/bin/uvicorn backend.server:app --host 0.0.0.0 --port 8000 --reload
```

## 10. Operations Notes

- The server is designed to run on port `8000`.
- The production frontend is served by FastAPI, while local React development uses the Vite dev server.
- The repository contains large runtime artifacts such as `server.log` and many saved snapshots under `backend/face_snapshots/`.
- Camera auto-start logic exists in `backend/server.py`, but the startup hook is currently disabled in comments to avoid server hangs during startup.
- Some docs still reference earlier temporary paths or older checkpoint names; use the current repository path and `requirements.txt` in this checkpoint unless a specific doc says otherwise.

## 11. Useful Project Documents

The `docs/` folder contains a lot of historical and operational context. Good starting points are:

- [`docs/SETUP_AND_STARTUP.md`](/Users/mva357/Desktop/ChronoSenseWeb-checkpoint-20260411_104154/docs/SETUP_AND_STARTUP.md)
- [`docs/CHECKPOINT_v3_README.md`](/Users/mva357/Desktop/ChronoSenseWeb-checkpoint-20260411_104154/docs/CHECKPOINT_v3_README.md)
- [`docs/EXECUTION_FLOW.md`](/Users/mva357/Desktop/ChronoSenseWeb-checkpoint-20260411_104154/docs/EXECUTION_FLOW.md)
- [`docs/EMOTION_ANALYTICS_INDEX.md`](/Users/mva357/Desktop/ChronoSenseWeb-checkpoint-20260411_104154/docs/EMOTION_ANALYTICS_INDEX.md)
- [`docs/SYSTEM_VERIFICATION_AUDIT_REPORT.md`](/Users/mva357/Desktop/ChronoSenseWeb-checkpoint-20260411_104154/docs/SYSTEM_VERIFICATION_AUDIT_REPORT.md)

## 12. Practical Summary

If you are new to this codebase, the shortest mental model is:

- FastAPI serves both APIs and static dashboard pages
- MongoDB is the operational datastore
- InsightFace powers face recognition
- FERPlus powers emotion inference
- OpenCV-based pose/activity logic feeds engagement analytics
- `npm run dev` is the primary day-to-day entrypoint
- the system is optimized around multi-camera classroom monitoring rather than a generic web app architecture
