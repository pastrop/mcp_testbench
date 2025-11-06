# Pandas Query Agent - Quick Start Guide

## What You've Got

A complete MCP-based agent system for querying Pandas DataFrames using natural language with Claude Sonnet 4.5 and Haiku 4.5.

## Files Created

### Core Components
- **mcp_server_pandas.py** (18K) - MCP server with 10 query tools
- **mcp_client_agent.py** (13K) - Intelligent agent client with reasoning
- **config.py** (2.4K) - Configuration settings

### Data & Testing
- **create_sample_data.py** (4.9K) - Sample data generator
- **sample_transactions.csv** (97K) - 500 sample transactions
- **test_agent.py** (2.1K) - Automated test script

### Documentation
- **README_PANDAS_AGENT.md** (7.5K) - Comprehensive documentation
- **QUICKSTART.md** (this file) - Quick start guide

### Utilities
- **run_agent.sh** (989B) - Quick launch script

## Setup (2 Steps)

### 1. Set API Key
```bash
export ANTHROPIC_API_KEY="your-api-key-here"
```

### 2. Run the Agent
```bash
# Easy way - using the script
./run_agent.sh sonnet

# Or directly
python mcp_client_agent.py mcp_server_pandas.py sample_transactions.csv sonnet
```

That's it! You're ready to query.

## Quick Test Queries

Try these to get started:

```
What columns are in the dataset?
How many transactions do we have?
What are the top 10 merchants by revenue?
Show me all transactions from the US
What's the average transaction amount by country?
Which card brand has the highest total amount?
```

## Model Switching

```bash
# Use Sonnet 4.5 (best reasoning, slower)
./run_agent.sh sonnet

# Use Haiku 4.5 (fast, good for simple queries)
./run_agent.sh haiku
```

## Running Tests

```bash
python test_agent.py
```

## Using Your Own Data

```bash
python mcp_client_agent.py mcp_server_pandas.py your_data.csv sonnet
```

Your data should have these columns:
```
comission_eur, amount_eur, card_brand_group, traffic_type_group,
transaction_comission, country, order_id, created_date, manager_id,
merchant_name, gate_id, merchant_id, company_id, company_name,
white_label_id, processor_name, processor_id, transaction_type,
transaction_status, agent_fee, card_type, tax_reserve_cost,
monthly_fee, item_id, records
```

## Architecture Summary

```
User Query → Claude (Reasoning) → MCP Tools → Pandas Operations → Results → Natural Language Response
```

### Detailed Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                         User                                 │
│                    (Natural Language Query)                  │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                    MCP Client (Agent)                        │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  Claude Sonnet 4.5 / Haiku 4.5 (Configurable)        │  │
│  │  • Extended Thinking enabled                          │  │
│  │  • Tool selection & reasoning                         │  │
│  │  • Multi-step query decomposition                     │  │
│  │  • Response synthesis                                 │  │
│  └───────────────────────────────────────────────────────┘  │
│                           │                                  │
│                           │ (MCP Protocol)                   │
│                           ▼                                  │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  MCP Client Connection Manager                        │  │
│  │  • Discovers available tools                          │  │
│  │  • Executes tool calls                                │  │
│  │  • Handles tool results                               │  │
│  └───────────────────────────────────────────────────────┘  │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           │ (stdio transport)
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                    MCP Server (Tools)                        │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  fastMCP Framework                                    │  │
│  │  • Tool registration & discovery                      │  │
│  │  • Request handling                                   │  │
│  │  • Response formatting                                │  │
│  └───────────────────────────────────────────────────────┘  │
│                           │                                  │
│                           ▼                                  │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  Pandas Query Tools (10 tools)                        │  │
│  │  • get_schema                                         │  │
│  │  • filter_by_value                                    │  │
│  │  • filter_by_range                                    │  │
│  │  • get_aggregates                                     │  │
│  │  • get_top_n                                          │  │
│  │  • get_unique_values                                  │  │
│  │  • group_by_aggregate                                 │  │
│  │  • filter_by_multiple_conditions                      │  │
│  │  • get_row_count                                      │  │
│  │  • search_text                                        │  │
│  └───────────────────────────────────────────────────────┘  │
│                           │                                  │
│                           ▼                                  │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  DataFrame Manager                                    │  │
│  │  • Load data from file                                │  │
│  │  • In-memory storage                                  │  │
│  │  • Query execution                                    │  │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

### Query Processing Flow Example

**Query:** "What are the top 5 merchants by total transaction amount?"

1. **User Input** → Client receives query
2. **Claude Reasoning** (with extended thinking):
   - Intent: Find merchants ranked by transaction amounts
   - Data needed: merchant_name, amount_eur
   - Operations: Group by merchant_name, sum amount_eur, sort descending, limit 5
   - Tool selection: `group_by_aggregate` → `get_top_n`
3. **Tool Execution**:
   - Call `group_by_aggregate(group_columns=['merchant_name'], agg_column='amount_eur', agg_function='sum')`
   - Call `get_top_n` on results (column='amount_eur', n=5, ascending=False)
4. **Response Synthesis**:
   - Format results as natural language
   - Include table/list of top merchants
5. **Return to User**

**Key Features:**
- Extended thinking for complex queries (Sonnet 4.5)
- 10 specialized Pandas query tools
- Natural language Q&A
- Validates query scope
- Multi-step reasoning

## 10 Available Tools

1. **get_schema** - Data structure and statistics
2. **filter_by_value** - Filter by single value
3. **filter_by_range** - Filter by range (numeric/date)
4. **get_aggregates** - Min, max, sum, mean, etc.
5. **get_top_n** - Top/bottom N rows
6. **get_unique_values** - Unique values with counts
7. **group_by_aggregate** - Group and aggregate
8. **filter_by_multiple_conditions** - Complex filtering
9. **get_row_count** - Count rows
10. **search_text** - Full-text search

## Common Issues

**"ANTHROPIC_API_KEY not set"**
```bash
export ANTHROPIC_API_KEY="sk-ant-..."
```

**"Data file not found"**
```bash
python create_sample_data.py 500 sample_transactions.csv
```

**"Import error"**
```bash
uv sync
```

## Model Comparison

| Feature | Sonnet 4.5 | Haiku 4.5 |
|---------|-----------|----------|
| Speed | ~5-15s | ~2-5s |
| Reasoning | Excellent | Good |
| Extended Thinking | Yes (2000 tokens) | No |
| Best For | Complex queries | Simple queries |
| Cost | Higher | Lower |

## What Can You Ask?

**✓ Good Queries:**
- Data analysis questions
- Filtering and searching
- Aggregations and statistics
- Grouping and comparisons
- Top N queries
- Schema questions

**✗ Out of Scope:**
- Non-data questions
- External information
- Code generation requests
- Predictions or ML tasks

## Next Steps

1. Try the sample queries above
2. Experiment with your own questions
3. Switch between Sonnet and Haiku
4. Load your own data
5. Add custom tools (see README_PANDAS_AGENT.md)

## Full Documentation

See **README_PANDAS_AGENT.md** for:
- Detailed architecture
- All tool descriptions
- Advanced usage
- Extending the system
- Troubleshooting
- Example queries

## Key Files to Know

- Modify tools: `mcp_server_pandas.py`
- Adjust reasoning: `mcp_client_agent.py`
- Change settings: `config.py`
- Generate data: `create_sample_data.py`

## Support

This is a demonstration project. Check the code comments and README for detailed information.

---

**Happy Querying! 🚀**
