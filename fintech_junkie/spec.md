# Financial Analysis Agentic System — Build Spec

## Overview

Build a terminal-based conversational agent that helps users with two core tasks:
1. Extracting financial information from contracts
2. Analyzing transaction tables to identify clusters of transactions with different rates

The system uses two separate MCP servers and a conversational agent that connects to both as a client.

---

## Phase 1: Project Scaffolding

### Setup
- Use Python with `uv` package manager
- Use Claude family of models. Use `claude-sonnet-4-5-20250929` for the conversational agent
- The API key is defined in the environment variable `ANTHROPIC_API_KEY`

### Project Structure

```
project-root/
├── src/
│   ├── agent/                          # Conversational agent (MCP client)
│   │   ├── classifier.py               # Query classification logic
│   │   └── conversation.py             # Main conversation loop + routing
│   ├── financial_tools_server/          # MCP Server 1: Contract tools
│   │   ├── server.py
│   │   └── tools/
│   │       └── contract_lookup.py
│   └── transaction_analysis/           # MCP Server 2: Transaction analysis skill
│       ├── SKILL.md                    # Skill definition (see Phase 3)
│       ├── server.py
│       ├── scripts/
│       │   ├── sorting_algorithm.py    # Placeholder
│       │   └── kmeans_algorithm.py     # Placeholder
│       └── references/                 # Extended documentation if needed
├── data/                               # Input files (gitignored)
│   ├── contracts_data.json
│   └── *.xlsx                          # Transaction tables
├── output/                             # Execution results (gitignored)
├── pyproject.toml
├── .gitignore
└── README.md
```

### .gitignore
Ensure that `/data/` and `/output/` directories and their contents are never committed to GitHub.

---

## Phase 2: Financial Tools MCP Server (Server 1)

### Contract Lookup Tool

**Purpose:** Extract financial information (rates, fees, rolling reserves, chargeback fees, currency-specific terms, and any other financial terms) from parsed contract PDFs.

**Data source:** `data/contracts_data.json`
- Before implementing, inspect this file to discover its schema and structure. Adapt the implementation to match whatever schema you find.
- The file contains contract data where PDF content has been pre-parsed into base64 using Python's `base64` library.

**Contract matching logic:**
The user will often provide partial or informal names. The tool must perform fuzzy matching against both `file_name` and `file_path` fields in the JSON data, since the file path is often more informative than the file name.

Examples:
- User says "Finthesis" → should match `Agreement_FINTHESIS_DEVALENIUS LTD_rev (1).docx (1) (1)`
- User says "Skinvault" → should match a contract where `file_path` is `contracts/SKINVALUT LIMITED/Complete_with_Docusign_ADDITIONAL_AGREEMENT (2).pdf` even though the file_name alone is generic

Matching rules:
- Case-insensitive
- Match against both file_name and file_path
- If multiple contracts match, return the list of matches and ask the user to clarify
- If no match is found, tell the user the contract is not available

**Financial extraction:**
When a contract is identified, decode the base64 content and extract all financial information including but not limited to: transaction rates, fees (chargeback fees, processing fees, etc.), rolling reserves, currency-specific terms, and any other monetary terms found in the document.

---

## Phase 3: Transaction Analysis MCP Server (Server 2) — Claude Skill

This must be built as a **standalone, self-contained MCP server** that can be used independently by any MCP client (Claude Desktop, this agentic system, or any future interface).

### SKILL.md Requirements

Create a `SKILL.md` file at the root of the transaction analysis server directory with:
- YAML frontmatter containing `name` and `description` fields
- The `description` should be assertive about triggering — include phrases like "Use this skill whenever the user mentions transaction analysis, commission rates, fee identification, rate clustering, or references transaction/acquiring Excel files"
- Keep the body under 500 lines
- Include: purpose, available tools and their parameters, the decision logic for algorithm selection, expected input formats, and example usage flows
- Do NOT include README.md, CHANGELOG.md, or human-onboarding docs — the SKILL.md is for AI agents

### Tools

#### `inspect_table`
- Input: file path to an Excel file
- Output: column names, sample rows, basic statistics
- Purpose: allows the agent (or any MCP client) to understand the table structure before deciding which algorithm to use

#### `analyze_transactions_sorting`
- Input: file path, relevant column names
- Purpose: handles the case where the table has a single commission column and commission = transaction_rate × transaction_amount
- **For this phase: implement as a placeholder** that logs the call parameters and returns a mock result. The actual sorting algorithm will be implemented later.

#### `analyze_transactions_kmeans`
- Input: file path, relevant column names
- Purpose: handles the case where the commission column includes a minimal fee component, so commission = transaction_rate × transaction_amount + minimal_fee
- **For this phase: implement as a placeholder** that logs the call parameters and returns a mock result.

#### Algorithm Selection Logic

This logic should be documented in SKILL.md so any MCP client can follow it, but the recommended flow is:

1. Always call `inspect_table` first
2. Based on the inspection results, determine which case applies:
   - **Case 1:** Table has a single commission column → use `analyze_transactions_sorting`
   - **Case 2:** Table has a commission column AND a minimal fee column → use `analyze_transactions_kmeans`
   - **Case 3:** All commission values in the table are identical (constant) → skip algorithms entirely, return the constant commission value to the user
3. If the column structure is ambiguous, return the inspection results and let the client/user decide

### File Resolution

- Do NOT hardcode any file names
- The file to analyze is determined from the user's query
- The agent should search the `/data` directory for files matching the user's description
- Users may give partial names. Example: "Blogwizarro" should match `BLOGWIZARRO_LTD_acquiring_monthly-202511.xlsx`
- Use case-insensitive fuzzy matching against filenames in `/data`
- If no match is found, tell the user the transaction data is not available
- Inspect the example Excel files in `/data` before implementing, to understand the actual column structures you'll be working with

---

## Phase 4: Conversational Agent (MCP Client)

### Architecture
The agent connects to both MCP servers as a client. It runs a terminal-based conversation loop (stdin/stdout).

### Query Classification

Classify each user message into one of three categories:

1. **Contract financial info request** — user is asking about rates, fees, or financial terms from a contract
2. **Transaction table analysis request** — user wants to analyze transaction data, identify rate clusters, or understand commission structures
3. **Other** — anything that doesn't fall into (1) or (2). Respond by explaining the available capabilities and asking the user to rephrase

### Conversation Flow by Category

#### Category 1: Contract Financial Info
1. Identify which contract the user is asking about
2. If the match is ambiguous, present candidates and ask user to confirm
3. Call the contract lookup tool on the confirmed contract
4. Display the extracted financial information in the terminal

#### Category 2: Transaction Table Analysis
1. Determine which file the user is referring to
2. If the file can't be resolved, ask for clarification
3. Call `inspect_table` to understand the column structure
4. Based on the inspection, determine which algorithm case applies (following the logic in SKILL.md)
5. If Case 3 (constant commission), report the value directly
6. Otherwise, call the appropriate analysis tool
7. Display results in the terminal

#### Category 3: Other
- Politely explain that the system supports contract financial info lookup and transaction table analysis
- Ask the user to rephrase their request

### Confirmation Flows
- Before executing contract lookups: confirm the matched contract with the user
- Before executing transaction analysis: confirm the file and the chosen approach

### Error Handling
- All tool calls should be wrapped in error handling
- If a tool call fails, present a clear error message to the user rather than crashing
- If a contract can't be decoded or an Excel file has unexpected structure, report this gracefully

---

## Phase 5: Conversation Loop

Implement the main loop in the terminal:
- Accept user input via stdin
- Classify the query
- Execute the appropriate flow (with confirmation steps)
- Display results to stdout
- Loop until the user exits (e.g., types "quit" or "exit")

---

## Execution Order

Build and verify in this order:

1. **Project scaffolding** — uv setup, directory structure, .gitignore, pyproject.toml
2. **Inspect data files** — examine `contracts_data.json` schema and Excel file structures in `/data` before writing any tool logic
3. **Transaction Analysis MCP Server** — SKILL.md, server.py, inspect_table tool, placeholder algorithm tools
4. **Financial Tools MCP Server** — contract lookup tool with fuzzy matching and financial extraction
5. **Conversational agent** — classifier, routing logic, confirmation flows, conversation loop
6. **Integration test** — run the full system from the terminal, test each category with example queries

---

## Constraints & Reminders

- Do not hardcode file names anywhere. All file resolution is dynamic based on user input.
- The transaction analysis server must be fully self-contained and usable independently of the conversational agent.
- Placeholder algorithm tools should accept the correct parameters and return plausible mock results so the full pipeline can be tested end-to-end.
- All user-facing output goes to the terminal.
- Use `claude-sonnet-4-5-20250929` as the model for the conversational agent.
