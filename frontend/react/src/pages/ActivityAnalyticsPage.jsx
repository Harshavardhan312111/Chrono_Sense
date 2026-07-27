import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { AppShell } from "../components/AppShell";
import {
  getActivityLocations,
  getEngagementScore
} from "../lib/admin";
import { getTodayDateInputValue } from "./admin-data";

function getPageCopy(mode) {
  if (mode === "engagement") {
    return {
      title: "Engagement Analysis",
      subtitle: "Cross-class student engagement and faculty classroom activity derived from the class-level analytics pipeline.",
      breadcrumbs: [
        { label: "Activities", to: "/activities/live" },
        { label: "Engagement" }
      ]
    };
  }

  if (mode === "reports") {
    return {
      title: "Behavior Reports",
      subtitle: "Activity reporting route reserved for exports, summaries, and research-facing deliverables.",
      breadcrumbs: [
        { label: "Activities", to: "/activities/live" },
        { label: "Reports" }
      ]
    };
  }

  return {
    title: "Live Activity",
    subtitle: "Current student activity, faculty activity, classroom context, and live engagement status.",
    breadcrumbs: [
      { label: "Activities", to: "/activities/live" },
      { label: "Live" }
    ]
  };
}

export function ActivityAnalyticsPage({ mode }) {
  const page = getPageCopy(mode);
  const [date, setDate] = useState(getTodayDateInputValue());
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState("");

  useEffect(() => {
    loadActivityData();
  }, [mode, date]);

  async function loadActivityData() {
    setLoading(true);
    setMessage("");

    try {
      const locationData = await getActivityLocations(date);
      const locations = locationData?.locations || {};

      if (mode === "engagement") {
        const engagementRows = await Promise.all(
          Object.keys(locations).map(async (location) => {
            const score = await getEngagementScore(location, date);
            return {
              location,
              score
            };
          })
        );
        setData({ locations, engagementRows });
      } else {
        setData({ locations });
      }
    } catch (error) {
      setData(null);
      setMessage(error.message || "Unable to load activity analytics.");
    } finally {
      setLoading(false);
    }
  }

  const locations = Object.entries(data?.locations || {});

  return (
    <AppShell
      title={page.title}
      subtitle={page.subtitle}
      eyebrow="Activities"
      breadcrumbs={page.breadcrumbs}
      actions={(
        <div className="hero-actions">
          <label className="filter-field compact">
            <span>Date</span>
            <input onChange={(event) => setDate(event.target.value)} type="date" value={date} />
          </label>
          <button className="secondary-button" onClick={loadActivityData} type="button">
            Refresh
          </button>
        </div>
      )}
    >
      {message ? <p className="inline-note">{message}</p> : null}

      {mode === "reports" ? (
        <section className="panel">
          <div className="section-header">
            <div>
              <h3>Behavior reporting center</h3>
              <p>The route exists now in the React shell while export presets continue to grow.</p>
            </div>
          </div>
          <div className="scaffold-grid">
            <article className="metric-card">
              <span>Current scope</span>
              <strong>{locations.length}</strong>
              <p>Locations already contributing live activity data to the reporting center.</p>
            </article>
            <article className="metric-card">
              <span>Next step</span>
              <strong>Exports</strong>
              <p>Scheduled exports and saved report presets are the next decomposition layer for this module.</p>
            </article>
          </div>
          <div className="link-cluster">
            <Link className="secondary-button inline-button" to="/reports">
              Open reports center
            </Link>
          </div>
        </section>
      ) : null}

      {mode !== "reports" ? (
        <section className="ops-card-grid wide">
          {loading ? <div className="table-empty">Loading activity analytics...</div> : null}
          {!loading && !locations.length ? <div className="table-empty">No activity detections available.</div> : null}
          {!loading ? locations.map(([location, details]) => {
            const engagementScore = data?.engagementRows?.find((item) => item.location === location)?.score;

            return (
              <article className="ops-card" key={location}>
                <div className="ops-card-header">
                  <strong>{location}</strong>
                  <span className="badge-light">{details.total_windows || 0} windows</span>
                </div>
                <p>Student activity: {details.dominant_student_activity || details.dominant_activity || "-"}</p>
                <ul className="compact-stat-list">
                  <li>Faculty activity: {details.dominant_faculty_activity || "-"}</li>
                  <li>Classroom context: {details.dominant_context || "-"}</li>
                  <li>Student engagement: {Math.round((details.engagement_score || 0) * 100)}%</li>
                  <li>Students visible: {details.recognized_student_count ?? 0}</li>
                  <li>Faculty visible: {details.recognized_faculty_count ?? 0}</li>
                  {mode === "engagement" ? (
                    <li>Backend score: {Math.round((engagementScore?.engagement_score || 0) * 100)}%</li>
                  ) : null}
                  {details.dominant_faculty_activity === "faculty_computer_work" ? (
                    <li>Faculty workstation activity detected</li>
                  ) : null}
                </ul>
              </article>
            );
          }) : null}
        </section>
      ) : null}

      <div className="link-cluster">
        <Link className="secondary-button inline-button" to="/emotions/live">
          Open emotion analytics
        </Link>
        <Link className="secondary-button inline-button" to="/classrooms">
          Open classroom health
        </Link>
      </div>
    </AppShell>
  );
}
