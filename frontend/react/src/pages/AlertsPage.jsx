import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { AppShell } from "../components/AppShell";
import { loadOperationsSnapshot } from "../lib/operations";
import { getTodayDateInputValue } from "./admin-data";

export function AlertsPage() {
  const [alerts, setAlerts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState("");

  useEffect(() => {
    loadAlerts();
  }, []);

  async function loadAlerts() {
    setLoading(true);
    setMessage("");

    try {
      const snapshot = await loadOperationsSnapshot(getTodayDateInputValue());
      setAlerts(snapshot.alerts || []);
    } catch (error) {
      setAlerts([]);
      setMessage(error.message || "Unable to load alerts.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <AppShell
      title="Operational Alerts"
      subtitle="Active incidents and anomalies surfaced from camera health, recognition state, validation backlog, and classroom activity."
      eyebrow="Overview"
      breadcrumbs={[
        { label: "Overview", to: "/overview" },
        { label: "Alerts" }
      ]}
      attentionCount={alerts.length}
      actions={(
        <button className="secondary-button" onClick={loadAlerts} type="button">
          Refresh alerts
        </button>
      )}
    >
      {message ? <p className="inline-note">{message}</p> : null}

      <section className="alert-list-grid">
        {loading ? <div className="table-empty">Loading alerts...</div> : null}
        {!loading && !alerts.length ? (
          <article className="panel">
            <h3>No active alerts</h3>
            <p>The system has no currently derived incidents from the monitored routes.</p>
          </article>
        ) : null}
        {!loading ? alerts.map((alert, index) => (
          <article className={`alert-card panel ${alert.severity}`} key={`${alert.title}-${index}`}>
            <span className="eyebrow">{alert.severity}</span>
            <h3>{alert.title}</h3>
            <p>{alert.detail}</p>
            <div className="link-cluster">
              <Link className="secondary-button inline-button" to="/overview/live">
                Live operations
              </Link>
              <Link className="secondary-button inline-button" to="/recognition/validation">
                Validation queue
              </Link>
            </div>
          </article>
        )) : null}
      </section>
    </AppShell>
  );
}
