# Transaction Fee Verification Agent

An autonomous Claude-powered agent that verifies transaction fees against contractual terms, handling ambiguous data and providing confidence-scored decisions.

---

## Overview

This agent analyzes transaction records from CSV files and verifies that fees charged match the contractual terms defined in a JSON contract file. It handles:

- **Ambiguous field mappings** (e.g., "commission" vs "comission")
- **Incomplete data** (inferring payment methods from multiple fields)
- **Complex fee structures** (tiered pricing, regional variations)
- **Confidence scoring** (0.0-1.0) for each decision
- **Detailed reasoning** for all discrepancies

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     INPUT DATA                               │
│  ┌─────────────────────┐    ┌─────────────────────────┐    │
│  │ parsed_contract.json│    │ transaction_table.csv   │    │
│  │                     │    │                         │    │
│  │ - Card fees         │    │ - Transaction records   │    │
│  │ - APM fees          │    │ - Commissions charged   │    │
│  │ - Tiered pricing    │    │ - Payment methods       │    │
│  │ - Regional rates    │    │ - Amounts, currencies   │    │
│  └─────────────────────┘    └─────────────────────────┘    │
└────────────────────┬──────────────────┬─────────────────────┘
                     │                   │
                     └────────┬──────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│              TRANSACTION FEE VERIFICATION AGENT              │
│                    (Claude Sonnet 4.5)                       │
│                                                              │
│  Main Capabilities:                                          │
│  • Orchestration & decision making                           │
│  • Reasoning about ambiguities                               │
│  • Confidence scoring                                        │
│  • Assumption documentation                                  │
└────────────────────┬────────────────────────────────────────┘
                     │
                     │ Uses Tools
                     ▼
┌─────────────────────────────────────────────────────────────┐
│                        TOOL LAYER                            │
│                                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │ Data Loaders │  │ Field Mapper │  │ Contract     │     │
│  │              │  │              │  │ Matcher      │     │
│  │ • Load JSON  │  │ • Normalize  │  │              │     │
│  │ • Load CSV   │  │   field names│  │ • Find rules │     │
│  │ • Batch      │  │ • Infer      │  │ • Match      │     │
│  │   processing │  │   payment    │  │   dimensions │     │
│  │              │  │   methods    │  │ • Handle     │     │
│  │              │  │              │  │   tiers      │     │
│  └──────────────┘  └──────────────┘  └──────────────┘     │
│                                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │ Fee          │  │ Validator    │  │ Reporter     │     │
│  │ Calculator   │  │              │  │              │     │
│  │              │  │ • Compare    │  │ • Generate   │     │
│  │ • Calculate  │  │   actual vs  │  │   reports    │     │
│  │   expected   │  │   expected   │  │ • Format     │     │
│  │   fees       │  │ • Tolerance  │  │   output     │     │
│  │ • Handle     │  │   checking   │  │ • Export     │     │
│  │   tiered     │  │ • Component  │  │   JSON/CSV   │     │
│  │   pricing    │  │   validation │  │              │     │
│  └──────────────┘  └──────────────┘  └──────────────┘     │
└────────────────────┬────────────────────────────────────────┘
                     │
                     │ Outputs
                     ▼
┌─────────────────────────────────────────────────────────────┐
│                      OUTPUT                                  │
│  ┌─────────────────────────────────────────────────────┐   │
│  │          discrepancy_report.json                     │   │
│  │                                                       │   │
│  │  {                                                    │   │
│  │    "transaction_id": "...",                          │   │
│  │    "actual_commission": 5.0,                         │   │
│  │    "expected_commission": 5.1028,                    │   │
│  │    "discrepancy": -0.1028,                           │   │
│  │    "status": "UNDERCHARGED",                         │   │
│  │    "confidence": 0.85,                               │   │
│  │    "reasoning": "...",                               │   │
│  │    "assumptions": ["..."]                            │   │
│  │  }                                                    │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

---

## Processing Flow

```
┌─────────────────┐
│ Load Contract   │
│ Data            │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Load Transaction│
│ Batch (N=100)   │
└────────┬────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────┐
│ FOR EACH TRANSACTION:                                    │
│                                                          │
│  1. Map Fields                                           │
│     ┌─────────────────────────────────────────┐        │
│     │ • comission_eur → commission_total      │        │
│     │ • traffic_type_group → payment_method   │        │
│     │ • mdr_eur → merchant_discount_rate      │        │
│     └─────────────────────────────────────────┘        │
│                                                          │
│  2. Infer Payment Method                                 │
│     ┌─────────────────────────────────────────┐        │
│     │ • Check traffic_type_group field        │        │
│     │ • Check gate_name field                 │        │
│     │ • Check card_brand field                │        │
│     │ → payment_method + confidence score     │        │
│     └─────────────────────────────────────────┘        │
│                                                          │
│  3. Find Contract Rule                                   │
│     ┌─────────────────────────────────────────┐        │
│     │ Match on:                                │        │
│     │  • Currency (EUR, USD, GBP, etc.)       │        │
│     │  • Payment method (card, sepa, etc.)    │        │
│     │  • Region (EEA, WW, UK, etc.)           │        │
│     │  • Card brand (Visa, Mastercard)        │        │
│     │  • Transaction type (payment, payout)   │        │
│     │ → best_match rule + confidence          │        │
│     └─────────────────────────────────────────┘        │
│                                                          │
│  4. Calculate Expected Fee                               │
│     ┌─────────────────────────────────────────┐        │
│     │ Payment: (amount × wl_rate) + fixed_fee │        │
│     │ Payout: (amount × rate) + payout_oct_fix│        │
│     │ Refund: refund_fee (flat)               │        │
│     │ Chargeback: chb_fee (flat)              │        │
│     │ → expected_fee breakdown                │        │
│     └─────────────────────────────────────────┘        │
│                                                          │
│  5. Compare Actual vs Expected                           │
│     ┌─────────────────────────────────────────┐        │
│     │ difference = actual - expected           │        │
│     │ within_tolerance = |diff| <= 0.01       │        │
│     │ → CORRECT / OVERCHARGED / UNDERCHARGED  │        │
│     └─────────────────────────────────────────┘        │
│                                                          │
│  6. Calculate Confidence                                 │
│     ┌─────────────────────────────────────────┐        │
│     │ confidence = min(                        │        │
│     │   payment_method_confidence,             │        │
│     │   contract_match_confidence              │        │
│     │ ) × ambiguity_factor                    │        │
│     └─────────────────────────────────────────┘        │
│                                                          │
│  7. Generate Report (if discrepancy)                     │
│     ┌─────────────────────────────────────────┐        │
│     │ • Document reasoning                     │        │
│     │ • List assumptions                       │        │
│     │ • Explain confidence score               │        │
│     │ • Include calculation details            │        │
│     └─────────────────────────────────────────┘        │
│                                                          │
└──────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────┐
│ Export Results  │
│ to JSON/CSV     │
└─────────────────┘
```

---

## Key Features

### 1. Ambiguity Handling

**Problem**: Field names vary ("commission" vs "comission")

**Solution**:
- Configurable field mapping dictionary
- Automatic field name normalization
- Document all mapping assumptions

**Example**:
```python
FIELD_MAPPINGS = {
    "comission_eur": "commission_total",  # Handle typo
    "mdr_eur": "merchant_discount_rate",
    "traffic_type_group": "payment_method"
}
```

### 2. Payment Method Inference

**Problem**: Payment method not always explicit

**Solution**:
- Multi-field inference algorithm
- Confidence scoring for each inference
- Evidence documentation

**Example**:
```
traffic_type_group = "apple_pay"
→ payment_method = "apple_pay" (confidence: 0.95)

gate_name = "SEPA OUT"
→ payment_method = "sepa" (confidence: 0.85)

card_brand = "VISA"
→ payment_method = "card" (confidence: 0.90)
```

### 3. Contract Rule Matching

**Problem**: Multiple dimensions to match (currency, region, card brand, etc.)

**Solution**:
- Multi-dimensional matching algorithm
- Match scoring (0.0-1.0)
- Ambiguity detection

**Example**:
```python
Transaction: EUR, card, Germany, Visa, payment
→ Matches:
  1. card_fees.eur_eea (score: 0.95)  # Exact match
  2. card_fees.eur_ww (score: 0.85)   # Universal fallback
→ Best match: eur_eea (confidence: 0.95)
```

### 4. Confidence Scoring

**High Confidence (0.8-1.0)**:
- Exact field matches
- Single applicable rule
- Simple fee structure
- All data present

**Medium Confidence (0.5-0.79)**:
- Inferred payment method
- Multiple possible rules
- Some ambiguity

**Low Confidence (0.0-0.49)**:
- High ambiguity
- Missing critical data
- Conflicting rules

### 5. Detailed Reasoning

Every discrepancy includes:
- **Calculation method**: How expected fee was calculated
- **Assumptions**: What was inferred or assumed
- **Confidence reasoning**: Why the confidence score
- **Contract rule**: Which rule was applied

**Example Report**:
```json
{
  "transaction_id": "dd523aac-...",
  "actual_commission": 5.0,
  "expected_commission": 5.1028,
  "discrepancy": -0.1028,
  "status": "UNDERCHARGED",
  "reasoning": "Expected: 510.28 × 0.01 = 5.1028. Actual: 5.0. Likely rounding error.",
  "assumptions": [
    "Mapped 'comission_eur' to commission_total",
    "Inferred payment_method='sepa' from gate_name='sepa'"
  ],
  "confidence": 0.85,
  "confidence_reasoning": "High: clear SEPA identifier, exact contract match"
}
```

---

## File Structure

```
transaction_analysis/
├── agent/
│   ├── __init__.py
│   ├── main.py                    # Main agent orchestrator
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── data_loader.py         # Load JSON/CSV
│   │   ├── field_mapper.py        # Field normalization
│   │   ├── contract_matcher.py    # Rule matching
│   │   ├── fee_calculator.py      # Fee calculations
│   │   ├── validator.py           # Fee comparison
│   │   └── reporter.py            # Report generation
│   └── models/
│       ├── __init__.py
│       ├── contract.py            # Contract data models
│       ├── transaction.py         # Transaction models
│       └── report.py              # Report models
├── data/
│   ├── parsed_contract.json       # Input: Contract terms
│   └── transaction_table.csv      # Input: Transactions
├── output/
│   └── discrepancy_report.json    # Output: Results
├── tests/
│   ├── test_data_loader.py
│   ├── test_fee_calculator.py
│   └── test_agent.py
├── ARCHITECTURE.md                # Detailed architecture
├── IMPLEMENTATION_GUIDE.md        # Code examples
├── README.md                      # This file
└── requirements.txt
```

---

## Quick Start

### Option 1: Automated Setup (Recommended)

```bash
# Run the setup script
./setup.sh

# Activate virtual environment
source .venv/bin/activate

# Set your API key in .env
# ANTHROPIC_API_KEY=sk-ant-your-key-here

# Run the agent
python main.py --max-transactions 5
```

### Option 2: Manual Setup

```bash
# 1. Install dependencies with uv (fast!)
uv sync  # Creates venv and installs everything!
source .venv/bin/activate

# 2. Configure API key
cp .env.example .env
# Edit .env and add your ANTHROPIC_API_KEY

# 3. Run the agent
python main.py --max-transactions 5
```

### Option 3: Using pip

```bash
# Install dependencies
pip install -r requirements.txt

# Configure and run
cp .env.example .env
python main.py --max-transactions 5
```

### Usage Examples

```bash
# Test with 5 transactions
python main.py --max-transactions 5

# Process all approved transactions
python main.py

# Custom batch size (faster)
python main.py --batch-size 50

# Verbose logging
python main.py --verbose

# Custom files
python main.py --contract my_contract.json --transactions my_data.csv
```

### Programmatic Usage

```python
from agent.core import TransactionVerificationAgent

agent = TransactionFeeVerificationAgent(
    contract_file="data/parsed_contract.json",
    transaction_file="data/transaction_table.csv"
)

# Verify transactions
results = agent.run(batch_size=100, max_transactions=1000)

# Export results
agent.export_results("output/discrepancy_report.json")
```

### 3. Review Results
```bash
cat output/discrepancy_report.json
```

---

## Example Output

```json
{
  "summary": {
    "total_discrepancies": 45,
    "discrepancies_by_status": {
      "OVERCHARGED": 23,
      "UNDERCHARGED": 22
    },
    "discrepancies_by_payment_method": {
      "card": 30,
      "sepa": 10,
      "apple_pay": 5
    },
    "total_discrepancy_amount": -15.67
  },
  "discrepancies": [
    {
      "transaction_id": "dd523aac-9bdf-429e-829e-7961316306bc",
      "transaction_date": "2024-09-20",
      "amount": 510.28,
      "currency": "EUR",
      "payment_method": "sepa",
      "actual_commission": 5.0,
      "expected_commission": 5.1028,
      "discrepancy": -0.1028,
      "discrepancy_percentage": -2.01,
      "status": "UNDERCHARGED",
      "reasoning": "Expected fee: 510.28 × 0.01 = 5.1028 EUR. Actual: 5.0 EUR.",
      "assumptions": [
        "Mapped 'comission_eur' to commission_total",
        "Inferred payment_method='sepa' from gate_name"
      ],
      "confidence": 0.85,
      "confidence_reasoning": "High confidence: clear SEPA identifier, exact contract match",
      "contract_rule_applied": {
        "category": "outgoing_fees.sepa",
        "rule_key": "balance_from_processing",
        "rate": 0.0,
        "payout_oct_fix": 2.5
      }
    }
  ]
}
```

---

## Advanced Features

### 1. Tiered Fee Handling

Some payment methods have volume-based tiers:

```python
# Open Banking Tiers
Tier 1 (€0 - €500k):    wl_rate=0.020, fixed=€0.70
Tier 2 (€500k - €1M):   wl_rate=0.017, fixed=€0.50
Tier 3 (€1M+):          wl_rate=0.015, fixed=€0.30

# Agent automatically determines tier based on monthly volume
```

### 2. Excessive Chargeback Fees

Conditionally applied fees:

```python
# If monthly CB volume > 1.0% AND CB count > 100
# → Apply excessive_chargeback_fees instead of standard chb_fee

# Agent tracks monthly metrics and applies correct fee
```

### 3. Currency Exchange Fees

```python
# When currency conversion occurs
# → Apply fx_fees.fiat_currency_exchange (0.5%)

# Agent detects currency mismatches and includes FX fees
```

---

## Testing

### Unit Tests
```bash
pytest tests/test_fee_calculator.py
pytest tests/test_contract_matcher.py
```

### Integration Test
```bash
pytest tests/test_agent.py
```

### Test Cases
- Exact match scenarios
- Ambiguous field names
- Multiple matching rules
- Tiered fee boundaries
- Missing data handling
- Edge cases (€0 amounts, declined transactions)

---

## Extending the Agent

### Adding New Payment Methods

1. Update `PAYMENT_METHOD_INDICATORS` in `field_mapper.py`
2. Add contract parsing in `contract_matcher.py`
3. Add fee calculation logic in `fee_calculator.py`

### Adding New Fee Types

1. Define fee structure in contract JSON
2. Add matching logic in `find_applicable_contract_rule()`
3. Add calculation logic in `calculate_expected_fees()`

### Custom Confidence Scoring

Modify `confidence.py`:
```python
def calculate_confidence(
    payment_method_confidence: float,
    rule_match_confidence: float,
    data_completeness: float,
    ambiguity_count: int
) -> float:
    # Custom logic here
    pass
```

---

## Documentation

- **ARCHITECTURE.md**: Detailed system design and tool specifications
- **IMPLEMENTATION_GUIDE.md**: Code examples and implementation details
- **README.md**: This file - overview and quick start

---

## Next Steps

1. **Implement core tools** (data_loader, fee_calculator, contract_matcher)
2. **Build agent orchestrator** with Claude API integration
3. **Add tests** for all tools and integration scenarios
4. **Run on sample data** to validate approach
5. **Iterate based on results** and edge cases found
6. **Add visualization** for results dashboard
7. **Deploy as MCP server** (optional) for integration

---

## Support & Contribution

For questions or contributions, please review the architecture and implementation guides first.

**Key Considerations**:
- Always document assumptions
- Provide confidence scores
- Handle incomplete data gracefully
- Never fail silently - report uncertainties
