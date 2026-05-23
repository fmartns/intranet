#!/bin/bash
set -euo pipefail

cd /workspace/django

exec "$@"
