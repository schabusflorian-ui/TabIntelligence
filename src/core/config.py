"""
Application configuration using Pydantic Settings.

Loads configuration from environment variables with validation and type checking.
"""
from pydantic_settings import BaseSettings
from pydantic import Field, field_validator
from typing import Optional
import os


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.

    All settings can be overridden by setting environment variables.
    Load from .env file automatically.
    """

    # =========================================================================
    # Database Configuration
    # =========================================================================
    database_url: str = Field(
        default="postgresql://emi:emi_dev@localhost:5432/emi",
        description="PostgreSQL database connection URL"
    )

    # =========================================================================
    # Redis Configuration
    # =========================================================================
    redis_url: str = Field(
        default="redis://localhost:6379/0",
        description="Redis connection URL for caching and queues"
    )

    # =========================================================================
    # S3/MinIO Configuration
    # =========================================================================
    s3_endpoint: str = Field(
        default="http://localhost:9000",
        description="S3 or MinIO endpoint URL"
    )
    s3_access_key: str = Field(
        default="minioadmin",
        description="S3/MinIO access key"
    )
    s3_secret_key: str = Field(
        default="minioadmin",
        description="S3/MinIO secret key"
    )
    s3_bucket: str = Field(
        default="financial-models",
        description="S3 bucket name for file storage"
    )
    s3_region: Optional[str] = Field(
        default="us-east-1",
        description="S3 region (for AWS S3)"
    )
    s3_verify_ssl: bool = Field(
        default=True,
        description="Verify SSL certificates for S3 connections (set to false ONLY for local MinIO with self-signed certs)"
    )

    # =========================================================================
    # Anthropic API Configuration
    # =========================================================================
    anthropic_api_key: str = Field(
        ...,  # Required field
        description="Anthropic API key for Claude"
    )

    # =========================================================================
    # Application Configuration
    # =========================================================================
    app_name: str = Field(
        default="DebtFund",
        description="Application name"
    )

    app_version: str = Field(
        default="0.1.0",
        description="Application version"
    )

    debug: bool = Field(
        default=False,
        description="Enable debug mode"
    )

    log_level: str = Field(
        default="INFO",
        description="Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)"
    )

    # =========================================================================
    # API Configuration
    # =========================================================================
    api_host: str = Field(
        default="0.0.0.0",
        description="API server host"
    )

    api_port: int = Field(
        default=8000,
        description="API server port"
    )

    cors_origins: list = Field(
        default=["http://localhost:3000"],
        description="CORS allowed origins (comma-separated list for security)"
    )

    # =========================================================================
    # Extraction Configuration
    # =========================================================================
    max_file_size_mb: int = Field(
        default=50,
        description="Maximum file upload size in MB"
    )

    extraction_timeout_seconds: int = Field(
        default=300,
        description="Maximum time for extraction in seconds"
    )

    claude_max_retries: int = Field(
        default=3,
        description="Maximum retries for Claude API calls"
    )

    claude_model: str = Field(
        default="claude-sonnet-4-20250514",
        description="Claude model to use for extraction"
    )

    # =========================================================================
    # Validators
    # =========================================================================

    @field_validator("anthropic_api_key")
    @classmethod
    def validate_api_key(cls, v: str) -> str:
        """Validate Anthropic API key format."""
        if not v:
            raise ValueError("ANTHROPIC_API_KEY is required")
        if not v.startswith("sk-ant-"):
            raise ValueError(
                "Invalid Anthropic API key format. "
                "Must start with 'sk-ant-'"
            )
        return v

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate log level."""
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        v_upper = v.upper()
        if v_upper not in valid_levels:
            raise ValueError(
                f"Invalid log level: {v}. "
                f"Must be one of {valid_levels}"
            )
        return v_upper

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, v: str) -> str:
        """Validate database URL format."""
        if not v.startswith("postgresql://"):
            raise ValueError(
                "Invalid database URL. Must start with 'postgresql://'"
            )
        return v

    @field_validator("max_file_size_mb")
    @classmethod
    def validate_max_file_size(cls, v: int) -> int:
        """Validate max file size."""
        if v <= 0 or v > 1000:
            raise ValueError(
                "Max file size must be between 1 and 1000 MB"
            )
        return v

    # =========================================================================
    # Computed Properties
    # =========================================================================

    @property
    def max_file_size_bytes(self) -> int:
        """Get max file size in bytes."""
        return self.max_file_size_mb * 1024 * 1024

    @property
    def is_development(self) -> bool:
        """Check if running in development mode."""
        return self.debug or self.log_level == "DEBUG"

    @property
    def is_production(self) -> bool:
        """Check if running in production mode."""
        return not self.is_development

    # =========================================================================
    # Config
    # =========================================================================

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
        "extra": "ignore",  # Ignore extra fields
    }


# ============================================================================
# Singleton Settings Instance
# ============================================================================

try:
    settings = Settings()
except Exception as e:
    # If settings fail to load, provide helpful error message
    print(f"ERROR: Failed to load settings: {str(e)}")
    print("Please check your .env file and environment variables.")
    raise


# ============================================================================
# Helper Functions
# ============================================================================

def get_settings() -> Settings:
    """
    Get the settings instance.

    Returns:
        Settings singleton instance

    Example:
        >>> from src.core.config import get_settings
        >>> settings = get_settings()
        >>> print(settings.database_url)
    """
    return settings


def print_settings():
    """Print all settings (masking sensitive values)."""
    print("=" * 60)
    print("DebtFund Configuration")
    print("=" * 60)

    for field_name, field_info in Settings.model_fields.items():
        value = getattr(settings, field_name)

        # Mask sensitive fields
        if any(keyword in field_name.lower() for keyword in ["key", "password", "secret", "token"]):
            if isinstance(value, str) and len(value) > 8:
                value = value[:4] + "..." + value[-4:]
            else:
                value = "***"

        print(f"{field_name:30} = {value}")

    print("=" * 60)


if __name__ == "__main__":
    # Test configuration loading
    print_settings()
