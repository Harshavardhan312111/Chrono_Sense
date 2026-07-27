import { useEffect, useMemo, useState } from "react";
import { AppShell } from "../components/AppShell";
import { getCameras, getCameraStatus } from "../lib/admin";

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
    if (selectedCamera) {
      setMessage(`Stopped ${selectedCamera.name}.`);
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
            </div>
          </div>

          {message ? <p className="inline-note">{message}</p> : null}

          <div className="camera-stream-frame-react">
            {streamSrc ? (
              <img
                alt={selectedCamera ? `${selectedCamera.name} live stream` : "Camera live stream"}
                className="camera-stream-image-react"
                onError={() => setMessage("Unable to open this stream right now.")}
                src={streamSrc}
              />
            ) : (
              <div className="camera-stream-empty-react">
                <strong>No live stream running</strong>
                <span>Select a camera and click Start stream.</span>
              </div>
            )}
          </div>

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
