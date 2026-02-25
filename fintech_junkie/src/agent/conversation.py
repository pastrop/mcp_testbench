"""Main conversation loop and routing for the financial analysis agent."""

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

import anthropic
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from .classifier import QueryCategory, classify_query, get_entity_from_query
from .programmatic_agent import run_combined_analysis

# Project paths
PROJECT_ROOT = Path(__file__).parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"

# Model configuration
MODEL = "claude-sonnet-4-5-20250929"

# Prompt for LLM-based column detection
COLUMN_DETECTION_PROMPT = """You are analyzing a financial transaction table to identify key columns.

Given the column names and sample data below, identify which columns contain:
1. **Transaction Amount** - The monetary value of each transaction
2. **Commission** - The fee charged per transaction (may also be called "fee", "charge", etc.)
3. **Minimal Fee** - A fixed minimum fee component (optional, may not exist)

Column names: {columns}

Sample data (first 3 rows):
{sample_data}

Respond in this exact JSON format:
{{
    "amount_column": "<column name or null if not found>",
    "commission_column": "<column name or null if not found>",
    "minimal_fee_column": "<column name or null if not found>",
    "reasoning": "<brief explanation of your choices>"
}}

Important:
- Use exact column names as they appear in the list
- Return null (not "null") for any column you cannot confidently identify
- Look for semantic meaning, not just keywords
- Commission columns often contain calculated fees based on transaction amounts
- Amount columns typically have larger numeric values than commission columns
"""


def _detect_columns_with_llm(
    client: anthropic.Anthropic,
    columns: list[str],
    sample_rows: list[dict],
) -> dict[str, str | None]:
    """Use LLM to detect column types when keyword matching fails.

    Args:
        client: Anthropic client.
        columns: List of column names.
        sample_rows: Sample data rows.

    Returns:
        Dictionary with detected column names for amount, commission, minimal_fee.
    """
    import json

    # Format sample data for the prompt
    sample_lines = []
    for i, row in enumerate(sample_rows[:3], 1):
        row_str = ", ".join(f"{k}: {v}" for k, v in row.items())
        sample_lines.append(f"Row {i}: {row_str}")
    sample_data = "\n".join(sample_lines)

    prompt = COLUMN_DETECTION_PROMPT.format(
        columns=", ".join(columns),
        sample_data=sample_data,
    )

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}],
        )

        content = response.content[0].text.strip()

        # Extract JSON from response (handle markdown code blocks)
        if "```" in content:
            start = content.find("{")
            end = content.rfind("}") + 1
            content = content[start:end]

        result = json.loads(content)

        return {
            "amount_column": result.get("amount_column"),
            "commission_column": result.get("commission_column"),
            "minimal_fee_column": result.get("minimal_fee_column"),
            "reasoning": result.get("reasoning", ""),
            "llm_detected": True,
        }

    except Exception as e:
        return {
            "amount_column": None,
            "commission_column": None,
            "minimal_fee_column": None,
            "error": str(e),
            "llm_detected": False,
        }


class FinancialAgent:
    """Conversational agent for financial analysis tasks."""

    def __init__(self) -> None:
        """Initialize the agent."""
        self.anthropic_client = anthropic.Anthropic()
        self.financial_tools_session: ClientSession | None = None
        self.transaction_session: ClientSession | None = None

    async def connect_to_servers(self) -> None:
        """Connect to both MCP servers."""
        # Note: In a real implementation, we would connect to running MCP servers.
        # For simplicity, we'll use the tools directly in this implementation.
        pass

    def _find_matching_files(self, query: str) -> list[str]:
        """Find Excel files in data directory matching the query.

        Args:
            query: Search query.

        Returns:
            List of matching file paths.
        """
        from rapidfuzz import fuzz

        if not DATA_DIR.exists():
            return []

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
        return [m[0] for m in matches]

    def _call_financial_tool(self, tool_name: str, **kwargs: Any) -> dict[str, Any]:
        """Call a financial tools server function directly.

        Args:
            tool_name: Name of the tool to call.
            **kwargs: Arguments for the tool.

        Returns:
            Tool result.
        """
        # Import and call tools directly (simplified approach)
        from src.financial_tools_server.tools.contract_lookup import (
            decode_pdf_content,
            extract_financial_info,
            find_matching_contracts,
            load_contracts_data,
        )

        contracts_file = DATA_DIR / "contracts_data.json"

        if tool_name == "list_contracts":
            contracts = load_contracts_data(contracts_file)
            return {
                "total_contracts": len(contracts),
                "contracts": [
                    {"file_name": c.get("file_name", ""), "file_path": c.get("file_path", "")}
                    for c in contracts
                ],
            }

        elif tool_name == "lookup_contract":
            query = kwargs.get("query", "")
            contracts = load_contracts_data(contracts_file)
            matches = find_matching_contracts(query, contracts, threshold=50)

            if not matches:
                return {"error": "No matching contracts found", "query": query}

            if len(matches) > 1:
                top_score = matches[0][1]
                close_matches = [(c, s) for c, s in matches if s >= top_score - 10]
                if len(close_matches) > 1:
                    return {
                        "status": "multiple_matches",
                        "candidates": [
                            {"file_name": c.get("file_name"), "file_path": c.get("file_path"), "score": s}
                            for c, s in close_matches[:5]
                        ],
                    }

            best_match, score = matches[0]
            pdf_data = best_match.get("pdf_data", "")

            if pdf_data:
                text = decode_pdf_content(pdf_data)
                financial_info = extract_financial_info(text)
            else:
                financial_info = {"error": "No PDF data available"}

            return {
                "status": "found",
                "contract": {
                    "file_name": best_match.get("file_name"),
                    "file_path": best_match.get("file_path"),
                },
                "match_score": score,
                "financial_info": financial_info,
            }

        return {"error": f"Unknown tool: {tool_name}"}

    def _call_transaction_tool(self, tool_name: str, **kwargs: Any) -> dict[str, Any]:
        """Call a transaction analysis server function directly.

        Args:
            tool_name: Name of the tool to call.
            **kwargs: Arguments for the tool.

        Returns:
            Tool result.
        """
        import numpy as np
        import pandas as pd

        def parse_numeric(series: pd.Series) -> pd.Series:
            """Parse numeric values that may use comma as decimal separator."""
            if pd.api.types.is_string_dtype(series):
                return pd.to_numeric(
                    series.astype(str).str.replace(",", ".").str.strip(),
                    errors="coerce",
                )
            return pd.to_numeric(series, errors="coerce")

        file_path = kwargs.get("file_path", "")

        if not file_path or not Path(file_path).exists():
            return {"error": "File not found", "path": file_path}

        if tool_name == "inspect_table":
            try:
                df = pd.read_excel(file_path)
                columns = df.columns.tolist()
                sample_rows = df.head(5).to_dict(orient="records")

                # Find commission columns (exclude currency columns)
                commission_cols = [
                    c for c in columns
                    if "commission" in c.lower() and "currency" not in c.lower()
                ]

                # Find amount columns
                amount_cols = [
                    c for c in columns
                    if any(kw in c.lower() for kw in ["amount", "sum", "value", "total"])
                    and "currency" not in c.lower()
                ]

                # Find minimal fee columns
                minimal_fee_keywords = ["minimal", "minimum", "min_fee", "fixed", "base_fee", "flat"]
                minimal_fee_cols = [
                    c for c in columns
                    if any(kw in c.lower() for kw in minimal_fee_keywords)
                ]

                # LLM fallback for column detection
                llm_detection = None
                if not commission_cols or not amount_cols:
                    llm_detection = _detect_columns_with_llm(
                        self.anthropic_client,
                        columns,
                        sample_rows[:3],
                    )

                    if llm_detection.get("llm_detected"):
                        if not commission_cols and llm_detection.get("commission_column"):
                            commission_cols = [llm_detection["commission_column"]]
                        if not amount_cols and llm_detection.get("amount_column"):
                            amount_cols = [llm_detection["amount_column"]]
                        if not minimal_fee_cols and llm_detection.get("minimal_fee_column"):
                            minimal_fee_cols = [llm_detection["minimal_fee_column"]]

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
                            "range": [float(parsed.min()), float(parsed.max())],
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

                        rate_cv = np.std(rates) / np.mean(rates) if np.mean(rates) > 0 else 0

                        if rate_cv < 0.001:
                            minimal_fee_detection = {"detected": False, "reason": "rates_consistent"}
                        else:
                            # Check if small transactions have higher rates
                            median_amt = np.median(valid_amounts)
                            small_rates = rates[valid_amounts < median_amt]
                            large_rates = rates[valid_amounts >= median_amt]

                            if len(small_rates) > 5 and len(large_rates) > 5:
                                if np.mean(small_rates) > np.mean(large_rates) * 1.05:
                                    # Estimate fee via linear regression
                                    coeffs = np.polyfit(valid_amounts, valid_commissions, 1)
                                    minimal_fee_detection = {
                                        "detected": True,
                                        "reason": "small_transactions_higher_rate",
                                        "estimated_rate_percent": round(coeffs[0] * 100, 4),
                                        "estimated_minimal_fee": round(max(0, coeffs[1]), 4),
                                    }
                                else:
                                    minimal_fee_detection = {"detected": False, "reason": "no_clear_pattern"}

                # Generate algorithm recommendation
                all_constant = all(a.get("is_constant", False) for a in commission_analysis.values())

                if all_constant:
                    algorithm_recommendation = {
                        "algorithm": "none",
                        "reason": "constant_commission",
                    }
                elif minimal_fee_cols:
                    algorithm_recommendation = {
                        "algorithm": "kmeans",
                        "reason": "minimal_fee_column_detected",
                        "minimal_fee_columns": minimal_fee_cols,
                    }
                elif minimal_fee_detection and minimal_fee_detection.get("detected"):
                    algorithm_recommendation = {
                        "algorithm": "kmeans",
                        "reason": "minimal_fee_pattern_detected",
                    }
                else:
                    algorithm_recommendation = {
                        "algorithm": "sorting",
                        "reason": "simple_rate_structure",
                    }

                result = {
                    "file_path": file_path,
                    "row_count": len(df),
                    "columns": columns,
                    "sample_rows": sample_rows[:3],
                    "potential_amount_columns": amount_cols,
                    "potential_commission_columns": commission_cols,
                    "potential_minimal_fee_columns": minimal_fee_cols,
                    "commission_analysis": commission_analysis,
                    "minimal_fee_detection": minimal_fee_detection,
                    "algorithm_recommendation": algorithm_recommendation,
                }

                # Include LLM detection info if it was used
                if llm_detection and llm_detection.get("llm_detected"):
                    result["llm_column_detection"] = {
                        "used": True,
                        "reasoning": llm_detection.get("reasoning", ""),
                    }

                return result

            except Exception as e:
                return {"error": str(e)}

        elif tool_name == "analyze_transactions_sorting":
            amount_col = kwargs.get("amount_column", "")
            commission_col = kwargs.get("commission_column", "")
            min_rate_diff = kwargs.get("min_rate_diff", 0.001)
            min_cluster_size = kwargs.get("min_cluster_size", 10)

            try:
                from src.transaction_analysis.scripts.sorting_algorithm import analyze_rates_sorting

                df = pd.read_excel(file_path)
                amounts = parse_numeric(df[amount_col]).abs()
                commissions = parse_numeric(df[commission_col]).abs()

                result = analyze_rates_sorting(
                    amounts=amounts,
                    commissions=commissions,
                    min_rate_diff=min_rate_diff,
                    min_cluster_size=min_cluster_size,
                )
                result["file_path"] = file_path
                return result

            except Exception as e:
                return {"error": str(e)}

        elif tool_name == "analyze_transactions_kmeans":
            amount_col = kwargs.get("amount_column", "")
            commission_col = kwargs.get("commission_column", "")
            n_clusters = kwargs.get("n_clusters", None)
            min_cluster_size = kwargs.get("min_cluster_size", 10)

            try:
                from src.transaction_analysis.scripts.kmeans_algorithm import analyze_rates_kmeans

                df = pd.read_excel(file_path)
                amounts = parse_numeric(df[amount_col]).abs()
                commissions = parse_numeric(df[commission_col]).abs()

                result = analyze_rates_kmeans(
                    amounts=amounts,
                    commissions=commissions,
                    n_clusters=n_clusters,
                    min_cluster_size=min_cluster_size,
                )
                result["file_path"] = file_path
                return result

            except Exception as e:
                return {"error": str(e)}

        return {"error": f"Unknown tool: {tool_name}"}

    def _format_financial_info(self, info: dict[str, Any]) -> str:
        """Format financial information for display.

        Args:
            info: Financial information dictionary.

        Returns:
            Formatted string.
        """
        lines = []

        if info.get("error"):
            return f"Error: {info['error']}"

        if info.get("rates"):
            lines.append("\n📊 RATES:")
            for item in info["rates"][:5]:
                ctx = item.get("context", "")
                vals = item.get("values", [])
                lines.append(f"  • {ctx}")
                if vals:
                    lines.append(f"    Values: {', '.join(str(v) + '%' for v in vals)}")

        if info.get("fees"):
            lines.append("\n💰 FEES:")
            for item in info["fees"][:5]:
                ctx = item.get("context", "")
                lines.append(f"  • {ctx}")

        if info.get("rolling_reserve"):
            lines.append("\n🏦 ROLLING RESERVE:")
            for item in info["rolling_reserve"][:3]:
                ctx = item.get("context", "")
                vals = item.get("values", [])
                lines.append(f"  • {ctx}")
                if vals:
                    lines.append(f"    Values: {', '.join(str(v) + '%' for v in vals)}")

        if info.get("currency_terms"):
            lines.append("\n💱 CURRENCY-SPECIFIC TERMS:")
            for item in info["currency_terms"][:5]:
                ctx = item.get("context", "")
                lines.append(f"  • {ctx}")

        if not any([info.get("rates"), info.get("fees"), info.get("rolling_reserve")]):
            lines.append("\nNo specific financial terms found in the extracted text.")
            lines.append("The contract may use different terminology or formatting.")

        return "\n".join(lines)

    def _format_transaction_analysis(self, result: dict[str, Any]) -> str:
        """Format transaction analysis results for display.

        Args:
            result: Analysis result dictionary.

        Returns:
            Formatted string.
        """
        if result.get("error"):
            return f"Error: {result['error']}"

        lines = []

        if result.get("commission_analysis"):
            # This is from inspect_table
            lines.append("\n📋 TABLE INSPECTION RESULTS:")
            lines.append(f"  Rows: {result.get('row_count', 'N/A')}")
            lines.append(f"  Columns: {', '.join(result.get('columns', []))}")

            for col, analysis in result.get("commission_analysis", {}).items():
                if analysis.get("is_constant"):
                    lines.append(f"\n  ✅ {col}: CONSTANT VALUE = {analysis['constant_value']}")
                else:
                    lines.append(
                        f"\n  📊 {col}: VARIABLE ({analysis['unique_count']} unique values)"
                    )
                    lines.append(f"     Range: {analysis['range'][0]} - {analysis['range'][1]}")

        elif result.get("clusters") or result.get("rate_clusters"):
            # This is from sorting or kmeans analysis
            algorithm = result.get('algorithm', 'N/A')
            lines.append("\n📊 RATE CLUSTER ANALYSIS RESULTS:")
            lines.append(f"  Algorithm: {algorithm}")
            lines.append(f"  Total transactions: {result.get('total_transactions', 'N/A')}")
            lines.append(f"  Valid transactions: {result.get('valid_transactions', 'N/A')}")

            # Handle new format (clusters) or old format (rate_clusters)
            clusters = result.get("clusters") or result.get("rate_clusters", [])

            if result.get("num_clusters") is not None:
                lines.append(f"  Clusters found: {result.get('num_clusters')}")
                if result.get('outlier_count') is not None:
                    lines.append(f"  Outliers: {result.get('outlier_count', 0)} ({result.get('outlier_percentage', 0)}%)")

            lines.append("\n  Rate Clusters (sorted by transaction count):")
            for cluster in clusters[:10]:
                rate = cluster.get("rate_percent", 0)
                count = cluster.get("transaction_count") or cluster.get("count", 0)
                pct = cluster.get("percentage_of_total", "")
                minimal_fee = cluster.get("minimal_fee")

                line = f"    • {rate:.4f}%"
                if minimal_fee is not None and minimal_fee > 0:
                    line += f" + {minimal_fee:.2f} (minimal fee)"
                line += f" - {count} transactions"
                if pct:
                    line += f" ({pct}%)"
                lines.append(line)

                # Show additional info based on algorithm
                if algorithm == "sorting":
                    std = cluster.get("rate_std_dev", "")
                    if std:
                        lines.append(f"      Range: {cluster.get('min_rate_percent', 0):.4f}% - {cluster.get('max_rate_percent', 0):.4f}%")
                elif algorithm == "kmeans":
                    r_squared = cluster.get("r_squared")
                    if r_squared is not None:
                        lines.append(f"      Fit quality (R²): {r_squared:.4f}")
                    amount_range = cluster.get("amount_range")
                    if amount_range:
                        lines.append(f"      Amount range: {amount_range[0]:.2f} - {amount_range[1]:.2f}")

            summary = result.get("summary", {})
            if summary:
                lines.append(f"\n  Summary:")
                if summary.get('dominant_rate_percent'):
                    lines.append(f"    Dominant rate: {summary.get('dominant_rate_percent')}%")
                if summary.get('dominant_fee') and summary.get('dominant_fee') > 0:
                    lines.append(f"    Dominant minimal fee: {summary.get('dominant_fee')}")
                if summary.get('dominant_cluster_coverage'):
                    lines.append(f"    Dominant cluster coverage: {summary.get('dominant_cluster_coverage')}%")
                # Also show overall stats if available (sorting algorithm)
                if summary.get('min_rate_percent') or summary.get('min_rate'):
                    lines.append(f"    Min rate: {summary.get('min_rate_percent') or summary.get('min_rate', 'N/A')}%")
                    lines.append(f"    Max rate: {summary.get('max_rate_percent') or summary.get('max_rate', 'N/A')}%")
                    lines.append(f"    Mean rate: {summary.get('mean_rate_percent') or summary.get('mean_rate', 'N/A')}%")
                if summary.get('median_rate_percent'):
                    lines.append(f"    Median rate: {summary.get('median_rate_percent')}%")

        return "\n".join(lines)

    def _confirm_with_user(self, message: str) -> bool:
        """Ask user for confirmation.

        Args:
            message: Confirmation message to display.

        Returns:
            True if user confirms, False otherwise.
        """
        print(f"\n{message}")
        response = input("Proceed? (y/n): ").strip().lower()
        return response in ("y", "yes")

    def _select_from_candidates(self, candidates: list[dict[str, Any]]) -> int | None:
        """Let user select from multiple candidates.

        Args:
            candidates: List of candidate dictionaries.

        Returns:
            Selected index, or None if cancelled.
        """
        print("\nMultiple matches found. Please select one:")
        for i, candidate in enumerate(candidates, 1):
            name = candidate.get("file_name") or candidate.get("name", "Unknown")
            path = candidate.get("file_path", "")
            score = candidate.get("score") or candidate.get("match_score", "")
            print(f"  {i}. {name}")
            if path:
                print(f"     Path: {path}")

        try:
            selection = input("\nEnter number (or 'c' to cancel): ").strip()
            if selection.lower() == "c":
                return None
            idx = int(selection) - 1
            if 0 <= idx < len(candidates):
                return idx
        except ValueError:
            pass

        print("Invalid selection.")
        return None

    async def handle_contract_query(self, query: str) -> str:
        """Handle a contract financial info request.

        Args:
            query: The user's query.

        Returns:
            Response string to display.
        """
        # Extract entity from query
        entity = get_entity_from_query(self.anthropic_client, query)

        if not entity:
            return (
                "I couldn't identify which contract you're asking about. "
                "Please specify a contract or company name (e.g., 'Finthesis', 'Skinvault', 'Blogwizarro')."
            )

        # Look up the contract
        result = self._call_financial_tool("lookup_contract", query=entity)

        if result.get("error"):
            return f"Error: {result['error']}"

        if result.get("status") == "multiple_matches":
            candidates = result.get("candidates", [])
            selection = self._select_from_candidates(candidates)

            if selection is None:
                return "Search cancelled."

            # Re-query with the specific selection
            selected = candidates[selection]
            result = self._call_financial_tool(
                "lookup_contract",
                query=selected.get("file_name", ""),
            )

        if result.get("status") == "found":
            contract = result.get("contract", {})
            contract_name = contract.get("file_name", "Unknown")

            # Confirm before showing results
            if not self._confirm_with_user(
                f"Found contract: {contract_name}\nExtract financial information?"
            ):
                return "Operation cancelled."

            financial_info = result.get("financial_info", {})
            formatted = self._format_financial_info(financial_info)

            return f"\n📄 Contract: {contract_name}\n{formatted}"

        return "Unable to process the contract lookup."

    async def handle_transaction_query(self, query: str) -> str:
        """Handle a transaction analysis request.

        Args:
            query: The user's query.

        Returns:
            Response string to display.
        """
        # Extract entity from query
        entity = get_entity_from_query(self.anthropic_client, query)

        if not entity:
            return (
                "I couldn't identify which transaction file you're asking about. "
                "Please specify a company name (e.g., 'Blogwizarro', 'codedtea', 'lingo ventures')."
            )

        # Find matching files
        matches = self._find_matching_files(entity)

        if not matches:
            return f"No transaction files found matching '{entity}' in the data directory."

        file_path = matches[0]

        if len(matches) > 1:
            print("\nMultiple files found:")
            for i, f in enumerate(matches[:5], 1):
                print(f"  {i}. {Path(f).name}")

            try:
                selection = input("\nSelect file number (or 'c' to cancel): ").strip()
                if selection.lower() == "c":
                    return "Operation cancelled."
                idx = int(selection) - 1
                if 0 <= idx < len(matches):
                    file_path = matches[idx]
            except ValueError:
                return "Invalid selection."

        # Confirm file selection
        if not self._confirm_with_user(f"Analyze file: {Path(file_path).name}?"):
            return "Operation cancelled."

        # First, inspect the table
        print("\nInspecting table structure...")
        inspect_result = self._call_transaction_tool("inspect_table", file_path=file_path)

        if inspect_result.get("error"):
            return f"Error inspecting file: {inspect_result['error']}"

        # Check commission analysis
        commission_analysis = inspect_result.get("commission_analysis", {})

        # Use columns detected by inspect_table (which already includes LLM fallback)
        columns = inspect_result.get("columns", [])
        potential_commission_cols = inspect_result.get("potential_commission_columns", [])
        potential_amount_cols = inspect_result.get("potential_amount_columns", [])

        commission_col = potential_commission_cols[0] if potential_commission_cols else None
        amount_col = potential_amount_cols[0] if potential_amount_cols else None

        # Show LLM detection info if it was used
        llm_detection_info = inspect_result.get("llm_column_detection", {})
        if llm_detection_info.get("used"):
            print(f"\n🤖 LLM-based column detection was used:")
            print(f"   Reasoning: {llm_detection_info.get('reasoning', 'N/A')}")

        if not commission_col:
            return (
                f"Could not find a commission column in the file.\n"
                f"Available columns: {', '.join(columns)}\n"
                f"Neither keyword matching nor LLM detection could identify the commission column."
            )

        # Check if commission is constant
        if commission_col in commission_analysis:
            analysis = commission_analysis[commission_col]
            if analysis.get("is_constant"):
                constant_value = analysis.get("constant_value")
                return (
                    f"\n✅ CONSTANT COMMISSION DETECTED\n"
                    f"File: {Path(file_path).name}\n"
                    f"All transactions have a fixed commission of: {constant_value}\n"
                    f"Total rows: {inspect_result.get('row_count', 'N/A')}"
                )

        # Commission varies - proceed with analysis
        if not amount_col:
            return (
                f"Could not find an amount column in the file.\n"
                f"Available columns: {', '.join(columns)}\n"
                f"Neither keyword matching nor LLM detection could identify the amount column."
            )

        # Get algorithm recommendation
        recommendation = inspect_result.get("algorithm_recommendation", {})
        recommended_algorithm = recommendation.get("algorithm", "sorting")
        recommendation_reason = recommendation.get("reason", "")

        # Check for minimal fee detection
        minimal_fee_detection = inspect_result.get("minimal_fee_detection", {})
        minimal_fee_cols = inspect_result.get("potential_minimal_fee_columns", [])

        # Display analysis info
        print(f"\n📊 Analysis Setup:")
        print(f"  Commission column: {commission_col}")
        print(f"  Amount column: {amount_col}")

        if minimal_fee_cols:
            print(f"  Minimal fee columns detected: {', '.join(minimal_fee_cols)}")

        if minimal_fee_detection and minimal_fee_detection.get("detected"):
            print(f"  ⚠️  Minimal fee pattern detected in data")
            if minimal_fee_detection.get("estimated_minimal_fee"):
                print(f"      Estimated minimal fee: {minimal_fee_detection['estimated_minimal_fee']}")
                print(f"      Estimated rate: {minimal_fee_detection.get('estimated_rate_percent', 'N/A')}%")

        # Show recommended algorithm
        if recommended_algorithm == "kmeans":
            print(f"\n  Recommended algorithm: K-MEANS (commission = rate × amount + minimal_fee)")
            print(f"  Reason: {recommendation_reason}")
            algorithm_desc = "kmeans"
        else:
            print(f"\n  Recommended algorithm: SORTING (commission = rate × amount)")
            print(f"  Reason: {recommendation_reason}")
            algorithm_desc = "sorting"

        # Confirm analysis approach
        if not self._confirm_with_user(f"Run rate cluster analysis using {algorithm_desc} algorithm?"):
            return "Analysis cancelled."

        # Run the appropriate analysis
        if recommended_algorithm == "kmeans":
            analysis_result = self._call_transaction_tool(
                "analyze_transactions_kmeans",
                file_path=file_path,
                amount_column=amount_col,
                commission_column=commission_col,
            )
        else:
            analysis_result = self._call_transaction_tool(
                "analyze_transactions_sorting",
                file_path=file_path,
                amount_column=amount_col,
                commission_column=commission_col,
            )

        formatted = self._format_transaction_analysis(analysis_result)
        return f"\n📁 File: {Path(file_path).name}{formatted}"

    async def handle_combined_query(self, query: str) -> str:
        """Handle queries that require both contract lookup and transaction analysis.

        Uses the programmatic tool calling agent to orchestrate multiple tools
        and provide a combined analysis comparing contractual rates with actual
        transaction fees.

        Args:
            query: The user's query requesting combined analysis.

        Returns:
            Response string with combined analysis results.
        """
        print("\n🔄 Running combined contract and transaction analysis...")
        print("   (Using programmatic tool calling with parallel execution)\n")

        try:
            # Run the combined analysis using the programmatic agent
            result = run_combined_analysis(query, verbose=True)
            return result

        except Exception as e:
            return (
                f"Error during combined analysis: {e}\n\n"
                "You can try running the contract lookup and transaction analysis "
                "separately:\n"
                "  - For contract info: 'What are the rates in the X contract?'\n"
                "  - For transactions: 'Analyze the X transactions'"
            )

    def handle_other_query(self, query: str) -> str:
        """Handle queries that don't fit the main categories.

        Args:
            query: The user's query.

        Returns:
            Response string to display.
        """
        return """
I'm a financial analysis assistant that can help you with these tasks:

1. 📄 CONTRACT LOOKUP
   Ask me about financial terms in contracts. Examples:
   - "What are the rates in the Finthesis contract?"
   - "Show me the fees for Skinvault"
   - "What's the rolling reserve for Blogwizarro?"

2. 📊 TRANSACTION ANALYSIS
   Ask me to analyze transaction files to identify commission rates. Examples:
   - "Analyze the Blogwizarro transactions"
   - "What rates are used in the codedtea file?"
   - "Show me the rate clusters for lingo ventures"

3. 🔄 COMBINED ANALYSIS (NEW!)
   Ask me to compare contractual rates with actual transaction fees. Examples:
   - "Compare contractual fees with actual transactions for Blogwizarro"
   - "What's the agreed rate vs actual rate for codedtea?"
   - "Give me the contractual fee and transaction analysis for lingo ventures"

Please rephrase your request to match one of these capabilities.
"""

    async def run(self) -> None:
        """Run the main conversation loop."""
        print("=" * 60)
        print("💼 Financial Analysis Agent")
        print("=" * 60)
        print("\nI can help you with:")
        print("  • Looking up financial terms in contracts")
        print("  • Analyzing transaction data for commission rates")
        print("  • Combined analysis: comparing contractual vs actual rates")
        print("\nType 'quit' or 'exit' to end the conversation.")
        print("=" * 60)

        while True:
            try:
                user_input = input("\n> You: ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n\nGoodbye!")
                break

            if not user_input:
                continue

            if user_input.lower() in ("quit", "exit", "q"):
                print("\nGoodbye!")
                break

            # Classify the query
            print("\nAnalyzing your request...")
            category = classify_query(self.anthropic_client, user_input)

            try:
                if category == QueryCategory.CONTRACT_INFO:
                    response = await self.handle_contract_query(user_input)
                elif category == QueryCategory.TRANSACTION_ANALYSIS:
                    response = await self.handle_transaction_query(user_input)
                elif category == QueryCategory.COMBINED_ANALYSIS:
                    response = await self.handle_combined_query(user_input)
                else:
                    response = self.handle_other_query(user_input)

                print(f"\n🤖 Assistant: {response}")

            except Exception as e:
                print(f"\n❌ Error: {e}")
                print("Please try again or rephrase your request.")


def main() -> None:
    """Entry point for the conversational agent."""
    # Check for API key
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("Error: ANTHROPIC_API_KEY environment variable not set.")
        sys.exit(1)

    agent = FinancialAgent()
    asyncio.run(agent.run())


if __name__ == "__main__":
    main()
