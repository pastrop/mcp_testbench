"""Contract lookup utilities with fuzzy matching."""

import base64
import io
import json
import re
from pathlib import Path
from typing import Any

from pypdf import PdfReader
from rapidfuzz import fuzz, process


def load_contracts_data(data_path: Path) -> list[dict[str, Any]]:
    """Load contracts data from JSON file.

    Args:
        data_path: Path to the contracts_data.json file.

    Returns:
        List of contract dictionaries.
    """
    if not data_path.exists():
        return []

    with open(data_path) as f:
        data = json.load(f)

    return data.get("contracts", [])


def find_matching_contracts(
    query: str,
    contracts: list[dict[str, Any]],
    threshold: int = 50,
) -> list[tuple[dict[str, Any], int]]:
    """Find contracts matching a query using fuzzy matching.

    Matches against both file_name and file_path fields.

    Args:
        query: The search query (e.g., "Finthesis", "Skinvault").
        contracts: List of contract dictionaries.
        threshold: Minimum match score (0-100) to include.

    Returns:
        List of (contract, score) tuples, sorted by score descending.
    """
    matches = []
    query_lower = query.lower()

    for contract in contracts:
        file_name = contract.get("file_name", "")
        file_path = contract.get("file_path", "")

        # Score against both fields and take the best
        name_score = fuzz.partial_ratio(query_lower, file_name.lower())
        path_score = fuzz.partial_ratio(query_lower, file_path.lower())
        best_score = max(name_score, path_score)

        # Also try token-based matching for multi-word queries
        name_token_score = fuzz.token_set_ratio(query_lower, file_name.lower())
        path_token_score = fuzz.token_set_ratio(query_lower, file_path.lower())
        token_best = max(name_token_score, path_token_score)

        final_score = max(best_score, token_best)

        if final_score >= threshold:
            matches.append((contract, final_score))

    # Sort by score descending
    matches.sort(key=lambda x: x[1], reverse=True)

    return matches


def decode_pdf_content(pdf_base64: str) -> str:
    """Decode base64 PDF content and extract text.

    Args:
        pdf_base64: Base64-encoded PDF data.

    Returns:
        Extracted text from the PDF.
    """
    try:
        pdf_bytes = base64.b64decode(pdf_base64)
        pdf_file = io.BytesIO(pdf_bytes)
        reader = PdfReader(pdf_file)

        text_parts = []
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text_parts.append(page_text)

        return "\n\n".join(text_parts)

    except Exception as e:
        return f"Error decoding PDF: {e}"


def extract_financial_info(text: str) -> dict[str, Any]:
    """Extract financial information from contract text.

    Looks for rates, fees, rolling reserves, currency-specific terms, etc.

    Args:
        text: The contract text content.

    Returns:
        Dictionary of extracted financial information.
    """
    financial_info: dict[str, Any] = {
        "rates": [],
        "fees": [],
        "rolling_reserve": [],
        "currency_terms": [],
        "other_terms": [],
    }

    # Common patterns for financial terms
    # Percentage patterns (e.g., "3.5%", "2.5 %", "3,5%")
    percentage_pattern = r"(\d+[.,]?\d*)\s*%"

    # Currency amount patterns (e.g., "€5", "$10", "EUR 5.00", "5 EUR")
    currency_pattern = r"(?:€|\$|EUR|USD|GBP)\s*(\d+[.,]?\d*)|(\d+[.,]?\d*)\s*(?:€|\$|EUR|USD|GBP)"

    # Look for rate-related terms
    rate_keywords = [
        r"transaction\s+(?:rate|fee)",
        r"processing\s+(?:rate|fee)",
        r"commission\s+(?:rate)?",
        r"merchant\s+(?:discount\s+)?rate",
        r"mdr",
        r"interchange",
        r"acquiring\s+(?:rate|fee)",
    ]

    # Look for fee-related terms
    fee_keywords = [
        r"chargeback\s+fee",
        r"refund\s+fee",
        r"setup\s+fee",
        r"monthly\s+fee",
        r"annual\s+fee",
        r"minimum\s+fee",
        r"transaction\s+fee",
        r"fixed\s+fee",
        r"per\s+transaction",
    ]

    # Look for rolling reserve terms
    reserve_keywords = [
        r"rolling\s+reserve",
        r"security\s+reserve",
        r"holdback",
        r"retention",
    ]

    # Process text line by line for context
    lines = text.split("\n")

    for i, line in enumerate(lines):
        line_lower = line.lower()

        # Check for rate keywords
        for keyword in rate_keywords:
            if re.search(keyword, line_lower):
                # Extract any percentages nearby
                percentages = re.findall(percentage_pattern, line)
                if percentages:
                    financial_info["rates"].append({
                        "context": line.strip()[:200],
                        "values": percentages,
                    })
                break

        # Check for fee keywords
        for keyword in fee_keywords:
            if re.search(keyword, line_lower):
                percentages = re.findall(percentage_pattern, line)
                amounts = re.findall(currency_pattern, line)
                if percentages or amounts:
                    financial_info["fees"].append({
                        "context": line.strip()[:200],
                        "percentages": percentages if percentages else None,
                        "amounts": [a[0] or a[1] for a in amounts] if amounts else None,
                    })
                break

        # Check for rolling reserve
        for keyword in reserve_keywords:
            if re.search(keyword, line_lower):
                percentages = re.findall(percentage_pattern, line)
                if percentages:
                    financial_info["rolling_reserve"].append({
                        "context": line.strip()[:200],
                        "values": percentages,
                    })
                break

        # Currency-specific terms
        if re.search(r"\b(eur|usd|gbp|pln|czk)\b", line_lower):
            if re.search(percentage_pattern, line):
                percentages = re.findall(percentage_pattern, line)
                financial_info["currency_terms"].append({
                    "context": line.strip()[:200],
                    "values": percentages,
                })

    # Deduplicate and limit results
    for key in financial_info:
        seen = set()
        unique = []
        for item in financial_info[key]:
            ctx = item.get("context", "")
            if ctx not in seen:
                seen.add(ctx)
                unique.append(item)
        financial_info[key] = unique[:10]  # Limit to 10 items per category

    return financial_info
