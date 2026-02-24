#!/bin/bash
# Test script for Claude Vision integration

echo "=== Claude Vision Test Script ==="
echo ""

# Check if API key is set
if [ -z "$ANTHROPIC_API_KEY" ]; then
    echo "❌ ANTHROPIC_API_KEY is not set"
    echo ""
    echo "To test Claude Vision:"
    echo "  1. Get API key from https://console.anthropic.com/"
    echo "  2. Run: export ANTHROPIC_API_KEY='your-key'"
    echo "  3. Run this script again"
    echo ""
    echo "Testing without Claude Vision (will show image-based detection)..."
    echo ""
else
    echo "✓ ANTHROPIC_API_KEY is set"
    echo ""
fi

# Show parser info
echo "=== Parser Information ==="
uv run pdf-parser info
echo ""

# Inspect image-based PDF
echo "=== Inspecting Image-Based PDF ==="
uv run pdf-parser inspect "data/290125_PIXTHENA._Terms_of_Business_Currency.pdf"
echo ""

# Test parsing
if [ -z "$ANTHROPIC_API_KEY" ]; then
    echo "=== Testing Without API Key (Expected: 0 elements) ==="
    uv run pdf-parser parse "data/290125_PIXTHENA._Terms_of_Business_Currency.pdf" -v 2>&1 | grep -E "(PDF type|vision parser|elements extracted|Saved to)"
    echo ""
    echo "To get actual content extraction, set ANTHROPIC_API_KEY and run again."
else
    echo "=== Testing With Claude Vision ==="
    uv run pdf-parser parse "data/290125_PIXTHENA._Terms_of_Business_Currency.pdf" -v
    echo ""
    echo "✓ Check output/ directory for generated markdown"
fi

echo ""
echo "=== Test Complete ==="
