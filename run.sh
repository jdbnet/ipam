#!/bin/bash
set -e
echo "Building frontend..."
(cd frontend && npm ci && npm run build)
echo "Starting app..."
python app.py
