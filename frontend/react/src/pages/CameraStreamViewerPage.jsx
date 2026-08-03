import { useEffect, useMemo, useState } from "react";
import { AppShell } from "../components/AppShell";
import { getCameras, getCameraFaceDebug, getCameraStatus } from "../lib/admin";

function getCameraConnectionLabel(camera) {
  if (!camera) {
    return "Not connected";
  }

  if (camera.status) {
    return camera.status;
  }

  return camera.enabled ? "enabled" : "disabled";
}

function normalizeCameraSource(source) {
  if (!source) {
    return "";
  }

  return String(source)
    .trim()
    .replace(/\/\/[^/]*@/, "//")
    .replace(/\/+$/, "")
    .toLowerCase();
}

function getUniqueEnabledCameras(cameraList) {
  const seen = new Set();
  const unique = [];

  for (const camera of cameraList || []) {
    if (!camera?.enabled) {
      continue;
    }

    const key = `${(camera.name || "").trim().toLowerCase()}|${normalizeCameraSource(camera.source)}|${(camera.type || "").trim().toLowerCase()}`;
    if (seen.has(key)) {
      continue;
    }

    seen.add(key);
    unique.push(camera);
  }

  return unique;
}

export function CameraStreamViewerPage() {
  const [cameras, setCameras] = useState([]);
  const [selectedCamera, setSelectedCamera] = useState(null);
  const [streamSrc, setStreamSrc] = useState("");
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [statusLoading, setStatusLoading] = useState(false);
  const [message, setMessage] = useState("");
  const [cameraStatus, setCameraStatus] = useState(null);
  const [faceDebugLoading, setFaceDebugLoading] = useState(false);
  const [faceDebug, setFaceDebug] = useState(null);

  useEffect(() => {
    loadCameras();
  }, []);

  async function loadCameras() {
    setLoading(true);
    setMessage("");

    try {
      const data = await getCameras();
      const nextCameras = getUniqueEnabledCameras(data?.data || data?.cameras || []);
      setCameras(nextCameras);

      if (!nextCameras.length) {
        setSelectedCamera(null);
        setStreamSrc("");
        setMessage("No cameras found.");
        return;
      }

      setSelectedCamera((current) => {
        if (current) {
          return nextCameras.find((camera) => camera.id === current.id) || nextCameras[0];
        }

        return nextCameras[0];
      });
    } catch (error) {
      setCameras([]);
      setSelectedCamera(null);
      setStreamSrc("");
      setMessage(error.message || "Unable to load cameras.");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }

  function handleSelectCamera(camera) {
    setSelectedCamera(camera);
    setStreamSrc("");
    setCameraStatus(null);
    setFaceDebug(null);
    setMessage(`Selected camera: ${camera.name}`);
    refreshSelectedCameraStatus(camera.id);
  }

  async function refreshSelectedCameraStatus(cameraId = selectedCamera?.id) {
    if (!cameraId) {
      return;
    }

    setStatusLoading(true);
    try {
      const data = await getCameraStatus(cameraId);
      setCameraStatus(data);

      if (data?.connection_status === "disconnected" && data?.error) {
        setMessage(data.error);
      }
    } catch (error) {
      setCameraStatus(null);
      setMessage(error.message || "Unable to check camera status.");
    } finally {
      setStatusLoading(false);
    }
  }

  function handleStartStream() {
    if (!selectedCamera) {
      setMessage("Select a camera first.");
      return;
    }

    setStreamSrc(`/api/cameras/${selectedCamera.id}/stream?t=${Date.now()}`);
    setMessage(`Streaming ${selectedCamera.name}.`);
    refreshSelectedCameraStatus(selectedCamera.id);
  }

  function handleStopStream() {
    setStreamSrc("");
    setFaceDebug(null);
    if (selectedCamera) {
      setMessage(`Stopped ${selectedCamera.name}.`);
    }
  }

  async function handleCaptureFaces() {
    if (!selectedCamera) {
      setMessage("Select a camera first.");
      return;
    }

    setFaceDebugLoading(true);
    try {
      const data = await getCameraFaceDebug(selectedCamera.id);
      setFaceDebug(data);
      setMessage(
        data?.face_count
          ? `Captured ${data.face_count} face ${data.face_count === 1 ? "box" : "boxes"} from ${selectedCamera.name}.`
          : `No faces detected in ${selectedCamera.name}.`
      );
    } catch (error) {
      setFaceDebug(null);
      setMessage(error.message || "Unable to capture face boxes.");
    } finally {
      setFaceDebugLoading(false);
    }
  }

  function handleRefresh() {
    setRefreshing(true);
    loadCameras();
  }

  const selectedConnection = useMemo(
    () => cameraStatus?.connection_status || getCameraConnectionLabel(selectedCamera),
    [cameraStatus, selectedCamera]
  );

  return (
    <AppShell title="Camera Stream Viewer" subtitle="Standalone live camera preview route.">
      <section className="camera-stream-layout-react">
        <aside className="panel camera-stream-sidebar-react">
          <div className="section-header">
            <div>
              <h3>Cameras</h3>
              <p>Select one source to preview its live stream.</p>
            </div>
            <button className="secondary-button" onClick={handleRefresh} type="button">
              {refreshing ? "Refreshing..." : "Refresh"}
            </button>
          </div>

          <div className="camera-stream-list-react">
            {loading ? <div className="table-empty">Loading cameras...</div> : null}
            {!loading && !cameras.length ? <div className="table-empty">No cameras available.</div> : null}
            {!loading
              ? cameras.map((camera) => (
                  <button
                    className={`camera-stream-list-item-react ${selectedCamera?.id === camera.id ? "active" : ""}`}
                    key={camera.id}
                    onClick={() => handleSelectCamera(camera)}
                    type="button"
                  >
                    <strong>{camera.name}</strong>
                    <span>{camera.enabled ? "Enabled" : "Disabled"}</span>
                  </button>
                ))
              : null}
          </div>
        </aside>

        <section className="panel camera-stream-main-react">
          <div className="section-header">
            <div>
              <h3>{selectedCamera ? selectedCamera.name : "Select a camera"}</h3>
              <p>Live MJPEG preview using the existing backend stream endpoint.</p>
            </div>
            <div className="section-actions">
              <button className="primary-button" onClick={handleStartStream} type="button">
                Start stream
              </button>
              <button className="secondary-button" onClick={handleStopStream} type="button">
                Stop stream
              </button>
              <button className="secondary-button" onClick={() => refreshSelectedCameraStatus()} type="button">
                {statusLoading ? "Checking..." : "Check status"}
              </button>
              <button className="secondary-button" onClick={handleCaptureFaces} type="button">
                {faceDebugLoading ? "Capturing..." : "Capture faces"}
              </button>
            </div>
          </div>

          {message ? <p className="inline-note">{message}</p> : null}

          <div className="camera-stream-frame-react">
            {streamSrc ? (
              <div style={{ position: "relative" }}>
                <img
                  alt={selectedCamera ? `${selectedCamera.name} live stream` : "Camera live stream"}
                  className="camera-stream-image-react"
                  onError={() => setMessage("Unable to open this stream right now.")}
                  src={streamSrc}
                />
                {faceDebug?.faces?.map((face) => {
                  const [x, y, width, height] = face.bbox || [];
                  const frameWidth = faceDebug?.frame_size?.width || 960;
                  const frameHeight = faceDebug?.frame_size?.height || 540;
                  return (
                    <div
                      key={face.id}
                      style={{
                        position: "absolute",
                        left: `${(x / frameWidth) * 100}%`,
                        top: `${(y / frameHeight) * 100}%`,
                        width: `${(width / frameWidth) * 100}%`,
                        height: `${(height / frameHeight) * 100}%`,
                        border: "2px solid #34c759",
                        boxSizing: "border-box",
                        pointerEvents: "none"
                      }}
                    >
                      <span
                        style={{
                          position: "absolute",
                          top: "-22px",
                          left: "0",
                          background: "#34c759",
                          color: "#0e1116",
                          fontSize: "12px",
                          fontWeight: 700,
                          padding: "2px 6px"
                        }}
                      >
                        {face.label}
                      </span>
                    </div>
                  );
                })}
              </div>
            ) : (
              <div className="camera-stream-empty-react">
                <strong>No live stream running</strong>
                <span>Select a camera and click Start stream.</span>
              </div>
            )}
          </div>

          {faceDebug ? (
            <section className="panel" style={{ marginTop: "1rem" }}>
              <div className="section-header">
                <div>
                  <h3>Face Debug</h3>
                  <p>Bounding boxes and cropped face captures from the latest debug snapshot.</p>
                </div>
              </div>

              {!faceDebug.faces?.length ? <div className="table-empty">No faces detected in the latest capture.</div> : null}

              {faceDebug.faces?.length ? (
                <div
                  style={{
                    display: "grid",
                    gap: "1rem",
                    gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))"
                  }}
                >
                  {faceDebug.faces.map((face) => (
                    <article
                      key={face.id}
                      style={{
                        border: "1px solid rgba(255,255,255,0.12)",
                        borderRadius: "12px",
                        padding: "0.75rem",
                        background: "rgba(255,255,255,0.03)"
                      }}
                    >
                      {face.crop_base64 ? (
                        <img
                          alt={`${face.label} crop`}
                          src={`data:image/jpeg;base64,${face.crop_base64}`}
                          style={{
                            width: "100%",
                            aspectRatio: "1 / 1",
                            objectFit: "cover",
                            borderRadius: "8px",
                            marginBottom: "0.75rem"
                          }}
                        />
                      ) : (
                        <div className="table-empty">Crop unavailable</div>
                      )}
                      <strong>{face.label}</strong>
                      <p style={{ margin: "0.35rem 0 0" }}>
                        Box: {face.bbox?.join(", ")}
                      </p>
                      <p style={{ margin: "0.2rem 0 0" }}>
                        Size: {face.size?.width} x {face.size?.height}
                      </p>
                    </article>
                  ))}
                </div>
              ) : null}
            </section>
          ) : null}

          <div className="camera-stream-details-grid-react">
            <article className="metric-card">
              <span>Status</span>
              <strong>{selectedConnection}</strong>
              <p>{cameraStatus?.error || (selectedCamera?.enabled ? "Source is enabled." : "Source is disabled.")}</p>
            </article>
            <article className="metric-card">
              <span>Camera ID</span>
              <strong>{selectedCamera ? `#${selectedCamera.id}` : "-"}</strong>
              <p>Database camera identifier.</p>
            </article>
            <article className="metric-card">
              <span>Type</span>
              <strong>{selectedCamera?.type || "-"}</strong>
              <p>Configured source type.</p>
            </article>
            <article className="metric-card">
              <span>Source</span>
              <strong className="camera-stream-source-react">{selectedCamera?.source || "-"}</strong>
              <p>Configured camera source URL.</p>
            </article>
          </div>
        </section>
      </section>
    </AppShell>
  );
}
