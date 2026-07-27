import { spawn } from "node:child_process";

const service = (process.argv[2] || "").trim().toLowerCase();
const python = "./.venv/bin/python";
const uvicorn = "./.venv/bin/uvicorn";

const services = {
  frontend: {
    processes: [
      {
        name: "frontend",
        command: "npm",
        args: ["--prefix", "frontend/react", "run", "dev"],
      },
    ],
  },
  attendance: {
    processes: [
      {
        name: "attendance-api",
        command: uvicorn,
        args: ["--app-dir", "backend", "attendance_service:app", "--host", "0.0.0.0", "--port", "8000", "--reload"],
      },
      {
        name: "attendance-worker",
        command: python,
        args: ["backend/attendance_worker.py"],
      },
    ],
  },
  emotion: {
    processes: [
      {
        name: "emotion-api",
        command: uvicorn,
        args: ["--app-dir", "backend", "emotion_service:app", "--host", "0.0.0.0", "--port", "8001", "--reload"],
      },
      {
        name: "emotion-worker",
        command: python,
        args: ["backend/emotion_worker.py"],
      },
    ],
  },
  activity: {
    processes: [
      {
        name: "activity-api",
        command: uvicorn,
        args: ["--app-dir", "backend", "activity_service:app", "--host", "0.0.0.0", "--port", "8002", "--reload"],
      },
      {
        name: "activity-worker",
        command: python,
        args: ["backend/activity_worker.py"],
      },
    ],
  },
};

if (!services[service]) {
  console.error(
    [
      "Unknown service.",
      "Use one of:",
      "  npm run dev: frontend",
      "  npm run dev: attendance",
      "  npm run dev: emotion",
      "  npm run dev: activity",
    ].join("\n")
  );
  process.exit(1);
}

const prepare = spawn(
  "sh",
  [
    "-c",
    "mkdir -p logs; if [ ! -x ./.venv/bin/python ]; then python3 -m venv .venv; fi; if ! ./.venv/bin/python -c \"import pymongo\" >/dev/null 2>&1; then ./.venv/bin/pip install -r requirements.txt; fi",
  ],
  {
    cwd: process.cwd(),
    env: process.env,
    stdio: "inherit",
  }
);

prepare.on("exit", (code, signal) => {
  if (signal) {
    process.kill(process.pid, signal);
    return;
  }

  if ((code ?? 0) !== 0) {
    process.exit(code ?? 1);
  }

  const children = [];
  let shuttingDown = false;

  const stopChildren = (receivedSignal = "SIGTERM") => {
    if (shuttingDown) {
      return;
    }
    shuttingDown = true;
    for (const child of children) {
      if (!child.killed) {
        child.kill(receivedSignal);
      }
    }
  };

  process.on("SIGINT", () => stopChildren("SIGINT"));
  process.on("SIGTERM", () => stopChildren("SIGTERM"));

  for (const proc of services[service].processes) {
    const child = spawn(proc.command, proc.args, {
      cwd: process.cwd(),
      env: {
        ...process.env,
        PYTHONDONTWRITEBYTECODE: "1",
      },
      stdio: "inherit",
    });
    children.push(child);

    child.on("exit", (childCode, childSignal) => {
      if (!shuttingDown) {
        console.error(`${proc.name} exited with ${childSignal ?? childCode ?? 0}`);
        stopChildren("SIGTERM");
        process.exit(childCode ?? 1);
      }
    });
  }
});
