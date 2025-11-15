# Quick Start Guide

Get up and running with the Text-to-SQL agent in 5 minutes!

## Prerequisites

- Python 3.13+
- UV package manager (already set up in your testbench environment)
- Anthropic API key (optional for schema analysis, required for query translation)

## Step 1: Set Up API Key (Optional)

For query translation features:
```bash
export ANTHROPIC_API_KEY="your-api-key-here"
```

Skip this step if you only want to use schema analysis features.

## Step 2: Run the Demo

You can run either the **automated** demo or the **interactive** demo:

### Automated Demo (No User Input)

```bash
cd /Users/alexsmirnoff/Documents/src/testbench
uv run python sql_agent/demo.py
```

This will show you:
- Schema loading and analysis
- Ambiguity detection
- Hardcoded example clarifications
- Column searching
- Query translation on 6 example queries (if API key is set)
- Automatic query rebuilding on validation failures
- **All output is automatically saved to `demo_output_YYYYMMDD_HHMMSS.txt`**

Perfect for quick demonstrations and automated testing.

### Interactive Demo (Human-in-the-Loop)

```bash
cd /Users/alexsmirnoff/Documents/src/testbench
uv run python sql_agent/demo_interactive.py
```

This will show you:
- Schema loading and analysis
- Ambiguity detection
- **Interactive prompts to clarify each ambiguity** (requires your input)
- Column searching
- Query translation on the same 6 example queries (if API key is set)
- Automatic query rebuilding on validation failures
- **All output is automatically saved to `demo_interactive_output_YYYYMMDD_HHMMSS.txt`**

Use this to experience the full human-in-the-loop clarification workflow.

## Step 3: Run the Tests

```bash
cd /Users/alexsmirnoff/Documents/src/testbench
uv run python sql_agent/test_agent.py
```

Expected output:
```
Tests run: 28
Successes: 28
Failures: 0
Errors: 0
```

## Step 4: Use in Your Code

### Example 1: Schema Analysis (No API Key Needed)

```python
from sql_agent.agent import TextToSQLAgent

# Initialize and analyze schema
agent = TextToSQLAgent(
    schema_path="sql_agent/schema.json",
    table_name="transactions"
)

# Load schema
result = agent.initialize()
print(f"Loaded {result['columns_loaded']} columns")
print(f"Found {result['ambiguities']['total']} ambiguities")

# Get ambiguities for review
ambiguities = agent.get_ambiguities_for_review()
for amb in ambiguities:
    print(f"{amb['severity']}: {amb['reason']}")
    print(f"Columns: {[c['name'] for c in amb['columns']]}")

# Search for columns
results = agent.schema_manager.search_columns("commission")
print(f"Found {len(results)} commission-related columns")
```

### Example 2: Query Translation (Requires API Key)

```python
from sql_agent.agent import TextToSQLAgent

agent = TextToSQLAgent(schema_path="sql_agent/schema.json")
agent.initialize()

# Add clarifications to improve translation
agent.add_clarification(
    "amount_eur",
    "Use this for transaction amounts in EUR"
)

# Translate natural language to SQL
result = agent.process_query_with_feedback(
    "What is the total commission by merchant?"
)

if result['success']:
    print(f"SQL: {result['sql']}")
    print(f"Confidence: {result['confidence']}")
    print(f"Explanation: {result['explanation']}")
else:
    print(f"Error: {result['error']}")
```

### Example 3: Run MCP Server

```bash
cd /Users/alexsmirnoff/Documents/src/testbench
uv run python sql_agent/mcp_server.py
```

Then use the MCP tools from any MCP client:
- `initialize_schema()`
- `get_ambiguities()`
- `translate_to_sql(query="your question")`
- etc.

## Common Use Cases

### Use Case 1: Analyze a New Schema

```python
agent = TextToSQLAgent(schema_path="your_schema.json")
agent.initialize()

# Review ambiguities
ambiguities = agent.get_ambiguities_for_review()

# Add clarifications
for amb in ambiguities:
    if amb['severity'] == 'high':
        # Handle high-priority ambiguities
        pass

# Save enriched schema
agent.save_clarifications("schema_clarified.json")
```

### Use Case 2: Translate Multiple Queries

```python
queries = [
    "Show total revenue by merchant",
    "What are the top 10 transactions?",
    "Count approved transactions by day"
]

agent = TextToSQLAgent(schema_path="sql_agent/schema.json")
agent.initialize()

for query in queries:
    result = agent.translate_query(query)
    if result.get('sql'):
        print(f"\nQuery: {query}")
        print(f"SQL: {result['sql']}\n")
```

### Use Case 3: Interactive Clarification Session

```python
agent = TextToSQLAgent(schema_path="sql_agent/schema.json")
agent.initialize()

# Run interactive session (CLI)
agent.interactive_clarification_session()

# Or programmatically
ambiguities = agent.get_ambiguities_for_review()
for amb in ambiguities:
    print(f"\nAmbiguity: {amb['reason']}")
    for col in amb['columns']:
        print(f"  {col['name']}: {col['short_description']}")

    # Get user input
    clarification = input("Add clarification? (column:clarification or skip): ")
    if ':' in clarification:
        col_name, text = clarification.split(':', 1)
        agent.add_clarification(col_name.strip(), text.strip())
```

## Troubleshooting

### Issue: "ANTHROPIC_API_KEY environment variable not set"

**Solution**:
```bash
export ANTHROPIC_API_KEY="anthropic key here"
```

Or if you only need schema analysis, the agent will work without it.

### Issue: "No such file or directory: 'schema.json'"

**Solution**: Use absolute or relative paths:
```python
from pathlib import Path

schema_path = Path(__file__).parent / "schema.json"
agent = TextToSQLAgent(schema_path=str(schema_path))
```

### Issue: Tests are skipped

**Reason**: Tests that require the API key are automatically skipped when `ANTHROPIC_API_KEY` is not set.

**Solution**: Set the API key to run all tests, or set `SKIP_API_TESTS=1` to explicitly skip them.

## Query Examples

Once you have your API key set, try these queries:

**Simple aggregation:**
```python
"What is the total transaction amount in EUR?"
```

**Grouping:**
```python
"Show total commission by merchant"
```

**Filtering:**
```python
"Show all approved transactions from Visa cards"
```

**Top N:**
```python
"What are the top 10 merchants by transaction count?"
```

**Date filtering:**
```python
"Show transactions from January 2024"
```

**Complex query:**
```python
"What is the average commission rate by card brand for approved transactions?"
```

## Directory Structure

```
testbench/
├── pyproject.toml          # Dependencies (already configured)
└── sql_agent/
    ├── agent.py            # Main agent
    ├── schema_manager.py   # Schema analysis
    ├── query_translator.py # SQL generation
    ├── mcp_server.py       # MCP server
    ├── test_agent.py       # Tests
    ├── demo.py             # Automated demo (no user input)
    ├── demo_interactive.py # Interactive demo (human-in-the-loop)
    ├── schema.json         # Your schema
    └── README.md           # Full documentation
```

## Next Steps

1. ✅ Run the automated demo: `uv run python sql_agent/demo.py`
2. ✅ Run the interactive demo: `uv run python sql_agent/demo_interactive.py`
3. ✅ Run the tests: `uv run python sql_agent/test_agent.py`
4. ✅ Try translating your own queries
5. ✅ Integrate into your application
6. ✅ Run the MCP server for tool integration

## Resources

- **Full Documentation**: `sql_agent/README.md`
- **Project Summary**: `sql_agent/SUMMARY.md`
- **Automated Demo**: `sql_agent/demo.py`
- **Interactive Demo**: `sql_agent/demo_interactive.py`
- **API Reference**: See docstrings in source files

## Support

For questions or issues:
1. Check `README.md` for detailed documentation
2. Review test cases in `test_agent.py` for examples
3. Run `demo.py` (automated) or `demo_interactive.py` (human-in-the-loop) to see the agent in action

---

**Ready to translate natural language to SQL!** 🚀
