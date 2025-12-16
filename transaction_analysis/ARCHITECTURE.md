# Transaction Fee Verification Agent - Architecture Design

## 1. System Overview

An autonomous Claude-powered agent that verifies transaction fees against contractual terms using a tool-based architecture.

### Key Capabilities
- Parse complex contract JSON and transaction CSV files
- Handle ambiguous field mappings (e.g., "commission" vs "fee")
- Calculate expected fees based on multiple contract dimensions
- Provide confidence-scored decisions with reasoning
- Handle incomplete information gracefully

---

## 2. Agent Core Design

### Main Agent (Claude Sonnet 4.5)
**Role**: Orchestrator and reasoning engine

**Responsibilities**:
- Coordinate tool calls in logical sequence
- Make decisions about ambiguous mappings
- Calculate confidence scores (0.0 - 1.0)
- Generate human-readable explanations
- Handle edge cases and incomplete data

**Decision Framework**:
```
For each transaction:
1. Identify transaction characteristics (currency, region, payment method, type)
2. Match to applicable contract rule(s)
3. Calculate expected fees
4. Compare with actual fees
5. If mismatch: generate explanation + confidence score
6. If ambiguous: document assumptions
```

---

## 3. Tool Architecture

### 3.1 Data Loader Tools

#### `load_contract_data`
**Purpose**: Load and parse contract JSON
**Input**: File path
**Output**: Structured contract data object
**Implementation**:
```python
{
    "tool": "load_contract_data",
    "description": "Load contract fee structures from JSON file",
    "parameters": {
        "file_path": "string"
    },
    "returns": {
        "contract_data": "dict",
        "fee_categories": "list[string]",
        "currencies": "list[string]",
        "regions": "list[string]"
    }
}
```

#### `load_transaction_data`
**Purpose**: Load transaction CSV with chunking support
**Input**: File path, optional row limit/offset
**Output**: Transaction records as structured data
**Implementation**:
```python
{
    "tool": "load_transaction_data",
    "description": "Load transaction records from CSV file",
    "parameters": {
        "file_path": "string",
        "limit": "int (optional)",
        "offset": "int (optional)",
        "filters": "dict (optional)"  # e.g., {"status": "approved"}
    },
    "returns": {
        "transactions": "list[dict]",
        "total_count": "int",
        "columns": "list[string]"
    }
}
```

#### `get_transaction_batch`
**Purpose**: Process transactions in manageable batches
**Input**: Batch size, offset
**Output**: Next batch of transactions
**Why**: Handle large CSV files efficiently

---

### 3.2 Mapping & Matcher Tools

#### `find_applicable_contract_rule`
**Purpose**: Match transaction to contract terms
**Input**: Transaction characteristics
**Output**: Applicable contract rule(s)

**Matching Logic**:
```python
{
    "tool": "find_applicable_contract_rule",
    "description": "Find contract rule(s) applicable to a transaction",
    "parameters": {
        "currency": "string",
        "region": "string (optional)",
        "payment_method": "string",  # card, apple_pay, sepa, etc.
        "card_brand": "string (optional)",  # Visa, MasterCard
        "transaction_type": "string",  # payment, payout, refund
        "amount": "float (optional)",  # for tiered fees
        "monthly_volume": "float (optional)"  # for tier calculations
    },
    "returns": {
        "rules": "list[dict]",
        "ambiguities": "list[string]",
        "confidence": "float"
    }
}
```

**Ambiguity Handling**:
- If multiple rules match → return all with confidence < 1.0
- If no exact match → return closest matches with confidence score
- Document assumptions in "ambiguities" field

#### `map_transaction_fields`
**Purpose**: Handle field name variations
**Input**: Transaction record
**Output**: Normalized field mapping

```python
{
    "tool": "map_transaction_fields",
    "description": "Map transaction CSV fields to standard names",
    "parameters": {
        "transaction": "dict",
        "available_columns": "list[string]"
    },
    "returns": {
        "mapped_fields": "dict",
        "unmapped_fields": "list[string]",
        "assumptions": "list[dict]"  # e.g., [{"assumed": "comission_eur means total commission"}]
    }
}
```

**Known Mappings**:
- `comission_eur` → `commission_eur` (spelling variation)
- `mdr_eur` → `merchant_discount_rate`
- `fixed_eur` → `fixed_fee`
- `traffic_type_group` → `payment_method` (inferred)

---

### 3.3 Fee Calculator Tools

#### `calculate_expected_fees`
**Purpose**: Calculate fees based on contract rules
**Input**: Transaction amount, contract rule
**Output**: Breakdown of expected fees

```python
{
    "tool": "calculate_expected_fees",
    "description": "Calculate expected fees per contract terms",
    "parameters": {
        "amount": "float",
        "contract_rule": "dict",
        "transaction_type": "string"  # payment, payout, refund, chargeback
    },
    "returns": {
        "breakdown": {
            "percentage_fee": "float",  # wl_rate * amount
            "fixed_fee": "float",
            "total": "float",
            "components": "dict"  # detailed breakdown
        },
        "calculation_method": "string",  # explanation
        "applicable_rates": "dict"
    }
}
```

**Calculation Logic**:
```python
# Standard card payment
total_fee = (amount * wl_rate) + fixed_fee

# Tiered fees (e.g., open banking)
# Determine tier based on monthly volume
# Apply tier-specific wl_rate and fixed_fee

# Chargeback fees
# Check if excessive CB conditions met
# Apply standard chb_fee or excessive fee
```

#### `calculate_tiered_fee`
**Purpose**: Handle volume-based tiered pricing
**Input**: Amount, cumulative volume, tier structure
**Output**: Applicable tier and fee

```python
{
    "tool": "calculate_tiered_fee",
    "description": "Calculate fee for tiered pricing structures",
    "parameters": {
        "amount": "float",
        "cumulative_monthly_volume": "float",
        "tier_structure": "dict"  # e.g., open_banking_turnover_tiers
    },
    "returns": {
        "applicable_tier": "string",
        "tier_rate": "float",
        "tier_fixed_fee": "float",
        "calculated_fee": "float",
        "tier_boundaries": "dict"
    }
}
```

---

### 3.4 Validation Tools

#### `compare_fees`
**Purpose**: Compare actual vs expected fees
**Input**: Actual fees, expected fees
**Output**: Comparison result with discrepancies

```python
{
    "tool": "compare_fees",
    "description": "Compare actual charged fees with expected fees",
    "parameters": {
        "actual_fees": "dict",
        "expected_fees": "dict",
        "tolerance": "float"  # e.g., 0.01 for 1 cent tolerance
    },
    "returns": {
        "is_correct": "bool",
        "discrepancies": "list[dict]",
        "difference_amount": "float",
        "difference_percentage": "float",
        "within_tolerance": "bool"
    }
}
```

#### `validate_fee_components`
**Purpose**: Verify individual fee components
**Input**: Transaction record, contract rule
**Output**: Component-level validation

```python
{
    "tool": "validate_fee_components",
    "description": "Validate individual fee components (fixed, variable, etc.)",
    "parameters": {
        "transaction": "dict",
        "contract_rule": "dict"
    },
    "returns": {
        "fixed_fee_correct": "bool",
        "variable_fee_correct": "bool",
        "total_fee_correct": "bool",
        "component_errors": "list[dict]"
    }
}
```

---

### 3.5 Context Tools

#### `get_monthly_volume`
**Purpose**: Calculate cumulative monthly volume for tier determination
**Input**: Merchant ID, date, payment method
**Output**: Volume statistics

```python
{
    "tool": "get_monthly_volume",
    "description": "Calculate monthly transaction volume for tiered pricing",
    "parameters": {
        "merchant_id": "string",
        "payment_method": "string",
        "month": "string",  # YYYY-MM
        "currency": "string"
    },
    "returns": {
        "total_volume": "float",
        "transaction_count": "int",
        "running_total_at_date": "dict"  # {date: volume}
    }
}
```

#### `get_chargeback_metrics`
**Purpose**: Calculate chargeback ratios for excessive CB fee determination
**Input**: Merchant ID, month
**Output**: Chargeback statistics

```python
{
    "tool": "get_chargeback_metrics",
    "description": "Calculate chargeback metrics for excessive fee assessment",
    "parameters": {
        "merchant_id": "string",
        "month": "string"
    },
    "returns": {
        "chargeback_count": "int",
        "chargeback_volume": "float",
        "total_sales_volume": "float",
        "chargeback_ratio": "float",
        "exceeds_threshold": "bool"
    }
}
```

#### `infer_payment_method`
**Purpose**: Infer payment method from transaction fields
**Input**: Transaction record
**Output**: Best guess payment method with confidence

```python
{
    "tool": "infer_payment_method",
    "description": "Infer payment method from transaction data",
    "parameters": {
        "transaction": "dict"
    },
    "returns": {
        "payment_method": "string",
        "confidence": "float",
        "evidence": "list[string]"  # fields used for inference
    }
}
```

---

### 3.6 Reporting Tools

#### `generate_discrepancy_report`
**Purpose**: Format findings for output
**Input**: Transaction, actual fees, expected fees, reasoning
**Output**: Structured report entry

```python
{
    "tool": "generate_discrepancy_report",
    "description": "Generate detailed discrepancy report",
    "parameters": {
        "transaction_id": "string",
        "actual_fees": "dict",
        "expected_fees": "dict",
        "discrepancies": "list[dict]",
        "reasoning": "string",
        "assumptions": "list[string]",
        "confidence": "float"
    },
    "returns": {
        "report_entry": "dict"  # structured report
    }
}
```

**Report Entry Format**:
```json
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
    "status": "INCORRECT_FEE",
    "reasoning": "Expected fee calculation: 510.28 * 0.01 = 5.1028 EUR. Actual charged: 5.0 EUR. Possible rounding down instead of standard rounding.",
    "assumptions": [
        "Mapped 'comission_eur' field to total commission",
        "Interpreted 'sepa' gate_name as SEPA payout (outgoing)",
        "Applied outgoing SEPA fixed fee of 2.5 EUR per contract, but mdr_eur shows 5.1028"
    ],
    "confidence": 0.75,
    "confidence_reasoning": "Clear SEPA identifier and fixed fee structure, but some ambiguity in whether this is processing balance or crypto-sourced SEPA transfer",
    "contract_rule_applied": {
        "category": "outgoing_fees.sepa.balance_from_processing",
        "rate": 0.0,
        "payout_oct_fix": 2.5
    }
}
```

#### `export_results`
**Purpose**: Export results to CSV/JSON
**Input**: All discrepancy reports
**Output**: File path

---

## 4. Agent Workflow

### Phase 1: Initialization
```
1. Load contract data → parse fee structures
2. Load transaction data metadata → understand columns
3. Create field mapping → handle naming variations
4. Initialize context (monthly volumes, CB metrics if needed)
```

### Phase 2: Transaction Processing
```
For each transaction (or batch):
  1. Map transaction fields → normalized format
  2. Infer payment method (if not explicit)
  3. Find applicable contract rule(s)
  4. Calculate expected fees
     - Handle tiered structures
     - Check special conditions (excessive CB)
  5. Compare actual vs expected
  6. If discrepancy:
     - Generate reasoning
     - Calculate confidence score
     - Document assumptions
     - Create report entry
```

### Phase 3: Reporting
```
1. Aggregate all discrepancies
2. Generate summary statistics
3. Export detailed report
4. Provide recommendations
```

---

## 5. Confidence Scoring Framework

The agent calculates confidence scores (0.0 - 1.0) based on:

### High Confidence (0.8 - 1.0)
- Exact field matches (e.g., "currency": "EUR")
- Clear payment method identifiers
- Single applicable contract rule
- Simple fee structure (no tiers)
- All required fields present

### Medium Confidence (0.5 - 0.79)
- Inferred payment method from partial data
- Multiple possible contract rules
- Some ambiguous field mappings
- Tiered structure requiring volume data
- Minor missing fields (can be defaulted)

### Low Confidence (0.0 - 0.49)
- High ambiguity in payment method
- Conflicting contract rules
- Significant field mapping uncertainty
- Missing critical data (amount, currency)
- Complex edge cases

### Confidence Calculation Formula
```python
confidence = base_confidence * field_quality * rule_clarity * data_completeness

where:
- base_confidence = 1.0
- field_quality = (mapped_fields / total_required_fields)
- rule_clarity = 1.0 / number_of_applicable_rules
- data_completeness = (present_fields / required_fields)
```

---

## 6. Implementation Approach

### Option A: Python Agent with FastMCP
**Pros**:
- Full Python ecosystem
- Easy CSV/JSON handling with pandas
- Can expose as MCP server
- Integration with existing systems

**Implementation**:
```python
from fastmcp import FastMCP

mcp = FastMCP("transaction-fee-verifier")

@mcp.tool()
def load_contract_data(file_path: str) -> dict:
    """Load and parse contract JSON"""
    # Implementation
    pass

@mcp.tool()
def calculate_expected_fees(
    amount: float,
    contract_rule: dict,
    transaction_type: str
) -> dict:
    """Calculate expected fees based on contract"""
    # Implementation
    pass

# ... other tools
```

### Option B: Pure Claude Tool Use (Recommended)
**Pros**:
- Simpler architecture
- Better for reasoning and ambiguity handling
- Natural language error messages
- Easier confidence scoring

**Implementation**:
1. Create Python functions for each tool
2. Define JSON schemas for tool parameters
3. Agent calls tools via Claude's tool use API
4. Agent reasons about results and makes decisions

---

## 7. Tool Implementation Details

### Technology Stack
- **Language**: Python 3.11+
- **Data Processing**: pandas, numpy
- **Validation**: pydantic
- **CSV/JSON**: Built-in libraries + pandas
- **Agent Framework**: Claude API with tool use
- **Optional MCP**: fastmcp for tooling

### File Structure
```
transaction_analysis/
├── agent/
│   ├── __init__.py
│   ├── main.py              # Agent orchestrator
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── data_loader.py
│   │   ├── fee_calculator.py
│   │   ├── mapper.py
│   │   ├── validator.py
│   │   ├── context.py
│   │   └── reporter.py
│   ├── models/
│   │   ├── __init__.py
│   │   ├── contract.py      # Pydantic models for contract
│   │   ├── transaction.py   # Pydantic models for transaction
│   │   └── report.py        # Report models
│   └── utils/
│       ├── __init__.py
│       ├── confidence.py    # Confidence scoring
│       └── field_mapper.py  # Field name mapping
├── data/
│   ├── parsed_contract.json
│   └── transaction_table.csv
├── output/
│   └── discrepancy_report.json
├── tests/
├── requirements.txt
├── ARCHITECTURE.md          # This file
└── README.md
```

---

## 8. Key Design Decisions

### 1. Tool Granularity
- **Decision**: Separate tools for distinct operations
- **Rationale**: Allows agent to reason step-by-step and handle errors gracefully

### 2. Confidence Scoring
- **Decision**: Quantitative confidence scores (0.0-1.0)
- **Rationale**: Provides clear signal of certainty; allows filtering/sorting results

### 3. Assumption Documentation
- **Decision**: Explicit assumption logging for each decision
- **Rationale**: Transparency for audit; allows human review of agent reasoning

### 4. Ambiguity Handling
- **Decision**: Don't fail on ambiguity; provide best guess + low confidence
- **Rationale**: Incomplete information is expected; useful to flag uncertain cases

### 5. Batch Processing
- **Decision**: Support batch processing of transactions
- **Rationale**: Large CSV files require efficient processing; avoid memory issues

### 6. Extensibility
- **Decision**: Modular tool design with clear interfaces
- **Rationale**: Easy to add new fee types, payment methods, or contract rules

---

## 9. Agent Prompt Template

```markdown
You are a transaction fee verification agent. Your task is to verify that transaction fees
charged match the contractual terms in the parsed_contract.json file.

You have access to the following tools: [list of tools]

For each transaction, you must:
1. Identify the transaction characteristics (currency, payment method, region, type)
2. Find the applicable contract rule(s)
3. Calculate the expected fees
4. Compare with actual fees charged
5. If there's a discrepancy, provide:
   - Clear reasoning for why fees don't match
   - Your assumptions about ambiguous fields
   - A confidence score (0.0 - 1.0) for your determination

Important considerations:
- Field names may vary (e.g., "commission" vs "comission" vs "fee")
- Payment methods may need to be inferred from multiple fields
- Some fee structures are tiered based on monthly volume
- Handle missing or incomplete data gracefully
- When unsure, provide your best analysis with a lower confidence score

Output format for discrepancies: [structured JSON format]
```

---

## 10. Next Steps

1. **Implement Core Tools** (Priority 1)
   - Data loaders
   - Fee calculators
   - Field mapper

2. **Build Agent Orchestrator** (Priority 1)
   - Tool calling logic
   - Decision flow
   - Error handling

3. **Implement Confidence Scoring** (Priority 2)
   - Scoring algorithm
   - Assumption tracking

4. **Add Advanced Features** (Priority 3)
   - Tiered fee handling
   - Monthly volume tracking
   - Chargeback metrics

5. **Testing & Validation** (Priority 1)
   - Unit tests for each tool
   - Integration tests
   - Sample transaction validation

6. **Documentation** (Priority 2)
   - API documentation
   - Usage examples
   - Troubleshooting guide
