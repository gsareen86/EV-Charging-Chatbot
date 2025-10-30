#!/bin/bash

# Build FAISS Vector Database
# This creates the vector embeddings from FAQ data

echo "=========================================="
echo "Building FAISS Vector Database"
echo "=========================================="

# Activate virtual environment
if [ -d "venv" ]; then
    source venv/bin/activate
else
    echo "Error: Virtual environment not found"
    echo "Please run ./scripts/setup.sh first"
    exit 1
fi

# Check if .env exists and has OpenAI key
if [ ! -f ".env" ]; then
    echo "Error: .env file not found"
    echo "Please copy .env.example to .env and add your OpenAI API key"
    exit 1
fi

# Build the database
echo "Building vector database from FAQ data..."
echo ""

python backend/build_vector_db.py

echo ""
echo "=========================================="
echo "Vector database built successfully!"
echo "=========================================="
