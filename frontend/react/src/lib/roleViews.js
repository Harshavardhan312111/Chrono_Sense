import {
  ROLE_ADMIN,
  ROLE_CLASS_TEACHER,
  ROLE_DIRECTOR,
  ROLE_MANAGER,
  ROLE_PRINCIPAL
} from "./rbac";

const roleViews = {
  [ROLE_ADMIN]: {
    homePath: "/overview",
    shell: {
      layoutVariant: "command",
      scopeLabel: "Full campus scope",
      workspaceTagline: "System-wide operations, recognition, people, and camera control."
    },
    overview: {
      title: "Admin Command Center",
      subtitle: "Full attendance, profile, camera, and operational visibility with management shortcuts.",
      eyebrow: "Overview",
      defaultFilters: {
        roleScope: "all",
        compareMode: "classes"
      },
      visibleKpis: [
        "profiles_completed",
        "profiles_incomplete",
        "cameras_working",
        "recognition_running",
        "present_today",
        "attendance_rate_today"
      ],
      visibleCharts: [
        "attendance_trend",
        "class_comparison",
        "status_distribution",
        "check_in_distribution",
        "camera_health"
      ],
      visibleTables: ["class_rollup", "recent_attendance_records"],
      quickLinks: [
        { label: "People", to: "/people/students" },
        { label: "Cameras", to: "/cameras" },
        { label: "Attendance", to: "/attendance/today" }
      ]
    }
  },
  [ROLE_MANAGER]: {
    homePath: "/overview",
    shell: {
      layoutVariant: "operations",
      scopeLabel: "Operations scope",
      workspaceTagline: "Operational control for people, classrooms, attendance, and camera readiness."
    },
    overview: {
      title: "Operations Hub",
      subtitle: "Operational attendance, profile completion, and camera readiness in one view.",
      eyebrow: "Overview",
      defaultFilters: {
        roleScope: "all",
        compareMode: "classes"
      },
      visibleKpis: [
        "profiles_completed",
        "profiles_incomplete",
        "cameras_added",
        "cameras_working",
        "present_today",
        "attendance_rate_today"
      ],
      visibleCharts: [
        "camera_health",
        "attendance_trend",
        "class_comparison",
        "status_distribution"
      ],
      visibleTables: ["class_rollup", "recent_attendance_records"],
      quickLinks: [
        { label: "People", to: "/people/students" },
        { label: "Cameras", to: "/cameras" },
        { label: "Reports", to: "/attendance/reports" }
      ]
    }
  },
  [ROLE_PRINCIPAL]: {
    homePath: "/overview",
    shell: {
      layoutVariant: "academic",
      scopeLabel: "School-wide read only",
      workspaceTagline: "School-wide academic operations with read-only summaries and attention signals."
    },
    overview: {
      title: "Principal Overview",
      subtitle: "School-wide attendance and class performance with attention-focused summaries.",
      eyebrow: "Overview",
      defaultFilters: {
        roleScope: "all",
        compareMode: "classes"
      },
      visibleKpis: [
        "present_today",
        "absent_today",
        "attendance_rate_today",
        "classes_below_threshold",
        "cameras_working"
      ],
      visibleCharts: [
        "attendance_trend",
        "class_comparison",
        "status_distribution",
        "check_in_distribution"
      ],
      visibleTables: ["class_rollup", "recent_attendance_records"]
    }
  },
  [ROLE_DIRECTOR]: {
    homePath: "/overview",
    shell: {
      layoutVariant: "executive",
      scopeLabel: "Leadership analytics scope",
      workspaceTagline: "Leadership-focused analytics across attendance, class trends, and campus readiness."
    },
    overview: {
      title: "Director Analytics",
      subtitle: "Leadership-facing attendance and readiness analytics with cross-school comparisons.",
      eyebrow: "Overview",
      defaultFilters: {
        roleScope: "all",
        compareMode: "classes"
      },
      visibleKpis: [
        "attendance_rate_today",
        "present_today",
        "multi_class_delta",
        "profile_completion_rate",
        "camera_uptime"
      ],
      visibleCharts: [
        "attendance_trend",
        "class_comparison",
        "status_distribution",
        "check_in_distribution"
      ],
      visibleTables: ["class_rollup"]
    }
  },
  [ROLE_CLASS_TEACHER]: {
    homePath: "/attendance/today",
    shell: {
      layoutVariant: "classroom",
      scopeLabel: "Assigned classroom scope",
      workspaceTagline: "Assigned-class attendance and student readiness view for daily classroom follow-up."
    },
    overview: {
      title: "Classroom Overview",
      subtitle: "Your assigned class attendance, arrivals, and follow-up signals in one place.",
      eyebrow: "Overview",
      defaultFilters: {
        roleScope: "student",
        compareMode: "sections"
      },
      visibleKpis: [
        "present_today",
        "absent_today",
        "late_today",
        "attendance_rate_today",
        "profiles_incomplete"
      ],
      visibleCharts: [
        "attendance_trend",
        "class_comparison",
        "check_in_distribution"
      ],
      visibleTables: ["recent_attendance_records"]
    }
  }
};

const fallbackRoleView = roleViews[ROLE_MANAGER];

export function getRoleView(role) {
  return roleViews[role] || fallbackRoleView;
}

export function getDefaultRouteForRole(role) {
  return getRoleView(role).homePath;
}

export function getRoleLayoutVariant(role) {
  return getRoleView(role).shell.layoutVariant;
}
