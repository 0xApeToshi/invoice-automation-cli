# src/services/base_client.py
"""
Base client interface for invoice providers.

This module defines the abstract base class that all provider-specific
clients must implement, ensuring consistent interface across different
advertising platforms (Meta Ads, Google Ads).
"""

import logging
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, List, Optional, Protocol, Tuple

import httpx
from rich.progress import Progress, TaskID

from ..models.invoice import Invoice
from ..models.config import RetryConfig
from ..utils.retry import RetryConfig as UtilsRetryConfig, async_retry_with_backoff

logger = logging.getLogger(__name__)


class InvoiceClient(Protocol):
    """
    Protocol defining the interface for invoice provider clients.
    
    This protocol ensures all provider implementations follow the same
    interface for fetching invoices, regardless of their specific API details.
    """

    async def get_invoices(
        self,
        start_date: datetime,
        end_date: datetime,
        progress: Progress,
        task_id: TaskID,
        client_filter: Optional[str] = None,
    ) -> List[Invoice]:
        """
        Retrieve invoices for the specified date range.

        Args:
            start_date: Start of date range for invoice retrieval
            end_date: End of date range for invoice retrieval
            progress: Rich progress bar for user feedback
            task_id: Task ID for progress updates
            client_filter: Optional filter for specific client/account

        Returns:
            List of Invoice objects

        Raises:
            ClientError: If invoice retrieval fails
        """
        ...

    async def test_connection(self) -> bool:
        """
        Test the connection to the provider API.

        Returns:
            True if connection is successful, False otherwise
        """
        ...


class ClientError(Exception):
    """Base exception for client-related errors."""

    def __init__(self, message: str, provider: str, status_code: Optional[int] = None) -> None:
        """
        Initialize client error.

        Args:
            message: Error message
            provider: Provider name where error occurred
            status_code: Optional HTTP status code
        """
        super().__init__(message)
        self.provider = provider
        self.status_code = status_code


class AuthenticationError(ClientError):
    """Raised when authentication with provider API fails."""
    pass


class RateLimitError(ClientError):
    """Raised when API rate limits are exceeded."""
    pass


class BaseInvoiceClient(ABC):
    """
    Abstract base class for invoice provider clients.
    
    Provides common functionality for HTTP requests, error handling,
    and retry logic that all provider implementations can use.
    """

    def __init__(self, retry_config: RetryConfig, timeout_seconds: int = 30) -> None:
        """
        Initialize base client with retry configuration.

        Args:
            retry_config: Configuration for retry behavior
            timeout_seconds: Request timeout in seconds
        """
        self.retry_config = retry_config
        self.timeout_seconds = timeout_seconds
        self._client: Optional[httpx.AsyncClient] = None

    @property
    def provider_name(self) -> str:
        """
        Get the provider name for this client.

        Returns:
            Provider name (e.g., "meta", "google")
        """
        return self.__class__.__name__.lower().replace("client", "").replace("ads", "")

    async def __aenter__(self) -> "BaseInvoiceClient":
        """Async context manager entry."""
        await self._ensure_client()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Async context manager exit."""
        await self.close()

    async def _ensure_client(self) -> httpx.AsyncClient:
        """
        Ensure HTTP client is initialized.

        Returns:
            Configured httpx.AsyncClient instance
        """
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout_seconds),
                limits=httpx.Limits(max_keepalive_connections=20, max_connections=100),
            )
        return self._client

    async def close(self) -> None:
        """Close the HTTP client and cleanup resources."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def _create_retry_config(self, retryable_exceptions: Tuple[type, ...] = ()) -> UtilsRetryConfig:
        """
        Create retry configuration for API calls.

        Args:
            retryable_exceptions: Tuple of exception types that should trigger retries

        Returns:
            UtilsRetryConfig instance for use with retry decorators
        """
        default_exceptions = (httpx.RequestError, httpx.TimeoutException, RateLimitError)
        all_exceptions = retryable_exceptions + default_exceptions

        return UtilsRetryConfig(
            max_attempts=self.retry_config.max_attempts,
            initial_wait=self.retry_config.initial_delay,
            max_wait=self.retry_config.max_delay,
            multiplier=self.retry_config.multiplier,
            retryable_exceptions=all_exceptions,
        )

    async def _make_request(
        self,
        method: str,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None,
        raise_for_status: bool = True,
    ) -> httpx.Response:
        """
        Make an HTTP request with error handling and logging.

        Args:
            method: HTTP method (GET, POST, etc.)
            url: Request URL
            headers: Optional request headers
            params: Optional query parameters
            json_data: Optional JSON payload
            raise_for_status: Whether to raise exception for HTTP errors

        Returns:
            HTTP response object

        Raises:
            ClientError: If request fails
            AuthenticationError: If authentication fails
            RateLimitError: If rate limits are exceeded
        """
        client = await self._ensure_client()
        
        logger.debug(f"Making {method} request to {url}")
        
        try:
            response = await client.request(
                method=method,
                url=url,
                headers=headers,
                params=params,
                json=json_data,
            )

            # Handle common HTTP status codes
            if response.status_code == 401:
                raise AuthenticationError(
                    f"Authentication failed: {response.text}",
                    self.provider_name,
                    response.status_code,
                )
            elif response.status_code == 429:
                raise RateLimitError(
                    f"Rate limit exceeded: {response.text}",
                    self.provider_name,
                    response.status_code,
                )
            elif raise_for_status and 400 <= response.status_code < 600:
                raise ClientError(
                    f"HTTP {response.status_code}: {response.text}",
                    self.provider_name,
                    response.status_code,
                )

            logger.debug(f"Request successful: {response.status_code}")
            return response

        except httpx.RequestError as e:
            logger.error(f"Request failed: {e}")
            raise ClientError(f"Request failed: {e}", self.provider_name) from e

    async def _make_retryable_request(
        self,
        method: str,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None,
    ) -> httpx.Response:
        """
        Make an HTTP request with automatic retry logic.

        This method wraps _make_request with retry logic for handling
        temporary failures and rate limits.

        Args:
            method: HTTP method
            url: Request URL
            headers: Optional request headers
            params: Optional query parameters
            json_data: Optional JSON payload

        Returns:
            HTTP response object

        Raises:
            ClientError: If all retries are exhausted
        """
        retry_config = self._create_retry_config()
        
        @async_retry_with_backoff(retry_config)
        async def make_request_with_retry() -> httpx.Response:
            return await self._make_request(
                method=method,
                url=url,
                headers=headers,
                params=params,
                json_data=json_data,
                raise_for_status=True,
            )
        
        return await make_request_with_retry()

    def _update_progress(
        self,
        progress: Progress,
        task_id: TaskID,
        description: str,
        advance: int = 0,
    ) -> None:
        """
        Update progress bar with current status.

        Args:
            progress: Rich progress bar instance
            task_id: Task ID for progress updates
            description: Current operation description
            advance: Number of steps to advance
        """
        progress.update(task_id, description=description, advance=advance)
        logger.debug(f"Progress update: {description}")

    @abstractmethod
    async def get_invoices(
        self,
        start_date: datetime,
        end_date: datetime,
        progress: Progress,
        task_id: TaskID,
        client_filter: Optional[str] = None,
    ) -> List[Invoice]:
        """
        Retrieve invoices for the specified date range.

        This method must be implemented by each provider-specific client.

        Args:
            start_date: Start of date range for invoice retrieval
            end_date: End of date range for invoice retrieval
            progress: Rich progress bar for user feedback
            task_id: Task ID for progress updates
            client_filter: Optional filter for specific client/account

        Returns:
            List of Invoice objects

        Raises:
            ClientError: If invoice retrieval fails
        """
        pass

    @abstractmethod
    async def test_connection(self) -> bool:
        """
        Test the connection to the provider API.

        This method should verify that authentication is working
        and the API is accessible.

        Returns:
            True if connection is successful, False otherwise
        """
        pass

    @abstractmethod
    def _get_base_headers(self) -> Dict[str, str]:
        """
        Get base headers for API requests.

        Returns:
            Dictionary of headers to include in all requests
        """
        pass
