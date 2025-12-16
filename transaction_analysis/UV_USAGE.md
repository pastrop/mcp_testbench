# UV Usage Guide

Quick reference for using `uv` with this project.

---

## What Changed

**Before (caused error):**
```bash
uv venv
uv pip install anthropic pandas pydantic python-dotenv
```

**Now (works perfectly):**
```bash
uv sync  # One command does it all!
```

---

## Why uv sync?

`uv sync` reads `pyproject.toml` and:
1. Creates `.venv/` virtual environment
2. Installs all dependencies automatically
3. Locks versions for reproducibility
4. Much faster than pip!

---

## Quick Start

### First Time Setup

```bash
# 1. Install everything
uv sync

# 2. Activate environment
source .venv/bin/activate

# 3. Configure API key
cp .env.example .env
nano .env  # Add your ANTHROPIC_API_KEY

# 4. Run!
python main.py --max-transactions 5
```

### Or Use the Setup Script

```bash
./setup.sh  # Does everything above automatically!
```

---

## Common Commands

### Install/Update Dependencies

```bash
# Install everything from pyproject.toml
uv sync

# Add a new package
uv add package-name

# Update all packages
uv sync --upgrade

# Update specific package
uv sync --upgrade anthropic
```

### Virtual Environment Management

```bash
# Create venv (usually done by uv sync)
uv venv

# Activate venv
source .venv/bin/activate

# Deactivate
deactivate

# Remove venv
rm -rf .venv

# Recreate from scratch
rm -rf .venv && uv sync
```

### Running Commands in venv

```bash
# Option 1: Activate first
source .venv/bin/activate
python main.py

# Option 2: Use uv run (auto-activates)
uv run python main.py

# Option 3: Use our run script
./run.sh --max-transactions 5
```

---

## Troubleshooting

### Error: "Failed to build transaction-fee-verifier"

**Fixed!** The `pyproject.toml` has been updated to remove the build configuration.

**Solution:**
```bash
# Just run
uv sync
```

### Error: "command not found: uv"

**Install uv:**
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Or on macOS:
```bash
brew install uv
```

### Virtual Environment Not Activating

```bash
# Make sure you're in the project directory
cd /path/to/transaction_analysis

# Then activate
source .venv/bin/activate

# Check it's active (should show .venv in prompt)
which python  # Should show: /path/to/.venv/bin/python
```

### Dependencies Not Installing

```bash
# Clear cache and retry
rm -rf .venv
uv sync --reinstall
```

---

## Project Structure

```
transaction_analysis/
├── .venv/              # Virtual environment (created by uv sync)
├── pyproject.toml      # Dependencies definition (read by uv sync)
├── uv.lock            # Locked versions (created by uv sync)
└── ...
```

---

## Daily Workflow

### Starting a Session

```bash
cd transaction_analysis
source .venv/bin/activate
python main.py --max-transactions 5
```

### Or Just Use the Script

```bash
cd transaction_analysis
./run.sh --max-transactions 5  # Auto-activates venv!
```

### Ending a Session

```bash
deactivate  # Leave virtual environment
```

---

## Comparison: uv vs pip

| Task | pip | uv | Speed |
|------|-----|----|----|
| Install deps | `pip install -r requirements.txt` | `uv sync` | **10-100x faster** |
| Add package | `pip install pkg` | `uv add pkg` | **10x faster** |
| Virtual env | `python -m venv venv` | `uv venv` | **5x faster** |
| Update all | `pip install -U -r requirements.txt` | `uv sync --upgrade` | **20x faster** |

---

## Configuration (pyproject.toml)

Your dependencies are defined in `pyproject.toml`:

```toml
[project]
name = "transaction-fee-verifier"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "anthropic>=0.39.0",
    "pandas>=2.0.0",
    "pydantic>=2.0.0",
    "python-dotenv>=1.0.0",
]
```

To add a new dependency:

**Option 1: Edit pyproject.toml**
```toml
dependencies = [
    "anthropic>=0.39.0",
    "pandas>=2.0.0",
    "pydantic>=2.0.0",
    "python-dotenv>=1.0.0",
    "new-package>=1.0.0",  # Add here
]
```

Then run:
```bash
uv sync
```

**Option 2: Use uv add (easier)**
```bash
uv add new-package
# Automatically updates pyproject.toml and installs
```

---

## Quick Reference Card

```bash
# Setup (first time)
uv sync                          # Create venv + install deps
source .venv/bin/activate        # Activate
cp .env.example .env            # Configure
python main.py --max-transactions 5  # Run

# Daily use
source .venv/bin/activate        # Activate
python main.py                   # Run
deactivate                       # Done

# Or just use
./run.sh --max-transactions 5    # One command!

# Maintenance
uv sync --upgrade                # Update all
uv add package-name             # Add package
rm -rf .venv && uv sync         # Fresh start
```

---

## Getting Help

- **uv docs**: https://github.com/astral-sh/uv
- **This project**: See `QUICKSTART.md`
- **Issues**: Check `ERROR_HANDLING.md`

---

## Summary

✅ **Use `uv sync`** - One command setup
✅ **Fast** - 10-100x faster than pip
✅ **Simple** - Reads `pyproject.toml` automatically
✅ **Reliable** - Locks versions for reproducibility

You're all set! 🚀
