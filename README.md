# Pandas Query Agent with MCP

An intelligent agent system that uses Claude's reasoning capabilities and the Model Context Protocol (MCP) to answer natural language queries about Pandas DataFrames.

## Architecture

The system consists of two main components:

### 1. MCP Server (`mcp_server_pandas.py`)
Provides 10 specialized tools for querying transaction data:
- **get_schema**: Get DataFrame structure and statistics
- **filter_by_value**: Filter by single column value
- **filter_by_range**: Filter by numeric/date ranges
- **get_aggregates**: Calculate min, max, sum, mean, median, etc.
- **get_top_n**: Get top/bottom N rows by value
- **get_unique_values**: List unique values with counts
- **group_by_aggregate**: Group and aggregate operations
- **filter_by_multiple_conditions**: Complex multi-column filtering
- **get_row_count**: Count total or filtered rows
- **search_text**: Full-text search across columns

### 2. MCP Client (`mcp_client_agent.py`)
Intelligent agent that:
- Uses Claude Sonnet 4 (with extended thinking) or Claude Haiku 4.5
- Reasons about user queries to select appropriate tools
- Chains multiple tool calls for complex queries
- Validates if queries can be answered with available data
- Synthesizes results into natural language responses

## Data Schema

The data schema as defined at when the dataset is ingested. Below is a schema example:
```
comission_eur, amount_eur, card_brand_group, traffic_type_group,
transaction_comission, country, order_id, created_date, manager_id,
merchant_name, gate_id, merchant_id, company_id, company_name,
white_label_id, processor_name, processor_id, transaction_type,
transaction_status, agent_fee, card_type, tax_reserve_cost,
monthly_fee, item_id, records
```

## Installation

1. Install dependencies:
```bash
uv sync
```

2. Set your Anthropic API key:
```bash
export ANTHROPIC_API_KEY="your-api-key-here"
```

3. Generate sample data:
```bash
python create_sample_data.py 1000 sample_transactions.csv
```

## Usage

### Interactive Mode

Start the agent in interactive mode:

```bash
# Using Sonnet 4.5 (default - best for complex queries)
python mcp_client_agent.py mcp_server_pandas.py sample_transactions.csv sonnet

# Using Claude Haiku 4.5 (faster for simple queries)
python mcp_client_agent.py mcp_server_pandas.py sample_transactions.csv haiku
```

### Example Queries

Here are some example queries you can try:

**Schema & Structure:**
```
What columns are available in the dataset?
How many rows are in the dataset?
Show me the data structure
```

**Filtering & Search:**
```
Show me all transactions from the US
Find transactions with amount greater than 1000 EUR
Show me all Visa transactions in Germany
Search for transactions from Merchant_5
```

**Aggregation & Statistics:**
```
What is the total transaction amount?
What are the top 10 merchants by revenue?
Show me average transaction amount by country
What is the highest commission earned?
```

**Grouping & Analysis:**
```
Group transactions by card brand and show total amounts
What are the top 5 countries by transaction volume?
Show me transaction count by status
Compare total amounts across different traffic types
```

**Complex Queries:**
```
Find all completed Visa transactions over 500 EUR in the US or UK
What are the top merchants by transaction count for online traffic?
Show me the breakdown of transaction statuses by processor
Which card type has the highest average transaction amount?
```

**Out-of-Scope Queries (will be rejected):**
```
What's the weather like today?
Who won the world cup?
Write me a Python function
```

## Model Selection

### Claude Sonnet 4 (Recommended)
- **Use for:** Complex queries, multi-step reasoning, ambiguous requests
- **Features:** Extended thinking, better reasoning, more accurate
- **Performance:** ~5-15 seconds per query
- **Model ID:** `claude-sonnet-4-20250514`

### Claude Haiku 4.5
- **Use for:** Simple queries, single operations, quick answers
- **Features:** Fast responses, efficient
- **Performance:** ~2-5 seconds per query
- **Model ID:** `claude-haiku-4-5-20251001`

## Query Processing Flow

1. **User Input** → Natural language query
2. **Reasoning Phase** → Claude analyzes intent and determines approach
3. **Tool Selection** → Selects appropriate MCP tool(s)
4. **Execution** → Calls tools via MCP protocol
5. **Synthesis** → Converts results to natural language
6. **Response** → Returns answer to user

## Project Structure

```
testbench/
├── mcp_server_pandas.py      # MCP server with Pandas tools
├── mcp_client_agent.py        # Reasoning agent client
├── config.py                  # Configuration settings
├── create_sample_data.py      # Sample data generator
├── sample_transactions.csv    # Generated sample data
├── README_PANDAS_AGENT.md     # This file
└── pyproject.toml            # Dependencies
```

## Advanced Usage

### Programmatic Usage

```python
import asyncio
from mcp_client_agent import PandasQueryAgent

async def main():
    agent = PandasQueryAgent(model="sonnet")

    async with agent.connect_to_server(
        "mcp_server_pandas.py",
        "sample_transactions.csv"
    ):
        response = await agent.query("What are the top 5 merchants?")
        print(response)

asyncio.run(main())
```

### Custom Data

Use your own CSV, Parquet, or JSON file:

```bash
python mcp_client_agent.py mcp_server_pandas.py your_data.csv sonnet
```

Ensure your data has the expected columns or modify the server to accept different schemas.

## Interactive Commands

While running the agent:
- `clear` - Clear conversation history
- `history` - Show conversation length
- `quit` or `exit` - Exit the program

## Troubleshooting

### API Key Not Set
```
Error: ANTHROPIC_API_KEY environment variable not set
```
Solution: `export ANTHROPIC_API_KEY="your-key"`

### File Not Found
```
Error: Data file not found: sample_transactions.csv
```
Solution: Run `python create_sample_data.py` first

### Connection Issues
```
Error starting server: [Errno 2] No such file or directory
```
Solution: Ensure Python is in PATH and all files exist

### Tool Errors
If a tool call fails, the agent will report the error and may suggest alternatives.

## Performance Tips

1. **Use Haiku for simple queries** - Much faster for basic operations
2. **Be specific** - Clear queries get better results
3. **Break down complex questions** - Agent handles multi-step reasoning better with clear intent
4. **Check schema first** - Use "show me the schema" to understand available data

## Extending the System

### Adding New Tools

In `mcp_server_pandas.py`:
```python
@mcp.tool()
def your_custom_tool(param1: str, param2: int) -> str:
    """Tool description for Claude."""
    df = get_dataframe()
    # Your logic here
    return dataframe_to_json(result)
```

### Supporting Different Schemas

Modify the `load_dataframe()` function to handle different column sets or add column mapping.

### Adding More Models

In `mcp_client_agent.py`, update the `MODELS` dictionary:
```python
MODELS = {
    "sonnet": "claude-sonnet-4-20250514",
    "haiku": "claude-haiku-4-20250520",
    "your_model": "model-id"
}
```

## Technical Details

- **MCP Protocol**: stdio transport for local development
- **Python Version**: 3.13+
- **Key Libraries**: anthropic, fastmcp, pandas, mcp
- **Extended Thinking**: Enabled for Sonnet (2000 token budget)
- **Max Tokens**: 4096 per response
- **Result Limits**: 1000 rows max per tool response

## License

This is a demonstration project. Modify and use as needed.

## Contributing

This is a testbench project. Feel free to extend and customize for your needs.
