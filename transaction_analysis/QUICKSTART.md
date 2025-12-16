# Quick Start Guide

Get started with the Transaction Fee Verification Agent in 5 minutes.

## 1. Install Dependencies

### Using uv (Recommended - Fast!)

```bash
# One command to create venv and install everything!
uv sync

# Activate virtual environment
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# That's it! All dependencies installed from pyproject.toml
```

**Alternative uv method:**
```bash
# Manual approach
uv venv
source .venv/bin/activate
uv pip install anthropic pandas pydantic python-dotenv
```

### Alternative: Using pip

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install requirements
pip install -r requirements.txt
```

## 2. Configure API Key

```bash
# Copy example environment file
cp .env.example .env

# Edit .env and add your Anthropic API key
# ANTHROPIC_API_KEY=sk-ant-...
```

Or pass it directly:
```bash
export ANTHROPIC_API_KEY="sk-ant-..."
```

## 3. Verify Data Files

Make sure you have:
- `data/parsed_contract.json` - Contract fee structures
- `data/transaction_table.csv` - Transaction records

These files are already in your directory!

## 4. Run Verification

### Basic Usage

```bash
python main.py
```

This will:
- Process transactions from `data/transaction_table.csv`
- Verify against `data/parsed_contract.json`
- Output results to:
  - `output/discrepancy_report.json` (structured data)
  - `output/discrepancy_report.txt` (human-readable report)

### Process Limited Transactions (for testing)

```bash
python main.py --max-transactions 10
```

### Custom Files

```bash
python main.py \
  --contract path/to/contract.json \
  --transactions path/to/transactions.csv \
  --output path/to/output.json
```

### Larger Batches (faster but more API calls)

```bash
python main.py --batch-size 50
```

### Verbose Logging

```bash
python main.py --verbose
```

## 5. View Results

Results are saved in two formats:

**JSON format** (for processing):
```bash
cat output/discrepancy_report.json
```

**Text format** (for reading):
```bash
cat output/discrepancy_report.txt
```

Example JSON output:
```json
{
  "summary": {
    "total_discrepancies": 5,
    "total_discrepancy_amount": -2.53
  },
  "discrepancies": [
    {
      "transaction_id": "dd523aac-9bdf-429e-829e-7961316306bc",
      "actual_commission": 5.0,
      "expected_commission": 5.1028,
      "discrepancy": -0.1028,
      "status": "UNDERCHARGED",
      "confidence": 0.85,
      "reasoning": "Expected fee calculation: (510.28 × 0.01) + 0 = 5.1028 EUR..."
    }
  ]
}
```

## Command Line Options

```
--contract PATH          Path to contract JSON (default: data/parsed_contract.json)
--transactions PATH      Path to transaction CSV (default: data/transaction_table.csv)
--output PATH           Output path (generates .json and .txt) (default: output/discrepancy_report.json)
--batch-size N          Transactions per batch (default: 10)
--max-transactions N    Limit total transactions (default: all)
--api-key KEY           Anthropic API key (default: from env)
--verbose               Enable detailed logging
```

## Troubleshooting

### "No API key provided"

Make sure you've set `ANTHROPIC_API_KEY` in `.env` or passed it via `--api-key`.

### "Contract file not found"

Check that `data/parsed_contract.json` exists in your directory.

### "Transaction file not found"

Check that `data/transaction_table.csv` exists in your directory.

### API Rate Limits

If you hit rate limits, reduce `--batch-size` or add delays between batches.

## Next Steps

- Review the discrepancy reports:
  - Human-readable: `output/discrepancy_report.txt`
  - Machine-readable: `output/discrepancy_report.json`
- Check the detailed architecture in `ARCHITECTURE.md`
- Explore the implementation in `IMPLEMENTATION_GUIDE.md`
- Learn about semantic field mapping in `SEMANTIC_MAPPING.md`

## Example Commands

```bash
# Quick test with 5 transactions
python main.py --max-transactions 5 --verbose

# Process all approved transactions
python main.py --batch-size 20

# Custom files with specific output
python main.py \
  --contract my_contract.json \
  --transactions my_transactions.csv \
  --output my_results.json

# Use API key from command line
python main.py --api-key sk-ant-your-key-here
```

## Performance Tips

1. **Batch size**: Larger batches = fewer API calls but more context per call
2. **Max transactions**: Start small (10-20) to test, then run on full dataset
3. **Filtering**: The agent automatically filters to approved transactions only

## Support

For issues or questions, check:
- `ARCHITECTURE.md` - System design details
- `IMPLEMENTATION_GUIDE.md` - Code examples
- `AGENT_TOOL_ARCHITECTURE.md` - Agent-tool interaction patterns
