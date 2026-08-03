import { useEffect, useState } from "react";
import { AppShell } from "../components/AppShell";
import {
  assignUnknownFace,
  deleteUnknownFace,
  getCurrentDetections,
  getPersistentUnknownFaces,
  getProfiles,
  getRecognitionStatus,
  getUnknownSnapshots,
  getValidationCameras,
  startRecognition,
  stopRecognition
} from "../lib/admin";
import { formatTimeInAppTimezone } from "../lib/time";

const PROFILES_PAGE_SIZE = 6;
const UNKNOWN_PAGE_SIZE = 4;
const SNAPSHOTS_PAGE_SIZE = 8;

function formatTime(value) {
  return formatTimeInAppTimezone(value);
}

export function ValidationPage() {
  const [cameras, setCameras] = useState([]);
  const [profiles, setProfiles] = useState([]);
  const [profilesLoading, setProfilesLoading] = useState(false);
  const [selectedCameraId, setSelectedCameraId] = useState("");
  const [message, setMessage] = useState("");
  const [recognitionRunning, setRecognitionRunning] = useState(false);
  const [loading, setLoading] = useState(false);
  const [detections, setDetections] = useState({
    total_faces: 0,
    known_faces: [],
    known_faces_count: 0,
    unknown_faces_count: 0,
    updated_at: null
  });
  const [snapshots, setSnapshots] = useState([]);
  const [unknownFaces, setUnknownFaces] = useState([]);
  const [profilePage, setProfilePage] = useState(1);
  const [unknownPage, setUnknownPage] = useState(1);
  const [snapshotPage, setSnapshotPage] = useState(1);

  useEffect(() => {
    loadInitialData();
  }, []);

  useEffect(() => {
    if (!selectedCameraId) {
      return;
    }

    refreshValidationData(selectedCameraId);

    const intervalId = window.setInterval(() => {
      refreshValidationData(selectedCameraId);
    }, 750);

    return () => window.clearInterval(intervalId);
  }, [selectedCameraId]);

  useEffect(() => {
    setUnknownPage(1);
    setSnapshotPage(1);
  }, [selectedCameraId]);

  async function loadInitialData() {
    setLoading(true);
    setProfilesLoading(true);

    try {
      const [cameraData, profileData] = await Promise.all([
        getValidationCameras(),
        getProfiles()
      ]);

      const cameraList = cameraData.cameras || [];
      const profileList = profileData.profiles || [];

      setCameras(cameraList);
      setProfiles(profileList);

      if (cameraList.length) {
        setSelectedCameraId(String(cameraList[0].id));
      }
    } catch (error) {
      setMessage(error.message || "Unable to load validation workspace.");
    } finally {
      setLoading(false);
      setProfilesLoading(false);
    }
  }

  async function refreshValidationData(cameraId) {
    try {
      const [statusData, detectionData, snapshotData, unknownData] = await Promise.all([
        getRecognitionStatus(cameraId),
        getCurrentDetections(cameraId),
        getUnknownSnapshots(cameraId),
        getPersistentUnknownFaces(cameraId)
      ]);

      setRecognitionRunning(Boolean(statusData?.data?.running));
      setDetections(detectionData?.data || {
        total_faces: 0,
        known_faces: [],
        known_faces_count: 0,
        unknown_faces_count: 0,
        updated_at: null
      });
      setSnapshots(snapshotData?.snapshots || []);
      setUnknownFaces(unknownData?.unknown_faces || []);
    } catch (error) {
      setMessage(error.message || "Unable to refresh validation data.");
    }
  }

  async function handleStartRecognition() {
    if (!selectedCameraId) {
      return;
    }

    try {
      setMessage("Starting recognition...");
      await startRecognition(selectedCameraId);
      setRecognitionRunning(true);
      setMessage("Recognition started.");
      await refreshValidationData(selectedCameraId);
    } catch (error) {
      setMessage(error.message || "Unable to start recognition.");
    }
  }

  async function handleStopRecognition() {
    if (!selectedCameraId) {
      return;
    }

    try {
      setMessage("Stopping recognition...");
      await stopRecognition(selectedCameraId);
      setRecognitionRunning(false);
      setMessage("Recognition stopped.");
      await refreshValidationData(selectedCameraId);
    } catch (error) {
      setMessage(error.message || "Unable to stop recognition.");
    }
  }

  async function handleDeleteUnknownFace(unknownFaceId) {
    const confirmed = window.confirm("Delete this unknown-face tracking entry?");

    if (!confirmed) {
      return;
    }

    try {
      await deleteUnknownFace(unknownFaceId);
      setMessage("Unknown face entry deleted.");
      await refreshValidationData(selectedCameraId);
    } catch (error) {
      setMessage(error.message || "Unable to delete unknown face entry.");
    }
  }

  async function handleAssignUnknownFace(event, unknownFaceId) {
    const profileId = event.target.value;

    if (!profileId) {
      return;
    }

    try {
      await assignUnknownFace(unknownFaceId, profileId);
      setMessage("Unknown face assigned to selected profile.");
      await refreshValidationData(selectedCameraId);
    } catch (error) {
      setMessage(error.message || "Unable to assign unknown face.");
    }
  }

  const selectedCamera = cameras.find((camera) => String(camera.id) === String(selectedCameraId));
  const totalProfilePages = Math.max(1, Math.ceil(profiles.length / PROFILES_PAGE_SIZE));
  const totalUnknownPages = Math.max(1, Math.ceil(unknownFaces.length / UNKNOWN_PAGE_SIZE));
  const totalSnapshotPages = Math.max(1, Math.ceil(snapshots.length / SNAPSHOTS_PAGE_SIZE));
  const paginatedProfiles = profiles.slice(
    (profilePage - 1) * PROFILES_PAGE_SIZE,
    profilePage * PROFILES_PAGE_SIZE
  );
  const paginatedUnknownFaces = unknownFaces.slice(
    (unknownPage - 1) * UNKNOWN_PAGE_SIZE,
    unknownPage * UNKNOWN_PAGE_SIZE
  );
  const paginatedSnapshots = snapshots.slice(
    (snapshotPage - 1) * SNAPSHOTS_PAGE_SIZE,
    snapshotPage * SNAPSHOTS_PAGE_SIZE
  );

  useEffect(() => {
    setProfilePage((current) => Math.min(current, totalProfilePages));
  }, [totalProfilePages]);

  useEffect(() => {
    setUnknownPage((current) => Math.min(current, totalUnknownPages));
  }, [totalUnknownPages]);

  useEffect(() => {
    setSnapshotPage((current) => Math.min(current, totalSnapshotPages));
  }, [totalSnapshotPages]);

  return (
    <AppShell
      title="Face validation"
      subtitle="Review active attendance detections, control recognition, and resolve unknown faces without opening the analytics stack."
    >
      <section className="hero-panel">
        <div>
          <p className="eyebrow">Validation</p>
          <h2>This page completes the attendance workflow from recognition to evidence review.</h2>
        </div>
      </section>

      {message ? <p className="inline-note">{message}</p> : null}

      <section className="panel">
        <div className="section-header">
          <div>
            <h3>Camera selection</h3>
            <p>Select a configured attendance camera to inspect live recognition output.</p>
          </div>
          <div className="section-actions responsive-filters">
            <label className="filter-field validation-select">
              <span>Camera</span>
              <select
                onChange={(event) => setSelectedCameraId(event.target.value)}
                value={selectedCameraId}
              >
                {cameras.map((camera) => (
                  <option key={camera.id} value={camera.id}>
                    {camera.name}
                  </option>
                ))}
              </select>
            </label>
            <button
              className="secondary-button"
              onClick={() => refreshValidationData(selectedCameraId)}
              type="button"
            >
              Refresh
            </button>
          </div>
        </div>

        {loading ? <div className="table-empty">Loading validation workspace...</div> : null}

        {!loading && selectedCamera ? (
          <>
            <section className="card-grid">
              <article className="metric-card">
                <span>Total faces</span>
                <strong>{detections.total_faces || 0}</strong>
                <p>Faces currently visible in the active validation feed.</p>
              </article>
              <article className="metric-card">
                <span>Registered</span>
                <strong>{detections.known_faces_count || 0}</strong>
                <p>Known attendance profiles matched in the current frame.</p>
              </article>
              <article className="metric-card">
                <span>Unknown</span>
                <strong>{detections.unknown_faces_count || 0}</strong>
                <p>Current unrecognized faces in the active validation frame.</p>
              </article>
              <article className="metric-card">
                <span>Recognition</span>
                <strong>{recognitionRunning ? "Running" : "Idle"}</strong>
                <p>{selectedCamera.name} recognition status from the backend engine.</p>
              </article>
            </section>

            <section className="panel validation-controls">
              <div className="section-actions">
                {!recognitionRunning ? (
                  <button className="primary-button" onClick={handleStartRecognition} type="button">
                    Start recognition
                  </button>
                ) : (
                  <button className="danger-button table-button" onClick={handleStopRecognition} type="button">
                    Stop recognition
                  </button>
                )}
              </div>
              <p className="inline-note">
                Last update: {formatTime(detections.updated_at)}
              </p>
            </section>

            <div className="validation-layout">
              <article className="panel">
                <div className="section-header">
                  <div>
                    <h3>Known faces</h3>
                    <p>Registered attendance matches from the most recent camera detection update.</p>
                  </div>
                  <span className="badge-light">{detections.known_faces_count || 0}</span>
                </div>

                <div className="stack-list">
                  {(detections.known_faces || []).length ? (
                    detections.known_faces.map((face) => {
                      const confidence = Number(face.confidence || 0);
                      return (
                        <div className="list-card static" key={`${face.profile_id}-${face.name}`}>
                          <div>
                            <strong>{face.name}</strong>
                            <p>Profile ID: {face.profile_id}</p>
                            <p>Quality: {face.quality_band || "-"}</p>
                            <p>Identity decision: {face.identity_decision_reason || face.decision_reason || face.recognition_rejection_reason || "-"}</p>
                            <p>Emotion status: {face.emotion_status_reason || face.emotion_unavailable_reason || "emotion_available"}</p>
                            <p>Recovery: {face.recovery_stage || face.preprocess_variant || "-"}</p>
                          </div>
                          <span className="badge-light">{(confidence * 100).toFixed(1)}%</span>
                        </div>
                      );
                    })
                  ) : (
                    <div className="table-empty">No registered faces detected yet.</div>
                  )}
                </div>
              </article>

              <article className="panel">
                <div className="section-header">
                  <div>
                    <h3>Registered users</h3>
                    <p>Attendance profiles available for unknown-face assignment.</p>
                  </div>
                  <span className="badge-light">{profiles.length}</span>
                </div>

                {profilesLoading ? (
                  <div className="table-empty">Loading registered users...</div>
                ) : (
                  <>
                    <div className="stack-list">
                      {paginatedProfiles.length ? (
                        paginatedProfiles.map((profile) => (
                          <div className="list-card static" key={profile.id}>
                            <div>
                              <strong>{profile.name}</strong>
                              <p>{profile.department || profile.email || "No department or email"}</p>
                            </div>
                            <span className="badge-light">#{profile.id}</span>
                          </div>
                        ))
                      ) : (
                        <div className="table-empty">No attendance users have been registered yet.</div>
                      )}
                    </div>
                    <div className="pagination-row">
                      <button
                        className="secondary-button table-button"
                        disabled={profilePage === 1}
                        onClick={() => setProfilePage((current) => Math.max(1, current - 1))}
                        type="button"
                      >
                        Previous
                      </button>
                      <span className="pagination-text">
                        Page {profilePage} of {totalProfilePages}
                      </span>
                      <button
                        className="secondary-button table-button"
                        disabled={profilePage === totalProfilePages}
                        onClick={() => setProfilePage((current) => Math.min(totalProfilePages, current + 1))}
                        type="button"
                      >
                        Next
                      </button>
                    </div>
                  </>
                )}
              </article>
            </div>

            <section className="panel">
              <div className="section-header">
                <div>
                  <h3>Persistent unknown faces</h3>
                  <p>Recent unknown faces tracked across frames for this camera.</p>
                </div>
                <span className="badge-light">{unknownFaces.length}</span>
              </div>

              <div className="stack-list">
                {paginatedUnknownFaces.length ? (
                  paginatedUnknownFaces.map((face) => (
                    <div className="detail-card" key={face.id}>
                      <div className="subsection-head">
                        <h4>Unknown #{face.id}</h4>
                        <span>{face.detection_count || 0} detections</span>
                      </div>
                      <p>First seen: {formatTime(face.first_seen)}</p>
                      <p>Last seen: {formatTime(face.last_seen)}</p>
                      <p>Identity decision: {face.identity_decision_reason || face.decision_reason || "-"}</p>
                      <div className="section-actions">
                        <label className="filter-field validation-assign">
                          <span>Assign to profile</span>
                          <select
                            defaultValue=""
                            onChange={(event) => handleAssignUnknownFace(event, face.id)}
                          >
                            <option value="">Select profile</option>
                            {profiles.map((profile) => (
                              <option key={profile.id} value={profile.id}>
                                {profile.name}
                              </option>
                            ))}
                          </select>
                        </label>
                        <button
                          className="danger-button table-button"
                          onClick={() => handleDeleteUnknownFace(face.id)}
                          type="button"
                        >
                          Delete
                        </button>
                      </div>
                    </div>
                  ))
                ) : (
                  <div className="table-empty">No persistent unknown faces detected.</div>
                )}
              </div>

              <div className="pagination-row">
                <button
                  className="secondary-button table-button"
                  disabled={unknownPage === 1}
                  onClick={() => setUnknownPage((current) => Math.max(1, current - 1))}
                  type="button"
                >
                  Previous
                </button>
                <span className="pagination-text">
                  Page {unknownPage} of {totalUnknownPages}
                </span>
                <button
                  className="secondary-button table-button"
                  disabled={unknownPage === totalUnknownPages}
                  onClick={() => setUnknownPage((current) => Math.min(totalUnknownPages, current + 1))}
                  type="button"
                >
                  Next
                </button>
              </div>
            </section>

            <section className="panel">
              <div className="section-header">
                <div>
                  <h3>Unknown face snapshots</h3>
                  <p>Recent unknown-face evidence captured for attendance validation.</p>
                </div>
                <span className="badge-light">{snapshots.length}</span>
              </div>

              {!paginatedSnapshots.length ? (
                <div className="table-empty">No snapshots captured yet.</div>
              ) : (
                <div className="snapshot-grid-react">
                  {paginatedSnapshots.map((snapshot) => (
                    <a
                      className="snapshot-card-react"
                      href={`/api/snapshots/${selectedCameraId}/${encodeURIComponent(snapshot.filename)}`}
                      key={snapshot.filename}
                      target="_blank"
                      rel="noreferrer"
                    >
                      <div className="snapshot-placeholder-react">📸</div>
                      <strong>{snapshot.filename}</strong>
                      <span>{formatTime(snapshot.timestamp)}</span>
                    </a>
                  ))}
                </div>
              )}

              <div className="pagination-row">
                <button
                  className="secondary-button table-button"
                  disabled={snapshotPage === 1}
                  onClick={() => setSnapshotPage((current) => Math.max(1, current - 1))}
                  type="button"
                >
                  Previous
                </button>
                <span className="pagination-text">
                  Page {snapshotPage} of {totalSnapshotPages}
                </span>
                <button
                  className="secondary-button table-button"
                  disabled={snapshotPage === totalSnapshotPages}
                  onClick={() => setSnapshotPage((current) => Math.min(totalSnapshotPages, current + 1))}
                  type="button"
                >
                  Next
                </button>
              </div>
            </section>
          </>
        ) : null}
      </section>
    </AppShell>
  );
}
