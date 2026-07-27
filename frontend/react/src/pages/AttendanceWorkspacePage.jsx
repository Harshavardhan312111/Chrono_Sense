import { AdminDashboardPage } from "./AdminDashboardPage";
import { WorkspaceScaffoldPage } from "./WorkspaceScaffoldPage";
import { useAuth } from "../state/auth";

const attendanceBreadcrumbs = {
  today: [
    { label: "Attendance", to: "/attendance/today" },
    { label: "Today's Attendance" }
  ],
  reports: [
    { label: "Attendance", to: "/attendance/today" },
    { label: "Reports" }
  ],
  analytics: [
    { label: "Attendance", to: "/attendance/today" },
    { label: "Analytics" }
  ],
  history: [
    { label: "Attendance", to: "/attendance/today" },
    { label: "History" }
  ],
  calendar: [
    { label: "Attendance", to: "/attendance/today" },
    { label: "Calendar" }
  ]
};

export function AttendanceWorkspacePage({ mode }) {
  const { user } = useAuth();
  const isTeacher = user?.role === "class_teacher";
  const isPrincipal = user?.role === "principal";
  const isAdmin = user?.role === "admin";
  const isManager = user?.role === "manager";

  if (mode === "today") {
    return (
      <AdminDashboardPage
        forcedTab="attendance"
        title={isTeacher ? "Class Attendance" : isPrincipal ? "School Attendance Snapshot" : "Today's Attendance"}
        subtitle={isTeacher
          ? "Assigned-class roster, present and absent review, and student follow-up for today."
          : isPrincipal
            ? "Read-only school-wide attendance snapshot with class-level drilldown."
            : isAdmin || isManager
              ? "Operational attendance control room with current-day records, status, and evidence review."
              : "Attendance review for the current day."}
        breadcrumbs={attendanceBreadcrumbs.today}
      />
    );
  }

  if (mode === "reports") {
    return (
      <AdminDashboardPage
        forcedTab="reports"
        title={isTeacher ? "Class Attendance Reports" : isPrincipal ? "School Attendance Reports" : "Attendance Reports"}
        subtitle={isTeacher
          ? "Assigned-scope attendance summaries and student report views."
          : isPrincipal
            ? "School-wide read-only attendance summaries with comparison filters."
            : "Generate daily, weekly, monthly, and custom-range attendance summaries from the React reporting workspace."}
        breadcrumbs={attendanceBreadcrumbs.reports}
      />
    );
  }

  if (mode === "analytics") {
    return (
      <AdminDashboardPage
        forcedTab="dashboard"
        title={isTeacher ? "Class Attendance Analytics" : isPrincipal ? "Attendance Analytics Overview" : "Attendance Analytics"}
        subtitle={isTeacher
          ? "Assigned-class attendance patterns and roster-level trend summaries."
          : isPrincipal
            ? "School-wide attendance trends and class-level comparison metrics."
            : "Attendance trends, KPI summaries, and operational performance metrics now live on a dedicated route."}
        breadcrumbs={attendanceBreadcrumbs.analytics}
      />
    );
  }

  return (
    <WorkspaceScaffoldPage
      title={mode === "calendar" ? "Attendance Calendar" : "Attendance History"}
      subtitle={mode === "calendar"
        ? "Calendar-oriented attendance review now has a route-native home in the React shell."
        : "Historical attendance search has been separated from the old hash-tab dashboard and reserved for the next decomposition pass."}
      eyebrow="Attendance"
      breadcrumbs={attendanceBreadcrumbs[mode]}
      highlights={[
        mode === "calendar"
          ? "Day, week, student, and class calendar views are planned on this route."
          : "Historical tables, saved filters, and trend drilldowns will move here from the monolithic admin dashboard.",
        "Current-day operations and reporting are already available on the neighboring attendance routes."
      ]}
      links={[
        { label: "Open today's attendance", to: "/attendance/today" },
        { label: "Open reports", to: "/attendance/reports" }
      ]}
    />
  );
}
