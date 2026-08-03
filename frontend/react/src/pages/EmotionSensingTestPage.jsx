import { useEffect, useMemo, useState } from "react";
import { AppShell } from "../components/AppShell";
import {
  getEmotionRoomStatus,
  getCurrentDetections,
  getCameras,
  startEmotionRecognition,
  startAllEmotionRecognition,
  stopAllEmotionRecognition,
} from "../lib/admin";
import { formatDateTimeInAppTimezone } from "../lib/time";

function formatTimestamp(value) {
  return formatDateTimeInAppTimezone(value, "No live data yet");
}

function getFaceEmotionState(face) {
  const rawConfidence = Number(face?.raw_confidence || 0);
  const smoothedConfidence = Number(face?.smoothed_confidence || 0);
  const emotionConfidence = Number(face?.emotion_confidence || 0);
  const hasReliableEmotion = Boolean(
    face?.emotion_available ||
    rawConfidence > 0 ||
    smoothedConfidence > 0 ||
    emotionConfidence > 0
  );

  if (!hasReliableEmotion) {
    return {
      available: false,
      emotion: "No reliable emotion yet",
      derived: "Unavailable",
      educational: "Unavailable",
      confidenceLabel: "Unavailable"
    };
  }

  return {
    available: true,
    emotion: face?.smoothed_emotion && face.smoothed_emotion !== "LowSignal"
      ? face.smoothed_emotion
      : (face?.emotion || face?.raw_emotion || "Unknown"),
    derived: face?.derived_emotion || "Unavailable",
    educational: face?.educational_state || "Unavailable",
    confidenceLabel: `${Math.round(emotionConfidence * 100)}%`
  };
}

function buildEmotionBreakdown(details) {
  return Object.entries(
    details?.educational_state_percentages ||
      details?.derived_emotion_percentages ||
      details?.emotion_percentages ||
      {}
  );
}

function formatEmotionScores(face) {
  const scores = face?.emotion_scores || face?.all_emotions || face?.raw_scores || {};
  const entries = Object.entries(scores)
    .filter(([, value]) => Number(value || 0) > 0)
    .sort((a, b) => Number(b[1] || 0) - Number(a[1] || 0));

  if (!entries.length) {
    return "No per-emotion scores yet";
  }

  return entries
    .map(([label, value]) => `${label}: ${Math.round(Number(value || 0) * 100)}%`)
    .join(", ");
}

function getNormalizedBbox(face) {
  const bbox = Array.isArray(face?.bbox) ? face.bbox : [];
  if (bbox.length < 4) {
    return null;
  }

  const [x, y, w, h] = bbox.map((value) => Number(value || 0));
  if (w <= 0 || h <= 0) {
    return null;
  }

  return { x, y, w, h };
}

export function EmotionSensingTestPage() {
  const [availableCameras, setAvailableCameras] = useState([]);
  const [selectedCameraId, setSelectedCameraId] = useState("");
  const [detections, setDetections] = useState(null);
  const [roomEmotion, setRoomEmotion] = useState(null);
  const [debugInfo, setDebugInfo] = useState(null);
  const [loading, setLoading] = useState(false);
  const [cameraLoading, setCameraLoading] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [allCameraLoading, setAllCameraLoading] = useState(false);
  const [roomStatuses, setRoomStatuses] = useState([]);
  const [message, setMessage] = useState("");
  const [cameraOpen, setCameraOpen] = useState(false);
  const [cameraReady, setCameraReady] = useState(false);
  const [cameraError, setCameraError] = useState("");
  const [streamSrc, setStreamSrc] = useState("");

  const emotionBreakdown = useMemo(
    () => buildEmotionBreakdown(roomEmotion),
    [roomEmotion]
  );

  const liveFaces = detections?.all_faces || [
    ...(detections?.known_faces || []),
    ...(detections?.unknown_faces || []),
  ];
  const recognizedFaces = detections?.known_faces || [];
  const selectedCamera = availableCameras.find((camera) => String(camera.id) === String(selectedCameraId)) || null;

  useEffect(() => {
    loadConfiguredCameras();
    loadRoomStatuses();

    return () => {
      stopBrowserCamera();
    };
  }, []);

  useEffect(() => {
    loadRoomStatuses();
    const intervalId = window.setInterval(() => {
      loadRoomStatuses();
    }, 5000);

    return () => window.clearInterval(intervalId);
  }, []);

  async function loadConfiguredCameras() {
    try {
      setLoading(true);
      const data = await getCameras();
      const nextCameras = (data?.cameras || []).filter(
        (camera) => camera?.enabled !== false && String(camera?.type || "").toLowerCase() !== "local_webcam"
      );
      setAvailableCameras(nextCameras);
      if (nextCameras.length && !selectedCameraId) {
        setSelectedCameraId(String(nextCameras[0].id));
      }
    } catch (error) {
      setMessage(error?.message || "Unable to load configured cameras.");
    } finally {
      setLoading(false);
    }
  }

  async function loadRoomStatuses() {
    try {
      const result = await getEmotionRoomStatus();
      setRoomStatuses(result?.rooms || []);
    } catch (_error) {
      setRoomStatuses([]);
    }
  }

  function stopBrowserCamera() {
    setCameraOpen(false);
    setCameraReady(false);
    setStreamSrc("");
  }

  async function openBrowserCamera() {
    setCameraLoading(true);
    setCameraError("");
    setMessage("");

    try {
      stopBrowserCamera();
      if (!selectedCameraId) {
        throw new Error("Select a camera first.");
      }
      await startEmotionRecognition(Number(selectedCameraId));
      const previewParams = new URLSearchParams({
        ts: String(Date.now()),
        roi: "emotion",
      });
      setStreamSrc(`/api/cameras/${selectedCameraId}/stream?${previewParams.toString()}`);
      setCameraReady(true);
      setCameraOpen(true);
      setMessage(`Started recognition for ${selectedCamera?.name || "selected camera"}.`);
    } catch (error) {
      setCameraError(error?.message || "Unable to open CCTV camera.");
    } finally {
      setCameraLoading(false);
    }
  }

  async function startAllCctvCameras() {
    setAllCameraLoading(true);
    setCameraError("");
    try {
      const result = await startAllEmotionRecognition();
      const startedCount = Number(result?.started_count || 0);
      const failedCount = Number(result?.failed_count || 0);
      setMessage(
        failedCount > 0
          ? `Started ${startedCount} CCTV cameras for emotion sensing. ${failedCount} failed.`
          : `Started ${startedCount} CCTV cameras for emotion sensing.`
      );
    } catch (error) {
      setCameraError(error?.message || "Unable to start all CCTV cameras.");
    } finally {
      setAllCameraLoading(false);
    }
  }

  async function stopAllCctvCameras() {
    setAllCameraLoading(true);
    setCameraError("");
    try {
      const result = await stopAllEmotionRecognition();
      setMessage(`Stopped ${Number(result?.stopped_count || 0)} CCTV cameras.`);
    } catch (error) {
      setCameraError(error?.message || "Unable to stop all CCTV cameras.");
    } finally {
      setAllCameraLoading(false);
    }
  }

  async function captureAndAnalyzeFrame() {
    if (!selectedCameraId) {
      return;
    }
    try {
      setAnalyzing(true);
      const result = await getCurrentDetections(Number(selectedCameraId));
      const nextData = result?.data || {};
      const allFaces = [
        ...(nextData.all_faces || []),
        ...((nextData.all_faces || []).length ? [] : (nextData.known_faces || [])),
        ...((nextData.all_faces || []).length ? [] : (nextData.unknown_faces || [])),
      ];
      const emotionCounts = allFaces.reduce((accumulator, face) => {
        const label = face?.smoothed_emotion && face.smoothed_emotion !== "LowSignal"
          ? face.smoothed_emotion
          : (face?.emotion || face?.raw_emotion || "");
        if (!label) {
          return accumulator;
        }
        accumulator[label] = (accumulator[label] || 0) + 1;
        return accumulator;
      }, {});
      const dominantEmotion = Object.entries(emotionCounts)
        .sort((left, right) => Number(right[1] || 0) - Number(left[1] || 0))[0]?.[0] || null;

      setDetections({
        ...nextData,
        all_faces: allFaces,
      });
      setRoomEmotion({
        dominant_emotion: dominantEmotion,
        dominant_derived_emotion: allFaces[0]?.derived_emotion || null,
        dominant_educational_state: allFaces[0]?.educational_state || null,
        recognized_people_count: Number(nextData.known_faces_count || 0),
        emotion_percentages: emotionCounts,
        derived_emotion_percentages: {},
        educational_state_percentages: {},
      });
      setDebugInfo((current) => ({
        ...(current || {}),
        frame_width: 0,
        frame_height: 0,
        prepared_frame_width: 0,
        prepared_frame_height: 0,
        raw_face_source: "runtime_detections",
        pipeline_detection_count: allFaces.length,
        known_face_count: nextData.known_faces_count || 0,
        unknown_face_count: nextData.unknown_faces_count || 0,
      }));
      setMessage("");
    } catch (error) {
      setMessage(error.message || "Unable to load CCTV detections.");
    } finally {
      setAnalyzing(false);
    }
  }

  useEffect(() => {
    if (!cameraOpen || !cameraReady) {
      return;
    }

    captureAndAnalyzeFrame();
    const intervalId = window.setInterval(() => {
      captureAndAnalyzeFrame();
    }, 1600);

    return () => window.clearInterval(intervalId);
  }, [cameraOpen, cameraReady, selectedCameraId]);
  const activeBrowserCameraLabel = selectedCamera?.name || "Selected CCTV camera";

  return (
    <AppShell
      title="Emotion Sensing Test"
      subtitle="Single-camera CCTV emotion testing for the selected room using the live backend recognition pipeline."
      eyebrow="Emotions"
      breadcrumbs={[
        { label: "Emotions", to: "/emotions/live" },
        { label: "Emotion Sensing Test" }
      ]}
    >
      {message ? <p className="inline-note">{message}</p> : null}

      <section className="panel emotion-test-panel">
        <div className="section-header">
          <div>
            <h3>CCTV camera control</h3>
            <p>Select the ChronoSense room camera below. Local webcam input is disabled for the emotion sensing module.</p>
          </div>
          <div className="section-actions">
            <button className="secondary-button" onClick={loadConfiguredCameras} type="button">
              Refresh cameras
            </button>
          </div>
        </div>

        <div className="emotion-test-toolbar">
          <label className="filter-field emotion-test-select">
            <span>Camera scope</span>
            <select disabled={loading || !availableCameras.length} onChange={(event) => setSelectedCameraId(event.target.value)} value={selectedCameraId}>
              {!availableCameras.length ? <option value="">No configured cameras available</option> : null}
              {availableCameras.map((camera) => (
                <option key={camera.id} value={String(camera.id)}>
                  {`${camera.name || `Camera ${camera.id}`} · uses CCTV stream`}
                </option>
              ))}
            </select>
          </label>

          <button className="primary-button" disabled={cameraLoading} onClick={openBrowserCamera} type="button">
            {cameraLoading ? "Starting..." : "Start recognizing"}
          </button>

          <button className="secondary-button" disabled={allCameraLoading} onClick={startAllCctvCameras} type="button">
            {allCameraLoading ? "Starting all..." : "Start all cameras"}
          </button>

          <button className="danger-button" disabled={!cameraOpen} onClick={stopBrowserCamera} type="button">
            Stop recognizing
          </button>

          <button className="danger-button" disabled={allCameraLoading} onClick={stopAllCctvCameras} type="button">
            {allCameraLoading ? "Stopping all..." : "Stop all cameras"}
          </button>

          <button className="secondary-button" disabled={!cameraOpen} onClick={captureAndAnalyzeFrame} type="button">
            {analyzing ? "Analyzing..." : "Analyze now"}
          </button>
        </div>
        {cameraError ? <p className="inline-note">{cameraError}</p> : null}
      </section>

      <section className="card-grid">
        <article className="metric-card">
          <span>Selected scope camera</span>
          <strong>{selectedCamera?.name || "No ChronoSense camera selected"}</strong>
          <p>Emotion test results are grouped under this configured camera scope.</p>
        </article>
        <article className="metric-card">
          <span>Input camera</span>
          <strong>{activeBrowserCameraLabel}</strong>
          <p>This is the selected CCTV camera feed from the backend stream.</p>
        </article>
        <article className="metric-card">
          <span>Camera state</span>
          <strong>{cameraOpen ? "Open" : "Closed"}</strong>
              <p>{cameraReady ? "Preview is live and frames can be analyzed." : "Start recognition to begin the CCTV preview."}</p>
        </article>
        <article className="metric-card">
          <span>Visible faces</span>
          <strong>{detections?.total_faces || 0}</strong>
          <p>{detections?.known_faces_count || 0} known, {detections?.unknown_faces_count || 0} unknown.</p>
        </article>
        <article className="metric-card">
          <span>Room emotion</span>
          <strong>{roomEmotion?.dominant_emotion || roomEmotion?.dominant_educational_state || roomEmotion?.dominant_derived_emotion || "-"}</strong>
          <p>Last live update: {formatTimestamp(detections?.updated_at)}</p>
        </article>
      </section>

      <section className="emotion-test-layout">
        <article className="panel">
          <div className="section-header">
            <div>
              <h3>CCTV preview</h3>
              <p>Live preview from the selected CCTV camera stream.</p>
            </div>
          </div>

          <div className="camera-stream-frame-react emotion-test-stream-frame">
            {cameraOpen && streamSrc ? (
              <img
                alt={selectedCamera ? `${selectedCamera.name} live stream` : "CCTV live stream"}
                className="camera-stream-image-react"
                onError={() => setMessage("Unable to open this CCTV stream right now.")}
                src={streamSrc}
              />
            ) : (
              <div className="camera-stream-empty-react">
                <strong>No CCTV stream running</strong>
                <span>Start recognition to open the selected CCTV stream.</span>
              </div>
            )}
          </div>
        </article>

        <article className="panel">
          <div className="section-header">
            <div>
              <h3>Current emotion summary</h3>
              <p>Aggregated emotion signal from the latest selected CCTV frame.</p>
            </div>
          </div>

          <div className="stack-list">
            <div className="list-card static">
              <div>
                <strong>Dominant emotion</strong>
                <p>{roomEmotion?.dominant_emotion || "No reliable emotion summary yet."}</p>
              </div>
            </div>
            <div className="list-card static">
              <div>
                <strong>Derived state</strong>
                <p>{roomEmotion?.dominant_derived_emotion || "No derived state yet."}</p>
              </div>
            </div>
            <div className="list-card static">
              <div>
                <strong>Educational state</strong>
                <p>{roomEmotion?.dominant_educational_state || "No educational state yet."}</p>
              </div>
            </div>
            <div className="list-card static">
              <div>
                <strong>Detected people</strong>
                <p>{roomEmotion?.recognized_people_count ?? 0} faces contributed emotion data in this frame.</p>
              </div>
            </div>
          </div>

          <div className="detail-card emotion-breakdown-card">
            <div className="subsection-head">
              <h4>Breakdown</h4>
              <span>{emotionBreakdown.length} signals</span>
            </div>
            {emotionBreakdown.length ? (
              <ul className="compact-stat-list">
                {emotionBreakdown.map(([label, value]) => (
                  <li key={label}>{label}: {value}%</li>
                ))}
              </ul>
            ) : (
              <div className="table-empty">No room emotion breakdown available yet.</div>
            )}
          </div>
        </article>
      </section>

      <section className="panel">
          <div className="section-header">
            <div>
              <h3>Frame debug</h3>
              <p>Live backend debug for the latest CCTV frame so we can see which stage is failing.</p>
            </div>
          </div>

        <div className="stack-list">
          <div className="detail-card">
            <div className="subsection-head">
              <h4>Backend pipeline</h4>
              <span>{debugInfo?.server_emotion_model_loaded ? "Model loaded" : "Model not loaded"}</span>
            </div>
            <p>Emotion backend: {debugInfo?.server_emotion_backend || "-"}</p>
            <p>Emotion model: {debugInfo?.server_emotion_model || "-"}</p>
            <p>Emotion version: {debugInfo?.server_emotion_version || "-"}</p>
            <p>Model loaded in API server: {String(Boolean(debugInfo?.server_emotion_model_loaded))}</p>
            <p>Model last error: {debugInfo?.server_emotion_last_error || "-"}</p>
          </div>

          <div className="detail-card">
            <div className="subsection-head">
              <h4>Detection counters</h4>
              <span>{debugInfo ? "Latest frame" : "Waiting"}</span>
            </div>
            <p>Frame size: {debugInfo ? `${debugInfo.frame_width}x${debugInfo.frame_height}` : "-"}</p>
            <p>Prepared frame size: {debugInfo?.prepared_frame_width ? `${debugInfo.prepared_frame_width}x${debugInfo.prepared_frame_height}` : "-"}</p>
            <p>Upload size: {debugInfo?.payload_bytes ?? "-"} bytes</p>
            <p>Raw face source: {debugInfo?.raw_face_source || "-"}</p>
            <p>Center fallback used: {String(Boolean(debugInfo?.center_person_fallback_used))}</p>
            <p>Raw face detector count: {debugInfo?.raw_face_count ?? "-"}</p>
            <p>Pipeline detection count: {debugInfo?.pipeline_detection_count ?? "-"}</p>
            <p>Known face count: {debugInfo?.known_face_count ?? "-"}</p>
            <p>Unknown face count: {debugInfo?.unknown_face_count ?? "-"}</p>
            <p>Emotion processed count: {debugInfo?.emotion_processed_count ?? "-"}</p>
            <p>Fallback emotion count: {debugInfo?.fallback_emotion_count ?? "-"}</p>
            <p>Low-signal count: {debugInfo?.low_signal_count ?? "-"}</p>
          </div>

          <div className="detail-card">
            <div className="subsection-head">
              <h4>Runtime notes</h4>
              <span>Diagnostics</span>
            </div>
            <p>Fallback unknown-face path used: {String(Boolean(debugInfo?.using_fallback_unknown_face_path))}</p>
            <p>Last server emotion error: {debugInfo?.server_last_emotion_error || "-"}</p>
            <p>Last server emotion detection: {formatTimestamp(debugInfo?.server_last_emotion_detection_at)}</p>
            <p>Unavailable reasons: {(debugInfo?.emotion_unavailable_reasons || []).length ? debugInfo.emotion_unavailable_reasons.join(", ") : "-"}</p>
          </div>
        </div>
      </section>

      <section className="panel">
          <div className="section-header">
            <div>
              <h3>Real-time attendance</h3>
            <p>Recognized people in the current CCTV frame, shown as live present status.</p>
          </div>
        </div>

        <div className="stack-list">
          {recognizedFaces.length ? recognizedFaces.map((face) => (
            <div className="detail-card" key={`attendance-${face.profile_id}-${face.name}`}>
              <div className="subsection-head">
                <h4>{face.name}</h4>
                <span>Present now</span>
              </div>
              <p>Recognition confidence: {Math.round(Number(face.confidence || 0) * 100)}%</p>
              <p>Live emotion: {getFaceEmotionState(face).emotion}</p>
              <p>Bounding box: {Array.isArray(face.bbox) ? face.bbox.map((value) => Math.round(Number(value || 0))).join(", ") : "-"}</p>
            </div>
          )) : (
            <div className="table-empty">No recognized people are marked present in the current frame yet.</div>
          )}
        </div>
      </section>

      <section className="panel">
          <div className="section-header">
            <div>
              <h3>Live face emotions</h3>
            <p>These are the current emotion results from the selected CCTV camera, whether the face is recognized or unknown.</p>
          </div>
        </div>

        <div className="stack-list">
          {liveFaces.length ? liveFaces.map((face, index) => (
            (() => {
              const emotionState = getFaceEmotionState(face);
              const faceKey = face.profile_id
                ? `${face.profile_id}-${face.name}`
                : `${face.name || "unknown"}-${index}`;

              return (
                <div className="detail-card" key={faceKey}>
                  <div className="subsection-head">
                    <h4>{face.name || `Unknown face ${index + 1}`}</h4>
                    <span>
                      {face.profile_id != null
                        ? `${Math.round(Number(face.confidence || 0) * 100)}% match`
                        : "Unrecognized"}
                    </span>
                  </div>
                  <p>Emotion: {emotionState.emotion}</p>
                  <p>Derived state: {emotionState.derived}</p>
                  <p>Educational state: {emotionState.educational}</p>
                  <p>Emotion confidence: {emotionState.confidenceLabel}</p>
                  <p>Emotion scores: {formatEmotionScores(face)}</p>
                  {!emotionState.available && face?.emotion_unavailable_reason ? (
                    <p>Pipeline status: {face.emotion_unavailable_reason}</p>
                  ) : null}
                </div>
              );
            })()
          )) : (
            <div className="table-empty">No visible faces are available from the selected CCTV camera yet.</div>
          )}
        </div>
      </section>

      <section className="panel">
        <div className="section-header">
          <div>
            <h3>All room emotion status</h3>
            <p>Use this board to verify whether every enabled room is actually producing live emotion detections on Monday, July 27, 2026.</p>
          </div>
        </div>

        <div className="stack-list">
          {roomStatuses.length ? roomStatuses.map((room) => (
            <div className="detail-card" key={`room-status-${room.camera_id}`}>
              <div className="subsection-head">
                <h4>{room.camera_name || `Camera ${room.camera_id}`}</h4>
                <span>{room.is_running ? "Running" : "Stopped"}</span>
              </div>
              <p>Status: {room.status || "-"}</p>
              <p>Last update: {formatTimestamp(room.updated_at)}</p>
              <p>Last emotion detection: {formatTimestamp(room.last_emotion_detection_at)}</p>
              <p>Total faces: {Number(room.total_faces || 0)} | Known: {Number(room.known_faces_count || 0)} | Unknown: {Number(room.unknown_faces_count || 0)}</p>
              <p>Dominant live emotion: {room.dominant_emotion || "No live emotion yet"}</p>
              <p>Frames processed: {Number(room.frames_processed || 0)} | FPS: {Number(room.fps || 0).toFixed(1)}</p>
              <p>Emotion backend: {room.emotion_backend || "-"} | Model loaded: {String(Boolean(room.emotion_model_loaded))}</p>
              <p>Runtime note: {room.message || room.emotion_detection_error || "-"}</p>
              <p>
                Emotion counts: {Object.keys(room.emotion_counts || {}).length
                  ? Object.entries(room.emotion_counts || {}).map(([label, count]) => `${label}: ${count}`).join(", ")
                  : "No face-level emotion signals yet"}
              </p>
            </div>
          )) : (
            <div className="table-empty">No room status data is available yet.</div>
          )}
        </div>
      </section>
    </AppShell>
  );
}
