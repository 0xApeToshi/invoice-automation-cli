# src/utils/file_utils.py
"""
File system utilities for invoice management.

This module provides utilities for creating directory structures,
managing file downloads, and organizing invoice files according to
configurable folder structures.
"""

import logging
from pathlib import Path
from typing import Optional, Protocol

import aiofiles

logger = logging.getLogger(__name__)


class FolderStructure(Protocol):
    """Protocol defining interface for folder structure strategies."""

    def get_file_path(
        self, base_dir: Path, client_name: str, provider: str, filename: str
    ) -> Path:
        """
        Generate file path based on folder structure strategy.

        Args:
            base_dir: Base output directory
            client_name: Name of the client
            provider: Provider name (meta, google)
            filename: Original filename

        Returns:
            Complete file path for the invoice
        """
        ...


class ClientProviderStructure:
    """Folder structure: Client -> Provider -> Files."""

    def get_file_path(
        self, base_dir: Path, client_name: str, provider: str, filename: str
    ) -> Path:
        """
        Generate file path using Client/Provider structure.

        Args:
            base_dir: Base output directory
            client_name: Name of the client
            provider: Provider name (meta, google)
            filename: Original filename

        Returns:
            Path in format: base_dir/client_name/provider/filename
        """
        return base_dir / client_name / provider / filename


class ProviderClientStructure:
    """Folder structure: Provider -> Client -> Files."""

    def get_file_path(
        self, base_dir: Path, client_name: str, provider: str, filename: str
    ) -> Path:
        """
        Generate file path using Provider/Client structure.

        Args:
            base_dir: Base output directory
            client_name: Name of the client
            provider: Provider name (meta, google)
            filename: Original filename

        Returns:
            Path in format: base_dir/provider/client_name/filename
        """
        return base_dir / provider / client_name / filename


class DateProviderStructure:
    """Folder structure: Year/Month -> Provider -> Files."""

    def get_file_path(
        self, base_dir: Path, client_name: str, provider: str, filename: str
    ) -> Path:
        """
        Generate file path using Date/Provider structure.

        Args:
            base_dir: Base output directory
            client_name: Name of the client (included in filename)
            provider: Provider name (meta, google)
            filename: Original filename

        Returns:
            Path in format: base_dir/YYYY/MM/provider/filename
        """
        # Extract date from filename or use current date
        # For now, assume filename contains date info
        import datetime
        
        current_date = datetime.datetime.now()
        year = current_date.strftime("%Y")
        month = current_date.strftime("%m")
        
        return base_dir / year / month / provider / filename


class FileManager:
    """
    Manages file operations for invoice downloads and organization.
    
    Handles creating directory structures, checking for existing files,
    and organizing downloads according to configurable folder structures.
    """

    def __init__(self, folder_structure: FolderStructure) -> None:
        """
        Initialize file manager with folder structure strategy.

        Args:
            folder_structure: Strategy for organizing files
        """
        self.folder_structure = folder_structure

    def get_invoice_path(
        self, base_dir: Path, client_name: str, provider: str, filename: str
    ) -> Path:
        """
        Get the full path for an invoice file.

        Args:
            base_dir: Base output directory
            client_name: Name of the client
            provider: Provider name (meta, google)
            filename: Original filename

        Returns:
            Complete file path for the invoice
        """
        return self.folder_structure.get_file_path(base_dir, client_name, provider, filename)

    async def ensure_directory_exists(self, file_path: Path) -> None:
        """
        Ensure the directory for a file path exists.

        Args:
            file_path: Full path to the file

        Raises:
            OSError: If directory creation fails
        """
        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)
            logger.debug(f"Ensured directory exists: {file_path.parent}")
        except OSError as e:
            logger.error(f"Failed to create directory {file_path.parent}: {e}")
            raise

    def file_exists(self, file_path: Path) -> bool:
        """
        Check if a file already exists.

        Args:
            file_path: Path to check

        Returns:
            True if file exists, False otherwise
        """
        exists = file_path.exists()
        if exists:
            logger.debug(f"File already exists: {file_path}")
        return exists

    async def write_file(self, file_path: Path, content: bytes) -> None:
        """
        Write content to a file asynchronously.

        Args:
            file_path: Path where to write the file
            content: Binary content to write

        Raises:
            OSError: If file writing fails
        """
        try:
            await self.ensure_directory_exists(file_path)
            async with aiofiles.open(file_path, "wb") as f:
                await f.write(content)
            logger.info(f"Successfully wrote file: {file_path}")
        except OSError as e:
            logger.error(f"Failed to write file {file_path}: {e}")
            raise

    async def write_text_file(self, file_path: Path, content: str) -> None:
        """
        Write text content to a file asynchronously.

        Args:
            file_path: Path where to write the file
            content: Text content to write

        Raises:
            OSError: If file writing fails
        """
        try:
            await self.ensure_directory_exists(file_path)
            async with aiofiles.open(file_path, "w", encoding="utf-8") as f:
                await f.write(content)
            logger.info(f"Successfully wrote text file: {file_path}")
        except OSError as e:
            logger.error(f"Failed to write text file {file_path}: {e}")
            raise

    def get_file_size(self, file_path: Path) -> Optional[int]:
        """
        Get the size of a file in bytes.

        Args:
            file_path: Path to the file

        Returns:
            File size in bytes, or None if file doesn't exist
        """
        try:
            if file_path.exists():
                return file_path.stat().st_size
            return None
        except OSError as e:
            logger.error(f"Failed to get file size for {file_path}: {e}")
            return None

    def cleanup_empty_directories(self, base_dir: Path) -> None:
        """
        Remove empty directories from the base directory tree.

        Args:
            base_dir: Base directory to start cleanup from
        """
        try:
            for directory in base_dir.rglob("*"):
                if directory.is_dir() and not any(directory.iterdir()):
                    directory.rmdir()
                    logger.debug(f"Removed empty directory: {directory}")
        except OSError as e:
            logger.warning(f"Failed to cleanup empty directories: {e}")
