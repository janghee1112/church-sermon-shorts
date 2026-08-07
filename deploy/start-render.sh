#!/usr/bin/env bash
set -euo pipefail

PUBLIC_PORT="${PORT:-10000}"
NEXT_PORT="${NEXT_INTERNAL_PORT:-3000}"

terminate() {
  kill "${API_PID:-}" "${WEB_PID:-}" 2>/dev/null || true
  wait "${API_PID:-}" "${WEB_PID:-}" 2>/dev/null || true
}
trap terminate EXIT INT TERM

cd /app/frontend
npm start -- --hostname 127.0.0.1 --port "${NEXT_PORT}" &
WEB_PID=$!

cd /app/backend
uvicorn app.main:app --host 0.0.0.0 --port "${PUBLIC_PORT}" &
API_PID=$!

wait -n "${API_PID}" "${WEB_PID}"
exit 1
