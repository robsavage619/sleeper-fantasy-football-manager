#!/bin/bash
# Start backend + frontend dev servers.
# Backend: FastAPI on :8000 (auto-reload)
# Frontend: Vite on :5173 (proxies /api → :8000)

pkill -f "sffm serve" 2>/dev/null
pkill -f "vite.*5173" 2>/dev/null
sleep 1

uv run sffm serve --reload &
cd frontend && npm run dev -- --port 5173 &

echo "Backend: http://127.0.0.1:8000/docs"
echo "Frontend: http://localhost:5173"
wait
