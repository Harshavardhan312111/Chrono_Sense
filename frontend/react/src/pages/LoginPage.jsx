import { useState } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { getDefaultRouteForRole } from "../lib/roleViews";
import { useAuth } from "../state/auth";

const initialState = {
  username: "",
  password: "",
  rememberMe: true
};

const demoAccounts = [
  { label: "Admin", username: "admin", password: "admin123" },
  { label: "Manager", username: "manager", password: "manager123" },
  { label: "Principal", username: "principal", password: "principal123" },
  { label: "Director", username: "director", password: "director123" },
  { label: "Class Teacher", username: "teacher", password: "teacher123" }
];

export function LoginPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const { isAuthenticated, isReady, login, user } = useAuth();
  const [formState, setFormState] = useState(initialState);
  const [error, setError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  if (isReady && isAuthenticated) {
    const redirectPath = location.state?.from || getDefaultRouteForRole(user?.role);
    return <Navigate to={redirectPath} replace />;
  }

  async function handleSubmit(event) {
    event.preventDefault();
    setIsSubmitting(true);
    setError("");

    try {
      const loggedInUser = await login(formState);
      navigate(location.state?.from || getDefaultRouteForRole(loggedInUser?.role), {
        replace: true
      });
    } catch (submitError) {
      setError(submitError.message || "Unable to sign in.");
    } finally {
      setIsSubmitting(false);
    }
  }

  function updateField(event) {
    const { name, value, type, checked } = event.target;
    setFormState((current) => ({
      ...current,
      [name]: type === "checkbox" ? checked : value
    }));
  }

  function fillDemoCredentials(account) {
    setFormState((current) => ({
      ...current,
      username: account.username,
      password: account.password
    }));
  }

  return (
    <div className="login-page">
      <section className="login-panel">
        <p className="eyebrow">Secure Access</p>
        <h1>Sign in to ChronoSense.</h1>
        <p className="login-copy">One login supports administrators, managers, principals, directors, and class teachers with role-aware access after authentication.</p>

        <div className="info-card">
          <h2>Demo accounts</h2>
          <div className="link-cluster">
            {demoAccounts.map((account) => (
              <button
                className="secondary-button"
                key={account.username}
                onClick={() => fillDemoCredentials(account)}
                type="button"
              >
                {account.label}
              </button>
            ))}
          </div>
        </div>

        <form className="login-form" onSubmit={handleSubmit}>
          <label>
            Username
            <input
              autoComplete="username"
              name="username"
              onChange={updateField}
              placeholder="Enter your username"
              required
              value={formState.username}
            />
          </label>

          <label>
            Password
            <input
              autoComplete="current-password"
              name="password"
              onChange={updateField}
              placeholder="Enter your password"
              required
              type="password"
              value={formState.password}
            />
          </label>

          <label className="checkbox-row">
            <input
              checked={formState.rememberMe}
              name="rememberMe"
              onChange={updateField}
              type="checkbox"
            />
            Keep me signed in on this browser
          </label>

          {error ? <p className="form-error">{error}</p> : null}

          <div className="form-actions">
            <button className="primary-button" disabled={isSubmitting} type="submit">
              {isSubmitting ? "Signing in..." : "Sign in"}
            </button>
          </div>
        </form>
      </section>

      <section className="info-panel">
        <div className="info-card">
          <h2>Role model</h2>
          <ul>
            <li>Admin has full system access</li>
            <li>Manager handles people, classes, and cameras</li>
            <li>Principal has school-wide read-only operations visibility</li>
            <li>Director sees analytics-focused leadership views</li>
            <li>Class Teacher is scoped to assigned classes and sections</li>
          </ul>
        </div>
        <div className="info-card accent">
          <h2>Current platform scope</h2>
          <ul>
            <li>Attendance, activity, and emotion routes follow the same role policy</li>
            <li>Server-side filtering limits class teacher access to assigned scope</li>
            <li>Operational actions are hidden or blocked for read-only roles</li>
          </ul>
        </div>
      </section>
    </div>
  );
}
