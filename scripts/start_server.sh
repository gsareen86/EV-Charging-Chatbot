#!/bin/bash

# Start FastAPI server
# This serves the frontend and provides token generation API

echo "=========================================="
echo "Starting FastAPI Server"
echo "=========================================="

# Activate virtual environment
if [ -d "venv" ]; then
    source venv/bin/activate
else
    echo "Error: Virtual environment not found"
    echo "Please run ./scripts/setup.sh first"
    exit 1
fi

# Check if .env exists
if [ ! -f ".env" ]; then
    echo "Warning: .env file not found"
    echo "Using default development settings"
    echo ""
fi

# Start the server
echo "Starting FastAPI server on http://localhost:5000"
echo "API docs available at http://localhost:5000/docs"
echo ""

cd backend && python server.py
