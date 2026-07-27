import {
  getOperationsSnapshot
} from "./admin";

export function formatTimestamp(value) {
  if (!value) {
    return "-";
  }

  const date = new Date(value);

  if (Number.isNaN(date.getTime())) {
    return String(value);
  }

  return date.toLocaleString();
}

export function normalizeNumber(value, fallback = 0) {
  return Number.isFinite(Number(value)) ? Number(value) : fallback;
}

function buildAlert(severity, title, detail, cameraId = null) {
  return {
    severity,
    title,
    detail,
    cameraId
  };
}

export function buildOperationsAlerts(snapshot) {
  const alerts = [];

  for (const camera of snapshot.cameras) {
    if (camera.connection === "disconnected") {
      alerts.push(
        buildAlert(
          "critical",
          `${camera.name} is offline`,
          camera.error || "Camera connection failed during the latest health check.",
          camera.id
        )
      );
    }

    if (camera.enabled && !camera.recognitionRunning) {
      alerts.push(
        buildAlert(
          "warning",
          `${camera.name} recognition is stopped`,
          "Attendance automation will not advance until recognition is restarted.",
          camera.id
        )
      );
    }

    if (camera.unknownFaceCount > 0) {
      alerts.push(
        buildAlert(
          camera.unknownFaceCount > 5 ? "warning" : "info",
          `${camera.name} has ${camera.unknownFaceCount} unknown faces pending`,
          "Review the validation queue to resolve pending identity assignments.",
          camera.id
        )
      );
    }

    if ((camera.activity?.engagement_score || 0) < 0.5 && camera.activity?.total_windows) {
      alerts.push(
        buildAlert(
          "warning",
          `${camera.name} engagement dropped`,
          `${Math.round((camera.activity.engagement_score || 0) * 100)}% student engagement in the latest classroom activity snapshot.`,
          camera.id
        )
      );
    }
  }

  if (!snapshot.cameras.length) {
    alerts.push(
      buildAlert(
        "critical",
        "No cameras configured",
        "The React shell is live, but no active camera inventory is available yet."
      )
    );
  }

  return alerts;
}

export async function loadOperationsSnapshot(date) {
  const snapshot = await getOperationsSnapshot(date);
  const data = snapshot?.data || {};
  const cameraDetails = (data.cameras || []).map((camera) => ({
    ...camera,
    recognitionRunning: Boolean(camera.recognition_running),
    unknownFaceCount: camera.unknown_face_count || 0
  }));
  const attendance = data.attendance || {};
  const uniqueIndividuals = data.unique_individuals?.total || 0;
  const emotionLocations = data.classroom_emotions || {};
  const activityLocations = data.activity_locations || {};
  const alerts = buildOperationsAlerts({ cameras: cameraDetails });

  return {
    date,
    attendance,
    uniqueIndividuals,
    cameras: cameraDetails,
    classroomEmotions: emotionLocations,
    activityLocations,
    alerts,
    recentLogs: data.recent_logs || []
  };
}
