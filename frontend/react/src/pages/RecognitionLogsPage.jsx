import { useEffect, useState } from "react";
import { AppShell } from "../components/AppShell";
import { getRecognitionLogs } from "../lib/admin";

function getLogName(log) {
  return log.name || log.profile_name || log.person_name || "Detection";
}

function getLogLocation(log) {
  return log.location || log.camera_name || log.source || "-";
}

function getLogTimestamp(log) {
  return log.timestamp || log.time || log.detected_at || "-";
}

export function RecognitionLogsPage() {
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState("");

  useEffect(() => {
    loadLogs();
  }, []);

  async function loadLogs() {
    setLoading(true);
    setMessage("");

    try {
      const data = await getRecognitionLogs({ limit: 100 });
      setLogs(data?.logs || []);
    } catch (error) {
      setLogs([]);
      setMessage(error.message || "Unable to load recognition logs.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <AppShell
      title="Recognition Logs"
      subtitle="Recent detection history and recognition events now live on a dedicated module route instead of being buried behind operational tabs."
      eyebrow="Recognition"
      breadcrumbs={[
        { label: "Recognition", to: "/recognition/validation" },
        { label: "Logs" }
      ]}
      actions={(
        <button className="secondary-button" onClick={loadLogs} type="button">
          Refresh logs
        </button>
      )}
    >
      {message ? <p className="inline-note">{message}</p> : null}

      <section className="panel">
        <div className="section-header">
          <div>
            <h3>Detection stream</h3>
            <p>Audit recent recognition output across all configured classroom cameras.</p>
          </div>
        </div>

        <div className="table-shell">
          <table>
            <thead>
              <tr>
                <th>Subject</th>
                <th>Location</th>
                <th>Timestamp</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td className="table-empty" colSpan="4">Loading logs...</td>
                </tr>
              ) : null}
              {!loading && !logs.length ? (
                <tr>
                  <td className="table-empty" colSpan="4">No recognition logs available.</td>
                </tr>
              ) : null}
              {!loading ? logs.map((log, index) => (
                <tr key={`${getLogName(log)}-${index}`}>
                  <td><strong>{getLogName(log)}</strong></td>
                  <td>{getLogLocation(log)}</td>
                  <td>{getLogTimestamp(log)}</td>
                  <td>
                    <span className={`status-pill ${String(log.status || "").toLowerCase() === "unknown" ? "absent" : "present"}`}>
                      {log.status || log.event_type || "detected"}
                    </span>
                  </td>
                </tr>
              )) : null}
            </tbody>
          </table>
        </div>
      </section>
    </AppShell>
  );
}
