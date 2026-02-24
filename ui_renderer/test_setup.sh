#!/bin/bash

# Test the UI Renderer setup

set -e

echo "======================================"
echo "Testing UI Renderer Setup"
echo "======================================"
echo ""

# Test backend
echo "1. Testing Backend..."
cd backend

if [ ! -f .env ]; then
    echo "   ⚠ .env file not found - copying from example"
    cp .env.example .env
fi

if [ ! -d .venv ]; then
    echo "   ⚠ Virtual environment not found - creating..."
    uv venv
    source .venv/bin/activate
    uv pip install -e .
else
    source .venv/bin/activate
fi

# Test imports
echo "   Testing Python imports..."
python -c "
from app.core.config import settings
from app.services.contract_service import ContractService
from app.api.routes import router
print('   ✓ All imports successful')
"

# Test contract service
echo "   Testing contract service..."
python -c "
from app.services.contract_service import ContractService
cs = ContractService()
contracts = cs.list_contracts()
print(f'   ✓ Found {contracts.count} contracts')
if contracts.count > 0:
    sample = cs.load_contract(contracts.contracts[0])
    print(f'   ✓ Successfully loaded sample contract: {sample.filename}')
"

cd ..

echo ""
echo "2. Testing Frontend..."
cd frontend

if [ ! -d node_modules ]; then
    echo "   ⚠ node_modules not found - would run npm install"
    echo "   (Skipping to avoid long install time)"
else
    echo "   ✓ node_modules found"
fi

# Check key files exist
echo "   Checking project structure..."
[ -f "package.json" ] && echo "   ✓ package.json exists"
[ -f "vite.config.js" ] && echo "   ✓ vite.config.js exists"
[ -f "src/App.jsx" ] && echo "   ✓ App.jsx exists"
[ -f "src/lib/Renderer.jsx" ] && echo "   ✓ Renderer.jsx exists"
[ -f "src/lib/api.js" ] && echo "   ✓ API client exists"
[ -d "src/components" ] && echo "   ✓ Components directory exists"

cd ..

echo ""
echo "3. Checking Data..."
contract_count=$(ls data/Parsed_Contracts/*.json 2>/dev/null | wc -l | tr -d ' ')
if [ "$contract_count" -gt 0 ]; then
    echo "   ✓ Found $contract_count contract JSON files"
else
    echo "   ✗ No contract files found in data/Parsed_Contracts/"
fi

echo ""
echo "======================================"
echo "Setup Test Complete!"
echo "======================================"
echo ""
echo "Next steps:"
echo "1. Add your Anthropic API key to backend/.env"
echo "2. Run backend: ./run_backend.sh"
echo "3. Run frontend: ./run_frontend.sh (in new terminal)"
echo "4. Open http://localhost:5173"
echo ""
