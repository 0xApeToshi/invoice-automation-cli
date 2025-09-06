"""
Google Drive client for uploading and managing invoice files.

This module implements the Google Drive API client for uploading invoices
with configurable folder structures and file organization.
"""

import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin

import httpx
from rich.progress import Progress, TaskID

from ..models.config import GoogleDriveConfig
from ..utils.retry import async_retry_with_backoff
from .base_client import AuthenticationError, BaseInvoiceClient, ClientError

logger = logging.getLogger(__name__)


class DriveUploadError(Exception):
    """Raised when file upload to Google Drive fails."""
    
    def __init__(self, message: str, file_path: Path, drive_path: Optional[str] = None) -> None:
        """
        Initialize drive upload error.

        Args:
            message: Error message
            file_path: Local file path that failed to upload
            drive_path: Optional Google Drive path where upload was attempted
        """
        super().__init__(message)
        self.file_path = file_path
        self.drive_path = drive_path


class GoogleDriveClient(BaseInvoiceClient):
    """
    Client for Google Drive API operations.
    
    Implements file upload, folder management, and organization
    for invoice files using the Google Drive API v3.
    """

    def __init__(self, config: GoogleDriveConfig, **kwargs: Any) -> None:
        """
        Initialize Google Drive client.

        Args:
            config: Google Drive configuration with credentials
            **kwargs: Additional arguments passed to base client
        """
        super().__init__(**kwargs)
        self.config = config
        self.base_url = "https://www.googleapis.com/drive/v3"
        self.upload_url = "https://www.googleapis.com/upload/drive/v3"
        self._access_token: Optional[str] = None
        self._folder_cache: Dict[str, str] = {}  # Cache folder IDs

    def _get_base_headers(self) -> Dict[str, str]:
        """
        Get base headers for Google Drive API requests.

        Returns:
            Dictionary of headers including authorization if available
        """
        headers = {
            "Content-Type": "application/json",
        }
        
        if self._access_token:
            headers["Authorization"] = f"Bearer {self._access_token}"
            
        return headers

    async def _refresh_access_token(self) -> str:
        """
        Refresh OAuth2 access token using refresh token.

        Returns:
            New access token

        Raises:
            AuthenticationError: If token refresh fails
        """
        try:
            token_url = "https://oauth2.googleapis.com/token"
            
            data = {
                "client_id": self.config.client_id,
                "client_secret": self.config.client_secret,
                "refresh_token": self.config.refresh_token,
                "grant_type": "refresh_token",
            }

            # Use form data for OAuth2 token endpoint
            response = await self._make_request(
                method="POST",
                url=token_url,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                params=data,
            )

            token_data = response.json()
            
            access_token = token_data.get("access_token")
            if not access_token or not isinstance(access_token, str):
                raise AuthenticationError(
                    f"Token refresh failed: {token_data.get('error_description', 'Unknown error')}",
                    self.provider_name,
                )

            # Type narrowing for mypy
            assert isinstance(access_token, str)

            self._access_token = access_token
            logger.debug("Google Drive access token refreshed successfully")
            return access_token

        except Exception as e:
            logger.error(f"Failed to refresh Google Drive access token: {e}")
            raise AuthenticationError(
                f"Google Drive token refresh failed: {e}",
                self.provider_name,
            ) from e

    async def test_connection(self) -> bool:
        """
        Test connection to Google Drive API.

        Attempts to retrieve basic drive information to verify authentication
        and API accessibility.

        Returns:
            True if connection test passes, False otherwise
        """
        try:
            await self._refresh_access_token()
            
            url = urljoin(self.base_url, "/about")
            params = {"fields": "user,storageQuota"}
            
            response = await self._make_request(
                method="GET",
                url=url,
                headers=self._get_base_headers(),
                params=params,
            )

            data = response.json()
            user_email = data.get("user", {}).get("emailAddress", "Unknown")
            logger.info(f"Google Drive connection test successful for user: {user_email}")
            return True

        except (ClientError, AuthenticationError) as e:
            logger.error(f"Google Drive connection test failed: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error during Google Drive connection test: {e}")
            return False

    async def upload_files(
        self,
        file_paths: List[Path],
        folder_structure: str,
        force_overwrite: bool,
        progress: Progress,
        task_id: TaskID,
    ) -> Tuple[List[Path], List[DriveUploadError]]:
        """
        Upload multiple files to Google Drive.

        Args:
            file_paths: List of local file paths to upload
            folder_structure: Folder organization method
            force_overwrite: Whether to overwrite existing files
            progress: Rich progress bar for user feedback
            task_id: Task ID for progress updates

        Returns:
            Tuple of (successfully_uploaded_files, upload_errors)
        """
        if not file_paths:
            logger.info("No files to upload")
            return [], []

        logger.info(f"Starting upload of {len(file_paths)} files to Google Drive")
        
        successful_uploads: List[Path] = []
        upload_errors: List[DriveUploadError] = []

        await self._refresh_access_token()

        for i, file_path in enumerate(file_paths, 1):
            try:
                progress.update(
                    task_id,
                    description=f"Uploading {file_path.name} ({i}/{len(file_paths)})",
                )

                # Determine target folder based on structure
                folder_id = await self._get_or_create_folder(file_path, folder_structure)
                
                # Check if file already exists (unless force overwrite)
                if not force_overwrite:
                    existing_file_id = await self._find_existing_file(file_path.name, folder_id)
                    if existing_file_id:
                        logger.debug(f"Skipping existing file: {file_path.name}")
                        successful_uploads.append(file_path)
                        progress.update(task_id, advance=1)
                        continue

                # Upload the file
                await self._upload_single_file(file_path, folder_id, force_overwrite)
                successful_uploads.append(file_path)
                logger.debug(f"Successfully uploaded: {file_path.name}")

            except Exception as e:
                error = DriveUploadError(
                    f"Failed to upload {file_path.name}: {e}",
                    file_path,
                )
                upload_errors.append(error)
                logger.error(f"Upload failed for {file_path.name}: {e}")

            progress.update(task_id, advance=1)

        logger.info(
            f"Upload completed: {len(successful_uploads)} successful, "
            f"{len(upload_errors)} failed"
        )

        return successful_uploads, upload_errors

    async def _get_or_create_folder(self, file_path: Path, folder_structure: str) -> str:
        """
        Get or create the appropriate folder for a file based on structure.

        Args:
            file_path: Local file path to determine folder for
            folder_structure: Folder organization method

        Returns:
            Google Drive folder ID

        Raises:
            ClientError: If folder creation fails
        """
        # Start with root or configured base folder
        base_folder_id = self.config.folder_id or "root"
        
        # Determine folder path based on structure
        folder_path = self._determine_folder_path(file_path, folder_structure)
        
        if not folder_path:
            return base_folder_id
        
        # Navigate/create folder hierarchy
        current_folder_id = base_folder_id
        
        for folder_name in folder_path:
            # Check cache first
            cache_key = f"{current_folder_id}/{folder_name}"
            if cache_key in self._folder_cache:
                current_folder_id = self._folder_cache[cache_key]
                continue
            
            # Look for existing folder
            existing_folder_id = await self._find_existing_folder(folder_name, current_folder_id)
            
            if existing_folder_id:
                current_folder_id = existing_folder_id
            else:
                # Create new folder
                current_folder_id = await self._create_folder(folder_name, current_folder_id)
            
            # Cache the result
            self._folder_cache[cache_key] = current_folder_id
        
        return current_folder_id

    def _determine_folder_path(self, file_path: Path, folder_structure: str) -> List[str]:
        """
        Determine the folder path for a file based on the structure setting.

        Args:
            file_path: Local file path
            folder_structure: Folder organization method

        Returns:
            List of folder names representing the path
        """
        if folder_structure == "flat":
            return []
        
        # Extract information from file path
        # Assuming structure: base/client/provider/file.pdf
        path_parts = file_path.parts
        
        if len(path_parts) >= 3:
            client = path_parts[-3]
            provider = path_parts[-2]
        else:
            client = "Unknown Client"
            provider = "Unknown Provider"
        
        # Get current date for date-based structures
        current_date = datetime.now()
        year = current_date.strftime("%Y")
        month = current_date.strftime("%m")
        
        if folder_structure == "date":
            return [year, month, provider.title()]
        elif folder_structure == "client":
            return [client, provider.title()]
        elif folder_structure == "provider":
            return [provider.title(), year, month]
        else:
            # Default to client-based structure
            return [client, provider.title()]

    async def _find_existing_folder(self, folder_name: str, parent_id: str) -> Optional[str]:
        """
        Find an existing folder by name within a parent folder.

        Args:
            folder_name: Name of the folder to find
            parent_id: Parent folder ID

        Returns:
            Folder ID if found, None otherwise
        """
        try:
            url = urljoin(self.base_url, "/files")
            params = {
                "q": f"name='{folder_name}' and '{parent_id}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false",
                "fields": "files(id,name)",
            }
            
            response = await self._make_request(
                method="GET",
                url=url,
                headers=self._get_base_headers(),
                params=params,
            )

            data = response.json()
            files = data.get("files", [])
            
            if files:
                file_id = files[0].get("id")
                if isinstance(file_id, str):
                    return file_id
            
            return None

        except Exception as e:
            logger.warning(f"Failed to search for folder {folder_name}: {e}")
            return None

    async def _create_folder(self, folder_name: str, parent_id: str) -> str:
        """
        Create a new folder in Google Drive.

        Args:
            folder_name: Name of the folder to create
            parent_id: Parent folder ID

        Returns:
            Created folder ID

        Raises:
            ClientError: If folder creation fails
        """
        try:
            url = urljoin(self.base_url, "/files")
            
            metadata = {
                "name": folder_name,
                "mimeType": "application/vnd.google-apps.folder",
                "parents": [parent_id],
            }

            response = await self._make_retryable_request(
                method="POST",
                url=url,
                headers=self._get_base_headers(),
                json_data=metadata,
            )

            data = response.json()
            folder_id = data.get("id")
            
            if not folder_id or not isinstance(folder_id, str):
                raise ClientError(
                    f"Failed to create folder {folder_name}: No ID returned",
                    self.provider_name,
                )

            # Type narrowing for mypy
            assert isinstance(folder_id, str)

            logger.debug(f"Created folder: {folder_name} (ID: {folder_id})")
            return folder_id

        except Exception as e:
            logger.error(f"Failed to create folder {folder_name}: {e}")
            raise ClientError(
                f"Failed to create folder {folder_name}: {e}",
                self.provider_name,
            ) from e

    async def _find_existing_file(self, filename: str, parent_id: str) -> Optional[str]:
        """
        Find an existing file by name within a folder.

        Args:
            filename: Name of the file to find
            parent_id: Parent folder ID

        Returns:
            File ID if found, None otherwise
        """
        try:
            url = urljoin(self.base_url, "/files")
            params = {
                "q": f"name='{filename}' and '{parent_id}' in parents and trashed=false",
                "fields": "files(id,name)",
            }
            
            response = await self._make_request(
                method="GET",
                url=url,
                headers=self._get_base_headers(),
                params=params,
            )

            data = response.json()
            files = data.get("files", [])
            
            if files:
                file_id = files[0].get("id")
                if isinstance(file_id, str):
                    return file_id
            
            return None

        except Exception as e:
            logger.warning(f"Failed to search for file {filename}: {e}")
            return None

    async def _upload_single_file(
        self, 
        file_path: Path, 
        folder_id: str, 
        force_overwrite: bool
    ) -> str:
        """
        Upload a single file to Google Drive.

        Args:
            file_path: Local file path to upload
            folder_id: Target folder ID
            force_overwrite: Whether to overwrite existing files

        Returns:
            Uploaded file ID

        Raises:
            DriveUploadError: If upload fails
        """
        try:
            # Check if file already exists and handle accordingly
            existing_file_id = None
            if force_overwrite:
                existing_file_id = await self._find_existing_file(file_path.name, folder_id)

            # Read file content
            async with asyncio.Lock():  # Limit concurrent file reads
                with open(file_path, "rb") as f:
                    file_content = f.read()

            # Prepare metadata
            metadata = {
                "name": file_path.name,
                "parents": [folder_id],
            }

            if existing_file_id:
                # Update existing file
                url = urljoin(self.upload_url, f"/files/{existing_file_id}")
                method = "PATCH"
            else:
                # Create new file
                url = urljoin(self.upload_url, "/files")
                method = "POST"

            # Use multipart upload for files
            headers = self._get_base_headers()
            headers["Content-Type"] = "multipart/related; boundary=upload_boundary"

            # Create multipart body
            boundary = "upload_boundary"
            body_parts = [
                f"--{boundary}",
                "Content-Type: application/json; charset=UTF-8",
                "",
                f'{{"name": "{file_path.name}", "parents": ["{folder_id}"]}}',
                "",
                f"--{boundary}",
                f"Content-Type: {self._get_mime_type(file_path)}",
                "",
            ]
            
            body_prefix = "\r\n".join(body_parts).encode() + b"\r\n"
            body_suffix = f"\r\n--{boundary}--\r\n".encode()
            body = body_prefix + file_content + body_suffix

            # Perform upload with retry
            retry_config = self._create_retry_config()

            @async_retry_with_backoff(retry_config)
            async def upload_with_retry() -> httpx.Response:
                client = await self._ensure_client()
                response = await client.request(
                    method=method,
                    url=url,
                    headers=headers,
                    content=body,
                )
                response.raise_for_status()
                return response

            response = await upload_with_retry()
            data = response.json()
            
            file_id = data.get("id")
            if not file_id or not isinstance(file_id, str):
                raise DriveUploadError(
                    f"Upload failed: No file ID returned",
                    file_path,
                )

            # Type narrowing for mypy
            assert isinstance(file_id, str)

            logger.debug(f"Uploaded {file_path.name} to Google Drive (ID: {file_id})")
            return file_id

        except Exception as e:
            raise DriveUploadError(
                f"Failed to upload {file_path.name}: {e}",
                file_path,
            ) from e

    def _get_mime_type(self, file_path: Path) -> str:
        """
        Determine MIME type based on file extension.

        Args:
            file_path: File path to determine type for

        Returns:
            MIME type string
        """
        extension = file_path.suffix.lower()
        
        mime_types = {
            ".pdf": "application/pdf",
            ".txt": "text/plain",
            ".json": "application/json",
            ".csv": "text/csv",
        }
        
        return mime_types.get(extension, "application/octet-stream")

    # Required abstract methods from base class
    async def get_invoices(self, *args: Any, **kwargs: Any) -> List[Any]:
        """Not implemented - Google Drive client is for upload only."""
        raise NotImplementedError("Google Drive client is for upload operations only")
