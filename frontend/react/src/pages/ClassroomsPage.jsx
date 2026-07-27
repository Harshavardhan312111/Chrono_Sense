import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { AppShell } from "../components/AppShell";
import { getActivityLocations, getClassroomEmotions } from "../lib/admin";
import { getTodayDateInputValue } from "./admin-data";

export function ClassroomsPage() {
  const [date, setDate] = useState(getTodayDateInputValue());
  const [data, setData] = useState({ emotions: {}, activities: {} });
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState("");

  useEffect(() => {
    loadClassroomHealth();
  }, [date]);

  async function loadClassroomHealth() {
    setLoading(true);
    setMessage("");

    try {
      const [emotionData, activityData] = await Promise.all([
        getClassroomEmotions({ date }),
        getActivityLocations(date)
      ]);
      setData({
        emotions: emotionData?.locations || {},
        activities: activityData?.locations || {}
      });
    } catch (error) {
      setData({ emotions: {}, activities: {} });
      setMessage(error.message || "Unable to load classroom health.");
    } finally {
      setLoading(false);
    }
  }

  const locations = Array.from(
    new Set([
      ...Object.keys(data.emotions || {}),
      ...Object.keys(data.activities || {})
    ])
  );

  return (
    <AppShell
      title="Classroom Health"
      subtitle="Cross-class comparisons now combine emotion signals with class-level student activity, faculty activity, and classroom context."
      eyebrow="Classrooms"
      breadcrumbs={[
        { label: "Classrooms", to: "/classrooms" },
        { label: "Overview" }
      ]}
      actions={(
        <div className="hero-actions">
          <label className="filter-field compact">
            <span>Date</span>
            <input onChange={(event) => setDate(event.target.value)} type="date" value={date} />
          </label>
          <button className="secondary-button" onClick={loadClassroomHealth} type="button">
            Refresh
          </button>
        </div>
      )}
    >
      {message ? <p className="inline-note">{message}</p> : null}

      <section className="ops-card-grid wide">
        {loading ? <div className="table-empty">Loading classroom health...</div> : null}
        {!loading && !locations.length ? <div className="table-empty">No classroom analytics available.</div> : null}
        {!loading ? locations.map((location) => {
          const emotion = data.emotions[location];
          const activity = data.activities[location];

          return (
            <article className="ops-card" key={location}>
              <div className="ops-card-header">
                <strong>{location}</strong>
                <span className="badge-light">{activity?.total_windows || emotion?.total_detections || 0} signals</span>
              </div>
              <ul className="compact-stat-list">
                <li>Dominant emotion: {emotion?.dominant_emotion || "-"}</li>
                <li>Student activity: {activity?.dominant_student_activity || activity?.dominant_activity || "-"}</li>
                <li>Faculty activity: {activity?.dominant_faculty_activity || "-"}</li>
                <li>Classroom context: {activity?.dominant_context || "-"}</li>
                <li>Engagement: {Math.round((activity?.engagement_score || 0) * 100)}%</li>
                <li>Emotion detections: {emotion?.total_detections || 0}</li>
                {activity?.dominant_faculty_activity === "faculty_computer_work" ? (
                  <li>Faculty workstation activity detected</li>
                ) : null}
              </ul>
            </article>
          );
        }) : null}
      </section>

      <div className="link-cluster">
        <Link className="secondary-button inline-button" to="/emotions/classes">
          Open class emotion analytics
        </Link>
        <Link className="secondary-button inline-button" to="/activities/engagement">
          Open engagement analysis
        </Link>
      </div>
    </AppShell>
  );
}
