"""Transaction Analysis MCP Server.

Provides tools for analyzing transaction tables to identify commission rate clusters.
"""

import logging
from pathlib import Path
from typing import Any

import pandas as pd
from fastmcp import FastMCP

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

mcp = FastMCP(
    name="transaction-analysis",
    instructions="""
    Transaction Analysis Server - Analyzes transaction tables to identify commission rate clusters.

    Available tools:
    - inspect_table: Examine Excel file structure before analysis
    - analyze_transactions_sorting: For simple commission = rate × amount
    - analyze_transactions_kmeans: For commission = rate × amount + minimal_fee

    Always call inspect_table first to understand the data structure.
    """,
)


def _parse_numeric_column(series: pd.Series) -> pd.Series:
    """Parse numeric values that may use comma as decimal separator."""
    # Handle string types (object or StringDtype)
    if pd.api.types.is_string_dtype(series):
        return pd.to_numeric(
            series.astype(str).str.replace(",", ".").str.strip(),
            errors="coerce",
        )
    return pd.to_numeric(series, errors="coerce")


def _detect_minimal_fee_pattern(
    amounts: pd.Series,
    commissions: pd.Series,
    tolerance: float = 0.001,
) -> dict[str, Any]:
    """Detect if commission pattern suggests a minimal fee component.

    If commission = rate × amount, then commission/amount should be roughly constant.
    If commission = rate × amount + minimal_fee, the ratio will vary more for small amounts.

    Args:
        amounts: Series of transaction amounts
        commissions: Series of commission values
        tolerance: Acceptable variation in rate to consider it "clean" (default 0.1%)

    Returns:
        Dictionary with detection results
    """
    import numpy as np

    valid_mask = (amounts > 0) & amounts.notna() & commissions.notna()
    valid_amounts = amounts[valid_mask].values
    valid_commissions = commissions[valid_mask].values

    if len(valid_amounts) < 10:
        return {"detected": False, "reason": "insufficient_data", "sample_size": len(valid_amounts)}

    # Calculate apparent rates
    rates = valid_commissions / valid_amounts

    # Check rate variation
    rate_std = np.std(rates)
    rate_mean = np.mean(rates)
    rate_cv = rate_std / rate_mean if rate_mean > 0 else 0  # Coefficient of variation

    # If rates are very consistent, no minimal fee
    if rate_cv < tolerance:
        return {
            "detected": False,
            "reason": "rates_consistent",
            "rate_cv": round(float(rate_cv), 6),
            "rate_mean_percent": round(float(rate_mean) * 100, 4),
        }

    # Check if small transactions have higher apparent rates (suggests minimal fee)
    # Split into small and large transactions
    median_amount = np.median(valid_amounts)
    small_mask = valid_amounts < median_amount
    large_mask = valid_amounts >= median_amount

    small_rates = rates[small_mask]
    large_rates = rates[large_mask]

    if len(small_rates) > 5 and len(large_rates) > 5:
        small_rate_mean = np.mean(small_rates)
        large_rate_mean = np.mean(large_rates)

        # If small transactions have noticeably higher rates, suggests minimal fee
        if small_rate_mean > large_rate_mean * 1.05:  # 5% higher
            # Estimate minimal fee using linear regression
            # commission = rate * amount + fee
            # Using least squares: fit line to (amount, commission)
            from numpy.polynomial import polynomial as P
            coeffs = np.polyfit(valid_amounts, valid_commissions, 1)
            estimated_rate = coeffs[0]
            estimated_fee = coeffs[1]

            return {
                "detected": True,
                "reason": "small_transactions_higher_rate",
                "small_rate_mean_percent": round(float(small_rate_mean) * 100, 4),
                "large_rate_mean_percent": round(float(large_rate_mean) * 100, 4),
                "estimated_rate_percent": round(float(estimated_rate) * 100, 4),
                "estimated_minimal_fee": round(float(max(0, estimated_fee)), 4),
                "confidence": "medium",
            }

    return {
        "detected": False,
        "reason": "no_clear_pattern",
        "rate_cv": round(float(rate_cv), 6),
    }


@mcp.tool()
def inspect_table(file_path: str) -> dict[str, Any]:
    """Inspect an Excel file to understand its structure and recommend analysis algorithm.

    Args:
        file_path: Absolute path to the Excel file to inspect.

    Returns:
        Dictionary containing:
        - Column names, sample rows, statistics, data types
        - Detected commission, amount, and minimal fee columns
        - Commission analysis (constant vs variable)
        - Minimal fee pattern detection
        - Algorithm recommendation
    """
    import numpy as np

    path = Path(file_path)

    if not path.exists():
        return {"error": "File not found", "path": file_path}

    if not path.suffix.lower() in (".xlsx", ".xls"):
        return {"error": "Invalid file format", "expected": ".xlsx or .xls", "got": path.suffix}

    try:
        df = pd.read_excel(path)
    except Exception as e:
        return {"error": "Unable to read file", "details": str(e)}

    # Get column info
    columns = df.columns.tolist()
    dtypes = {col: str(df[col].dtype) for col in columns}

    # Get sample rows (first 5)
    sample_rows = df.head(5).to_dict(orient="records")

    # Get statistics for numeric columns
    numeric_stats = {}
    for col in df.select_dtypes(include=["number"]).columns:
        stats = df[col].describe()
        numeric_stats[col] = {
            "count": int(stats.get("count", 0)),
            "mean": round(float(stats.get("mean", 0)), 4),
            "std": round(float(stats.get("std", 0)), 4),
            "min": round(float(stats.get("min", 0)), 4),
            "max": round(float(stats.get("max", 0)), 4),
            "unique_values": int(df[col].nunique()),
        }

    # Check for potential commission columns (exclude currency columns)
    potential_commission_cols = [
        col for col in columns
        if any(kw in col.lower() for kw in ["commission", "fee"])
        and "currency" not in col.lower()
    ]

    # Check for potential amount columns
    potential_amount_cols = [
        col for col in columns
        if any(kw in col.lower() for kw in ["amount", "sum", "value", "total"])
        and "currency" not in col.lower()
    ]

    # Check for potential minimal fee columns
    minimal_fee_keywords = ["minimal", "minimum", "min_fee", "fixed", "base_fee", "flat"]
    potential_minimal_fee_cols = [
        col for col in columns
        if any(kw in col.lower() for kw in minimal_fee_keywords)
    ]

    # Check if commission is constant
    commission_analysis = {}
    for col in potential_commission_cols:
        parsed = _parse_numeric_column(df[col])
        unique_values = parsed.dropna().unique()
        if len(unique_values) == 1:
            commission_analysis[col] = {
                "is_constant": True,
                "constant_value": float(unique_values[0]),
            }
        elif len(unique_values) == 0:
            commission_analysis[col] = {
                "is_constant": False,
                "unique_count": 0,
                "value_range": [None, None],
            }
        else:
            commission_analysis[col] = {
                "is_constant": False,
                "unique_count": len(unique_values),
                "value_range": [float(parsed.min()), float(parsed.max())],
            }

    # Detect minimal fee pattern if we have amount and commission columns
    minimal_fee_detection = None
    if potential_amount_cols and potential_commission_cols:
        amount_col = potential_amount_cols[0]
        commission_col = potential_commission_cols[0]

        amounts = _parse_numeric_column(df[amount_col]).abs()
        commissions = _parse_numeric_column(df[commission_col]).abs()

        minimal_fee_detection = _detect_minimal_fee_pattern(amounts, commissions)

    # Generate algorithm recommendation
    recommendation = _generate_algorithm_recommendation(
        commission_analysis=commission_analysis,
        potential_minimal_fee_cols=potential_minimal_fee_cols,
        minimal_fee_detection=minimal_fee_detection,
    )

    return {
        "file_path": file_path,
        "row_count": len(df),
        "columns": columns,
        "data_types": dtypes,
        "sample_rows": sample_rows,
        "numeric_statistics": numeric_stats,
        "potential_commission_columns": potential_commission_cols,
        "potential_amount_columns": potential_amount_cols,
        "potential_minimal_fee_columns": potential_minimal_fee_cols,
        "commission_analysis": commission_analysis,
        "minimal_fee_detection": minimal_fee_detection,
        "algorithm_recommendation": recommendation,
    }


def _generate_algorithm_recommendation(
    commission_analysis: dict[str, Any],
    potential_minimal_fee_cols: list[str],
    minimal_fee_detection: dict[str, Any] | None,
) -> dict[str, Any]:
    """Generate algorithm recommendation based on table analysis.

    Args:
        commission_analysis: Results of commission column analysis
        potential_minimal_fee_cols: List of detected minimal fee columns
        minimal_fee_detection: Results of minimal fee pattern detection

    Returns:
        Dictionary with algorithm recommendation and reasoning
    """
    # Check if all commissions are constant
    all_constant = all(
        analysis.get("is_constant", False)
        for analysis in commission_analysis.values()
    )

    if all_constant:
        constant_values = [
            analysis.get("constant_value")
            for analysis in commission_analysis.values()
            if analysis.get("is_constant")
        ]
        return {
            "algorithm": "none",
            "reason": "constant_commission",
            "message": "All commission values are constant. No clustering needed.",
            "constant_values": constant_values,
        }

    # Check for explicit minimal fee column
    if potential_minimal_fee_cols:
        return {
            "algorithm": "kmeans",
            "reason": "minimal_fee_column_detected",
            "message": f"Found minimal fee column(s): {potential_minimal_fee_cols}. Use kmeans algorithm.",
            "minimal_fee_columns": potential_minimal_fee_cols,
        }

    # Check for minimal fee pattern in data
    if minimal_fee_detection and minimal_fee_detection.get("detected"):
        return {
            "algorithm": "kmeans",
            "reason": "minimal_fee_pattern_detected",
            "message": "Commission pattern suggests minimal fee component. Use kmeans algorithm.",
            "detection_details": minimal_fee_detection,
        }

    # Default to sorting algorithm
    return {
        "algorithm": "sorting",
        "reason": "simple_rate_structure",
        "message": "No minimal fee detected. Commission appears to be rate × amount. Use sorting algorithm.",
    }


@mcp.tool()
def analyze_transactions_sorting(
    file_path: str,
    amount_column: str,
    commission_column: str,
    min_rate_diff: float = 0.001,
    min_cluster_size: int = 10,
) -> dict[str, Any]:
    """Analyze transactions using sorting-based clustering algorithm.

    For tables where commission = rate × amount (no minimal fee).

    This algorithm:
    1. Calculates commission rate for each transaction
    2. Sorts all rates
    3. Scans sorted rates to find clusters of nearby values
    4. Returns cluster statistics

    Args:
        file_path: Path to the Excel file.
        amount_column: Name of the column containing transaction amounts.
        commission_column: Name of the column containing commission values.
        min_rate_diff: Minimum expected difference between commission rates.
            Points within min_rate_diff/2 of each other can be in same cluster.
            Default 0.001 = 0.1% rate difference.
        min_cluster_size: Minimum number of transactions to form a valid cluster.
            Default 10.

    Returns:
        Analysis results with identified rate clusters.
    """
    from .scripts.sorting_algorithm import analyze_rates_sorting

    path = Path(file_path)

    if not path.exists():
        return {"error": "File not found", "path": file_path}

    try:
        df = pd.read_excel(path)
    except Exception as e:
        return {"error": "Unable to read file", "details": str(e)}

    # Validate columns exist
    if amount_column not in df.columns:
        return {
            "error": "Column not found",
            "column": amount_column,
            "available": df.columns.tolist(),
        }

    if commission_column not in df.columns:
        return {
            "error": "Column not found",
            "column": commission_column,
            "available": df.columns.tolist(),
        }

    # Log the call
    logger.info(
        f"analyze_transactions_sorting called: "
        f"file={file_path}, amount_col={amount_column}, commission_col={commission_column}"
    )

    # Parse numeric columns
    amounts = _parse_numeric_column(df[amount_column]).abs()
    commissions = _parse_numeric_column(df[commission_column]).abs()

    # Run the sorting-based clustering algorithm
    result = analyze_rates_sorting(
        amounts=amounts,
        commissions=commissions,
        min_rate_diff=min_rate_diff,
        min_cluster_size=min_cluster_size,
    )

    # Add file path to result
    result["file_path"] = file_path

    return result


@mcp.tool()
def analyze_transactions_kmeans(
    file_path: str,
    amount_column: str,
    commission_column: str,
    minimal_fee_column: str | None = None,
    n_clusters: int | None = None,
    min_cluster_size: int = 10,
) -> dict[str, Any]:
    """Analyze transactions using k-means clustering algorithm.

    For tables where commission = rate × amount + minimal_fee.

    This algorithm:
    1. Clusters transactions by (amount, commission) similarity
    2. For each cluster, fits: commission = rate × amount + fee
    3. Returns cluster parameters and statistics

    Args:
        file_path: Path to the Excel file.
        amount_column: Name of the column containing transaction amounts.
        commission_column: Name of the column containing commission values.
        minimal_fee_column: Optional name of column containing minimal fee values.
        n_clusters: Number of clusters (if None, auto-detect).
        min_cluster_size: Minimum transactions per cluster.

    Returns:
        Analysis results with identified rate and fee clusters.
    """
    from .scripts.kmeans_algorithm import analyze_rates_kmeans

    path = Path(file_path)

    if not path.exists():
        return {"error": "File not found", "path": file_path}

    try:
        df = pd.read_excel(path)
    except Exception as e:
        return {"error": "Unable to read file", "details": str(e)}

    # Validate columns exist
    for col_name, col_value in [
        ("amount_column", amount_column),
        ("commission_column", commission_column),
    ]:
        if col_value not in df.columns:
            return {
                "error": "Column not found",
                "column": col_value,
                "available": df.columns.tolist(),
            }

    if minimal_fee_column and minimal_fee_column not in df.columns:
        return {
            "error": "Column not found",
            "column": minimal_fee_column,
            "available": df.columns.tolist(),
        }

    # Log the call
    logger.info(
        f"analyze_transactions_kmeans called: "
        f"file={file_path}, amount_col={amount_column}, "
        f"commission_col={commission_column}, fee_col={minimal_fee_column}"
    )

    # Parse numeric columns
    amounts = _parse_numeric_column(df[amount_column]).abs()
    commissions = _parse_numeric_column(df[commission_column]).abs()

    # Run the kmeans clustering algorithm
    result = analyze_rates_kmeans(
        amounts=amounts,
        commissions=commissions,
        n_clusters=n_clusters,
        min_cluster_size=min_cluster_size,
    )

    # Add file path to result
    result["file_path"] = file_path

    return result


def main() -> None:
    """Run the MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()
