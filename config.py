"""
Configuration file for Pandas Query Agent

Centralized configuration for model selection, paths, and settings.
"""

import os
from pathlib import Path

# Project paths
PROJECT_ROOT = Path(__file__).parent
DATA_DIR = PROJECT_ROOT / "data"
SERVER_SCRIPT = PROJECT_ROOT / "mcp_server_pandas.py"

# Model configurations
MODELS = {
    "sonnet": {
        "id": "claude-sonnet-4-20250514",
        "name": "Claude Sonnet 4.5",
        "max_tokens": 4096,
        "thinking_enabled": True,
        "thinking_budget": 2000,
        "description": "Most capable model with extended thinking for complex queries"
    },
    "haiku": {
        "id": "claude-haiku-4-20250520",
        "name": "Claude Haiku 4.5",
        "max_tokens": 4096,
        "thinking_enabled": False,
        "thinking_budget": 0,
        "description": "Fast and efficient model for simpler queries"
    }
}

# Default model
DEFAULT_MODEL = "sonnet"

# API configuration
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")

# Query settings
MAX_RESULT_ROWS = 1000  # Maximum rows to return in tool responses
MAX_UNIQUE_VALUES = 100  # Maximum unique values to return
DEFAULT_TOP_N = 10  # Default number of rows for top_n queries

# Server settings
MCP_TRANSPORT = "stdio"  # Transport type for MCP (stdio or sse)

# Data file settings
SUPPORTED_FORMATS = [".csv", ".parquet", ".json"]

# Expected DataFrame columns
EXPECTED_COLUMNS = [
    "comission_eur",
    "amount_eur",
    "card_brand_group",
    "traffic_type_group",
    "transaction_comission",
    "country",
    "order_id",
    "created_date",
    "manager_id",
    "merchant_name",
    "gate_id",
    "merchant_id",
    "company_id",
    "company_name",
    "white_label_id",
    "processor_name",
    "processor_id",
    "transaction_type",
    "transaction_status",
    "agent_fee",
    "card_type",
    "tax_reserve_cost",
    "monthly_fee",
    "item_id",
    "records"
]


def get_model_config(model_type: str = DEFAULT_MODEL) -> dict:
    """Get configuration for a specific model."""
    if model_type not in MODELS:
        raise ValueError(f"Invalid model type: {model_type}. Choose from {list(MODELS.keys())}")
    return MODELS[model_type]


def validate_api_key() -> bool:
    """Check if Anthropic API key is set."""
    return bool(ANTHROPIC_API_KEY)


def validate_data_file(file_path: str) -> bool:
    """Validate if data file exists and has supported format."""
    path = Path(file_path)
    return path.exists() and path.suffix in SUPPORTED_FORMATS
