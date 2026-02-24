"""Financial Tools MCP Server.

Provides tools for looking up financial information from contracts.
"""

import logging
from pathlib import Path
from typing import Any

from fastmcp import FastMCP

from .tools.contract_lookup import (
    decode_pdf_content,
    extract_financial_info,
    find_matching_contracts,
    load_contracts_data,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Determine data directory (relative to project root)
PROJECT_ROOT = Path(__file__).parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
CONTRACTS_FILE = DATA_DIR / "contracts_data.json"

mcp = FastMCP(
    name="financial-tools",
    instructions="""
    Financial Tools Server - Provides contract lookup and financial information extraction.

    Available tools:
    - lookup_contract: Search for contracts by name and extract financial terms
    - list_contracts: List all available contracts

    Contracts are matched using fuzzy search against both file names and paths.
    """,
)


@mcp.tool()
def list_contracts() -> dict[str, Any]:
    """List all available contracts.

    Returns:
        Dictionary with list of contract names and paths.
    """
    contracts = load_contracts_data(CONTRACTS_FILE)

    if not contracts:
        return {
            "error": "No contracts found",
            "path": str(CONTRACTS_FILE),
        }

    contract_list = []
    for contract in contracts:
        contract_list.append({
            "file_name": contract.get("file_name", ""),
            "file_path": contract.get("file_path", ""),
            "file_size_bytes": contract.get("file_size_bytes", 0),
        })

    return {
        "total_contracts": len(contracts),
        "contracts": contract_list,
    }


@mcp.tool()
def lookup_contract(
    query: str,
    extract_financial_terms: bool = True,
) -> dict[str, Any]:
    """Look up a contract by name and optionally extract financial terms.

    Performs fuzzy matching against contract file names and paths.

    Args:
        query: Search query (e.g., "Finthesis", "Skinvault", "Blogwizarro").
        extract_financial_terms: Whether to extract financial information from the contract.

    Returns:
        Dictionary with matched contract(s) and optionally financial information.
    """
    contracts = load_contracts_data(CONTRACTS_FILE)

    if not contracts:
        return {
            "error": "No contracts data available",
            "path": str(CONTRACTS_FILE),
        }

    # Find matching contracts
    matches = find_matching_contracts(query, contracts, threshold=50)

    if not matches:
        return {
            "error": "No matching contracts found",
            "query": query,
            "suggestion": "Try a different search term or use list_contracts to see available contracts.",
        }

    # If multiple matches with similar scores, return candidates
    if len(matches) > 1:
        top_score = matches[0][1]
        close_matches = [(c, s) for c, s in matches if s >= top_score - 10]

        if len(close_matches) > 1:
            return {
                "status": "multiple_matches",
                "query": query,
                "message": "Multiple contracts match your query. Please specify which one:",
                "candidates": [
                    {
                        "file_name": c.get("file_name", ""),
                        "file_path": c.get("file_path", ""),
                        "match_score": s,
                    }
                    for c, s in close_matches[:5]  # Limit to 5 candidates
                ],
            }

    # Single best match
    best_match, score = matches[0]

    result: dict[str, Any] = {
        "status": "found",
        "query": query,
        "match_score": score,
        "contract": {
            "file_name": best_match.get("file_name", ""),
            "file_path": best_match.get("file_path", ""),
            "file_size_bytes": best_match.get("file_size_bytes", 0),
        },
    }

    # Extract financial terms if requested
    if extract_financial_terms:
        pdf_data = best_match.get("pdf_data", "")

        if not pdf_data:
            result["financial_info"] = {
                "error": "No PDF data available for this contract",
            }
        else:
            # Decode and extract text
            text = decode_pdf_content(pdf_data)

            if text.startswith("Error"):
                result["financial_info"] = {
                    "error": text,
                }
            else:
                # Extract financial information
                financial_info = extract_financial_info(text)

                # Add summary
                has_rates = len(financial_info.get("rates", [])) > 0
                has_fees = len(financial_info.get("fees", [])) > 0
                has_reserve = len(financial_info.get("rolling_reserve", [])) > 0
                has_currency = len(financial_info.get("currency_terms", [])) > 0

                financial_info["summary"] = {
                    "has_rates": has_rates,
                    "has_fees": has_fees,
                    "has_rolling_reserve": has_reserve,
                    "has_currency_specific_terms": has_currency,
                    "total_terms_found": sum(
                        len(v) for v in financial_info.values()
                        if isinstance(v, list)
                    ),
                }

                result["financial_info"] = financial_info

    return result


@mcp.tool()
def get_contract_text(query: str) -> dict[str, Any]:
    """Get the full text content of a contract.

    Useful for detailed analysis when the extracted financial terms aren't sufficient.

    Args:
        query: Search query to find the contract.

    Returns:
        Dictionary with contract text content.
    """
    contracts = load_contracts_data(CONTRACTS_FILE)

    if not contracts:
        return {"error": "No contracts data available"}

    matches = find_matching_contracts(query, contracts, threshold=60)

    if not matches:
        return {"error": "No matching contracts found", "query": query}

    if len(matches) > 1:
        top_score = matches[0][1]
        close_matches = [(c, s) for c, s in matches if s >= top_score - 10]
        if len(close_matches) > 1:
            return {
                "status": "multiple_matches",
                "candidates": [c.get("file_name") for c, _ in close_matches[:5]],
            }

    best_match, score = matches[0]
    pdf_data = best_match.get("pdf_data", "")

    if not pdf_data:
        return {"error": "No PDF data available"}

    text = decode_pdf_content(pdf_data)

    return {
        "contract": best_match.get("file_name", ""),
        "file_path": best_match.get("file_path", ""),
        "match_score": score,
        "text_length": len(text),
        "text": text[:50000] if len(text) > 50000 else text,  # Limit size
        "truncated": len(text) > 50000,
    }


def main() -> None:
    """Run the MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()
