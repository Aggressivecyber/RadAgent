"""Custom exceptions for the model gateway."""

from __future__ import annotations


class ModelGatewayError(Exception):
    """Base exception for model gateway errors."""


class ModelProviderError(ModelGatewayError):
    """Error from the model provider API."""


class ModelConfigError(ModelGatewayError):
    """Configuration error (missing env vars, invalid profile)."""


class ModelTimeoutError(ModelGatewayError):
    """Model call timed out."""
