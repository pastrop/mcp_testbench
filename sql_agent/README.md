# Text-to-SQL Translation Agent

An intelligent agent that translates natural language queries into executable GoogleSQL (BigQuery dialect) queries. The agent features schema analysis, ambiguity detection, and a human-in-the-loop approach for clarifications.

## Features

- **Schema Management**: Loads and analyzes database schemas from JSON files
- **Ambiguity Detection**: Automatically detects potential issues like:
  - Similar column names (e.g., `amount` vs `amount_eur`)
  - Duplicate descriptions
  - Ambiguous naming patterns
- **Human-in-the-Loop**: Prompts for clarifications when ambiguities are detected
- **SQL Translation**: Converts natural language to GoogleSQL using Claude Sonnet 4.5
- **Query Validation**: Validates generated queries for safety and correctness
- **MCP Integration**: Exposes functionality via FastMCP for tool integration

## Architecture

```
┌─────────────────────┐
│  Natural Language   │
│      Query          │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│   TextToSQLAgent    │
│  (Orchestration)    │
└─────┬───────┬───────┘
      │       │
      ▼       ▼
┌───────────┐ ┌──────────────┐
│  Schema   │ │    Query     │
│  Manager  │ │  Translator  │
└───────────┘ └──────────────┘
      │              │
      ▼              ▼
┌───────────┐ ┌──────────────┐
│ schema.   │ │ Claude API   │
│  json     │ │ (Sonnet 4.5) │
└───────────┘ └──────────────┘
```

## Installation

1. Clone the repository and navigate to the directory:
```bash
cd sql_agent
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Set up your Anthropic API key:
```bash
export ANTHROPIC_API_KEY="your-api-key-here"
```

## Usage

### Command Line Interface

Run the agent directly:

```bash
python agent.py
```

This will:
1. Load and analyze the schema
2. Display detected ambiguities
3. Run an example query translation

### Python API

```python
from agent import TextToSQLAgent

# Initialize the agent
agent = TextToSQLAgent(schema_path="schema.json", table_name="transactions")

# Initialize and analyze schema
init_result = agent.initialize()
print(f"Loaded {init_result['columns_loaded']} columns")
print(f"Found {init_result['ambiguities']['total']} ambiguities")

# Add clarifications if needed
agent.add_clarification(
    "amount_eur",
    "This is the transaction amount in EUR after conversion"
)

# Translate a query
result = agent.process_query_with_feedback(
    "What is the total commission by merchant?"
)

if result['success']:
    print(f"SQL: {result['sql']}")
    print(f"Confidence: {result['confidence']}")
```

### MCP Server

Run the MCP server to expose tools:

```bash
python mcp_server.py
```

Available MCP tools:
- `initialize_schema`: Load and analyze a schema file
- `get_schema_summary`: Get schema statistics
- `get_ambiguities`: List detected ambiguities
- `add_clarification`: Add user clarifications
- `translate_to_sql`: Convert natural language to SQL
- `search_columns`: Search for columns by keyword
- `validate_sql`: Validate SQL query safety
- `save_schema_with_clarifications`: Save enriched schema

## Schema Format

The agent expects a JSON schema file with the following structure:

```json
[
  {
    "name": "column_name",
    "type": "STRING|FLOAT|INTEGER|DATE|TIMESTAMP",
    "short_description": "Brief description",
    "detailed_description": "Detailed explanation of the column"
  }
]
```

## Testing

Run the comprehensive test suite:

```bash
# Run all tests
python test_agent.py

# Or use pytest
pytest test_agent.py -v

# Skip API tests to avoid costs
SKIP_API_TESTS=1 python test_agent.py
```

Test coverage includes:
- Schema loading and analysis
- Ambiguity detection
- Query translation
- Validation
- End-to-end scenarios

## Query Examples

The agent can handle various query types:

**Aggregation:**
```
"What is the total transaction amount in EUR?"
→ SELECT SUM(amount_eur) as total FROM transactions
```

**Filtering:**
```
"Show all approved transactions from Visa cards"
→ SELECT * FROM transactions WHERE status = 'approved' AND card_brand = 'Visa'
```

**Grouping:**
```
"Show total commission by merchant and card brand"
→ SELECT merchant_name, card_brand, SUM(comission_eur) as total
  FROM transactions GROUP BY merchant_name, card_brand
```

**Date Filtering:**
```
"Show transactions from January 2024"
→ SELECT * FROM transactions
  WHERE created_date BETWEEN '2024-01-01' AND '2024-01-31'
```

**Top N:**
```
"Show top 10 merchants by transaction volume"
→ SELECT merchant_name, COUNT(*) as txn_count
  FROM transactions GROUP BY merchant_name
  ORDER BY txn_count DESC LIMIT 10
```

## Configuration

### Model Selection

By default, the agent uses Claude Sonnet 4.5 (`claude-sonnet-4-5-20250929`) which provides:
- Excellent SQL generation accuracy
- Strong reasoning for complex queries
- Reliable GoogleSQL dialect support

To use a different model:

```python
from query_translator import QueryTranslator

translator = QueryTranslator(model="claude-opus-4-20250514")
```

### Schema Path

Specify a custom schema file:

```python
agent = TextToSQLAgent(
    schema_path="/path/to/your/schema.json",
    table_name="your_table_name"
)
```

## How It Works

### 1. Schema Analysis

The agent analyzes the schema to detect:
- **Similar names**: Columns like `amount` and `amount_eur`
- **Similar descriptions**: Columns with nearly identical descriptions
- **Ambiguous patterns**: Groups like status/transaction_status

### 2. Human-in-the-Loop

When ambiguities are detected, the agent presents them for user clarification:

```
⚠️ Found 5 potential ambiguities in the schema.

Ambiguity 1 [MEDIUM]:
Reason: Multiple commission-related columns that may be confusing

  Column: comission_eur (FLOAT)
    Total commission in EUR

  Column: transaction_comission (FLOAT)
    Total commission in original currency

Would you like to clarify? (y/n)
```

### 3. Query Translation

The agent constructs a detailed prompt for Claude including:
- Full schema with types and descriptions
- User clarifications
- GoogleSQL-specific guidelines
- Single table constraint (no JOINs)

### 4. Validation

Generated queries are validated for:
- No JOIN operations
- No destructive operations (DROP, DELETE, etc.)
- Proper SELECT structure
- No SQL injection patterns

## Limitations

- **Single Table Only**: Designed for single-table queries (no JOINs)
- **GoogleSQL Dialect**: Optimized for BigQuery syntax
- **API Costs**: Each query translation requires a Claude API call
- **No Query Execution**: Generates SQL but doesn't execute it

## API Reference

### TextToSQLAgent

Main orchestration class.

**Methods:**
- `initialize()`: Load and analyze schema
- `get_ambiguities_for_review()`: Get list of detected ambiguities
- `add_clarification(column_name, clarification)`: Add user clarification
- `translate_query(query)`: Translate NL to SQL
- `process_query_with_feedback(query)`: Translate with full details
- `get_schema_summary()`: Get schema statistics
- `save_clarifications(path)`: Save enriched schema

### SchemaManager

Handles schema loading and analysis.

**Methods:**
- `load_schema()`: Load schema from JSON
- `analyze_schema()`: Detect ambiguities
- `get_column(name)`: Get column by name
- `search_columns(term)`: Search columns
- `get_enriched_schema_description()`: Get full schema text

### QueryTranslator

Translates queries using Claude API.

**Methods:**
- `translate(query, schema, table)`: Translate NL to SQL
- `validate_query(sql)`: Validate SQL safety

## Troubleshooting

**Issue**: "ANTHROPIC_API_KEY environment variable not set"
```bash
export ANTHROPIC_API_KEY="your-key-here"
```

**Issue**: Schema file not found
```bash
# Ensure schema.json exists in the current directory
ls schema.json
```

**Issue**: API rate limits
- Add delays between requests
- Use caching for repeated queries
- Consider batch processing

## Contributing

Contributions are welcome! Areas for improvement:
- Support for multi-table queries with automatic join detection
- Query result caching
- Interactive web UI
- Additional SQL dialects (PostgreSQL, MySQL)
- Query optimization suggestions

## License

MIT License

## Support

For issues and questions:
- Open an issue on GitHub
- Check the test suite for usage examples
- Review the docstrings in the code
