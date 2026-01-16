# Fee Verification Agent

Transaction fee verification agent for contract compliance. Automatically verifies transaction fees against contract terms with support for multiple currencies, sheets, and data formats.

## Features

- **Auto-Discovery**: Automatically finds contract JSON and Excel files in `data/` directory
- **Multi-Language Support**: Parse Excel files with Russian and English headers
- **Smart Column Detection**: Auto-detect fee columns with confidence scoring
- **Comprehensive Fee Verification**: Verify remuneration, rolling reserve, chargeback, and refund fees
- **Multi-Sheet Processing**: Process all sheets in an Excel workbook simultaneously
- **Decimal Precision**: Accurate monetary calculations using Python's Decimal type
- **Detailed Reports**: Generate structured text reports with ASCII tables and JSON exports
- **Flexible Calculations**:
  - Percentage-based fees (remuneration, rolling reserve)
  - Quantity-based fees (chargeback = qty × €50, refund = qty × €5)
  - Capped calculations (rolling reserve cap support)
- **Intelligent Categorization**: Separates correct, erroneous, questionable, and missing data transactions

## Installation

### Prerequisites
- Python 3.11 or higher
- `uv` package manager (recommended) or `pip`

### Setup

```bash
# Clone or navigate to the project directory
cd recon_agent

# Install dependencies with uv (recommended)
uv sync

# Or with pip
pip install -e .
```

## Quick Start

### 1. Prepare Your Data

Place your files in the `data/` directory:

```
data/
├── your_contract.json        # Contract terms (JSON format)
└── your_transactions.xlsx    # Transaction data (Excel)
```

### 2. Run the Agent

```bash
# Auto-discover and verify all sheets
uv run python main.py --all-sheets

# Or with activated virtual environment
source .venv/bin/activate
python main.py --all-sheets
```

### 3. View Results

Reports are generated in the `output/` directory:
- `fee_verification_report.txt` - Human-readable report
- `fee_verification_report.json` - Machine-readable data

## Usage

### Auto-Discovery (Recommended)

Process all sheets with auto-discovered files:

```bash
uv run python main.py --all-sheets
```

The agent automatically finds:
- Contract JSON file (`.json`) in `data/`
- Excel file (`.xlsx`, `.xls`, `.xlsm`) in `data/`

### Discovery Mode

Preview Excel structure before verification:

```bash
uv run python main.py --discovery
```

Shows:
- Available sheets
- Column names (original and normalized)
- Row counts
- Detected header rows

### Specify Custom Files

```bash
uv run python main.py \
  --contract data/my_contract.json \
  --excel data/my_transactions.xlsx \
  --all-sheets
```

### Process Specific Sheet

```bash
uv run python main.py --sheet "EUR (F)"
```

### Custom Output Path

```bash
uv run python main.py --output output/custom_report --all-sheets
```

### Adjust Confidence Threshold

```bash
uv run python main.py --confidence-threshold 0.7 --all-sheets
```

Transactions with confidence below threshold are marked as "QUESTIONABLE".

## Input Files

### Contract JSON

**Location**: `data/` directory (auto-discovered)

**Required Fields**:
```json
{
  "fees_and_rates": [
    {
      "fee_name": "Remuneration",
      "amount": 0.038
    },
    {
      "fee_name": "Chargeback",
      "amount": 50
    },
    {
      "fee_name": "Refund",
      "amount": 5
    },
    {
      "fee_name": "Rolling Reserve",
      "amount": 0.1,
      "maximum_cap": 37500
    }
  ],
  "payment_methods": {
    "supported_cards": ["MasterCard", "Maestro"],
    "currencies": ["EUR", "GBP", "USD", "AUD", "NOK"]
  }
}
```

### Excel File

**Location**: `data/` directory (auto-discovered)

**Supported Formats**: `.xlsx`, `.xls`, `.xlsm`

**Column Detection**:

The agent auto-detects columns using multiple patterns:

| Fee Type | English Patterns | Russian Patterns |
|----------|-----------------|------------------|
| Amount | amount, sum, total, оборот | сумма, оборот |
| Commission | commission, fee, charge | комиссия, вознаграждение |
| Rolling Reserve | rolling_reserve, rr, reserve | резерв, резервфонд |
| Chargeback | chargeback, chb, cb | чарджбэк, чб |
| Refund | refund, ref | возврат |

**Special Sheet Support**:

For sheets like `EUR (F)` and `AUD (F)` with multi-level headers:
- Automatically merges main headers (row 1) with sub-headers (row 2)
- Detects quantity columns (`кол-во`) for chargeback/refund calculations
- Detects actual fee collected columns (`fix 50 euro`, `fix 5 euro`)

## Output Reports

### Text Report

**File**: `output/fee_verification_report.txt`

**Sections**:
1. **Detection Assumptions**: Lists any assumptions made during column detection
2. **Summary**:
   - Total transactions processed
   - Count by category (Correct, Erroneous, Questionable, Missing Data)
   - Total discrepancy amount
   - Complete data only discrepancy (excludes transactions with missing data)
3. **Breakdown by Sheet**: Per-sheet statistics
4. **Erroneous Transactions**:
   - Split by fee type (Remuneration, Rolling Reserve, Chargeback, Refund)
   - Sorted by absolute difference (largest discrepancies first)
   - Shows expected, actual, and difference amounts
5. **Questionable Transactions**: Low-confidence detections with reasons
6. **Missing Data Transactions**: All transactions with any missing fee data

### JSON Report

**File**: `output/fee_verification_report.json`

**Structure**:
```json
{
  "metadata": {
    "generated": "2026-01-15T11:30:21",
    "contract_file": "contract.json",
    "excel_file": "transactions.xlsx",
    "sheet_name": "all_sheets",
    "detection_assumptions": [...]
  },
  "summary": {
    "total_transactions": 1316,
    "correct_count": 22,
    "erroneous_count": 366,
    "questionable_count": 413,
    "missing_data_count": 515,
    "total_discrepancy": "151297.37",
    "total_discrepancy_complete_data_only": "151258.82"
  },
  "erroneous_transactions": [...],
  "questionable_transactions": [...],
  "missing_data_transactions": [...],
  "all_verifications": [...]
}
```

## Fee Verification Rules

### Standard Fees (Percentage-based)

- **Remuneration**: Percentage of transaction amount (e.g., 3.8%)
- **Rolling Reserve**: Percentage of transaction amount (e.g., 10%)
  - Subject to maximum cap (e.g., €37,500 or €150,000)
  - Holding period: typically 180 days

### Quantity-based Fees (EUR (F) / AUD (F) sheets)

For sheets with quantity columns:

- **Chargeback**: `quantity × €50 per chargeback`
  - Read from: `chb_кол-во` (quantity) and `chb_fix_50_euro` (actual collected)
  - Formula: Expected = qty × 50, compare with actual collected

- **Refund**: `quantity × €5 per refund`
  - Read from: `refund_кол-во` (quantity) and `refund_fix_5_euro` (actual collected)
  - Formula: Expected = qty × 5, compare with actual collected

### Tolerance

Default tolerance: **€0.01** for all comparisons

Differences within tolerance are considered "CORRECT".

## Transaction Categorization

Each transaction is categorized based on verification results and confidence:

| Category | Criteria | Meaning |
|----------|----------|---------|
| **CORRECT** | All fees within tolerance, high confidence | ✅ Fees are accurate |
| **ERRONEOUS** | One or more fees outside tolerance | ❌ Fee discrepancies found |
| **QUESTIONABLE** | Low confidence detection (< threshold) | ⚠️ Uncertain data, manual review needed |
| **MISSING DATA** | Missing required fee columns | 📭 Incomplete data |

## Confidence Scoring

Each field detection receives a confidence score (0.0-1.0):

| Score Range | Match Type | Example |
|-------------|------------|---------|
| **1.0** | Exact match | Column "commission" → "commission" |
| **0.9** | Starts with | Column "commission_eur" → "commission" |
| **0.8** | Ends with | Column "processing_commission" → "commission" |
| **0.7** | Contains | Column "total_commission_amount" → "commission" |
| **0.6** | Fuzzy (2 char diff) | Column "commision" → "commission" |
| **0.5** | Fuzzy (3 char diff) | Column "comission" → "commission" |

**Overall Confidence** is calculated from:
- Average confidence of required fields (amount, commission, etc.)
- Number of assumptions made
- Penalty for very low confidence critical fields (< 0.6)

## Architecture

```
recon_agent/
├── .venv/                       # Virtual environment
├── agent/
│   ├── core.py                  # Main orchestrator
│   ├── models/                  # Pydantic data models
│   │   └── contract.py          # Contract structure
│   └── tools/                   # Modular tools
│       ├── excel_loader.py      # Excel parsing with auto-discovery
│       ├── contract_loader.py   # Contract JSON parser with auto-discovery
│       ├── field_detector.py    # Auto-detect columns with confidence scoring
│       ├── fee_calculator.py    # Calculate expected fees
│       ├── rr_calculator.py     # Rolling Reserve tracker with cap
│       ├── fee_verifier.py      # Compare actual vs expected (qty-based logic)
│       └── report_generator.py  # Generate text/JSON reports
├── data/                        # Input files (auto-discovered)
│   ├── *.json                   # Contract files
│   └── *.xlsx                   # Excel transaction files
├── output/                      # Generated reports
│   ├── *.txt                    # Human-readable reports
│   └── *.json                   # Machine-readable reports
├── main.py                      # CLI entry point
├── pyproject.toml               # Dependencies and project config
└── README.md                    # This file
```

## Examples

### Example 1: Basic Verification

```bash
# Place files in data/
# - contract.json
# - transactions.xlsx

# Run verification
uv run python main.py --all-sheets

# Output:
# Auto-discovered contract: contract.json
# Auto-discovered Excel file: transactions.xlsx
# ...
# ✓ Text report: output/fee_verification_report.txt
# ✓ JSON report: output/fee_verification_report.json
```

### Example 2: Multiple Currencies

```bash
# Excel file with sheets: EUR (S), USD (S), GBP (S), AUD (S)
uv run python main.py --all-sheets

# Processes all currency sheets and generates combined report
```

### Example 3: Single Currency Analysis

```bash
# Process only EUR transactions
uv run python main.py --sheet "EUR (F)" --output output/eur_only
```

### Example 4: Custom Threshold

```bash
# Mark transactions with confidence < 0.7 as questionable
uv run python main.py --all-sheets --confidence-threshold 0.7
```

## Troubleshooting

### Multiple Files Found

**Error**: `Multiple contract files found in data/`

**Solution**: Specify which file to use:
```bash
uv run python main.py --contract data/specific_contract.json --all-sheets
```

### No Files Found

**Error**: `No JSON contract files found in data/`

**Solution**: Ensure files are in the `data/` directory and have correct extensions (`.json`, `.xlsx`)

### Low Confidence Warnings

**Message**: `Questionable: 89 transactions`

**Meaning**: Column detection had low confidence for some transactions.

**Action**:
1. Check the "Detection Assumptions" section in the report
2. Review "Questionable Transactions" table
3. Manually verify these transactions or adjust column names in Excel

### Virtual Environment Issues

**Error**: `ModuleNotFoundError: No module named 'pandas'`

**Solution**:
```bash
# Re-sync dependencies
uv sync

# Or manually activate and install
source .venv/bin/activate
pip install -e .
```

## Command Reference

```bash
# Show help
uv run python main.py --help

# Discovery mode
uv run python main.py --discovery

# All sheets with auto-discovery
uv run python main.py --all-sheets

# Single sheet
uv run python main.py --sheet "EUR (F)"

# Custom files
uv run python main.py --contract data/c.json --excel data/t.xlsx

# Custom output
uv run python main.py --output output/report --all-sheets

# Custom threshold
uv run python main.py --confidence-threshold 0.7 --all-sheets

# Verbose mode
uv run python main.py --verbose --all-sheets
```

## Development

### Running Tests

```bash
# Install dev dependencies
uv sync --dev

# Run tests
pytest
```

### Adding Dependencies

```bash
# Add new dependency
uv add package-name

# Add dev dependency
uv add --dev package-name
```

## License

MIT
