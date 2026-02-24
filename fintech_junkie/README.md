# Financial Analysis Agentic System

A terminal-based conversational agent for financial analysis tasks:
1. Extracting financial information from contracts
2. Analyzing transaction tables to identify commission rate clusters

## Setup

### Prerequisites
- Python 3.11+
- `uv` package manager
- Anthropic API key

### Installation

```bash
# Install dependencies
uv sync

# Set your API key
export ANTHROPIC_API_KEY="your-api-key"
```

## Usage

### Running the Conversational Agent

```bash
uv run fintech-agent
```

Or directly:

```bash
uv run python -m src.agent.conversation
```

### Example Queries

**Contract Lookup:**
- "What are the rates in the Finthesis contract?"
- "Show me the fees for Skinvault"
- "What's the rolling reserve for Blogwizarro?"

**Transaction Analysis:**
- "Analyze the Blogwizarro transactions"
- "What rates are used in the codedtea file?"
- "Show me the rate clusters for lingo ventures"

## Project Structure

```
project-root/
├── src/
│   ├── agent/                          # Conversational agent
│   │   ├── classifier.py               # Query classification
│   │   └── conversation.py             # Main conversation loop
│   ├── financial_tools_server/         # MCP Server 1: Contract tools
│   │   ├── server.py
│   │   └── tools/
│   │       └── contract_lookup.py
│   └── transaction_analysis/           # MCP Server 2: Transaction analysis
│       ├── SKILL.md                    # Skill definition
│       ├── server.py
│       └── scripts/
│           ├── sorting_algorithm.py    # Placeholder
│           └── kmeans_algorithm.py     # Placeholder
├── data/                               # Input files (gitignored)
├── output/                             # Results (gitignored)
├── pyproject.toml
└── README.md
```

## MCP Servers

### Financial Tools Server

Provides contract lookup with fuzzy matching and financial term extraction.

```bash
uv run python -m src.financial_tools_server.server
```

### Transaction Analysis Server

Provides transaction table inspection and rate cluster analysis.

```bash
uv run python -m src.transaction_analysis.server
```

## Architecture

The system uses:
- **Claude Sonnet 4.5** (`claude-sonnet-4-5-20250929`) for the conversational agent
- **FastMCP** for MCP server implementation
- **RapidFuzz** for fuzzy string matching
- **Pandas** for data analysis
- **PyPDF** for PDF text extraction
