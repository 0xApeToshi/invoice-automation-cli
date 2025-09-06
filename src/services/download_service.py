# src/services/download_service.py
"""
Invoice download service for handling PDF downloads and file management.

This module provides a service for downloading invoice PDFs from provider URLs,
organizing them according to folder structures, and handling download errors
with appropriate retry logic.
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
from rich.progress import Progress, TaskID

from ..models.invoice import Invoice
from ..models.config import RetryConfig
from ..utils.file_utils import FileManager
from ..utils.retry import RetryConfig as UtilsRetryConfig, async_retry_with_backoff

logger = logging.getLogger(__name__)


class DownloadError(Exception):
    """Raised when invoice download fails."""
    
    def __init__(self, message: str, invoice_id: str, url: Optional[str] = None) -> None:
        """
        Initialize download error.

        Args:
            message: Error message
            invoice_id: ID of the invoice that failed to download
            url: Optional download URL that failed
        """
        super().__init__(message)
        self.invoice_id = invoice_id
        self.url = url


class DownloadService:
    """
    Service for downloading and managing invoice PDF files.
    
    Handles downloading invoice PDFs from provider URLs, organizing them
    according to configurable folder structures, and managing download
    retry logic and error handling.
    """

    def __init__(
        self,
        file_manager: FileManager,
        retry_config: RetryConfig,
        timeout_seconds: int = 30,
    ) -> None:
        """
        Initialize download service.

        Args:
            file_manager: File manager for organizing downloads
            retry_config: Configuration for retry behavior
            timeout_seconds: Request timeout in seconds
        """
        self.file_manager = file_manager
        self.retry_config = retry_config
        self.timeout_seconds = timeout_seconds
        self._client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self) -> "DownloadService":
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
                follow_redirects=True,
            )
        return self._client

    async def close(self) -> None:
        """Close the HTTP client and cleanup resources."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def _create_retry_config(self) -> UtilsRetryConfig:
        """
        Create retry configuration for download operations.

        Returns:
            UtilsRetryConfig instance for use with retry decorators
        """
        return UtilsRetryConfig(
            max_attempts=self.retry_config.max_attempts,
            initial_wait=self.retry_config.initial_delay,
            max_wait=self.retry_config.max_delay,
            multiplier=self.retry_config.multiplier,
            retryable_exceptions=(httpx.RequestError, httpx.TimeoutException),
        )

    async def download_invoices(
        self,
        invoices: List[Invoice],
        base_dir: Path,
        progress: Progress,
        task_id: TaskID,
        skip_existing: bool = True,
    ) -> tuple[List[Invoice], List[DownloadError]]:
        """
        Download PDFs for a list of invoices.

        Args:
            invoices: List of invoices to download
            base_dir: Base directory for downloads
            progress: Rich progress bar for user feedback
            task_id: Task ID for progress updates
            skip_existing: Whether to skip files that already exist

        Returns:
            Tuple of (successfully_downloaded, download_errors)
        """
        if not invoices:
            logger.info("No invoices to download")
            return [], []

        logger.info(f"Starting download of {len(invoices)} invoices")
        
        successful_downloads: List[Invoice] = []
        download_errors: List[DownloadError] = []

        await self._ensure_client()

        for i, invoice in enumerate(invoices, 1):
            try:
                progress.update(
                    task_id,
                    description=f"Downloading {invoice.filename} ({i}/{len(invoices)})",
                )

                # Get file path using folder structure
                file_path = self.file_manager.get_invoice_path(
                    base_dir, invoice.client_name, invoice.provider.value, invoice.filename
                )

                # Skip if file exists and skip_existing is True
                if skip_existing and self.file_manager.file_exists(file_path):
                    logger.debug(f"Skipping existing file: {file_path}")
                    successful_downloads.append(invoice)
                    progress.update(task_id, advance=1)
                    continue

                # Download the invoice
                if invoice.download_url:
                    await self._download_single_invoice(invoice, file_path)
                else:
                    # Create placeholder file if no download URL
                    await self._create_placeholder_file(invoice, file_path)

                successful_downloads.append(invoice)
                logger.debug(f"Successfully downloaded: {invoice.filename}")

            except Exception as e:
                error = DownloadError(
                    f"Failed to download {invoice.filename}: {e}",
                    invoice.id,
                    invoice.download_url,
                )
                download_errors.append(error)
                logger.error(f"Download failed for {invoice.filename}: {e}")

            progress.update(task_id, advance=1)

        logger.info(
            f"Download completed: {len(successful_downloads)} successful, "
            f"{len(download_errors)} failed"
        )

        return successful_downloads, download_errors

    async def _download_single_invoice(self, invoice: Invoice, file_path: Path) -> None:
        """
        Download a single invoice PDF with retry logic.

        Args:
            invoice: Invoice to download
            file_path: Where to save the downloaded file

        Raises:
            DownloadError: If download fails after all retries
        """
        if not invoice.download_url:
            raise DownloadError(
                "No download URL available",
                invoice.id,
            )

        retry_config = self._create_retry_config()

        @async_retry_with_backoff(retry_config)
        async def download_with_retry() -> bytes:
            client = await self._ensure_client()
            
            # Prepare headers (some providers require authentication)
            headers = {
                "User-Agent": "invoice-automation/1.0",
            }

            # For Meta Ads, the download URL might require the access token
            # For Google Ads, the download URL should be pre-authenticated
            
            if not invoice.download_url:
                raise DownloadError(
                    "Download URL is None",
                    invoice.id,
                )
            
            response = await client.get(invoice.download_url, headers=headers)
            response.raise_for_status()

            # Verify content type is PDF
            content_type = response.headers.get("content-type", "").lower()
            if "pdf" not in content_type and "application/octet-stream" not in content_type:
                logger.warning(
                    f"Unexpected content type for {invoice.filename}: {content_type}"
                )

            return response.content

        try:
            pdf_content = await download_with_retry()
            
            # Verify minimum file size (PDFs should be at least a few KB)
            if len(pdf_content) < 1024:
                raise DownloadError(
                    f"Downloaded file too small ({len(pdf_content)} bytes), likely not a valid PDF",
                    invoice.id,
                    invoice.download_url,
                )

            await self.file_manager.write_file(file_path, pdf_content)
            logger.debug(f"Downloaded {len(pdf_content)} bytes to {file_path}")

        except Exception as e:
            raise DownloadError(
                f"Download failed: {e}",
                invoice.id,
                invoice.download_url,
            ) from e

    async def _create_placeholder_file(self, invoice: Invoice, file_path: Path) -> None:
        """
        Create a placeholder text file when no download URL is available.

        Args:
            invoice: Invoice to create placeholder for
            file_path: Where to save the placeholder file

        Raises:
            DownloadError: If placeholder creation fails
        """
        try:
            # Change extension to .txt for placeholder
            placeholder_path = file_path.with_suffix(".txt")
            
            placeholder_content = f"""Invoice Information - No PDF Available

Provider: {invoice.provider.value.title()}
Invoice ID: {invoice.id}
Client: {invoice.client_name}
Date: {invoice.invoice_date.strftime('%Y-%m-%d')}
Amount: {invoice.currency} {invoice.amount:,.2f}
Status: {invoice.payment_status.value.title()}

Note: This is a placeholder file created because no download URL was available.
Original filename would have been: {invoice.filename}
"""

            await self.file_manager.write_text_file(placeholder_path, placeholder_content)
            logger.debug(f"Created placeholder file: {placeholder_path}")

        except Exception as e:
            raise DownloadError(
                f"Failed to create placeholder file: {e}",
                invoice.id,
            ) from e

    async def verify_downloads(
        self,
        invoices: List[Invoice],
        base_dir: Path,
        progress: Progress,
        task_id: TaskID,
    ) -> tuple[List[Invoice], List[Invoice]]:
        """
        Verify that downloaded files exist and are valid.

        Args:
            invoices: List of invoices to verify
            base_dir: Base directory where files should be located
            progress: Rich progress bar for user feedback
            task_id: Task ID for progress updates

        Returns:
            Tuple of (verified_invoices, missing_invoices)
        """
        logger.info(f"Verifying {len(invoices)} downloaded files")
        
        verified: List[Invoice] = []
        missing: List[Invoice] = []

        for i, invoice in enumerate(invoices, 1):
            progress.update(
                task_id,
                description=f"Verifying {invoice.filename} ({i}/{len(invoices)})",
            )

            file_path = self.file_manager.get_invoice_path(
                base_dir, invoice.client_name, invoice.provider.value, invoice.filename
            )

            # Check for PDF file or placeholder
            pdf_exists = self.file_manager.file_exists(file_path)
            placeholder_path = file_path.with_suffix(".txt")
            placeholder_exists = self.file_manager.file_exists(placeholder_path)

            if pdf_exists or placeholder_exists:
                # Verify file size is reasonable
                actual_path = file_path if pdf_exists else placeholder_path
                file_size = self.file_manager.get_file_size(actual_path)
                
                if file_size and file_size > 0:
                    verified.append(invoice)
                    logger.debug(f"Verified file: {actual_path} ({file_size} bytes)")
                else:
                    missing.append(invoice)
                    logger.warning(f"File exists but has zero size: {actual_path}")
            else:
                missing.append(invoice)
                logger.warning(f"Missing file: {file_path}")

            progress.update(task_id, advance=1)

        logger.info(
            f"Verification completed: {len(verified)} verified, {len(missing)} missing"
        )

        return verified, missing

    def get_download_summary(
        self,
        successful: List[Invoice],
        errors: List[DownloadError],
    ) -> Dict[str, Any]:
        """
        Create a summary of download results.

        Args:
            successful: List of successfully downloaded invoices
            errors: List of download errors

        Returns:
            Dictionary with download summary information
        """
        total_attempted = len(successful) + len(errors)
        success_rate = (len(successful) / total_attempted * 100) if total_attempted > 0 else 0

        # Calculate total size of successful downloads
        by_provider: Dict[str, int] = {}
        
        for invoice in successful:
            provider = invoice.provider.value
            by_provider[provider] = by_provider.get(provider, 0) + 1

        return {
            "total_attempted": total_attempted,
            "successful": len(successful),
            "failed": len(errors),
            "success_rate": round(success_rate, 1),
            "by_provider": by_provider,
            "error_summary": [
                {
                    "invoice_id": error.invoice_id,
                    "error": str(error),
                    "url": error.url,
                }
                for error in errors
            ],
        }
