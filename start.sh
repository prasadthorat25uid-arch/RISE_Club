#!/usr/bin/env bash
set -e
python3 -m pip install -r requirements.txt
uvicorn backend:app --host 0.0.0.0 --port "${PORT:-8000}"
