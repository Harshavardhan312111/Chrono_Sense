import { Link } from "react-router-dom";
import { AppShell } from "../components/AppShell";

export function ReportsCenterPage() {
  return (
    <AppShell
      title="Reports Center"
      subtitle="ChronoSense reporting is now positioned as a product-wide capability rather than a single attendance tab."
      eyebrow="Reports"
      breadcrumbs={[
        { label: "Reports", to: "/reports" },
        { label: "Center" }
      ]}
    >
      <section className="scaffold-grid">
        <article className="panel">
          <h3>Attendance reporting</h3>
          <p>Daily, weekly, monthly, and custom-range reports remain fully usable from the React reporting route.</p>
          <div className="link-cluster">
            <Link className="secondary-button inline-button" to="/attendance/reports">
              Open attendance reports
            </Link>
          </div>
        </article>
        <article className="panel">
          <h3>Emotion reporting</h3>
          <p>Trend analysis and classroom emotional summaries now have dedicated module routes that can grow into export-ready reporting workflows.</p>
          <div className="link-cluster">
            <Link className="secondary-button inline-button" to="/emotions/trends">
              Open emotion trends
            </Link>
          </div>
        </article>
        <article className="panel">
          <h3>Behavior reporting</h3>
          <p>Activity reporting routes are now part of the React information architecture and ready for scheduled exports and saved views.</p>
          <div className="link-cluster">
            <Link className="secondary-button inline-button" to="/activities/reports">
              Open behavior reports
            </Link>
          </div>
        </article>
      </section>
    </AppShell>
  );
}
