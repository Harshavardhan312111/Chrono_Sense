export const adminTabs = [
  { id: "dashboard", label: "DASHBOARD" },
  { id: "attendance", label: "TODAY'S ATTENDANCE" },
  { id: "profiles", label: "PROFILES" },
  { id: "reports", label: "REPORTS" }
];

function padDatePart(value) {
  return String(value).padStart(2, "0");
}

function formatLocalDateInputValue(date) {
  return [
    date.getFullYear(),
    padDatePart(date.getMonth() + 1),
    padDatePart(date.getDate())
  ].join("-");
}

export function getTodayDateInputValue() {
  return formatLocalDateInputValue(new Date());
}

export function getCurrentMonthInputValue() {
  return getTodayDateInputValue().slice(0, 7);
}

export function getWeekStartDateInputValue(date = new Date()) {
  const weekDate = new Date(date);
  const day = weekDate.getDay();
  const diff = day === 0 ? -6 : 1 - day;

  weekDate.setDate(weekDate.getDate() + diff);

  return formatLocalDateInputValue(weekDate);
}

export function addDays(dateString, days) {
  const date = new Date(`${dateString}T00:00:00`);
  date.setDate(date.getDate() + days);
  return formatLocalDateInputValue(date);
}

export function getDateRangeForMonth(monthValue) {
  const [year, month] = monthValue.split("-").map(Number);
  const start = `${monthValue}-01`;
  const endDate = new Date(year, month, 0);
  const end = formatLocalDateInputValue(endDate);

  return { start, end };
}

export function enumerateDatesBetween(startDate, endDate) {
  if (!startDate || !endDate || startDate > endDate) {
    return [];
  }

  const dates = [];
  const current = new Date(`${startDate}T00:00:00`);
  const end = new Date(`${endDate}T00:00:00`);

  while (current <= end) {
    dates.push(formatLocalDateInputValue(current));
    current.setDate(current.getDate() + 1);
  }

  return dates;
}

export function formatDate(dateString) {
  if (!dateString) {
    return "-";
  }

  return new Date(dateString).toLocaleDateString();
}

export function formatDuration(durationMinutes) {
  if (!durationMinutes) {
    return "0 min";
  }

  const hours = Math.floor(durationMinutes / 60);
  const minutes = durationMinutes % 60;

  if (!hours) {
    return `${minutes} min`;
  }

  if (!minutes) {
    return `${hours} hr`;
  }

  return `${hours} hr ${minutes} min`;
}

export function buildAttendanceRows({ records, absentMembers }) {
  const normalizedRows = (records || []).map((record) => ({
    ...record,
    id: record.id ?? record.profile_id,
    profile_id: record.profile_id ?? record.id,
    status: record.status || "absent"
  }));

  const seenIds = new Set(
    normalizedRows
      .map((record) => record.profile_id ?? record.id)
      .filter((value) => value !== undefined && value !== null)
  );

  const absentRows = (absentMembers || [])
    .filter((record) => !seenIds.has(record.profile_id ?? record.id))
    .map((record) => ({
      ...record,
      id: record.id ?? record.profile_id,
      profile_id: record.profile_id ?? record.id,
      check_in_time: record.check_in_time || "-",
      check_out_time: record.check_out_time || "-",
      duration_minutes: record.duration_minutes || 0,
      location: record.location || "-",
      frame_path: record.frame_path || null,
      status: record.status || "absent"
    }));

  return [...normalizedRows, ...absentRows];
}
