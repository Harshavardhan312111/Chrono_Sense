import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { AppShell } from "../components/AppShell";
import { getProfiles, getStudentEmotionTimeline } from "../lib/admin";
import { getTodayDateInputValue, getWeekStartDateInputValue } from "./admin-data";

function formatEmotionScores(scores) {
  return Object.entries(scores || {})
    .map(([emotion, score]) => ({ emotion, score: Number(score || 0) }))
    .filter((entry) => entry.score > 0)
    .sort((left, right) => right.score - left.score)
    .map((entry) => `${entry.emotion}: ${Math.round(entry.score * 100)}%`)
    .join(", ");
}

export function PersonEmotionTimelinePage() {
  const { profileId } = useParams();
  const [startDate, setStartDate] = useState(getWeekStartDateInputValue());
  const [endDate, setEndDate] = useState(getTodayDateInputValue());
  const [data, setData] = useState(null);
  const [profile, setProfile] = useState(null);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState("");

  useEffect(() => {
    loadTimeline();
  }, [profileId, startDate, endDate]);

  async function loadTimeline() {
    setLoading(true);
    setMessage("");
    try {
      const [timelineData, profileData] = await Promise.all([
        getStudentEmotionTimeline(profileId, { startDate, endDate }),
        getProfiles()
      ]);
      const matchedProfile = (profileData?.profiles || []).find(
        (entry) => String(entry.id) === String(profileId)
      );
      setData(timelineData);
      setProfile(matchedProfile || null);
    } catch (error) {
      setData(null);
      setProfile(null);
      setMessage(error.message || "Unable to load person emotion timeline.");
    } finally {
      setLoading(false);
    }
  }

  const timeline = data?.timeline || [];
  const distribution = Object.entries(data?.emotion_distribution || {});
  const profileTypeLabel = profile?.profile_type === "faculty" ? "Teacher" : profile?.profile_type === "student" ? "Student" : "Person";

  return (
    <AppShell
      title="Person Emotion Timeline"
      subtitle="Confidence-gated observational emotion signals for a recognized teacher or student across the selected period."
      eyebrow="Emotions"
      breadcrumbs={[
        { label: "Emotions", to: "/emotions/live" },
        { label: "Person Timeline" },
      ]}
      actions={(
        <div className="hero-actions">
          <label className="filter-field compact">
            <span>Start</span>
            <input onChange={(event) => setStartDate(event.target.value)} type="date" value={startDate} />
          </label>
          <label className="filter-field compact">
            <span>End</span>
            <input onChange={(event) => setEndDate(event.target.value)} type="date" value={endDate} />
          </label>
          <button className="secondary-button" onClick={loadTimeline} type="button">
            Refresh
          </button>
        </div>
      )}
    >
      <p className="inline-note">
        Emotion outputs are inferred model signals, not ground truth psychological states.
      </p>
      {message ? <p className="inline-note">{message}</p> : null}

      <section className="card-grid">
        <article className="metric-card">
          <span>Person</span>
          <strong>{loading ? "..." : data?.name || profile?.name || "-"}</strong>
          <p>Recognized teacher or student tied to this timeline.</p>
        </article>
        <article className="metric-card">
          <span>Type</span>
          <strong>{loading ? "..." : profileTypeLabel}</strong>
          <p>Profile classification for the selected person.</p>
        </article>
        <article className="metric-card">
          <span>Dominant emotion</span>
          <strong>{loading ? "..." : data?.dominant_emotion || "-"}</strong>
          <p>Most frequent signal during the selected range.</p>
        </article>
        <article className="metric-card">
          <span>Average confidence</span>
          <strong>{loading ? "..." : `${Math.round((data?.average_confidence || 0) * 100)}%`}</strong>
          <p>Mean model confidence across recorded emotion events.</p>
        </article>
        <article className="metric-card">
          <span>Total detections</span>
          <strong>{loading ? "..." : data?.total_detections || 0}</strong>
          <p>Emotion events that passed logging thresholds.</p>
        </article>
      </section>

      <section className="panel">
        <div className="section-header">
          <div>
            <h3>Emotion distribution</h3>
            <p>Summary of the confidence-gated signals stored for this person.</p>
          </div>
        </div>
        <div className="ops-card-grid">
          {loading ? <div className="table-empty">Loading person emotion summary...</div> : null}
          {!loading && !distribution.length ? <div className="table-empty">No person emotion events available.</div> : null}
          {!loading ? distribution.map(([emotion, count]) => (
            <article className="ops-card" key={emotion}>
              <div className="ops-card-header">
                <strong>{emotion}</strong>
                <span className="badge-light">{count}</span>
              </div>
            </article>
          )) : null}
        </div>
      </section>

      <section className="panel">
        <div className="section-header">
          <div>
            <h3>Timeline events</h3>
            <p>Event-level emotion signals for review, filtered to qualified recognized detections.</p>
          </div>
        </div>
        <div className="table-wrapper">
          <table>
            <thead>
              <tr>
                <th>Timestamp</th>
                <th>Emotion</th>
                <th>Emotion scores</th>
                <th>Emotion confidence</th>
                <th>Recognition confidence</th>
                <th>Location</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td className="table-empty" colSpan="6">Loading timeline...</td></tr>
              ) : null}
              {!loading && !timeline.length ? (
                <tr><td className="table-empty" colSpan="6">No timeline events available.</td></tr>
              ) : null}
              {!loading ? timeline.map((event) => (
                <tr key={`${event.timestamp}-${event.emotion}`}>
                  <td>{event.timestamp || "-"}</td>
                  <td>{event.emotion || "-"}</td>
                  <td>{formatEmotionScores(event.smoothed_scores || event.raw_scores || event.all_emotions) || "-"}</td>
                  <td>{Math.round((event.emotion_confidence || 0) * 100)}%</td>
                  <td>{Math.round((event.recognition_confidence || 0) * 100)}%</td>
                  <td>{event.location || "-"}</td>
                </tr>
              )) : null}
            </tbody>
          </table>
        </div>
      </section>

      <div className="link-cluster">
        <Link className="secondary-button inline-button" to="/emotions/live">
          Back to live emotions
        </Link>
      </div>
    </AppShell>
  );
}
