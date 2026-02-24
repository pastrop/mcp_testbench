"""Application configuration using Pydantic settings."""

from pathlib import Path
from typing import List, Union

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Anthropic API
    anthropic_api_key: str = Field(
        default="", description="Anthropic API key for Claude"
    )

    # Application
    app_env: str = Field(default="development", description="Application environment")
    app_host: str = Field(default="0.0.0.0", description="Host to bind the server")
    app_port: int = Field(default=8000, description="Port to bind the server")
    app_debug: bool = Field(default=False, description="Enable debug mode")

    # CORS
    cors_origins: Union[List[str], str] = Field(
        default="http://localhost:3000,http://localhost:5173",
        description="Allowed CORS origins (comma-separated string or list)",
    )

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, v):
        """Parse CORS origins from comma-separated string or list."""
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",")]
        return v

    # Data paths
    contracts_data_path: str = Field(
        default="../data/Parsed_Contracts",
        description="Path to parsed contracts directory",
    )

    # Demo mode
    demo_mode: bool = Field(
        default=False,
        description="Use demo UI specs instead of AI generation (for testing without API credits)",
    )

    @property
    def contracts_directory(self) -> Path:
        """Get the absolute path to contracts directory."""
        base_path = Path(__file__).parent.parent.parent
        return (base_path / self.contracts_data_path).resolve()


settings = Settings()
