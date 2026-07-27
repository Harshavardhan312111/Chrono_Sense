import { Navigate, Route, Routes } from "react-router-dom";
import { ProtectedRoute } from "./components/ProtectedRoute";
import { useAuth } from "./state/auth";
import { LoginPage } from "./pages/LoginPage";
import { AdminDashboardPage } from "./pages/AdminDashboardPage";
import { NotFoundPage } from "./pages/NotFoundPage";
import { RegistrationPage } from "./pages/RegistrationPage";
import { ValidationPage } from "./pages/ValidationPage";
import { CameraSettingsPage } from "./pages/CameraSettingsPage";
import { CameraStreamViewerPage } from "./pages/CameraStreamViewerPage";
import { ActivityAnalyticsPage } from "./pages/ActivityAnalyticsPage";
import { AlertsPage } from "./pages/AlertsPage";
import { AttendanceWorkspacePage } from "./pages/AttendanceWorkspacePage";
import { ClassroomsPage } from "./pages/ClassroomsPage";
import { EmotionAnalyticsPage } from "./pages/EmotionAnalyticsPage";
import { EmotionSensingTestPage } from "./pages/EmotionSensingTestPage";
import { OverviewDashboardPage } from "./pages/OverviewDashboardPage";
import { PersonEmotionTimelinePage } from "./pages/PersonEmotionTimelinePage";
import { PeopleWorkspacePage } from "./pages/PeopleWorkspacePage";
import { RecognitionLogsPage } from "./pages/RecognitionLogsPage";
import { ReportsCenterPage } from "./pages/ReportsCenterPage";
import { WorkspaceScaffoldPage } from "./pages/WorkspaceScaffoldPage";
import { LiveOperationsPage } from "./pages/LiveOperationsPage";
import {
  CAPABILITY_ACTIVITIES_VIEW,
  CAPABILITY_ANALYTICS_VIEW,
  CAPABILITY_ATTENDANCE_VIEW,
  CAPABILITY_CAMERAS_VIEW,
  CAPABILITY_EMOTIONS_VIEW,
  CAPABILITY_OVERVIEW_VIEW,
  CAPABILITY_PEOPLE_MANAGE,
  CAPABILITY_PEOPLE_VIEW,
  CAPABILITY_RECOGNITION_MANAGE,
  CAPABILITY_RECOGNITION_VIEW,
  CAPABILITY_SYSTEM_ADMIN
} from "./lib/rbac";
import { getDefaultRouteForRole } from "./lib/roleViews";

function HomeRedirect() {
  const { isAuthenticated, user } = useAuth();

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  return <Navigate to={getDefaultRouteForRole(user?.role)} replace />;
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<HomeRedirect />} />
      <Route path="/login" element={<LoginPage />} />
      <Route path="/login/admin" element={<Navigate to="/login" replace />} />
      <Route path="/login/director" element={<Navigate to="/login" replace />} />
      <Route
        path="/overview"
        element={
          <ProtectedRoute capability={CAPABILITY_OVERVIEW_VIEW}>
            <OverviewDashboardPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/overview/live"
        element={
          <ProtectedRoute capability={CAPABILITY_OVERVIEW_VIEW}>
            <LiveOperationsPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/overview/alerts"
        element={
          <ProtectedRoute capability={CAPABILITY_OVERVIEW_VIEW}>
            <AlertsPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/attendance/today"
        element={
          <ProtectedRoute capability={CAPABILITY_ATTENDANCE_VIEW}>
            <AttendanceWorkspacePage mode="today" />
          </ProtectedRoute>
        }
      />
      <Route
        path="/attendance/history"
        element={
          <ProtectedRoute capability={CAPABILITY_ATTENDANCE_VIEW}>
            <AttendanceWorkspacePage mode="history" />
          </ProtectedRoute>
        }
      />
      <Route
        path="/attendance/calendar"
        element={
          <ProtectedRoute capability={CAPABILITY_ATTENDANCE_VIEW}>
            <AttendanceWorkspacePage mode="calendar" />
          </ProtectedRoute>
        }
      />
      <Route
        path="/attendance/reports"
        element={
          <ProtectedRoute capability={CAPABILITY_ATTENDANCE_VIEW}>
            <AttendanceWorkspacePage mode="reports" />
          </ProtectedRoute>
        }
      />
      <Route
        path="/attendance/analytics"
        element={
          <ProtectedRoute capability={CAPABILITY_ANALYTICS_VIEW}>
            <AttendanceWorkspacePage mode="analytics" />
          </ProtectedRoute>
        }
      />
      <Route
        path="/recognition/validation"
        element={
          <ProtectedRoute capability={CAPABILITY_RECOGNITION_MANAGE}>
            <ValidationPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/recognition/unknown-faces"
        element={
          <ProtectedRoute capability={CAPABILITY_RECOGNITION_MANAGE}>
            <ValidationPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/recognition/logs"
        element={
          <ProtectedRoute capability={CAPABILITY_RECOGNITION_VIEW}>
            <RecognitionLogsPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/emotions/live"
        element={
          <ProtectedRoute capability={CAPABILITY_EMOTIONS_VIEW}>
            <EmotionAnalyticsPage mode="live" />
          </ProtectedRoute>
        }
      />
      <Route
        path="/emotions/test"
        element={
          <ProtectedRoute capability={CAPABILITY_EMOTIONS_VIEW}>
            <EmotionSensingTestPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/emotions/trends"
        element={
          <ProtectedRoute capability={CAPABILITY_EMOTIONS_VIEW}>
            <EmotionAnalyticsPage mode="trends" />
          </ProtectedRoute>
        }
      />
      <Route
        path="/emotions/classes"
        element={
          <ProtectedRoute capability={CAPABILITY_EMOTIONS_VIEW}>
            <EmotionAnalyticsPage mode="classes" />
          </ProtectedRoute>
        }
      />
      <Route
        path="/emotions/students/:profileId"
        element={
          <ProtectedRoute capability={CAPABILITY_EMOTIONS_VIEW}>
            <PersonEmotionTimelinePage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/activities/live"
        element={
          <ProtectedRoute capability={CAPABILITY_ACTIVITIES_VIEW}>
            <ActivityAnalyticsPage mode="live" />
          </ProtectedRoute>
        }
      />
      <Route
        path="/activities/engagement"
        element={
          <ProtectedRoute capability={CAPABILITY_ACTIVITIES_VIEW}>
            <ActivityAnalyticsPage mode="engagement" />
          </ProtectedRoute>
        }
      />
      <Route
        path="/activities/reports"
        element={
          <ProtectedRoute capability={CAPABILITY_ACTIVITIES_VIEW}>
            <ActivityAnalyticsPage mode="reports" />
          </ProtectedRoute>
        }
      />
      <Route
        path="/classrooms"
        element={
          <ProtectedRoute capability={CAPABILITY_ACTIVITIES_VIEW}>
            <ClassroomsPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/people/students"
        element={
          <ProtectedRoute capability={CAPABILITY_PEOPLE_VIEW}>
            <PeopleWorkspacePage mode="students" />
          </ProtectedRoute>
        }
      />
      <Route
        path="/people/faculty"
        element={
          <ProtectedRoute capability={CAPABILITY_PEOPLE_VIEW}>
            <PeopleWorkspacePage mode="faculty" />
          </ProtectedRoute>
        }
      />
      <Route
        path="/people/register"
        element={
          <ProtectedRoute capability={CAPABILITY_PEOPLE_MANAGE}>
            <RegistrationPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/cameras"
        element={
          <ProtectedRoute capability={CAPABILITY_CAMERAS_VIEW}>
            <CameraSettingsPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/cameras/setup"
        element={
          <ProtectedRoute capability={CAPABILITY_CAMERAS_VIEW}>
            <CameraSettingsPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/cameras/stream"
        element={
          <ProtectedRoute capability={CAPABILITY_CAMERAS_VIEW}>
            <CameraStreamViewerPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/reports"
        element={
          <ProtectedRoute capability={CAPABILITY_ANALYTICS_VIEW}>
            <ReportsCenterPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/admin/users"
        element={
          <ProtectedRoute capability={CAPABILITY_SYSTEM_ADMIN}>
            <WorkspaceScaffoldPage
              title="User Administration"
              subtitle="Future-facing workspace for user provisioning, operator onboarding, and role lifecycle management."
              eyebrow="Administration"
              breadcrumbs={[
                { label: "Administration" },
                { label: "Users" }
              ]}
              highlights={[
                "Current backend roles remain admin and director.",
                "Administrator, Operator, Teacher, and Viewer role design is now reflected in the shell IA.",
                "Backend permission claims still need to expand before this screen becomes fully interactive."
              ]}
            />
          </ProtectedRoute>
        }
      />
      <Route
        path="/admin/roles"
        element={
          <ProtectedRoute capability={CAPABILITY_SYSTEM_ADMIN}>
            <WorkspaceScaffoldPage
              title="Roles and Permissions"
              subtitle="Permission-aware navigation is now in place on the frontend shell, while backend claims remain the next implementation step."
              eyebrow="Administration"
              breadcrumbs={[
                { label: "Administration" },
                { label: "Roles" }
              ]}
              highlights={[
                "Administrator maps to the current admin role.",
                "Viewer maps to the current director role.",
                "Operator and Teacher remain planned backend authorization additions."
              ]}
            />
          </ProtectedRoute>
        }
      />
      <Route
        path="/admin/system"
        element={
          <ProtectedRoute capability={CAPABILITY_SYSTEM_ADMIN}>
            <WorkspaceScaffoldPage
              title="System Health"
              subtitle="Use live operations, camera monitoring, and recognition logs for today’s operational visibility while deeper system administration evolves."
              eyebrow="Administration"
              breadcrumbs={[
                { label: "Administration" },
                { label: "System" }
              ]}
              highlights={[
                "Recognition and camera monitoring already live under Overview, Recognition, and Cameras.",
                "This route reserves the admin surface for future health checks, environment diagnostics, and audit trails."
              ]}
            />
          </ProtectedRoute>
        }
      />
      <Route
        path="/admin"
        element={
          <ProtectedRoute capability={CAPABILITY_SYSTEM_ADMIN}>
            <Navigate to="/overview" replace />
          </ProtectedRoute>
        }
      />
      <Route
        path="/director"
        element={
          <ProtectedRoute capability={CAPABILITY_ANALYTICS_VIEW}>
            <Navigate to="/overview" replace />
          </ProtectedRoute>
        }
      />
      <Route
        path="/register"
        element={
          <ProtectedRoute capability={CAPABILITY_PEOPLE_MANAGE}>
            <Navigate to="/people/register" replace />
          </ProtectedRoute>
        }
      />
      <Route
        path="/validation"
        element={
          <ProtectedRoute capability={CAPABILITY_RECOGNITION_MANAGE}>
            <Navigate to="/recognition/validation" replace />
          </ProtectedRoute>
        }
      />
      <Route
        path="/camera-stream"
        element={
          <ProtectedRoute capability={CAPABILITY_CAMERAS_VIEW}>
            <Navigate to="/cameras/stream" replace />
          </ProtectedRoute>
        }
      />
      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  );
}
