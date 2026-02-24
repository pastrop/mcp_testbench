# Quick Start Guide

Get the UI Renderer system running in 5 minutes.

## Prerequisites Check

```bash
# Check Python version (need 3.11+)
python3 --version

# Check Node version (need 18+)
node --version

# Check if uv is installed
uv --version
```

If uv is not installed:
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

## Step 1: Set Up Anthropic API Key

You need an Anthropic API key to use Claude Haiku.

1. Get your API key from: https://console.anthropic.com/
2. Edit `backend/.env`:
```bash
# Open the file
nano backend/.env

# Or use any text editor
# code backend/.env  # VS Code
# vi backend/.env    # Vim
```

3. Add your key:
```
ANTHROPIC_API_KEY=sk-ant-xxxxxxxxxxxxx
```

## Step 2: Start the Backend

```bash
./run_backend.sh
```

You should see:
```
Starting UI Renderer Backend...
API will be available at http://localhost:8000
Docs available at http://localhost:8000/docs

INFO:     Started server process
INFO:     Uvicorn running on http://0.0.0.0:8000
```

**Test the backend:**
Open http://localhost:8000 in your browser - you should see a JSON response.

## Step 3: Start the Frontend (New Terminal)

Open a new terminal window:

```bash
cd ui_renderer  # Navigate to project root
./run_frontend.sh
```

You should see:
```
Starting UI Renderer Frontend...
App will be available at http://localhost:5173

  VITE ready in XXX ms
  ➜  Local:   http://localhost:5173/
```

## Step 4: Use the System

1. Open http://localhost:5173 in your browser
2. You'll see the Contract UI Renderer interface
3. Click the dropdown and select a contract (e.g., `AETHERIC_CORE_LIMITED...`)
4. Watch the magic happen:
   - Backend loads the contract JSON
   - Claude Haiku analyzes the structure
   - AI generates a UI specification
   - Frontend renders the beautiful UI

## Test with a Sample Contract

Try selecting: `AETHERIC_CORE_LIMITED_PAYMENT_MANAGEMENT_SERVICES_AGREEMENT_2_2.pdf.json`

You should see:
- Document information card
- Fee cards for different fee types
- Payment terms details
- Merchant account information
- All beautifully organized!

## Troubleshooting

### Backend Issues

**Port 8000 already in use:**
```bash
# Find and kill the process
lsof -ti:8000 | xargs kill -9
```

**API key not set:**
```
Error: ANTHROPIC_API_KEY not found
```
Solution: Make sure you edited `backend/.env` and added your API key.

**Module not found:**
```bash
cd backend
source .venv/bin/activate
uv pip install -e .
```

### Frontend Issues

**Port 5173 already in use:**
Edit `frontend/vite.config.js` and change the port:
```js
server: {
  port: 5174,  // Use different port
}
```

**Dependencies not installed:**
```bash
cd frontend
npm install
```

**Cannot connect to backend:**
- Make sure backend is running on port 8000
- Check browser console for CORS errors
- Verify `frontend/.env` has correct API URL

### No Contracts Showing

Make sure contracts exist in `data/Parsed_Contracts/`:
```bash
ls data/Parsed_Contracts/*.json | wc -l
# Should show 25 (or the number of contracts you have)
```

## API Testing (Optional)

Test the backend directly:

```bash
# List contracts
curl http://localhost:8000/api/v1/contracts

# Get a specific contract
curl http://localhost:8000/api/v1/contracts/AETHERIC_CORE_LIMITED_PAYMENT_MANAGEMENT_SERVICES_AGREEMENT_2_2.pdf.json

# Generate UI (requires API key)
curl -X POST "http://localhost:8000/api/v1/generate-ui?filename=AETHERIC_CORE_LIMITED_PAYMENT_MANAGEMENT_SERVICES_AGREEMENT_2_2.pdf.json"
```

## Next Steps

- **Add new contracts**: Drop JSON files in `data/Parsed_Contracts/`
- **Customize components**: Edit components in `frontend/src/components/`
- **Extend AI prompt**: Modify `backend/app/services/ai_service.py`
- **Add new component types**: Follow instructions in README.md

## Stopping the Services

**Backend:**
Press `Ctrl+C` in the terminal running the backend

**Frontend:**
Press `Ctrl+C` in the terminal running the frontend

---

Enjoy building dynamic UIs! 🚀
