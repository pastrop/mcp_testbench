"""Programmatic Tool Calling Agent for Combined Contract and Transaction Analysis.

This module implements the Anthropic Tool Runner pattern for handling queries that
require both contract lookup and transaction analysis in a single request.

Architecture:
    - Uses @beta_tool decorator to define tools
    - Tool Runner handles the agentic loop automatically
    - Claude can call multiple tools in parallel when they are independent
    - Supports combined queries like "Get contractual fee for X and compare with transactions"

Example usage:
    from src.agent.programmatic_agent import run_combined_analysis

    result = run_combined_analysis(
        "Give me the contractual transaction fee rate for BLOGWIZARRO LTD "
        "and tell me what fees are charged in their transaction table"
    )
"""

import json
import logging
from pathlib import Path
from typing import Any

import anthropic
from anthropic import beta_tool

# Project paths
PROJECT_ROOT = Path(__file__).parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
CONTRACTS_FILE = DATA_DIR / "contracts_data.json"

# Model configuration
MODEL = "claude-sonnet-4-5-20250929"

# Logging setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# System prompt for the combined analysis agent
COMBINED_ANALYSIS_SYSTEM_PROMPT = """You are a financial analyst assistant specialized in comparing
contractual terms with actual transaction data.

When users ask about vendor fees, you should:
1. Look up contractual rates using the lookup_contract tool to find what rates are specified in the contract
2. Analyze actual transaction data using inspect_table first to understand the data structure
3. Then use the appropriate analysis tool (analyze_transactions_sorting or analyze_transactions_kmeans)
   based on the inspection results
4. Compare the contractual rates with the actual rates found in transactions
5. Highlight any discrepancies between contractual and actual rates

IMPORTANT GUIDELINES:
- You CAN and SHOULD call multiple tools in parallel when they are independent
  (e.g., lookup_contract and inspect_table can run simultaneously)
- Always call inspect_table BEFORE calling analyze_transactions_* tools
- Use analyze_transactions_sorting when commission = rate × amount (no minimal fee)
- Use analyze_transactions_kmeans when commission = rate × amount + minimal_fee
- The algorithm_recommendation from inspect_table tells you which algorithm to use

When comparing rates:
- Contractual rates are usually expressed as percentages (e.g., "2.5%")
- Transaction analysis returns rate_percent values that should match contractual rates
- Consider a match if rates are within 0.1% of each other
- Report any significant discrepancies clearly
"""


def _load_contracts_data() -> list[dict[str, Any]]:
    """Load contracts data from JSON file."""
    from src.financial_tools_server.tools.contract_lookup import load_contracts_data
    return load_contracts_data(CONTRACTS_FILE)


def _find_transaction_file(query: str) -> str | None:
    """Find a transaction Excel file matching the query.

    Args:
        query: Search query (vendor name).

    Returns:
        File path if found, None otherwise.
    """
    from rapidfuzz import fuzz

    if not DATA_DIR.exists():
        return None

    matches = []
    query_lower = query.lower()

    for file_path in DATA_DIR.glob("*.xlsx"):
        file_name = file_path.name.lower()
        score = max(
            fuzz.partial_ratio(query_lower, file_name),
            fuzz.token_set_ratio(query_lower, file_name),
        )
        if score >= 50:
            matches.append((str(file_path), score))

    matches.sort(key=lambda x: x[1], reverse=True)
    return matches[0][0] if matches else None


# =============================================================================
# Tool Definitions using @beta_tool decorator
# =============================================================================

@beta_tool
def lookup_contract(query: str, extract_financial_terms: bool = True) -> str:
    """Look up contractual fee rates for a vendor from the contracts database.

    Use this tool when you need to find what fee rates, commissions, or financial
    terms are specified in a vendor's contract. This searches through all available
    contracts using fuzzy matching on the vendor/company name.

    Args:
        query: The vendor name, company name, or contract identifier to search for.
               Examples: "BLOGWIZARRO", "Finthesis", "codedtea", "lingo ventures"
        extract_financial_terms: Whether to extract rates, fees, and reserves from
                                 the contract text. Defaults to True.

    Returns:
        JSON string containing:
        - contract: Matched contract metadata (file_name, file_path)
        - match_score: Fuzzy match score (0-100)
        - financial_info: Extracted financial terms including:
          - rates: Transaction rates, processing fees, commission rates
          - fees: Chargeback fees, refund fees, monthly fees, etc.
          - rolling_reserve: Reserve percentages and terms
          - currency_terms: Currency-specific rates
    """
    from src.financial_tools_server.tools.contract_lookup import (
        find_matching_contracts,
        decode_pdf_content,
        extract_financial_info,
    )

    logger.info(f"lookup_contract called with query='{query}'")

    contracts = _load_contracts_data()

    if not contracts:
        return json.dumps({
            "error": "No contracts data available",
            "query": query,
        })

    matches = find_matching_contracts(query, contracts, threshold=50)

    if not matches:
        return json.dumps({
            "error": "No matching contracts found",
            "query": query,
            "suggestion": "Try a different spelling or a partial company name",
        })

    # If multiple close matches, return candidates
    if len(matches) > 1:
        top_score = matches[0][1]
        close_matches = [(c, s) for c, s in matches if s >= top_score - 10]
        if len(close_matches) > 1:
            return json.dumps({
                "status": "multiple_matches",
                "message": "Multiple contracts match this query. Using the best match.",
                "best_match": {
                    "file_name": matches[0][0].get("file_name"),
                    "score": matches[0][1],
                },
                "other_candidates": [
                    {"file_name": c.get("file_name"), "score": s}
                    for c, s in close_matches[1:5]
                ],
            })

    # Get the best match
    best_match, score = matches[0]

    result = {
        "status": "found",
        "contract": {
            "file_name": best_match.get("file_name"),
            "file_path": best_match.get("file_path"),
        },
        "match_score": score,
    }

    # Extract financial information if requested
    if extract_financial_terms:
        pdf_data = best_match.get("pdf_data", "")
        if pdf_data:
            text = decode_pdf_content(pdf_data)
            financial_info = extract_financial_info(text)
            result["financial_info"] = financial_info
        else:
            result["financial_info"] = {"error": "No PDF data available for this contract"}

    return json.dumps(result)


@beta_tool
def inspect_table(file_path: str) -> str:
    """Inspect an Excel transaction file to understand its structure before analysis.

    ALWAYS call this tool BEFORE calling analyze_transactions_sorting or
    analyze_transactions_kmeans. This tool examines the file structure and
    recommends which analysis algorithm to use.

    Args:
        file_path: Absolute path to the Excel file (.xlsx or .xls).
                   If you only have a vendor name, use find_transaction_file first.

    Returns:
        JSON string containing:
        - columns: List of all column names
        - row_count: Number of rows in the file
        - sample_rows: First few rows of data
        - potential_amount_columns: Detected columns that may contain transaction amounts
        - potential_commission_columns: Detected columns that may contain fees/commissions
        - commission_analysis: Whether commission values are constant or variable
        - minimal_fee_detection: Whether a minimal fee pattern was detected
        - algorithm_recommendation: Which algorithm to use:
          - "none" if commission is constant (no analysis needed)
          - "sorting" for simple rate × amount structures
          - "kmeans" for rate × amount + minimal_fee structures
    """
    import numpy as np
    import pandas as pd

    logger.info(f"inspect_table called with file_path='{file_path}'")

    path = Path(file_path)

    if not path.exists():
        return json.dumps({"error": "File not found", "path": file_path})

    if path.suffix.lower() not in (".xlsx", ".xls"):
        return json.dumps({
            "error": "Invalid file format",
            "expected": ".xlsx or .xls",
            "got": path.suffix,
        })

    try:
        df = pd.read_excel(path)
    except Exception as e:
        return json.dumps({"error": "Unable to read file", "details": str(e)})

    def parse_numeric(series: pd.Series) -> pd.Series:
        if pd.api.types.is_string_dtype(series):
            return pd.to_numeric(
                series.astype(str).str.replace(",", ".").str.strip(),
                errors="coerce",
            )
        return pd.to_numeric(series, errors="coerce")

    columns = df.columns.tolist()
    sample_rows = df.head(5).to_dict(orient="records")

    # Detect column types
    commission_cols = [
        c for c in columns
        if any(kw in c.lower() for kw in ["commission", "fee"])
        and "currency" not in c.lower()
    ]

    amount_cols = [
        c for c in columns
        if any(kw in c.lower() for kw in ["amount", "sum", "value", "total"])
        and "currency" not in c.lower()
    ]

    minimal_fee_keywords = ["minimal", "minimum", "min_fee", "fixed", "base_fee", "flat"]
    minimal_fee_cols = [
        c for c in columns
        if any(kw in c.lower() for kw in minimal_fee_keywords)
    ]

    # Analyze commission columns
    commission_analysis = {}
    for col in commission_cols:
        parsed = parse_numeric(df[col])
        unique = parsed.dropna().unique()
        if len(unique) == 1:
            commission_analysis[col] = {
                "is_constant": True,
                "constant_value": float(unique[0]),
            }
        elif len(unique) > 0:
            commission_analysis[col] = {
                "is_constant": False,
                "unique_count": len(unique),
                "value_range": [float(parsed.min()), float(parsed.max())],
            }

    # Detect minimal fee pattern
    minimal_fee_detection = None
    if amount_cols and commission_cols:
        amounts = parse_numeric(df[amount_cols[0]]).abs()
        commissions = parse_numeric(df[commission_cols[0]]).abs()

        valid_mask = (amounts > 0) & amounts.notna() & commissions.notna()
        if valid_mask.sum() >= 10:
            valid_amounts = amounts[valid_mask].values
            valid_commissions = commissions[valid_mask].values
            rates = valid_commissions / valid_amounts

            rate_mean = np.mean(rates)
            rate_cv = np.std(rates) / rate_mean if rate_mean > 0 else 0

            if rate_cv < 0.001:
                minimal_fee_detection = {
                    "detected": False,
                    "reason": "rates_consistent",
                    "rate_cv": round(float(rate_cv), 6),
                }
            else:
                median_amt = np.median(valid_amounts)
                small_rates = rates[valid_amounts < median_amt]
                large_rates = rates[valid_amounts >= median_amt]

                if len(small_rates) > 5 and len(large_rates) > 5:
                    if np.mean(small_rates) > np.mean(large_rates) * 1.05:
                        coeffs = np.polyfit(valid_amounts, valid_commissions, 1)
                        minimal_fee_detection = {
                            "detected": True,
                            "reason": "small_transactions_higher_rate",
                            "estimated_rate_percent": round(float(coeffs[0]) * 100, 4),
                            "estimated_minimal_fee": round(float(max(0, coeffs[1])), 4),
                        }
                    else:
                        minimal_fee_detection = {
                            "detected": False,
                            "reason": "no_clear_pattern",
                            "rate_cv": round(float(rate_cv), 6),
                        }

    # Generate algorithm recommendation
    all_constant = all(
        a.get("is_constant", False) for a in commission_analysis.values()
    ) if commission_analysis else False

    if all_constant and commission_analysis:
        constant_values = [
            a.get("constant_value")
            for a in commission_analysis.values()
            if a.get("is_constant")
        ]
        algorithm_recommendation = {
            "algorithm": "none",
            "reason": "constant_commission",
            "message": "All commission values are constant. No clustering needed.",
            "constant_values": constant_values,
        }
    elif minimal_fee_cols:
        algorithm_recommendation = {
            "algorithm": "kmeans",
            "reason": "minimal_fee_column_detected",
            "message": f"Found minimal fee column(s): {minimal_fee_cols}. Use kmeans algorithm.",
        }
    elif minimal_fee_detection and minimal_fee_detection.get("detected"):
        algorithm_recommendation = {
            "algorithm": "kmeans",
            "reason": "minimal_fee_pattern_detected",
            "message": "Commission pattern suggests minimal fee component. Use kmeans algorithm.",
        }
    else:
        algorithm_recommendation = {
            "algorithm": "sorting",
            "reason": "simple_rate_structure",
            "message": "No minimal fee detected. Commission appears to be rate × amount. Use sorting algorithm.",
        }

    return json.dumps({
        "file_path": file_path,
        "row_count": len(df),
        "columns": columns,
        "sample_rows": sample_rows,
        "potential_amount_columns": amount_cols,
        "potential_commission_columns": commission_cols,
        "potential_minimal_fee_columns": minimal_fee_cols,
        "commission_analysis": commission_analysis,
        "minimal_fee_detection": minimal_fee_detection,
        "algorithm_recommendation": algorithm_recommendation,
    })


@beta_tool
def find_transaction_file(vendor_name: str) -> str:
    """Find the transaction Excel file for a given vendor name.

    Use this tool when you have a vendor name but need to find the corresponding
    transaction file path. This uses fuzzy matching to find the best matching file.

    Args:
        vendor_name: The vendor or company name to search for.
                     Examples: "BLOGWIZARRO", "codedtea", "lingo ventures"

    Returns:
        JSON string containing:
        - file_path: The full path to the matching Excel file
        - file_name: Just the filename
        - match_score: How well the name matched (0-100)
        - error: Error message if no file was found
    """
    from rapidfuzz import fuzz

    logger.info(f"find_transaction_file called with vendor_name='{vendor_name}'")

    if not DATA_DIR.exists():
        return json.dumps({
            "error": "Data directory not found",
            "path": str(DATA_DIR),
        })

    matches = []
    query_lower = vendor_name.lower()

    for file_path in DATA_DIR.glob("*.xlsx"):
        file_name = file_path.name.lower()
        score = max(
            fuzz.partial_ratio(query_lower, file_name),
            fuzz.token_set_ratio(query_lower, file_name),
        )
        if score >= 40:  # Lower threshold for finding files
            matches.append({
                "file_path": str(file_path),
                "file_name": file_path.name,
                "score": score,
            })

    if not matches:
        available_files = [f.name for f in DATA_DIR.glob("*.xlsx")]
        return json.dumps({
            "error": f"No transaction file found for '{vendor_name}'",
            "available_files": available_files,
            "suggestion": "Try a different spelling or check the available files list",
        })

    matches.sort(key=lambda x: x["score"], reverse=True)
    best_match = matches[0]

    result = {
        "file_path": best_match["file_path"],
        "file_name": best_match["file_name"],
        "match_score": best_match["score"],
    }

    if len(matches) > 1:
        result["other_matches"] = [
            {"file_name": m["file_name"], "score": m["score"]}
            for m in matches[1:4]
        ]

    return json.dumps(result)


@beta_tool
def analyze_transactions_sorting(
    file_path: str,
    amount_column: str,
    commission_column: str,
    min_rate_diff: float = 0.001,
    min_cluster_size: int = 10,
) -> str:
    """Analyze transactions using sorting-based clustering to find rate clusters.

    Use this algorithm when commission = rate × amount (NO minimal fee component).
    The inspect_table tool will recommend this algorithm when appropriate.

    IMPORTANT: Always call inspect_table first to get the correct column names
    and verify this is the right algorithm to use.

    Args:
        file_path: Absolute path to the Excel file.
        amount_column: Name of the column containing transaction amounts.
                       Get this from inspect_table's potential_amount_columns.
        commission_column: Name of the column containing commission/fee values.
                          Get this from inspect_table's potential_commission_columns.
        min_rate_diff: Minimum difference between rate clusters (default 0.001 = 0.1%).
        min_cluster_size: Minimum transactions to form a valid cluster (default 10).

    Returns:
        JSON string containing:
        - algorithm: "sorting"
        - total_transactions: Total number of rows
        - valid_transactions: Rows with valid numeric data
        - num_clusters: Number of rate clusters found
        - clusters: List of clusters, each with:
          - rate_percent: The commission rate as a percentage
          - transaction_count: Number of transactions in this cluster
          - percentage_of_total: What % of all transactions are in this cluster
          - min_rate_percent, max_rate_percent: Rate range in the cluster
        - summary: Overall statistics including dominant rate
    """
    import pandas as pd

    logger.info(f"analyze_transactions_sorting called: file={file_path}, "
                f"amount_col={amount_column}, commission_col={commission_column}")

    from src.transaction_analysis.scripts.sorting_algorithm import analyze_rates_sorting

    path = Path(file_path)
    if not path.exists():
        return json.dumps({"error": "File not found", "path": file_path})

    try:
        df = pd.read_excel(path)
    except Exception as e:
        return json.dumps({"error": "Unable to read file", "details": str(e)})

    if amount_column not in df.columns:
        return json.dumps({
            "error": f"Column '{amount_column}' not found",
            "available_columns": df.columns.tolist(),
        })

    if commission_column not in df.columns:
        return json.dumps({
            "error": f"Column '{commission_column}' not found",
            "available_columns": df.columns.tolist(),
        })

    def parse_numeric(series: pd.Series) -> pd.Series:
        if pd.api.types.is_string_dtype(series):
            return pd.to_numeric(
                series.astype(str).str.replace(",", ".").str.strip(),
                errors="coerce",
            )
        return pd.to_numeric(series, errors="coerce")

    amounts = parse_numeric(df[amount_column]).abs()
    commissions = parse_numeric(df[commission_column]).abs()

    result = analyze_rates_sorting(
        amounts=amounts,
        commissions=commissions,
        min_rate_diff=min_rate_diff,
        min_cluster_size=min_cluster_size,
    )

    result["file_path"] = file_path
    result["amount_column"] = amount_column
    result["commission_column"] = commission_column

    return json.dumps(result)


@beta_tool
def analyze_transactions_kmeans(
    file_path: str,
    amount_column: str,
    commission_column: str,
    n_clusters: int | None = None,
    min_cluster_size: int = 10,
) -> str:
    """Analyze transactions using k-means clustering for complex fee structures.

    Use this algorithm when commission = rate × amount + minimal_fee.
    The inspect_table tool will recommend this algorithm when it detects
    a minimal fee pattern in the data.

    IMPORTANT: Always call inspect_table first to get the correct column names
    and verify this is the right algorithm to use.

    Args:
        file_path: Absolute path to the Excel file.
        amount_column: Name of the column containing transaction amounts.
                       Get this from inspect_table's potential_amount_columns.
        commission_column: Name of the column containing commission/fee values.
                          Get this from inspect_table's potential_commission_columns.
        n_clusters: Number of clusters (if None, auto-detect optimal number).
        min_cluster_size: Minimum transactions per cluster (default 10).

    Returns:
        JSON string containing:
        - algorithm: "kmeans"
        - total_transactions: Total number of rows
        - valid_transactions: Rows with valid numeric data
        - num_clusters: Number of clusters found
        - clusters: List of clusters, each with:
          - rate_percent: The commission rate as a percentage
          - minimal_fee: The fixed fee component
          - transaction_count: Number of transactions in this cluster
          - r_squared: How well the linear model fits (1.0 = perfect fit)
          - amount_range: [min, max] transaction amounts in this cluster
        - summary: Overall statistics including dominant rate and fee
    """
    import pandas as pd

    logger.info(f"analyze_transactions_kmeans called: file={file_path}, "
                f"amount_col={amount_column}, commission_col={commission_column}")

    from src.transaction_analysis.scripts.kmeans_algorithm import analyze_rates_kmeans

    path = Path(file_path)
    if not path.exists():
        return json.dumps({"error": "File not found", "path": file_path})

    try:
        df = pd.read_excel(path)
    except Exception as e:
        return json.dumps({"error": "Unable to read file", "details": str(e)})

    if amount_column not in df.columns:
        return json.dumps({
            "error": f"Column '{amount_column}' not found",
            "available_columns": df.columns.tolist(),
        })

    if commission_column not in df.columns:
        return json.dumps({
            "error": f"Column '{commission_column}' not found",
            "available_columns": df.columns.tolist(),
        })

    def parse_numeric(series: pd.Series) -> pd.Series:
        if pd.api.types.is_string_dtype(series):
            return pd.to_numeric(
                series.astype(str).str.replace(",", ".").str.strip(),
                errors="coerce",
            )
        return pd.to_numeric(series, errors="coerce")

    amounts = parse_numeric(df[amount_column]).abs()
    commissions = parse_numeric(df[commission_column]).abs()

    result = analyze_rates_kmeans(
        amounts=amounts,
        commissions=commissions,
        n_clusters=n_clusters,
        min_cluster_size=min_cluster_size,
    )

    result["file_path"] = file_path
    result["amount_column"] = amount_column
    result["commission_column"] = commission_column

    return json.dumps(result)


# =============================================================================
# Main Entry Points
# =============================================================================

def run_combined_analysis(
    user_query: str,
    verbose: bool = True,
) -> str:
    """Run combined contract and transaction analysis using the Tool Runner.

    This function uses the Anthropic Tool Runner to automatically handle
    the agentic loop of tool calls. Claude will:
    1. Analyze the query to understand what's needed
    2. Call appropriate tools (potentially in parallel)
    3. Synthesize results into a coherent response

    Args:
        user_query: The user's natural language query.
                    Example: "Give me the contractual fee for BLOGWIZARRO
                             and compare with their transaction table"
        verbose: Whether to print intermediate steps.

    Returns:
        Claude's final analysis and response as a string.
    """
    client = anthropic.Anthropic()

    if verbose:
        print(f"\n{'='*60}")
        print("🔄 Running Combined Analysis with Tool Runner")
        print(f"{'='*60}")
        print(f"Query: {user_query}")
        print(f"{'='*60}\n")

    # Define all available tools
    tools = [
        lookup_contract,
        find_transaction_file,
        inspect_table,
        analyze_transactions_sorting,
        analyze_transactions_kmeans,
    ]

    # Create the tool runner
    runner = client.beta.messages.tool_runner(
        model=MODEL,
        max_tokens=4096,
        system=COMBINED_ANALYSIS_SYSTEM_PROMPT,
        tools=tools,
        messages=[{"role": "user", "content": user_query}],
    )

    # Iterate through the agentic loop
    message_count = 0
    for message in runner:
        message_count += 1

        if verbose:
            # Show tool calls if any
            for block in message.content:
                if hasattr(block, 'type'):
                    if block.type == "tool_use":
                        print(f"🔧 Tool call: {block.name}")
                        print(f"   Input: {json.dumps(block.input, indent=2)[:200]}...")
                    elif block.type == "text" and block.text:
                        # Show intermediate text if any
                        if message.stop_reason == "tool_use":
                            print(f"💭 {block.text[:200]}...")

    # Get the final message
    final_message = runner.until_done()

    # Extract the text response
    response_text = ""
    for block in final_message.content:
        if hasattr(block, 'type') and block.type == "text":
            response_text += block.text

    if verbose:
        print(f"\n{'='*60}")
        print(f"✅ Analysis complete ({message_count} tool call rounds)")
        print(f"{'='*60}\n")

    return response_text


def run_combined_analysis_streaming(
    user_query: str,
) -> str:
    """Run combined analysis with streaming output.

    Similar to run_combined_analysis but streams the response as it's generated.

    Args:
        user_query: The user's natural language query.

    Returns:
        Claude's final analysis and response as a string.
    """
    client = anthropic.Anthropic()

    tools = [
        lookup_contract,
        find_transaction_file,
        inspect_table,
        analyze_transactions_sorting,
        analyze_transactions_kmeans,
    ]

    runner = client.beta.messages.tool_runner(
        model=MODEL,
        max_tokens=4096,
        system=COMBINED_ANALYSIS_SYSTEM_PROMPT,
        tools=tools,
        messages=[{"role": "user", "content": user_query}],
        stream=True,
    )

    full_response = ""

    for message_stream in runner:
        for event in message_stream:
            # Handle streaming events
            if hasattr(event, 'type'):
                if event.type == "content_block_delta":
                    if hasattr(event.delta, 'text'):
                        print(event.delta.text, end="", flush=True)
                        full_response += event.delta.text

    print()  # Newline after streaming
    return full_response


# =============================================================================
# CLI Entry Point for Testing
# =============================================================================

def main() -> None:
    """CLI entry point for testing the programmatic agent."""
    import sys
    import os

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("Error: ANTHROPIC_API_KEY environment variable not set.")
        sys.exit(1)

    # Default test query
    default_query = (
        "Give me the contractual transaction fee rate for BLOGWIZARRO LTD "
        "and tell me what transaction fees are charged according to their transaction table"
    )

    # Use command line argument if provided
    if len(sys.argv) > 1:
        query = " ".join(sys.argv[1:])
    else:
        query = default_query
        print(f"Using default test query: {query}\n")

    result = run_combined_analysis(query, verbose=True)

    print("\n" + "="*60)
    print("📊 FINAL ANALYSIS")
    print("="*60)
    print(result)


if __name__ == "__main__":
    main()
