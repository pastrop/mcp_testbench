#!/bin/bash
# Convenient run script for Transaction Fee Verification Agent

# Activate virtual environment if it exists
if [ -d ".venv" ]; then
    source .venv/bin/activate
else
    echo "❌ Virtual environment not found"
    echo "Run ./setup.sh first"
    exit 1
fi

# Check if .env exists
if [ ! -f ".env" ]; then
    echo "❌ .env file not found"
    echo "Copy .env.example to .env and add your ANTHROPIC_API_KEY"
    exit 1
fi

# Run the agent with all arguments passed through
python main.py "$@"
