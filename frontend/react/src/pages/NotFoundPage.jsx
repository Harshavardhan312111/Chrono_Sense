import { Link } from "react-router-dom";

export function NotFoundPage() {
  return (
    <div className="screen-message">
      <div>
        <p className="eyebrow">404</p>
        <h1>That route has not been mapped yet.</h1>
        <p>Return to the React workspace home and continue from a supported module.</p>
        <Link className="primary-button inline-button" to="/">
          Back to app home
        </Link>
      </div>
    </div>
  );
}
