# Error Handling Guide

The agent provides clear, actionable error messages for all common issues, especially API key problems.

---

## API Key Errors

### 1. Invalid or Missing API Key

**What you'll see:**

```
============================================================
❌ INVALID API KEY
============================================================
Your Anthropic API key is invalid or missing.

Please check:
1. Create .env file: cp .env.example .env
2. Add your key: ANTHROPIC_API_KEY=sk-ant-your-key-here
3. Get a key at: https://console.anthropic.com/

Current .env status:
  ✓ .env file exists
  ❌ ANTHROPIC_API_KEY is not set in .env
============================================================
```

**What to do:**
1. Create `.env` file if it doesn't exist
2. Add your API key: `ANTHROPIC_API_KEY=sk-ant-your-key-here`
3. Make sure the key starts with `sk-ant-`

**Example fix:**
```bash
# Create .env file
cp .env.example .env

# Edit it
nano .env

# Add this line:
ANTHROPIC_API_KEY=sk-ant-api03-your-actual-key-here
```

---

### 2. Insufficient Permissions / Credits

**What you'll see:**

```
============================================================
❌ INSUFFICIENT PERMISSIONS
============================================================
Your API key doesn't have the required permissions.

Please check:
1. Your account has sufficient credits
2. Your API key has access to Claude Sonnet 4.5
3. Visit: https://console.anthropic.com/settings/plans
============================================================
```

**What to do:**
1. Check your account credits at https://console.anthropic.com/
2. Verify your plan includes Claude Sonnet 4.5
3. Add credits if needed

---

### 3. Rate Limit Exceeded

**What you'll see:**

```
============================================================
⚠️  RATE LIMIT EXCEEDED
============================================================
You've hit the API rate limit.

Options:
1. Wait a few minutes and try again
2. Reduce --batch-size to process slower
3. Upgrade your API plan at: https://console.anthropic.com/
============================================================
```

**What to do:**

**Option 1: Wait and retry**
```bash
# Wait 5 minutes, then try again
python main.py --max-transactions 5
```

**Option 2: Reduce batch size**
```bash
# Process transactions slower
python main.py --batch-size 5
```

**Option 3: Upgrade your plan**
- Visit https://console.anthropic.com/settings/plans

---

### 4. Network / Connection Error

**What you'll see:**

```
============================================================
❌ CONNECTION ERROR
============================================================
Cannot connect to Anthropic API.

Please check:
1. Your internet connection
2. Firewall/proxy settings
3. Try again in a few moments
============================================================
```

**What to do:**
1. Check your internet connection
2. Check if you're behind a proxy/firewall
3. Verify Anthropic API status: https://status.anthropic.com/
4. Try again in a few minutes

---

### 5. Anthropic Server Error

**What you'll see:**

```
============================================================
❌ ANTHROPIC API ERROR
============================================================
There's an issue with Anthropic's servers.

What to do:
1. Wait a few minutes and try again
2. Check status at: https://status.anthropic.com/
============================================================
```

**What to do:**
1. This is on Anthropic's side, not your code
2. Wait 5-10 minutes
3. Check https://status.anthropic.com/
4. Try again

---

## Data File Errors

### Contract File Not Found

**What you'll see:**
```
ERROR - Contract file not found: data/parsed_contract.json
```

**What to do:**
```bash
# Check if file exists
ls -la data/parsed_contract.json

# If not, create symlink or copy
ln -s ../parsed_contract.json data/parsed_contract.json
```

### Transaction File Not Found

**What you'll see:**
```
ERROR - Transaction file not found: data/transaction_table.csv
```

**What to do:**
```bash
# Check if file exists
ls -la data/transaction_table.csv

# If not, create symlink or copy
ln -s ../transaction_table.csv data/transaction_table.csv
```

---

## When Errors Occur

### During Initialization (Before Processing)

The agent **validates your API key immediately** when you run it:

```bash
$ python main.py --max-transactions 5

2024-12-15 10:00:00 - agent.core - INFO - Initializing...
2024-12-15 10:00:00 - agent.core - INFO - Validating API key...

# If there's a problem, you'll see a clear error right here
# BEFORE any transactions are processed
```

This means you'll know about API key issues **within seconds**, not after processing hundreds of transactions.

### During Transaction Processing

If an error occurs while processing (rare), you'll see:
- Clear error message
- Which transaction failed
- What went wrong
- How to fix it

The agent will:
1. Log the error
2. Display user-friendly message
3. Exit gracefully (not crash)

---

## Testing Error Messages

Want to see what error messages look like?

### Test Invalid API Key

```bash
# Set an invalid key temporarily
export ANTHROPIC_API_KEY="invalid-key"
python main.py --max-transactions 1

# You should see:
# ❌ INVALID API KEY
# (with clear instructions)
```

### Test Missing API Key

```bash
# Unset the key
unset ANTHROPIC_API_KEY
python main.py --max-transactions 1

# You should see:
# ❌ INVALID API KEY
# Current .env status: ❌ ANTHROPIC_API_KEY is not set in .env
```

---

## Error Prevention

### Pre-Flight Checks

The agent performs these checks **before** processing:

1. ✓ API key exists
2. ✓ API key is valid (test call)
3. ✓ Contract file exists
4. ✓ Transaction file exists
5. ✓ All dependencies installed

This means most errors are caught **before** you waste time processing.

### Use test_setup.py

Run this to verify everything works:

```bash
python test_setup.py
```

It checks:
- All dependencies installed
- Agent modules load correctly
- Data files present
- Tools execute properly

---

## Common Scenarios

### Scenario 1: First Time Setup

```bash
$ python main.py --max-transactions 5

ERROR - No API key provided. Set ANTHROPIC_API_KEY...

# Solution: Create .env and add key
$ cp .env.example .env
$ nano .env  # Add key
$ python main.py --max-transactions 5  # Works!
```

### Scenario 2: Invalid Key

```bash
$ python main.py

============================================================
❌ INVALID API KEY
============================================================
Your Anthropic API key is invalid or missing.
...
Current .env status:
  ✓ .env file exists
  ✓ ANTHROPIC_API_KEY is set (starts with: sk-ant-XXX...)
============================================================

# The key format is correct but invalid
# Solution: Check you copied the full key correctly
```

### Scenario 3: Ran Out of Credits

```bash
$ python main.py

============================================================
❌ INSUFFICIENT PERMISSIONS
============================================================
Your API key doesn't have the required permissions.

Please check:
1. Your account has sufficient credits  ← THIS
...
============================================================

# Solution: Add credits at console.anthropic.com
```

### Scenario 4: Everything Works!

```bash
$ python main.py --max-transactions 5

2024-12-15 10:00:00 - agent.core - INFO - Initializing...
2024-12-15 10:00:00 - agent.core - INFO - Validating API key...
2024-12-15 10:00:00 - agent.core - INFO - ✓ API key validated successfully
2024-12-15 10:00:00 - agent.core - INFO - Contract loaded: 6 currencies
2024-12-15 10:00:00 - agent.core - INFO - Starting verification...
2024-12-15 10:00:00 - agent.core - INFO - Processing batch 1...

# Everything working smoothly!
```

---

## Summary

### ✅ Clear Error Messages

Every error shows:
- **What happened** (in plain English)
- **Why it happened** (diagnosis)
- **How to fix it** (action steps)
- **Helpful links** (where to get help)

### ✅ Early Detection

API key issues are caught **before** processing:
- Saves time
- Saves API credits
- Clear feedback

### ✅ Graceful Failures

The agent:
- Never crashes silently
- Always explains what's wrong
- Exits cleanly with proper error codes
- Logs everything for debugging

### ✅ Helpful Context

Error messages include:
- Current configuration status
- Diagnostic information
- Links to documentation
- Suggestions for fixes

You'll **never be left wondering** why something failed!
