import { useEffect, useMemo, useState } from "react";
import { AppShell } from "../components/AppShell";
import {
  exportRecognitionReviewCsv,
  getRecognitionReviewRecords,
  getValidationCameras,
  resetRecognitionReviewRecords,
  updateRecognitionReviewVerdict
} from "../lib/admin";
import { formatDateTimeInAppTimezone } from "../lib/time";

function formatScore(value) {
  const numeric = Number(value || 0);
  return numeric ? numeric.toFixed(4) : "0.0000";
}

export function RecognitionReviewPage() {
  const [cameras, setCameras] = useState([]);
  const [selectedCameraId, setSelectedCameraId] = useState("");
  const [reviewStatus, setReviewStatus] = useState("");
  const [records, setRecords] = useState([]);
  const [noteDrafts, setNoteDrafts] = useState({});
  const [loading, setLoading] = useState(true);
  const [exporting, setExporting] = useState(false);
  const [resetting, setResetting] = useState(false);
  const [message, setMessage] = useState("");
  const [savingId, setSavingId] = useState(null);
  const [hiddenImages, setHiddenImages] = useState({});

  useEffect(() => {
    loadInitialData();
  }, []);

  useEffect(() => {
    if (!loading) {
      loadRecords();
    }
  }, [selectedCameraId, reviewStatus]);

  async function loadInitialData() {
    setLoading(true);
    setMessage("");

    try {
      const cameraData = await getValidationCameras();
      const nextCameras = cameraData?.cameras || [];
      setCameras(nextCameras);
      if (nextCameras.length) {
        setSelectedCameraId(String(nextCameras[0].id));
      }
      await loadRecords(nextCameras.length ? String(nextCameras[0].id) : "");
    } catch (error) {
      setMessage(error.message || "Unable to load threshold review workspace.");
      setRecords([]);
    } finally {
      setLoading(false);
    }
  }

  async function loadRecords(cameraIdOverride = selectedCameraId) {
    try {
      const data = await getRecognitionReviewRecords({
        cameraId: cameraIdOverride || undefined,
        reviewStatus: reviewStatus || undefined,
        limit: 500
      });
      const nextRecords = data?.records || [];
      setRecords(nextRecords);
      setNoteDrafts(
        nextRecords.reduce((accumulator, record) => {
          accumulator[record.id] = record.review_note || "";
          return accumulator;
        }, {})
      );
    } catch (error) {
      setMessage(error.message || "Unable to load threshold review records.");
      setRecords([]);
    }
  }

  async function handleSaveVerdict(recordId, reviewValue) {
    setSavingId(recordId);
    setMessage("");

    try {
      await updateRecognitionReviewVerdict(recordId, {
        reviewStatus: reviewValue,
        note: noteDrafts[recordId] || ""
      });
      setMessage("Review verdict updated.");
      await loadRecords();
    } catch (error) {
      setMessage(error.message || "Unable to update verdict.");
    } finally {
      setSavingId(null);
    }
  }

  async function handleExport() {
    setExporting(true);
    setMessage("");

    try {
      await exportRecognitionReviewCsv({
        cameraId: selectedCameraId || undefined,
        reviewStatus: reviewStatus || undefined
      });
      setMessage("Recognition review CSV exported.");
    } catch (error) {
      setMessage(error.message || "Unable to export CSV.");
    } finally {
      setExporting(false);
    }
  }

  async function handleReset() {
    if (!window.confirm("Clear the stored threshold review records for the selected camera?")) {
      return;
    }

    setResetting(true);
    setMessage("");

    try {
      await resetRecognitionReviewRecords(selectedCameraId ? Number(selectedCameraId) : null);
      setMessage("Threshold review records cleared.");
      await loadRecords();
    } catch (error) {
      setMessage(error.message || "Unable to reset threshold review records.");
    } finally {
      setResetting(false);
    }
  }

  const selectedCameraName = useMemo(() => {
    const selected = cameras.find((camera) => String(camera.id) === String(selectedCameraId));
    return selected?.name || "All cameras";
  }, [cameras, selectedCameraId]);

  return (
    <AppShell
      title="Threshold Review"
      subtitle="Review the best recognition evidence per predicted student, compare top scores, and export truth labels for threshold tuning."
      eyebrow="Recognition"
      breadcrumbs={[
        { label: "Recognition", to: "/recognition/validation" },
        { label: "Threshold Review" }
      ]}
      actions={(
        <>
          <button className="secondary-button" onClick={() => loadRecords()} type="button">
            Refresh
          </button>
          <button className="secondary-button" onClick={handleExport} type="button">
            {exporting ? "Exporting..." : "Export CSV"}
          </button>
          <button className="danger-button" onClick={handleReset} type="button">
            {resetting ? "Clearing..." : "Reset camera"}
          </button>
        </>
      )}
    >
      {message ? <p className="inline-note">{message}</p> : null}

      <section className="panel">
        <div className="section-header">
          <div>
            <h3>Review filters</h3>
            <p>Showing best evidence rows for {selectedCameraName}.</p>
          </div>
        </div>

        <div className="filters-grid">
          <label className="filter-field">
            <span>Camera</span>
            <select onChange={(event) => setSelectedCameraId(event.target.value)} value={selectedCameraId}>
              {cameras.map((camera) => (
                <option key={camera.id} value={camera.id}>{camera.name}</option>
              ))}
            </select>
          </label>

          <label className="filter-field">
            <span>Review status</span>
            <select onChange={(event) => setReviewStatus(event.target.value)} value={reviewStatus}>
              <option value="">All</option>
              <option value="unreviewed">Unreviewed</option>
              <option value="correct">Correct</option>
              <option value="incorrect">Incorrect</option>
            </select>
          </label>
        </div>
      </section>

      <section className="panel">
        <div className="section-header">
          <div>
            <h3>Threshold review table</h3>
            <p>Each row keeps only the highest score seen so far for that predicted student on this camera.</p>
          </div>
        </div>

        <div className="table-shell">
          <table>
            <thead>
              <tr>
                <th>Face</th>
                <th>Predicted student</th>
                <th>Top-1</th>
                <th>Threshold</th>
                <th>Top-2</th>
                <th>Top-3</th>
                <th>Matched view</th>
                <th>First seen</th>
                <th>Last seen</th>
                <th>Detections</th>
                <th>Verdict</th>
                <th>Note</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td className="table-empty" colSpan="12">Loading threshold review data...</td>
                </tr>
              ) : null}
              {!loading && !records.length ? (
                <tr>
                  <td className="table-empty" colSpan="12">No threshold review records yet.</td>
                </tr>
              ) : null}
              {!loading ? records.map((record) => (
                <tr key={record.id}>
                  <td>
                    {record.snapshot_url && !hiddenImages[record.id] ? (
                      <a href={record.snapshot_url} target="_blank" rel="noreferrer">
                        <img
                          alt={record.predicted_name || "Recognition face"}
                          onError={() => setHiddenImages((current) => ({ ...current, [record.id]: true }))}
                          src={record.snapshot_url}
                          style={{ width: "72px", height: "72px", objectFit: "cover", borderRadius: "12px" }}
                        />
                      </a>
                    ) : (
                      <div className="table-empty">No image</div>
                    )}
                  </td>
                  <td>
                    <strong>{record.predicted_name || "-"}</strong>
                    <div className="inline-note">#{record.predicted_profile_id || "-"}</div>
                  </td>
                  <td>{formatScore(record.top1_score)}</td>
                  <td>{formatScore(record.applied_threshold)}</td>
                  <td>{record.top2_name ? `${record.top2_name} (${formatScore(record.top2_score)})` : "-"}</td>
                  <td>{record.top3_name ? `${record.top3_name} (${formatScore(record.top3_score)})` : "-"}</td>
                  <td>{record.matched_view || "-"}</td>
                  <td>{formatTimestamp(record.first_seen_at)}</td>
                  <td>{formatTimestamp(record.last_seen_at)}</td>
                  <td>{record.detection_count || 0}</td>
                  <td>
                    <select
                      onChange={(event) => handleSaveVerdict(record.id, event.target.value)}
                      value={record.review_status || "unreviewed"}
                    >
                      <option value="unreviewed">Unreviewed</option>
                      <option value="correct">Correct</option>
                      <option value="incorrect">Incorrect</option>
                    </select>
                    {savingId === record.id ? <div className="inline-note">Saving...</div> : null}
                  </td>
                  <td>
                    <textarea
                      onChange={(event) => setNoteDrafts((current) => ({ ...current, [record.id]: event.target.value }))}
                      placeholder="Optional note"
                      rows={3}
                      value={noteDrafts[record.id] || ""}
                    />
                    <button
                      className="secondary-button"
                      onClick={() => handleSaveVerdict(record.id, record.review_status || "unreviewed")}
                      type="button"
                    >
                      Save note
                    </button>
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
function formatTimestamp(value) {
  return formatDateTimeInAppTimezone(value);
}
