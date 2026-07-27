import { useEffect, useState } from "react";
import { AppShell } from "../components/AppShell";
import { useAuth } from "../state/auth";
import {
  addCamera,
  deleteCamera,
  getCameras,
  testCameraConnection,
  updateCamera
} from "../lib/admin";
import { CAPABILITY_CAMERAS_MANAGE, hasCapability } from "../lib/rbac";

const initialForm = {
  name: "",
  type: "rtsp",
  source: "",
  wing: "",
  customWing: "",
  room_number: "",
  username: "",
  password: "",
  fps: "30",
  resolution: "1280x720"
};

function normalizeWingValue(form) {
  if (form.wing === "__new__") {
    return form.customWing.trim();
  }

  return form.wing.trim();
}

function isLocalWebcamType(type) {
  return type === "local_webcam";
}

function normalizeLocalWebcamSource(source) {
  const trimmed = String(source ?? "").trim();
  return trimmed || "0";
}

export function CameraSettingsPage() {
  const { user } = useAuth();
  const canManageCameras = hasCapability(user, CAPABILITY_CAMERAS_MANAGE);
  const isPrincipal = user?.role === "principal";
  const isManager = user?.role === "manager";
  const [form, setForm] = useState(initialForm);
  const [message, setMessage] = useState("");
  const [cameras, setCameras] = useState([]);
  const [wingOptions, setWingOptions] = useState([]);
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testingCameraId, setTestingCameraId] = useState(null);
  const [editingCameraId, setEditingCameraId] = useState(null);

  useEffect(() => {
    loadCameras();
  }, []);

  useEffect(() => {
    if (!isLocalWebcamType(form.type)) {
      return;
    }

    setForm((current) => ({
      ...current,
      source: normalizeLocalWebcamSource(current.source),
      name: current.name || "My Computer Camera",
      wing: current.wing || "Local",
      room_number: current.room_number || "USB Camera",
      username: "",
      password: ""
    }));
  }, [form.type]);

  function updateField(event) {
    const { name, value } = event.target;
    setForm((current) => ({
      ...current,
      [name]: value
    }));
  }

  async function loadCameras() {
    setLoading(true);

    try {
      const data = await getCameras();
      setCameras(data.cameras || []);
      setWingOptions(data.wings || []);
    } catch (error) {
      setCameras([]);
      setWingOptions([]);
      setMessage(error.message || "Unable to load cameras.");
    } finally {
      setLoading(false);
    }
  }

  function validateForm(requireName = true) {
    if (requireName && !isLocalWebcamType(form.type) && !form.name.trim()) {
      return "Camera name is required.";
    }

    if (!form.type.trim()) {
      return "Camera type is required.";
    }

    if (isLocalWebcamType(form.type) && !/^\d+$/.test(normalizeLocalWebcamSource(form.source))) {
      return "Local camera source must be a numeric device index like 0, 1, or 2.";
    }

    if (!isLocalWebcamType(form.type) && !form.source.trim()) {
      return "Source URL is required.";
    }

    if (!isLocalWebcamType(form.type) && !normalizeWingValue(form)) {
      return "Wing is required.";
    }

    if (!isLocalWebcamType(form.type) && !form.room_number.trim()) {
      return "Room number is required.";
    }

    if (
      !isLocalWebcamType(form.type) &&
      form.type !== "usb" &&
      !form.source.startsWith("rtsp://") &&
      !form.source.startsWith("http://") &&
      !form.source.startsWith("https://")
    ) {
      return "Source must start with rtsp://, http://, or https://.";
    }

    return "";
  }

  async function handleTestConnection() {
    const validationError = validateForm(false);

    if (validationError) {
      setMessage(validationError);
      return;
    }

    setTesting(true);
    setMessage("Testing camera connection...");

    try {
      const result = await testCameraConnection({
        type: form.type,
        source: isLocalWebcamType(form.type) ? normalizeLocalWebcamSource(form.source) : form.source.trim(),
        username: form.username.trim() || null,
        password: form.password.trim() || null
      });

      setMessage(result.message || `Connection successful. Frames read: ${result.frames_read}`);
    } catch (error) {
      setMessage(error.message || "Unable to test camera connection.");
    } finally {
      setTesting(false);
    }
  }

  async function handleSubmit(event) {
    event.preventDefault();

    const validationError = validateForm(true);

    if (validationError) {
      setMessage(validationError);
      return;
    }

    setSubmitting(true);
    setMessage(editingCameraId ? "Updating camera..." : "Adding camera...");

    const payload = {
      name: isLocalWebcamType(form.type) ? (form.name.trim() || "My Computer Camera") : form.name.trim(),
      type: form.type,
      source: isLocalWebcamType(form.type) ? normalizeLocalWebcamSource(form.source) : form.source.trim(),
      wing: isLocalWebcamType(form.type) ? "Local" : normalizeWingValue(form),
      room_number: isLocalWebcamType(form.type) ? "USB Camera" : form.room_number.trim(),
      username: isLocalWebcamType(form.type) ? null : (form.username.trim() || null),
      password: isLocalWebcamType(form.type) ? null : (form.password.trim() || null),
      fps: Number(form.fps || 30),
      resolution: form.resolution
    };

    try {
      const result = editingCameraId
        ? await updateCamera(editingCameraId, payload)
        : await addCamera(payload);

      setMessage(result.message || (editingCameraId ? "Camera updated successfully." : "Camera added successfully."));
      setForm(initialForm);
      setEditingCameraId(null);
      await loadCameras();
    } catch (error) {
      setMessage(error.message || (editingCameraId ? "Unable to update camera." : "Unable to add camera."));
    } finally {
      setSubmitting(false);
    }
  }

  function handleEdit(camera) {
    const useExistingWing = camera.wing && wingOptions.includes(camera.wing);

    setEditingCameraId(camera.id);
    setForm({
      name: camera.name || "",
      type: (camera.type || "rtsp").toLowerCase(),
      source: camera.source || "",
      wing: useExistingWing ? camera.wing : (camera.wing ? "__new__" : ""),
      customWing: useExistingWing ? "" : (camera.wing || ""),
      room_number: camera.room_number || "",
      username: camera.username || "",
      password: camera.password || "",
      fps: String(camera.fps || 30),
      resolution: camera.resolution || "1280x720"
    });
    setMessage(`Editing "${camera.name}".`);
  }

  function handleCancelEdit() {
    setEditingCameraId(null);
    setForm(initialForm);
    setMessage("Edit cancelled.");
  }

  async function handleDelete(camera) {
    const confirmed = window.confirm(`Delete camera "${camera.name}"?`);

    if (!confirmed) {
      return;
    }

    try {
      await deleteCamera(camera.id);
      setCameras((current) => current.filter((item) => item.id !== camera.id));
      setMessage(`Camera "${camera.name}" deleted.`);
    } catch (error) {
      setMessage(error.message || "Unable to delete camera.");
    }
  }

  async function handleCopySource(source) {
    if (!source) {
      setMessage("No source URL available to copy.");
      return;
    }

    try {
      await navigator.clipboard.writeText(source);
      setMessage("Camera source URL copied.");
    } catch (error) {
      setMessage("Unable to copy source URL.");
    }
  }

  async function handleTestConfiguredCamera(camera) {
    setTestingCameraId(camera.id);
    setMessage(`Testing "${camera.name}" connection...`);

    try {
      const result = await testCameraConnection({
        type: (camera.type || "rtsp").toLowerCase(),
        source: camera.source || "",
        username: camera.username || null,
        password: camera.password || null
      });

      setCameras((current) =>
        current.map((item) =>
          item.id === camera.id
            ? { ...item, status: "connected" }
            : item
        )
      );
      setMessage(result.message || `Camera "${camera.name}" connection successful.`);
    } catch (error) {
      setCameras((current) =>
        current.map((item) =>
          item.id === camera.id
            ? { ...item, status: "disconnected" }
            : item
        )
      );
      setMessage(error.message || `Unable to connect to "${camera.name}".`);
    } finally {
      setTestingCameraId(null);
    }
  }

  return (
    <AppShell
      title={isPrincipal ? "Camera Health" : isManager ? "Camera Operations" : "Camera Settings"}
      subtitle={canManageCameras
        ? isManager
          ? "Operational camera setup, connection testing, and classroom coverage management."
          : "Add, test, and manage classroom camera feeds."
        : "View classroom camera feeds and their current health status."}
    >
      {message ? <p className="inline-note">{message}</p> : null}

      <section className="camera-settings-layout">
        {canManageCameras ? (
        <form className="panel registration-form" onSubmit={handleSubmit}>
          <div className="section-header">
            <div>
              <h3>{editingCameraId ? "Edit camera" : "Add camera"}</h3>
              <p>Store wing and room number with each configured camera.</p>
            </div>
          </div>

          <div className="camera-form-grid">
            <label className="filter-field">
              <span>Camera name</span>
              <input name="name" onChange={updateField} value={form.name} />
            </label>
            <label className="filter-field">
              <span>Camera type</span>
              <select name="type" onChange={updateField} value={form.type}>
                <option value="rtsp">RTSP</option>
                <option value="mjpeg">MJPEG</option>
                <option value="hls">HLS</option>
                <option value="usb">USB</option>
                <option value="local_webcam">This Computer Camera</option>
              </select>
            </label>
            <label className="filter-field camera-form-wide">
              <span>{isLocalWebcamType(form.type) ? "Camera device index" : "Source URL"}</span>
              <input
                name="source"
                onChange={updateField}
                placeholder={isLocalWebcamType(form.type) ? "0, 1, or 2" : "rtsp://192.168.1.100:554/stream1"}
                value={form.source}
              />
            </label>
            <label className="filter-field">
              <span>Wing</span>
              <select disabled={isLocalWebcamType(form.type)} name="wing" onChange={updateField} value={form.wing}>
                <option value="">Select wing</option>
                {wingOptions.map((wing) => (
                  <option key={wing} value={wing}>{wing}</option>
                ))}
                <option value="__new__">Add new wing</option>
              </select>
            </label>
            <label className="filter-field">
              <span>Room number</span>
              <input disabled={isLocalWebcamType(form.type)} name="room_number" onChange={updateField} value={form.room_number} />
            </label>
            {form.wing === "__new__" && !isLocalWebcamType(form.type) ? (
              <label className="filter-field">
                <span>New wing</span>
                <input name="customWing" onChange={updateField} value={form.customWing} />
              </label>
            ) : null}
            <label className="filter-field">
              <span>Username</span>
              <input disabled={isLocalWebcamType(form.type)} name="username" onChange={updateField} value={form.username} />
            </label>
            <label className="filter-field">
              <span>Password</span>
              <input disabled={isLocalWebcamType(form.type)} name="password" onChange={updateField} type="password" value={form.password} />
            </label>
            <label className="filter-field">
              <span>FPS</span>
              <input name="fps" onChange={updateField} type="number" value={form.fps} />
            </label>
            <label className="filter-field">
              <span>Resolution</span>
              <select name="resolution" onChange={updateField} value={form.resolution}>
                <option value="640x480">640x480</option>
                <option value="1280x720">1280x720</option>
                <option value="1920x1080">1920x1080</option>
              </select>
            </label>
          </div>

          <div className="section-actions">
            <button className="primary-button" disabled={submitting} type="submit">
              {submitting ? (editingCameraId ? "Updating..." : "Adding...") : (editingCameraId ? "Save camera" : "Add camera")}
            </button>
            <button
              className="secondary-button"
              disabled={testing}
              onClick={handleTestConnection}
              type="button"
            >
              {testing ? "Testing..." : "Test connection"}
            </button>
            <button className="secondary-button" onClick={loadCameras} type="button">
              Refresh list
            </button>
            {editingCameraId ? (
              <button className="secondary-button" onClick={handleCancelEdit} type="button">
                Cancel edit
              </button>
            ) : null}
          </div>
        </form>
        ) : null}

        <section className="panel">
          <div className="section-header">
            <div>
              <h3>Configured cameras</h3>
              <p>Connected camera feeds available in the current system.</p>
            </div>
          </div>

          {loading ? <div className="table-empty">Loading cameras...</div> : null}

          {!loading && !cameras.length ? (
            <div className="table-empty">No cameras configured yet.</div>
          ) : null}

          {!loading && cameras.length ? (
            <div className="camera-list">
              {cameras.map((camera) => (
                <article className="detail-card camera-card" key={camera.id}>
                  <div className="subsection-head">
                    <h4>{camera.name}</h4>
                    <span className={`status-pill ${camera.status === "connected" ? "present" : "absent"}`}>
                      {camera.status || "unknown"}
                    </span>
                  </div>
                  <p><strong>ID:</strong> #{camera.id}</p>
                  <p><strong>Wing:</strong> {camera.wing || "-"}</p>
                  <p><strong>Room:</strong> {camera.room_number || "-"}</p>
                  <p><strong>Type:</strong> {(camera.type || "unknown").toUpperCase()}</p>
                  <p><strong>Resolution:</strong> {camera.resolution || "-"}</p>
                  <p><strong>FPS:</strong> {camera.fps || "-"}</p>
                  <div className="camera-card-actions">
                    <button
                      className="link-action"
                      onClick={() => handleCopySource(camera.source)}
                      type="button"
                    >
                      Copy URL
                    </button>
                    <div className="camera-card-buttons">
                      {canManageCameras ? (
                        <>
                          <button
                            className="secondary-button table-button"
                            onClick={() => handleEdit(camera)}
                            type="button"
                          >
                            Edit
                          </button>
                          <button
                            className="secondary-button table-button"
                            disabled={testingCameraId === camera.id}
                            onClick={() => handleTestConfiguredCamera(camera)}
                            type="button"
                          >
                            {testingCameraId === camera.id ? "Testing..." : "Test connection"}
                          </button>
                          <button
                            className="danger-button table-button"
                            onClick={() => handleDelete(camera)}
                            type="button"
                          >
                            Delete
                          </button>
                        </>
                      ) : (
                        <span className="muted-text">Read only</span>
                      )}
                    </div>
                  </div>
                </article>
              ))}
            </div>
          ) : null}
        </section>
      </section>
    </AppShell>
  );
}
