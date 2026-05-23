#!/bin/bash
set -euo pipefail

cd /workspace

venv_python="/workspace/.venv/bin/python"

if [ ! -x "$venv_python" ] || ! "$venv_python" -c "import django" >/dev/null 2>&1; then
  rm -rf .venv
  poetry install --no-interaction --no-ansi
fi

export PATH="/workspace/.venv/bin:${PATH}"
export VIRTUAL_ENV="/workspace/.venv"

cd /workspace/django

exec "$@"
