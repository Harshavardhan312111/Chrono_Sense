import { Link } from "react-router-dom";
import { AppShell } from "../components/AppShell";

export function WorkspaceScaffoldPage({
  title,
  subtitle,
  eyebrow,
  breadcrumbs,
  highlights = [],
  links = []
}) {
  return (
    <AppShell
      title={title}
      subtitle={subtitle}
      eyebrow={eyebrow}
      breadcrumbs={breadcrumbs}
    >
      <section className="panel">
        <div className="section-header">
          <div>
            <h3>Module rollout</h3>
            <p>This route now exists in the React-only information architecture and is ready for deeper workflow decomposition.</p>
          </div>
        </div>

        <div className="scaffold-grid">
          {highlights.map((item) => (
            <article className="metric-card" key={item}>
              <span>Implementation note</span>
              <strong>In progress</strong>
              <p>{item}</p>
            </article>
          ))}
        </div>

        {links.length ? (
          <div className="link-cluster">
            {links.map((link) => (
              <Link className="secondary-button inline-button" key={link.to} to={link.to}>
                {link.label}
              </Link>
            ))}
          </div>
        ) : null}
      </section>
    </AppShell>
  );
}
