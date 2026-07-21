#!/bin/bash
# Start backend + frontend dev servers.
# Backend: FastAPI on :8001 (auto-reload) — the port frontend/vite.config.ts proxies to.
# Frontend: Vite on :5173 (proxies /api → :8001)

pkill -f "sffm serve" 2>/dev/null
pkill -f "vite.*5173" 2>/dev/null
sleep 1

# --port explicit (not just the CLI default) so this can't silently drift off the proxy.
uv run sffm serve --reload --port 8001 &
cd frontend && npm run dev -- --port 5173 &

echo "Backend: http://127.0.0.1:8001/docs"
echo "Frontend: http://localhost:5173"
wait
