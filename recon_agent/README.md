# DINTARES Fee Verification Agent

Transaction fee verification agent for DINTARES contract compliance.

## Features

- Parse Excel files with Russian and English headers
- Auto-detect fee columns with confidence scoring
- Verify all fee types: Remuneration (3.8%), Chargeback (€50), Refund (€5), Rolling Reserve (10%)
- Rolling Reserve tracking with €37,500 cap and 180-day holding
- Decimal precision for accurate monetary calculations
- Generate structured text reports with ASCII tables
- Export JSON reports for machine processing

## Installation

```bash
# Install dependencies with UV
uv sync

# Or with pip
pip install -e .
```

## Usage

### Discovery Mode

Show Excel structure before verification:

```bash
python main.py --discovery
```

### Basic Verification

Verify transactions with default files:

```bash
python main.py
```

### Custom Files

```bash
python main.py --excel path/to/transactions.xlsx --contract path/to/contract.json
```

### Specific Sheet

```bash
python main.py --sheet "Sheet2"
```

### Custom Output

```bash
python main.py --output output/my_report
```

## Input Files

### Contract JSON

Expected location: `data/Agreement_FINTHESIS_DINTARES LTD.docx.pdf.json`

Contract must include fee structure with:
- Remuneration rate
- Chargeback cost
- Refund cost
- Rolling Reserve rate, cap, and holding period

### Excel File

Expected location: `data/DINTARES  LIMITED_.xlsx`

Excel file can have Russian or English column headers. The agent auto-detects:
- Transaction ID (номер, transaction_id)
- Amount (сумма, amount)
- Commission (комиссия, commission)
- Rolling Reserve (резерв, RR, rolling_reserve)
- Chargeback (чарджбэк, chargeback)
- Refund (возврат, refund)

## Output

The agent generates two reports:

1. **Text Report** (`output/fee_verification_report.txt`)
   - Summary with total transactions, errors, and questionable cases
   - ASCII table of erroneous transactions
   - ASCII table of questionable transactions

2. **JSON Report** (`output/fee_verification_report.json`)
   - Machine-readable structured data
   - Complete verification details for all transactions

## Fee Verification Rules

Based on DINTARES contract:

- **Remuneration**: 3.8% of transaction amount
- **Chargeback**: €50 flat fee per chargeback
- **Refund**: €5 flat fee per refund
- **Rolling Reserve**: 10% of transaction amount
  - Maximum cap: €37,500
  - Holding period: 180 days
- **Tolerance**: €0.01 for comparisons

## Confidence Scoring

Each verification includes a confidence score (0.0-1.0):

- **High (0.8-1.0)**: Clear data, exact column matches
- **Medium (0.5-0.79)**: Some inference needed, partial matches
- **Low (0.0-0.49)**: Missing/ambiguous data → marked as "QUESTIONABLE"

## Architecture

```
recon_agent/
├── agent/
│   ├── core.py                   # Main orchestrator
│   ├── models/                   # Pydantic data models
│   │   ├── contract.py
│   │   ├── transaction.py
│   │   └── report.py
│   └── tools/                    # Modular tools
│       ├── excel_loader.py       # Excel parsing with Russian support
│       ├── contract_loader.py    # Contract JSON parser
│       ├── field_detector.py     # Auto-detect columns
│       ├── fee_calculator.py     # Calculate expected fees
│       ├── rr_calculator.py      # Rolling Reserve tracker
│       ├── fee_verifier.py       # Compare actual vs expected
│       └── report_generator.py   # Generate reports
├── data/                         # Input files
├── output/                       # Generated reports
└── main.py                       # CLI entry point
```

## License

MIT
