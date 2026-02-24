"""Sorting-based algorithm for transaction rate clustering.

This algorithm is used when commission = rate × amount (no minimal fee).

The algorithm:
1. Calculates the rate for each transaction (commission / amount)
2. Sorts transactions by calculated rate
3. Identifies rate clusters by scanning sorted rates - points within epsilon
   distance that form groups of at least min_cluster_size are considered clusters
4. Returns cluster statistics and assignments
"""

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd


@dataclass
class ClusterResult:
    """Result of clustering a single cluster."""

    cluster_id: int
    rate_percent: float
    transaction_count: int
    percentage_of_total: float
    rate_std_dev: float
    min_rate_percent: float
    max_rate_percent: float


@dataclass
class SortingAnalysisResult:
    """Complete result of the sorting-based analysis."""

    total_transactions: int
    valid_transactions: int
    outlier_count: int
    clusters: list[ClusterResult]
    summary: dict[str, float]


def analyze_rates_sorting(
    amounts: pd.Series,
    commissions: pd.Series,
    min_rate_diff: float = 0.001,
    min_cluster_size: int = 10,
) -> dict[str, Any]:
    """Analyze transaction rates using sorting-based clustering.

    This is a memory-efficient clustering algorithm that uses sorting instead
    of distance-based methods like DBSCAN. It works by:
    1. Calculating commission rate for each transaction
    2. Sorting all rates
    3. Scanning through sorted rates to find clusters of nearby values
    4. Assigning cluster IDs and computing statistics

    Args:
        amounts: Series of transaction amounts (must be positive)
        commissions: Series of commission values
        min_rate_diff: Minimum expected difference between commission rates.
            Points within min_rate_diff/2 of each other can be in same cluster.
            Default 0.001 = 0.1% rate difference.
        min_cluster_size: Minimum number of transactions to form a valid cluster.
            Smaller groups are marked as outliers. Default 10.

    Returns:
        Dictionary with:
        - total_transactions: Total number of input transactions
        - valid_transactions: Number with valid (positive, finite) rates
        - outlier_count: Transactions not assigned to any cluster
        - clusters: List of cluster dictionaries with:
            - cluster_id: Unique identifier
            - rate_percent: Median rate for the cluster (as percentage)
            - transaction_count: Number of transactions in cluster
            - percentage_of_total: Percentage of valid transactions
            - rate_std_dev: Standard deviation of rates in cluster
            - min_rate_percent: Minimum rate in cluster
            - max_rate_percent: Maximum rate in cluster
        - summary: Overall statistics (min, max, mean rates)
    """
    # Convert to numpy for efficiency
    amounts_arr = np.asarray(amounts, dtype=np.float64)
    commissions_arr = np.asarray(commissions, dtype=np.float64)

    total_transactions = len(amounts_arr)

    # Step 1: Calculate rates (as ratios, not percentages)
    with np.errstate(divide="ignore", invalid="ignore"):
        rates = commissions_arr / amounts_arr

    # Step 2: Filter valid rates (positive amounts, finite results)
    valid_mask = (amounts_arr > 0) & np.isfinite(rates)
    valid_indices = np.where(valid_mask)[0]
    valid_rates = rates[valid_mask]

    valid_transactions = len(valid_rates)

    if valid_transactions == 0:
        return {
            "total_transactions": total_transactions,
            "valid_transactions": 0,
            "outlier_count": 0,
            "clusters": [],
            "summary": {
                "min_rate_percent": None,
                "max_rate_percent": None,
                "mean_rate_percent": None,
            },
            "error": "No valid transactions found (all amounts <= 0 or invalid)",
        }

    # Step 3: Sort rates with indices for mapping back
    sorted_idx = np.argsort(valid_rates)
    sorted_rates = valid_rates[sorted_idx]

    # Step 4: Scan sorted rates to find clusters
    # Points within eps of each other can be in the same cluster
    eps = min_rate_diff / 2
    labels = np.full(len(valid_rates), -1, dtype=np.int32)
    cluster_id = 0

    i = 0
    while i < len(sorted_rates):
        # Find all points within eps of current point
        j = i
        while j < len(sorted_rates) and (sorted_rates[j] - sorted_rates[i]) <= eps:
            j += 1

        cluster_size = j - i

        # If enough points, form a cluster
        if cluster_size >= min_cluster_size:
            labels[sorted_idx[i:j]] = cluster_id
            cluster_id += 1
            i = j
        else:
            # Skip this point (remains outlier with label -1)
            i += 1

    # Step 5: Compute cluster statistics
    clusters = []
    for cid in range(cluster_id):
        mask = labels == cid
        cluster_rates = valid_rates[mask]

        cluster_info = {
            "cluster_id": cid,
            "rate_percent": round(float(np.median(cluster_rates)) * 100, 4),
            "transaction_count": int(mask.sum()),
            "percentage_of_total": round(float(mask.sum()) / valid_transactions * 100, 2),
            "rate_std_dev": round(float(np.std(cluster_rates)) * 100, 6),
            "min_rate_percent": round(float(cluster_rates.min()) * 100, 4),
            "max_rate_percent": round(float(cluster_rates.max()) * 100, 4),
        }
        clusters.append(cluster_info)

    # Sort clusters by transaction count (descending)
    clusters.sort(key=lambda x: x["transaction_count"], reverse=True)

    # Count outliers
    outlier_count = int((labels == -1).sum())

    # Overall summary
    summary = {
        "min_rate_percent": round(float(valid_rates.min()) * 100, 4),
        "max_rate_percent": round(float(valid_rates.max()) * 100, 4),
        "mean_rate_percent": round(float(valid_rates.mean()) * 100, 4),
        "median_rate_percent": round(float(np.median(valid_rates)) * 100, 4),
    }

    return {
        "algorithm": "sorting",
        "total_transactions": total_transactions,
        "valid_transactions": valid_transactions,
        "outlier_count": outlier_count,
        "outlier_percentage": round(outlier_count / valid_transactions * 100, 2) if valid_transactions > 0 else 0,
        "num_clusters": cluster_id,
        "clusters": clusters,
        "summary": summary,
        "parameters": {
            "min_rate_diff": min_rate_diff,
            "min_cluster_size": min_cluster_size,
            "eps": eps,
        },
    }


def get_cluster_assignments(
    amounts: pd.Series,
    commissions: pd.Series,
    min_rate_diff: float = 0.001,
    min_cluster_size: int = 10,
) -> pd.DataFrame:
    """Get cluster assignments for each transaction.

    Returns a DataFrame with the original data plus cluster assignments.
    Useful for detailed analysis or export.

    Args:
        amounts: Series of transaction amounts
        commissions: Series of commission values
        min_rate_diff: Minimum rate difference for clustering
        min_cluster_size: Minimum cluster size

    Returns:
        DataFrame with columns:
        - amount: Original amount
        - commission: Original commission
        - rate_percent: Calculated rate as percentage
        - cluster_id: Assigned cluster (-1 for outliers)
        - cluster_rate_percent: Median rate of assigned cluster (NaN for outliers)
    """
    amounts_arr = np.asarray(amounts, dtype=np.float64)
    commissions_arr = np.asarray(commissions, dtype=np.float64)

    with np.errstate(divide="ignore", invalid="ignore"):
        rates = commissions_arr / amounts_arr

    valid_mask = (amounts_arr > 0) & np.isfinite(rates)
    valid_indices = np.where(valid_mask)[0]
    valid_rates = rates[valid_mask]

    if len(valid_rates) == 0:
        return pd.DataFrame({
            "amount": amounts,
            "commission": commissions,
            "rate_percent": np.nan,
            "cluster_id": -1,
            "cluster_rate_percent": np.nan,
        })

    # Sort and cluster
    sorted_idx = np.argsort(valid_rates)
    sorted_rates = valid_rates[sorted_idx]

    eps = min_rate_diff / 2
    labels = np.full(len(valid_rates), -1, dtype=np.int32)
    cluster_id = 0

    i = 0
    while i < len(sorted_rates):
        j = i
        while j < len(sorted_rates) and (sorted_rates[j] - sorted_rates[i]) <= eps:
            j += 1

        if (j - i) >= min_cluster_size:
            labels[sorted_idx[i:j]] = cluster_id
            cluster_id += 1
            i = j
        else:
            i += 1

    # Map back to original indices
    all_labels = np.full(len(amounts), -1, dtype=np.int32)
    all_labels[valid_indices] = labels

    # Compute cluster rates
    cluster_rates = {}
    for cid in range(cluster_id):
        mask = labels == cid
        cluster_rates[cid] = float(np.median(valid_rates[mask])) * 100

    # Build result DataFrame
    result = pd.DataFrame({
        "amount": amounts_arr,
        "commission": commissions_arr,
        "rate_percent": rates * 100,
        "cluster_id": all_labels,
    })

    result["cluster_rate_percent"] = result["cluster_id"].map(
        lambda x: cluster_rates.get(x, np.nan)
    )

    return result
