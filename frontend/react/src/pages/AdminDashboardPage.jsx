import { useEffect, useRef, useState } from "react";
import { useLocation } from "react-router-dom";
import { AppShell } from "../components/AppShell";
import { getRoleView } from "../lib/roleViews";
import { useAuth } from "../state/auth";
import {
  bulkUploadProfiles,
  deleteProfile,
  downloadAttendanceReportCsv,
  getAbsentMembers,
  getAttendanceCheckInOut,
  getAttendanceDashboardAnalytics,
  getAttendanceMarkingStatus,
  getAttendanceReport,
  getProfiles,
  startAttendanceMarking,
  stopAttendanceMarking,
  updateProfile,
  registerProfile
} from "../lib/admin";
import {
  addDays,
  buildAttendanceRows,
  enumerateDatesBetween,
  formatDate,
  formatDuration,
  getCurrentMonthInputValue,
  getDateRangeForMonth,
  getTodayDateInputValue,
  getWeekStartDateInputValue
} from "./admin-data";
import {
  CAPABILITY_ATTENDANCE_EXPORT,
  CAPABILITY_ATTENDANCE_MANAGE,
  CAPABILITY_PEOPLE_MANAGE,
  ROLE_ADMIN,
  ROLE_CLASS_TEACHER,
  ROLE_MANAGER,
  ROLE_PRINCIPAL,
  hasCapability
} from "../lib/rbac";

const CLASS_OPTIONS = Array.from({ length: 12 }, (_, index) => `K${index + 1}`);
const DEFAULT_SECTION_OPTIONS = ["A", "B", "C", "D"];
const TABLE_PAGE_SIZE = 10;
const FACE_VIEW_FIELDS = [
  { key: "straight", label: "Look straight" },
  { key: "left", label: "Turn slightly left" },
  { key: "right", label: "Turn slightly right" },
  { key: "top", label: "Tilt face up" },
  { key: "down", label: "Tilt face down" }
];
const initialProfileForm = {
  profile_type: "faculty",
  name: "",
  email: "",
  department: "",
  class_name: "",
  section_name: "",
  roll_number: "",
  check_in_time: "09:00",
  check_out_time: "17:00"
};

function getCameraSupportMessage() {
  if (!window.isSecureContext) {
    return "Camera access requires HTTPS or localhost. Chrome blocks webcam permission on this non-secure network address.";
  }

  if (!navigator.mediaDevices?.getUserMedia) {
    return "Camera capture is not available in this browser.";
  }

  return "";
}

function matchesSearch(row, query) {
  const normalizedQuery = (query || "").trim().toLowerCase();

  if (!normalizedQuery) {
    return true;
  }

  return Object.values(row).some((value) => String(value ?? "").toLowerCase().includes(normalizedQuery));
}

function paginateRows(rows, currentPage, pageSize = TABLE_PAGE_SIZE) {
  const totalPages = Math.max(1, Math.ceil(rows.length / pageSize));
  const safePage = Math.min(currentPage, totalPages);
  const startIndex = (safePage - 1) * pageSize;

  return {
    totalPages,
    currentPage: safePage,
    rows: rows.slice(startIndex, startIndex + pageSize)
  };
}

function getReportModeLabel(mode) {
  if (mode === "daily") {
    return "Daily";
  }

  if (mode === "weekly") {
    return "Weekly";
  }

  if (mode === "monthly") {
    return "Monthly";
  }

  return "Custom range";
}

function getReportPeriodLabel(mode, startDate, endDate) {
  if (!startDate || !endDate) {
    return "";
  }

  if (startDate === endDate) {
    return formatDate(startDate);
  }

  return `${formatDate(startDate)} - ${formatDate(endDate)}`;
}

function buildReportFileName(mode, startDate, endDate) {
  const normalizedMode = mode === "custom" ? "date-range" : mode;
  return `attendance-report-${normalizedMode}-${startDate}-to-${endDate}.csv`;
}

const initialStats = {
  totalUsers: "-",
  activeUsers: "-",
  adminCount: "-",
  registeredFaces: "-",
  presentToday: "-",
  absentToday: "-"
};

const initialDashboardAnalytics = {
  selected_date: getTodayDateInputValue(),
  selected_range: {
    start_date: getTodayDateInputValue(),
    end_date: getTodayDateInputValue()
  },
  scope: {
    role_scope: "faculty",
    class_name: null,
    section_name: null
  },
  today_kpis: {
    total_profiles: 0,
    present_today: 0,
    absent_today: 0,
    attendance_rate_today: 0
  },
  operational_summary: {
    average_check_in_time_today: null,
    top_source: null,
    last_detection_time: null
  },
  historical_trends: {
    daily: [],
    summary: {
      total_days: 0,
      total_present: 0,
      total_absent: 0,
      average_attendance_rate: 0
    },
    best_day: null,
    worst_day: null
  },
  attendance_records: []
};

function getTabFromHash(hash) {
  if (!hash || hash === "#dashboard") {
    return "dashboard";
  }

  if (hash === "#profiles") {
    return "profiles";
  }

  if (hash === "#reports") {
    return "reports";
  }

  return "attendance";
}

export function AdminDashboardPage({
  forcedTab,
  initialProfileType = "faculty",
  title = "Attendance",
  subtitle = "Attendance analytics and daily records.",
  breadcrumbs
}) {
  const videoRef = useRef(null);
  const streamRef = useRef(null);
  const captureCanvasRef = useRef(null);
  const editFileInputRefs = useRef({});
  const location = useLocation();
  const { user } = useAuth();
  const roleView = getRoleView(user?.role);
  const activeTab = forcedTab || getTabFromHash(location.hash);
  const canManagePeople = hasCapability(user, CAPABILITY_PEOPLE_MANAGE);
  const canManageAttendance = hasCapability(user, CAPABILITY_ATTENDANCE_MANAGE);
  const canExportAttendance = hasCapability(user, CAPABILITY_ATTENDANCE_EXPORT);
  const isTeacher = user?.role === ROLE_CLASS_TEACHER;
  const isPrincipal = user?.role === ROLE_PRINCIPAL;
  const isManager = user?.role === ROLE_MANAGER;
  const isAdmin = user?.role === ROLE_ADMIN;
  const isOperationsRole = isManager || isAdmin;
  const assignedClasses = user?.scope?.class_names || [];
  const assignedSections = user?.scope?.section_names || [];
  const primaryAssignedClass = assignedClasses[0] || "";
  const primaryAssignedSection = assignedSections[0] || "";
  const scopeBadgeText = isTeacher
    ? [primaryAssignedClass, primaryAssignedSection].filter(Boolean).join(" • ") || "Assigned class scope"
    : isPrincipal
      ? "School-wide read only"
      : isOperationsRole
        ? "Operational scope"
        : roleView.shell.scopeLabel;
  const [profiles, setProfiles] = useState([]);
  const [profileTypeFilter, setProfileTypeFilter] = useState(initialProfileType);
  const [profileClassFilter, setProfileClassFilter] = useState("");
  const [profileSectionFilter, setProfileSectionFilter] = useState("");
  const [profileFilters, setProfileFilters] = useState({
    classes: [],
    sections_by_class: {}
  });
  const [customStudentSections, setCustomStudentSections] = useState([]);
  const [profilesLoading, setProfilesLoading] = useState(false);
  const [profilesMessage, setProfilesMessage] = useState("");
  const [profileSearchQuery, setProfileSearchQuery] = useState("");
  const [profilePage, setProfilePage] = useState(1);
  const [editingProfile, setEditingProfile] = useState(null);
  const [editingProfileImages, setEditingProfileImages] = useState({});
  const [editingPreviewUrls, setEditingPreviewUrls] = useState({});
  const [editCameraOpen, setEditCameraOpen] = useState(false);
  const [editCameraLoading, setEditCameraLoading] = useState(false);
  const [editCameraError, setEditCameraError] = useState("");
  const [editCameraReady, setEditCameraReady] = useState(false);
  const [selectedEditCaptureView, setSelectedEditCaptureView] = useState(FACE_VIEW_FIELDS[0].key);
  const [creatingProfile, setCreatingProfile] = useState(false);
  const [newProfile, setNewProfile] = useState(initialProfileForm);
  const [newProfileIncludeImages, setNewProfileIncludeImages] = useState(false);
  const [bulkFile, setBulkFile] = useState(null);
  const [bulkUploading, setBulkUploading] = useState(false);
  const [attendanceDate, setAttendanceDate] = useState(getTodayDateInputValue());
  const [attendanceFilter, setAttendanceFilter] = useState("");
  const [attendanceRoleFilter, setAttendanceRoleFilter] = useState("faculty");
  const [attendanceClassFilter, setAttendanceClassFilter] = useState("");
  const [attendanceSectionFilter, setAttendanceSectionFilter] = useState("");
  const [attendanceLoading, setAttendanceLoading] = useState(false);
  const [attendanceSearchQuery, setAttendanceSearchQuery] = useState("");
  const [attendancePage, setAttendancePage] = useState(1);
  const [attendanceRows, setAttendanceRows] = useState([]);
  const [attendanceStats, setAttendanceStats] = useState({
    present: 0,
    absent: 0,
    total: 0
  });
  const [attendanceMessage, setAttendanceMessage] = useState("");
  const [attendanceControl, setAttendanceControl] = useState({
    overall_running: false,
    enabled_count: 0,
    running_count: 0,
    sources: []
  });
  const [attendanceControlLoading, setAttendanceControlLoading] = useState(false);
  const [selectedFrame, setSelectedFrame] = useState(null);
  const [dashboardAnalytics, setDashboardAnalytics] = useState(initialDashboardAnalytics);
  const [dashboardLoading, setDashboardLoading] = useState(false);
  const [dashboardMessage, setDashboardMessage] = useState("");
  const [dashboardRosterPage, setDashboardRosterPage] = useState(1);
  const [dashboardTrendPage, setDashboardTrendPage] = useState(1);
  const [dashboardRoleFilter, setDashboardRoleFilter] = useState("faculty");
  const [dashboardClassFilter, setDashboardClassFilter] = useState("");
  const [dashboardSectionFilter, setDashboardSectionFilter] = useState("");
  const [dashboardTrendMode, setDashboardTrendMode] = useState("monthly");
  const [dashboardRangeMonth, setDashboardRangeMonth] = useState(getCurrentMonthInputValue());
  const [dashboardRangeWeekStart, setDashboardRangeWeekStart] = useState(getWeekStartDateInputValue());
  const [dashboardRangeStartDate, setDashboardRangeStartDate] = useState(getTodayDateInputValue());
  const [dashboardRangeEndDate, setDashboardRangeEndDate] = useState(getTodayDateInputValue());
  const [reportMode, setReportMode] = useState("daily");
  const [reportRoleFilter, setReportRoleFilter] = useState("faculty");
  const [reportClassFilter, setReportClassFilter] = useState("");
  const [reportSectionFilter, setReportSectionFilter] = useState("");
  const [reportDate, setReportDate] = useState(getTodayDateInputValue());
  const [reportMonth, setReportMonth] = useState(getCurrentMonthInputValue());
  const [reportWeekStart, setReportWeekStart] = useState(getWeekStartDateInputValue());
  const [reportStartDate, setReportStartDate] = useState(getTodayDateInputValue());
  const [reportEndDate, setReportEndDate] = useState(getTodayDateInputValue());
  const [reportsLoading, setReportsLoading] = useState(false);
  const [reportMessage, setReportMessage] = useState("");
  const [reportSearchQuery, setReportSearchQuery] = useState("");
  const [reportSummaryPage, setReportSummaryPage] = useState(1);
  const [reportDetailPage, setReportDetailPage] = useState(1);
  const [reportRows, setReportRows] = useState([]);
  const [reportPersonRows, setReportPersonRows] = useState([]);
  const [reportSummary, setReportSummary] = useState({
    totalDays: 0,
    totalPresent: 0,
    totalAbsent: 0,
    averagePresentRate: 0
  });
  const [loadedReport, setLoadedReport] = useState({
    mode: "daily",
    start: getTodayDateInputValue(),
    end: getTodayDateInputValue()
  });

  useEffect(() => {
    setProfileTypeFilter(initialProfileType);
  }, [initialProfileType]);

  useEffect(() => {
    const nextPreviewUrls = FACE_VIEW_FIELDS.reduce((accumulator, view) => {
      const file = editingProfileImages[view.key];
      accumulator[view.key] = file ? URL.createObjectURL(file) : "";
      return accumulator;
    }, {});

    setEditingPreviewUrls(nextPreviewUrls);

    return () => {
      Object.values(nextPreviewUrls).forEach((url) => {
        if (url) {
          URL.revokeObjectURL(url);
        }
      });
    };
  }, [editingProfileImages]);

  useEffect(() => () => {
    stopEditCameraStream();
  }, []);

  useEffect(() => {
    async function attachEditStream() {
      if (!editCameraOpen || !videoRef.current || !streamRef.current) {
        return;
      }

      try {
        videoRef.current.srcObject = streamRef.current;
        await videoRef.current.play();
        setEditCameraReady(true);
      } catch (error) {
        setEditCameraReady(false);
        setEditCameraError(error?.message || "Unable to render the camera preview.");
      }
    }

    attachEditStream();
  }, [editCameraOpen, selectedEditCaptureView]);

  useEffect(() => {
    if (!isTeacher) {
      return;
    }

    setAttendanceRoleFilter("student");
    setDashboardRoleFilter("student");
    setReportRoleFilter("student");
    if (primaryAssignedClass) {
      setAttendanceClassFilter(primaryAssignedClass);
      setDashboardClassFilter(primaryAssignedClass);
      setReportClassFilter(primaryAssignedClass);
    }
    if (primaryAssignedSection) {
      setAttendanceSectionFilter(primaryAssignedSection);
      setDashboardSectionFilter(primaryAssignedSection);
      setReportSectionFilter(primaryAssignedSection);
    }
  }, [isTeacher, primaryAssignedClass, primaryAssignedSection]);

  useEffect(() => {
    if (activeTab === "profiles" && !profiles.length && !profilesLoading) {
      loadProfiles();
    }

    if (activeTab === "attendance") {
      loadAttendance(attendanceDate);
    }

  }, [activeTab]);

  useEffect(() => {
    if (activeTab !== "profiles") {
      return;
    }

    loadProfiles();
  }, [activeTab, profileTypeFilter, profileClassFilter, profileSectionFilter]);

  useEffect(() => {
    if (profileFilters.classes.length) {
      return;
    }

    async function loadProfileFiltersOnly() {
      try {
        const data = await getProfiles({ profileType: "student" });
        setProfileFilters(
          data.filters || {
            classes: [],
            sections_by_class: {}
          }
        );
      } catch {
        // Keep existing empty filter state; table views already handle empty states.
      }
    }

    if (
      (activeTab === "dashboard" && dashboardRoleFilter === "student") ||
      (activeTab === "attendance" && attendanceRoleFilter === "student") ||
      (activeTab === "reports" && reportRoleFilter === "student")
    ) {
      loadProfileFiltersOnly();
    }
  }, [
    activeTab,
    dashboardRoleFilter,
    attendanceRoleFilter,
    reportRoleFilter,
    profileFilters.classes.length
  ]);

  useEffect(() => {
    setProfilePage(1);
  }, [profileTypeFilter, profileClassFilter, profileSectionFilter, profileSearchQuery]);

  useEffect(() => {
    setNewProfile((current) => ({
      ...current,
      profile_type: profileTypeFilter,
      class_name: profileTypeFilter === "student" ? profileClassFilter : "",
      section_name: profileTypeFilter === "student" ? profileSectionFilter : "",
      department: profileTypeFilter === "faculty" ? current.department : ""
    }));
  }, [profileTypeFilter, profileClassFilter, profileSectionFilter]);

  useEffect(() => {
    if (activeTab !== "dashboard") {
      return;
    }

    loadDashboardAnalytics();
  }, [
    activeTab,
    dashboardRoleFilter,
    dashboardClassFilter,
    dashboardSectionFilter,
    dashboardTrendMode,
    dashboardRangeMonth,
    dashboardRangeWeekStart,
    dashboardRangeStartDate,
    dashboardRangeEndDate
  ]);

  useEffect(() => {
    if (activeTab !== "reports") {
      return;
    }

    loadReports();
  }, [activeTab, reportMode, reportDate, reportWeekStart, reportMonth, reportStartDate, reportEndDate]);

  useEffect(() => {
    if (activeTab !== "attendance") {
      return;
    }

    loadAttendanceMarkingStatus();

    const intervalId = window.setInterval(() => {
      loadAttendanceMarkingStatus({ silent: true });
    }, 5000);

    return () => window.clearInterval(intervalId);
  }, [activeTab]);

  useEffect(() => {
    setAttendancePage(1);
  }, [attendanceRoleFilter, attendanceClassFilter, attendanceSectionFilter, attendanceFilter, attendanceSearchQuery]);

  useEffect(() => {
    setDashboardRosterPage(1);
  }, [dashboardRoleFilter, dashboardClassFilter, dashboardSectionFilter, dashboardAnalytics]);

  useEffect(() => {
    setDashboardTrendPage(1);
  }, [dashboardTrendMode, dashboardRangeMonth, dashboardRangeWeekStart, dashboardRangeStartDate, dashboardRangeEndDate, dashboardAnalytics]);

  useEffect(() => {
    setReportSummaryPage(1);
    setReportDetailPage(1);
  }, [reportMode, reportRoleFilter, reportClassFilter, reportSectionFilter, reportDate, reportWeekStart, reportMonth, reportStartDate, reportEndDate, reportSearchQuery, reportPersonRows.length, reportRows.length]);

  async function loadProfiles() {
    setProfilesLoading(true);
    setProfilesMessage("");

    try {
      const data = await getProfiles({
        profileType: profileTypeFilter,
        className: profileTypeFilter === "student" ? profileClassFilter : "",
        sectionName: profileTypeFilter === "student" ? profileSectionFilter : ""
      });
      setProfiles(data.profiles || []);
      setProfileFilters(
        data.filters || {
          classes: [],
          sections_by_class: {}
        }
      );
    } catch (error) {
      setProfiles([]);
      setProfileFilters({
        classes: [],
        sections_by_class: {}
      });
      setProfilesMessage(error.message || "Unable to load profiles.");
    } finally {
      setProfilesLoading(false);
    }
  }

  async function handleDeleteProfile(profile) {
    const confirmed = window.confirm(`Delete profile "${profile.name}"?`);

    if (!confirmed) {
      return;
    }

    try {
      await deleteProfile(profile.id);
      setProfilesMessage(`Profile "${profile.name}" deleted.`);
      await loadProfiles();
    } catch (error) {
      setProfilesMessage(error.message || "Unable to delete profile.");
    }
  }

  async function handleSaveProfile(event) {
    event.preventDefault();

    if (!editingProfile) {
      return;
    }

    const updates = {
      name: editingProfile.name?.trim(),
      profile_type: editingProfile.profile_type?.trim(),
      email: editingProfile.email?.trim(),
      department: editingProfile.department?.trim(),
      class_name: editingProfile.class_name?.trim(),
      section_name: editingProfile.section_name?.trim(),
      roll_number: editingProfile.roll_number?.trim(),
      check_in_time: editingProfile.check_in_time?.toString(),
      check_out_time: editingProfile.check_out_time?.toString()
    };
    FACE_VIEW_FIELDS.forEach((view) => {
      const file = editingProfileImages[view.key];
      if (file instanceof File && file.size > 0) {
        updates[`image_${view.key}`] = file;
      }
    });

    try {
      await updateProfile(editingProfile.id, updates);
      closeEditModal();
      setEditingProfile(null);
      setProfilesMessage("Profile updated successfully.");
      await loadProfiles();
    } catch (error) {
      setProfilesMessage(error.message || "Unable to update profile.");
    }
  }

  function openCreateProfileModal() {
    setCreatingProfile(true);
    setNewProfileIncludeImages(false);
    setNewProfile({
      ...initialProfileForm,
      profile_type: profileTypeFilter,
      class_name: profileTypeFilter === "student" ? profileClassFilter : "",
      section_name: profileTypeFilter === "student" ? profileSectionFilter : ""
    });
    setProfilesMessage("");
  }

  function updateNewProfileField(name, value) {
    setNewProfile((current) => {
      if (name === "profile_type") {
        return {
          ...current,
          profile_type: value,
          department: value === "faculty" ? current.department : "",
          class_name: value === "student" ? current.class_name : "",
          section_name: value === "student" ? current.section_name : "",
          roll_number: value === "student" ? current.roll_number : ""
        };
      }
      return {
        ...current,
        [name]: value
      };
    });
  }

  async function handleCreateProfile(event) {
    event.preventDefault();
    const formData = new FormData(event.currentTarget);
    const payload = new FormData();
    [
      "profile_type",
      "name",
      "email",
      "department",
      "class_name",
      "section_name",
      "roll_number",
      "check_in_time",
      "check_out_time"
    ].forEach((key) => {
      const value = formData.get(key)?.toString().trim();
      if (value) {
        payload.append(key, value);
      }
    });
    if (newProfileIncludeImages) {
      FACE_VIEW_FIELDS.forEach((view) => {
        const file = formData.get(`image_${view.key}`);
        if (file instanceof File && file.size > 0) {
          payload.append(`image_${view.key}`, file);
        }
      });
    }

    try {
      await registerProfile(payload);
      setCreatingProfile(false);
      setProfilesMessage(
        newProfileIncludeImages
          ? "Profile saved with images."
          : "Profile saved. It will stay incomplete until face images are uploaded."
      );
      await loadProfiles();
    } catch (error) {
      setProfilesMessage(error.message || "Unable to save profile.");
    }
  }

  async function handleBulkUpload() {
    if (!bulkFile) {
      setProfilesMessage("Choose a CSV or Excel file first.");
      return;
    }
    setBulkUploading(true);
    try {
      const formData = new FormData();
      formData.append("file", bulkFile);
      formData.append("profile_type", profileTypeFilter);
      const result = await bulkUploadProfiles(formData);
      setProfilesMessage(result.message || "Bulk upload completed.");
      setBulkFile(null);
      await loadProfiles();
    } catch (error) {
      setProfilesMessage(error.message || "Unable to process bulk upload.");
    } finally {
      setBulkUploading(false);
    }
  }

  function updateEditingProfileField(name, value) {
    setEditingProfile((current) => {
      if (!current) {
        return current;
      }

      if (name === "section_name" && value === "__new__") {
        return {
          ...current,
          section_name: "",
          isAddingSection: true
        };
      }

      if (name === "profile_type") {
        return {
          ...current,
          profile_type: value,
          department: value === "faculty" ? current.department : "",
          class_name: value === "student" ? current.class_name : "",
          section_name: value === "student" ? current.section_name : "",
          roll_number: value === "student" ? current.roll_number : "",
          isAddingSection: false,
          newSectionName: ""
        };
      }

      return {
        ...current,
        [name]: value
      };
    });
  }

  function stopEditCameraStream() {
    setEditCameraReady(false);

    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
    }

    if (videoRef.current) {
      videoRef.current.srcObject = null;
    }
  }

  async function openEditCamera(viewKey = FACE_VIEW_FIELDS[0].key) {
    const supportMessage = getCameraSupportMessage();

    if (supportMessage) {
      setEditCameraError(supportMessage);
      return;
    }

    setEditCameraLoading(true);
    setEditCameraError("");
    setSelectedEditCaptureView(viewKey);

    try {
      stopEditCameraStream();
      const stream = await navigator.mediaDevices.getUserMedia({
        video: {
          facingMode: "user"
        },
        audio: false
      });

      streamRef.current = stream;
      setEditCameraOpen(true);
    } catch (error) {
      if (error?.name === "NotAllowedError") {
        setEditCameraError("Camera permission was denied. Allow camera access in Chrome and try again.");
      } else if (error?.name === "NotFoundError") {
        setEditCameraError("No camera was found on this device.");
      } else {
        setEditCameraError(error?.message || "Unable to access the camera.");
      }
      setEditCameraOpen(false);
    } finally {
      setEditCameraLoading(false);
    }
  }

  function closeEditCamera() {
    stopEditCameraStream();
    setEditCameraOpen(false);
    setEditCameraError("");
  }

  async function captureEditPhoto() {
    const video = videoRef.current;
    const canvas = captureCanvasRef.current;

    if (!video || !canvas || !selectedEditCaptureView) {
      setEditCameraError("Camera preview is not ready yet.");
      return;
    }

    if (!editCameraReady || !video.videoWidth || !video.videoHeight) {
      setEditCameraError("Wait for the camera preview to load before capturing.");
      return;
    }

    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    const context = canvas.getContext("2d");

    if (!context) {
      setEditCameraError("Unable to prepare captured image.");
      return;
    }

    context.drawImage(video, 0, 0, canvas.width, canvas.height);

    const blob = await new Promise((resolve) => {
      canvas.toBlob(resolve, "image/jpeg", 0.92);
    });

    if (!blob) {
      setEditCameraError("Unable to capture photo. Please try again.");
      return;
    }

    const capturedFile = new File(
      [blob],
      `${editingProfile?.name?.trim().replace(/\s+/g, "-").toLowerCase() || "profile"}-${selectedEditCaptureView}.jpg`,
      { type: "image/jpeg" }
    );

    setEditingProfileImages((current) => ({
      ...current,
      [selectedEditCaptureView]: capturedFile
    }));
    setProfilesMessage(`${FACE_VIEW_FIELDS.find((view) => view.key === selectedEditCaptureView)?.label || "Selected"} image captured.`);
    setEditCameraError("");
  }

  function updateEditingFile(viewKey, event) {
    const file = event.target.files?.[0] || null;

    setEditingProfileImages((current) => ({
      ...current,
      [viewKey]: file
    }));
  }

  function triggerEditingFilePicker(viewKey) {
    editFileInputRefs.current[viewKey]?.click();
  }

  function closeEditModal() {
    closeEditCamera();
    setEditingProfileImages({});
    setSelectedEditCaptureView(FACE_VIEW_FIELDS[0].key);
  }

  function saveEditingProfileSection() {
    const normalized = (editingProfile?.newSectionName || "").trim();

    if (!normalized) {
      setProfilesMessage("Enter a section name before saving it.");
      return;
    }

    setCustomStudentSections((current) => (current.includes(normalized) ? current : [...current, normalized]));
    setEditingProfile((current) => {
      if (!current) {
        return current;
      }

      return {
        ...current,
        section_name: normalized,
        isAddingSection: false,
        newSectionName: ""
      };
    });
    setProfilesMessage("");
  }

  async function loadAttendance(date) {
    setAttendanceLoading(true);
    setAttendanceMessage("");

    try {
      const today = getTodayDateInputValue();
      const [checkInData, absentData, profilesData] = await Promise.all([
        getAttendanceCheckInOut(today),
        getAbsentMembers(today),
        getProfiles()
      ]);

      const combinedRows = buildAttendanceRows({
        records: checkInData.records || [],
        absentMembers: absentData.records || []
      });
      const profileMapById = new Map((profilesData.profiles || []).map((profile) => [profile.id, profile]));
      const profileMapByName = new Map((profilesData.profiles || []).map((profile) => [profile.name, profile]));
      const enrichedRows = combinedRows.map((row) => {
        const matchedProfile = profileMapById.get(row.id) || profileMapByName.get(row.name);

        return {
          ...row,
          profile_type: matchedProfile?.profile_type || "faculty",
          class_name: matchedProfile?.class_name || "",
          section_name: matchedProfile?.section_name || "",
          roll_number: matchedProfile?.roll_number || ""
        };
      });

      setAttendanceDate(today);
      setAttendanceRows(enrichedRows);
      setAttendanceStats({
        present: (checkInData.records || []).filter((row) => ["present", "late"].includes(String(row.status || "").toLowerCase())).length,
        absent: (absentData.records || []).length,
        total: profilesData.count || (profilesData.profiles || []).length
      });
    } catch (error) {
      setAttendanceRows([]);
      setAttendanceStats({
        present: 0,
        absent: 0,
        total: 0
      });
      setAttendanceMessage(error.message || "Unable to load attendance.");
    } finally {
      setAttendanceLoading(false);
    }
  }

  async function refreshTodayAttendance() {
    setAttendanceLoading(true);
    setAttendanceMessage("");

    try {
      const today = getTodayDateInputValue();
      const [checkInData, absentData, profilesData] = await Promise.all([
        getAttendanceCheckInOut(today),
        getAbsentMembers(today),
        getProfiles()
      ]);

      const combinedRows = buildAttendanceRows({
        records: checkInData.records || [],
        absentMembers: absentData.records || []
      });
      const profileMapById = new Map((profilesData.profiles || []).map((profile) => [profile.id, profile]));
      const profileMapByName = new Map((profilesData.profiles || []).map((profile) => [profile.name, profile]));
      const enrichedRows = combinedRows.map((row) => {
        const matchedProfile = profileMapById.get(row.id) || profileMapByName.get(row.name);

        return {
          ...row,
          profile_type: matchedProfile?.profile_type || "faculty",
          class_name: matchedProfile?.class_name || "",
          section_name: matchedProfile?.section_name || "",
          roll_number: matchedProfile?.roll_number || ""
        };
      });

      setAttendanceDate(today);
      setAttendanceRows(enrichedRows);
      setAttendanceStats({
        present: (checkInData.records || []).filter((row) => ["present", "late"].includes(String(row.status || "").toLowerCase())).length,
        absent: (absentData.records || []).length,
        total: profilesData.count || (profilesData.profiles || []).length
      });
    } catch (error) {
      setAttendanceRows([]);
      setAttendanceStats({
        present: 0,
        absent: 0,
        total: 0
      });
      setAttendanceMessage(error.message || "Unable to load attendance.");
    } finally {
      setAttendanceLoading(false);
    }
  }

  async function loadAttendanceMarkingStatus(options = {}) {
    const { silent = false } = options;

    if (!silent) {
      setAttendanceControlLoading(true);
    }

    try {
      const data = await getAttendanceMarkingStatus();
      setAttendanceControl(data?.data || {
        overall_running: false,
        enabled_count: 0,
        running_count: 0,
        sources: []
      });
    } catch (error) {
      if (!silent) {
        setAttendanceMessage(error.message || "Unable to load attendance marking status.");
      }
    } finally {
      if (!silent) {
        setAttendanceControlLoading(false);
      }
    }
  }

  async function handleStartAttendanceMarking() {
    setAttendanceControlLoading(true);
    setAttendanceMessage("Starting attendance marking...");

    try {
      const result = await startAttendanceMarking();
      setAttendanceControl(result?.data || attendanceControl);
      setAttendanceMessage(result?.message || "Attendance marking started.");
      await Promise.all([
        refreshTodayAttendance(),
        loadAttendanceMarkingStatus({ silent: true }),
        loadDashboardAnalytics({ silent: true })
      ]);
    } catch (error) {
      setAttendanceMessage(error.message || "Unable to start attendance marking.");
    } finally {
      setAttendanceControlLoading(false);
    }
  }

  async function handleStopAttendanceMarking() {
    setAttendanceControlLoading(true);
    setAttendanceMessage("Stopping attendance marking...");

    try {
      const result = await stopAttendanceMarking();
      setAttendanceControl(result?.data || attendanceControl);
      setAttendanceMessage(result?.message || "Attendance marking stopped.");
      await Promise.all([
        loadAttendanceMarkingStatus({ silent: true }),
        loadDashboardAnalytics({ silent: true })
      ]);
    } catch (error) {
      setAttendanceMessage(error.message || "Unable to stop attendance marking.");
    } finally {
      setAttendanceControlLoading(false);
    }
  }

  function getDashboardRange() {
    if (dashboardTrendMode === "monthly") {
      return getDateRangeForMonth(dashboardRangeMonth);
    }

    if (dashboardTrendMode === "weekly") {
      return {
        start: dashboardRangeWeekStart,
        end: addDays(dashboardRangeWeekStart, 6)
      };
    }

    return {
      start: dashboardRangeStartDate,
      end: dashboardRangeEndDate
    };
  }

  async function loadDashboardAnalytics(options = {}) {
    const { silent = false } = options;
    const { start, end } = getDashboardRange();

    if (!silent) {
      setDashboardLoading(true);
      setDashboardMessage("");
    }

    try {
      const data = await getAttendanceDashboardAnalytics({
        date: getTodayDateInputValue(),
        startDate: start,
        endDate: end,
        roleScope: dashboardRoleFilter,
        className: dashboardRoleFilter === "student" ? dashboardClassFilter : undefined,
        sectionName: dashboardRoleFilter === "student" ? dashboardSectionFilter : undefined
      });

      setDashboardAnalytics(data?.data || initialDashboardAnalytics);
      if (!silent) {
        setDashboardMessage("Attendance analytics updated.");
      }
    } catch (error) {
      setDashboardAnalytics(initialDashboardAnalytics);
      if (!silent) {
        setDashboardMessage(error.message || "Unable to load attendance analytics.");
      }
    } finally {
      if (!silent) {
        setDashboardLoading(false);
      }
    }
  }

  function getReportRange() {
    if (reportMode === "daily") {
      return {
        start: reportDate,
        end: reportDate
      };
    }

    if (reportMode === "monthly") {
      return getDateRangeForMonth(reportMonth);
    }

    if (reportMode === "weekly") {
      return {
        start: reportWeekStart,
        end: addDays(reportWeekStart, 6)
      };
    }

    return {
      start: reportStartDate,
      end: reportEndDate
    };
  }

  async function loadReports() {
    const { start, end } = getReportRange();
    const reportFilters = {
      reportType: reportMode,
      date: reportMode === "daily" ? reportDate : undefined,
      weekStart: reportMode === "weekly" ? reportWeekStart : undefined,
      month: reportMode === "monthly" ? reportMonth : undefined,
      startDate: reportMode === "custom" ? reportStartDate : undefined,
      endDate: reportMode === "custom" ? reportEndDate : undefined
    };

    if (!start || !end) {
      setReportMessage("Choose a valid report date range.");
      return;
    }

    if (start > end) {
      setReportMessage("Start date cannot be after end date.");
      return;
    }

    setReportsLoading(true);
    setReportMessage("");

    try {
      const reportData = await getAttendanceReport(reportFilters);
      const rows = (reportData.records || []).map((entry) => ({
        date: entry.date,
        present: entry.present,
        absent: entry.absent,
        total: entry.total_profiles,
        rate: Math.round(entry.attendance_rate || 0)
      }));
      const personRows = (reportData.person_records || []).map((entry) => ({
        date: entry.date,
        name: entry.name,
        profileType: entry.profile_type || "faculty",
        className: entry.class_name || "",
        sectionName: entry.section_name || "",
        rollNumber: entry.roll_number || "",
        status: entry.status || "absent",
        checkIn: entry.check_in_time || entry.check_in || "-",
        checkOut: entry.check_out_time || entry.check_out || "-",
        detections: entry.detections || 0,
        lastLocation: entry.last_location || "-"
      }));

      setReportRows(rows);
      setReportPersonRows(personRows);
      setReportSummary({
        totalDays: reportData.summary?.total_days || 0,
        totalPresent: reportData.summary?.total_present || 0,
        totalAbsent: reportData.summary?.total_absent || 0,
        averagePresentRate: Math.round(reportData.summary?.average_attendance_rate || 0)
      });
      setLoadedReport({
        mode: reportMode,
        start,
        end
      });
      setReportMessage(
        rows.length
          ? `Showing ${getReportModeLabel(reportMode).toLowerCase()} report for ${getReportPeriodLabel(reportMode, start, end)}.`
          : "No attendance data found for the selected range."
      );
    } catch (error) {
      setReportRows([]);
      setReportPersonRows([]);
      setReportSummary({
        totalDays: 0,
        totalPresent: 0,
        totalAbsent: 0,
        averagePresentRate: 0
      });
      setReportMessage(error.message || "Unable to load reports.");
    } finally {
      setReportsLoading(false);
    }
  }

  async function downloadReport() {
    const { start, end } = getReportRange();

    if (!reportRows.length) {
      setReportMessage("Load a report before downloading it.");
      return;
    }

    try {
      await downloadAttendanceReportCsv({
        reportType: reportMode,
        date: reportMode === "daily" ? reportDate : undefined,
        weekStart: reportMode === "weekly" ? reportWeekStart : undefined,
        month: reportMode === "monthly" ? reportMonth : undefined,
        startDate: reportMode === "custom" ? reportStartDate : undefined,
        endDate: reportMode === "custom" ? reportEndDate : undefined,
        fallbackFileName: buildReportFileName(reportMode, start, end)
      });
      setReportMessage("Report downloaded.");
    } catch (error) {
      setReportMessage(error.message || "Unable to download report.");
    }
  }

  const filteredAttendanceRows = attendanceFilter
    ? attendanceRows.filter((row) => row.status === attendanceFilter)
    : attendanceRows;
  const roleFilteredAttendanceRows = filteredAttendanceRows.filter((row) =>
    attendanceRoleFilter === "student" ? row.profile_type === "student" : row.profile_type !== "student"
  );
  const scopedAttendanceRows = attendanceRoleFilter === "student"
    ? roleFilteredAttendanceRows.filter((row) => {
        if (!attendanceClassFilter || !attendanceSectionFilter) {
          return false;
        }

        return row.class_name === attendanceClassFilter && row.section_name === attendanceSectionFilter;
      })
    : roleFilteredAttendanceRows;
  const attendanceSections = Array.from(
    new Set(
      [
        ...(profileFilters.sections_by_class?.[attendanceClassFilter] || []),
        ...attendanceRows
          .filter((row) => row.profile_type === "student" && row.class_name === attendanceClassFilter && row.section_name)
          .map((row) => row.section_name)
      ]
    )
  );

  const dashboardTrendSummary = dashboardAnalytics.historical_trends?.summary || initialDashboardAnalytics.historical_trends.summary;
  const dashboardRecords = dashboardAnalytics.attendance_records || [];
  const dashboardSections = Array.from(
    new Set(
      profileFilters.sections_by_class?.[dashboardClassFilter] || []
    )
  );
  const requiresDashboardStudentScope = dashboardRoleFilter === "student" && (!dashboardClassFilter || !dashboardSectionFilter);
  const availableSections = Array.from(
    new Set([...(profileFilters.sections_by_class?.[profileClassFilter] || []), ...customStudentSections])
  );
  const requiresStudentScope = profileTypeFilter === "student" && (!profileClassFilter || !profileSectionFilter);
  const visibleProfiles = profiles.filter((profile) => matchesSearch(profile, profileSearchQuery));
  const requiresAttendanceStudentScope = attendanceRoleFilter === "student" && (!attendanceClassFilter || !attendanceSectionFilter);
  const searchedAttendanceRows = scopedAttendanceRows.filter((row) => matchesSearch(row, attendanceSearchQuery));
  const requiresReportStudentScope = reportRoleFilter === "student" && (!reportClassFilter || !reportSectionFilter);
  const reportMatrixDates = loadedReport.start && loadedReport.end
    ? enumerateDatesBetween(loadedReport.start, loadedReport.end)
    : [];
  const reportSections = Array.from(
    new Set(
      [
        ...(profileFilters.sections_by_class?.[reportClassFilter] || []),
        ...reportPersonRows
          .filter((row) => row.profileType === "student" && row.className === reportClassFilter && row.sectionName)
          .map((row) => row.sectionName)
      ]
    )
  );
  const roleFilteredReportPersonRows = reportPersonRows.filter((row) =>
    reportRoleFilter === "student" ? row.profileType === "student" : row.profileType !== "student"
  );
  const scopedReportPersonRows = reportRoleFilter === "student"
    ? roleFilteredReportPersonRows.filter((row) => {
        if (!reportClassFilter || !reportSectionFilter) {
          return false;
        }

        return row.className === reportClassFilter && row.sectionName === reportSectionFilter;
      })
    : roleFilteredReportPersonRows;
  const reportAttendanceMatrix = Array.from(
    scopedReportPersonRows.reduce((map, row) => {
      const key = `${row.profileType}-${row.name}-${row.rollNumber || row.className || "base"}`;

      if (!map.has(key)) {
        map.set(key, {
          key,
          name: row.name,
          profileType: row.profileType,
          className: row.className,
          sectionName: row.sectionName,
          rollNumber: row.rollNumber,
          statuses: {}
        });
      }

      map.get(key).statuses[row.date] = row.status;
      return map;
    }, new Map()).values()
  );
  const filteredReportRows = reportMatrixDates.map((date) => {
    const dayRows = scopedReportPersonRows.filter((row) => row.date === date);
    const present = dayRows.filter((row) => row.status === "present").length;
    const total = dayRows.length;
    const absent = Math.max(total - present, 0);

    return {
      date,
      present,
      absent,
      total,
      rate: total ? Math.round((present / total) * 100) : 0
    };
  });
  const filteredReportSummary = {
    totalDays: filteredReportRows.length,
    totalPresent: filteredReportRows.reduce((sum, row) => sum + row.present, 0),
    totalAbsent: filteredReportRows.reduce((sum, row) => sum + row.absent, 0),
    averagePresentRate: filteredReportRows.length
      ? Math.round(filteredReportRows.reduce((sum, row) => sum + row.rate, 0) / filteredReportRows.length)
      : 0
  };
  const searchedReportPersonRows = scopedReportPersonRows.filter((row) => matchesSearch(row, reportSearchQuery));
  const searchedReportAttendanceMatrix = reportAttendanceMatrix.filter((row) => matchesSearch(row, reportSearchQuery));
  const paginatedDashboardRoster = paginateRows(dashboardRecords, dashboardRosterPage);
  const paginatedDashboardTrend = paginateRows(dashboardAnalytics.historical_trends?.daily || [], dashboardTrendPage);
  const paginatedProfiles = paginateRows(visibleProfiles, profilePage);
  const paginatedAttendanceRows = paginateRows(searchedAttendanceRows, attendancePage);
  const paginatedReportRows = paginateRows(filteredReportRows, reportSummaryPage);
  const paginatedReportDetails = paginateRows(
    reportMode === "daily" ? searchedReportPersonRows : searchedReportAttendanceMatrix,
    reportDetailPage
  );
  const editingSectionOptions = Array.from(
    new Set([
      ...DEFAULT_SECTION_OPTIONS,
      ...(profileFilters.sections_by_class?.[editingProfile?.class_name || ""] || []),
      ...customStudentSections,
      editingProfile?.section_name || ""
    ].filter(Boolean))
  );

  return (
    <AppShell
      title={title}
      subtitle={subtitle}
      breadcrumbs={breadcrumbs}
    >
      {activeTab === "dashboard" ? (
        <>
          <section className="panel">
            <div className="section-header">
              <div>
                <h3>{isTeacher ? "Class analytics" : isPrincipal ? "School analytics" : "Dashboard"}</h3>
                <p>{isTeacher
                  ? "Assigned-class attendance, roster review, and trend summary."
                  : isPrincipal
                    ? "Read-only attendance trends and school-wide roster signals."
                    : "Attendance operations with a compact live view and recent trend summary."}</p>
              </div>
              <div className="section-actions">
                <button className="secondary-button" disabled={dashboardLoading} onClick={() => loadDashboardAnalytics()} type="button">
                  Refresh analytics
                </button>
              </div>
            </div>

            <div className="workspace-meta-inline">
              <span className="badge-light">{scopeBadgeText}</span>
            </div>

            {!isTeacher ? (
            <div className="report-mode-row" role="tablist" aria-label="Dashboard role filter">
              <button
                aria-pressed={dashboardRoleFilter === "faculty"}
                className={`report-mode-button ${dashboardRoleFilter === "faculty" ? "active" : ""}`}
                onClick={() => {
                  setDashboardRoleFilter("faculty");
                  setDashboardClassFilter("");
                  setDashboardSectionFilter("");
                }}
                type="button"
              >
                Faculty
              </button>
              <button
                aria-pressed={dashboardRoleFilter === "student"}
                className={`report-mode-button ${dashboardRoleFilter === "student" ? "active" : ""}`}
                onClick={() => setDashboardRoleFilter("student")}
                type="button"
              >
                Student
              </button>
            </div>
            ) : null}

            {dashboardRoleFilter === "student" ? (
              <div className="report-filter-grid">
                <label className="filter-field">
                  <span>Class</span>
                  <select
                    onChange={(event) => {
                      setDashboardClassFilter(event.target.value);
                      setDashboardSectionFilter("");
                    }}
                    value={dashboardClassFilter}
                  >
                    <option value="">Select class</option>
                    {CLASS_OPTIONS.map((className) => (
                      <option key={className} value={className}>
                        {className}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="filter-field">
                  <span>Section</span>
                  <select
                    disabled={!dashboardClassFilter}
                    onChange={(event) => setDashboardSectionFilter(event.target.value)}
                    value={dashboardSectionFilter}
                  >
                    <option value="">Select section</option>
                    {dashboardSections.map((sectionName) => (
                      <option key={sectionName} value={sectionName}>
                        {sectionName}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
            ) : null}

            {dashboardMessage ? <p className="inline-note">{dashboardMessage}</p> : null}

            {requiresDashboardStudentScope ? (
              <div className="table-empty">Choose class and section to load student dashboard analytics.</div>
            ) : null}

            <section className="analytics-grid analytics-grid-top">
              <article className="metric-card">
                <span>Present today</span>
                <strong>{requiresDashboardStudentScope ? 0 : dashboardAnalytics.today_kpis?.present_today || 0}</strong>
                <p>In current dashboard scope.</p>
              </article>
              <article className="metric-card">
                <span>Absent today</span>
                <strong>{requiresDashboardStudentScope ? 0 : dashboardAnalytics.today_kpis?.absent_today || 0}</strong>
                <p>In current dashboard scope.</p>
              </article>
              <article className="metric-card">
                <span>Total in scope</span>
                <strong>{requiresDashboardStudentScope ? 0 : dashboardAnalytics.today_kpis?.total_profiles || 0}</strong>
                <p>Registered profiles in this view.</p>
              </article>
              <article className="metric-card">
                <span>Attendance rate</span>
                <strong>{requiresDashboardStudentScope ? 0 : dashboardAnalytics.today_kpis?.attendance_rate_today || 0}%</strong>
                <p>Present vs total in scope.</p>
              </article>
            </section>
          </section>

          <section className="analytics-grid analytics-grid-bottom">
            <article className="metric-card">
              <span>Attendance marking</span>
              <strong>{dashboardAnalytics.marking_status?.overall_running ? "Running" : "Stopped"}</strong>
              <p>{dashboardAnalytics.marking_status?.running_count || 0} of {dashboardAnalytics.marking_status?.enabled_count || 0} sources active.</p>
            </article>
            <article className="metric-card">
              <span>Top source</span>
              <strong>{dashboardAnalytics.operational_summary?.top_source || "-"}</strong>
              <p>Most active source today.</p>
            </article>
            <article className="metric-card">
              <span>Last detection</span>
              <strong>{dashboardAnalytics.operational_summary?.last_detection_time ? formatDate(dashboardAnalytics.operational_summary.last_detection_time) : "-"}</strong>
              <p>Latest detection timestamp.</p>
            </article>
            <article className="metric-card">
              <span>Average check-in</span>
              <strong>{dashboardAnalytics.operational_summary?.average_check_in_time_today || "-"}</strong>
              <p>For present people in scope.</p>
            </article>
          </section>

          <section className="panel">
            <div className="section-header">
              <div>
                <h3>Today&apos;s attendance</h3>
                <p>{isTeacher
                  ? "Compact attendance list for your assigned students."
                  : "Compact attendance list for operational scanning."}</p>
              </div>
            </div>

            <div className="table-shell">
              <table>
                <thead>
                  <tr>
                    <th>Name</th>
                    {dashboardRoleFilter === "student" ? (
                      <>
                        <th>Class</th>
                        <th>Section</th>
                        <th>Roll number</th>
                      </>
                    ) : null}
                    <th>Status</th>
                    <th>Check-in</th>
                    <th>Check-out</th>
                    <th>Last location</th>
                  </tr>
                </thead>
                <tbody>
                  {dashboardLoading ? (
                    <tr>
                      <td colSpan={dashboardRoleFilter === "student" ? 8 : 5} className="table-empty">Loading attendance analytics...</td>
                    </tr>
                  ) : null}
                  {!dashboardLoading && requiresDashboardStudentScope ? (
                    <tr>
                      <td colSpan={dashboardRoleFilter === "student" ? 8 : 5} className="table-empty">Choose class and section to view student dashboard attendance.</td>
                    </tr>
                  ) : null}
                  {!dashboardLoading && !requiresDashboardStudentScope && !dashboardRecords.length ? (
                    <tr>
                      <td colSpan={dashboardRoleFilter === "student" ? 8 : 5} className="table-empty">No attendance records for today.</td>
                    </tr>
                  ) : null}
                  {!dashboardLoading && !requiresDashboardStudentScope ? paginatedDashboardRoster.rows.map((record) => (
                    <tr key={`dashboard-${record.id}`}>
                      <td><strong>{record.name}</strong></td>
                      {dashboardRoleFilter === "student" ? (
                        <>
                          <td>{record.class_name || "-"}</td>
                          <td>{record.section_name || "-"}</td>
                          <td>{record.roll_number || "-"}</td>
                        </>
                      ) : null}
                      <td><span className={`status-pill ${record.status}`}>{record.status}</span></td>
                      <td>{record.check_in_display || "-"}</td>
                      <td>{record.check_out_display || "-"}</td>
                      <td>{record.last_location || "-"}</td>
                    </tr>
                  )) : null}
                </tbody>
              </table>
            </div>
            {paginatedDashboardRoster.totalPages > 1 ? (
              <div className="pagination-row">
                <button
                  className="secondary-button table-button"
                  disabled={paginatedDashboardRoster.currentPage === 1}
                  onClick={() => setDashboardRosterPage((current) => Math.max(1, current - 1))}
                  type="button"
                >
                  Previous
                </button>
                <span className="pagination-text">
                  Page {paginatedDashboardRoster.currentPage} of {paginatedDashboardRoster.totalPages}
                </span>
                <button
                  className="secondary-button table-button"
                  disabled={paginatedDashboardRoster.currentPage === paginatedDashboardRoster.totalPages}
                  onClick={() => setDashboardRosterPage((current) => Math.min(paginatedDashboardRoster.totalPages, current + 1))}
                  type="button"
                >
                  Next
                </button>
              </div>
            ) : null}
          </section>

          <section className="panel">
            <div className="section-header">
              <div>
                <h3>Recent trend</h3>
                <p>{isPrincipal
                  ? "Read-only recent attendance trend for the selected school scope."
                  : "Compact recent attendance trend for the selected dashboard scope."}</p>
              </div>
            </div>

            <div className="report-mode-row">
              {[
                { id: "monthly", label: "Monthly" },
                { id: "weekly", label: "Weekly" },
                { id: "custom", label: "Custom range" }
              ].map((mode) => (
                <button
                  key={mode.id}
                  className={`report-mode-button ${dashboardTrendMode === mode.id ? "active" : ""}`}
                  onClick={() => setDashboardTrendMode(mode.id)}
                  type="button"
                >
                  {mode.label}
                </button>
              ))}
            </div>

            <div className="report-filter-grid">
              {dashboardTrendMode === "monthly" ? (
                <label className="filter-field">
                  <span>Month</span>
                  <input onChange={(event) => setDashboardRangeMonth(event.target.value)} type="month" value={dashboardRangeMonth} />
                </label>
              ) : null}
              {dashboardTrendMode === "weekly" ? (
                <label className="filter-field">
                  <span>Week start</span>
                  <input onChange={(event) => setDashboardRangeWeekStart(event.target.value)} type="date" value={dashboardRangeWeekStart} />
                </label>
              ) : null}
              {dashboardTrendMode === "custom" ? (
                <>
                  <label className="filter-field">
                    <span>From date</span>
                    <input onChange={(event) => setDashboardRangeStartDate(event.target.value)} type="date" value={dashboardRangeStartDate} />
                  </label>
                  <label className="filter-field">
                    <span>To date</span>
                    <input onChange={(event) => setDashboardRangeEndDate(event.target.value)} type="date" value={dashboardRangeEndDate} />
                  </label>
                </>
              ) : null}
            </div>

            <section className="analytics-grid analytics-grid-bottom">
              <article className="metric-card">
                <span>Average attendance</span>
                <strong>{dashboardTrendSummary.average_attendance_rate || 0}%</strong>
                <p>{dashboardTrendSummary.total_days || 0} days covered.</p>
              </article>
              <article className="metric-card">
                <span>Best day</span>
                <strong>{dashboardAnalytics.historical_trends?.best_day?.attendance_rate || 0}%</strong>
                <p>{dashboardAnalytics.historical_trends?.best_day?.date ? formatDate(dashboardAnalytics.historical_trends.best_day.date) : "-"}</p>
              </article>
              <article className="metric-card">
                <span>Worst day</span>
                <strong>{dashboardAnalytics.historical_trends?.worst_day?.attendance_rate || 0}%</strong>
                <p>{dashboardAnalytics.historical_trends?.worst_day?.date ? formatDate(dashboardAnalytics.historical_trends.worst_day.date) : "-"}</p>
              </article>
              <article className="metric-card">
                <span>Days covered</span>
                <strong>{dashboardTrendSummary.total_days || 0}</strong>
                <p>In the selected recent range.</p>
              </article>
            </section>

            <div className="table-shell">
              <table>
                <thead>
                  <tr>
                    <th>Date</th>
                    <th>Present</th>
                    <th>Absent</th>
                    <th>Rate</th>
                  </tr>
                </thead>
                <tbody>
                  {(dashboardAnalytics.historical_trends?.daily || []).length ? (
                    paginatedDashboardTrend.rows.map((row) => (
                      <tr key={`trend-${row.date}`}>
                        <td>{formatDate(row.date)}</td>
                        <td>{row.present}</td>
                        <td>{row.absent}</td>
                        <td>{row.attendance_rate}%</td>
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td colSpan="4" className="table-empty">No trend data available.</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
            {paginatedDashboardTrend.totalPages > 1 ? (
              <div className="pagination-row">
                <button
                  className="secondary-button table-button"
                  disabled={paginatedDashboardTrend.currentPage === 1}
                  onClick={() => setDashboardTrendPage((current) => Math.max(1, current - 1))}
                  type="button"
                >
                  Previous
                </button>
                <span className="pagination-text">
                  Page {paginatedDashboardTrend.currentPage} of {paginatedDashboardTrend.totalPages}
                </span>
                <button
                  className="secondary-button table-button"
                  disabled={paginatedDashboardTrend.currentPage === paginatedDashboardTrend.totalPages}
                  onClick={() => setDashboardTrendPage((current) => Math.min(paginatedDashboardTrend.totalPages, current + 1))}
                  type="button"
                >
                  Next
                </button>
              </div>
            ) : null}
          </section>
        </>
      ) : null}

      {activeTab === "profiles" ? (
        <section className="panel">
          <div className="section-header">
            <div>
              <h3>Profiles</h3>
              <p>Save profile details first, bulk import without images, and complete face enrollment later from this same settings area.</p>
            </div>
            <div className="section-actions">
              <button className="secondary-button" onClick={loadProfiles} type="button">
                Refresh
              </button>
              {canManagePeople ? (
                <button className="primary-button inline-button" onClick={openCreateProfileModal} type="button">
                  {profileTypeFilter === "student" ? "Add student" : "Add faculty"}
                </button>
              ) : null}
            </div>
          </div>

          <div className="report-mode-row" role="tablist" aria-label="Profile role filter">
            <button
              aria-pressed={profileTypeFilter === "faculty"}
              className={`report-mode-button ${profileTypeFilter === "faculty" ? "active" : ""}`}
              onClick={() => {
                setProfileTypeFilter("faculty");
                setProfileClassFilter("");
                setProfileSectionFilter("");
              }}
              type="button"
            >
              Faculty
            </button>
            <button
              aria-pressed={profileTypeFilter === "student"}
              className={`report-mode-button ${profileTypeFilter === "student" ? "active" : ""}`}
              onClick={() => setProfileTypeFilter("student")}
              type="button"
            >
              Student
            </button>
          </div>

          {profileTypeFilter === "student" ? (
            <div className="report-filter-grid">
              <label className="filter-field">
                <span>Class</span>
                <select
                  onChange={(event) => {
                    setProfileClassFilter(event.target.value);
                    setProfileSectionFilter("");
                  }}
                  value={profileClassFilter}
                >
                  <option value="">Select class</option>
                  {CLASS_OPTIONS.map((className) => (
                    <option key={className} value={className}>
                      {className}
                    </option>
                  ))}
                </select>
              </label>
              <label className="filter-field">
                <span>Section</span>
                <select
                  disabled={!profileClassFilter}
                  onChange={(event) => setProfileSectionFilter(event.target.value)}
                  value={profileSectionFilter}
                >
                  <option value="">Select section</option>
                  {availableSections.map((sectionName) => (
                    <option key={sectionName} value={sectionName}>
                      {sectionName}
                    </option>
                  ))}
                </select>
              </label>
            </div>
          ) : null}

          <div className="table-search-row">
            <label className="filter-field table-search-field">
              <span>Search</span>
              <input
                onChange={(event) => setProfileSearchQuery(event.target.value)}
                placeholder="Search name, class, section, roll number..."
                type="text"
                value={profileSearchQuery}
              />
            </label>
          </div>

          {canManagePeople ? (
            <div className="report-filter-grid">
              <label className="filter-field">
                <span>Bulk upload file</span>
                <input
                  accept=".csv,.xlsx,.xls"
                  onChange={(event) => setBulkFile(event.target.files?.[0] || null)}
                  type="file"
                />
              </label>
              <div className="section-actions">
                <button className="secondary-button" disabled={bulkUploading} onClick={handleBulkUpload} type="button">
                  {bulkUploading ? "Uploading..." : "Bulk upload"}
                </button>
              </div>
            </div>
          ) : null}

          {profilesMessage ? <p className="inline-note">{profilesMessage}</p> : null}

          <div className="table-shell">
            <table>
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Name</th>
                  {profileTypeFilter === "student" ? (
                    <>
                      <th>Class</th>
                      <th>Section</th>
                      <th>Roll number</th>
                    </>
                  ) : (
                    <>
                      <th>Type</th>
                      <th>Email</th>
                      <th>Department</th>
                      <th>Check-in</th>
                      <th>Check-out</th>
                    </>
                  )}
                  <th>Status</th>
                  <th>Registered</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {profilesLoading ? (
                  <tr>
                    <td colSpan={profileTypeFilter === "student" ? 8 : 10} className="table-empty">Loading profiles...</td>
                  </tr>
                ) : null}
                {!profilesLoading && requiresStudentScope ? (
                  <tr>
                    <td colSpan={profileTypeFilter === "student" ? 8 : 10} className="table-empty">Choose class and section to view student profiles.</td>
                  </tr>
                ) : null}
                {!profilesLoading && !requiresStudentScope && !visibleProfiles.length ? (
                  <tr>
                    <td colSpan={profileTypeFilter === "student" ? 8 : 10} className="table-empty">No registered profiles found.</td>
                  </tr>
                ) : null}
                {!profilesLoading && !requiresStudentScope
                  ? paginatedProfiles.rows.map((profile) => (
                      <tr key={profile.id}>
                        <td>#{profile.id}</td>
                        <td><strong>{profile.name || "-"}</strong></td>
                        {profileTypeFilter === "student" ? (
                          <>
                            <td>{profile.class_name || "-"}</td>
                            <td>{profile.section_name || "-"}</td>
                            <td>{profile.roll_number || "-"}</td>
                          </>
                        ) : (
                          <>
                            <td>
                              <span className={`status-pill ${profile.profile_type === "student" ? "late" : "present"}`}>
                                {profile.profile_type || "faculty"}
                              </span>
                            </td>
                            <td>{profile.email || "-"}</td>
                            <td>{profile.department || "-"}</td>
                            <td>{profile.check_in_time || "09:00"}</td>
                            <td>{profile.check_out_time || "17:00"}</td>
                          </>
                        )}
                        <td>
                          <span className={`status-pill ${profile.profile_complete ? "present" : "late"}`}>
                            {profile.profile_complete ? "completed" : "incomplete"}
                          </span>
                        </td>
                        <td>{formatDate(profile.created_at)}</td>
                        <td>
                          {canManagePeople ? (
                            <div className="table-actions">
                              <button
                                className="secondary-button table-button"
                                onClick={() =>
                                  setEditingProfile({
                                    ...profile,
                                    isAddingSection: false,
                                    newSectionName: ""
                                  })
                                }
                                type="button"
                              >
                                Edit
                              </button>
                              <button
                                className="danger-button table-button"
                                onClick={() => handleDeleteProfile(profile)}
                                type="button"
                              >
                                Delete
                              </button>
                            </div>
                          ) : (
                            <span className="muted-text">Read only</span>
                          )}
                        </td>
                      </tr>
                    ))
                  : null}
                </tbody>
              </table>
          </div>
          {paginatedProfiles.totalPages > 1 ? (
            <div className="pagination-row">
              <button
                className="secondary-button table-button"
                disabled={paginatedProfiles.currentPage === 1}
                onClick={() => setProfilePage((current) => Math.max(1, current - 1))}
                type="button"
              >
                Previous
              </button>
              <span className="pagination-text">
                Page {paginatedProfiles.currentPage} of {paginatedProfiles.totalPages}
              </span>
              <button
                className="secondary-button table-button"
                disabled={paginatedProfiles.currentPage === paginatedProfiles.totalPages}
                onClick={() => setProfilePage((current) => Math.min(paginatedProfiles.totalPages, current + 1))}
                type="button"
              >
                Next
              </button>
            </div>
          ) : null}
        </section>
      ) : null}

      {activeTab === "attendance" ? (
        <>
          <section className="card-grid">
            <article className="metric-card">
              <span>Present</span>
              <strong>{attendanceStats.present}</strong>
              <p>Seen today.</p>
            </article>
            <article className="metric-card">
              <span>Absent</span>
              <strong>{attendanceStats.absent}</strong>
              <p>Not seen.</p>
            </article>
            <article className="metric-card">
              <span>Total</span>
              <strong>{attendanceStats.total}</strong>
              <p>Registered profiles.</p>
            </article>
          </section>

          <section className="panel">
            <div className="section-header">
              <div>
                <h3>{isTeacher ? "Class attendance today" : isPrincipal ? "School attendance today" : "Today's attendance"}</h3>
                <p>{isTeacher
                  ? "Assigned-class roster with present, absent, and late review."
                  : isPrincipal
                    ? "Read-only school-wide attendance view across faculty and student groups."
                    : "Present or absent only, scoped by faculty or student groups."}</p>
              </div>
              <div className="section-actions responsive-filters">
                <label className="filter-field">
                  <span>Date</span>
                  <input disabled type="date" value={attendanceDate} />
                </label>
                <label className="filter-field">
                  <span>Status</span>
                  <select
                    onChange={(event) => setAttendanceFilter(event.target.value)}
                    value={attendanceFilter}
                  >
                    <option value="">All status</option>
                    <option value="present">Present</option>
                    <option value="absent">Absent</option>
                  </select>
                </label>
                {canManageAttendance ? (
                  <>
                    <button
                      className="primary-button"
                      disabled={attendanceControlLoading}
                      onClick={handleStartAttendanceMarking}
                      type="button"
                    >
                      {attendanceControlLoading ? "Working..." : "Start attendance"}
                    </button>
                    <button
                      className="secondary-button"
                      disabled={attendanceControlLoading}
                      onClick={handleStopAttendanceMarking}
                      type="button"
                    >
                      Stop attendance
                    </button>
                  </>
                ) : null}
                <button className="secondary-button" onClick={refreshTodayAttendance} type="button">
                  Refresh
                </button>
              </div>
            </div>

            <div className="workspace-meta-inline">
              <span className="badge-light">{scopeBadgeText}</span>
            </div>

            {!isTeacher ? (
            <div className="report-mode-row" role="tablist" aria-label="Attendance role filter">
              <button
                aria-pressed={attendanceRoleFilter === "faculty"}
                className={`report-mode-button ${attendanceRoleFilter === "faculty" ? "active" : ""}`}
                onClick={() => {
                  setAttendanceRoleFilter("faculty");
                  setAttendanceClassFilter("");
                  setAttendanceSectionFilter("");
                }}
                type="button"
              >
                Faculty
              </button>
              <button
                aria-pressed={attendanceRoleFilter === "student"}
                className={`report-mode-button ${attendanceRoleFilter === "student" ? "active" : ""}`}
                onClick={() => setAttendanceRoleFilter("student")}
                type="button"
              >
                Student
              </button>
            </div>
            ) : null}

            {attendanceRoleFilter === "student" ? (
              <div className="report-filter-grid">
                <label className="filter-field">
                  <span>Class</span>
                  <select
                    onChange={(event) => {
                      setAttendanceClassFilter(event.target.value);
                      setAttendanceSectionFilter("");
                    }}
                    value={attendanceClassFilter}
                  >
                    <option value="">Select class</option>
                    {CLASS_OPTIONS.map((className) => (
                      <option key={className} value={className}>
                        {className}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="filter-field">
                  <span>Section</span>
                  <select
                    disabled={!attendanceClassFilter}
                    onChange={(event) => setAttendanceSectionFilter(event.target.value)}
                    value={attendanceSectionFilter}
                  >
                    <option value="">Select section</option>
                    {attendanceSections.map((sectionName) => (
                      <option key={sectionName} value={sectionName}>
                        {sectionName}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
            ) : null}

            <div className="table-search-row">
              <label className="filter-field table-search-field">
                <span>Search</span>
                <input
                  onChange={(event) => setAttendanceSearchQuery(event.target.value)}
                  placeholder="Search name, class, section, status, location..."
                  type="text"
                  value={attendanceSearchQuery}
                />
              </label>
            </div>

            {attendanceMessage ? <p className="inline-note">{attendanceMessage}</p> : null}

            <div className="table-shell">
              <table>
                <thead>
                  <tr>
                    <th>Name</th>
                    {attendanceRoleFilter === "student" ? (
                      <>
                        <th>Class</th>
                        <th>Section</th>
                        <th>Roll number</th>
                      </>
                    ) : null}
                    <th>Check-in</th>
                    <th>Check-out</th>
                    <th>Status</th>
                    <th>Duration</th>
                    <th>Last location</th>
                    <th>Frame</th>
                  </tr>
                </thead>
                <tbody>
                  {attendanceLoading ? (
                    <tr>
                      <td colSpan={attendanceRoleFilter === "student" ? 10 : 7} className="table-empty">Loading attendance...</td>
                    </tr>
                  ) : null}
                  {!attendanceLoading && requiresAttendanceStudentScope ? (
                    <tr>
                      <td colSpan={attendanceRoleFilter === "student" ? 10 : 7} className="table-empty">Choose class and section to view student attendance.</td>
                    </tr>
                  ) : null}
                  {!attendanceLoading && !requiresAttendanceStudentScope && !searchedAttendanceRows.length ? (
                    <tr>
                      <td colSpan={attendanceRoleFilter === "student" ? 10 : 7} className="table-empty">No attendance records for this filter.</td>
                    </tr>
                  ) : null}
                  {!attendanceLoading && !requiresAttendanceStudentScope
                    ? paginatedAttendanceRows.rows.map((record) => (
                        <tr key={`${record.status}-${record.id}`}>
                          <td><strong>{record.name}</strong></td>
                          {attendanceRoleFilter === "student" ? (
                            <>
                              <td>{record.class_name || "-"}</td>
                              <td>{record.section_name || "-"}</td>
                              <td>{record.roll_number || "-"}</td>
                            </>
                          ) : null}
                          <td>{record.check_in_time || "-"}</td>
                          <td>{record.check_out_time || "-"}</td>
                          <td>
                            <span className={`status-pill ${record.status}`}>{record.status}</span>
                          </td>
                          <td>{formatDuration(record.duration_minutes)}</td>
                          <td>{record.last_location || "-"}</td>
                          <td>
                            {record.frame_path ? (
                              <button
                                className="frame-button"
                                onClick={() => setSelectedFrame(record)}
                                type="button"
                              >
                                View
                              </button>
                            ) : (
                              <span className="muted-text">No frame</span>
                            )}
                          </td>
                        </tr>
                      ))
                    : null}
                </tbody>
              </table>
            </div>
            {paginatedAttendanceRows.totalPages > 1 ? (
              <div className="pagination-row">
                <button
                  className="secondary-button table-button"
                  disabled={paginatedAttendanceRows.currentPage === 1}
                  onClick={() => setAttendancePage((current) => Math.max(1, current - 1))}
                  type="button"
                >
                  Previous
                </button>
                <span className="pagination-text">
                  Page {paginatedAttendanceRows.currentPage} of {paginatedAttendanceRows.totalPages}
                </span>
                <button
                  className="secondary-button table-button"
                  disabled={paginatedAttendanceRows.currentPage === paginatedAttendanceRows.totalPages}
                  onClick={() => setAttendancePage((current) => Math.min(paginatedAttendanceRows.totalPages, current + 1))}
                  type="button"
                >
                  Next
                </button>
              </div>
            ) : null}
          </section>
        </>
      ) : null}

      {activeTab === "reports" ? (
        <>
          <section className="panel">
            <div className="section-header">
              <div>
                <h3>{isTeacher ? "Class attendance reports" : isPrincipal ? "School attendance reports" : "Attendance reports"}</h3>
                <p>{isTeacher
                  ? "Assigned-scope attendance summaries and student report views."
                  : isPrincipal
                    ? "School-wide read-only attendance summaries and comparison views."
                    : "View and download daily, weekly, monthly, or custom attendance reports."}</p>
              </div>
              <div className="report-actions">
                <button className="secondary-button" onClick={loadReports} type="button">
                  View report
                </button>
                {canExportAttendance ? (
                  <button className="primary-button" onClick={downloadReport} type="button">
                    Download report
                  </button>
                ) : null}
              </div>
            </div>

            <div className="report-mode-row" role="tablist" aria-label="Report type">
              {[
                { id: "daily", label: "Daily" },
                { id: "weekly", label: "Weekly" },
                { id: "monthly", label: "Monthly" },
                { id: "custom", label: "Custom range" }
              ].map((mode) => (
                <button
                  key={mode.id}
                  className={`report-mode-button ${reportMode === mode.id ? "active" : ""}`}
                  onClick={() => setReportMode(mode.id)}
                  type="button"
                >
                  {mode.label}
                </button>
              ))}
            </div>

            <div className="report-filter-grid">
              {reportMode === "daily" ? (
                <label className="filter-field">
                  <span>Date</span>
                  <input
                    onChange={(event) => setReportDate(event.target.value)}
                    type="date"
                    value={reportDate}
                  />
                </label>
              ) : null}

              {reportMode === "monthly" ? (
                <label className="filter-field">
                  <span>Month</span>
                  <input
                    onChange={(event) => setReportMonth(event.target.value)}
                    type="month"
                    value={reportMonth}
                  />
                </label>
              ) : null}

              {reportMode === "weekly" ? (
                <label className="filter-field">
                  <span>Week start</span>
                  <input
                    onChange={(event) => setReportWeekStart(event.target.value)}
                    type="date"
                    value={reportWeekStart}
                  />
                </label>
              ) : null}

              {reportMode === "custom" ? (
                <>
                  <label className="filter-field">
                    <span>From date</span>
                    <input
                      onChange={(event) => setReportStartDate(event.target.value)}
                      type="date"
                      value={reportStartDate}
                    />
                  </label>
                  <label className="filter-field">
                    <span>To date</span>
                    <input
                      onChange={(event) => setReportEndDate(event.target.value)}
                      type="date"
                      value={reportEndDate}
                    />
                  </label>
                </>
              ) : null}

            </div>

            <div className="workspace-meta-inline">
              <span className="badge-light">{scopeBadgeText}</span>
            </div>

            {!isTeacher ? (
            <div className="report-mode-row" role="tablist" aria-label="Report role filter">
              <button
                aria-pressed={reportRoleFilter === "faculty"}
                className={`report-mode-button ${reportRoleFilter === "faculty" ? "active" : ""}`}
                onClick={() => {
                  setReportRoleFilter("faculty");
                  setReportClassFilter("");
                  setReportSectionFilter("");
                }}
                type="button"
              >
                Faculty
              </button>
              <button
                aria-pressed={reportRoleFilter === "student"}
                className={`report-mode-button ${reportRoleFilter === "student" ? "active" : ""}`}
                onClick={() => setReportRoleFilter("student")}
                type="button"
              >
                Student
              </button>
            </div>
            ) : null}

            {reportRoleFilter === "student" ? (
              <div className="report-filter-grid">
                <label className="filter-field">
                  <span>Class</span>
                  <select
                    onChange={(event) => {
                      setReportClassFilter(event.target.value);
                      setReportSectionFilter("");
                    }}
                    value={reportClassFilter}
                  >
                    <option value="">Select class</option>
                    {CLASS_OPTIONS.map((className) => (
                      <option key={className} value={className}>
                        {className}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="filter-field">
                  <span>Section</span>
                  <select
                    disabled={!reportClassFilter}
                    onChange={(event) => setReportSectionFilter(event.target.value)}
                    value={reportSectionFilter}
                  >
                    <option value="">Select section</option>
                    {reportSections.map((sectionName) => (
                      <option key={sectionName} value={sectionName}>
                        {sectionName}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
            ) : null}

            <div className="table-search-row">
              <label className="filter-field table-search-field">
                <span>Search</span>
                <input
                  onChange={(event) => setReportSearchQuery(event.target.value)}
                  placeholder="Search name, type, class, section, roll number..."
                  type="text"
                  value={reportSearchQuery}
                />
              </label>
            </div>

            {reportMessage ? <p className="inline-note">{reportMessage}</p> : null}
          </section>

          <section className="card-grid">
            <article className="metric-card">
              <span>Days covered</span>
              <strong>{filteredReportSummary.totalDays}</strong>
              <p>{getReportModeLabel(loadedReport.mode)} report period.</p>
            </article>
            <article className="metric-card">
              <span>Total present</span>
              <strong>{filteredReportSummary.totalPresent}</strong>
              <p>For {getReportPeriodLabel(loadedReport.mode, loadedReport.start, loadedReport.end) || "selected period"}.</p>
            </article>
            <article className="metric-card">
              <span>Total absent</span>
              <strong>{filteredReportSummary.totalAbsent}</strong>
              <p>For {getReportPeriodLabel(loadedReport.mode, loadedReport.start, loadedReport.end) || "selected period"}.</p>
            </article>
            <article className="metric-card">
              <span>Average rate</span>
              <strong>{filteredReportSummary.averagePresentRate}%</strong>
              <p>{getReportModeLabel(loadedReport.mode)} attendance view.</p>
            </article>
          </section>

          <section className="panel">
            <div className="section-header">
              <div>
                <h3>Report data</h3>
                <p>
                  {getReportModeLabel(loadedReport.mode)} attendance totals for{" "}
                  {getReportPeriodLabel(loadedReport.mode, loadedReport.start, loadedReport.end) || "the selected period"}.
                </p>
              </div>
            </div>

            <div className="table-shell">
              <table>
                <thead>
                  <tr>
                    <th>Date</th>
                    <th>Present</th>
                    <th>Absent</th>
                    <th>Total profiles</th>
                    <th>Attendance rate</th>
                  </tr>
                </thead>
                <tbody>
                  {reportsLoading ? (
                    <tr>
                      <td className="table-empty" colSpan="5">Loading reports...</td>
                    </tr>
                  ) : null}
                  {!reportsLoading && requiresReportStudentScope ? (
                    <tr>
                      <td className="table-empty" colSpan="5">Choose class and section to view student reports.</td>
                    </tr>
                  ) : null}
                  {!reportsLoading && !requiresReportStudentScope && !filteredReportRows.length ? (
                    <tr>
                      <td className="table-empty" colSpan="5">No report data available for this range.</td>
                    </tr>
                  ) : null}
                  {!reportsLoading && !requiresReportStudentScope
                    ? paginatedReportRows.rows.map((row) => (
                        <tr key={row.date}>
                          <td>{formatDate(row.date)}</td>
                          <td>{row.present}</td>
                          <td>{row.absent}</td>
                          <td>{row.total}</td>
                          <td>{row.rate}%</td>
                        </tr>
                      ))
                    : null}
                </tbody>
              </table>
            </div>
            {paginatedReportRows.totalPages > 1 ? (
              <div className="pagination-row">
                <button
                  className="secondary-button table-button"
                  disabled={paginatedReportRows.currentPage === 1}
                  onClick={() => setReportSummaryPage((current) => Math.max(1, current - 1))}
                  type="button"
                >
                  Previous
                </button>
                <span className="pagination-text">
                  Page {paginatedReportRows.currentPage} of {paginatedReportRows.totalPages}
                </span>
                <button
                  className="secondary-button table-button"
                  disabled={paginatedReportRows.currentPage === paginatedReportRows.totalPages}
                  onClick={() => setReportSummaryPage((current) => Math.min(paginatedReportRows.totalPages, current + 1))}
                  type="button"
                >
                  Next
                </button>
              </div>
            ) : null}
          </section>

          <section className="panel">
            <div className="section-header">
              <div>
                <h3>{reportMode === "daily" ? "Person-wise report" : "Attendance matrix"}</h3>
                <p>
                  {reportMode === "daily"
                    ? "Attendance records for each person in the selected report range."
                    : "Each person is listed once, with each date shown as present or absent."}
                </p>
              </div>
            </div>

            <div className="table-shell">
              <table>
                <thead>
                  {reportMode === "daily" ? (
                    <tr>
                      <th>Date</th>
                      <th>Name</th>
                      <th>Type</th>
                      <th>Class</th>
                      <th>Section</th>
                      <th>Roll number</th>
                      <th>Status</th>
                      <th>Check-in</th>
                      <th>Check-out</th>
                      <th>Detections</th>
                      <th>Last location</th>
                    </tr>
                  ) : (
                    <tr>
                      <th>Name</th>
                      <th>Type</th>
                      <th>Class</th>
                      <th>Section</th>
                      <th>Roll number</th>
                      {reportMatrixDates.map((date) => (
                        <th key={`report-date-${date}`}>{formatDate(date)}</th>
                      ))}
                    </tr>
                  )}
                </thead>
                <tbody>
                  {reportsLoading ? (
                    <tr>
                      <td className="table-empty" colSpan={reportMode === "daily" ? 11 : 5 + reportMatrixDates.length}>
                        Loading person-wise report...
                      </td>
                    </tr>
                  ) : null}
                  {!reportsLoading && requiresReportStudentScope ? (
                    <tr>
                      <td className="table-empty" colSpan={reportMode === "daily" ? 11 : 5 + reportMatrixDates.length}>
                        Choose class and section to view student reports.
                      </td>
                    </tr>
                  ) : null}
                  {!reportsLoading && !requiresReportStudentScope && !(reportMode === "daily" ? searchedReportPersonRows.length : searchedReportAttendanceMatrix.length) ? (
                    <tr>
                      <td className="table-empty" colSpan={reportMode === "daily" ? 11 : 5 + reportMatrixDates.length}>
                        No person-wise report data available for this range.
                      </td>
                    </tr>
                  ) : null}
                  {!reportsLoading && !requiresReportStudentScope
                    ? paginatedReportDetails.rows.map((row) => (
                        reportMode === "daily" ? (
                          <tr key={`${row.date}-${row.profileType}-${row.name}-${row.rollNumber}`}>
                            <td>{formatDate(row.date)}</td>
                            <td>{row.name}</td>
                            <td>{row.profileType}</td>
                            <td>{row.className || "-"}</td>
                            <td>{row.sectionName || "-"}</td>
                            <td>{row.rollNumber || "-"}</td>
                            <td>
                              <span className={`status-pill ${row.status}`}>{row.status}</span>
                            </td>
                            <td>{row.checkIn}</td>
                            <td>{row.checkOut}</td>
                            <td>{row.detections}</td>
                            <td>{row.lastLocation}</td>
                          </tr>
                        ) : (
                          <tr key={row.key}>
                            <td>{row.name}</td>
                            <td>{row.profileType}</td>
                            <td>{row.className || "-"}</td>
                            <td>{row.sectionName || "-"}</td>
                            <td>{row.rollNumber || "-"}</td>
                            {reportMatrixDates.map((date) => {
                              const status = row.statuses[date] || "absent";
                              return (
                                <td key={`${row.key}-${date}`}>
                                  <span className={`status-pill ${status}`}>{status === "present" ? "P" : "A"}</span>
                                </td>
                              );
                            })}
                          </tr>
                        )
                      ))
                    : null}
                </tbody>
              </table>
            </div>
            {paginatedReportDetails.totalPages > 1 ? (
              <div className="pagination-row">
                <button
                  className="secondary-button table-button"
                  disabled={paginatedReportDetails.currentPage === 1}
                  onClick={() => setReportDetailPage((current) => Math.max(1, current - 1))}
                  type="button"
                >
                  Previous
                </button>
                <span className="pagination-text">
                  Page {paginatedReportDetails.currentPage} of {paginatedReportDetails.totalPages}
                </span>
                <button
                  className="secondary-button table-button"
                  disabled={paginatedReportDetails.currentPage === paginatedReportDetails.totalPages}
                  onClick={() => setReportDetailPage((current) => Math.min(paginatedReportDetails.totalPages, current + 1))}
                  type="button"
                >
                  Next
                </button>
              </div>
            ) : null}
          </section>
        </>
      ) : null}

      {creatingProfile ? (
        <div className="modal-backdrop" onClick={() => setCreatingProfile(false)} role="presentation">
          <div className="modal-card" onClick={(event) => event.stopPropagation()} role="dialog" aria-modal="true">
            <div className="section-header">
              <div>
                <h3>Create profile</h3>
                <p>Save profile details now. Face images can be uploaded later, and the profile will remain incomplete until then.</p>
              </div>
            </div>

            <form className="modal-form" onSubmit={handleCreateProfile}>
              <label className="filter-field">
                <span>Profile type</span>
                <select
                  name="profile_type"
                  onChange={(event) => updateNewProfileField("profile_type", event.target.value)}
                  value={newProfile.profile_type}
                >
                  <option value="faculty">Faculty</option>
                  <option value="student">Student</option>
                </select>
              </label>
              <label className="filter-field">
                <span>Name</span>
                <input name="name" required onChange={(event) => updateNewProfileField("name", event.target.value)} value={newProfile.name} />
              </label>
              <label className="filter-field">
                <span>Email</span>
                <input name="email" onChange={(event) => updateNewProfileField("email", event.target.value)} type="email" value={newProfile.email} />
              </label>
              <label className="filter-field">
                <span>Face images</span>
                <label className="checkbox-row">
                  <input
                    checked={newProfileIncludeImages}
                    onChange={(event) => setNewProfileIncludeImages(event.target.checked)}
                    type="checkbox"
                  />
                  <span>Insert images now</span>
                </label>
              </label>
              {newProfile.profile_type === "student" ? (
                <>
                  <div className="split-fields">
                    <label className="filter-field">
                      <span>Class</span>
                      <select name="class_name" onChange={(event) => updateNewProfileField("class_name", event.target.value)} value={newProfile.class_name}>
                        <option value="">Select class</option>
                        {CLASS_OPTIONS.map((className) => (
                          <option key={className} value={className}>{className}</option>
                        ))}
                      </select>
                    </label>
                    <label className="filter-field">
                      <span>Section</span>
                      <select name="section_name" onChange={(event) => updateNewProfileField("section_name", event.target.value)} value={newProfile.section_name}>
                        <option value="">Select section</option>
                        {availableSections.map((sectionName) => (
                          <option key={sectionName} value={sectionName}>{sectionName}</option>
                        ))}
                      </select>
                    </label>
                  </div>
                  <label className="filter-field">
                    <span>Roll number</span>
                    <input name="roll_number" onChange={(event) => updateNewProfileField("roll_number", event.target.value)} value={newProfile.roll_number} />
                  </label>
                </>
              ) : (
                <>
                  <label className="filter-field">
                    <span>Department</span>
                    <input name="department" onChange={(event) => updateNewProfileField("department", event.target.value)} value={newProfile.department} />
                  </label>
                  <div className="split-fields">
                    <label className="filter-field">
                      <span>Check-in</span>
                      <input name="check_in_time" onChange={(event) => updateNewProfileField("check_in_time", event.target.value)} type="time" value={newProfile.check_in_time} />
                    </label>
                    <label className="filter-field">
                      <span>Check-out</span>
                      <input name="check_out_time" onChange={(event) => updateNewProfileField("check_out_time", event.target.value)} type="time" value={newProfile.check_out_time} />
                    </label>
                  </div>
                </>
              )}
              {newProfileIncludeImages ? (
                <>
                  <div className="report-filter-grid">
                    {FACE_VIEW_FIELDS.map((view) => (
                      <label className="filter-field" key={`create-${view.key}`}>
                        <span>{view.label}</span>
                        <input accept="image/*" name={`image_${view.key}`} type="file" />
                      </label>
                    ))}
                  </div>
                  <p className="inline-note">
                    Upload all five images to complete the profile immediately. If you leave this unchecked, only the profile details will be saved.
                  </p>
                </>
              ) : null}
              <div className="section-actions">
                <button className="secondary-button" onClick={() => setCreatingProfile(false)} type="button">
                  Cancel
                </button>
                <button className="primary-button" type="submit">
                  Save profile
                </button>
              </div>
            </form>
          </div>
        </div>
      ) : null}

      {editingProfile ? (
        <div className="modal-backdrop" onClick={() => {
          closeEditModal();
          setEditingProfile(null);
        }} role="presentation">
          <div className="modal-card" onClick={(event) => event.stopPropagation()} role="dialog" aria-modal="true">
            <div className="section-header">
              <div>
                <h3>Edit profile</h3>
                <p>Update role-aware profile metadata and upload all five face images here to complete incomplete profiles.</p>
              </div>
            </div>

            <form className="modal-form" onSubmit={handleSaveProfile}>
              <label className="filter-field">
                <span>Profile type</span>
                <select
                  name="profile_type"
                  onChange={(event) => updateEditingProfileField("profile_type", event.target.value)}
                  value={editingProfile.profile_type || "faculty"}
                >
                  <option value="faculty">Faculty</option>
                  <option value="student">Student</option>
                </select>
              </label>
              <label className="filter-field">
                <span>Name</span>
                <input
                  name="name"
                  onChange={(event) => updateEditingProfileField("name", event.target.value)}
                  value={editingProfile.name || ""}
                />
              </label>
              <label className="filter-field">
                <span>Email</span>
                <input
                  name="email"
                  onChange={(event) => updateEditingProfileField("email", event.target.value)}
                  type="email"
                  value={editingProfile.email || ""}
                />
              </label>
              {editingProfile.profile_type === "student" ? (
                <>
                  <div className="split-fields">
                    <label className="filter-field">
                      <span>Class</span>
                      <select
                        name="class_name"
                        onChange={(event) => updateEditingProfileField("class_name", event.target.value)}
                        value={editingProfile.class_name || ""}
                      >
                        <option value="">Select class</option>
                        {CLASS_OPTIONS.map((className) => (
                          <option key={className} value={className}>
                            {className}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label className="filter-field">
                      <span>Section</span>
                      <select
                        name="section_name"
                        onChange={(event) => updateEditingProfileField("section_name", event.target.value)}
                        value={editingProfile.isAddingSection ? "__new__" : editingProfile.section_name || ""}
                      >
                        <option value="">Select section</option>
                        {editingSectionOptions.map((sectionName) => (
                          <option key={sectionName} value={sectionName}>
                            {sectionName}
                          </option>
                        ))}
                        <option value="__new__">Add new section</option>
                      </select>
                    </label>
                  </div>
                  {editingProfile.isAddingSection ? (
                    <div className="split-fields">
                      <label className="filter-field">
                        <span>New section</span>
                        <input
                          onChange={(event) => updateEditingProfileField("newSectionName", event.target.value)}
                          placeholder="Enter section name"
                          value={editingProfile.newSectionName || ""}
                        />
                      </label>
                      <div className="section-actions">
                        <button className="secondary-button" onClick={saveEditingProfileSection} type="button">
                          Save section
                        </button>
                      </div>
                    </div>
                  ) : null}
                  <label className="filter-field">
                    <span>Roll number</span>
                    <input
                      name="roll_number"
                      onChange={(event) => updateEditingProfileField("roll_number", event.target.value)}
                      value={editingProfile.roll_number || ""}
                    />
                  </label>
                </>
              ) : (
                <>
                  <label className="filter-field">
                    <span>Department</span>
                    <input
                      name="department"
                      onChange={(event) => updateEditingProfileField("department", event.target.value)}
                      value={editingProfile.department || ""}
                    />
                  </label>
                </>
              )}
              {editingProfile.profile_type !== "student" ? (
                <div className="split-fields">
                  <label className="filter-field">
                    <span>Check-in</span>
                    <input
                      name="check_in_time"
                      onChange={(event) => updateEditingProfileField("check_in_time", event.target.value)}
                      type="time"
                      value={editingProfile.check_in_time || "09:00"}
                    />
                  </label>
                  <label className="filter-field">
                    <span>Check-out</span>
                    <input
                      name="check_out_time"
                      onChange={(event) => updateEditingProfileField("check_out_time", event.target.value)}
                      type="time"
                      value={editingProfile.check_out_time || "17:00"}
                    />
                  </label>
                </div>
              ) : null}
              <div className="filter-field camera-form-wide">
                <span>Required face views</span>
                <p className="inline-note capture-help-text">
                  Use <strong>Upload</strong> to open the file picker, or <strong>Capture</strong> to take the image directly in this edit form.
                </p>
                {editCameraError ? <p className="inline-note">{editCameraError}</p> : null}
                {editCameraOpen ? (
                  <div className="camera-capture-panel">
                    <div className="capture-toolbar">
                      <div className="capture-session-copy">
                        Capturing for <strong>{FACE_VIEW_FIELDS.find((view) => view.key === selectedEditCaptureView)?.label}</strong>
                      </div>
                      <button className="primary-button" onClick={captureEditPhoto} type="button">
                        Capture photo
                      </button>
                      <button className="secondary-button" onClick={closeEditCamera} type="button">
                        Close camera
                      </button>
                    </div>
                    <div className="frame-preview">
                      <video autoPlay muted playsInline ref={videoRef} />
                      {!editCameraReady ? <div className="camera-preview-placeholder">Loading camera preview...</div> : null}
                    </div>
                    <p className="inline-note">
                      Align the face for <strong>{FACE_VIEW_FIELDS.find((view) => view.key === selectedEditCaptureView)?.label}</strong>, then capture.
                    </p>
                  </div>
                ) : null}
                <div className="multi-view-upload-grid">
                  {FACE_VIEW_FIELDS.map((view) => (
                    <div className="capture-input-card" key={view.key}>
                      <div className="capture-card-header">
                        <span>{view.label}</span>
                        <span className={`status-pill ${editingProfileImages[view.key] ? "present" : "absent"}`}>
                          {editingProfileImages[view.key] ? "Ready" : "Pending"}
                        </span>
                      </div>
                      <input
                        accept="image/*"
                        hidden
                        onChange={(event) => updateEditingFile(view.key, event)}
                        ref={(node) => {
                          editFileInputRefs.current[view.key] = node;
                        }}
                        type="file"
                      />
                      <div className="capture-card-footer">
                        <button className="secondary-button" onClick={() => triggerEditingFilePicker(view.key)} type="button">
                          Upload
                        </button>
                        <button
                          className={`secondary-button ${selectedEditCaptureView === view.key ? "active-capture-button" : ""}`}
                          disabled={editCameraLoading}
                          onClick={() => openEditCamera(view.key)}
                          type="button"
                        >
                          {editCameraLoading && selectedEditCaptureView === view.key
                            ? "Opening..."
                            : editCameraOpen && selectedEditCaptureView === view.key
                              ? "Capture active"
                              : "Capture"}
                        </button>
                        {editingProfileImages[view.key] ? (
                          <button
                            className="ghost-button"
                            onClick={() =>
                              setEditingProfileImages((current) => ({
                                ...current,
                                [view.key]: null
                              }))
                            }
                            type="button"
                          >
                            Remove
                          </button>
                        ) : null}
                      </div>
                      {editingPreviewUrls[view.key] ? (
                        <div className="frame-preview compact-preview">
                          <img alt={`${view.label} preview`} src={editingPreviewUrls[view.key]} />
                        </div>
                      ) : null}
                    </div>
                  ))}
                </div>
              </div>
              <p className="inline-note">
                Upload all five face images together to complete face recognition training for this profile.
              </p>
              <div className="section-actions">
                <button className="secondary-button" onClick={() => {
                  closeEditModal();
                  setEditingProfile(null);
                }} type="button">
                  Cancel
                </button>
                <button className="primary-button" type="submit">
                  Save changes
                </button>
              </div>
            </form>
            <canvas hidden ref={captureCanvasRef} />
          </div>
        </div>
      ) : null}

      {selectedFrame ? (
        <div className="modal-backdrop" onClick={() => setSelectedFrame(null)} role="presentation">
          <div className="modal-card frame-modal-card" onClick={(event) => event.stopPropagation()} role="dialog" aria-modal="true">
            <div className="section-header">
              <div>
                <h3>Captured frame</h3>
                <p>
                  {selectedFrame.name} at {selectedFrame.check_in_time || "-"}
                </p>
              </div>
            </div>

            <div className="frame-preview">
              {selectedFrame.camera_id && selectedFrame.frame_path ? (
                <img
                  alt={`Captured frame for ${selectedFrame.name}`}
                  src={`/api/snapshots/${selectedFrame.camera_id}/${encodeURIComponent(selectedFrame.frame_path)}`}
                />
              ) : (
                <div className="table-empty">Snapshot metadata is missing for this attendance record.</div>
              )}
            </div>

            <div className="section-actions">
              <button className="secondary-button" onClick={() => setSelectedFrame(null)} type="button">
                Close
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </AppShell>
  );
}
