# ChronoSense Installation Guide

This guide installs the ChronoSense backend, frontend, Python dependencies, JavaScript dependencies, emotion models, and MongoDB configuration.

## Prerequisites

Install Python 3.10–3.14, Node.js 18 or newer, npm, Git, and MongoDB 6 or newer.

Verify:

```bash
python3 --version
node --version
npm --version
git --version
```

On macOS with Homebrew:

```bash
brew install python node mongodb-community
brew services start mongodb-community
```

## Clone the repository

```bash
git clone https://github.com/Harshavardhan312111/Chrono_Sense.git
cd Chrono_Sense
```

## Configure MongoDB

```bash
cp .env.example .env
```

Set these values in `.env`:

```dotenv
MONGO_URI=mongodb://localhost:27017
MONGO_DB_NAME=chronosense
```

The `.env` file is local-only and must not be committed.

## Install everything

```bash
chmod +x scripts/setup/install.sh
./scripts/setup/install.sh
```

The installer creates `.venv`, installs Python requirements, installs frontend packages, creates runtime directories, downloads FERPlus, and initializes the configured EmotiEffLib model cache.

To redownload models:

```bash
./scripts/setup/install.sh --force
```

## Optional MMA-DFER model

MMA-DFER is not required by the default `auto` backend. To install it, provide a valid checkpoint URL:

```bash
export CHRONOSENSE_MMA_DFER_CHECKPOINT_URL="https://your-valid-checkpoint-url/fold1_112.pth"
./scripts/setup/install.sh --with-mma-dfer
```

Then configure:

```dotenv
CHRONOSENSE_EMOTION_BACKEND=mma_dfer
CHRONOSENSE_MMA_DFER_CHECKPOINT_PATH=backend/models/mma-dfer/fold1_112.pth
```

Model files are intentionally excluded from Git.

## Start the application

Start the backend:

```bash
./start-server.sh
```

Backend URL: `http://localhost:8000`.

Start the frontend in a second terminal:

```bash
npm --prefix frontend/react run dev
```

Frontend URL: normally `http://localhost:5173`.

To run backend and frontend together:

```bash
npm run dev
```

## Verify installation

```bash
./.venv/bin/python -m compileall -q backend
test -s backend/models/emotion-ferplus-8.onnx && echo "FERPlus model ready"
npm run build
curl http://localhost:8000/api/health
```

## Troubleshooting

### MongoDB is unavailable

```bash
mongosh --eval 'db.adminCommand({ ping: 1 })'
```

### FERPlus model is missing

```bash
./scripts/setup/install.sh --force
```

### Python installation fails

```bash
rm -rf .venv
./scripts/setup/install.sh
```

### Frontend installation fails

```bash
rm -rf frontend/react/node_modules
npm --prefix frontend/react ci
```

### Port is already in use

```bash
lsof -i :8000
lsof -i :5173
```

Stop the conflicting process and restart the application.

### GitHub push returns 403

Use a GitHub account with repository write permission and a Personal Access Token:

```bash
printf "protocol=https\nhost=github.com\n\n" | git credential-osxkeychain erase
git push --force-with-lease origin main
```

## Files generated locally

These are intentionally not committed:

- `.venv/`
- `frontend/react/node_modules/`
- `frontend/react/dist/`
- downloaded model files under `backend/models/`
- `backend/face_snapshots/`
- local databases, backups, caches, and logs

After cloning, run `./scripts/setup/install.sh` to recreate the local environment.
