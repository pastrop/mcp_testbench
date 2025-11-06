#!/bin/bash
# Quick start script for the Pandas Query Agent

echo "==========================================="
echo "Pandas Query Agent - Quick Start"
echo "==========================================="
echo ""

# Check if API key is set
if [ -z "$ANTHROPIC_API_KEY" ]; then
    echo "Error: ANTHROPIC_API_KEY environment variable not set"
    echo ""
    echo "Please set it first:"
    echo "  export ANTHROPIC_API_KEY='your-api-key-here'"
    exit 1
fi

# Check if sample data exists
if [ ! -f "sample_transactions.csv" ]; then
    echo "Sample data not found. Generating..."
    python create_sample_data.py 500 sample_transactions.csv
    echo ""
fi

# Parse arguments
MODEL=${1:-sonnet}
DATA_FILE=${2:-sample_transactions.csv}

echo "Configuration:"
echo "  Model: $MODEL"
echo "  Data file: $DATA_FILE"
echo ""
echo "Starting agent..."
echo "==========================================="
echo ""

# Run the agent
python mcp_client_agent.py mcp_server_pandas.py "$DATA_FILE" "$MODEL"
