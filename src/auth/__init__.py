"""
Authentication and authorization module for DebtFund.

Provides API key authentication, rate limiting integration, and audit trail.
"""

from src.auth.api_key import generate_api_key, verify_api_key
from src.auth.dependencies import get_current_api_key
from src.auth.models import APIKey

__all__ = [
    "APIKey",
    "generate_api_key",
    "verify_api_key",
    "get_current_api_key",
]
