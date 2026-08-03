import {
  Activity,
  BarChart3,
  Camera,
  ClipboardList,
  FileText,
  LayoutDashboard,
  ScanSearch,
  Sparkles,
  Users
} from "lucide-react";
import {
  CAPABILITY_ACTIVITIES_VIEW,
  CAPABILITY_ATTENDANCE_VIEW,
  CAPABILITY_CAMERAS_VIEW,
  CAPABILITY_EMOTIONS_VIEW,
  CAPABILITY_OVERVIEW_VIEW,
  CAPABILITY_PEOPLE_VIEW,
  CAPABILITY_RECOGNITION_MANAGE,
  CAPABILITY_RECOGNITION_VIEW,
  getRoleLabel,
  hasCapability
} from "./rbac";

export { getRoleLabel };

export function getNavigationSections(user) {
  const sections = [];

  if (hasCapability(user, CAPABILITY_OVERVIEW_VIEW)) {
    sections.push({
      label: "Overview",
      items: [
        { label: "Dashboard", to: "/overview", icon: LayoutDashboard }
      ]
    });
  }

  if (
    hasCapability(user, CAPABILITY_ATTENDANCE_VIEW) ||
    hasCapability(user, CAPABILITY_ACTIVITIES_VIEW) ||
    hasCapability(user, CAPABILITY_EMOTIONS_VIEW)
  ) {
    const attendanceItems = [];
    if (hasCapability(user, CAPABILITY_ATTENDANCE_VIEW)) {
      attendanceItems.push(
        { label: "Today", to: "/attendance/today", icon: ClipboardList },
        { label: "Reports", to: "/attendance/reports", icon: FileText }
      );
    }
    if (hasCapability(user, CAPABILITY_ACTIVITIES_VIEW)) {
      attendanceItems.push({ label: "Activity Analytics", to: "/activities/live", icon: Activity });
    }
    if (hasCapability(user, CAPABILITY_EMOTIONS_VIEW)) {
      attendanceItems.push({ label: "Emotion Detection", to: "/emotions/live", icon: Sparkles });
    }
    sections.push({
      label: "Attendance",
      items: attendanceItems
    });
  }

  if (hasCapability(user, CAPABILITY_PEOPLE_VIEW) || hasCapability(user, CAPABILITY_CAMERAS_VIEW)) {
    const operationItems = [];
    if (hasCapability(user, CAPABILITY_PEOPLE_VIEW)) {
      operationItems.push({ label: "People", to: "/people/students", icon: Users });
    }
    if (hasCapability(user, CAPABILITY_CAMERAS_VIEW)) {
      operationItems.push({ label: "Cameras", to: "/cameras", icon: Camera });
    }
    sections.push({
      label: "Operations",
      items: operationItems
    });
  }

  if (hasCapability(user, CAPABILITY_RECOGNITION_VIEW) || hasCapability(user, CAPABILITY_RECOGNITION_MANAGE)) {
    const recognitionItems = [];
    if (hasCapability(user, CAPABILITY_RECOGNITION_MANAGE)) {
      recognitionItems.push(
        { label: "Validation", to: "/recognition/validation", icon: ScanSearch },
        { label: "Threshold Review", to: "/recognition/review", icon: BarChart3 }
      );
    }
    if (hasCapability(user, CAPABILITY_RECOGNITION_VIEW)) {
      recognitionItems.push({ label: "Logs", to: "/recognition/logs", icon: FileText });
    }
    sections.push({
      label: "Recognition",
      items: recognitionItems
    });
  }

  return sections.filter((section) => section.items.length > 0);
}
