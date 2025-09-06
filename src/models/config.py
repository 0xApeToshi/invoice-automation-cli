# src/models/config.py
"""
Configuration models for the invoice automation application.

This module defines Pydantic models for application configuration,
including API credentials, output settings, and retry parameters.
All configuration is loaded from environment variables for security.
"""

from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class MetaAdsConfig(BaseModel):
    """
    Configuration for Meta Ads API integration.
    
    Contains credentials and settings required to authenticate
    with and interact with the Meta Ads API.
    """

    business_id: str = Field(..., description="Meta Business Manager ID")
    access_token: str = Field(..., description="Meta Graph API access token")
    api_version: str = Field(default="v21.0", description="Meta API version to use")

    @field_validator("business_id")
    @classmethod
    def validate_business_id(cls, v: str) -> str:
        """
        Validate Meta Business ID format.

        Args:
            v: Business ID to validate

        Returns:
            Validated business ID

        Raises:
            ValueError: If business ID is invalid
        """
        if not v or not v.isdigit():
            raise ValueError("Meta Business ID must be a numeric string")
        return v

    @field_validator("access_token")
    @classmethod
    def validate_access_token(cls, v: str) -> str:
        """
        Validate Meta access token format.

        Args:
            v: Access token to validate

        Returns:
            Validated access token

        Raises:
            ValueError: If access token is invalid
        """
        if not v or len(v) < 20:
            raise ValueError("Meta access token appears to be invalid")
        return v


class GoogleAdsConfig(BaseModel):
    """
    Configuration for Google Ads API integration.
    
    Contains OAuth2 credentials and settings required to authenticate
    with and interact with the Google Ads API.
    """

    customer_id: str = Field(..., description="Google Ads customer ID")
    client_id: str = Field(..., description="OAuth2 client ID")
    client_secret: str = Field(..., description="OAuth2 client secret")
    refresh_token: str = Field(..., description="OAuth2 refresh token")
    developer_token: str = Field(..., description="Google Ads developer token")

    @field_validator("customer_id")
    @classmethod
    def validate_customer_id(cls, v: str) -> str:
        """
        Validate Google Ads customer ID format.

        Args:
            v: Customer ID to validate

        Returns:
            Validated customer ID (with hyphens removed)

        Raises:
            ValueError: If customer ID is invalid
        """
        # Remove hyphens and validate
        clean_id = v.replace("-", "")
        if not clean_id.isdigit() or len(clean_id) != 10:
            raise ValueError("Google Ads customer ID must be a 10-digit number")
        return clean_id

    @field_validator("developer_token")
    @classmethod
    def validate_developer_token(cls, v: str) -> str:
        """
        Validate Google Ads developer token format.

        Args:
            v: Developer token to validate

        Returns:
            Validated developer token

        Raises:
            ValueError: If developer token is invalid
        """
        if not v or len(v) < 20:
            raise ValueError("Google Ads developer token appears to be invalid")
        return v


class RetryConfig(BaseModel):
    """
    Configuration for retry behavior and error handling.
    
    Defines parameters for exponential backoff and retry logic
    when API calls fail due to rate limits or temporary errors.
    """

    max_attempts: int = Field(default=3, ge=1, le=10, description="Maximum retry attempts")
    initial_delay: float = Field(default=1.0, ge=0.1, description="Initial retry delay in seconds")
    max_delay: float = Field(default=60.0, ge=1.0, description="Maximum retry delay in seconds")
    multiplier: float = Field(default=2.0, ge=1.0, description="Exponential backoff multiplier")
    timeout_seconds: int = Field(default=30, ge=5, description="Request timeout in seconds")


class ApplicationConfig(BaseModel):
    """
    Main application configuration.
    
    Aggregates all configuration sections and provides validation
    for the complete application setup.
    """

    meta: Optional[MetaAdsConfig] = Field(default=None, description="Meta Ads configuration")
    google: Optional[GoogleAdsConfig] = Field(default=None, description="Google Ads configuration")
    retry: RetryConfig = Field(default_factory=RetryConfig, description="Retry configuration")
    output_dir: Path = Field(default=Path("./invoices"), description="Output directory for invoices")
    log_level: str = Field(default="INFO", description="Logging level")
    debug: bool = Field(default=False, description="Enable debug mode")

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """
        Validate logging level.

        Args:
            v: Log level to validate

        Returns:
            Validated log level

        Raises:
            ValueError: If log level is invalid
        """
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if v.upper() not in valid_levels:
            raise ValueError(f"Log level must be one of: {', '.join(valid_levels)}")
        return v.upper()

    @field_validator("output_dir")
    @classmethod
    def validate_output_dir(cls, v: Path) -> Path:
        """
        Validate and normalize output directory path.

        Args:
            v: Output directory path

        Returns:
            Normalized absolute path
        """
        return v.expanduser().resolve()

    def has_meta_config(self) -> bool:
        """
        Check if Meta Ads configuration is available.

        Returns:
            True if Meta configuration is complete
        """
        return self.meta is not None

    def has_google_config(self) -> bool:
        """
        Check if Google Ads configuration is available.

        Returns:
            True if Google configuration is complete
        """
        return self.google is not None

    def get_enabled_providers(self) -> list[str]:
        """
        Get list of enabled providers based on configuration.

        Returns:
            List of provider names ("meta", "google") that are configured
        """
        providers = []
        if self.has_meta_config():
            providers.append("meta")
        if self.has_google_config():
            providers.append("google")
        return providers
