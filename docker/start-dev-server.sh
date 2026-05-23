#!/usr/bin/env bash
set -euo pipefail

LOG_FILE="/tmp/django-runserver.log"
PID_FILE="/tmp/django-runserver.pid"

if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
    echo "Django already running (pid $(cat "$PID_FILE")). Logs: $LOG_FILE"
    exit 0
fi

if command -v ss >/dev/null 2>&1 && ss -tlnp 2>/dev/null | grep -q ':8000 '; then
    echo "Port 8000 already in use. Logs: $LOG_FILE"
    exit 0
fi

cd /workspace/django
export DJANGO_SETTINGS_MODULE="${DJANGO_SETTINGS_MODULE:-core.settings.development}"
export PYTHONPATH="/workspace/django"
export PATH="/workspace/.venv/bin:${PATH}"

nohup python manage.py runserver 0.0.0.0:8000 >>"$LOG_FILE" 2>&1 &
echo $! >"$PID_FILE"

sleep 1
if ! kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
    echo "Django failed to start. Last log lines:"
    tail -20 "$LOG_FILE" 2>/dev/null || true
    exit 1
fi

echo "Django started on http://0.0.0.0:8000 (pid $(cat "$PID_FILE"))"
echo "Logs: tail -f $LOG_FILE"
