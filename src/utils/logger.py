# src/utils/logger.py
"""
Logging utilities for the invoice automation application.

This module provides centralized logging configuration with support for
different log levels, file output, and structured formatting.
"""

import logging
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.logging import RichHandler


class LoggerSetup:
    """
    Handles logger configuration and setup for the application.
    
    Provides both file and console logging with appropriate formatting
    and log levels based on configuration.
    """

    def __init__(self) -> None:
        """Initialize the logger setup utility."""
        self.console = Console(stderr=True)

    def setup_logger(
        self,
        name: str,
        level: str = "INFO",
        log_file: Optional[Path] = None,
        debug: bool = False,
    ) -> logging.Logger:
        """
        Configure and return a logger instance.

        Args:
            name: The name of the logger (typically __name__)
            level: Log level as string (DEBUG, INFO, WARNING, ERROR, CRITICAL)
            log_file: Optional path to log file for file output
            debug: Whether to enable debug mode with verbose output

        Returns:
            Configured logger instance

        Raises:
            ValueError: If an invalid log level is provided
        """
        logger = logging.getLogger(name)
        
        # Don't add handlers if they already exist
        if logger.handlers:
            return logger

        # Set log level
        try:
            log_level = getattr(logging, level.upper())
        except AttributeError:
            raise ValueError(f"Invalid log level: {level}")

        logger.setLevel(log_level)

        # Create formatters
        detailed_formatter = logging.Formatter(
            fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

        # Console handler with Rich
        console_handler = RichHandler(
            console=self.console,
            show_time=True,
            show_path=debug,
            rich_tracebacks=debug,
        )
        console_handler.setLevel(log_level)
        logger.addHandler(console_handler)

        # File handler if specified
        if log_file:
            log_file.parent.mkdir(parents=True, exist_ok=True)
            file_handler = logging.FileHandler(log_file)
            file_handler.setLevel(log_level)
            file_handler.setFormatter(detailed_formatter)
            logger.addHandler(file_handler)

        # Prevent propagation to avoid duplicate logs
        logger.propagate = False

        return logger


def get_logger(
    name: str,
    level: str = "INFO",
    log_file: Optional[Path] = None,
    debug: bool = False,
) -> logging.Logger:
    """
    Get a configured logger instance.

    Args:
        name: The name of the logger (typically __name__)
        level: Log level as string (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Optional path to log file for file output
        debug: Whether to enable debug mode with verbose output

    Returns:
        Configured logger instance
    """
    setup = LoggerSetup()
    return setup.setup_logger(name, level, log_file, debug)
