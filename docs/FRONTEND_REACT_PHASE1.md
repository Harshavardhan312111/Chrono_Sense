# Frontend React Phase 1

This repository now uses the React frontend in `frontend/react/` as the primary and only maintained UI.

## What was added

- Vite-based React scaffold
- shared auth context using the existing `/api/auth/login`, `/api/auth/verify`, and `/api/auth/logout` endpoints
- protected admin and director routes
- a backend target that serves the React build as the default frontend

## Current status

The React app is the production/default UI and currently provides:

- login flow
- admin shell
- director shell
- routing and token persistence foundations

## Local development

From the repo root:

```bash
npm install
npm run dev
```

This starts:

- the FastAPI backend via `npm --prefix backend run dev`
- the React frontend via `npm --prefix frontend/react run dev`

If `frontend/react/node_modules` is missing, the root dev command installs the frontend dependencies automatically before starting Vite.

For frontend-only work, from `frontend/react/`:

```bash
npm install
npm run dev
```

The Vite dev server proxies `/api/*` requests to `http://localhost:8000`.

## Production serving path

Build the app with:

```bash
npm run build
```

Once `frontend/react/dist/` exists, FastAPI serves it from `/`.

## Suggested next steps

1. Continue filling parity gaps for remaining non-core analytics views.
2. Remove any remaining legacy frontend references from documentation and utility scripts.
3. Add chart components and protected data-fetching patterns where needed.
4. Update `start-server.sh` to optionally build the React bundle after the workflow is validated.
