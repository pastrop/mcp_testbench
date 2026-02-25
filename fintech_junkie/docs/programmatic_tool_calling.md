# Programmatic Tool Calling Design Document

## Overview

This document describes the implementation of programmatic tool calling for combined contract and transaction analysis in the Financial Analysis Agentic System.

## Problem Statement

Users frequently need to compare contractual fee rates with actual transaction fees. For example:

> "Give me the contractual transaction fee rate for vendor X and tell me what transaction fees are charged according to the vendor X transaction table"

This query requires:
1. Looking up the contract to get the agreed-upon rates
2. Analyzing the transaction table to find actual applied rates
3. Comparing the two and highlighting any discrepancies

The existing system handled these as separate query categories, requiring users to make two separate requests.

## Solution: Programmatic Tool Calling with Tool Runner

We implemented the **Anthropic Tool Runner** pattern, which allows Claude to:
1. Receive all available tools in a single request
2. Decide which tools to call (potentially in parallel)
3. Automatically handle the agentic loop of tool calls and results
4. Synthesize a final response comparing both data sources

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              User Query                                     │
│  "Get contractual fee for Vendor X and compare with transaction table"      │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Query Classifier                                    │
│              Detects: COMBINED_ANALYSIS category                            │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                    Programmatic Agent (Tool Runner)                         │
│  ─────────────────────────────────────────────────────────────────────────  │
│  Tools provided:                                                            │
│    • lookup_contract                                                        │
│    • find_transaction_file                                                  │
│    • inspect_table                                                          │
│    • analyze_transactions_sorting                                           │
│    • analyze_transactions_kmeans                                            │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                    ┌─────────────────┴─────────────────┐
                    │   Claude decides tool calls       │
                    │   (can be PARALLEL)               │
                    └─────────────────┬─────────────────┘
                                      │
              ┌───────────────────────┼───────────────────────┐
              │                       │                       │
              ▼                       ▼                       ▼
   ┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐
   │  lookup_contract │    │   inspect_table  │    │ find_txn_file    │
   │  (PARALLEL)      │    │   (PARALLEL)     │    │ (if needed)      │
   └──────────────────┘    └──────────────────┘    └──────────────────┘
              │                       │
              │                       ▼
              │            ┌──────────────────────────┐
              │            │  analyze_transactions_*  │
              │            │  (based on inspect       │
              │            │   recommendation)        │
              │            └──────────────────────────┘
              │                       │
              └───────────┬───────────┘
                          ▼
   ┌─────────────────────────────────────────────────────────────────────────┐
   │                        Claude Analysis                                  │
   │  ─────────────────────────────────────────────────────────────────────  │
   │  • Contractual rate from lookup_contract: X%                            │
   │  • Actual rates from analyze_transactions: [Y%, Z%, ...]                │
   │  • Comparison: "Rates match" or "Discrepancy found"                     │
   └─────────────────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                          Final Response to User                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Implementation Details

### Files Changed/Created

1. **`src/agent/programmatic_agent.py`** (NEW)
   - Defines tools using `@beta_tool` decorator
   - Implements `run_combined_analysis()` using Tool Runner
   - Provides streaming variant `run_combined_analysis_streaming()`

2. **`src/agent/classifier.py`** (UPDATED)
   - Added `COMBINED_ANALYSIS` category
   - Updated classification prompt to detect combined queries

3. **`src/agent/conversation.py`** (UPDATED)
   - Added `handle_combined_query()` method
   - Routes `COMBINED_ANALYSIS` queries to programmatic agent

### Tool Definitions

All tools are defined using the `@beta_tool` decorator which extracts JSON schema from Python type hints and docstrings:

```python
@beta_tool
def lookup_contract(query: str, extract_financial_terms: bool = True) -> str:
    """Look up contractual fee rates for a vendor from the contracts database.

    Args:
        query: The vendor name or contract identifier to search for
        extract_financial_terms: Whether to extract rates, fees, reserves

    Returns:
        JSON string with contract info and financial terms
    """
    # Implementation wraps existing contract_lookup module
```

### Tool Runner Usage

```python
runner = client.beta.messages.tool_runner(
    model="claude-sonnet-4-5-20250929",
    max_tokens=4096,
    system=COMBINED_ANALYSIS_SYSTEM_PROMPT,
    tools=[lookup_contract, find_transaction_file, inspect_table, ...],
    messages=[{"role": "user", "content": user_query}],
)

# Iterate through the agentic loop
for message in runner:
    # Tool calls are handled automatically
    pass

# Get final response
final_message = runner.until_done()
```

### Parallel Execution

The system prompt instructs Claude to call independent tools in parallel:

```
When users ask about vendor fees, you should:
1. Look up contractual rates using the lookup_contract tool
2. Analyze actual transaction data using inspect_table first
3. Then use the appropriate analysis tool based on inspection results
4. Compare the contractual rates with the actual rates

You CAN and SHOULD call multiple tools in parallel when they are independent
(e.g., lookup_contract and inspect_table can run simultaneously)
```

## Query Classification

The classifier now detects combined queries:

```
COMBINED_ANALYSIS - User wants BOTH contract information AND transaction analysis
Examples:
- "Give me the contractual fee for vendor X and compare with their transactions"
- "What's the contractual rate for Blogwizarro and what rates are in their transaction table?"
- "Compare the contract rates with actual transaction fees for codedtea"
```

## Benefits

1. **Parallel Execution**: `lookup_contract` and `inspect_table` run simultaneously
2. **Intelligent Orchestration**: Claude decides which algorithm to use based on `inspect_table` results
3. **Natural Comparison**: Claude synthesizes results into coherent analysis
4. **Reuses Existing Code**: Wraps existing tool implementations
5. **Automatic Loop**: Tool Runner handles the back-and-forth automatically

## Example Execution

Query: "Give me the contractual transaction fee rate for BLOGWIZARRO LTD and tell me what fees are in their transaction table"

**Step 1**: Claude calls tools in parallel:
- `lookup_contract(query="BLOGWIZARRO LTD")`
- `find_transaction_file(vendor_name="BLOGWIZARRO")`

**Step 2**: After finding the file, Claude calls:
- `inspect_table(file_path="data/BLOGWIZARRO_LTD_acquiring_monthly-202511.xlsx")`

**Step 3**: Based on inspection (constant commission detected), Claude synthesizes:

```
Based on my analysis:

**Contractual Rate (from contract):**
- Transaction fee: 2.5%
- Rolling reserve: 10%

**Actual Fees (from transaction table):**
- The transaction table shows a constant commission of €5.0 per transaction
- This appears to be a flat fee rather than a percentage-based rate

**Analysis:**
There is a discrepancy between the contractual percentage rate (2.5%)
and the actual flat fee (€5.0) in the transaction data...
```

## Testing

Run the programmatic agent directly:

```bash
cd /path/to/fintech_junkie
python -m src.agent.programmatic_agent
```

Or through the main conversation agent:

```bash
python -m src.agent.conversation
> Give me the contractual fee for BLOGWIZARRO and compare with their transactions
```

## Future Enhancements

1. **Streaming Output**: Use `run_combined_analysis_streaming()` for real-time response display
2. **Caching**: Cache tool results to avoid redundant API calls
3. **Error Recovery**: Implement retry logic for transient failures
4. **Multiple Vendors**: Support comparing multiple vendors in a single query
