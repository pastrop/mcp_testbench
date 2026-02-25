# Financial Analysis Agentic System — Architecture Document

## Table of Contents

1. [System Overview](#system-overview)
2. [Architecture Diagram](#architecture-diagram)
3. [Component Details](#component-details)
4. [Data Flow](#data-flow)
5. [Entry Points](#entry-points)
6. [Tool Definitions](#tool-definitions)
7. [Query Classification](#query-classification)
8. [Algorithms](#algorithms)
9. [Technology Stack](#technology-stack)

---

## System Overview

The Financial Analysis Agentic System is a terminal-based conversational agent that helps users with financial analysis tasks. It provides three core capabilities:

| Capability | Description | Tools Used |
|------------|-------------|------------|
| **Contract Lookup** | Extract financial terms (rates, fees, reserves) from contracts | `lookup_contract`, `get_contract_text` |
| **Transaction Analysis** | Identify commission rate clusters in transaction data | `inspect_table`, `analyze_transactions_*` |
| **Combined Analysis** | Compare contractual rates with actual transaction fees | All tools via Tool Runner |

The system follows the **Model Context Protocol (MCP)** architecture with two specialized servers and a conversational agent that acts as an MCP client.

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                                USER INTERFACE                                    │
│                            (Terminal / stdin/stdout)                             │
└─────────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           CONVERSATIONAL AGENT                                   │
│                         (src/agent/conversation.py)                              │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────────────────┐  │
│  │    Classifier   │  │  Entity         │  │  Query Handlers                 │  │
│  │  ─────────────  │  │  Extractor      │  │  ───────────────────────────    │  │
│  │  CONTRACT_INFO  │  │  ─────────────  │  │  • handle_contract_query()      │  │
│  │  TRANSACTION    │  │  Extracts       │  │  • handle_transaction_query()   │  │
│  │  COMBINED       │  │  vendor names   │  │  • handle_combined_query()      │  │
│  │  OTHER          │  │  from queries   │  │  • handle_other_query()         │  │
│  └─────────────────┘  └─────────────────┘  └─────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────────┘
          │                        │                           │
          │ CONTRACT_INFO          │ TRANSACTION_ANALYSIS      │ COMBINED_ANALYSIS
          ▼                        ▼                           ▼
┌──────────────────────┐  ┌──────────────────────┐  ┌─────────────────────────────┐
│  FINANCIAL TOOLS     │  │  TRANSACTION         │  │  PROGRAMMATIC AGENT         │
│  MCP SERVER          │  │  ANALYSIS SERVER     │  │  (Tool Runner)              │
│  ──────────────────  │  │  ──────────────────  │  │  ─────────────────────────  │
│  • list_contracts    │  │  • inspect_table     │  │  Uses ALL tools with        │
│  • lookup_contract   │  │  • analyze_sorting   │  │  Anthropic Tool Runner      │
│  • get_contract_text │  │  • analyze_kmeans    │  │  for parallel execution     │
└──────────────────────┘  └──────────────────────┘  └─────────────────────────────┘
          │                        │                           │
          ▼                        ▼                           ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                                DATA LAYER                                        │
│  ┌─────────────────────────────────┐  ┌─────────────────────────────────────┐   │
│  │     contracts_data.json         │  │     Transaction Excel Files         │   │
│  │  ─────────────────────────────  │  │  ─────────────────────────────────  │   │
│  │  • Contract metadata            │  │  • BLOGWIZARRO_LTD_*.xlsx           │   │
│  │  • Base64-encoded PDF content   │  │  • codedtea-ltd-*.xlsx              │   │
│  │  • File paths and names         │  │  • lingo-ventures-*.xlsx            │   │
│  └─────────────────────────────────┘  └─────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## Component Details

### 1. Conversational Agent (`src/agent/`)

The main user interface and orchestration layer.

| File | Purpose |
|------|---------|
| `conversation.py` | Main conversation loop, routing logic, user interaction |
| `classifier.py` | Query classification using Claude, entity extraction |
| `programmatic_agent.py` | Tool Runner implementation for combined analysis |

**Key Classes:**
- `FinancialAgent` — Main agent class with handlers for each query type
- `QueryCategory` — Enum defining query categories

### 2. Financial Tools Server (`src/financial_tools_server/`)

MCP server for contract-related operations.

| File | Purpose |
|------|---------|
| `server.py` | FastMCP server definition with tool registration |
| `tools/contract_lookup.py` | Contract matching, PDF decoding, financial extraction |

**Capabilities:**
- Fuzzy matching on contract names and paths (RapidFuzz)
- Base64 PDF decoding and text extraction (PyPDF)
- Regex-based financial term extraction (rates, fees, reserves)

### 3. Transaction Analysis Server (`src/transaction_analysis/`)

MCP server for transaction table analysis.

| File | Purpose |
|------|---------|
| `server.py` | FastMCP server with analysis tools |
| `SKILL.md` | AI agent-focused documentation |
| `scripts/sorting_algorithm.py` | Sorting-based rate clustering |
| `scripts/kmeans_algorithm.py` | K-means clustering for complex fees |

**Algorithm Selection Logic:**
```
inspect_table()
     │
     ▼
┌─────────────────────┐
│ Commission constant?│
└─────────────────────┘
     │ Yes        │ No
     ▼            ▼
  Return      ┌─────────────────────┐
  constant    │ Minimal fee pattern?│
  value       └─────────────────────┘
                  │ Yes        │ No
                  ▼            ▼
              K-MEANS      SORTING
              algorithm    algorithm
```

### 4. Programmatic Agent (`src/agent/programmatic_agent.py`)

Implements Anthropic's Tool Runner pattern for combined analysis.

**Key Features:**
- Defines tools using `@beta_tool` decorator
- Enables parallel tool execution
- Automatic agentic loop handling
- Synthesizes results from multiple tools

---

## Data Flow

### Contract Lookup Flow

```
User: "What are the rates in the Finthesis contract?"
                    │
                    ▼
            ┌───────────────┐
            │   Classify    │ → CONTRACT_INFO
            └───────────────┘
                    │
                    ▼
            ┌───────────────┐
            │Extract Entity │ → "Finthesis"
            └───────────────┘
                    │
                    ▼
            ┌───────────────┐
            │Fuzzy Match    │ → Find matching contract
            └───────────────┘
                    │
                    ▼
            ┌───────────────┐
            │Decode PDF     │ → Extract text from base64
            └───────────────┘
                    │
                    ▼
            ┌───────────────┐
            │Extract Terms  │ → Rates, fees, reserves
            └───────────────┘
                    │
                    ▼
            Display Results
```

### Transaction Analysis Flow

```
User: "Analyze the Blogwizarro transactions"
                    │
                    ▼
            ┌───────────────┐
            │   Classify    │ → TRANSACTION_ANALYSIS
            └───────────────┘
                    │
                    ▼
            ┌───────────────┐
            │Extract Entity │ → "Blogwizarro"
            └───────────────┘
                    │
                    ▼
            ┌───────────────┐
            │Find File      │ → Match Excel file in /data
            └───────────────┘
                    │
                    ▼
            ┌───────────────┐
            │inspect_table  │ → Analyze structure
            └───────────────┘
                    │
         ┌──────────┴──────────┐
         ▼                     ▼
    Constant             Variable
    Commission           Commission
         │                     │
         ▼                     ▼
    Return value      Choose algorithm
                           │
              ┌────────────┴────────────┐
              ▼                         ▼
         SORTING                    K-MEANS
         (rate × amount)    (rate × amount + fee)
```

### Combined Analysis Flow (Tool Runner)

```
User: "Compare contractual rates with actual fees for vendor X"
                    │
                    ▼
            ┌───────────────┐
            │   Classify    │ → COMBINED_ANALYSIS
            └───────────────┘
                    │
                    ▼
            ┌───────────────────────────────────────┐
            │         TOOL RUNNER                   │
            │  (Anthropic beta.messages.tool_runner)│
            └───────────────────────────────────────┘
                    │
        ┌───────────┴───────────┐
        ▼                       ▼
  lookup_contract         find_transaction_file
  (PARALLEL)              (PARALLEL)
        │                       │
        │                       ▼
        │               inspect_table
        │                       │
        │                       ▼
        │               analyze_transactions_*
        │                       │
        └───────────┬───────────┘
                    ▼
            ┌───────────────┐
            │Claude Analysis│ → Compare & synthesize
            └───────────────┘
                    │
                    ▼
            Final Response
```

---

## Entry Points

The system provides multiple ways to run different components:

### 1. Main Conversation Agent

```bash
uv run fintech-agent
```

**What it does:**
- Runs the full interactive conversation loop
- Handles ALL query types (contract, transaction, combined, other)
- Provides a REPL interface with prompts and confirmations
- Classifies queries and routes to appropriate handlers

**Defined in:** `pyproject.toml` → `[project.scripts]`
```toml
fintech-agent = "src.agent.conversation:main"
```

**Use when:** You want the full interactive experience with all features.

### 2. Programmatic Agent (Direct)

```bash
uv run python -m src.agent.programmatic_agent "Your query here"
```

**What it does:**
- Runs ONLY the programmatic tool calling agent
- Skips the classifier and conversation loop
- Goes directly to the Tool Runner with all tools
- Single-shot execution (not interactive)

**Defined in:** `programmatic_agent.py` → `if __name__ == "__main__": main()`

**Use when:**
- Testing combined analysis queries directly
- Scripting/automation
- Debugging the Tool Runner behavior

### 3. MCP Servers (Standalone)

```bash
# Financial Tools Server
uv run python -m src.financial_tools_server.server

# Transaction Analysis Server
uv run python -m src.transaction_analysis.server
```

**What it does:**
- Runs MCP servers as standalone processes
- Can be connected to by any MCP client (Claude Desktop, etc.)

**Use when:** Integrating with external MCP clients.

### Comparison Table

| Command | Interactive | Classifier | All Query Types | Tool Runner |
|---------|-------------|------------|-----------------|-------------|
| `uv run fintech-agent` | ✅ Yes | ✅ Yes | ✅ Yes | Only for COMBINED |
| `uv run python -m src.agent.programmatic_agent "..."` | ❌ No | ❌ No | ❌ Combined only | ✅ Always |
| `uv run python -m src.financial_tools_server.server` | ❌ No | ❌ N/A | ❌ Contract only | ❌ No |
| `uv run python -m src.transaction_analysis.server` | ❌ No | ❌ N/A | ❌ Transaction only | ❌ No |

---

## Tool Definitions

### Financial Tools Server

| Tool | Parameters | Returns |
|------|------------|---------|
| `list_contracts()` | None | List of all contracts with metadata |
| `lookup_contract(query, extract_financial_terms)` | `query`: str, `extract_financial_terms`: bool | Matched contract + financial info |
| `get_contract_text(query)` | `query`: str | Full contract text (up to 50KB) |

### Transaction Analysis Server

| Tool | Parameters | Returns |
|------|------------|---------|
| `inspect_table(file_path)` | `file_path`: str | Columns, stats, algorithm recommendation |
| `analyze_transactions_sorting(file_path, amount_column, commission_column, ...)` | File path + column names | Rate clusters (simple model) |
| `analyze_transactions_kmeans(file_path, amount_column, commission_column, ...)` | File path + column names | Rate + fee clusters (complex model) |

### Programmatic Agent Tools

All tools from above, plus:

| Tool | Parameters | Returns |
|------|------------|---------|
| `find_transaction_file(vendor_name)` | `vendor_name`: str | File path for vendor's transaction data |

---

## Query Classification

The classifier uses Claude to categorize queries:

```python
class QueryCategory(Enum):
    CONTRACT_INFO = "contract_info"
    TRANSACTION_ANALYSIS = "transaction_analysis"
    COMBINED_ANALYSIS = "combined_analysis"
    OTHER = "other"
```

### Classification Examples

| Query | Category |
|-------|----------|
| "What are the rates in the Finthesis contract?" | CONTRACT_INFO |
| "Analyze the Blogwizarro transactions" | TRANSACTION_ANALYSIS |
| "Compare contractual fees with actual rates for codedtea" | COMBINED_ANALYSIS |
| "Hello, what can you do?" | OTHER |

---

## Algorithms

### Sorting Algorithm

**Use case:** `commission = rate × amount`

**Process:**
1. Calculate rate for each transaction: `rate = commission / amount`
2. Sort all rates
3. Scan sorted rates to find clusters (points within `min_rate_diff/2`)
4. Return clusters with statistics

**Complexity:** O(n log n)

### K-Means Algorithm

**Use case:** `commission = rate × amount + minimal_fee`

**Process:**
1. Normalize (amount, commission) data
2. Auto-detect optimal cluster count using silhouette scoring
3. Fit linear model to each cluster: `commission = rate × amount + fee`
4. Compute R² fit quality for each cluster

**Output:** Clusters with rate, minimal_fee, and fit quality

---

## Technology Stack

| Component | Technology |
|-----------|------------|
| Language | Python 3.11+ |
| Package Manager | uv |
| LLM | Claude (claude-sonnet-4-5-20250929) |
| LLM SDK | anthropic>=0.40.0 |
| MCP Framework | fastmcp>=0.4.0 |
| Data Analysis | pandas>=2.0.0 |
| Excel Parsing | openpyxl>=3.1.0 |
| PDF Extraction | pypdf>=4.0.0 |
| Fuzzy Matching | rapidfuzz>=3.0.0 |

---

## Directory Structure

```
fintech_junkie/
├── src/
│   ├── agent/                          # Conversational Agent
│   │   ├── __init__.py
│   │   ├── classifier.py               # Query classification
│   │   ├── conversation.py             # Main conversation loop
│   │   └── programmatic_agent.py       # Tool Runner implementation
│   │
│   ├── financial_tools_server/         # MCP Server 1: Contracts
│   │   ├── __init__.py
│   │   ├── server.py                   # FastMCP server
│   │   └── tools/
│   │       ├── __init__.py
│   │       └── contract_lookup.py      # Contract matching & extraction
│   │
│   └── transaction_analysis/           # MCP Server 2: Transactions
│       ├── __init__.py
│       ├── server.py                   # FastMCP server
│       ├── SKILL.md                    # AI agent documentation
│       └── scripts/
│           ├── __init__.py
│           ├── sorting_algorithm.py    # Sorting-based clustering
│           └── kmeans_algorithm.py     # K-means clustering
│
├── data/                               # Input data (gitignored)
│   ├── contracts_data.json             # Contract database
│   └── *.xlsx                          # Transaction files
│
├── docs/                               # Documentation
│   ├── architecture.md                 # This document
│   └── programmatic_tool_calling.md    # Tool Runner design doc
│
├── output/                             # Results (gitignored)
├── pyproject.toml                      # Project configuration
├── spec.md                             # Build specification
└── README.md                           # User documentation
```

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 0.1.0 | Initial | Core system with contract lookup and transaction analysis |
| 0.2.0 | Current | Added programmatic tool calling for combined analysis |
