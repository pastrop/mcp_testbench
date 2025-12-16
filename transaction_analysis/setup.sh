#!/bin/bash
# Setup script for Transaction Fee Verification Agent

set -e  # Exit on error

echo "=================================="
echo "Transaction Fee Verification Agent"
echo "Setup Script"
echo "=================================="
echo

# Check if uv is installed
if ! command -v uv &> /dev/null; then
    echo "❌ uv is not installed"
    echo
    echo "Install uv with:"
    echo "  curl -LsSf https://astral.sh/uv/install.sh | sh"
    echo
    echo "Or visit: https://github.com/astral-sh/uv"
    exit 1
fi

echo "✓ uv is installed"
echo

# Create virtual environment and install dependencies
echo "Setting up virtual environment and installing dependencies..."
uv sync
echo "✓ Virtual environment created at .venv"
echo "✓ Dependencies installed"
echo

# Create .env file if it doesn't exist
if [ ! -f .env ]; then
    echo "Creating .env file from template..."
    cp .env.example .env
    echo "✓ .env file created"
    echo
    echo "⚠️  Please edit .env and add your ANTHROPIC_API_KEY"
else
    echo "✓ .env file already exists"
fi
echo

# Check for data files
echo "Checking data files..."
if [ -f "data/parsed_contract.json" ]; then
    echo "✓ data/parsed_contract.json found"
else
    echo "❌ data/parsed_contract.json not found"
fi

if [ -f "data/transaction_table.csv" ]; then
    echo "✓ data/transaction_table.csv found"
else
    echo "❌ data/transaction_table.csv not found"
fi
echo

# Run tests
echo "Running setup tests..."
source .venv/bin/activate
python test_setup.py
echo

echo "=================================="
echo "Setup complete!"
echo "=================================="
echo
echo "Next steps:"
echo "1. Activate virtual environment:"
echo "   source .venv/bin/activate"
echo
echo "2. Set your API key in .env:"
echo "   ANTHROPIC_API_KEY=sk-ant-your-key-here"
echo
echo "3. Run the agent:"
echo "   python main.py --max-transactions 5"
echo
