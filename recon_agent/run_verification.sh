#!/bin/bash

# Auto-generate output filename from contract/Excel files in data/

# Get contract filename (remove path and extension)
CONTRACT=$(ls data/*.json 2>/dev/null | head -1)
if [ -z "$CONTRACT" ]; then
    echo "Error: No contract JSON found in data/"
    exit 1
fi

# Extract business name from contract filename
# Example: "Agreement_FINTHESIS_ARTEFACTAX LIMITED.docx.pdf.json" -> "artefactax"
BUSINESS_NAME=$(basename "$CONTRACT" .json | sed 's/.*_\([A-Z]*\).*/\1/' | tr '[:upper:]' '[:lower:]')

# If extraction failed, use a timestamp
if [ -z "$BUSINESS_NAME" ] || [ "$BUSINESS_NAME" = "agreement" ]; then
    BUSINESS_NAME="verification_$(date +%Y%m%d_%H%M%S)"
fi

# Run verification with auto-generated output name
OUTPUT_NAME="output/${BUSINESS_NAME}_verification"

echo "Running verification for: $BUSINESS_NAME"
echo "Output will be: ${OUTPUT_NAME}.txt and ${OUTPUT_NAME}.json"
echo ""

uv run python main.py --all-sheets --output "$OUTPUT_NAME"
