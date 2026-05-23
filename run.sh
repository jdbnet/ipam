#!/bin/bash
set -e
if [ ! -f static/dist/index.html ]; then
  echo "Building frontend..."
  (cd frontend && npm ci && npm run build)
fi
echo "Starting app..."
python app.py
