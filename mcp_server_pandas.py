#!/usr/bin/env python3
"""
MCP Server for Pandas DataFrame Query Operations

This server provides tools for querying and analyzing transaction data stored in a Pandas DataFrame.
It supports SQL-like operations including filtering, aggregation, grouping, and sorting.
"""

import json
import os
from typing import Optional

import pandas as pd
from fastmcp import FastMCP

# Initialize MCP server
mcp = FastMCP("pandas-query-server")

# Global DataFrame storage
_dataframe: Optional[pd.DataFrame] = None
_data_path: Optional[str] = None


def load_dataframe(file_path: str) -> pd.DataFrame:
    """Load DataFrame from file (CSV, Parquet, or JSON)."""
    global _dataframe, _data_path

    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Data file not found: {file_path}")

    ext = os.path.splitext(file_path)[1].lower()

    if ext == ".csv":
        _dataframe = pd.read_csv(file_path)
    elif ext == ".parquet":
        _dataframe = pd.read_parquet(file_path)
    elif ext == ".json":
        _dataframe = pd.read_json(file_path)
    else:
        raise ValueError(f"Unsupported file format: {ext}. Use CSV, Parquet, or JSON.")

    _data_path = file_path
    return _dataframe


def get_dataframe() -> pd.DataFrame:
    """Get the current DataFrame or raise an error if not loaded."""
    if _dataframe is None:
        raise RuntimeError("DataFrame not loaded. Please load data first.")
    return _dataframe


def dataframe_to_json(df: pd.DataFrame, limit: int = 1000) -> str:
    """Convert DataFrame to JSON string with optional row limit."""
    if len(df) > limit:
        result = {
            "data": df.head(limit).to_dict(orient="records"),
            "total_rows": len(df),
            "returned_rows": limit,
            "truncated": True,
            "message": f"Results truncated to {limit} rows out of {len(df)} total rows."
        }
    else:
        result = {
            "data": df.to_dict(orient="records"),
            "total_rows": len(df),
            "returned_rows": len(df),
            "truncated": False
        }

    return json.dumps(result, indent=2, default=str)


@mcp.tool()
def get_schema() -> str:
    """
    Get DataFrame schema including column names, data types, and basic statistics.

    Returns:
        JSON string with schema information including columns, types, null counts, and sample values.
    """
    df = get_dataframe()

    schema_info = {
        "total_rows": len(df),
        "total_columns": len(df.columns),
        "columns": []
    }

    for col in df.columns:
        col_info = {
            "name": col,
            "dtype": str(df[col].dtype),
            "null_count": int(df[col].isnull().sum()),
            "null_percentage": float(df[col].isnull().sum() / len(df) * 100),
            "unique_count": int(df[col].nunique())
        }

        # Add sample values
        sample_values = df[col].dropna().head(5).tolist()
        col_info["sample_values"] = [str(v) for v in sample_values]

        # Add numeric stats if applicable
        if pd.api.types.is_numeric_dtype(df[col]):
            col_info["statistics"] = {
                "min": float(df[col].min()) if not pd.isna(df[col].min()) else None,
                "max": float(df[col].max()) if not pd.isna(df[col].max()) else None,
                "mean": float(df[col].mean()) if not pd.isna(df[col].mean()) else None,
                "median": float(df[col].median()) if not pd.isna(df[col].median()) else None
            }

        schema_info["columns"].append(col_info)

    return json.dumps(schema_info, indent=2)


@mcp.tool()
def filter_by_value(
    column_name: str,
    value: str,
    operator: str = "equals"
) -> str:
    """
    Filter DataFrame rows based on a single column value.

    Args:
        column_name: Name of the column to filter
        value: Value to filter by (will be converted to appropriate type)
        operator: Comparison operator - 'equals', 'not_equals', 'contains', 'starts_with',
                 'ends_with', 'greater_than', 'less_than', 'greater_equal', 'less_equal'

    Returns:
        JSON string with filtered rows
    """
    df = get_dataframe()

    if column_name not in df.columns:
        raise ValueError(f"Column '{column_name}' not found. Available columns: {list(df.columns)}")

    col = df[column_name]

    # Try to convert value to the column's dtype
    try:
        if pd.api.types.is_numeric_dtype(col):
            value = float(value)
        elif pd.api.types.is_datetime64_any_dtype(col):
            value = pd.to_datetime(value)
    except (ValueError, TypeError):
        pass  # Keep as string if conversion fails

    # Apply filter based on operator
    if operator == "equals":
        mask = col == value
    elif operator == "not_equals":
        mask = col != value
    elif operator == "contains":
        mask = col.astype(str).str.contains(str(value), case=False, na=False)
    elif operator == "starts_with":
        mask = col.astype(str).str.startswith(str(value), na=False)
    elif operator == "ends_with":
        mask = col.astype(str).str.endswith(str(value), na=False)
    elif operator == "greater_than":
        mask = col > value
    elif operator == "less_than":
        mask = col < value
    elif operator == "greater_equal":
        mask = col >= value
    elif operator == "less_equal":
        mask = col <= value
    else:
        raise ValueError(f"Invalid operator: {operator}")

    filtered_df = df[mask]
    return dataframe_to_json(filtered_df)


@mcp.tool()
def filter_by_range(
    column_name: str,
    min_value: Optional[str] = None,
    max_value: Optional[str] = None,
    inclusive: str = "both"
) -> str:
    """
    Filter DataFrame rows by a range of values (numeric or date).

    Args:
        column_name: Name of the column to filter
        min_value: Minimum value (inclusive/exclusive based on 'inclusive' param)
        max_value: Maximum value (inclusive/exclusive based on 'inclusive' param)
        inclusive: 'both', 'left', 'right', or 'neither' for boundary inclusion

    Returns:
        JSON string with filtered rows
    """
    df = get_dataframe()

    if column_name not in df.columns:
        raise ValueError(f"Column '{column_name}' not found. Available columns: {list(df.columns)}")

    col = df[column_name]

    # Convert values to appropriate type
    if pd.api.types.is_numeric_dtype(col):
        min_val = float(min_value) if min_value is not None else None
        max_val = float(max_value) if max_value is not None else None
    elif pd.api.types.is_datetime64_any_dtype(col):
        min_val = pd.to_datetime(min_value) if min_value is not None else None
        max_val = pd.to_datetime(max_value) if max_value is not None else None
    else:
        min_val = min_value
        max_val = max_value

    # Apply range filter
    mask = pd.Series([True] * len(df), index=df.index)

    if min_val is not None:
        if inclusive in ["both", "left"]:
            mask &= col >= min_val
        else:
            mask &= col > min_val

    if max_val is not None:
        if inclusive in ["both", "right"]:
            mask &= col <= max_val
        else:
            mask &= col < max_val

    filtered_df = df[mask]
    return dataframe_to_json(filtered_df)


@mcp.tool()
def get_aggregates(
    column_name: str,
    agg_function: str,
    filter_column: Optional[str] = None,
    filter_value: Optional[str] = None
) -> str:
    """
    Get aggregate statistics for a column (min, max, sum, mean, count, etc.).

    Args:
        column_name: Name of the column to aggregate
        agg_function: Aggregation function - 'min', 'max', 'sum', 'mean', 'median',
                     'count', 'std', 'var', 'nunique'
        filter_column: Optional column to filter by before aggregating
        filter_value: Optional value to filter by

    Returns:
        JSON string with aggregate result
    """
    df = get_dataframe()

    if column_name not in df.columns:
        raise ValueError(f"Column '{column_name}' not found. Available columns: {list(df.columns)}")

    # Apply filter if specified
    if filter_column and filter_value:
        if filter_column not in df.columns:
            raise ValueError(f"Filter column '{filter_column}' not found.")
        df = df[df[filter_column] == filter_value]

    col = df[column_name]

    # Apply aggregation
    agg_functions = {
        "min": lambda c: c.min(),
        "max": lambda c: c.max(),
        "sum": lambda c: c.sum(),
        "mean": lambda c: c.mean(),
        "median": lambda c: c.median(),
        "count": lambda c: c.count(),
        "std": lambda c: c.std(),
        "var": lambda c: c.var(),
        "nunique": lambda c: c.nunique()
    }

    if agg_function not in agg_functions:
        raise ValueError(f"Invalid aggregation function: {agg_function}")

    result = agg_functions[agg_function](col)

    response = {
        "column": column_name,
        "aggregation": agg_function,
        "result": float(result) if pd.api.types.is_numeric_dtype(type(result)) else str(result),
        "row_count": len(df)
    }

    if filter_column and filter_value:
        response["filter"] = {
            "column": filter_column,
            "value": filter_value
        }

    return json.dumps(response, indent=2, default=str)


@mcp.tool()
def get_top_n(
    column_name: str,
    n: int = 10,
    ascending: bool = False
) -> str:
    """
    Get top N rows sorted by a column value.

    Args:
        column_name: Name of the column to sort by
        n: Number of rows to return (default 10)
        ascending: If True, return smallest values; if False, return largest values

    Returns:
        JSON string with top N rows
    """
    df = get_dataframe()

    if column_name not in df.columns:
        raise ValueError(f"Column '{column_name}' not found. Available columns: {list(df.columns)}")

    sorted_df = df.sort_values(by=column_name, ascending=ascending).head(n)
    return dataframe_to_json(sorted_df, limit=n)


@mcp.tool()
def get_unique_values(
    column_name: str,
    limit: int = 100
) -> str:
    """
    Get unique values from a column.

    Args:
        column_name: Name of the column
        limit: Maximum number of unique values to return (default 100)

    Returns:
        JSON string with unique values and their counts
    """
    df = get_dataframe()

    if column_name not in df.columns:
        raise ValueError(f"Column '{column_name}' not found. Available columns: {list(df.columns)}")

    value_counts = df[column_name].value_counts().head(limit)

    result = {
        "column": column_name,
        "unique_count": int(df[column_name].nunique()),
        "returned_count": len(value_counts),
        "values": [
            {
                "value": str(val),
                "count": int(count)
            }
            for val, count in value_counts.items()
        ]
    }

    return json.dumps(result, indent=2)


@mcp.tool()
def group_by_aggregate(
    group_columns: str,
    agg_column: str,
    agg_function: str = "sum"
) -> str:
    """
    Group DataFrame by one or more columns and aggregate.

    Args:
        group_columns: Comma-separated column names to group by
        agg_column: Column to aggregate
        agg_function: Aggregation function - 'sum', 'mean', 'count', 'min', 'max', 'median'

    Returns:
        JSON string with grouped results
    """
    df = get_dataframe()

    # Parse group columns
    group_cols = [col.strip() for col in group_columns.split(",")]

    # Validate columns
    for col in group_cols:
        if col not in df.columns:
            raise ValueError(f"Column '{col}' not found. Available columns: {list(df.columns)}")

    if agg_column not in df.columns:
        raise ValueError(f"Aggregation column '{agg_column}' not found.")

    # Perform groupby
    agg_functions = {
        "sum": "sum",
        "mean": "mean",
        "count": "count",
        "min": "min",
        "max": "max",
        "median": "median"
    }

    if agg_function not in agg_functions:
        raise ValueError(f"Invalid aggregation function: {agg_function}")

    grouped = df.groupby(group_cols)[agg_column].agg(agg_functions[agg_function]).reset_index()
    grouped.columns = list(group_cols) + [f"{agg_column}_{agg_function}"]

    # Sort by aggregated value descending
    grouped = grouped.sort_values(by=grouped.columns[-1], ascending=False)

    return dataframe_to_json(grouped)


@mcp.tool()
def filter_by_multiple_conditions(
    conditions: str,
    logic: str = "AND"
) -> str:
    """
    Filter DataFrame by multiple conditions with AND/OR logic.

    Args:
        conditions: JSON string with list of conditions, each containing:
                   {"column": "col_name", "operator": "equals", "value": "val"}
        logic: 'AND' or 'OR' to combine conditions

    Returns:
        JSON string with filtered rows
    """
    df = get_dataframe()

    # Parse conditions
    try:
        conditions_list = json.loads(conditions)
    except json.JSONDecodeError:
        raise ValueError("Invalid JSON format for conditions")

    if not isinstance(conditions_list, list):
        raise ValueError("Conditions must be a list")

    # Build mask
    masks = []

    for condition in conditions_list:
        col_name = condition.get("column")
        operator = condition.get("operator", "equals")
        value = condition.get("value")

        if col_name not in df.columns:
            raise ValueError(f"Column '{col_name}' not found")

        col = df[col_name]

        # Convert value to appropriate type
        try:
            if pd.api.types.is_numeric_dtype(col):
                value = float(value)
        except (ValueError, TypeError):
            pass

        # Apply operator
        if operator == "equals":
            mask = col == value
        elif operator == "not_equals":
            mask = col != value
        elif operator == "contains":
            mask = col.astype(str).str.contains(str(value), case=False, na=False)
        elif operator == "greater_than":
            mask = col > value
        elif operator == "less_than":
            mask = col < value
        elif operator == "greater_equal":
            mask = col >= value
        elif operator == "less_equal":
            mask = col <= value
        else:
            raise ValueError(f"Invalid operator: {operator}")

        masks.append(mask)

    # Combine masks
    if logic.upper() == "AND":
        final_mask = masks[0]
        for mask in masks[1:]:
            final_mask &= mask
    elif logic.upper() == "OR":
        final_mask = masks[0]
        for mask in masks[1:]:
            final_mask |= mask
    else:
        raise ValueError(f"Invalid logic: {logic}. Use 'AND' or 'OR'")

    filtered_df = df[final_mask]
    return dataframe_to_json(filtered_df)


@mcp.tool()
def get_row_count(
    filter_column: Optional[str] = None,
    filter_value: Optional[str] = None
) -> str:
    """
    Get total row count or filtered row count.

    Args:
        filter_column: Optional column to filter by
        filter_value: Optional value to filter by

    Returns:
        JSON string with row count
    """
    df = get_dataframe()

    if filter_column and filter_value:
        if filter_column not in df.columns:
            raise ValueError(f"Column '{filter_column}' not found")
        filtered_df = df[df[filter_column] == filter_value]
        count = len(filtered_df)
        result = {
            "count": count,
            "filtered": True,
            "filter": {
                "column": filter_column,
                "value": filter_value
            }
        }
    else:
        count = len(df)
        result = {
            "count": count,
            "filtered": False
        }

    return json.dumps(result, indent=2)


@mcp.tool()
def search_text(
    search_term: str,
    columns: Optional[str] = None,
    case_sensitive: bool = False
) -> str:
    """
    Search for text across specified columns or all text columns.

    Args:
        search_term: Text to search for
        columns: Comma-separated column names to search (searches all if not specified)
        case_sensitive: Whether search should be case-sensitive

    Returns:
        JSON string with matching rows
    """
    df = get_dataframe()

    # Determine columns to search
    if columns:
        search_cols = [col.strip() for col in columns.split(",")]
        for col in search_cols:
            if col not in df.columns:
                raise ValueError(f"Column '{col}' not found")
    else:
        # Search all object/string columns
        search_cols = df.select_dtypes(include=["object", "string"]).columns.tolist()

    # Build search mask
    mask = pd.Series([False] * len(df), index=df.index)

    for col in search_cols:
        if case_sensitive:
            mask |= df[col].astype(str).str.contains(search_term, na=False, regex=False)
        else:
            mask |= df[col].astype(str).str.contains(search_term, case=False, na=False, regex=False)

    filtered_df = df[mask]

    result = {
        "search_term": search_term,
        "columns_searched": search_cols,
        "case_sensitive": case_sensitive,
        "matches_found": len(filtered_df),
        "data": filtered_df.to_dict(orient="records") if len(filtered_df) <= 100 else filtered_df.head(100).to_dict(orient="records"),
        "truncated": len(filtered_df) > 100
    }

    return json.dumps(result, indent=2, default=str)


def main():
    """Main entry point for the MCP server."""
    import sys

    # Check for data file argument
    if len(sys.argv) < 2:
        print("Usage: python mcp_server_pandas.py <data_file_path>", file=sys.stderr)
        print("Supported formats: CSV, Parquet, JSON", file=sys.stderr)
        sys.exit(1)

    data_file = sys.argv[1]

    try:
        # Load the DataFrame
        load_dataframe(data_file)
        print(f"Successfully loaded data from {data_file}", file=sys.stderr)
        print(f"DataFrame shape: {_dataframe.shape}", file=sys.stderr)

        # Run the MCP server
        mcp.run()
    except Exception as e:
        print(f"Error starting server: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
