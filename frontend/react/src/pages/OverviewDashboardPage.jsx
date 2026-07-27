import { useEffect, useMemo, useState } from "react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis
} from "recharts";
import { Link } from "react-router-dom";
import { AppShell } from "../components/AppShell";
import { getRoleView } from "../lib/roleViews";
import { getAttendanceDashboardAnalytics, getOperationsSnapshot, getOverviewAnalytics } from "../lib/admin";
import { useAuth } from "../state/auth";
import { formatDate, getTodayDateInputValue } from "./admin-data";

const CHART_COLORS = ["#0f766e", "#f59e0b", "#ef4444", "#2563eb", "#7c3aed", "#14b8a6"];

const initialOverviewState = {
  summary: {
    profiles_completed: 0,
    profiles_incomplete: 0,
    cameras_added: 0,
    cameras_working: 0,
    present_today: 0,
    absent_today: 0,
    attendance_rate_today: 0
  },
  filter_options: {
    classes: [],
    sections_by_class: {},
    camera_names: []
  },
  charts: {
    attendance_trend: [],
    class_comparison: [],
    status_distribution: [],
    check_in_distribution: [],
    camera_health: {
      summary: {
        total: 0,
        connected: 0,
        disconnected: 0,
        recognition_running: 0
      },
      records: []
    }
  },
  tables: {
    class_rollup: [],
    recent_attendance_records: []
  }
};

function ChartCard({ title, subtitle, controls = null, children }) {
  return (
    <article className="panel overview-chart-card">
      <div className="section-header">
        <div>
          <h3>{title}</h3>
          <p>{subtitle}</p>
        </div>
        {controls ? <div className="section-actions">{controls}</div> : null}
      </div>
      {children}
    </article>
  );
}

function EmptyChartState({ message }) {
  return <div className="table-empty overview-chart-empty">{message}</div>;
}

function formatAxisLabel(value) {
  if (!value) {
    return "-";
  }
  if (/^\d{4}-\d{2}-\d{2}$/.test(value)) {
    return formatDate(value);
  }
  return value;
}

function getSelectedValues(event) {
  return Array.from(event.target.selectedOptions).map((option) => option.value);
}

function safePercent(value, total) {
  if (!total) {
    return 0;
  }
  return Math.round((Number(value || 0) / Number(total || 0)) * 100);
}

function isOverviewMeaningfullyPopulated(payload) {
  const data = payload?.data || payload || {};
  const summary = data.summary || {};
  const charts = data.charts || {};
  const tables = data.tables || {};

  return [
    Number(summary.profiles_completed || 0),
    Number(summary.profiles_incomplete || 0),
    Number(summary.cameras_added || 0),
    Number(summary.cameras_working || 0),
    Number(summary.present_today || 0),
    Number(summary.absent_today || 0),
    Number(summary.attendance_rate_today || 0),
    Array.isArray(charts.attendance_trend) ? charts.attendance_trend.length : 0,
    Array.isArray(charts.class_comparison) ? charts.class_comparison.length : 0,
    Array.isArray(charts.status_distribution) ? charts.status_distribution.length : 0,
    Array.isArray(charts.check_in_distribution) ? charts.check_in_distribution.length : 0,
    Array.isArray(tables.class_rollup) ? tables.class_rollup.length : 0,
    Array.isArray(tables.recent_attendance_records) ? tables.recent_attendance_records.length : 0
  ].some((value) => value > 0);
}

function buildFallbackOverviewAnalytics({ dashboard, snapshot, filters, trendGroupBy, currentOverview }) {
  const dashboardData = dashboard?.data || dashboard || {};
  const snapshotData = snapshot?.data || snapshot || {};
  const attendance = snapshotData.attendance || dashboardData || {};
  const records = attendance.attendance_records || [];
  const trends = attendance.historical_trends?.daily || [];
  const todayKpis = attendance.today_kpis || {};
  const cameras = snapshotData.cameras || [];
  const completion = snapshotData.profile_completion || {};
  const selectedRoleScope = filters.roleScope || attendance.scope?.role_scope || "all";
  const selectedDate = filters.endDate || filters.startDate;
  const selectedClasses = new Set(filters.classNames || []);
  const selectedSections = new Set(filters.sectionNames || []);

  const scopedRecords = records.filter((record) => {
    if (selectedRoleScope === "student" && record.profile_type !== "student") {
      return false;
    }
    if (selectedRoleScope === "faculty" && record.profile_type !== "faculty") {
      return false;
    }
    if (selectedClasses.size && !selectedClasses.has(record.class_name)) {
      return false;
    }
    if (selectedSections.size && !selectedSections.has(record.section_name)) {
      return false;
    }
    return true;
  });

  const groupedMap = new Map();
  for (const record of scopedRecords) {
    const group = filters.compareMode === "sections"
      ? `${record.class_name || "Unassigned"}-${record.section_name || "General"}`
      : filters.compareMode === "none"
        ? (record.class_name || record.section_name || record.profile_type || "Current scope")
        : (record.class_name || record.profile_type || "Unassigned");
    if (!groupedMap.has(group)) {
      groupedMap.set(group, {
        group,
        present: 0,
        absent: 0,
        late: 0,
        total: 0,
        incomplete_profiles: 0
      });
    }
    const entry = groupedMap.get(group);
    entry.total += 1;
    if (record.status === "late") {
      entry.present += 1;
      entry.late += 1;
    } else if (record.status === "present") {
      entry.present += 1;
    } else {
      entry.absent += 1;
    }
  }

  const classRollup = Array.from(groupedMap.values())
    .map((row) => ({
      ...row,
      absent: row.absent || Math.max(row.total - row.present, 0),
      attendance_rate: safePercent(row.present, row.total)
    }))
    .sort((left, right) => right.total - left.total || left.group.localeCompare(right.group));

  const statusCounts = scopedRecords.reduce((accumulator, record) => {
    const status = record.status === "late" ? "Late" : record.status === "present" ? "Present" : "Absent";
    accumulator[status] = (accumulator[status] || 0) + 1;
    return accumulator;
  }, {});

  const checkInBuckets = scopedRecords.reduce((accumulator, record) => {
    const checkInTime = record.check_in_display || record.check_in_time || "";
    const hour = String(checkInTime).slice(0, 2);
    if (!hour || Number.isNaN(Number(hour))) {
      return accumulator;
    }
    const bucket = `${hour}:00`;
    accumulator[bucket] = (accumulator[bucket] || 0) + 1;
    return accumulator;
  }, {});

  const cameraHealth = {
    summary: {
      total: cameras.length,
      connected: cameras.filter((camera) => camera.connection === "connected").length,
      disconnected: cameras.filter((camera) => camera.connection !== "connected").length,
      recognition_running: cameras.filter((camera) => camera.recognition_running || camera.recognitionRunning).length
    },
    records: cameras.map((camera) => ({
      id: camera.id,
      name: camera.name,
      connection: camera.connection || "disconnected",
      recognition_running: Boolean(camera.recognition_running || camera.recognitionRunning)
    }))
  };

  return {
    ...currentOverview,
    summary: {
      profiles_completed: completion.completed || 0,
      profiles_incomplete: completion.incomplete || 0,
      cameras_added: cameras.length,
      cameras_working: cameraHealth.summary.connected,
      present_today: todayKpis.present_today || statusCounts.Present || 0,
      absent_today: todayKpis.absent_today || statusCounts.Absent || 0,
      attendance_rate_today: Math.round(todayKpis.attendance_rate_today || safePercent(todayKpis.present_today || statusCounts.Present || 0, todayKpis.total_profiles || scopedRecords.length || 0))
    },
    filter_options: currentOverview.filter_options,
    charts: {
      attendance_trend: trends.map((row) => ({
        date: row.date,
        present: row.present || 0,
        absent: row.absent || 0,
        late: row.attendance_rate || 0,
        total: (row.present || 0) + (row.absent || 0),
        attendance_rate: Math.round(row.attendance_rate || 0)
      })),
      class_comparison: classRollup.slice(0, 8),
      status_distribution: [
        { name: "Present", value: statusCounts.Present || 0 },
        { name: "Absent", value: statusCounts.Absent || 0 },
        { name: "Late", value: statusCounts.Late || 0 },
        { name: "Incomplete Profiles", value: completion.incomplete || 0 }
      ],
      check_in_distribution: Object.keys(checkInBuckets)
        .sort()
        .map((bucket) => ({ bucket, count: checkInBuckets[bucket] })),
      camera_health: cameraHealth
    },
    tables: {
      class_rollup: classRollup,
      recent_attendance_records: scopedRecords.slice(0, 12).map((record) => ({
        profile_id: record.id || record.profile_id,
        name: record.name,
        status: record.status,
        check_in_time: record.check_in_display || record.check_in_time || "-",
        check_out_time: record.check_out_display || record.check_out_time || "-",
        last_location: record.last_location || "-",
        class_name: record.class_name,
        section_name: record.section_name,
        profile_type: record.profile_type || selectedRoleScope
      }))
    },
    scope: {
      ...currentOverview.scope,
      date: selectedDate,
      start_date: filters.startDate,
      end_date: filters.endDate,
      role_scope: selectedRoleScope,
      group_by: trendGroupBy
    }
  };
}

function mergeDashboardAnalytics(responses = []) {
  const dashboards = responses
    .map((response) => response?.data || response)
    .filter(Boolean);

  if (!dashboards.length) {
    return null;
  }

  if (dashboards.length === 1) {
    return dashboards[0];
  }

  const mergedTrendMap = new Map();
  const mergedRecords = [];
  let totalProfiles = 0;
  let totalPresent = 0;
  let totalAbsent = 0;

  for (const dashboard of dashboards) {
    const todayKpis = dashboard.today_kpis || {};
    totalProfiles += Number(todayKpis.total_profiles || 0);
    totalPresent += Number(todayKpis.present_today || 0);
    totalAbsent += Number(todayKpis.absent_today || 0);
    mergedRecords.push(...(dashboard.attendance_records || []));

    for (const row of dashboard.historical_trends?.daily || []) {
      const existing = mergedTrendMap.get(row.date) || {
        date: row.date,
        present: 0,
        absent: 0,
        total: 0,
        attendance_rate: 0
      };
      existing.present += Number(row.present || 0);
      existing.absent += Number(row.absent || 0);
      existing.total += Number(row.present || 0) + Number(row.absent || 0);
      mergedTrendMap.set(row.date, existing);
    }
  }

  const mergedDaily = Array.from(mergedTrendMap.values())
    .sort((left, right) => String(left.date).localeCompare(String(right.date)))
    .map((row) => ({
      ...row,
      attendance_rate: safePercent(row.present, row.total)
    }));

  const averageAttendanceRate = mergedDaily.length
    ? Math.round(mergedDaily.reduce((sum, row) => sum + Number(row.attendance_rate || 0), 0) / mergedDaily.length)
    : safePercent(totalPresent, totalProfiles);

  return {
    ...dashboards[0],
    today_kpis: {
      total_profiles: totalProfiles,
      present_today: totalPresent,
      absent_today: totalAbsent,
      attendance_rate_today: safePercent(totalPresent, totalProfiles)
    },
    historical_trends: {
      ...(dashboards[0].historical_trends || {}),
      daily: mergedDaily,
      summary: {
        total_days: mergedDaily.length,
        total_present: mergedDaily.reduce((sum, row) => sum + Number(row.present || 0), 0),
        total_absent: mergedDaily.reduce((sum, row) => sum + Number(row.absent || 0), 0),
        average_attendance_rate: averageAttendanceRate
      },
      best_day: mergedDaily.reduce((best, row) => !best || row.attendance_rate > best.attendance_rate ? row : best, null),
      worst_day: mergedDaily.reduce((worst, row) => !worst || row.attendance_rate < worst.attendance_rate ? row : worst, null)
    },
    attendance_records: mergedRecords
  };
}

export function OverviewDashboardPage() {
  const { user } = useAuth();
  const roleView = getRoleView(user?.role);
  const overviewView = roleView.overview || {};
  const today = getTodayDateInputValue();
  const scopedClasses = user?.scope?.class_names || [];
  const scopedSections = user?.scope?.section_names || [];
  const [filters, setFilters] = useState({
    startDate: today,
    endDate: today,
    roleScope: overviewView.defaultFilters?.roleScope || "all",
    classNames: user?.role === "class_teacher" ? scopedClasses : [],
    sectionNames: user?.role === "class_teacher" ? scopedSections : [],
    compareMode: overviewView.defaultFilters?.compareMode || "classes"
  });
  const [trendGroupBy, setTrendGroupBy] = useState("day");
  const [overview, setOverview] = useState(initialOverviewState);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState("");

  useEffect(() => {
    loadOverview();
  }, []);

  useEffect(() => {
    if (user?.role !== "class_teacher") {
      return;
    }

    setFilters((current) => ({
      ...current,
      roleScope: "student",
      classNames: scopedClasses.length ? scopedClasses : current.classNames,
      sectionNames: scopedSections.length ? scopedSections : current.sectionNames,
      compareMode: scopedSections.length > 1 ? "sections" : "none"
    }));
  }, [user?.role, scopedClasses, scopedSections]);

  const availableSections = useMemo(() => {
    const sectionsByClass = overview.filter_options?.sections_by_class || {};
    const sourceClasses = filters.classNames.length ? filters.classNames : Object.keys(sectionsByClass);
    return Array.from(
      new Set(
        sourceClasses.flatMap((className) => sectionsByClass[className] || [])
      )
    ).sort();
  }, [overview.filter_options, filters.classNames]);

  useEffect(() => {
    setFilters((current) => {
      const nextSectionNames = current.sectionNames.filter((sectionName) => availableSections.includes(sectionName));
      if (nextSectionNames.length === current.sectionNames.length) {
        return current;
      }
      return {
        ...current,
        sectionNames: nextSectionNames
      };
    });
  }, [availableSections]);

  async function loadOverview() {
    setLoading(true);
    setMessage("");

    try {
      const requestFilters = {
        date: filters.endDate,
        startDate: filters.startDate,
        endDate: filters.endDate,
        roleScope: filters.roleScope,
        classNames: filters.classNames,
        sectionNames: filters.sectionNames,
        groupBy: trendGroupBy,
        compareMode: filters.compareMode
      };
      const response = await getOverviewAnalytics(requestFilters);

      if (isOverviewMeaningfullyPopulated(response)) {
        setOverview(response?.data || initialOverviewState);
        return;
      }

      const dashboardRequests = filters.roleScope === "all"
        ? ["faculty", "student"]
        : [filters.roleScope];
      const [dashboardResponses, operationsResponse] = await Promise.all([
        Promise.all(
          dashboardRequests.map((roleScope) => getAttendanceDashboardAnalytics({
            date: filters.endDate,
            startDate: filters.startDate,
            endDate: filters.endDate,
            roleScope,
            className: roleScope === "student" ? filters.classNames[0] : undefined,
            sectionName: roleScope === "student" ? filters.sectionNames[0] : undefined
          }))
        ),
        getOperationsSnapshot(filters.endDate)
      ]);

      setOverview(buildFallbackOverviewAnalytics({
        dashboard: mergeDashboardAnalytics(dashboardResponses),
        snapshot: operationsResponse,
        filters,
        trendGroupBy,
        currentOverview: response?.data || initialOverviewState
      }));
      setMessage("Overview analytics were backfilled from live attendance and operations data.");
    } catch (error) {
      try {
        const dashboardRequests = filters.roleScope === "all"
          ? ["faculty", "student"]
          : [filters.roleScope];
        const [dashboardResponses, operationsResponse] = await Promise.all([
          Promise.all(
            dashboardRequests.map((roleScope) => getAttendanceDashboardAnalytics({
              date: filters.endDate,
              startDate: filters.startDate,
              endDate: filters.endDate,
              roleScope,
              className: roleScope === "student" ? filters.classNames[0] : undefined,
              sectionName: roleScope === "student" ? filters.sectionNames[0] : undefined
            }))
          ),
          getOperationsSnapshot(filters.endDate)
        ]);

        setOverview(buildFallbackOverviewAnalytics({
          dashboard: mergeDashboardAnalytics(dashboardResponses),
          snapshot: operationsResponse,
          filters,
          trendGroupBy,
          currentOverview: initialOverviewState
        }));
        setMessage("Overview analytics are using the live attendance fallback because the dedicated overview source was unavailable.");
      } catch (fallbackError) {
        setOverview(initialOverviewState);
        setMessage(fallbackError.message || error.message || "Unable to load overview analytics.");
      }
    } finally {
      setLoading(false);
    }
  }

  function updateFilter(name, value) {
    setFilters((current) => ({
      ...current,
      [name]: value
    }));
  }

  function resetFilters() {
    setFilters({
      startDate: today,
      endDate: today,
      roleScope: overviewView.defaultFilters?.roleScope || "all",
      classNames: user?.role === "class_teacher" ? scopedClasses : [],
      sectionNames: user?.role === "class_teacher" ? scopedSections : [],
      compareMode: user?.role === "class_teacher"
        ? (scopedSections.length > 1 ? "sections" : "none")
        : (overviewView.defaultFilters?.compareMode || "classes")
    });
    setTrendGroupBy("day");
  }

  const summary = overview.summary || initialOverviewState.summary;
  const trendData = overview.charts?.attendance_trend || [];
  const comparisonData = overview.charts?.class_comparison || [];
  const distributionData = overview.charts?.status_distribution || [];
  const checkInData = overview.charts?.check_in_distribution || [];
  const cameraHealth = overview.charts?.camera_health || initialOverviewState.charts.camera_health;
  const classRollup = overview.tables?.class_rollup || [];
  const recentAttendance = overview.tables?.recent_attendance_records || [];
  const lateToday = distributionData.find((entry) => String(entry.name || "").toLowerCase().includes("late"))?.value || 0;
  const classesBelowThreshold = classRollup.filter((row) => Number(row.attendance_rate || 0) < 75).length;
  const profileCompletionRate = summary.profiles_completed + summary.profiles_incomplete
    ? Math.round((summary.profiles_completed / (summary.profiles_completed + summary.profiles_incomplete)) * 100)
    : 0;
  const cameraUptime = summary.cameras_added ? Math.round((summary.cameras_working / summary.cameras_added) * 100) : 0;
  const attendanceRates = comparisonData.map((row) => Number(row.attendance_rate || 0)).filter((value) => Number.isFinite(value));
  const multiClassDelta = attendanceRates.length > 1 ? Math.max(...attendanceRates) - Math.min(...attendanceRates) : 0;
  const metricValues = {
    profiles_completed: summary.profiles_completed,
    profiles_incomplete: summary.profiles_incomplete,
    cameras_added: summary.cameras_added,
    cameras_working: summary.cameras_working,
    present_today: summary.present_today,
    absent_today: summary.absent_today,
    attendance_rate_today: `${summary.attendance_rate_today}%`,
    recognition_running: cameraHealth.summary?.recognition_running || 0,
    late_today: lateToday,
    classes_below_threshold: classesBelowThreshold,
    profile_completion_rate: `${profileCompletionRate}%`,
    camera_uptime: `${cameraUptime}%`,
    multi_class_delta: `${multiClassDelta}%`
  };
  const metricDescriptions = {
    profiles_completed: "Profiles with images uploaded and recognition training completed.",
    profiles_incomplete: "Saved profiles still waiting for face image completion.",
    cameras_added: "Total cameras configured in the system.",
    cameras_working: "Cameras currently reporting a connected state.",
    present_today: "Detected present profiles in the selected scope.",
    absent_today: "Profiles marked absent in the selected scope.",
    attendance_rate_today: "Attendance rate for the selected scope and date.",
    recognition_running: "Camera feeds actively running recognition right now.",
    late_today: "Late arrivals in your current attendance scope.",
    classes_below_threshold: "Classes currently below the attention threshold.",
    profile_completion_rate: "Profiles that are fully enrollment-ready.",
    camera_uptime: "Working cameras as a share of configured cameras.",
    multi_class_delta: "Spread between the highest and lowest class attendance rate."
  };
  const metricLabels = {
    profiles_completed: "Profiles Completed",
    profiles_incomplete: "Profiles Incomplete",
    cameras_added: "Cameras Added",
    cameras_working: "Cameras Working",
    present_today: "Present Today",
    absent_today: "Absent Today",
    attendance_rate_today: "Attendance Rate",
    recognition_running: "Recognition Running",
    late_today: "Late Today",
    classes_below_threshold: "Classes Below 75%",
    profile_completion_rate: "Profile Completion",
    camera_uptime: "Camera Uptime",
    multi_class_delta: "Class Delta"
  };
  const visibleKpis = overviewView.visibleKpis || [];
  const visibleCharts = new Set(overviewView.visibleCharts || []);
  const visibleTables = new Set(overviewView.visibleTables || []);
  const isTeacher = user?.role === "class_teacher";
  const isPrincipal = user?.role === "principal";
  const isDirector = user?.role === "director";
  const scopeSummary = [scopedClasses.join(", "), scopedSections.join(", ")].filter(Boolean).join(" • ");

  return (
    <AppShell
      title={overviewView.title || "Operations Overview"}
      subtitle={overviewView.subtitle || "Attendance, multi-class comparison, profile completion, and camera health in one filterable overview."}
      eyebrow={overviewView.eyebrow || "Overview"}
      breadcrumbs={[
        { label: "Overview", to: "/overview" },
        { label: "Dashboard" }
      ]}
      attentionCount={Math.max(summary.cameras_added - summary.cameras_working, 0)}
      actions={(
        <div className="hero-actions">
          <button className="secondary-button" onClick={loadOverview} type="button">
            Refresh
          </button>
          <button className="secondary-button" onClick={resetFilters} type="button">
            Reset filters
          </button>
        </div>
      )}
    >
      {message ? <p className="inline-note">{message}</p> : null}

      {overviewView.quickLinks?.length ? (
        <section className="panel">
          <div className="section-header">
            <div>
              <h3>Quick actions</h3>
              <p>Jump directly into the most common operational tasks for this role.</p>
            </div>
          </div>
          <div className="link-cluster overview-quick-links">
            {overviewView.quickLinks.map((link) => (
              <Link className="secondary-button quick-link-button" key={link.to} to={link.to}>
                {link.label}
              </Link>
            ))}
          </div>
        </section>
      ) : null}

      <section className="panel">
        <div className="section-header">
          <div>
            <h3>Overview filters</h3>
            <p>{isTeacher
              ? "Your assigned class scope is applied automatically so you can focus on classroom follow-up."
              : isDirector
                ? "Use shared filters for leadership analysis across classes and time ranges."
                : "Use shared filters for campus-level analysis, then adjust individual charts when needed."}</p>
          </div>
        </div>

        {scopeSummary ? (
          <div className="overview-scope-banner">
            <span className="badge-light">Data scope</span>
            <strong>{scopeSummary}</strong>
          </div>
        ) : null}

        <div className="report-filter-grid">
          <label className="filter-field">
            <span>From date</span>
            <input
              onChange={(event) => updateFilter("startDate", event.target.value)}
              type="date"
              value={filters.startDate}
            />
          </label>
          <label className="filter-field">
            <span>To date</span>
            <input
              onChange={(event) => updateFilter("endDate", event.target.value)}
              type="date"
              value={filters.endDate}
            />
          </label>
          {!isTeacher ? (
            <label className="filter-field">
              <span>Role scope</span>
              <select
                onChange={(event) => updateFilter("roleScope", event.target.value)}
                value={filters.roleScope}
              >
                <option value="all">All</option>
                <option value="faculty">Faculty</option>
                <option value="student">Student</option>
              </select>
            </label>
          ) : null}
          <label className="filter-field">
            <span>Compare mode</span>
            <select
              disabled={isTeacher && scopedSections.length <= 1}
              onChange={(event) => updateFilter("compareMode", event.target.value)}
              value={filters.compareMode}
            >
              <option value="classes">Classes</option>
              <option value="sections">Sections</option>
              <option value="none">None</option>
            </select>
          </label>
          <label className="filter-field">
            <span>Classes</span>
            <select
              disabled={isTeacher}
              multiple
              onChange={(event) => updateFilter("classNames", getSelectedValues(event))}
              size={Math.min(4, Math.max(2, (overview.filter_options?.classes || []).length || 2))}
              value={filters.classNames}
            >
              {(overview.filter_options?.classes || []).map((className) => (
                <option key={className} value={className}>{className}</option>
              ))}
            </select>
          </label>
          <label className="filter-field">
            <span>Sections</span>
            <select
              disabled={isTeacher}
              multiple
              onChange={(event) => updateFilter("sectionNames", getSelectedValues(event))}
              size={Math.min(4, Math.max(2, availableSections.length || 2))}
              value={filters.sectionNames}
            >
              {availableSections.map((sectionName) => (
                <option key={sectionName} value={sectionName}>{sectionName}</option>
              ))}
            </select>
          </label>
        </div>
      </section>

      <section className="enterprise-kpi-band">
        {visibleKpis.map((metricKey) => (
          <article className={`metric-card ${isDirector ? "metric-card-executive" : ""}`} key={metricKey}>
            <span>{metricLabels[metricKey]}</span>
            <strong>{loading ? "..." : metricValues[metricKey]}</strong>
            <p>{metricDescriptions[metricKey]}</p>
          </article>
        ))}
      </section>

      <section className="overview-chart-grid">
        {visibleCharts.has("attendance_trend") ? (
        <ChartCard
          title="Attendance Trend"
          subtitle="Present, absent, and attendance rate across the selected range."
          controls={(
            <label className="filter-field compact">
              <span>Trend view</span>
              <select onChange={(event) => setTrendGroupBy(event.target.value)} value={trendGroupBy}>
                <option value="day">Daily</option>
                <option value="week">Weekly</option>
                <option value="month">Monthly</option>
              </select>
            </label>
          )}
        >
          {loading ? <EmptyChartState message="Loading attendance trend..." /> : null}
          {!loading && !trendData.length ? <EmptyChartState message="No attendance trend data for the selected range." /> : null}
          {!loading && trendData.length ? (
            <div className="overview-chart-wrap">
              <ResponsiveContainer width="100%" height={280}>
                <AreaChart data={trendData}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="date" tickFormatter={formatAxisLabel} />
                  <YAxis />
                  <Tooltip labelFormatter={formatAxisLabel} />
                  <Legend />
                  <Area dataKey="present" fill="#99f6e4" name="Present" stroke="#0f766e" type="monotone" />
                  <Area dataKey="absent" fill="#fecaca" name="Absent" stroke="#dc2626" type="monotone" />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          ) : null}
        </ChartCard>
        ) : null}

        {visibleCharts.has("class_comparison") ? (
        <ChartCard
          title="Class Comparison"
          subtitle={isTeacher ? "Assigned-class or section attendance comparison for your scope." : "Side-by-side attendance comparison across multiple classes or sections."}
        >
          {loading ? <EmptyChartState message="Loading class comparison..." /> : null}
          {!loading && !comparisonData.length ? <EmptyChartState message="No class comparison data for the selected scope." /> : null}
          {!loading && comparisonData.length ? (
            <div className="overview-chart-wrap">
              <ResponsiveContainer width="100%" height={280}>
                <BarChart data={comparisonData}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="group" interval={0} angle={-12} textAnchor="end" height={60} />
                  <YAxis />
                  <Tooltip />
                  <Legend />
                  <Bar dataKey="present" fill="#0f766e" name="Present" radius={[4, 4, 0, 0]} />
                  <Bar dataKey="absent" fill="#ef4444" name="Absent" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          ) : null}
        </ChartCard>
        ) : null}

        {visibleCharts.has("status_distribution") ? (
        <ChartCard
          title="Status Distribution"
          subtitle="Current mix of present, absent, late, and incomplete profiles."
        >
          {loading ? <EmptyChartState message="Loading status distribution..." /> : null}
          {!loading && !distributionData.length ? <EmptyChartState message="No status distribution data available." /> : null}
          {!loading && distributionData.length ? (
            <div className="overview-chart-wrap">
              <ResponsiveContainer width="100%" height={280}>
                <PieChart>
                  <Pie
                    cx="50%"
                    cy="50%"
                    data={distributionData}
                    dataKey="value"
                    innerRadius={58}
                    label
                    nameKey="name"
                    outerRadius={92}
                  >
                    {distributionData.map((entry, index) => (
                      <Cell fill={CHART_COLORS[index % CHART_COLORS.length]} key={entry.name} />
                    ))}
                  </Pie>
                  <Tooltip />
                  <Legend />
                </PieChart>
              </ResponsiveContainer>
            </div>
          ) : null}
        </ChartCard>
        ) : null}

        {visibleCharts.has("check_in_distribution") ? (
        <ChartCard
          title="Check-in Distribution"
          subtitle="Arrival pattern by hour based on recorded check-in times."
        >
          {loading ? <EmptyChartState message="Loading check-in distribution..." /> : null}
          {!loading && !checkInData.length ? <EmptyChartState message="No check-in distribution data available." /> : null}
          {!loading && checkInData.length ? (
            <div className="overview-chart-wrap">
              <ResponsiveContainer width="100%" height={280}>
                <BarChart data={checkInData}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="bucket" />
                  <YAxis />
                  <Tooltip />
                  <Bar dataKey="count" fill="#2563eb" name="Check-ins" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          ) : null}
        </ChartCard>
        ) : null}
      </section>

      {visibleCharts.has("camera_health") ? (
      <section className="overview-chart-grid overview-chart-grid-secondary">
        <ChartCard
          title="Camera Health"
          subtitle="Connected, disconnected, and recognition-running state by camera."
        >
          {loading ? <EmptyChartState message="Loading camera health..." /> : null}
          {!loading && !cameraHealth.records.length ? <EmptyChartState message="No camera health data available." /> : null}
          {!loading && cameraHealth.records.length ? (
            <>
              <section className="analytics-grid analytics-grid-bottom">
                <article className="metric-card">
                  <span>Total Cameras</span>
                  <strong>{cameraHealth.summary.total}</strong>
                  <p>Configured camera records in the system.</p>
                </article>
                <article className="metric-card">
                  <span>Connected</span>
                  <strong>{cameraHealth.summary.connected}</strong>
                  <p>Currently connected camera sources.</p>
                </article>
                <article className="metric-card">
                  <span>Disconnected</span>
                  <strong>{cameraHealth.summary.disconnected}</strong>
                  <p>Cameras needing connectivity attention.</p>
                </article>
                <article className="metric-card">
                  <span>Recognition Running</span>
                  <strong>{cameraHealth.summary.recognition_running}</strong>
                  <p>Cameras actively processing recognition.</p>
                </article>
              </section>
              <div className="table-shell">
                <table>
                  <thead>
                    <tr>
                      <th>Camera</th>
                      <th>Connection</th>
                      <th>Recognition</th>
                    </tr>
                  </thead>
                  <tbody>
                    {cameraHealth.records.map((camera) => (
                      <tr key={camera.id}>
                        <td>{camera.name}</td>
                        <td><span className={`status-pill ${camera.connection === "connected" ? "present" : "absent"}`}>{camera.connection}</span></td>
                        <td>{camera.recognition_running ? "Running" : "Stopped"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          ) : null}
        </ChartCard>
      </section>
      ) : null}

      {(isTeacher || isPrincipal) ? (
        <section className="panel">
          <div className="section-header">
            <div>
              <h3>{isTeacher ? "Classroom attention summary" : "School attention summary"}</h3>
              <p>{isTeacher
                ? "Emotion and activity analytics will expand here later; this card already surfaces the attendance follow-up context you need now."
                : "Use this summary as the read-only bridge between attendance signals and the next emotion/activity analytics phase."}</p>
            </div>
          </div>
          <div className="ops-card-grid wide">
            <article className="ops-card">
              <div className="ops-card-header">
                <strong>{summary.absent_today}</strong>
                <span className="badge-light">Absent today</span>
              </div>
              <p>{isTeacher ? "Students needing direct classroom follow-up." : "People missing from the school-wide attendance picture."}</p>
            </article>
            <article className="ops-card">
              <div className="ops-card-header">
                <strong>{lateToday}</strong>
                <span className="badge-light">Late arrivals</span>
              </div>
              <p>{isTeacher ? "Late arrivals in your assigned class scope." : "Late arrivals that may need section-level follow-up."}</p>
            </article>
          </div>
        </section>
      ) : null}

      <section className="analytics-two-column">
        {visibleTables.has("class_rollup") ? (
        <article className="panel">
          <div className="section-header">
            <div>
              <h3>{isDirector ? "Executive Rollup" : "Class Rollup"}</h3>
              <p>{isDirector
                ? "Compact attendance totals and profile readiness by comparison group."
                : "Compact attendance totals and incomplete-profile counts by current comparison group."}</p>
            </div>
          </div>
          <div className="table-shell">
            <table>
              <thead>
                <tr>
                  <th>Group</th>
                  <th>Present</th>
                  <th>Absent</th>
                  <th>Total</th>
                  <th>Rate</th>
                  <th>Incomplete</th>
                </tr>
              </thead>
              <tbody>
                {!classRollup.length ? (
                  <tr>
                    <td colSpan="6" className="table-empty">No rollup data for the selected scope.</td>
                  </tr>
                ) : classRollup.map((row) => (
                  <tr key={row.group}>
                    <td>{row.group}</td>
                    <td>{row.present}</td>
                    <td>{row.absent}</td>
                    <td>{row.total}</td>
                    <td>{row.attendance_rate}%</td>
                    <td>{row.incomplete_profiles}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </article>
        ) : null}

        {visibleTables.has("recent_attendance_records") ? (
        <article className="panel">
          <div className="section-header">
            <div>
              <h3>{isTeacher ? "Recent Student Attendance" : isPrincipal ? "Recent Attendance Signals" : "Recent Attendance"}</h3>
              <p>{isTeacher
                ? "Fast classroom scan of the most relevant attendance records in your scope."
                : isPrincipal
                  ? "Read-only operational scan of the most relevant attendance records in the current scope."
                  : "Fast operational scan of the most relevant attendance records in the current scope."}</p>
            </div>
          </div>
          <div className="table-shell">
            <table>
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Status</th>
                  <th>Check-in</th>
                  <th>Check-out</th>
                  <th>Location</th>
                </tr>
              </thead>
              <tbody>
                {!recentAttendance.length ? (
                  <tr>
                    <td colSpan="5" className="table-empty">No recent attendance records for the selected scope.</td>
                  </tr>
                ) : recentAttendance.map((record) => (
                  <tr key={`${record.profile_id}-${record.name}`}>
                    <td>{record.name}</td>
                    <td><span className={`status-pill ${record.status}`}>{record.status}</span></td>
                    <td>{record.check_in_time || "-"}</td>
                    <td>{record.check_out_time || "-"}</td>
                    <td>{record.last_location || "-"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </article>
        ) : null}
      </section>
    </AppShell>
  );
}
