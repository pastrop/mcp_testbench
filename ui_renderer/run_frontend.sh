#!/bin/bash

# Run the UI Renderer Frontend

set -e

cd frontend

# Check if node_modules exists
if [ ! -d node_modules ]; then
    echo "Installing dependencies..."
    npm install
fi

echo "Starting UI Renderer Frontend..."
echo "App will be available at http://localhost:5173"
echo ""

npm run dev
