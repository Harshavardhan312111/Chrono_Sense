# ChronoSenseWeb Full KT and Production Readiness Report

## 1. Document Purpose

ChronoSenseWeb is a classroom intelligence platform combining facial recognition, attendance, emotion analytics, activity analytics, camera operations, and administrative workflows. This document is the engineering handoff for the current repository state.

It describes the implemented architecture, runtime behavior, persistence model, operating procedures, verified issues, and repository-level production readiness. Findings are separated into confirmed evidence and validation-needed observations. The production score does not claim that live cameras, MongoDB, network bandwidth, load, or deployment infrastructure were tested from this workspace.

## 2. Product Capabilities

- Register students and faculty with captured or uploaded face images.
- Generate and persist primary and multi-view face embeddings.
- Process local webcam and CCTV RTSP streams.
- Detect faces, compare embeddings, apply recognition thresholds, and retain top candidates.
- Mark attendance with confidence floors and duplicate-event controls.
- Store recognition review evidence, including best score and face snapshot.
- Review unknown faces and associate them with registered profiles.
- Process classroom emotion signals and historical emotion analytics.
- Process classroom activity and engagement signals.
- Configure cameras, stream sources, per-camera thresholds, and processing modes.
- Operate recognition, attendance, emotion, and activity workers through camera runtime state.
- Provide dashboards, exports, reports, role-based administration, and session-based authentication.

## 3. Technology and Runtime Stack

### Backend

- Python, FastAPI, and Uvicorn.
- MongoDB accessed through PyMongo.
- OpenCV for frame capture and image operations.
- InsightFace/ArcFace and ONNX Runtime for face detection and embeddings.
- NumPy, SciPy, scikit-learn, FilterPy, pandas, and report-generation dependencies.
- Optional emotion and activity model runtimes with controlled fallback behavior.

### Frontend

- React 18, Vite, React Router, Recharts, and lucide-react.
- The built React application is served by FastAPI; Vite is used for local development.

### Runtime artifacts

- `backend/face_snapshots/`: face and review snapshots.
- `logs/` and `server.log`: service and worker logs.
- `backend/models/` and vendor directories: model/runtime assets.
- MongoDB: operational and analytical state.

## 4. Repository Structure

```text
backend/                 FastAPI application, AI pipelines, managers, workers
frontend/react/          React SPA, pages, components, API helpers, styles
docs/                    KT, implementation reports, diagnostics, verification notes
scripts/setup/           Data setup and restore helpers
scripts/testing/         API and subsystem test scripts
scripts/diagnostics/     Runtime and data diagnostics
scripts/verify/          System verification scripts
logs/                    Generated runtime logs
requirements.txt         Python dependencies
package.json             Root development orchestration
start-server.sh          Local backend startup helper
.env.example             Configuration template
```

## 5. High-Level Architecture

```text
React SPA -> FastAPI API -> domain managers/services -> MongoDB
                              |
                              +-> recognition runtime state
                              +-> camera workers -> RTSP/webcam -> AI pipelines
                              +-> snapshots and analytics events
```

`backend/server.py` initializes shared services and exposes the API. Worker processes use the same domain code and coordinate desired/current camera state through MongoDB runtime collections. Recognition produces identity candidates and quality metadata; attendance, emotion, activity, and review persistence consume those results according to their own rules.

## 6. Implementation Map

| Area | Main implementation | Responsibility |
|---|---|---|
| API and app startup | `backend/server.py` | FastAPI initialization, CORS, service construction, routes, static frontend, streams, snapshots |
| Recognition engine | `backend/ai_engine.py` | Face detection, embedding extraction, similarity scoring, threshold decisions, top candidates |
| Camera processing | `backend/cctv_recognition.py` | Frame loops, tracking, camera configuration, snapshots, recognition persistence, analytics handoff |
| Attendance and analytics storage | `backend/attendance.py` | Attendance events/summaries, confidence gates, deduplication, reports, emotion/activity event persistence |
| Profile storage | `backend/database.py` | Profile CRUD, embedding serialization, view embeddings, unknown-face records |
| Authentication | `backend/auth.py` and `backend/rbac.py` | User credentials, sessions, capability checks, role scope |
| Camera storage | `backend/cctv_manager.py` | Camera CRUD, credentials, stream source, thresholds, enabled state, processing flags |
| Runtime coordination | `backend/recognition_runtime.py` | Desired state, worker state, heartbeats, latest detections, runtime cleanup |
| MongoDB setup | `backend/mongo_store.py` | Connection, database selection, indexes, TTL indexes, counters |
| Time handling | `backend/time_utils.py`, `frontend/react/src/lib/time.js` | `Asia/Kolkata` application time and frontend formatting |
| Frontend routing | `frontend/react/src/App.jsx` | Route map and protected workspaces |
| Frontend domains | `frontend/react/src/pages/` | Registration, people, attendance, recognition, cameras, emotion, activity, reports, admin |
| Frontend integration | `frontend/react/src/lib/` | API calls, operations, RBAC, navigation, date/time helpers |

## 7. Backend API Domains

The route surface in `backend/server.py` is grouped around these domains:

- Authentication, session verification, users, roles, and capabilities.
- Overview dashboards, live operations, alerts, and system status.
- People, profiles, registration, embeddings, class, and section metadata.
- Attendance marking, history, calendar, schedules, summaries, reports, CSV, and PDF exports.
- Recognition start/stop, status, logs, detections, validation, unknown faces, and threshold review.
- Camera CRUD, connection tests, stream access, camera status, enablement, and processing controls.
- Emotion analytics, live sensing, test endpoints, trends, class summaries, and student timelines.
- Activity analytics, engagement summaries, class activity, and reports.
- Snapshot serving, browser-camera analysis, face boxes, and MJPEG/stream access.

Authentication is session-token based. Protected endpoints resolve the user and check capability constants from `backend/rbac.py`. The API also retains compatibility/legacy routes alongside React delivery routes.

## 8. Frontend Surface

The React route groups are:

- `/overview`: overview dashboard and live operations.
- `/attendance/*`: today, history, calendar, reports, and analytics.
- `/recognition/*`: validation, unknown faces, recognition logs, and threshold review.
- `/emotions/*`: live analytics, sensing test, trends, class summaries, and student timeline.
- `/activities/*`: live activity, engagement, and activity reports.
- `/people/*`: student/faculty workspaces and registration.
- `/cameras/*`: settings, setup, and stream viewer.
- `/reports`: report center.
- `/admin/*`: users, roles, and system administration.

Important pages include `RegistrationPage`, `ValidationPage`, `RecognitionReviewPage`, `RecognitionLogsPage`, `AttendanceWorkspacePage`, `EmotionAnalyticsPage`, `EmotionSensingTestPage`, `ActivityAnalyticsPage`, `CameraSettingsPage`, and `CameraStreamViewerPage`. Shared shell, protected routes, authentication state, API helpers, navigation, RBAC, and date formatting are under `frontend/react/src/components`, `frontend/react/src/state`, and `frontend/react/src/lib`.

## 9. Primary Runtime Workflows

### Profile registration and embeddings

1. The frontend submits captured or uploaded images.
2. The backend detects faces and extracts embeddings.
3. Embeddings are serialized into MongoDB-compatible lists.
4. Primary and `view_embeddings` are stored with profile metadata, including profile type, class, and section.
5. Recognition workers reload profiles into memory at startup and refresh when runtime logic requests it.

### Recognition

1. A worker opens the configured camera source.
2. Frames are sampled and faces are detected.
3. Precomputed face embeddings are reused when available; otherwise the engine extracts one from the crop.
4. Candidate profiles are ranked by similarity and the top candidates are retained.
5. Threshold, score gap, quality, and temporal consensus rules determine the recognition result.
6. Recognized and near-threshold candidate evidence can be written to the recognition review collection.
7. Face snapshots are written under `backend/face_snapshots/` when the relevant persistence path accepts the crop.

### Attendance

Attendance consumes recognized detections through `AttendanceTracker`. A registered profile must satisfy the configured strict recognition floor before an attendance event is written. Existing events are checked using profile/location/time data to prevent repeated writes within the configured deduplication window. Daily summaries are maintained separately from raw attendance events.

### Emotion and activity

Emotion processing uses the configured model backends, quality gates, temporal aggregation, and an explicit fallback state when a model is unavailable. Activity processing combines face/pose and classroom context into event and summary records. These paths are separate from the attendance write decision, although they may consume the same frame/detection cycle.

### Threshold review

`recognition_review` stores one best-evidence row per camera and predicted profile. A higher top score replaces the score fields and snapshot; a lower/equal score increments observation metadata without replacing the best evidence. Verdicts and notes are editable through the review API. The collection has a Mongo TTL index on `updated_at` for 86,400 seconds.

## 10. Database and Collection Model

| Collection | Purpose | Main indexing/retention behavior |
|---|---|---|
| `profiles` | Registered people and embeddings | Unique name; profile/class/section index |
| `users` | Application users | Unique username |
| `sessions` | Session tokens and expiry | TTL on `expires_at` |
| `class_assignments` | User class/section scope | Unique user/class/section |
| `cctv_cameras` | Camera configuration | Unique name |
| `attendance_log` | Raw attendance events | Profile/time and location/time indexes |
| `attendance_summary` | Daily attendance rollups | Unique profile/date |
| `emotion_events` | Per-event emotion output | Profile, location, camera/time indexes |
| `emotion_analytics` | Aggregated emotion values | Profile/date/emotion index |
| `activity_log` | Activity events | Profile/unknown-face/time and location/activity/time indexes |
| `activity_summary` | Per-profile activity rollups | Unique profile/unknown/date/location/activity |
| `class_activity_log` | Classroom activity events | Camera/location/class/time indexes |
| `class_activity_summary` | Classroom daily activity | Unique camera/date/class/section |
| `unknown_faces` | Unknown-face snapshots and embeddings | Camera/last-seen index; application cleanup logic |
| `recognition_review` | Threshold tuning evidence | Unique camera/profile; TTL after one day |
| `camera_logs` | Camera operational events | Camera/time index |
| runtime collections | Desired state, worker state, detections, heartbeats, counters | Used by runtime coordination and sequence IDs |

MongoDB is mandatory for the current backend. `MONGO_URI`, database name, and connection timeout are read from environment configuration.

## 11. Camera and Stream Processing

Camera records hold source type, URL/source, credentials, enabled state, stream settings, threshold overrides, weak-match settings, and worker-related flags. CCTV processing normally depends on RTSP transport and OpenCV/FFmpeg support. Browser webcam analysis is exposed separately through browser-permission-compatible routes.

The application supports main/sub/alternate stream URLs when supplied by the camera configuration, but the actual stream profile is determined by the configured URL and camera firmware. The camera settings and stream viewer expose connection/status behavior; they do not prove that a configured URL is the camera's highest-quality main stream.

## 12. Configuration and Startup

### Required configuration

- `MONGO_URI`: reachable MongoDB connection string.
- `MONGO_DB_NAME`: database name, defaulting to `chronosense`.
- `MONGO_CONNECT_TIMEOUT_MS`: MongoDB connection timeout.
- Recognition thresholds, face-size limits, consensus frames, and weak-match settings as defined by `backend/cctv_recognition.py` and `.env.example`.
- Emotion backend/model settings and emergency fallback configuration.

### Local commands

- `./start-server.sh`: creates/uses `.venv`, installs requirements, and starts the backend.
- `npm run dev`: root development orchestration for backend/frontend services.
- `npm --prefix backend run dev`: backend API and recognition worker development entrypoint.
- Frontend build: run the scripts defined in `frontend/react/package.json`.

### Startup sequence

1. Load `.env` values.
2. Connect to MongoDB and create indexes.
3. Construct the engine, profile database, attendance tracker, authentication manager, camera manager, and recognition runtime.
4. Load profiles and models.
5. Start FastAPI and serve the built React application.
6. Workers poll desired camera state and start/stop per-camera processing loops.

The application standardizes timestamps through `backend/time_utils.py` using `Asia/Kolkata`; frontend formatting uses the corresponding helper in `frontend/react/src/lib/time.js`.

## 13. Logs, Snapshots, and Generated Artifacts

Application and worker logs are written under `logs/` and may also be written to `server.log`. Face snapshots are stored under `backend/face_snapshots/` and referenced by Mongo records or API snapshot routes. CSV/PDF report generation uses temporary files or response streams. Python `__pycache__` files and runtime logs are generated artifacts and are not implementation modules.

Operational review should use structured service logs, camera status, worker heartbeat/state, Mongo record timestamps, and snapshot references together. A log line alone is not proof that a person was correctly identified or that attendance was written.

## 14. Confirmed Issues and Evidence Register

The following findings are supported by repository source, existing project reports, or supplied runtime logs. They describe current behavior; they are not claims that every deployment experiences each condition.

| Finding | Area | Evidence | Impact | Severity | Status |
|---|---|---|---|---|---|
| Small face crops fail embedding extraction | Recognition | Runtime logs show crops such as `(0, 0, 32, 32)` and `backend/ai_engine.py` enforces minimum identity face sizes | Candidate cannot be embedded or reliably identified | High | Confirmed |
| Recognition candidates below threshold are rejected | Recognition | `ai_engine.py` threshold decision path and supplied `NOT_RECOGNIZED` logs | A visually plausible face may not produce attendance | Medium | Confirmed behavior; tuning requires labelled ground truth |
| RTSP setup can fail with `453 Not Enough Bandwidth` | Camera transport | Supplied OpenCV/FFmpeg logs for `profile1` | Worker receives zero frames and retries/fails to open camera | High | Confirmed for reported camera/session |
| Stream availability depends on valid profile/transport configuration | Cameras | RTSP URL is passed to OpenCV; camera firmware determines profile paths | Main/sub-stream mismatch or unsupported profile can produce black/unavailable stream | High | Confirmed dependency; exact URL requires live camera validation |
| Recognition and attendance are separate decisions | Attendance | `AttendanceTracker` applies a strict confidence floor after recognition | A candidate can appear matched/reviewed but not be written to attendance | High | Confirmed behavior |
| Emotion model fallback can produce non-model output | Emotion | `emotion_pipeline.py` exposes model-loaded and fallback state; emergency heuristic fallback is configurable | Analytics may represent fallback estimates rather than model inference | Medium | Confirmed behavior when fallback is active |
| CORS allows all origins | Security | `backend/server.py` configures `allow_origins=["*"]` | Deployment accepts cross-origin requests broadly unless constrained upstream | High | Confirmed source configuration |
| Demo/default credentials are present in application paths | Security | `backend/server.py` includes an `admin123` credential payload and `LoginPage.jsx` includes demo login entries | Unsafe if exposed unchanged in a deployed environment | High | Confirmed source configuration |
| Critical-path automated coverage is script-heavy | Testing | `scripts/testing`, `scripts/diagnostics`, and `scripts/verify` contain many executable checks, but no complete backend/frontend test suite was identified in the inspected manifests | Regression confidence depends on manual/script execution | Medium | Confirmed repository observation |
| Generated logs and bytecode are present in the worktree | Operations | `git status` showed modified logs and `backend/__pycache__` artifacts | Repository state is harder to review and package cleanly | Low | Confirmed workspace state |

### Validation-needed observations

- Whether the affected camera is using its main stream or substream must be checked against the live camera's negotiated RTSP session.
- Whether a particular student's embedding is correctly stored must be checked in MongoDB for the profile and its `view_embeddings` values.
- Whether a matched candidate was intentionally blocked by attendance deduplication, threshold floor, disabled camera state, section filtering, or worker mode requires correlating the detection, attendance event, camera runtime state, and profile metadata.
- Current live throughput, frame latency, MongoDB capacity, model startup time, and multi-camera scaling were not measured in this repository-only review.

## 15. Production Readiness Score

This is a repository-level score, not a live deployment certification. Scores use a 0-10 category rating multiplied by the stated weight. The overall result is rounded to the nearest whole number.

| Category | Weight | Score | Evidence | Production implication |
|---|---:|---:|---|---|
| Functional completeness | 20% | 8/10 | Broad API, React pages, workers, reports, camera controls, review workflow | Suitable for a controlled pilot across the implemented domains |
| Recognition and attendance reliability | 20% | 5/10 | Threshold/gap logic, quality checks, consensus, strict attendance floor; reported crop and RTSP failures | Requires camera-specific validation and labelled accuracy testing before unattended operation |
| Data persistence and integrity | 15% | 7/10 | Mongo managers, indexes, unique keys, attendance summaries, review TTL, session TTL | Core records have defined persistence and indexing behavior |
| Security and access control | 15% | 4/10 | Session/RBAC implementation exists, but broad CORS and demo credentials are present in source | Not suitable for unrestricted production exposure without configuration/security hardening |
| Observability and operations | 10% | 6/10 | Service logs, runtime state, worker heartbeat, camera status, snapshots, diagnostics | Operable with active monitoring and evidence correlation |
| Testing and verification | 10% | 4/10 | Numerous scripts and verification documents; limited unified automated test coverage identified | Regression and release confidence is below a mature production standard |
| Deployment and configuration readiness | 5% | 5/10 | Startup scripts, manifests, `.env.example`, Mongo requirement, React build path | Repeatable local startup exists; production deployment controls are not evidenced here |
| Performance and scalability | 5% | 4/10 | CPU InsightFace path at 1280 detection size, per-camera loops, optional model pipelines | Live multi-camera capacity and latency remain deployment-dependent |

### Overall result

**Production-readiness score: 56/100**

**Classification: Pilot-ready with production blockers.**

The score reflects a feature-complete engineering prototype suitable for controlled classroom pilots when cameras, thresholds, credentials, MongoDB, and worker health are actively monitored. It is not a certification for unattended or unrestricted production operation because live accuracy, RTSP stability, deployment security, load capacity, and comprehensive regression coverage are not established by repository inspection alone.

## 16. Remediation Tracking Categories

The issue register should be converted into release gates in this order:

- Validate each target camera's negotiated main/substream URL and transport mode.
- Run labelled face-quality and recognition tests for each classroom and threshold.
- Verify the end-to-end chain from embedding storage to candidate match to attendance write.
- Replace deployment credentials and constrain CORS through environment-specific configuration.
- Add automated tests for registration embeddings, recognition decisions, attendance floors/deduplication, snapshot persistence, review TTL, and camera state transitions.
- Measure worker latency, frame rate, reconnect behavior, MongoDB load, and multi-camera capacity.

## 17. Verification Entry Points

- Backend syntax/import check: compile the application modules using the active project Python environment.
- Frontend validation: run the scripts in `frontend/react/package.json`, including the production build.
- API checks: `scripts/testing/test_api_*.py` and `scripts/testing/test_venue_api.py`.
- Recognition/attendance checks: `scripts/testing/test_dedup_logic.py`, `scripts/diagnostics/check_webcam_attendance.py`, and `scripts/diagnostics/check_face_ids.py`.
- Emotion/activity checks: `scripts/testing/test_emotion_analytics.py`, `scripts/testing/test_activity_api.py`, and `scripts/testing/test_engagement_metrics.py`.
- System checks: `scripts/verify/verify_complete_system.py`, `scripts/verify/verify_upgraded_server.py`, and related verification scripts.
- Camera diagnostics: `scripts/debug/debug_cameras.py`, `scripts/diagnostics/check_dbs.py`, and the camera diagnostic documents under `docs/`.

These scripts are verification entrypoints, not a substitute for live environment acceptance testing.

## 18. Glossary

- **Profile**: Registered person record containing identity metadata and face embeddings.
- **Embedding**: Numeric face representation used for similarity comparison.
- **View embedding**: Embedding captured from a named registration view or angle.
- **Top candidate**: Highest-scoring registered profile for a detected face.
- **Recognition threshold**: Minimum score required by the recognition decision path.
- **Attendance floor**: Separate strict minimum applied before writing attendance.
- **Score gap**: Difference between the best and second-best candidate scores.
- **Unknown face**: Detected face not accepted as a registered profile.
- **Recognition review**: Temporary best-evidence dataset used to inspect threshold behavior.
- **Camera runtime state**: Desired and current worker state for a camera.
- **Worker heartbeat**: Periodic status indicating that a worker is alive and reporting.
- **Main stream/substream**: Camera-provided RTSP profiles with different resolution, bitrate, and processing cost.
- **Application timezone**: `Asia/Kolkata`, used for application-local timestamp handling.

## 19. Current-State Conclusion

ChronoSenseWeb has an implemented end-to-end classroom monitoring platform with a React administration surface, FastAPI services, MongoDB persistence, computer-vision workers, camera controls, reporting, and recognition review tooling. The current repository supports controlled pilot operation. The evidence-based score is limited primarily by unresolved live camera/recognition validation, deployment security configuration, performance measurement, and test-suite maturity rather than by absence of the major product subsystems.
