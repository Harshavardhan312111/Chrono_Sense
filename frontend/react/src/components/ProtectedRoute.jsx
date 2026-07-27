import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "../state/auth";
import { hasCapability } from "../lib/rbac";

export function ProtectedRoute({ allowedRoles, capability, children }) {
  const { isAuthenticated, isReady, user } = useAuth();
  const location = useLocation();

  if (!isReady) {
    return <div className="screen-message">Restoring your session...</div>;
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }

  if (allowedRoles?.length && !allowedRoles.includes(user?.role)) {
    const redirectPath = "/overview";
    return <Navigate to={redirectPath} replace />;
  }

  if (capability && !hasCapability(user, capability)) {
    return <Navigate to="/overview" replace />;
  }

  return children;
}
