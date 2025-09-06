# src/config/settings.py
"""
Application settings and configuration loading.

This module handles loading configuration from environment variables
and providing validated configuration objects throughout the application.
Uses python-dotenv for development environment support.
"""

import os
import logging
from pathlib import Path
from typing import Optional, Union

from dotenv import load_dotenv
from pydantic import ValidationError

from ..models.config import ApplicationConfig, GoogleAdsConfig, MetaAdsConfig, RetryConfig

logger = logging.getLogger(__name__)


class ConfigurationError(Exception):
    """Raised when configuration is invalid or incomplete."""
    pass


class Settings:
    """
    Centralized settings management for the application.
    
    Loads configuration from environment variables and provides
    validated configuration objects with proper error handling.
    """

    def __init__(self, env_file: Optional[Path] = None) -> None:
        """
        Initialize settings manager.

        Args:
            env_file: Optional path to .env file to load
        """
        self._config: Optional[ApplicationConfig] = None
        self._load_environment(env_file)

    def _load_environment(self, env_file: Optional[Path]) -> None:
        """
        Load environment variables from .env file if it exists.

        Args:
            env_file: Optional path to .env file
        """
        if env_file and env_file.exists():
            load_dotenv(env_file)
            logger.debug(f"Loaded environment from {env_file}")
        else:
            # Try to find .env in current directory
            default_env = Path(".env")
            if default_env.exists():
                load_dotenv(default_env)
                logger.debug(f"Loaded environment from {default_env}")

    def _load_meta_config(self) -> Optional[MetaAdsConfig]:
        """
        Load Meta Ads configuration from environment variables.

        Returns:
            MetaAdsConfig if all required variables are present, None otherwise
        """
        business_id = os.getenv("META_BUSINESS_ID")
        access_token = os.getenv("META_ACCESS_TOKEN")
        api_version = os.getenv("META_API_VERSION", "v21.0")

        if not business_id or not access_token:
            logger.debug("Meta Ads configuration incomplete")
            return None

        try:
            return MetaAdsConfig(
                business_id=business_id,
                access_token=access_token,
                api_version=api_version,
            )
        except ValidationError as e:
            logger.error(f"Invalid Meta Ads configuration: {e}")
            raise ConfigurationError(f"Invalid Meta Ads configuration: {e}") from e

    def _load_google_config(self) -> Optional[GoogleAdsConfig]:
        """
        Load Google Ads configuration from environment variables.

        Returns:
            GoogleAdsConfig if all required variables are present, None otherwise
        """
        customer_id = os.getenv("GOOGLE_CUSTOMER_ID")
        client_id = os.getenv("GOOGLE_CLIENT_ID")
        client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
        refresh_token = os.getenv("GOOGLE_REFRESH_TOKEN")
        developer_token = os.getenv("GOOGLE_DEVELOPER_TOKEN")

        if not all([customer_id, client_id, client_secret, refresh_token, developer_token]):
            logger.debug("Google Ads configuration incomplete")
            return None

        try:
            # All values are guaranteed to be non-None at this point due to the check above
            return GoogleAdsConfig(
                customer_id=customer_id,  # type: ignore
                client_id=client_id,  # type: ignore
                client_secret=client_secret,  # type: ignore
                refresh_token=refresh_token,  # type: ignore
                developer_token=developer_token,  # type: ignore
            )
        except ValidationError as e:
            logger.error(f"Invalid Google Ads configuration: {e}")
            raise ConfigurationError(f"Invalid Google Ads configuration: {e}") from e

    def _load_retry_config(self) -> RetryConfig:
        """
        Load retry configuration from environment variables.

        Returns:
            RetryConfig with values from environment or defaults
        """
        try:
            return RetryConfig(
                max_attempts=int(os.getenv("MAX_RETRIES", "3")),
                initial_delay=float(os.getenv("RETRY_DELAY", "1.0")),
                timeout_seconds=int(os.getenv("TIMEOUT_SECONDS", "30")),
            )
        except (ValueError, ValidationError) as e:
            logger.warning(f"Invalid retry configuration, using defaults: {e}")
            return RetryConfig()

    def get_config(self) -> ApplicationConfig:
        """
        Get the complete application configuration.

        Returns:
            Validated ApplicationConfig instance

        Raises:
            ConfigurationError: If configuration is invalid
        """
        if self._config is not None:
            return self._config

        try:
            output_dir = Path(os.getenv("OUTPUT_DIR", "./invoices"))
            log_level = os.getenv("LOG_LEVEL", "INFO")
            debug = os.getenv("DEBUG", "false").lower() in ("true", "1", "yes", "on")

            self._config = ApplicationConfig(
                meta=self._load_meta_config(),
                google=self._load_google_config(),
                retry=self._load_retry_config(),
                output_dir=output_dir,
                log_level=log_level,
                debug=debug,
            )

            # Validate that at least one provider is configured
            if not self._config.has_meta_config() and not self._config.has_google_config():
                raise ConfigurationError(
                    "No providers configured. Please set up Meta Ads or Google Ads credentials."
                )

            logger.debug(
                f"Configuration loaded successfully. Enabled providers: {self._config.get_enabled_providers()}"
            )
            return self._config

        except ValidationError as e:
            logger.error(f"Configuration validation failed: {e}")
            raise ConfigurationError(f"Configuration validation failed: {e}") from e

    def reload_config(self, env_file: Optional[Path] = None) -> ApplicationConfig:
        """
        Reload configuration from environment variables.

        Args:
            env_file: Optional path to .env file to load

        Returns:
            Reloaded ApplicationConfig instance
        """
        self._config = None
        self._load_environment(env_file)
        return self.get_config()

    def validate_provider_config(self, provider: str) -> bool:
        """
        Validate that a specific provider is properly configured.

        Args:
            provider: Provider name ("meta" or "google")

        Returns:
            True if provider is properly configured

        Raises:
            ConfigurationError: If provider is not configured or invalid
        """
        config = self.get_config()

        if provider == "meta":
            if not config.has_meta_config():
                raise ConfigurationError("Meta Ads configuration not found")
            return True
        elif provider == "google":
            if not config.has_google_config():
                raise ConfigurationError("Google Ads configuration not found")
            return True
        else:
            raise ConfigurationError(f"Unknown provider: {provider}")

    def get_provider_config(self, provider: str) -> Union[MetaAdsConfig, GoogleAdsConfig]:
        """
        Get configuration for a specific provider.

        Args:
            provider: Provider name ("meta" or "google")

        Returns:
            Provider-specific configuration

        Raises:
            ConfigurationError: If provider is not configured
        """
        config = self.get_config()

        if provider == "meta":
            if config.meta is None:
                raise ConfigurationError("Meta Ads configuration not found")
            return config.meta
        elif provider == "google":
            if config.google is None:
                raise ConfigurationError("Google Ads configuration not found")
            return config.google
        else:
            raise ConfigurationError(f"Unknown provider: {provider}")


# Global settings instance
_settings: Optional[Settings] = None


def get_settings(env_file: Optional[Path] = None) -> Settings:
    """
    Get or create the global settings instance.

    Args:
        env_file: Optional path to .env file to load

    Returns:
        Settings instance
    """
    global _settings
    if _settings is None:
        _settings = Settings(env_file)
    return _settings


def get_config(env_file: Optional[Path] = None) -> ApplicationConfig:
    """
    Get the application configuration.

    Args:
        env_file: Optional path to .env file to load

    Returns:
        ApplicationConfig instance
    """
    return get_settings(env_file).get_config()
