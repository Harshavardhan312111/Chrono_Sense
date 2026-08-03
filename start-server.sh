#!/bin/bash

# ChronoSenseWeb Startup Script
# This script sets up the environment and starts the server

PROJECT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$PROJECT_DIR"

if [ -f ".env" ]; then
    set -a
    # shellcheck disable=SC1091
    source .env
    set +a
fi

echo "======================================"
echo "ChronoSenseWeb Server Startup"
echo "======================================"
echo ""

# Kill any existing Python processes on port 8000
echo "🔍 Checking for existing server processes..."
pkill -f "python.*server.py" || true
sleep 1

# Clean Python cache
echo "🧹 Cleaning Python cache..."
find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
find . -type f -name "*.pyc" -delete 2>/dev/null || true

# Create or activate virtual environment
if [ ! -d ".venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv .venv
fi

echo "✅ Activating virtual environment..."
source .venv/bin/activate

# Install/update dependencies
echo "📥 Installing dependencies..."
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt

if [ ! -s "backend/models/emotion-ferplus-8.onnx" ]; then
    echo "FERPlus model is missing. Run ./scripts/setup/install.sh first." >&2
    exit 1
fi

if [ -z "${MONGO_URI}" ]; then
    echo "⚠️  MONGO_URI is not set. Create .env or export MongoDB settings before startup."
fi

# Start server
echo ""
echo "🚀 Starting ChronoSenseWeb server..."
echo "📍 Server will be available at: http://localhost:8000"
echo "📍 Default credentials: admin / admin123"
echo ""
echo "Press Ctrl+C to stop the server"
echo "======================================"
echo ""

export PYTHONDONTWRITEBYTECODE=1
./.venv/bin/python backend/server.py
