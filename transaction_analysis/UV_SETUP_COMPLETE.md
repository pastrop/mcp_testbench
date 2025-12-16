# UV Setup Complete! 🎉

Your Transaction Fee Verification Agent is now set up with **uv** - the fast Python package manager!

## What Was Configured

✅ **pyproject.toml** - Project configuration for uv
✅ **Virtual environment** - Created with `uv venv` at `.venv/`
✅ **Dependencies installed** - All packages installed via `uv pip install`
✅ **Data directory** - Set up with your contract and transaction files
✅ **Setup script** - Automated setup with `./setup.sh`
✅ **Run script** - Convenient runner with `./run.sh`
✅ **Tests passed** - All modules working correctly

## Quick Commands

### One-Time Setup (Already Done!)

```bash
# This has been completed for you
uv sync                    # ✓ Virtual environment created + dependencies installed
```

### Daily Usage

```bash
# Activate virtual environment
source .venv/bin/activate

# Run the agent (test with 5 transactions)
python main.py --max-transactions 5
```

### Or Use the Convenience Script

```bash
# No need to activate manually
./run.sh --max-transactions 5
```

## Next Steps

### 1. Configure Your API Key

```bash
# Create .env file
cp .env.example .env

# Edit .env and add your Anthropic API key
nano .env  # or vim, or your favorite editor

# Add this line:
# ANTHROPIC_API_KEY=sk-ant-your-key-here
```

### 2. Run Your First Test

```bash
# Activate environment
source .venv/bin/activate

# Test with 5 transactions
python main.py --max-transactions 5
```

### 3. View Results

```bash
cat output/discrepancy_report.json
```

## Command Reference

### Using uv

```bash
# Create new virtual environment (if needed)
uv venv

# Install new package
uv pip install package-name

# Update all packages
uv pip install --upgrade anthropic pandas pydantic python-dotenv

# Show installed packages
uv pip list
```

### Running the Agent

```bash
# Basic run (all transactions)
python main.py

# Test with limited transactions
python main.py --max-transactions 10

# Larger batches (faster)
python main.py --batch-size 50

# Verbose logging
python main.py --verbose

# Custom files
python main.py \
  --contract path/to/contract.json \
  --transactions path/to/transactions.csv \
  --output path/to/output.json
```

### Using the Run Script

```bash
# The run.sh script automatically activates the venv
./run.sh --max-transactions 5
./run.sh --verbose
./run.sh --batch-size 20
```

## Project Structure

```
transaction_analysis/
├── .venv/                  # Virtual environment (created by uv)
├── agent/                  # Agent code
│   ├── core.py            # Main agent
│   └── tools/             # Tool implementations
├── data/                   # Input data
│   ├── parsed_contract.json
│   └── transaction_table.csv
├── output/                 # Results (created on first run)
│   └── discrepancy_report.json
├── pyproject.toml          # UV project config
├── setup.sh               # Automated setup script
├── run.sh                 # Convenient run script
├── main.py                # CLI entry point
└── test_setup.py          # Test installation
```

## Why uv?

**uv** is blazingly fast compared to pip:
- ⚡ **10-100x faster** than pip
- 🦀 Written in Rust for maximum performance
- 🎯 Better dependency resolution
- 📦 Drop-in replacement for pip

### Performance Comparison

```
Traditional pip:    ~30 seconds to install
uv:                 ~2 seconds to install  ⚡

That's 15x faster!
```

## Troubleshooting

### "Virtual environment not found"

```bash
# Recreate virtual environment
uv venv
source .venv/bin/activate
```

### "Module not found"

```bash
# Reinstall dependencies
source .venv/bin/activate
uv pip install anthropic pandas pydantic python-dotenv
```

### "No API key provided"

```bash
# Make sure .env file exists and has your key
cat .env
# Should contain: ANTHROPIC_API_KEY=sk-ant-...
```

### "Data files not found"

```bash
# Check data directory
ls -la data/

# Should show:
# data/parsed_contract.json
# data/transaction_table.csv
```

## Updating Dependencies

```bash
# Activate environment
source .venv/bin/activate

# Update a specific package
uv pip install --upgrade anthropic

# Update all packages
uv pip install --upgrade anthropic pandas pydantic python-dotenv
```

## Re-running Setup

If you need to start fresh:

```bash
# Remove virtual environment
rm -rf .venv

# Run setup again
./setup.sh
```

## Performance Tips

1. **Use larger batch sizes** for faster processing:
   ```bash
   python main.py --batch-size 50
   ```

2. **Test with small datasets first**:
   ```bash
   python main.py --max-transactions 10
   ```

3. **Use the run script** to avoid manual activation:
   ```bash
   ./run.sh --max-transactions 5
   ```

## Getting Help

- **Quick Start**: See `QUICKSTART.md`
- **Architecture**: See `ARCHITECTURE.md`
- **Examples**: See `IMPLEMENTATION_GUIDE.md`
- **Project Structure**: See `PROJECT_STRUCTURE.md`

## Ready to Go!

Everything is set up and tested. Just:

1. Add your `ANTHROPIC_API_KEY` to `.env`
2. Run `source .venv/bin/activate`
3. Execute `python main.py --max-transactions 5`

Enjoy your blazingly fast transaction verification agent! 🚀
