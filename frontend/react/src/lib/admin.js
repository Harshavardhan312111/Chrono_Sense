import { apiRequest, getStoredToken } from "./api";

export async function getProfiles(filters = {}) {
  const params = new URLSearchParams();

  if (filters.profileType) {
    params.set("profile_type", filters.profileType);
  }

  if (filters.className) {
    params.set("class_name", filters.className);
  }

  if (filters.sectionName) {
    params.set("section_name", filters.sectionName);
  }

  const query = params.toString();
  return apiRequest(`/api/profiles${query ? `?${query}` : ""}`);
}

export async function deleteProfile(profileId) {
  return apiRequest(`/api/profiles/${profileId}`, {
    method: "DELETE"
  });
}

export async function updateProfile(profileId, updates) {
  const formData = new FormData();

  Object.entries(updates).forEach(([key, value]) => {
    if (value !== null && value !== undefined) {
      formData.append(key, value);
    }
  });

  return apiRequest(`/api/profiles/${profileId}`, {
    method: "PUT",
    body: formData
  });
}

export async function getAttendanceCheckInOut(date) {
  return apiRequest(`/api/attendance/check-in-out?date=${encodeURIComponent(date)}`);
}

export async function getAttendanceDashboardAnalytics({ date, startDate, endDate, roleScope, className, sectionName }) {
  const params = new URLSearchParams();

  if (date) {
    params.set("date", date);
  }

  if (startDate) {
    params.set("start_date", startDate);
  }

  if (endDate) {
    params.set("end_date", endDate);
  }

  if (roleScope) {
    params.set("role_scope", roleScope);
  }

  if (className) {
    params.set("class_name", className);
  }

  if (sectionName) {
    params.set("section_name", sectionName);
  }

  return apiRequest(`/api/attendance/dashboard?${params.toString()}`);
}

export async function getAttendanceMarkingStatus() {
  return apiRequest("/api/attendance/marking/status");
}

export async function startAttendanceMarking() {
  return apiRequest("/api/attendance/marking/start", {
    method: "POST"
  });
}

export async function stopAttendanceMarking() {
  return apiRequest("/api/attendance/marking/stop", {
    method: "POST"
  });
}

export async function getAbsentMembers(date) {
  return apiRequest(`/api/attendance/absent-members?date=${encodeURIComponent(date)}`);
}

export async function getLateArrivals(date) {
  return apiRequest(`/api/attendance/late-arrivals?date=${encodeURIComponent(date)}`);
}

function buildAttendanceReportQuery({
  reportType,
  date,
  weekStart,
  month,
  startDate,
  endDate
}) {
  const params = new URLSearchParams();

  params.set("report_type", reportType);

  if (date) {
    params.set("date", date);
  }

  if (weekStart) {
    params.set("week_start", weekStart);
  }

  if (month) {
    params.set("month", month);
  }

  if (startDate) {
    params.set("start_date", startDate);
  }

  if (endDate) {
    params.set("end_date", endDate);
  }

  return params.toString();
}

export async function getAttendanceReport(filters) {
  return apiRequest(`/api/attendance/reports?${buildAttendanceReportQuery(filters)}`);
}

export async function downloadAttendanceReportCsv({ fallbackFileName, ...filters }) {
  const token = getStoredToken();
  const response = await fetch(
    `/api/attendance/reports/export/csv?${buildAttendanceReportQuery(filters)}`,
    {
      headers: token ? { Authorization: `Bearer ${token}` } : {}
    }
  );

  if (!response.ok) {
    throw new Error("Unable to download report.");
  }

  const blob = await response.blob();
  const downloadUrl = window.URL.createObjectURL(blob);
  const link = document.createElement("a");
  const disposition = response.headers.get("content-disposition") || "";
  const matchedFileName = disposition.match(/filename="([^"]+)"/)?.[1];

  link.href = downloadUrl;
  link.download = matchedFileName || fallbackFileName || "attendance-report.csv";
  document.body.append(link);
  link.click();
  link.remove();
  window.URL.revokeObjectURL(downloadUrl);
}

export async function getUsersSafe() {
  try {
    return await apiRequest("/api/users");
  } catch {
    return null;
  }
}

export async function getCameras() {
  return apiRequest("/api/cameras");
}

export async function addCamera(camera) {
  return apiRequest("/api/cameras/add", {
    method: "POST",
    body: JSON.stringify(camera)
  });
}

export async function updateCamera(cameraId, camera) {
  return apiRequest(`/api/cameras/${cameraId}`, {
    method: "PUT",
    body: JSON.stringify(camera)
  });
}

export async function testCameraConnection(camera) {
  return apiRequest("/api/cameras/test", {
    method: "POST",
    body: JSON.stringify(camera)
  });
}

export async function deleteCamera(cameraId) {
  return apiRequest(`/api/cameras/${cameraId}`, {
    method: "DELETE"
  });
}

export async function getCameraStatus(cameraId) {
  return apiRequest(`/api/cameras/${cameraId}/status`);
}

export async function getCameraFaceDebug(cameraId) {
  return apiRequest(`/api/cameras/${cameraId}/face-debug`);
}

export async function setCameraProcessingEnabled(cameraId, processingEnabled) {
  return apiRequest(`/api/cameras/${cameraId}/processing-enabled`, {
    method: "POST",
    body: JSON.stringify({ processing_enabled: processingEnabled })
  });
}

export async function getEmotionLocations(date) {
  return apiRequest(`/api/emotions/by-location?date=${encodeURIComponent(date)}`);
}

export async function getDayWiseEmotions({ date, profileIds } = {}) {
  const params = new URLSearchParams();

  if (date) {
    params.set("date", date);
  }

  if (profileIds?.length) {
    params.set("profile_ids", profileIds.join(","));
  }

  return apiRequest(`/api/emotions/day-wise?${params.toString()}`);
}

export async function getEmotionTrends({ startDate, endDate, profileId } = {}) {
  const params = new URLSearchParams();

  if (startDate) {
    params.set("start_date", startDate);
  }

  if (endDate) {
    params.set("end_date", endDate);
  }

  if (profileId) {
    params.set("profile_id", String(profileId));
  }

  return apiRequest(`/api/emotions/trends?${params.toString()}`);
}

export async function getStudentEmotionTimeline(profileId, { startDate, endDate, location } = {}) {
  const params = new URLSearchParams();

  if (startDate) {
    params.set("start_date", startDate);
  }

  if (endDate) {
    params.set("end_date", endDate);
  }

  if (location) {
    params.set("location", location);
  }

  return apiRequest(`/api/emotions/students/${encodeURIComponent(profileId)}${params.toString() ? `?${params.toString()}` : ""}`);
}

export async function getClassroomEmotions({ location, date } = {}) {
  const params = new URLSearchParams();

  if (location) {
    params.set("location", location);
  }

  if (date) {
    params.set("date", date);
  }

  const query = params.toString();
  return apiRequest(`/api/classroom/emotions${query ? `?${query}` : ""}`);
}

export async function getEmotionRoomStatus() {
  return apiRequest("/api/cameras/emotion/room-status");
}

export async function getActivityLocations(date) {
  return apiRequest(`/api/classroom/activities?date=${encodeURIComponent(date)}`);
}

export async function getActivitiesByPerson(location) {
  const params = new URLSearchParams();

  if (location) {
    params.set("location", location);
  }

  const query = params.toString();
  return apiRequest(`/api/activities/by-person${query ? `?${query}` : ""}`);
}

export async function getActivityTimeline(location, hours = 24) {
  return apiRequest(`/api/classroom/activities/timeline/${encodeURIComponent(location)}?hours=${encodeURIComponent(hours)}`);
}

export async function getEngagementScore(location, date) {
  const params = new URLSearchParams();

  if (date) {
    params.set("date", date);
  }

  const query = params.toString();
  const payload = await apiRequest(`/api/classroom/activities${query ? `?${query}` : ""}${query ? "&" : "?"}location=${encodeURIComponent(location)}`);
  const details = payload?.locations?.[location] || {};
  return {
    location,
    engagement_score: Number(details.engagement_score || 0),
    engagement_level:
      Number(details.engagement_score || 0) >= 0.7
        ? "High"
        : Number(details.engagement_score || 0) >= 0.4
          ? "Medium"
          : "Low",
    dominant_student_activity: details.dominant_student_activity,
    dominant_faculty_activity: details.dominant_faculty_activity,
    dominant_context: details.dominant_context,
    total_windows: Number(details.total_windows || 0),
  };
}

export async function getClassroomActivitySummary({ date, className, sectionName } = {}) {
  const params = new URLSearchParams();

  if (date) {
    params.set("date", date);
  }
  if (className) {
    params.set("class_name", className);
  }
  if (sectionName) {
    params.set("section_name", sectionName);
  }

  return apiRequest(`/api/classroom/activities/summary${params.toString() ? `?${params.toString()}` : ""}`);
}

export async function getUniqueIndividuals() {
  return apiRequest("/api/system/unique-individuals");
}

export async function getOperationsSnapshot(date) {
  const params = new URLSearchParams();

  if (date) {
    params.set("date", date);
  }

  return apiRequest(`/api/operations/snapshot${params.toString() ? `?${params.toString()}` : ""}`);
}

export async function getOverviewAnalytics({
  date,
  startDate,
  endDate,
  roleScope,
  classNames,
  sectionNames,
  groupBy,
  compareMode
} = {}) {
  const params = new URLSearchParams();

  if (date) {
    params.set("date", date);
  }
  if (startDate) {
    params.set("start_date", startDate);
  }
  if (endDate) {
    params.set("end_date", endDate);
  }
  if (roleScope) {
    params.set("role_scope", roleScope);
  }
  if (classNames?.length) {
    params.set("class_names", classNames.join(","));
  }
  if (sectionNames?.length) {
    params.set("section_names", sectionNames.join(","));
  }
  if (groupBy) {
    params.set("group_by", groupBy);
  }
  if (compareMode) {
    params.set("compare_mode", compareMode);
  }

  return apiRequest(`/api/overview/analytics?${params.toString()}`);
}

export async function registerProfile(formData) {
  return apiRequest("/api/register", {
    method: "POST",
    body: formData
  });
}

export async function bulkUploadProfiles(formData) {
  return apiRequest("/api/profiles/bulk-upload", {
    method: "POST",
    body: formData
  });
}

export async function getValidationCameras() {
  return apiRequest("/api/cameras");
}

export async function getRecognitionStatus(cameraId) {
  return apiRequest(`/api/cameras/${cameraId}/recognition/status`);
}

export async function getAllRecognitionStatus() {
  return apiRequest("/api/cameras/recognition/status/all");
}

export async function startRecognition(cameraId) {
  return apiRequest(`/api/cameras/${cameraId}/recognition/start`, {
    method: "POST"
  });
}

export async function stopRecognition(cameraId) {
  return apiRequest(`/api/cameras/${cameraId}/recognition/stop`, {
    method: "POST"
  });
}

export async function startEmotionRecognition(cameraId) {
  return apiRequest(`/api/cameras/${cameraId}/emotion/start`, {
    method: "POST"
  });
}

export async function startAllEmotionRecognition() {
  return apiRequest("/api/cameras/emotion/start-all", {
    method: "POST"
  });
}

export async function stopAllEmotionRecognition() {
  return apiRequest("/api/cameras/emotion/stop-all", {
    method: "POST"
  });
}

export async function analyzeBrowserCameraFrame(formData) {
  return apiRequest("/api/browser-camera/analyze", {
    method: "POST",
    body: formData
  });
}

export async function getCurrentDetections(cameraId) {
  return apiRequest(`/api/cameras/${cameraId}/detections`);
}

export async function getRecognitionLogs({ cameraId, limit = 100 } = {}) {
  const params = new URLSearchParams();

  if (cameraId) {
    params.set("camera_id", String(cameraId));
  }

  params.set("limit", String(limit));
  return apiRequest(`/api/cameras/recognition/logs?${params.toString()}`);
}

export async function getRecognitionReviewRecords({
  cameraId,
  reviewStatus,
  predictedProfileId,
  limit = 200,
  sort = "top_score_desc"
} = {}) {
  const params = new URLSearchParams();

  if (cameraId) {
    params.set("camera_id", String(cameraId));
  }

  if (reviewStatus) {
    params.set("review_status", reviewStatus);
  }

  if (predictedProfileId) {
    params.set("predicted_profile_id", String(predictedProfileId));
  }

  params.set("limit", String(limit));
  params.set("sort", sort);
  return apiRequest(`/api/recognition/review?${params.toString()}`);
}

export async function updateRecognitionReviewVerdict(recordId, { reviewStatus, note }) {
  return apiRequest(`/api/recognition/review/${recordId}/verdict`, {
    method: "POST",
    body: JSON.stringify({
      review_status: reviewStatus,
      note
    })
  });
}

export async function resetRecognitionReviewRecords(cameraId = null) {
  return apiRequest("/api/recognition/review/reset", {
    method: "POST",
    body: JSON.stringify({
      camera_id: cameraId
    })
  });
}

export async function exportRecognitionReviewCsv({
  cameraId,
  reviewStatus,
  predictedProfileId,
  limit = 5000,
  sort = "top_score_desc"
} = {}) {
  const params = new URLSearchParams();

  if (cameraId) {
    params.set("camera_id", String(cameraId));
  }

  if (reviewStatus) {
    params.set("review_status", reviewStatus);
  }

  if (predictedProfileId) {
    params.set("predicted_profile_id", String(predictedProfileId));
  }

  params.set("limit", String(limit));
  params.set("sort", sort);

  const token = getStoredToken();
  const response = await fetch(`/api/recognition/review/export.csv?${params.toString()}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {}
  });

  if (!response.ok) {
    const payload = await response.text();
    throw new Error(payload || "Unable to export recognition review CSV.");
  }

  const blob = await response.blob();
  const downloadUrl = window.URL.createObjectURL(blob);
  const disposition = response.headers.get("content-disposition") || "";
  const filenameMatch = disposition.match(/filename=\"([^\"]+)\"/);
  const filename = filenameMatch?.[1] || "recognition-review.csv";

  const anchor = document.createElement("a");
  anchor.href = downloadUrl;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.URL.revokeObjectURL(downloadUrl);
}

export async function getUnknownSnapshots(cameraId, limit = 50) {
  return apiRequest(`/api/cameras/${cameraId}/snapshots?limit=${encodeURIComponent(limit)}`);
}

export async function getPersistentUnknownFaces(cameraId) {
  return apiRequest(`/api/cameras/${cameraId}/unknown-faces-persistent`);
}

export async function deleteUnknownFace(unknownFaceId) {
  return apiRequest(`/api/unknown-faces/${unknownFaceId}`, {
    method: "DELETE"
  });
}

export async function assignUnknownFace(unknownFaceId, profileId) {
  const formData = new FormData();
  formData.append("profile_id", String(profileId));

  return apiRequest(`/api/unknown-faces/${unknownFaceId}/assign`, {
    method: "POST",
    body: formData
  });
}
