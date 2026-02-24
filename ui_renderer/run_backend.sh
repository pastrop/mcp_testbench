#!/bin/bash

# Run the UI Renderer Backend

set -e

# Check if port 8000 is in use and kill the process
if lsof -ti:8000 > /dev/null 2>&1; then
    echo "Stopping existing backend on port 8000..."
    lsof -ti:8000 | xargs kill -9 2>/dev/null || true
    sleep 1
fi

cd backend

# Unset ANTHROPIC_API_KEY to use .env file instead
unset ANTHROPIC_API_KEY

# Check if .env exists
if [ ! -f .env ]; then
    echo "Error: .env file not found in backend/"
    echo "Please copy .env.example to .env and add your ANTHROPIC_API_KEY"
    exit 1
fi

# Check if virtual environment exists
if [ ! -d .venv ]; then
    echo "Creating virtual environment..."
    uv venv
fi

# Activate virtual environment
source .venv/bin/activate

# Check if dependencies are installed
if ! python -c "import fastapi" 2>/dev/null; then
    echo "Installing dependencies..."
    uv pip install -e .
fi

echo "Starting UI Renderer Backend..."
echo "API will be available at http://localhost:8000"
echo "Docs available at http://localhost:8000/docs"
echo ""

python -m app.main
