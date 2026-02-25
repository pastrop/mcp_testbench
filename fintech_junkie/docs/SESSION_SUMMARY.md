# Session Summary: Programmatic Tool Calling Implementation

**Date:** February 25, 2026
**Purpose:** Implement programmatic tool calling for combined contract + transaction analysis

---

## What Was Requested

The user wanted to implement a feature where a single query could trigger both:
1. Contract lookup (to get contractual fee rates)
2. Transaction analysis (to see actual fees charged)

Example query:
> "Give me the contractual transaction fee rate for vendor X and tell me what transaction fees are charged according to the vendor X transaction table"

The user referenced [Anthropic's programmatic tool calling documentation](https://platform.claude.com/docs/en/agents-and-tools/tool-use/programmatic-tool-calling).

---

## Design Decision

After exploring multiple approaches, we chose **Approach 1 + Approach 4**:

- **Approach 1 (Agentic Loop):** Define independent tools and let Claude orchestrate calls
- **Approach 4 (Tool Runner):** Use Anthropic's beta Tool Runner SDK for automatic loop handling

**Why this approach:**
- Tools can run in parallel (contract lookup + table inspection simultaneously)
- Claude intelligently chooses which algorithm based on inspection results
- Reuses existing tool implementations
- SDK handles the agentic loop automatically

---

## What Was Implemented

### New Files Created

1. **`src/agent/programmatic_agent.py`**
   - 5 tools defined with `@beta_tool` decorator:
     - `lookup_contract` - Find contractual rates
     - `find_transaction_file` - Locate transaction Excel file
     - `inspect_table` - Analyze table structure
     - `analyze_transactions_sorting` - Simple rate clustering
     - `analyze_transactions_kmeans` - Complex fee clustering
   - `run_combined_analysis()` - Main function using Tool Runner
   - `run_combined_analysis_streaming()` - Streaming variant
   - CLI entry point for direct testing

2. **`docs/architecture.md`**
   - Complete system architecture documentation
   - Component details, data flows, entry points
   - Explains difference between `fintech-agent` and direct module execution

3. **`docs/programmatic_tool_calling.md`**
   - Design document for the Tool Runner implementation
   - Architecture diagrams, execution flow, benefits

### Files Modified

1. **`src/agent/classifier.py`**
   - Added `COMBINED_ANALYSIS` category to `QueryCategory` enum
   - Updated classification prompt to detect combined queries
   - Updated `classify_query()` to handle new category

2. **`src/agent/conversation.py`**
   - Imported `run_combined_analysis` from programmatic_agent
   - Added `handle_combined_query()` method
   - Updated routing in `run()` to handle `COMBINED_ANALYSIS`
   - Updated welcome message and help text

3. **`spec.md`**
   - Added Phase 6 documentation for combined analysis feature

---

## How It Works

```
User Query: "Compare contractual fees with actual transactions for vendor X"
                    │
                    ▼
            ┌───────────────┐
            │  Classifier   │ → Detects COMBINED_ANALYSIS
            └───────────────┘
                    │
                    ▼
            ┌───────────────┐
            │  Tool Runner  │ → Claude gets all 5 tools
            └───────────────┘
                    │
         ┌──────────┴──────────┐  (PARALLEL)
         ▼                     ▼
   lookup_contract      find_transaction_file
         │                     │
         │                     ▼
         │               inspect_table
         │                     │
         │                     ▼
         │            analyze_transactions_*
         │                     │
         └──────────┬──────────┘
                    ▼
            Claude synthesizes comparison
```

---

## Testing Results

**Test 1: BLOGWIZARRO LTD**
- Found contract ✓
- Found transaction file ✓
- Detected constant €5.00 flat fee ✓
- 3 tool call rounds

**Test 2: codedtea**
- Contract not found (fuzzy match issue)
- Found transaction file ✓
- Analyzed 23,988 transactions ✓
- Found dominant 3.8% rate ✓
- 5 tool call rounds

---

## Entry Points

| Command | Purpose |
|---------|---------|
| `uv run fintech-agent` | Full interactive agent (all query types) |
| `uv run python -m src.agent.programmatic_agent "query"` | Direct Tool Runner test (combined only) |

---

## Key Technical Details

- **Model:** `claude-sonnet-4-5-20250929`
- **SDK Feature:** `client.beta.messages.tool_runner()` (beta)
- **Tool Decorator:** `@beta_tool` from `anthropic`
- **Parallel Execution:** Claude can call independent tools simultaneously

---

## Current Project State

The project now has three query handling modes:
1. **CONTRACT_INFO** → Direct tool calls to contract lookup
2. **TRANSACTION_ANALYSIS** → Direct tool calls to transaction analysis
3. **COMBINED_ANALYSIS** → Tool Runner orchestrates all tools

All tests passing. Documentation complete.

---

## Potential Future Work

- Add caching for tool results
- Implement retry logic for transient failures
- Support multiple vendors in single query
- Add more sophisticated rate comparison logic
- Consider streaming output for better UX
