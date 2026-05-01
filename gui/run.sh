#!/usr/bin/env bash
# run.sh — One-command dev launcher for Chickpea SRG RAG GUI
# Starts the FastAPI backend and Vite frontend concurrently.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$SCRIPT_DIR/backend"
FRONTEND_DIR="$SCRIPT_DIR/frontend"

echo ""
echo "🌱  Chickpea SRG RAG GUI — Dev Launcher"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Backend  → http://localhost:7860"
echo "  Frontend → http://localhost:5173"
echo ""

# ── Backend ──────────────────────────────────────────────────────────────────
cd "$BACKEND_DIR"

# Install backend deps if needed
if ! python3 -c "import fastapi, sse_starlette" 2>/dev/null; then
  echo "📦 Installing backend dependencies…"
  pip3 install -q -r requirements.txt
fi

echo "🚀 Starting FastAPI backend on :7860"
uvicorn app:app --reload --host 0.0.0.0 --port 7860 &
BACKEND_PID=$!

# Wait for backend to be ready (max 20s) before starting frontend
echo "⏳ Waiting for backend to become ready…"
MAX_WAIT=20
WAITED=0
until curl -sf http://localhost:7860/api/health > /dev/null 2>&1; do
  if [ $WAITED -ge $MAX_WAIT ]; then
    echo "❌ Backend did not start within ${MAX_WAIT}s. Check for errors above."
    kill $BACKEND_PID 2>/dev/null
    exit 1
  fi
  sleep 1
  WAITED=$((WAITED + 1))
done
echo "✓ Backend ready (${WAITED}s)"

# ── Frontend ─────────────────────────────────────────────────────────────────
cd "$FRONTEND_DIR"

if [ ! -d "node_modules" ]; then
  echo "📦 Installing frontend dependencies…"
  npm install --silent
fi

echo "⚡ Starting Vite frontend on :5173"
npm run dev &
FRONTEND_PID=$!

# ── Cleanup on exit ───────────────────────────────────────────────────────────
trap "echo ''; echo 'Shutting down…'; kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit 0" SIGINT SIGTERM

echo ""
echo "✓ Both servers running. Open http://localhost:5173 in your browser."
echo "  Press Ctrl+C to stop."
echo ""

wait $BACKEND_PID $FRONTEND_PID
