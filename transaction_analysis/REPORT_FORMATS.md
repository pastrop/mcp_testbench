# Report Output Formats

The Transaction Fee Verification Agent generates two report formats for every analysis run.

## Output Files

When you run the agent, it automatically generates both:

1. **JSON Report** (structured data)
   - File: `output/discrepancy_report.json`
   - Use for: programmatic processing, APIs, databases

2. **Text Report** (human-readable)
   - File: `output/discrepancy_report.txt`
   - Use for: reading, sharing, documentation

## JSON Report Format

The JSON report contains structured data optimized for machine processing:

```json
{
  "summary": {
    "total_discrepancies": 5,
    "total_discrepancy_amount": -2.53
  },
  "discrepancies": [
    {
      "transaction_id": "dd523aac-9bdf-429e-829e-7961316306bc",
      "status": "UNDERCHARGED",
      "actual_commission": 5.0,
      "expected_commission": 5.1028,
      "discrepancy": -0.1028,
      "discrepancy_percentage": -2.01,
      "amount": 510.28,
      "currency": "EUR",
      "payment_method": "card",
      "reasoning": "...",
      "assumptions": [...],
      "confidence": 0.85,
      "confidence_reasoning": "...",
      "expected_breakdown": {...},
      "contract_rule_applied": {...}
    }
  ]
}
```

## Text Report Format

The text report provides a human-readable format with clear sections:

### Executive Summary
- Total discrepancies found
- Total discrepancy amount
- Breakdown by type (overcharged/undercharged/errors)

### Individual Discrepancy Details
For each discrepancy:

**STATUS**
- OVERCHARGED: Fee higher than expected
- UNDERCHARGED: Fee lower than expected
- ERROR: Could not be analyzed

**TRANSACTION DETAILS**
- Amount, currency, payment method
- Card brand (if applicable)
- Region/country
- Transaction date

**FINANCIAL DISCREPANCY**
```
Metric                                      Amount (EUR)
---------------------------------------- ---------------
Actual Commission Charged                €         10.50
Expected Commission                      €          9.25
Discrepancy                              €          1.25
Discrepancy Percentage                            13.51%
```

**EXPECTED FEE BREAKDOWN**
- Percentage fee calculation
- Fixed fee
- Total expected

**ANALYSIS**
Detailed reasoning about why this is a discrepancy

**ASSUMPTIONS MADE**
- List of assumptions and inferences
- How ambiguous data was interpreted

**CONFIDENCE LEVEL**
- Percentage (0-100%)
- Category (High/Medium/Low)
- Reasoning for confidence level

**CONTRACT RULE APPLIED**
- Category (card_fees, apm_fees, etc.)
- Specific rule used
- Rate and fixed fee

**RECOMMENDATIONS**
Action items based on discrepancy type

### Overall Recommendations
Summary of all findings with recommendations

## Usage

```bash
# Run the agent (generates both reports)
python main.py --max-transactions 10

# View JSON report
cat output/discrepancy_report.json

# View text report
cat output/discrepancy_report.txt

# Or use less for better reading
less output/discrepancy_report.txt
```

## Custom Output Location

```bash
# Specify custom output path (generates both .json and .txt)
python main.py --output my_reports/analysis.json

# This creates:
#   - my_reports/analysis.json (JSON format)
#   - my_reports/analysis.txt (text format)
```

## Example Use Cases

### JSON Report Use Cases
- Import into spreadsheet/database
- Process with scripts
- Send to APIs
- Generate charts/graphs
- Automated analysis pipelines

### Text Report Use Cases
- Share with stakeholders
- Include in documentation
- Email to finance team
- Review in terminal
- Print for meetings

## Report Features

Both formats include:
- ✓ All discrepancies found
- ✓ Detailed reasoning
- ✓ Assumptions and confidence scores
- ✓ Financial calculations
- ✓ Contract rule matching
- ✓ Actionable recommendations
- ✓ Timestamp of generation

## Viewing Tips

**JSON Report:**
```bash
# Pretty print
cat output/discrepancy_report.json | python -m json.tool

# Search for specific transaction
jq '.discrepancies[] | select(.transaction_id == "test-123")' output/discrepancy_report.json
```

**Text Report:**
```bash
# View with pagination
less output/discrepancy_report.txt

# Search for specific content
grep -n "OVERCHARGED" output/discrepancy_report.txt

# Count discrepancies
grep -c "DISCREPANCY #" output/discrepancy_report.txt
```

## Integration

Both reports are generated automatically by the `export_results()` method in `agent/core.py`:

```python
# In your code
agent = TransactionVerificationAgent(api_key, contract_file)
discrepancies = agent.run(transaction_file)
agent.export_results("output/report.json")  # Generates both .json and .txt
```

## Sample Output

See `output/test_report.txt` for a sample text report generated from test data.
