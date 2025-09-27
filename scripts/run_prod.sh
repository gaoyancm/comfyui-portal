#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"/..

python -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

export FLASK_ENV=production
export COMFY_URL=${COMFY_URL:-http://127.0.0.1:8188}
export UPLOAD_DIR=${UPLOAD_DIR:-uploads}
export RESULTS_DIR=${RESULTS_DIR:-results}

exec gunicorn -b 0.0.0.0:5000 app:app --chdir . --workers 2 --timeout 120

