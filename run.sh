#!/bin/bash
set -e

echo "Building frontend UI..."
cd frontend
npm install
npm run build
cd ..

echo "Setting up Python virtual environment..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi

source venv/bin/activate
pip install -r requirements.txt

echo "Starting server..."
python app.py serve
