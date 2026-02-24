---
name: transaction-analysis
description: >
  Use this skill whenever the user mentions transaction analysis, commission rates,
  fee identification, rate clustering, or references transaction/acquiring Excel files.
  This skill analyzes transaction tables to identify commission rate clusters and
  understand fee structures in financial data.
---

# Transaction Analysis Skill

## Purpose

This skill analyzes transaction tables (Excel files) to identify clusters of transactions
with different commission rates. It helps users understand:
- What commission rates are applied to transactions
- Whether rates vary or are constant
- Whether commissions include fixed minimal fees

## Available Tools

### 1. `inspect_table`

**Purpose:** Examine the structure of an Excel file before analysis.

**Parameters:**
- `file_path` (required): Absolute path to the Excel file

**Returns:**
- Column names
- Sample rows (first 5 rows)
- Basic statistics for numeric columns
- Data types of each column

**Usage:** Always call this tool first to understand the table structure before deciding
which analysis algorithm to use.

### 2. `analyze_transactions_sorting`

**Purpose:** Analyze transactions where commission is calculated as a simple percentage of
the transaction amount (commission = rate × amount).

**Parameters:**
- `file_path` (required): Path to the Excel file
- `amount_column` (required): Name of the column containing transaction amounts
- `commission_column` (required): Name of the column containing commission values

**When to use:** When the table has a single commission column and no minimal fee column.

**Returns:** Identified rate clusters with transaction counts.

### 3. `analyze_transactions_kmeans`

**Purpose:** Analyze transactions where commission includes a minimal fee component
(commission = rate × amount + minimal_fee).

**Parameters:**
- `file_path` (required): Path to the Excel file
- `amount_column` (required): Name of the column containing transaction amounts
- `commission_column` (required): Name of the column containing commission values
- `minimal_fee_column` (optional): Name of the column containing minimal fee values

**When to use:** When the table has both a commission column AND evidence of minimal fee
components in the commission structure.

**Returns:** Identified rate and fee clusters.

## Algorithm Selection Logic

Follow this decision tree after calling `inspect_table`:

```
1. Call inspect_table to examine the file
   |
2. Check commission values in the data
   |
   +-- All commission values are identical (constant)?
   |   |
   |   YES → Return the constant commission value directly
   |         (No algorithm needed)
   |
   +-- Commission values vary?
       |
       3. Check for minimal fee column or evidence
          |
          +-- Table has commission column ONLY (no minimal fee column)?
          |   |
          |   → Use analyze_transactions_sorting
          |     (Simple: commission = rate × amount)
          |
          +-- Table has commission AND minimal fee column?
          |   OR commission doesn't divide evenly by amount?
              |
              → Use analyze_transactions_kmeans
                (Complex: commission = rate × amount + minimal_fee)
```

## Column Detection Guidelines

Common column names for transaction amounts:
- `Amount`, `amount`, `Transaction Amount`, `Sum`, `Value`

Common column names for commissions:
- `commission`, `Commission`, `Commission amount`, `Fee`, `Commission Amount`

Common column names for minimal fees:
- `minimal_fee`, `Minimal Fee`, `Fixed Fee`, `Base Fee`

## Expected Input Format

- **File format:** Excel files (.xlsx, .xls)
- **Amount format:** Numeric values (may use comma as decimal separator: "22,80")
- **Commission format:** Numeric values
- **Currency columns:** Expected but not required for analysis

## Example Usage Flows

### Flow 1: Constant Commission

```
User: "Analyze the BLOGWIZARRO transaction file"

1. MCP Client searches /data for matching file
2. Call inspect_table(file_path="/data/BLOGWIZARRO_LTD_acquiring_monthly-202511.xlsx")
3. Observe that all commission values are 5.0 EUR
4. Return: "All transactions have a constant commission of 5.00 EUR"
```

### Flow 2: Variable Rate Analysis

```
User: "What rates are used in the codedtea transactions?"

1. MCP Client searches /data for matching file
2. Call inspect_table(file_path="/data/codedtea-ltd-(fst)-372-report-payments-202511.xlsx")
3. Observe commission varies, no minimal fee column
4. Call analyze_transactions_sorting(
     file_path="/data/codedtea-ltd-(fst)-372-report-payments-202511.xlsx",
     amount_column="Amount",
     commission_column="Commission amount"
   )
5. Return identified rate clusters
```

### Flow 3: Complex Fee Structure

```
User: "Analyze lingo ventures payouts"

1. MCP Client searches /data for matching file
2. Call inspect_table(file_path="/data/lingo-ventures-payouts-20445-report-payouts-202511.xlsx")
3. Check if minimal fee pattern exists
4. Call appropriate algorithm based on findings
5. Return analysis results
```

## File Resolution

This server does NOT perform file resolution. The MCP client is responsible for:
1. Searching the `/data` directory for files matching user descriptions
2. Using case-insensitive fuzzy matching on filenames
3. Presenting candidates to user if multiple matches found
4. Providing the absolute file path to these tools

## Error Handling

All tools return structured error responses:
- File not found: `{"error": "File not found", "path": "..."}`
- Invalid format: `{"error": "Unable to read file", "details": "..."}`
- Missing columns: `{"error": "Column not found", "column": "...", "available": [...]}`
