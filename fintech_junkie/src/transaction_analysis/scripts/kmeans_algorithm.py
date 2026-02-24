"""K-means clustering algorithm for transaction rate analysis.

This algorithm is used when commission = rate × amount + minimal_fee.

The algorithm:
1. Normalizes transaction data (amount, commission) for clustering
2. Uses k-means to identify clusters of similar transactions
3. For each cluster, fits a linear model: commission = rate × amount + fee
4. Returns cluster parameters (rate, minimal_fee) and statistics
"""

from typing import Any

import numpy as np
import pandas as pd


def _fit_linear_model(amounts: np.ndarray, commissions: np.ndarray) -> tuple[float, float]:
    """Fit a linear model: commission = rate * amount + fee.

    Args:
        amounts: Array of transaction amounts
        commissions: Array of commission values

    Returns:
        Tuple of (rate, fee)
    """
    if len(amounts) < 2:
        if len(amounts) == 1:
            # Single point: assume no minimal fee
            return float(commissions[0] / amounts[0]) if amounts[0] > 0 else 0.0, 0.0
        return 0.0, 0.0

    # Use least squares to fit: commission = rate * amount + fee
    # Formulated as: [amount, 1] @ [rate, fee]^T = commission
    A = np.column_stack([amounts, np.ones(len(amounts))])
    result, residuals, rank, s = np.linalg.lstsq(A, commissions, rcond=None)

    rate = float(result[0])
    fee = float(result[1])

    # Fee should be non-negative (can't have negative minimal fee)
    fee = max(0.0, fee)

    return rate, fee


def _simple_kmeans(
    data: np.ndarray,
    n_clusters: int,
    max_iter: int = 100,
    random_state: int = 42,
) -> tuple[np.ndarray, np.ndarray]:
    """Simple k-means implementation without sklearn dependency.

    Args:
        data: 2D array of shape (n_samples, n_features)
        n_clusters: Number of clusters
        max_iter: Maximum iterations
        random_state: Random seed for reproducibility

    Returns:
        Tuple of (labels, centroids)
    """
    np.random.seed(random_state)
    n_samples = len(data)

    # Initialize centroids randomly from data points
    indices = np.random.choice(n_samples, n_clusters, replace=False)
    centroids = data[indices].copy()

    labels = np.zeros(n_samples, dtype=np.int32)

    for _ in range(max_iter):
        # Assign points to nearest centroid
        for i in range(n_samples):
            distances = np.sum((centroids - data[i]) ** 2, axis=1)
            labels[i] = np.argmin(distances)

        # Update centroids
        new_centroids = np.zeros_like(centroids)
        for k in range(n_clusters):
            mask = labels == k
            if np.sum(mask) > 0:
                new_centroids[k] = data[mask].mean(axis=0)
            else:
                new_centroids[k] = centroids[k]

        # Check convergence
        if np.allclose(centroids, new_centroids):
            break

        centroids = new_centroids

    return labels, centroids


def analyze_rates_kmeans(
    amounts: pd.Series,
    commissions: pd.Series,
    n_clusters: int | None = None,
    max_clusters: int = 5,
    min_cluster_size: int = 10,
) -> dict[str, Any]:
    """Analyze transaction rates using k-means clustering.

    This algorithm handles cases where commission = rate × amount + minimal_fee.

    The approach:
    1. Normalize (amount, commission) data for clustering
    2. Try different numbers of clusters and select best fit
    3. For each cluster, fit linear model to extract rate and fee
    4. Return cluster parameters and statistics

    Args:
        amounts: Series of transaction amounts (must be positive)
        commissions: Series of commission values
        n_clusters: Number of clusters (if None, auto-detect)
        max_clusters: Maximum clusters to try when auto-detecting
        min_cluster_size: Minimum transactions per cluster

    Returns:
        Dictionary with:
        - total_transactions: Total number of input transactions
        - valid_transactions: Number with valid data
        - clusters: List of cluster dictionaries with rate_percent, minimal_fee, etc.
        - summary: Overall statistics
    """
    # Convert to numpy for efficiency
    amounts_arr = np.asarray(amounts, dtype=np.float64)
    commissions_arr = np.asarray(commissions, dtype=np.float64)

    total_transactions = len(amounts_arr)

    # Filter valid data (positive amounts, finite values)
    valid_mask = (amounts_arr > 0) & np.isfinite(amounts_arr) & np.isfinite(commissions_arr)
    valid_indices = np.where(valid_mask)[0]
    valid_amounts = amounts_arr[valid_mask]
    valid_commissions = commissions_arr[valid_mask]

    valid_transactions = len(valid_amounts)

    if valid_transactions == 0:
        return {
            "algorithm": "kmeans",
            "total_transactions": total_transactions,
            "valid_transactions": 0,
            "clusters": [],
            "summary": {},
            "error": "No valid transactions found",
        }

    if valid_transactions < min_cluster_size:
        # Too few transactions for clustering, treat as single cluster
        rate, fee = _fit_linear_model(valid_amounts, valid_commissions)
        return {
            "algorithm": "kmeans",
            "total_transactions": total_transactions,
            "valid_transactions": valid_transactions,
            "num_clusters": 1,
            "clusters": [{
                "cluster_id": 0,
                "rate_percent": round(rate * 100, 4),
                "minimal_fee": round(fee, 4),
                "transaction_count": valid_transactions,
                "percentage_of_total": 100.0,
            }],
            "summary": {
                "dominant_rate_percent": round(rate * 100, 4),
                "dominant_fee": round(fee, 4),
            },
        }

    # Prepare data for clustering: normalize amount and commission
    # Use (amount, commission) as features
    data = np.column_stack([valid_amounts, valid_commissions])

    # Normalize for better clustering
    data_mean = data.mean(axis=0)
    data_std = data.std(axis=0)
    data_std[data_std == 0] = 1  # Avoid division by zero
    data_normalized = (data - data_mean) / data_std

    # Determine number of clusters
    if n_clusters is None:
        # Try different cluster counts and pick best using silhouette-like score
        best_n = 1
        best_score = -1

        for n in range(1, min(max_clusters + 1, valid_transactions // min_cluster_size + 1)):
            if n == 1:
                # Single cluster
                labels = np.zeros(valid_transactions, dtype=np.int32)
                score = 0  # Baseline
            else:
                labels, _ = _simple_kmeans(data_normalized, n)

                # Check if all clusters have enough points
                cluster_sizes = [np.sum(labels == k) for k in range(n)]
                if min(cluster_sizes) < min_cluster_size:
                    continue

                # Compute simple quality score: within-cluster variance ratio
                total_var = np.var(data_normalized)
                within_var = 0
                for k in range(n):
                    mask = labels == k
                    if np.sum(mask) > 1:
                        within_var += np.var(data_normalized[mask]) * np.sum(mask)
                within_var /= valid_transactions

                score = 1 - (within_var / total_var) if total_var > 0 else 0

            if score > best_score:
                best_score = score
                best_n = n

        n_clusters = best_n

    # Final clustering
    if n_clusters == 1:
        labels = np.zeros(valid_transactions, dtype=np.int32)
    else:
        labels, _ = _simple_kmeans(data_normalized, n_clusters)

    # Analyze each cluster
    clusters = []
    for k in range(n_clusters):
        mask = labels == k
        cluster_amounts = valid_amounts[mask]
        cluster_commissions = valid_commissions[mask]

        if len(cluster_amounts) == 0:
            continue

        # Fit linear model for this cluster
        rate, fee = _fit_linear_model(cluster_amounts, cluster_commissions)

        # Compute fit quality (R-squared)
        predicted = rate * cluster_amounts + fee
        ss_res = np.sum((cluster_commissions - predicted) ** 2)
        ss_tot = np.sum((cluster_commissions - cluster_commissions.mean()) ** 2)
        r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 1.0

        # Compute apparent rates for statistics
        apparent_rates = cluster_commissions / cluster_amounts

        clusters.append({
            "cluster_id": k,
            "rate_percent": round(rate * 100, 4),
            "minimal_fee": round(fee, 4),
            "transaction_count": int(mask.sum()),
            "percentage_of_total": round(float(mask.sum()) / valid_transactions * 100, 2),
            "r_squared": round(r_squared, 4),
            "apparent_rate_mean_percent": round(float(apparent_rates.mean()) * 100, 4),
            "apparent_rate_std_percent": round(float(apparent_rates.std()) * 100, 4),
            "amount_range": [round(float(cluster_amounts.min()), 2), round(float(cluster_amounts.max()), 2)],
        })

    # Sort by transaction count
    clusters.sort(key=lambda x: x["transaction_count"], reverse=True)

    # Summary
    if clusters:
        dominant = clusters[0]
        summary = {
            "dominant_rate_percent": dominant["rate_percent"],
            "dominant_fee": dominant["minimal_fee"],
            "dominant_cluster_coverage": dominant["percentage_of_total"],
        }
    else:
        summary = {}

    return {
        "algorithm": "kmeans",
        "total_transactions": total_transactions,
        "valid_transactions": valid_transactions,
        "num_clusters": len(clusters),
        "clusters": clusters,
        "summary": summary,
        "parameters": {
            "n_clusters": n_clusters,
            "min_cluster_size": min_cluster_size,
        },
    }


def get_cluster_assignments(
    amounts: pd.Series,
    commissions: pd.Series,
    n_clusters: int | None = None,
) -> pd.DataFrame:
    """Get cluster assignments for each transaction.

    Returns a DataFrame with cluster assignments and fitted parameters.

    Args:
        amounts: Series of transaction amounts
        commissions: Series of commission values
        n_clusters: Number of clusters (if None, auto-detect)

    Returns:
        DataFrame with columns:
        - amount: Original amount
        - commission: Original commission
        - cluster_id: Assigned cluster
        - fitted_rate_percent: Rate for assigned cluster
        - fitted_fee: Minimal fee for assigned cluster
        - predicted_commission: Predicted commission from fitted model
        - residual: Actual - predicted commission
    """
    result = analyze_rates_kmeans(amounts, commissions, n_clusters)

    amounts_arr = np.asarray(amounts, dtype=np.float64)
    commissions_arr = np.asarray(commissions, dtype=np.float64)

    # Build mapping from cluster_id to (rate, fee)
    cluster_params = {
        c["cluster_id"]: (c["rate_percent"] / 100, c["minimal_fee"])
        for c in result.get("clusters", [])
    }

    # This is a simplified version - would need full labels from clustering
    # For now, assign based on best fit
    n_samples = len(amounts)
    cluster_ids = np.full(n_samples, -1, dtype=np.int32)
    fitted_rates = np.full(n_samples, np.nan)
    fitted_fees = np.full(n_samples, np.nan)
    predicted = np.full(n_samples, np.nan)

    valid_mask = (amounts_arr > 0) & np.isfinite(amounts_arr) & np.isfinite(commissions_arr)

    for i in np.where(valid_mask)[0]:
        best_cluster = -1
        best_error = float("inf")

        for cid, (rate, fee) in cluster_params.items():
            pred = rate * amounts_arr[i] + fee
            error = abs(commissions_arr[i] - pred)
            if error < best_error:
                best_error = error
                best_cluster = cid

        if best_cluster >= 0:
            rate, fee = cluster_params[best_cluster]
            cluster_ids[i] = best_cluster
            fitted_rates[i] = rate * 100
            fitted_fees[i] = fee
            predicted[i] = rate * amounts_arr[i] + fee

    return pd.DataFrame({
        "amount": amounts_arr,
        "commission": commissions_arr,
        "cluster_id": cluster_ids,
        "fitted_rate_percent": fitted_rates,
        "fitted_fee": fitted_fees,
        "predicted_commission": predicted,
        "residual": commissions_arr - predicted,
    })
