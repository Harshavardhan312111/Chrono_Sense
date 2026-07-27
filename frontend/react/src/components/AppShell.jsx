import {
  Bell,
  ChevronRight,
  Command,
  LogOut,
  Search
} from "lucide-react";
import { Link, useLocation } from "react-router-dom";
import { getNavigationSections, getRoleLabel } from "../lib/navigation";
import { getRoleView } from "../lib/roleViews";
import { useAuth } from "../state/auth";

function NavItem({ active, icon: Icon, label, to, variant = "nav-link" }) {
  const className = `${variant} ${active ? "active" : ""}`;

  return (
    <Link className={className} to={to}>
      {Icon ? <span className="nav-icon"><Icon size={16} strokeWidth={2.1} /></span> : null}
      <span>{label}</span>
    </Link>
  );
}

function matchesRoute(pathname, target) {
  return pathname === target || pathname.startsWith(`${target}/`);
}

export function AppShell({
  title,
  subtitle,
  eyebrow = "ChronoSense",
  breadcrumbs = [],
  actions = null,
  attentionCount = 0,
  children
}) {
  const { logout, user } = useAuth();
  const location = useLocation();
  const navigationSections = getNavigationSections(user);
  const breadcrumbItems = breadcrumbs.length
    ? breadcrumbs
    : [
        { label: "Overview", to: "/overview" },
        { label: title }
      ];
  const roleLabel = getRoleLabel(user?.role);
  const roleView = getRoleView(user?.role);
  const shellVariant = roleView?.shell?.layoutVariant || "operations";
  const scopeLabel = roleView?.shell?.scopeLabel || "Campus scope";
  const workspaceTagline = roleView?.shell?.workspaceTagline || "Attendance, people, and camera operations";

  return (
    <div className="app-stage">
      <div className={`app-shell role-shell-${shellVariant}`}>
        <header className="portal-topbar">
          <div className="portal-brand">
            <strong>ChronoSense Workspace</strong>
            <span>{workspaceTagline}</span>
          </div>

          <div className="topbar-brandline">
            <label className="topbar-search">
              <Search size={16} strokeWidth={2.1} />
              <input placeholder="Search people, cameras, classes, reports" type="text" />
            </label>
            <button className="scope-chip" type="button">
              <Command size={14} strokeWidth={2.1} />
              <span>{scopeLabel}</span>
            </button>
          </div>

          <div className="topbar-tools">
            <button className="notification-button" type="button">
              <Bell size={16} strokeWidth={2.1} />
              <span>Alerts</span>
              <strong>{attentionCount}</strong>
            </button>
            <div className="topbar-user">
              <div className="topbar-logo">CS</div>
              <div className="topbar-user-copy">
                <strong>{user?.first_name || user?.username || "Operator"}</strong>
                <span>{roleLabel}</span>
              </div>
              <span className="role-badge">{roleLabel}</span>
            </div>
            <button className="topbar-logout" onClick={logout} type="button">
              <LogOut size={15} strokeWidth={2.1} />
              <span>Sign out</span>
            </button>
          </div>
        </header>

        <div className="workspace-shell">
          <aside className="app-sidebar">
            <div className="sidebar-school">
              <div className="school-badge">CS</div>
              <div className="school-copy">
                <strong>ChronoSense</strong>
                <p>{roleLabel}</p>
              </div>
            </div>

            <div className="sidebar-nav-columns">
              {navigationSections.map((section) => (
                <section className="sidebar-nav-group" key={section.label}>
                  <p className="sidebar-section-title">{section.label}</p>
                  {section.items.map((item) => (
                    <NavItem
                      key={item.to}
                      active={matchesRoute(location.pathname, item.to)}
                      icon={item.icon}
                      label={item.label}
                      to={item.to}
                    />
                  ))}
                </section>
              ))}
            </div>

            <div className="sidebar-user-card">
              <div className="avatar-badge">{(user?.first_name || user?.username || "U").slice(0, 1)}</div>
              <div className="profile-copy">
                <strong>{user?.first_name || user?.username}</strong>
                <p>{roleLabel}</p>
              </div>
            </div>
          </aside>

          <main className="app-main">
            <section className="workspace-hero">
              <div className="workspace-hero-copy">
              <div className="workspace-breadcrumbs" aria-label="Breadcrumbs">
                  {breadcrumbItems.map((item, index) => (
                    <span className="breadcrumb-segment" key={`${item.label}-${index}`}>
                      {item.to ? (
                        <Link className="breadcrumb-link" to={item.to}>
                          {item.label}
                        </Link>
                      ) : (
                        <span className="breadcrumb-current">{item.label}</span>
                      )}
                      {index < breadcrumbItems.length - 1 ? <ChevronRight size={14} strokeWidth={2.1} /> : null}
                    </span>
                  ))}
                </div>
                <p className="eyebrow">{eyebrow}</p>
                <h1>{title}</h1>
                <p className="workspace-subtitle">{subtitle}</p>
                <div className="workspace-meta-row">
                  <span className="badge-light">{roleLabel}</span>
                  <span className="workspace-scope-note">{scopeLabel}</span>
                </div>
              </div>
              <div className="workspace-hero-actions">
                {actions}
              </div>
            </section>

            <div className="app-body">{children}</div>
          </main>
        </div>

        <footer className="portal-footer">
          <span>React operations frontend served by FastAPI</span>
          <span>{title}</span>
        </footer>
      </div>
    </div>
  );
}
