#!/bin/bash

# Start LiveKit Voice Agent
# This runs the AI agent that handles voice interactions

echo "=========================================="
echo "Starting Voice Agent"
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
    echo "Error: .env file not found"
    echo "Please copy .env.example to .env and fill in your API keys"
    exit 1
fi

# Check if FAISS index exists
if [ ! -d "data/faiss_index" ]; then
    echo "Error: FAISS index not found"
    echo "Please build the vector database first:"
    echo "  python backend/build_vector_db.py"
    exit 1
fi

# Start the agent
echo "Starting LiveKit voice agent..."
echo ""

cd backend && python voice_agent.py start
