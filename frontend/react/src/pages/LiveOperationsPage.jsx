import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { AppShell } from "../components/AppShell";
import { loadOperationsSnapshot } from "../lib/operations";
import { getTodayDateInputValue } from "./admin-data";

export function LiveOperationsPage() {
  const [snapshot, setSnapshot] = useState(null);
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadLiveOperations();
  }, []);

  useEffect(() => {
    const intervalId = window.setInterval(() => {
      loadLiveOperations();
    }, 3000);

    return () => window.clearInterval(intervalId);
  }, []);

  async function loadLiveOperations() {
    setLoading(true);
    setMessage("");

    try {
      const data = await loadOperationsSnapshot(getTodayDateInputValue());
      setSnapshot(data);
    } catch (error) {
      setSnapshot(null);
      setMessage(error.message || "Unable to load live operations.");
    } finally {
      setLoading(false);
    }
  }

  const cameras = snapshot?.cameras || [];

  return (
    <AppShell
      title="Live Operations"
      subtitle="A dedicated operational workspace for monitoring camera health, recognition state, validation backlog, and classroom signals."
      eyebrow="Overview"
      breadcrumbs={[
        { label: "Overview", to: "/overview" },
        { label: "Live Operations" }
      ]}
      attentionCount={snapshot?.alerts?.length || 0}
      actions={(
        <div className="hero-actions">
          <button className="secondary-button" onClick={loadLiveOperations} type="button">
            Refresh workspace
          </button>
          <Link className="primary-button inline-button" to="/recognition/validation">
            Open validation queue
          </Link>
        </div>
      )}
    >
      {message ? <p className="inline-note">{message}</p> : null}

      <section className="panel">
        <div className="section-header">
          <div>
            <h3>Camera monitoring</h3>
            <p>Every configured camera is now visible from a single route-native operations page.</p>
          </div>
        </div>

        <div className="ops-card-grid wide">
          {loading ? <div className="table-empty">Loading cameras...</div> : null}
          {!loading && !cameras.length ? <div className="table-empty">No cameras configured.</div> : null}
          {!loading ? cameras.map((camera) => (
            <article className="ops-card" key={camera.id}>
              <div className="ops-card-header">
                <strong>{camera.name}</strong>
                <span className={`status-pill ${camera.connection === "connected" ? "present" : "absent"}`}>
                  {camera.connection}
                </span>
              </div>
              <p>{camera.wing || "No wing"} · Room {camera.room_number || "-"} · {camera.type || "camera"}</p>
              <ul className="compact-stat-list">
                <li>Recognition: {camera.recognitionRunning ? "Running" : "Stopped"}</li>
                <li>Unknown face backlog: {camera.unknownFaceCount}</li>
                <li>Dominant emotion: {camera.emotion?.dominant_emotion || "-"}</li>
                <li>Student activity: {camera.activity?.dominant_student_activity || camera.activity?.dominant_activity || "-"}</li>
                <li>Faculty activity: {camera.activity?.dominant_faculty_activity || "-"}</li>
                <li>Classroom context: {camera.activity?.dominant_context || "-"}</li>
                <li>Engagement: {Math.round((camera.activity?.engagement_score || 0) * 100)}%</li>
                <li>Students visible: {camera.activity?.recognized_student_count ?? 0}</li>
                <li>Faculty visible: {camera.activity?.recognized_faculty_count ?? 0}</li>
                {camera.activity?.dominant_faculty_activity === "faculty_computer_work" ? (
                  <li>Faculty workstation activity detected</li>
                ) : null}
              </ul>
              <div className="link-cluster">
                <Link className="secondary-button inline-button" to="/cameras/stream">
                  Stream viewer
                </Link>
                <Link className="secondary-button inline-button" to="/cameras">
                  Camera settings
                </Link>
              </div>
            </article>
          )) : null}
        </div>
      </section>

      <section className="enterprise-layout-grid">
        <article className="panel">
          <div className="section-header">
            <div>
              <h3>Operational alert rail</h3>
              <p>These alerts are generated from current device and recognition conditions.</p>
            </div>
          </div>
          <div className="alert-list">
            {(snapshot?.alerts || []).length ? (snapshot?.alerts || []).map((alert, index) => (
              <article className={`alert-card ${alert.severity}`} key={`${alert.title}-${index}`}>
                <strong>{alert.title}</strong>
                <p>{alert.detail}</p>
              </article>
            )) : <div className="table-empty">No active alerts.</div>}
          </div>
        </article>

        <article className="panel">
          <div className="section-header">
            <div>
              <h3>Next actions</h3>
              <p>The new shell keeps operational workflows within one to three clicks.</p>
            </div>
          </div>
          <div className="link-cluster vertical">
            <Link className="secondary-button inline-button" to="/recognition/logs">
              Inspect recognition logs
            </Link>
            <Link className="secondary-button inline-button" to="/recognition/unknown-faces">
              Review unknown faces
            </Link>
            <Link className="secondary-button inline-button" to="/attendance/today">
              Open attendance control room
            </Link>
          </div>
        </article>
      </section>
    </AppShell>
  );
}
