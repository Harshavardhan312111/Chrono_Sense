#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
FORCE=0
MMA=0
for arg in "$@"; do
  case "$arg" in
    --force) FORCE=1 ;;
    --with-mma-dfer) MMA=1 ;;
    -h|--help) echo "Usage: $0 [--force] [--with-mma-dfer]"; exit 0 ;;
    *) echo "Unknown option: $arg" >&2; exit 2 ;;
  esac
done

command -v python3 >/dev/null || { echo "Python 3 is required" >&2; exit 1; }
command -v node >/dev/null || { echo "Node.js is required" >&2; exit 1; }
command -v npm >/dev/null || { echo "npm is required" >&2; exit 1; }

if [ ! -x .venv/bin/python ]; then python3 -m venv .venv; fi
PYTHON="$ROOT/.venv/bin/python"
PIP="$ROOT/.venv/bin/pip"
"$PIP" install --upgrade pip
"$PIP" install -r requirements.txt

if [ -f frontend/react/package-lock.json ]; then npm --prefix frontend/react ci; else npm --prefix frontend/react install; fi
mkdir -p backend/models/mma-dfer backend/face_snapshots logs

download() {
  local url="$1" dst="$2" tmp="${2}.download.$$"
  if [ "$FORCE" -eq 0 ] && [ -s "$dst" ]; then echo "Using $(basename "$dst")"; return; fi
  echo "Downloading $(basename "$dst")"
  curl --fail --location --retry 3 --retry-delay 2 --progress-bar "$url" -o "$tmp"
  test -s "$tmp" && mv "$tmp" "$dst"
}

download "${CHRONOSENSE_FERPLUS_MODEL_URL:-https://github.com/onnx/models/raw/main/vision/body_analysis/emotion_ferplus/model/emotion-ferplus-8.onnx}" backend/models/emotion-ferplus-8.onnx

"$PYTHON" - <<'PY'
import os
from emotiefflib.facial_analysis import EmotiEffLibRecognizer
EmotiEffLibRecognizer(
    engine=os.getenv("CHRONOSENSE_EMOTIEFFLIB_ENGINE", "onnx"),
    model_name=os.getenv("CHRONOSENSE_EMOTIEFFLIB_MODEL_NAME", "enet_b2_8"),
    device=os.getenv("CHRONOSENSE_EMOTIEFFLIB_DEVICE", "cpu"),
)
print("EmotiEffLib model ready")
PY

if [ "$MMA" -eq 1 ]; then
  : "${CHRONOSENSE_MMA_DFER_CHECKPOINT_URL:?Set CHRONOSENSE_MMA_DFER_CHECKPOINT_URL before using --with-mma-dfer}"
  download "$CHRONOSENSE_MMA_DFER_CHECKPOINT_URL" backend/models/mma-dfer/fold1_112.pth
fi

test -s backend/models/emotion-ferplus-8.onnx
if [ ! -f .env ]; then cp .env.example .env; fi
echo "Setup complete. Set MONGO_URI in .env, then run ./start-server.sh"
