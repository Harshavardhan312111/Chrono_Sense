import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis
} from "recharts";
import { AppShell } from "../components/AppShell";
import { getRoleView } from "../lib/roleViews";
import {
  ROLE_CLASS_TEACHER,
  ROLE_DIRECTOR,
  ROLE_PRINCIPAL
} from "../lib/rbac";
import {
  getClassroomEmotions,
  getDayWiseEmotions,
  getEmotionTrends,
  getProfiles,
  getStudentEmotionTimeline
} from "../lib/admin";
import { useAuth } from "../state/auth";
import {
  formatDate,
  getTodayDateInputValue,
  getWeekStartDateInputValue
} from "./admin-data";

const CHART_COLORS = ["#0f766e", "#2563eb", "#f59e0b", "#ef4444", "#8b5cf6", "#14b8a6", "#ec4899", "#64748b"];

function getInitialFocus(mode, requestedFocus, role) {
  if (requestedFocus === "students") {
    return "students";
  }

  if (requestedFocus === "classes") {
    return "classes";
  }

  if (role === ROLE_CLASS_TEACHER) {
    return "students";
  }

  if (mode === "classes") {
    return "classes";
  }

  return "classes";
}

function sumEmotionCounts(locations) {
  return locations.reduce((accumulator, [, details]) => {
    Object.entries(details.emotions || {}).forEach(([emotion, count]) => {
      accumulator[emotion] = (accumulator[emotion] || 0) + Number(count || 0);
    });
    return accumulator;
  }, {});
}

function sumRawEmotionCounts(locations) {
  return locations.reduce((accumulator, [, details]) => {
    Object.entries(details.raw_emotions || {}).forEach(([emotion, count]) => {
      accumulator[emotion] = (accumulator[emotion] || 0) + Number(count || 0);
    });
    return accumulator;
  }, {});
}

function formatPercent(value) {
  return `${Math.round(Number(value || 0) * 100)}%`;
}

function formatEventTimestamp(value) {
  if (!value) {
    return "-";
  }
  const stringValue = String(value);
  if (stringValue.includes("T")) {
    return `${formatDate(stringValue.slice(0, 10))} ${stringValue.slice(11, 19)}`;
  }
  return stringValue;
}

function formatEmotionScores(scores) {
  return Object.entries(scores || {})
    .map(([emotion, score]) => ({ emotion, score: Number(score || 0) }))
    .filter((entry) => entry.score > 0)
    .sort((left, right) => right.score - left.score)
    .map((entry) => `${entry.emotion}: ${Math.round(entry.score * 100)}%`)
    .join(", ");
}

function getTimelineEmotionLabel(event, showAdvanced) {
  const smoothedEmotion = event?.smoothed_emotion;
  const usableEmotion = event?.emotion;
  const rawEmotion = event?.raw_emotion;

  if (showAdvanced) {
    if (smoothedEmotion && smoothedEmotion !== "LowSignal") {
      return smoothedEmotion;
    }
    if (rawEmotion) {
      return `${rawEmotion} (raw)`;
    }
    if (smoothedEmotion === "LowSignal") {
      return "Neutral";
    }
    return usableEmotion || "-";
  }

  if ((usableEmotion || rawEmotion) === "LowSignal") {
    return "Neutral";
  }
  return usableEmotion || rawEmotion || "Neutral";
}

function getTimelineEmotionScores(event) {
  if (event?.smoothed_emotion && event.smoothed_emotion !== "LowSignal") {
    return event.smoothed_scores || event.raw_scores || event.all_emotions;
  }
  return event?.raw_scores || event?.all_emotions || event?.smoothed_scores;
}

function getTimelineEmotionConfidence(event, showAdvanced) {
  if (showAdvanced && event?.smoothed_emotion && event.smoothed_emotion !== "LowSignal") {
    return event?.smoothed_confidence || event?.emotion_confidence || 0;
  }
  if (event?.smoothed_emotion === "LowSignal" && Number(event?.raw_confidence || 0) > 0) {
    return event.raw_confidence;
  }
  return event?.emotion_confidence || event?.smoothed_confidence || event?.raw_confidence || 0;
}

function normalizeTrendRows(dailyTrends) {
  return Object.entries(dailyTrends || {})
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([date, emotions]) => ({
      date,
      total: Object.values(emotions || {}).reduce((sum, count) => sum + Number(count || 0), 0),
      Happy: Number(emotions?.Happy || 0),
      Neutral: Number(emotions?.Neutral || 0),
      Surprise: Number(emotions?.Surprise || 0),
      Sad: Number(emotions?.Sad || 0),
      Angry: Number(emotions?.Angry || 0),
      Fear: Number(emotions?.Fear || 0),
      Disgust: Number(emotions?.Disgust || 0),
      Contempt: Number(emotions?.Contempt || 0)
    }));
}

function getTrendChartRows(trendData, noReliableTrendSignal) {
  if (!noReliableTrendSignal) {
    return normalizeTrendRows(trendData?.daily_trends);
  }
  return normalizeTrendRows(trendData?.daily_raw_trends);
}

function buildEmotionDistributionRows(counts) {
  return Object.entries(counts || {})
    .map(([name, value]) => ({ name, value: Number(value || 0) }))
    .sort((left, right) => right.value - left.value);
}

function getDistributionEntries(primaryDistribution, rawDistribution) {
  const primaryEntries = Object.entries(primaryDistribution || {});
  if (primaryEntries.length) {
    return primaryEntries;
  }
  return Object.entries(rawDistribution || {});
}

function getDiagnosticEmotionLabel(primaryEmotion, rawEmotion, totalDetections, usableDetections) {
  if (primaryEmotion) {
    return primaryEmotion;
  }
  if (Number(totalDetections || 0) > 0 && Number(usableDetections || 0) === 0 && rawEmotion) {
    return `${rawEmotion} (raw)`;
  }
  if (Number(totalDetections || 0) > 0 && Number(usableDetections || 0) === 0) {
    return "Neutral";
  }
  return "-";
}

export function EmotionAnalyticsPage({ mode }) {
  const { user } = useAuth();
  const roleView = getRoleView(user?.role);
  const [searchParams, setSearchParams] = useSearchParams();
  const [focus, setFocus] = useState(getInitialFocus(mode, searchParams.get("focus"), user?.role));
  const [date, setDate] = useState(getTodayDateInputValue());
  const [startDate, setStartDate] = useState(getWeekStartDateInputValue());
  const [endDate, setEndDate] = useState(getTodayDateInputValue());
  const [selectedLocation, setSelectedLocation] = useState("");
  const [selectedPersonId, setSelectedPersonId] = useState("");
  const [profileTypeFilter, setProfileTypeFilter] = useState(user?.role === ROLE_CLASS_TEACHER ? "student" : "all");
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [people, setPeople] = useState([]);
  const [classData, setClassData] = useState(null);
  const [studentData, setStudentData] = useState(null);
  const [trendData, setTrendData] = useState(null);
  const [dayWiseData, setDayWiseData] = useState(null);
  const [classLoading, setClassLoading] = useState(true);
  const [summaryLoading, setSummaryLoading] = useState(true);
  const [personLoading, setPersonLoading] = useState(false);
  const [peopleLoading, setPeopleLoading] = useState(true);
  const [message, setMessage] = useState("");
  const [personMessage, setPersonMessage] = useState("");

  const isTeacher = user?.role === ROLE_CLASS_TEACHER;
  const isPrincipal = user?.role === ROLE_PRINCIPAL;
  const isDirector = user?.role === ROLE_DIRECTOR;
  const scopeSummary = [
    ...(user?.scope?.class_names || []),
    ...(user?.scope?.section_names || [])
  ].join(" • ");

  useEffect(() => {
    const requestedFocus = searchParams.get("focus");
    if (requestedFocus === "students" || requestedFocus === "classes") {
      setFocus(requestedFocus);
    }
  }, [searchParams]);

  useEffect(() => {
    loadPeople();
  }, []);

  useEffect(() => {
    if (isTeacher) {
      setProfileTypeFilter("student");
    }
  }, [isTeacher]);

  useEffect(() => {
    loadClassEmotionData();
  }, [date, selectedLocation]);

  useEffect(() => {
    loadSummaryData();
  }, [date, startDate, endDate]);

  useEffect(() => {
    if (!selectedPersonId) {
      setStudentData(null);
      setPersonMessage("");
      return;
    }

    loadPersonEmotionData();
  }, [selectedPersonId, startDate, endDate, selectedLocation]);

  async function loadPeople() {
    setPeopleLoading(true);
    try {
      const profileData = await getProfiles();
      setPeople(profileData?.profiles || []);
    } catch (error) {
      setPeople([]);
      setPersonMessage(error.message || "Unable to load people.");
    } finally {
      setPeopleLoading(false);
    }
  }

  async function loadClassEmotionData() {
    setClassLoading(true);
    setMessage("");
    try {
      const classroomData = await getClassroomEmotions({
        date,
        location: selectedLocation || undefined
      });
      setClassData(classroomData);
    } catch (error) {
      setClassData(null);
      setMessage(error.message || "Unable to load classroom emotions.");
    } finally {
      setClassLoading(false);
    }
  }

  async function loadSummaryData() {
    setSummaryLoading(true);
    try {
      const [trendResponse, dayWiseResponse] = await Promise.all([
        getEmotionTrends({
          startDate,
          endDate
        }),
        getDayWiseEmotions({
          date
        })
      ]);
      setTrendData(trendResponse);
      setDayWiseData(dayWiseResponse);
    } catch (error) {
      setTrendData(null);
      setDayWiseData(null);
      setMessage(error.message || "Unable to load emotion trend analytics.");
    } finally {
      setSummaryLoading(false);
    }
  }

  async function loadPersonEmotionData() {
    setPersonLoading(true);
    setPersonMessage("");
    try {
      const timelineData = await getStudentEmotionTimeline(selectedPersonId, {
        startDate,
        endDate,
        location: selectedLocation || undefined
      });
      setStudentData(timelineData);
    } catch (error) {
      setStudentData(null);
      setPersonMessage(error.message || "Unable to load person emotion timeline.");
    } finally {
      setPersonLoading(false);
    }
  }

  function handleFocusChange(nextFocus) {
    setFocus(nextFocus);
    const nextParams = new URLSearchParams(searchParams);
    nextParams.set("focus", nextFocus);
    setSearchParams(nextParams, { replace: true });
  }

  const locations = useMemo(
    () => Object.entries(classData?.locations || {}),
    [classData]
  );
  const locationOptions = useMemo(
    () => locations.map(([location]) => location),
    [locations]
  );
  const filteredLocations = useMemo(() => {
    if (!selectedLocation) {
      return locations;
    }

    return locations.filter(([location]) => location === selectedLocation);
  }, [locations, selectedLocation]);
  const totalDetections = filteredLocations.reduce(
    (sum, [, details]) => sum + Number(details.total_detections || 0),
    0
  );
  const usableDetections = filteredLocations.reduce(
    (sum, [, details]) => sum + Number(details.usable_detections || 0),
    0
  );
  const lowSignalDetections = filteredLocations.reduce(
    (sum, [, details]) => sum + Number(details.low_signal_detections || 0),
    0
  );
  const leadingClassroom = filteredLocations[0]?.[1] || locations[0]?.[1] || null;
  const visiblePeople = useMemo(() => {
    const source = isTeacher
      ? people.filter((person) => person.profile_type === "student")
      : people;

    if (profileTypeFilter === "all") {
      return source;
    }

    return source.filter((person) => person.profile_type === profileTypeFilter);
  }, [people, profileTypeFilter, isTeacher]);
  const selectedPerson = people.find((person) => String(person.id) === String(selectedPersonId));
  const studentDistribution = Object.entries(studentData?.emotion_distribution || {});
  const studentRawDistribution = Object.entries(studentData?.raw_emotion_distribution || {});
  const studentEducationalDistribution = Object.entries(studentData?.educational_state_distribution || {});

  const aggregatedLocationCounts = sumEmotionCounts(filteredLocations);
  const aggregatedLocationRawCounts = sumRawEmotionCounts(filteredLocations);
  const classDistributionRows = buildEmotionDistributionRows(
    Object.keys(aggregatedLocationCounts).length ? aggregatedLocationCounts : aggregatedLocationRawCounts
  );
  const classVolumeRows = filteredLocations
    .map(([location, details]) => ({
      location,
      detections: Number(details.total_detections || 0),
      confidence: Math.round(Number(details.average_confidence || 0) * 100)
    }))
    .sort((left, right) => right.detections - left.detections);
  const noReliableClassSignal = totalDetections > 0 && usableDetections === 0;
  const trendUsableDetections = Number(trendData?.usable_detection_count || 0);
  const trendLowSignalDetections = Number(trendData?.low_signal_detection_count || 0);
  const noReliableTrendSignal = Number(trendData?.total_detection_count || 0) > 0 && trendUsableDetections === 0;
  const trendRows = getTrendChartRows(trendData, noReliableTrendSignal);
  const trendSummaryRows = buildEmotionDistributionRows(trendData?.overall_stats);
  const trendRawSummaryRows = buildEmotionDistributionRows(trendData?.overall_raw_stats);
  const trendEducationalRows = buildEmotionDistributionRows(trendData?.overall_educational_states);
  const peopleEmotionRows = Object.entries(dayWiseData?.distribution || {})
    .map(([profileId, details]) => {
      const matchedProfile = people.find((person) => String(person.id) === String(profileId));
      return {
        profileId,
        name: details.name || matchedProfile?.name || "Unknown",
        profileType: matchedProfile?.profile_type || "unknown",
        dominantEmotion: getDiagnosticEmotionLabel(
          details.dominant_emotion,
          details.dominant_raw_emotion,
          details.total_detections,
          details.usable_detections
        ),
        averageConfidence: Math.round(Number(details.average_confidence || 0) * 100),
        totalDetections: Number(details.total_detections || 0),
        usableDetections: Number(details.usable_detections || 0),
        lowSignalDetections: Number(details.low_signal_detections || 0)
      };
    })
    .filter((row) => {
      if (isTeacher) {
        return row.profileType === "student";
      }
      if (profileTypeFilter === "all") {
        return true;
      }
      return row.profileType === profileTypeFilter;
    })
    .sort((left, right) => right.totalDetections - left.totalDetections);

  return (
    <AppShell
      title={isTeacher ? "Class Emotion Analytics" : isDirector ? "Emotion Leadership Analytics" : "Emotion Analytics"}
      subtitle={isTeacher
        ? "Classroom emotion trends and student emotion timelines for your assigned scope."
        : isPrincipal
          ? "School-wide read-only emotion insights across classrooms, staff, and students."
          : isDirector
            ? "Leadership-facing classroom climate analytics across time, people, and locations."
            : "Role-aware emotion analytics for classrooms, people, and trend review using the existing sensing pipeline."}
      eyebrow="Emotion Detection"
      breadcrumbs={[
        { label: "Attendance", to: "/attendance/today" },
        { label: "Emotion Detection" }
      ]}
      actions={(
        <div className="hero-actions">
          <button
            className={`report-mode-button ${showAdvanced ? "active" : ""}`}
            onClick={() => setShowAdvanced((value) => !value)}
            type="button"
          >
            {showAdvanced ? "Advanced view" : "Basic view"}
          </button>
          <button
            className={`report-mode-button ${focus === "classes" ? "active" : ""}`}
            onClick={() => handleFocusChange("classes")}
            type="button"
          >
            Class-wise
          </button>
          <button
            className={`report-mode-button ${focus === "students" ? "active" : ""}`}
            onClick={() => handleFocusChange("students")}
            type="button"
          >
            Person-wise
          </button>
        </div>
      )}
    >
      <p className="inline-note">
        Emotion outputs are inferred model signals. Use them as classroom trend indicators, not exact psychological truth.
      </p>
      {scopeSummary ? (
        <div className="workspace-meta-inline">
          <span className="badge-light">{roleView.shell.scopeLabel}</span>
          <span className="workspace-scope-note">{scopeSummary}</span>
        </div>
      ) : null}
      {message ? <p className="inline-note">{message}</p> : null}
      {noReliableClassSignal ? (
        <p className="inline-note">
          Live detections are arriving, but none of the current classroom rows have passed the reliable emotion-signal filters yet.
        </p>
      ) : null}
      {noReliableTrendSignal ? (
        <p className="inline-note">
          The selected date range currently contains detections, but they are all low-signal or below the emotion quality threshold.
        </p>
      ) : null}

      <section className="card-grid">
        <article className="metric-card">
          <span>Locations reporting</span>
          <strong>{classLoading ? "..." : filteredLocations.length}</strong>
          <p>Camera locations reporting detections for {formatDate(date)}.</p>
        </article>
        <article className="metric-card">
          <span>Total detections</span>
          <strong>{classLoading ? "..." : totalDetections}</strong>
          <p>All emotion events seen in the current classroom scope before reliability filtering.</p>
        </article>
        <article className="metric-card">
          <span>Usable detections</span>
          <strong>{classLoading ? "..." : usableDetections}</strong>
          <p>Emotion events that passed the current low-signal and quality thresholds.</p>
        </article>
        <article className="metric-card">
          <span>Low-signal detections</span>
          <strong>{classLoading ? "..." : lowSignalDetections}</strong>
          <p>Events that were seen but suppressed as unreliable emotion readings.</p>
        </article>
        <article className="metric-card">
          <span>Leading emotion</span>
          <strong>{summaryLoading ? "..." : getDiagnosticEmotionLabel(
            trendData?.most_common_emotion || leadingClassroom?.dominant_emotion,
            trendData?.most_common_raw_emotion || leadingClassroom?.dominant_raw_emotion,
            trendData?.total_detection_count || totalDetections,
            trendData?.usable_detection_count || usableDetections
          )}</strong>
          <p>Most common usable signal across the selected range, with raw fallback when usable detections are zero.</p>
        </article>
        <article className="metric-card">
          <span>People sensed</span>
          <strong>{summaryLoading ? "..." : peopleEmotionRows.length}</strong>
          <p>Recognized people with logged emotion events on {formatDate(date)}.</p>
        </article>
        {showAdvanced ? (
          <>
            <article className="metric-card">
              <span>Derived signal</span>
              <strong>{summaryLoading ? "..." : trendData?.dominant_derived_emotion || "-"}</strong>
              <p>Most common interpreted human-emotion layer across the selected range.</p>
            </article>
            <article className="metric-card">
              <span>Education state</span>
              <strong>{summaryLoading ? "..." : trendData?.dominant_educational_state || "-"}</strong>
              <p>Most common educational state inferred from smoothed signals.</p>
            </article>
            <article className="metric-card">
              <span>Classroom climate</span>
              <strong>{summaryLoading ? "..." : trendData?.dominant_classroom_state || "-"}</strong>
              <p>Leading classroom climate across the selected date range.</p>
            </article>
            <article className="metric-card">
              <span>Avg engagement</span>
              <strong>{summaryLoading ? "..." : `${Math.round((trendData?.average_engagement || 0) * 100)}%`}</strong>
              <p>Average engagement score from the modernized pipeline.</p>
            </article>
          </>
        ) : null}
      </section>

      <section className="panel">
        <div className="section-header">
          <div>
            <h3>Emotion trend summary</h3>
            <p>Cross-day view of emotion volume across the selected date range for the current role scope.</p>
          </div>
          <div className="section-actions responsive-filters">
            <label className="filter-field compact">
              <span>Start</span>
              <input onChange={(event) => setStartDate(event.target.value)} type="date" value={startDate} />
            </label>
            <label className="filter-field compact">
              <span>End</span>
              <input onChange={(event) => setEndDate(event.target.value)} type="date" value={endDate} />
            </label>
            <button className="secondary-button" onClick={loadSummaryData} type="button">
              Refresh trends
            </button>
          </div>
        </div>

        <div className="overview-chart-grid">
          <article className="panel overview-chart-card">
            <div className="section-header">
              <div>
                <h3>Daily Emotion Volume</h3>
                <p>Happy, neutral, and negative signals over the selected period.</p>
              </div>
            </div>
            {summaryLoading ? <div className="table-empty">Loading emotion trends...</div> : null}
            {!summaryLoading && !trendRows.length ? (
              <div className="table-empty">
                {noReliableTrendSignal ? "Detections exist, but none passed the reliable emotion filters for this range." : "No trend rows available for this range."}
              </div>
            ) : null}
            {!summaryLoading && trendRows.length ? (
              <div className="overview-chart-wrap">
                <ResponsiveContainer width="100%" height={280}>
                  <LineChart data={trendRows}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="date" tickFormatter={formatDate} />
                    <YAxis />
                    <Tooltip labelFormatter={formatDate} />
                    <Legend />
                    <Line dataKey="Happy" dot={false} stroke="#0f766e" strokeWidth={2.5} type="monotone" />
                    <Line dataKey="Neutral" dot={false} stroke="#2563eb" strokeWidth={2.5} type="monotone" />
                    <Line dataKey="Sad" dot={false} stroke="#ef4444" strokeWidth={2.5} type="monotone" />
                    <Line dataKey="Angry" dot={false} stroke="#f59e0b" strokeWidth={2.5} type="monotone" />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            ) : null}
          </article>

          <article className="panel overview-chart-card">
            <div className="section-header">
              <div>
                <h3>Range Distribution</h3>
                <p>Overall emotion mix across the selected date range.</p>
              </div>
            </div>
            {summaryLoading ? <div className="table-empty">Loading emotion mix...</div> : null}
            {!summaryLoading && !trendSummaryRows.length && !trendRawSummaryRows.length ? (
              <div className="table-empty">
                {noReliableTrendSignal ? `Low-signal detections: ${trendLowSignalDetections}. No reliable overall emotion mix is available yet.` : "No overall emotion distribution available."}
              </div>
            ) : null}
            {!summaryLoading && (trendSummaryRows.length || trendRawSummaryRows.length) ? (
              <div className="overview-chart-wrap">
                <ResponsiveContainer width="100%" height={280}>
                  <PieChart>
                    <Pie
                      cx="50%"
                      cy="50%"
                      data={trendSummaryRows.length ? trendSummaryRows : trendRawSummaryRows}
                      dataKey="value"
                      innerRadius={56}
                      label
                      nameKey="name"
                      outerRadius={96}
                    >
                      {(trendSummaryRows.length ? trendSummaryRows : trendRawSummaryRows).map((entry, index) => (
                        <Cell fill={CHART_COLORS[index % CHART_COLORS.length]} key={entry.name} />
                      ))}
                    </Pie>
                    <Tooltip />
                    <Legend />
                  </PieChart>
                </ResponsiveContainer>
              </div>
            ) : null}
          </article>
          {showAdvanced ? (
            <article className="panel overview-chart-card">
              <div className="section-header">
                <div>
                  <h3>Educational State Mix</h3>
                  <p>Teacher-ready learning states derived from the smoothed emotion layer.</p>
                </div>
              </div>
              {summaryLoading ? <div className="table-empty">Loading educational states...</div> : null}
              {!summaryLoading && !trendEducationalRows.length ? <div className="table-empty">No educational state distribution available.</div> : null}
              {!summaryLoading && trendEducationalRows.length ? (
                <div className="overview-chart-wrap">
                  <ResponsiveContainer width="100%" height={280}>
                    <BarChart data={trendEducationalRows.slice(0, 8)}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis dataKey="name" interval={0} angle={-10} textAnchor="end" height={70} />
                      <YAxis />
                      <Tooltip />
                      <Bar dataKey="value" fill="#8b5cf6" radius={[4, 4, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              ) : null}
            </article>
          ) : null}
        </div>
      </section>

      {focus === "classes" ? (
        <section className="panel">
          <div className="section-header">
            <div>
              <h3>Class-wise emotions</h3>
              <p>Review classroom climate, dominant signals, and confidence by location.</p>
            </div>
          </div>

          <div className="toolbar-grid">
            <label className="filter-field compact">
              <span>Date</span>
              <input onChange={(event) => setDate(event.target.value)} type="date" value={date} />
            </label>
            <label className="filter-field compact">
              <span>Classroom</span>
              <select
                onChange={(event) => setSelectedLocation(event.target.value)}
                value={selectedLocation}
              >
                <option value="">All classrooms</option>
                {locationOptions.map((location) => (
                  <option key={location} value={location}>
                    {location}
                  </option>
                ))}
              </select>
            </label>
            <button className="secondary-button" onClick={loadClassEmotionData} type="button">
              Refresh classes
            </button>
          </div>

          <div className="overview-chart-grid">
            <article className="panel overview-chart-card">
              <div className="section-header">
                <div>
                  <h3>Emotion Mix by Classroom Scope</h3>
                  <p>Aggregated emotion balance across the selected classroom filter.</p>
                </div>
              </div>
              {classLoading ? <div className="table-empty">Loading classroom mix...</div> : null}
              {!classLoading && !classDistributionRows.length ? <div className="table-empty">No classroom emotion detections available for this filter yet.</div> : null}
              {!classLoading && classDistributionRows.length ? (
                <div className="overview-chart-wrap">
                  <ResponsiveContainer width="100%" height={280}>
                    <PieChart>
                      <Pie
                        cx="50%"
                        cy="50%"
                        data={classDistributionRows}
                        dataKey="value"
                        innerRadius={56}
                        outerRadius={96}
                        label
                        nameKey="name"
                      >
                        {classDistributionRows.map((entry, index) => (
                          <Cell fill={CHART_COLORS[index % CHART_COLORS.length]} key={entry.name} />
                        ))}
                      </Pie>
                      <Tooltip />
                      <Legend />
                    </PieChart>
                  </ResponsiveContainer>
                </div>
              ) : null}
            </article>

            <article className="panel overview-chart-card">
              <div className="section-header">
                <div>
                  <h3>Detection Volume by Location</h3>
                  <p>Emotion detections and average confidence per classroom location.</p>
                </div>
              </div>
              {classLoading ? <div className="table-empty">Loading classroom volumes...</div> : null}
              {!classLoading && !classVolumeRows.length ? <div className="table-empty">No classroom detection volumes available.</div> : null}
              {!classLoading && classVolumeRows.length ? (
                <div className="overview-chart-wrap">
                  <ResponsiveContainer width="100%" height={280}>
                    <BarChart data={classVolumeRows}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis dataKey="location" interval={0} angle={-10} textAnchor="end" height={60} />
                      <YAxis />
                      <Tooltip />
                      <Legend />
                      <Bar dataKey="detections" fill="#0f766e" name="Detections" radius={[4, 4, 0, 0]} />
                      <Bar dataKey="confidence" fill="#2563eb" name="Avg confidence %" radius={[4, 4, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              ) : null}
            </article>
          </div>

          <div className="ops-card-grid wide">
            {classLoading ? <div className="table-empty">Loading classroom emotions...</div> : null}
            {!classLoading && !filteredLocations.length ? <div className="table-empty">No classroom emotion detections available for this filter.</div> : null}
            {!classLoading ? filteredLocations.map(([location, details]) => (
              <article className="ops-card" key={location}>
                <div className="ops-card-header">
                  <strong>{location}</strong>
                  <span className="badge-light">{details.total_detections || 0} detections</span>
                </div>
                <p>Dominant emotion: {getDiagnosticEmotionLabel(details.dominant_emotion, details.dominant_raw_emotion, details.total_detections, details.usable_detections)}</p>
                <p>Average confidence: {Math.round((details.average_confidence || 0) * 100)}%</p>
                <p>Usable detections: {details.usable_detections || 0}</p>
                <p>Low-signal detections: {details.low_signal_detections || 0}</p>
                {showAdvanced ? <p>Derived emotion: {details.dominant_derived_emotion || "-"}</p> : null}
                {showAdvanced ? <p>Educational state: {details.dominant_educational_state || "-"}</p> : null}
                {showAdvanced ? <p>Classroom climate: {details.dominant_classroom_state || "-"}</p> : null}
                {showAdvanced ? <p>Avg engagement: {Math.round((details.average_engagement || 0) * 100)}%</p> : null}
                <p>Low-confidence suppressed: {details.suppressed_low_confidence_count || 0}</p>
                <p>Last updated: {details.last_updated || "-"}</p>
                <ul className="compact-stat-list">
                  {Object.entries(
                    showAdvanced
                      ? (details.educational_state_percentages || details.derived_emotion_percentages || details.emotion_percentages || {})
                      : (details.emotion_percentages && Object.keys(details.emotion_percentages).length
                        ? details.emotion_percentages
                        : (details.raw_emotion_percentages || {}))
                  ).slice(0, 5).map(([emotion, percent]) => (
                    <li key={`${location}-${emotion}`}>{emotion}: {percent}%</li>
                  ))}
                </ul>
              </article>
            )) : null}
          </div>
        </section>
      ) : null}

      {focus === "students" ? (
        <section className="panel">
          <div className="section-header">
            <div>
              <h3>Teacher and student emotions</h3>
              <p>{isTeacher
                ? "Review student emotion timelines and the strongest signals across your assigned class."
                : "Review confidence-gated emotion trends for teachers and students over a selected time range."}</p>
            </div>
          </div>

          {personMessage ? <p className="inline-note">{personMessage}</p> : null}

          <div className="toolbar-grid">
            {!isTeacher ? (
              <label className="filter-field compact">
                <span>Person type</span>
                <select
                  onChange={(event) => setProfileTypeFilter(event.target.value)}
                  value={profileTypeFilter}
                >
                  <option value="all">All people</option>
                  <option value="student">Students</option>
                  <option value="faculty">Teachers</option>
                </select>
              </label>
            ) : null}
            <label className="filter-field compact">
              <span>Person</span>
              <select
                onChange={(event) => setSelectedPersonId(event.target.value)}
                value={selectedPersonId}
              >
                <option value="">{peopleLoading ? "Loading people..." : "Select a person"}</option>
                {visiblePeople.map((person) => (
                  <option key={person.id} value={person.id}>
                    {person.name} ({person.profile_type === "faculty" ? "Teacher" : "Student"})
                  </option>
                ))}
              </select>
            </label>
            <label className="filter-field compact">
              <span>Start</span>
              <input onChange={(event) => setStartDate(event.target.value)} type="date" value={startDate} />
            </label>
            <label className="filter-field compact">
              <span>End</span>
              <input onChange={(event) => setEndDate(event.target.value)} type="date" value={endDate} />
            </label>
            <label className="filter-field compact">
              <span>Classroom</span>
              <select
                onChange={(event) => setSelectedLocation(event.target.value)}
                value={selectedLocation}
              >
                <option value="">All classrooms</option>
                {locationOptions.map((location) => (
                  <option key={`student-${location}`} value={location}>
                    {location}
                  </option>
                ))}
              </select>
            </label>
            <button
              className="secondary-button"
              disabled={!selectedPersonId}
              onClick={loadPersonEmotionData}
              type="button"
            >
              Refresh person
            </button>
          </div>

        <section className="card-grid">
            <article className="metric-card">
              <span>Person</span>
              <strong>{personLoading ? "..." : selectedPerson?.name || studentData?.name || "-"}</strong>
              <p>Recognized person tied to the selected timeline.</p>
            </article>
            <article className="metric-card">
              <span>Type</span>
              <strong>{personLoading ? "..." : selectedPerson?.profile_type === "faculty" ? "Teacher" : selectedPerson?.profile_type === "student" ? "Student" : "-"}</strong>
              <p>Profile type for the selected person.</p>
            </article>
            <article className="metric-card">
              <span>Dominant emotion</span>
              <strong>{personLoading ? "..." : getDiagnosticEmotionLabel(
                studentData?.dominant_emotion,
                studentData?.dominant_raw_emotion,
                studentData?.total_detections,
                studentData?.usable_detections
              )}</strong>
              <p>Most frequent usable emotion across the filtered range, with raw fallback when nothing passes filtering.</p>
            </article>
            <article className="metric-card">
              <span>Average confidence</span>
              <strong>{personLoading ? "..." : `${Math.round((studentData?.average_confidence || 0) * 100)}%`}</strong>
              <p>Mean emotion confidence across stored events.</p>
            </article>
            <article className="metric-card">
              <span>Total detections</span>
              <strong>{personLoading ? "..." : studentData?.total_detections || 0}</strong>
              <p>All stored emotion events in the selected window.</p>
            </article>
            <article className="metric-card">
              <span>Usable detections</span>
              <strong>{personLoading ? "..." : studentData?.usable_detections || 0}</strong>
              <p>Events that passed reliability filtering for this person.</p>
            </article>
            {showAdvanced ? (
              <>
                <article className="metric-card">
                  <span>Derived emotion</span>
                  <strong>{personLoading ? "..." : studentData?.dominant_derived_emotion || "-"}</strong>
                  <p>Most common interpreted human-emotion layer for the selected person.</p>
                </article>
                <article className="metric-card">
                  <span>Education state</span>
                  <strong>{personLoading ? "..." : studentData?.dominant_educational_state || "-"}</strong>
                  <p>Most common educational state across the selected window.</p>
                </article>
                <article className="metric-card">
                  <span>Attention</span>
                  <strong>{personLoading ? "..." : `${Math.round((studentData?.average_attention || 0) * 100)}%`}</strong>
                  <p>Average attention score across usable detections.</p>
                </article>
                <article className="metric-card">
                  <span>Engagement</span>
                  <strong>{personLoading ? "..." : `${Math.round((studentData?.average_engagement || 0) * 100)}%`}</strong>
                  <p>Average engagement score across usable detections.</p>
                </article>
              </>
            ) : null}
          </section>

          <div className="overview-chart-grid">
            <article className="panel overview-chart-card">
              <div className="section-header">
                <div>
                  <h3>Top People on {formatDate(date)}</h3>
                  <p>People with the highest number of emotion detections for the selected day.</p>
                </div>
              </div>
              {summaryLoading ? <div className="table-empty">Loading daily emotion profiles...</div> : null}
              {!summaryLoading && !peopleEmotionRows.length ? <div className="table-empty">No person emotion summaries available for this day.</div> : null}
              {!summaryLoading && peopleEmotionRows.length ? (
                <div className="overview-chart-wrap">
                  <ResponsiveContainer width="100%" height={280}>
                    <BarChart data={peopleEmotionRows.slice(0, 8)}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis dataKey="name" interval={0} angle={-10} textAnchor="end" height={70} />
                      <YAxis />
                      <Tooltip />
                      <Legend />
                      <Bar dataKey="totalDetections" fill="#0f766e" name="Detections" radius={[4, 4, 0, 0]} />
                      <Bar dataKey="averageConfidence" fill="#2563eb" name="Avg confidence %" radius={[4, 4, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              ) : null}
            </article>

            <article className="panel overview-chart-card">
              <div className="section-header">
                <div>
                  <h3>Selected Person Distribution</h3>
                  <p>{showAdvanced ? "Educational-state mix for the selected teacher or student." : "Emotion mix for the selected teacher or student."}</p>
                </div>
              </div>
              {!selectedPersonId ? <div className="table-empty">Choose a person to load their emotion distribution.</div> : null}
              {selectedPersonId && personLoading ? <div className="table-empty">Loading person emotions...</div> : null}
              {selectedPersonId && !personLoading && !(showAdvanced ? studentEducationalDistribution.length : getDistributionEntries(studentData?.emotion_distribution, studentData?.raw_emotion_distribution).length) ? <div className="table-empty">No person emotion events available for this filter.</div> : null}
              {selectedPersonId && !personLoading && (showAdvanced ? studentEducationalDistribution.length : getDistributionEntries(studentData?.emotion_distribution, studentData?.raw_emotion_distribution).length) ? (
                <div className="overview-chart-wrap">
                  <ResponsiveContainer width="100%" height={280}>
                    <PieChart>
                      <Pie
                        cx="50%"
                        cy="50%"
                        data={(showAdvanced
                          ? studentEducationalDistribution
                          : getDistributionEntries(studentData?.emotion_distribution, studentData?.raw_emotion_distribution)
                        ).map(([name, value]) => ({ name, value }))}
                        dataKey="value"
                        innerRadius={56}
                        outerRadius={96}
                        label
                        nameKey="name"
                      >
                        {(showAdvanced
                          ? studentEducationalDistribution
                          : getDistributionEntries(studentData?.emotion_distribution, studentData?.raw_emotion_distribution)
                        ).map(([name], index) => (
                          <Cell fill={CHART_COLORS[index % CHART_COLORS.length]} key={name} />
                        ))}
                      </Pie>
                      <Tooltip />
                      <Legend />
                    </PieChart>
                  </ResponsiveContainer>
                </div>
              ) : null}
            </article>
          </div>

          <div className="table-shell">
            <table>
              <thead>
                <tr>
                  <th>Timestamp</th>
                  <th>{showAdvanced ? "Smoothed emotion" : "Emotion"}</th>
                  {showAdvanced ? <th>Derived / state</th> : null}
                  <th>Emotion scores</th>
                  <th>Emotion confidence</th>
                  {showAdvanced ? <th>Quality</th> : null}
                  <th>Recognition confidence</th>
                  <th>Location</th>
                </tr>
              </thead>
              <tbody>
                {!selectedPersonId ? (
                  <tr><td className="table-empty" colSpan={showAdvanced ? 8 : 6}>Select a teacher or student to inspect the timeline.</td></tr>
                ) : null}
                {selectedPersonId && personLoading ? (
                  <tr><td className="table-empty" colSpan={showAdvanced ? 8 : 6}>Loading person timeline...</td></tr>
                ) : null}
                {selectedPersonId && !personLoading && !(studentData?.timeline || []).length ? (
                  <tr><td className="table-empty" colSpan={showAdvanced ? 8 : 6}>No timeline events available.</td></tr>
                ) : null}
                {selectedPersonId && !personLoading ? (studentData?.timeline || []).map((event) => (
                  <tr key={`${event.timestamp}-${event.emotion}-${event.location}`}>
                    <td>{formatEventTimestamp(event.timestamp)}</td>
                    <td>{getTimelineEmotionLabel(event, showAdvanced)}</td>
                    {showAdvanced ? <td>{event.educational_state || event.derived_emotion || "-"}</td> : null}
                    <td>{formatEmotionScores(getTimelineEmotionScores(event)) || "-"}</td>
                    <td>{formatPercent(getTimelineEmotionConfidence(event, showAdvanced))}</td>
                    {showAdvanced ? <td>{Math.round((event.quality_score || 0) * 100)}%</td> : null}
                    <td>{formatPercent(event.recognition_confidence || 0)}</td>
                    <td>{event.location || "-"}</td>
                  </tr>
                )) : null}
              </tbody>
            </table>
          </div>
        </section>
      ) : null}
    </AppShell>
  );
}
