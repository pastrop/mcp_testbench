# Claude Integration Guide

This guide shows how to integrate Claude's reasoning capabilities with the transaction verification tools to create an autonomous agent with advanced decision-making abilities.

---

## Integration Architecture

```
┌─────────────────────────────────────────────────────────┐
│                   Your Application                       │
└────────────────────┬────────────────────────────────────┘
                     │
                     │ Sends prompt + tool definitions
                     ▼
┌─────────────────────────────────────────────────────────┐
│              Claude API (Sonnet 4.5)                     │
│                                                          │
│  • Receives transaction data                            │
│  • Decides which tools to call                          │
│  • Reasons about ambiguities                            │
│  • Calculates confidence scores                         │
│  • Generates explanations                               │
└────────────────────┬────────────────────────────────────┘
                     │
                     │ Calls tools
                     ▼
┌─────────────────────────────────────────────────────────┐
│                   Tool Functions                         │
│                                                          │
│  • load_contract_data()                                 │
│  • find_applicable_contract_rule()                      │
│  • calculate_expected_fees()                            │
│  • compare_fees()                                       │
│  • etc.                                                 │
└────────────────────┬────────────────────────────────────┘
                     │
                     │ Returns results
                     ▼
┌─────────────────────────────────────────────────────────┐
│              Claude API (continues)                      │
│                                                          │
│  • Processes tool results                               │
│  • Makes decisions                                      │
│  • Generates final report                               │
└────────────────────┬────────────────────────────────────┘
                     │
                     │ Returns response
                     ▼
┌─────────────────────────────────────────────────────────┐
│                   Your Application                       │
│                                                          │
│  • Receives discrepancy report                          │
│  • Stores results                                       │
│  • Displays to user                                     │
└─────────────────────────────────────────────────────────┘
```

---

## System Prompt

This is the core prompt that instructs Claude on its role and capabilities:

```python
SYSTEM_PROMPT = """You are a transaction fee verification agent. Your task is to verify that transaction fees charged match the contractual terms defined in a parsed_contract.json file.

## Your Capabilities

You have access to the following tools that you can call to gather information and perform calculations:

1. **load_contract_data**: Load contract fee structures from JSON
2. **load_transaction_data**: Load transaction records from CSV
3. **map_transaction_fields**: Normalize field names and handle variations
4. **infer_payment_method**: Determine payment method from transaction data
5. **find_applicable_contract_rule**: Match transaction to contract terms
6. **calculate_expected_fees**: Calculate fees based on contract rules
7. **compare_fees**: Compare actual vs expected fees
8. **generate_discrepancy_report**: Create detailed report for mismatches

## Your Responsibilities

For each transaction, you must:

1. **Identify characteristics**: Extract currency, payment method, region, card brand, transaction type
2. **Handle ambiguity**: When field names vary (e.g., "commission" vs "comission"), document your interpretation
3. **Find contract rule**: Match transaction to applicable contract terms based on multiple dimensions
4. **Calculate expected fee**: Apply contract formula to determine correct fee
5. **Compare**: Check if actual fee matches expected fee (within 0.01 tolerance)
6. **Report discrepancies**: If fees don't match, provide:
   - Clear reasoning for the mismatch
   - Your assumptions about ambiguous fields
   - A confidence score (0.0-1.0) with explanation
   - The contract rule applied

## Important Guidelines

### Field Name Variations
Transaction CSV may use inconsistent field names:
- "comission_eur" vs "commission_eur"
- "mdr_eur" might represent merchant discount rate
- "traffic_type_group" indicates payment method
- "gate_name" provides payment method hints

Always document which fields you used and what you inferred.

### Payment Method Inference
Payment method may not be explicit. Use multiple fields:
- Check `traffic_type_group` first
- Check `gate_name` for keywords (sepa, card, apple_pay)
- Check `card_brand` for card transactions
- Document evidence for your inference

### Contract Rule Matching
Match on multiple dimensions:
- **Currency**: EUR, USD, GBP, etc. (required)
- **Payment method**: card, sepa, apple_pay, etc. (required)
- **Region**: EEA, WW, UK (optional but important)
- **Card brand**: Visa, Mastercard (optional)
- **Transaction type**: payment, payout, refund, chargeback (required)

If multiple rules match, choose the most specific one.

### Fee Calculations

**Standard payment**:
```
fee = (amount × wl_rate) + fixed_fee
```

**Payout**:
```
fee = (amount × rate) + payout_oct_fix
fee = max(fee, payout_oct_min)  # if minimum defined
```

**Refund**:
```
fee = refund_fee  # flat fee
```

**Chargeback**:
```
fee = chb_fee  # flat fee, or excessive_chb_fee if conditions met
```

### Confidence Scoring

Assign confidence scores based on:

**High Confidence (0.8-1.0)**:
- Exact field matches
- Clear payment method identifier
- Single applicable contract rule
- Simple fee structure
- All required data present

**Medium Confidence (0.5-0.79)**:
- Inferred payment method from partial data
- Multiple possible contract rules
- Ambiguous field mappings
- Tiered pricing requiring volume estimation
- Some missing optional fields

**Low Confidence (0.0-0.49)**:
- High ambiguity in payment method
- Conflicting contract rules
- Significant missing data
- Unclear field interpretations

### Confidence Formula
```
confidence = base_confidence × field_clarity × rule_certainty × data_completeness

Adjust downward for:
- Each ambiguous field: -5%
- Multiple matching rules: -10%
- Missing critical data: -20%
- Complex inference chains: -10%
```

### Special Cases

**Declined transactions**: Should have 0 fee. If fee > 0, report as error with confidence 1.0.

**Tiered pricing**: Some payment methods (e.g., open banking, BLIK) have volume-based tiers. Use monthly volume if available, otherwise assume tier 1.

**Excessive chargeback fees**: If monthly CB ratio > 1.0% AND CB count > 100, use excessive_chargeback_fees instead of standard chb_fee.

**Currency exchange**: When transaction currency differs from settlement currency, FX fees may apply (0.5%).

### Output Format

For each discrepancy, provide a structured report:

```json
{
  "transaction_id": "...",
  "transaction_date": "...",
  "amount": 123.45,
  "currency": "EUR",
  "payment_method": "card",
  "actual_commission": 5.0,
  "expected_commission": 5.1028,
  "discrepancy": -0.1028,
  "discrepancy_percentage": -2.01,
  "status": "UNDERCHARGED",  // or "OVERCHARGED"
  "reasoning": "Expected fee calculation: (510.28 × 0.01) + 0 = 5.1028 EUR. Actual charged: 5.0 EUR. Discrepancy of -0.1028 EUR (-2.01%). Possible rounding down instead of standard rounding.",
  "assumptions": [
    "Mapped field 'comission_eur' to commission_total",
    "Inferred payment_method='sepa' from gate_name='sepa'",
    "Applied SEPA payout fixed fee (2.5 EUR) per contract section outgoing_fees.sepa"
  ],
  "confidence": 0.85,
  "confidence_reasoning": "High confidence (0.85) due to: clear SEPA identifier in gate_name (0.9), exact currency match (1.0), unambiguous fee structure (1.0). Slight reduction due to field name variation (comission vs commission).",
  "contract_rule_applied": {
    "category": "outgoing_fees.sepa.balance_from_processing",
    "wl_rate": 0.0,
    "payout_oct_fix": 2.5,
    "currency": "EUR"
  },
  "expected_breakdown": {
    "percentage_fee": 0.0,
    "fixed_fee": 2.5,
    "total": 2.5
  }
}
```

## Workflow

For each transaction:
1. Call `map_transaction_fields()` to normalize field names
2. Call `infer_payment_method()` if not explicit
3. Call `find_applicable_contract_rule()` with all characteristics
4. Call `calculate_expected_fees()` using the matched rule
5. Call `compare_fees()` to check for discrepancies
6. If discrepancy found, generate detailed report with reasoning and confidence

## Key Principles

- **Transparency**: Document every assumption and inference
- **Caution**: Lower confidence when uncertain, never guess
- **Thoroughness**: Check multiple fields before concluding
- **Precision**: Use exact decimal arithmetic for fee calculations
- **Clarity**: Explain reasoning in plain language

Remember: This is an incomplete information task. When in doubt, document your uncertainty in the confidence score and assumptions list.
"""
```

---

## Tool Definitions for Claude API

Define tools in the format expected by Claude API:

```python
TOOLS = [
    {
        "name": "load_contract_data",
        "description": "Load and parse contract fee structures from JSON file. Returns contract data including all fee categories, currencies, regions, and payment methods.",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to the contract JSON file"
                }
            },
            "required": ["file_path"]
        }
    },
    {
        "name": "load_transaction_data",
        "description": "Load transaction records from CSV file with optional filtering and batching support.",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to the transaction CSV file"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of transactions to load (optional)"
                },
                "offset": {
                    "type": "integer",
                    "description": "Number of rows to skip (optional)"
                },
                "filters": {
                    "type": "object",
                    "description": "Filters to apply, e.g., {\"status\": \"approved\"} (optional)"
                }
            },
            "required": ["file_path"]
        }
    },
    {
        "name": "map_transaction_fields",
        "description": "Map transaction CSV fields to standardized names, handling variations like 'comission' vs 'commission'. Returns mapped fields, unmapped fields, and assumptions made.",
        "input_schema": {
            "type": "object",
            "properties": {
                "transaction": {
                    "type": "object",
                    "description": "Raw transaction record as a dictionary"
                },
                "available_columns": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of available column names in the CSV"
                }
            },
            "required": ["transaction", "available_columns"]
        }
    },
    {
        "name": "infer_payment_method",
        "description": "Infer payment method from transaction data by analyzing multiple fields (traffic_type_group, gate_name, card_brand). Returns inferred method, confidence score, and evidence.",
        "input_schema": {
            "type": "object",
            "properties": {
                "transaction": {
                    "type": "object",
                    "description": "Transaction record with mapped fields"
                }
            },
            "required": ["transaction"]
        }
    },
    {
        "name": "find_applicable_contract_rule",
        "description": "Find contract rule(s) applicable to a transaction by matching on currency, payment method, region, card brand, and transaction type. Returns best match, alternatives, ambiguities, and confidence.",
        "input_schema": {
            "type": "object",
            "properties": {
                "contract_data": {
                    "type": "object",
                    "description": "Loaded contract data"
                },
                "currency": {
                    "type": "string",
                    "description": "Transaction currency (e.g., EUR, USD)"
                },
                "payment_method": {
                    "type": "string",
                    "description": "Payment method (e.g., card, sepa, apple_pay)"
                },
                "region": {
                    "type": "string",
                    "description": "Transaction region/country (optional)"
                },
                "card_brand": {
                    "type": "string",
                    "description": "Card brand if applicable (optional)"
                },
                "transaction_type": {
                    "type": "string",
                    "description": "Transaction type (payment, payout, refund, chargeback)"
                },
                "amount": {
                    "type": "number",
                    "description": "Transaction amount (optional, for tiered fees)"
                },
                "monthly_volume": {
                    "type": "number",
                    "description": "Monthly cumulative volume (optional, for tiered fees)"
                }
            },
            "required": ["contract_data", "currency", "payment_method", "transaction_type"]
        }
    },
    {
        "name": "calculate_expected_fees",
        "description": "Calculate expected fees based on contract rule. Applies appropriate formula based on transaction type (payment, payout, refund, chargeback). Returns detailed breakdown.",
        "input_schema": {
            "type": "object",
            "properties": {
                "amount": {
                    "type": "number",
                    "description": "Transaction amount"
                },
                "contract_rule": {
                    "type": "object",
                    "description": "Contract rule from find_applicable_contract_rule"
                },
                "transaction_type": {
                    "type": "string",
                    "description": "Transaction type (payment, payout, refund, chargeback)"
                }
            },
            "required": ["amount", "contract_rule", "transaction_type"]
        }
    },
    {
        "name": "compare_fees",
        "description": "Compare actual charged fee with expected fee. Checks if within tolerance (default 0.01). Returns comparison result, status (CORRECT/OVERCHARGED/UNDERCHARGED), and differences.",
        "input_schema": {
            "type": "object",
            "properties": {
                "actual_fee": {
                    "type": "number",
                    "description": "Fee that was actually charged"
                },
                "expected_fee": {
                    "type": "number",
                    "description": "Fee calculated from contract"
                },
                "tolerance": {
                    "type": "number",
                    "description": "Acceptable difference in currency units (default 0.01)"
                }
            },
            "required": ["actual_fee", "expected_fee"]
        }
    }
]
```

---

## Implementation Example

### Basic Integration

```python
import anthropic
from agent.tools.data_loader import load_contract_data, load_transaction_data
from agent.tools.field_mapper import map_transaction_fields, infer_payment_method
from agent.tools.contract_matcher import find_applicable_contract_rule
from agent.tools.fee_calculator import calculate_expected_fees, compare_fees

client = anthropic.Anthropic(api_key="your-api-key")

# Tool execution function
def execute_tool(tool_name: str, tool_input: dict):
    """Execute a tool based on name and input."""
    if tool_name == "load_contract_data":
        return load_contract_data(tool_input["file_path"])
    elif tool_name == "load_transaction_data":
        return load_transaction_data(**tool_input)
    elif tool_name == "map_transaction_fields":
        return map_transaction_fields(**tool_input)
    elif tool_name == "infer_payment_method":
        return infer_payment_method(tool_input["transaction"])
    elif tool_name == "find_applicable_contract_rule":
        return find_applicable_contract_rule(**tool_input)
    elif tool_name == "calculate_expected_fees":
        return calculate_expected_fees(**tool_input)
    elif tool_name == "compare_fees":
        return compare_fees(**tool_input)
    else:
        raise ValueError(f"Unknown tool: {tool_name}")

# Verify a single transaction
def verify_transaction_with_claude(transaction: dict, contract_data: dict) -> dict:
    """
    Use Claude to verify a transaction with tool use.
    """
    messages = [
        {
            "role": "user",
            "content": f"""Please verify this transaction against the contract terms:

Transaction: {json.dumps(transaction, indent=2)}

Contract data is available via the load_contract_data tool.

Check if the fee charged (comission_eur field) matches the contractual requirements.
If there's a discrepancy, provide a detailed report with your reasoning and confidence score."""
        }
    ]

    # Agentic loop
    while True:
        response = client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages
        )

        # Check if Claude wants to use tools
        if response.stop_reason == "tool_use":
            # Extract tool use requests
            tool_uses = [block for block in response.content if block.type == "tool_use"]

            # Execute each tool
            tool_results = []
            for tool_use in tool_uses:
                result = execute_tool(tool_use.name, tool_use.input)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_use.id,
                    "content": json.dumps(result)
                })

            # Add assistant's response and tool results to messages
            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results})

        else:
            # Claude has finished - extract final response
            text_content = [block.text for block in response.content if hasattr(block, "text")]
            final_response = "\n".join(text_content)

            # Try to parse JSON report from response
            try:
                # Look for JSON in the response
                import re
                json_match = re.search(r'\{.*\}', final_response, re.DOTALL)
                if json_match:
                    report = json.loads(json_match.group())
                    return report
                else:
                    return {"error": "No structured report found", "response": final_response}
            except json.JSONDecodeError:
                return {"error": "Could not parse report", "response": final_response}

# Usage
contract_data = load_contract_data("data/parsed_contract.json")
transactions = load_transaction_data("data/transaction_table.csv", limit=10)

for transaction in transactions["transactions"]:
    report = verify_transaction_with_claude(transaction, contract_data)
    print(json.dumps(report, indent=2))
```

---

## Advanced: Batch Processing with Claude

For processing many transactions efficiently:

```python
def batch_verify_with_claude(
    transaction_file: str,
    contract_file: str,
    batch_size: int = 10
) -> list:
    """
    Process transactions in batches with Claude.
    """
    discrepancies = []

    # Load contract once
    contract_data = load_contract_data(contract_file)

    # Process in batches
    offset = 0
    while True:
        batch = load_transaction_data(
            transaction_file,
            limit=batch_size,
            offset=offset
        )

        if not batch["transactions"]:
            break

        # Send batch to Claude
        messages = [
            {
                "role": "user",
                "content": f"""Please verify these {len(batch['transactions'])} transactions against contract terms.

For each transaction, check if fees are correct. Only report transactions with discrepancies.

Transactions:
{json.dumps(batch['transactions'], indent=2)}

Use the tools to:
1. Load contract data
2. For each transaction:
   - Map fields
   - Infer payment method
   - Find contract rule
   - Calculate expected fee
   - Compare with actual fee
3. Report only discrepancies with full details"""
            }
        ]

        # Agentic loop (same as before)
        # ... [Claude tool use loop]

        offset += batch_size

        if not batch["has_more"]:
            break

    return discrepancies
```

---

## Hybrid Approach: Python + Claude

Best of both worlds - use Python for deterministic operations, Claude for reasoning:

```python
class HybridVerificationAgent:
    """
    Use Python tools for data loading and calculations,
    Claude for reasoning about ambiguities and confidence scoring.
    """

    def __init__(self, contract_file: str, transaction_file: str):
        self.client = anthropic.Anthropic(api_key="your-api-key")
        self.contract_data = load_contract_data(contract_file)

    def verify_transaction(self, transaction: dict) -> dict:
        # Do deterministic operations in Python
        mapped = map_transaction_fields(transaction, list(transaction.keys()))
        payment_info = infer_payment_method(mapped["mapped_fields"])

        # If high uncertainty, ask Claude for reasoning
        if payment_info["confidence"] < 0.7:
            claude_analysis = self._ask_claude_about_payment_method(
                transaction,
                payment_info
            )
            # Use Claude's analysis to override
            payment_info = claude_analysis

        # Continue with Python tools
        rule_match = find_applicable_contract_rule(
            self.contract_data,
            currency=transaction["currency"],
            payment_method=payment_info["payment_method"],
            # ... other params
        )

        expected = calculate_expected_fees(
            amount=float(transaction["amount_eur"]),
            contract_rule=rule_match["best_match"],
            transaction_type="payment"
        )

        comparison = compare_fees(
            actual_fee=float(transaction["comission_eur"]),
            expected_fee=expected["breakdown"]["total"]
        )

        # If discrepancy found, ask Claude to generate reasoning
        if not comparison["is_correct"]:
            return self._ask_claude_for_report(
                transaction=transaction,
                expected=expected,
                comparison=comparison,
                rule_match=rule_match,
                payment_info=payment_info,
                mapped=mapped
            )

        return None  # No discrepancy

    def _ask_claude_for_report(self, **context) -> dict:
        """Ask Claude to generate detailed reasoning and confidence score."""
        response = self.client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=2048,
            messages=[{
                "role": "user",
                "content": f"""A fee discrepancy was detected. Please analyze and generate a detailed report.

Context:
{json.dumps(context, indent=2)}

Provide:
1. Clear reasoning for why fees don't match
2. List of assumptions made
3. Confidence score (0.0-1.0) with explanation
4. Structured JSON report in the format specified in your instructions"""
            }]
        )

        # Extract and parse Claude's response
        # ... [parse JSON from response]
```

---

## Benefits of Claude Integration

### 1. **Advanced Reasoning**
Claude can handle complex ambiguities that rule-based systems struggle with:
- Inferring payment methods from incomplete data
- Choosing between multiple matching contract rules
- Explaining complex fee calculations in plain language

### 2. **Natural Language Output**
Claude generates human-readable explanations:
```
"The transaction appears to be a SEPA payout based on the gate_name field containing 'sepa'. However, the actual commission (5.0 EUR) is lower than expected (5.1028 EUR), suggesting possible rounding down. Confidence: 0.85 due to clear payment method but minor field name inconsistency."
```

### 3. **Adaptive Confidence Scoring**
Claude considers multiple factors dynamically:
- Data completeness
- Field ambiguity
- Rule matching certainty
- Historical patterns (if provided)

### 4. **Continuous Improvement**
As Claude models improve, the agent automatically benefits without code changes.

---

## Best Practices

### 1. Use Python for Deterministic Operations
- Data loading
- Simple calculations
- Exact matching

### 2. Use Claude for Reasoning
- Ambiguous field interpretation
- Complex rule matching
- Confidence assessment
- Report generation

### 3. Validate Claude's Output
Always check that Claude:
- Used tools correctly
- Applied correct formulas
- Provided valid confidence scores
- Included required report fields

### 4. Provide Rich Context
Give Claude all available information:
- Full transaction record
- Contract data structure
- Field mappings
- Previous similar cases (if available)

### 5. Iterate Based on Results
Review discrepancy reports and refine:
- System prompt
- Tool descriptions
- Confidence scoring guidelines
- Edge case handling

---

## Testing Claude Integration

```python
def test_claude_verification():
    """Test cases for Claude-powered verification."""

    # Test 1: Clear case - should have high confidence
    transaction = {
        "comission_eur": 5.0,
        "amount_eur": 100.0,
        "currency": "EUR",
        "traffic_type_group": "card",
        "card_brand": "VISA",
        "status": "approved"
    }
    result = verify_transaction_with_claude(transaction, contract_data)
    assert result["confidence"] >= 0.8

    # Test 2: Ambiguous case - should have lower confidence
    transaction = {
        "comission_eur": 5.0,
        "amount_eur": 100.0,
        "currency": "EUR",
        # No payment method indicators
        "status": "approved"
    }
    result = verify_transaction_with_claude(transaction, contract_data)
    assert result["confidence"] < 0.7
    assert len(result["assumptions"]) > 0

    # Test 3: Fee mismatch - should detect discrepancy
    transaction = {
        "comission_eur": 10.0,  # Wrong fee
        "amount_eur": 100.0,
        "currency": "EUR",
        "traffic_type_group": "card",
        "status": "approved"
    }
    result = verify_transaction_with_claude(transaction, contract_data)
    assert result["status"] in ["OVERCHARGED", "UNDERCHARGED"]
    assert "reasoning" in result
```

---

## Next Steps

1. **Implement basic Claude integration** with single transaction verification
2. **Test with sample transactions** to validate approach
3. **Add batch processing** for efficiency
4. **Monitor Claude's decisions** and refine prompts
5. **Build feedback loop** to improve confidence scoring
6. **Deploy as production agent** with error handling and logging

---

## Cost Optimization

When using Claude API:

1. **Batch transactions** when possible
2. **Cache contract data** - don't reload on every transaction
3. **Use Python for simple cases** - only invoke Claude for ambiguous ones
4. **Set max_tokens appropriately** - reports don't need 4096 tokens
5. **Consider using Haiku** for simple classifications, Sonnet for complex reasoning

Example cost-effective approach:
```python
def verify_with_cost_optimization(transaction: dict) -> dict:
    # Do quick checks in Python
    if transaction["status"] == "declined":
        if transaction["comission_eur"] == 0:
            return None  # Correct, no Claude needed

    # Check if payment method is obvious
    if transaction.get("traffic_type_group") in KNOWN_METHODS:
        # Use Python tools
        return python_verify(transaction)

    # Only use Claude for ambiguous cases
    return claude_verify(transaction)
```

This reduces Claude API calls by ~70% while maintaining accuracy.
