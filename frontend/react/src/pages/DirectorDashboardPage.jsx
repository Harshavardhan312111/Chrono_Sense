import { useEffect, useState } from "react";
import { AppShell } from "../components/AppShell";
import {
  getAbsentMembers,
  getAttendanceCheckInOut,
  getProfiles
} from "../lib/admin";
import { formatDuration, getTodayDateInputValue } from "./admin-data";

function buildDirectorRows(records, profiles) {
  return (records || []).map((record) => {
    const recordId = record.id ?? record.profile_id;
    const profile = (profiles || []).find((item) => item.id === recordId);

    return {
      ...record,
      id: recordId,
      profile_id: record.profile_id ?? recordId,
      expected_check_in: profile?.check_in_time || "-",
      status: record.status || "absent"
    };
  });
}

export function DirectorDashboardPage() {
  const [date, setDate] = useState(getTodayDateInputValue());
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");
  const [rows, setRows] = useState([]);
  const [stats, setStats] = useState({
    present: 0,
    absent: 0,
    total: 0
  });

  useEffect(() => {
    loadDirectorAttendance(date);
  }, []);

  async function loadDirectorAttendance(selectedDate) {
    setLoading(true);
    setMessage("");

    try {
      const [attendanceData, absentData, profileData] = await Promise.all([
        getAttendanceCheckInOut(selectedDate),
        getAbsentMembers(selectedDate),
        getProfiles()
      ]);

      const profiles = profileData.profiles || [];
      const attendanceRows = attendanceData.records || [];
      const absentRows = absentData.records || [];
      const tableRows = buildDirectorRows(attendanceRows, profiles);
      const presentIds = new Set(
        attendanceRows
          .filter((row) => ["present", "late"].includes(String(row.status || "").toLowerCase()))
          .map((row) => row.id ?? row.profile_id)
      );

      setRows(tableRows);
      setStats({
        present: presentIds.size,
        absent: absentRows.length,
        total: profiles.length
      });
    } catch (error) {
      setRows([]);
      setStats({
        present: 0,
        absent: 0,
        total: 0
      });
      setMessage(error.message || "Unable to load director attendance view.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <AppShell
      title="Director attendance"
      subtitle="Read-only attendance review."
    >
      <section className="hero-panel">
        <div>
          <h2>Attendance overview</h2>
        </div>
      </section>

      <section className="card-grid">
        <article className="metric-card">
          <span>Present</span>
          <strong>{stats.present}</strong>
          <p>Detected today.</p>
        </article>
        <article className="metric-card">
          <span>Absent</span>
          <strong>{stats.absent}</strong>
          <p>Not seen today.</p>
        </article>
        <article className="metric-card">
          <span>Total</span>
          <strong>{stats.total}</strong>
          <p>Registered profiles.</p>
        </article>
      </section>

      <section className="panel">
        <div className="section-header">
          <div>
            <h3>Attendance detail</h3>
            <p>Director access is intentionally read-only in the React frontend.</p>
          </div>
          <div className="section-actions responsive-filters">
            <label className="filter-field">
              <span>Date</span>
              <input
                onChange={(event) => {
                  const value = event.target.value;
                  setDate(value);
                  loadDirectorAttendance(value);
                }}
                type="date"
                value={date}
              />
            </label>
          </div>
        </div>

        {message ? <p className="inline-note">{message}</p> : null}

        <div className="table-shell">
          <table>
            <thead>
              <tr>
                <th>Name</th>
                <th>Expected check-in</th>
                <th>Actual check-in</th>
                <th>Check-out</th>
                <th>Status</th>
                <th>Duration</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td colSpan="6" className="table-empty">Loading attendance...</td>
                </tr>
              ) : null}
              {!loading && !rows.length ? (
                <tr>
                  <td colSpan="6" className="table-empty">No attendance records available for this date.</td>
                </tr>
              ) : null}
              {!loading
                ? rows.map((row) => (
                    <tr key={row.id}>
                      <td><strong>{row.name}</strong></td>
                      <td>{row.expected_check_in}</td>
                      <td>{row.check_in || "-"}</td>
                      <td>{row.check_out || "-"}</td>
                      <td>
                        <span className={`status-pill ${row.status}`}>{row.status}</span>
                      </td>
                      <td>{formatDuration(row.duration)}</td>
                    </tr>
                  ))
                : null}
            </tbody>
          </table>
        </div>
      </section>
    </AppShell>
  );
}
