# src/utils/retry.py
"""
Retry utilities with exponential backoff for handling API failures.

This module provides decorators and utilities for implementing retry logic
with exponential backoff, particularly useful for API calls that may fail
due to rate limits or temporary service issues.
"""

import asyncio
import logging
from functools import wraps
from typing import Any, Callable, Tuple, Type, TypeVar, Union

from tenacity import (
    AsyncRetrying,
    RetryError,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


class RetryConfig:
    """
    Configuration for retry behavior.
    
    Centralizes retry settings to ensure consistent behavior
    across the application.
    """

    def __init__(
        self,
        max_attempts: int = 3,
        initial_wait: float = 1.0,
        max_wait: float = 60.0,
        multiplier: float = 2.0,
        retryable_exceptions: Tuple[Type[Exception], ...] = (),
    ) -> None:
        """
        Initialize retry configuration.

        Args:
            max_attempts: Maximum number of retry attempts
            initial_wait: Initial wait time in seconds
            max_wait: Maximum wait time in seconds
            multiplier: Multiplier for exponential backoff
            retryable_exceptions: Tuple of exception types that should trigger retries
        """
        self.max_attempts = max_attempts
        self.initial_wait = initial_wait
        self.max_wait = max_wait
        self.multiplier = multiplier
        self.retryable_exceptions = retryable_exceptions


def async_retry_with_backoff(
    config: RetryConfig,
) -> Callable[[F], F]:
    """
    Decorator for async functions to add retry logic with exponential backoff.

    Args:
        config: Retry configuration specifying behavior

    Returns:
        Decorator function that adds retry logic

    Example:
        @async_retry_with_backoff(RetryConfig(max_attempts=3))
        async def api_call():
            # Your API call logic here
            pass
    """

    def decorator(func: F) -> F:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            retry_strategy = AsyncRetrying(
                stop=stop_after_attempt(config.max_attempts),
                wait=wait_exponential(
                    multiplier=config.multiplier,
                    min=config.initial_wait,
                    max=config.max_wait,
                ),
                retry=retry_if_exception_type(config.retryable_exceptions)
                if config.retryable_exceptions
                else retry_if_exception_type(Exception),
                reraise=True,
            )

            try:
                async for attempt in retry_strategy:
                    with attempt:
                        logger.debug(
                            f"Attempting {func.__name__} (attempt {attempt.retry_state.attempt_number})"
                        )
                        result = await func(*args, **kwargs)
                        if attempt.retry_state.attempt_number > 1:
                            logger.info(
                                f"{func.__name__} succeeded on attempt {attempt.retry_state.attempt_number}"
                            )
                        return result
            except RetryError as e:
                logger.error(
                    f"{func.__name__} failed after {config.max_attempts} attempts: {e.last_attempt.exception()}"
                )
                last_exception = e.last_attempt.exception()
                if last_exception:
                    raise last_exception
                raise RuntimeError("Retry failed with no exception information")

        return wrapper  # type: ignore

    return decorator


async def retry_with_backoff(
    func: Callable[..., Any],
    config: RetryConfig,
    *args: Any,
    **kwargs: Any,
) -> Any:
    """
    Execute a function with retry logic and exponential backoff.

    Args:
        func: The async function to execute
        config: Retry configuration
        *args: Arguments to pass to the function
        **kwargs: Keyword arguments to pass to the function

    Returns:
        The result of the function call

    Raises:
        The last exception if all retries are exhausted
    """
    for attempt in range(config.max_attempts):
        try:
            logger.debug(f"Attempting {func.__name__} (attempt {attempt + 1})")
            result = await func(*args, **kwargs)
            if attempt > 0:
                logger.info(f"{func.__name__} succeeded on attempt {attempt + 1}")
            return result
        except Exception as e:
            if attempt == config.max_attempts - 1:
                logger.error(
                    f"{func.__name__} failed after {config.max_attempts} attempts: {e}"
                )
                raise
            
            if config.retryable_exceptions and not isinstance(e, config.retryable_exceptions):
                logger.error(f"{func.__name__} failed with non-retryable exception: {e}")
                raise

            wait_time = min(
                config.initial_wait * (config.multiplier**attempt), config.max_wait
            )
            logger.warning(
                f"{func.__name__} failed on attempt {attempt + 1}, retrying in {wait_time:.2f}s: {e}"
            )
            await asyncio.sleep(wait_time)

    # This should never be reached due to the raise in the loop
    raise RuntimeError("Unexpected code path in retry logic")
