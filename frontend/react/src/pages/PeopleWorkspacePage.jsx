import { AdminDashboardPage } from "./AdminDashboardPage";
import { useAuth } from "../state/auth";

export function PeopleWorkspacePage({ mode }) {
  const isStudentMode = mode === "students";
  const { user } = useAuth();
  const isTeacher = user?.role === "class_teacher";
  const isPrincipal = user?.role === "principal";
  const isManager = user?.role === "manager";

  return (
    <AdminDashboardPage
      forcedTab="profiles"
      initialProfileType={isStudentMode ? "student" : "faculty"}
      title={isStudentMode ? "Student Directory" : "Faculty Directory"}
      subtitle={isStudentMode
        ? isTeacher
          ? "Assigned student roster with profile completion visibility."
          : isPrincipal
            ? "Read-only student directory with completion status and class context."
            : isManager
              ? "Roster management, bulk upload, and incomplete profile follow-up for enrolled students."
              : "Roster management, re-registration, and profile maintenance for enrolled students."
        : isTeacher
          ? "Assigned faculty and support contacts visible to your class scope."
          : isPrincipal
            ? "Read-only faculty and staff directory."
            : "Faculty and staff identity registry maintained within the React-only operations frontend."}
      breadcrumbs={[
        { label: "People", to: isStudentMode ? "/people/students" : "/people/faculty" },
        { label: isStudentMode ? "Students" : "Faculty" }
      ]}
    />
  );
}
