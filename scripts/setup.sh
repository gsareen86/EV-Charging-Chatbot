#!/bin/bash

# EV Charging Chatbot - Setup Script
# This script sets up the development environment

echo "=========================================="
echo "EV Charging Chatbot - Setup"
echo "=========================================="

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "Error: Python 3 is not installed"
    exit 1
fi

echo "✓ Python 3 found"

# Create virtual environment
echo ""
echo "Creating virtual environment..."
python3 -m venv venv

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Upgrade pip
echo ""
echo "Upgrading pip..."
pip install --upgrade pip

# Install dependencies
echo ""
echo "Installing Python dependencies..."
pip install -r requirements.txt

echo ""
echo "=========================================="
echo "Setup complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo "1. Copy .env.example to .env and fill in your API keys:"
echo "   cp .env.example .env"
echo ""
echo "2. Build the FAISS vector database:"
echo "   python backend/build_vector_db.py"
echo ""
echo "3. Start LiveKit server (in a separate terminal):"
echo "   ./scripts/start_livekit.sh"
echo ""
echo "4. Start the Flask server (in a separate terminal):"
echo "   ./scripts/start_server.sh"
echo ""
echo "5. Start the voice agent (in a separate terminal):"
echo "   ./scripts/start_agent.sh"
echo ""
echo "6. Open http://localhost:5000 in your browser"
echo ""
echo "=========================================="
