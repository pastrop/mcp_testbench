# Project Structure

```
transaction_analysis/
│
├── agent/                          # Main agent package
│   ├── __init__.py
│   ├── core.py                     # Agent orchestrator with Claude API
│   └── tools/                      # Tool implementations
│       ├── __init__.py
│       ├── data_loader.py          # Load contract and transaction data
│       ├── field_mapper.py         # Field mapping and payment method inference
│       ├── contract_matcher.py     # Contract rule matching
│       └── fee_calculator.py       # Fee calculations and comparisons
│
├── data/                           # Input data files
│   ├── parsed_contract.json        # Contract fee structures
│   └── transaction_table.csv       # Transaction records
│
├── output/                         # Generated reports (created at runtime)
│   └── discrepancy_report.json     # Verification results
│
├── main.py                         # CLI entry point
├── requirements.txt                # Python dependencies
│
├── .env.example                    # Environment variables template
├── .gitignore                      # Git ignore rules
│
├── QUICKSTART.md                   # This file - Quick start guide
├── README.md                       # Project overview
├── ARCHITECTURE.md                 # Detailed system design
├── IMPLEMENTATION_GUIDE.md         # Code examples and patterns
├── AGENT_TOOL_ARCHITECTURE.md      # Agent-tool interaction patterns
├── SEMANTIC_MAPPING.md             # Semantic field mapping with Claude
└── CLAUDE_INTEGRATION.md           # Claude API integration guide
```

## Component Descriptions

### Core Agent (`agent/core.py`)
- Main orchestrator using Claude's native tool use
- Manages conversation with Claude
- Executes tools based on Claude's decisions
- Generates discrepancy reports

### Tools (`agent/tools/`)

**data_loader.py**
- `load_contract_data()` - Parse contract JSON
- `load_transaction_data()` - Load transactions from CSV
- `get_transaction_batch()` - Batch processing support

**field_mapper.py**
- `map_transaction_fields()` - Normalize field names
- `infer_payment_method()` - Infer payment method from transaction
- `extract_transaction_characteristics()` - Extract all characteristics

**contract_matcher.py**
- `find_applicable_contract_rule()` - Match transaction to contract rule
- Multi-dimensional matching (currency, region, payment method, etc.)

**fee_calculator.py**
- `calculate_expected_fees()` - Calculate fees per contract
- `compare_fees()` - Compare actual vs expected
- `calculate_confidence_score()` - Calculate overall confidence

### CLI (`main.py`)
- Command-line interface
- Argument parsing
- Progress reporting
- Error handling

## Data Flow

```
1. Load Contract
   └─> load_contract_data()
        └─> Returns: contract_data dict

2. Load Transaction Batch
   └─> load_transaction_data()
        └─> Returns: list of transactions

3. For Each Transaction:
   │
   ├─> Extract Characteristics
   │   └─> extract_transaction_characteristics()
   │        └─> map_transaction_fields()
   │        └─> infer_payment_method()
   │
   ├─> Find Contract Rule
   │   └─> find_applicable_contract_rule()
   │        └─> Returns: best_match rule + confidence
   │
   ├─> Calculate Expected Fee
   │   └─> calculate_expected_fees()
   │        └─> Returns: fee breakdown
   │
   ├─> Compare Fees
   │   └─> compare_fees()
   │        └─> Returns: CORRECT/OVERCHARGED/UNDERCHARGED
   │
   └─> If Discrepancy: Generate Report
       └─> Claude provides reasoning + confidence

4. Export Results
   └─> Save to output/discrepancy_report.json
```

## Tool Execution Flow

```
User runs main.py
    │
    ▼
Initialize Agent
    │
    ├─> Load contract_data
    └─> Setup Claude API client
    │
    ▼
For each transaction:
    │
    ├─> Send to Claude with system prompt
    │
    ├─> Claude decides which tools to call
    │   (via tool_use response)
    │
    ├─> Agent executes requested tools
    │   └─> Returns results to Claude
    │
    ├─> Claude processes results
    │   └─> May call more tools or finish
    │
    └─> Claude provides final assessment
        └─> Agent collects discrepancy reports
    │
    ▼
Export all discrepancies to JSON
```

## Key Files by Purpose

### Getting Started
- `QUICKSTART.md` - Start here!
- `main.py` - Run the agent

### Understanding the System
- `ARCHITECTURE.md` - System design
- `AGENT_TOOL_ARCHITECTURE.md` - How agent uses tools

### Implementation Details
- `IMPLEMENTATION_GUIDE.md` - Code examples
- `SEMANTIC_MAPPING.md` - Field mapping with Claude
- `CLAUDE_INTEGRATION.md` - Claude API patterns

### Configuration
- `.env.example` - Environment variables
- `requirements.txt` - Dependencies

## Adding New Tools

To add a new tool:

1. **Implement tool function** in `agent/tools/`
   ```python
   def my_new_tool(param1: str, param2: int) -> Dict:
       """Tool description."""
       # Implementation
       return result
   ```

2. **Add tool schema** in `agent/core.py`
   ```python
   {
       "name": "my_new_tool",
       "description": "What this tool does",
       "input_schema": {
           "type": "object",
           "properties": {
               "param1": {"type": "string"},
               "param2": {"type": "number"}
           },
           "required": ["param1", "param2"]
       }
   }
   ```

3. **Register tool function** in `agent/core.py`
   ```python
   self.tool_functions["my_new_tool"] = my_new_tool
   ```

Claude will automatically learn to use your new tool!

## Testing

```bash
# Test with limited transactions
python main.py --max-transactions 5 --verbose

# Test specific files
python main.py \
  --contract data/parsed_contract.json \
  --transactions data/transaction_table.csv

# Full run
python main.py --batch-size 20
```

## Monitoring

The agent logs:
- INFO: Progress updates
- DEBUG: Tool executions (with --verbose)
- ERROR: Failures and exceptions

Watch logs in real-time:
```bash
python main.py --verbose 2>&1 | tee verification.log
```
