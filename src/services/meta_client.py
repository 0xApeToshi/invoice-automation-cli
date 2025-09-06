# src/services/meta_client.py
"""
Meta Ads API client for invoice retrieval.

This module implements the Meta Ads (Facebook) Graph API client
for retrieving business invoices from Meta Business Manager accounts.
Handles pagination, authentication, and error scenarios specific to Meta's API.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

from rich.progress import Progress, TaskID

from ..models.config import MetaAdsConfig
from ..models.invoice import Invoice
from .base_client import AuthenticationError, BaseInvoiceClient, ClientError

logger = logging.getLogger(__name__)


class MetaAdsClient(BaseInvoiceClient):
    """
    Client for Meta Ads Graph API invoice operations.
    
    Implements invoice retrieval from Meta Business Manager using the
    Graph API business_invoices endpoint with proper error handling
    and pagination support.
    """

    def __init__(self, config: MetaAdsConfig, **kwargs: Any) -> None:
        """
        Initialize Meta Ads client.

        Args:
            config: Meta Ads configuration with credentials
            **kwargs: Additional arguments passed to base client
        """
        super().__init__(**kwargs)
        self.config = config
        self.base_url = f"https://graph.facebook.com/{config.api_version}"

    def _get_base_headers(self) -> Dict[str, str]:
        """
        Get base headers for Meta API requests.

        Returns:
            Dictionary of headers including content type
        """
        return {
            "Content-Type": "application/json",
            "User-Agent": "invoice-automation/1.0",
        }

    async def test_connection(self) -> bool:
        """
        Test connection to Meta Ads API.

        Attempts to retrieve basic business information to verify
        authentication and API accessibility.

        Returns:
            True if connection test passes, False otherwise
        """
        try:
            url = urljoin(self.base_url, f"/{self.config.business_id}")
            params = {
                "access_token": self.config.access_token,
                "fields": "id,name",
            }

            response = await self._make_request(
                method="GET",
                url=url,
                headers=self._get_base_headers(),
                params=params,
            )

            data = response.json()
            business_name = data.get("name", "Unknown")
            logger.info(f"Meta Ads connection test successful for business: {business_name}")
            return True

        except (ClientError, AuthenticationError) as e:
            logger.error(f"Meta Ads connection test failed: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error during Meta Ads connection test: {e}")
            return False

    async def get_invoices(
        self,
        start_date: datetime,
        end_date: datetime,
        progress: Progress,
        task_id: TaskID,
        client_filter: Optional[str] = None,
    ) -> List[Invoice]:
        """
        Retrieve Meta Ads invoices for the specified date range.

        Args:
            start_date: Start of date range for invoice retrieval
            end_date: End of date range for invoice retrieval
            progress: Rich progress bar for user feedback
            task_id: Task ID for progress updates
            client_filter: Optional filter for specific client/account (unused for Meta)

        Returns:
            List of Invoice objects from Meta Ads

        Raises:
            ClientError: If invoice retrieval fails
            AuthenticationError: If authentication is invalid
        """
        self._update_progress(
            progress, task_id, "Fetching Meta Ads invoices...", 0
        )

        invoices: List[Invoice] = []
        url = urljoin(self.base_url, f"/{self.config.business_id}/business_invoices")
        
        params = {
            "access_token": self.config.access_token,
            "start_date": start_date.strftime("%Y-%m-%d"),
            "end_date": end_date.strftime("%Y-%m-%d"),
            "limit": 50,  # Meta's default limit
        }

        try:
            has_more = True
            page_count = 0
            
            while has_more:
                page_count += 1
                self._update_progress(
                    progress, task_id, f"Fetching Meta Ads invoices (page {page_count})..."
                )

                response = await self._make_retryable_request(
                    method="GET",
                    url=url,
                    headers=self._get_base_headers(),
                    params=params,
                )

                data = response.json()
                
                # Handle API errors in response
                if "error" in data:
                    error_info = data["error"]
                    error_code = error_info.get("code", "unknown")
                    error_message = error_info.get("message", "Unknown error")
                    
                    if error_code in [190, 102]:  # Invalid access token
                        raise AuthenticationError(
                            f"Meta Ads authentication failed: {error_message}",
                            self.provider_name,
                        )
                    else:
                        raise ClientError(
                            f"Meta Ads API error {error_code}: {error_message}",
                            self.provider_name,
                        )

                # Process invoice data
                business_invoices = data.get("business_invoices", {})
                invoice_data = business_invoices.get("data", [])
                
                for raw_invoice in invoice_data:
                    try:
                        # Determine client name from business info or use default
                        client_name = await self._get_client_name_for_invoice(raw_invoice)
                        
                        invoice = Invoice.from_meta_response(raw_invoice, client_name)
                        invoices.append(invoice)
                        
                        logger.debug(f"Processed Meta invoice: {invoice.id}")
                        
                    except ValueError as e:
                        logger.warning(f"Skipping invalid Meta invoice data: {e}")
                        continue

                # Check for pagination
                paging = business_invoices.get("paging", {})
                next_url = paging.get("next")
                
                if next_url:
                    # Extract cursor from next URL for pagination
                    cursors = paging.get("cursors", {})
                    after_cursor = cursors.get("after")
                    
                    if after_cursor:
                        params["after"] = after_cursor
                    else:
                        has_more = False
                else:
                    has_more = False

                self._update_progress(
                    progress, task_id, f"Found {len(invoices)} Meta invoices so far..."
                )

            self._update_progress(
                progress, 
                task_id, 
                f"Completed Meta Ads: {len(invoices)} invoices retrieved",
                advance=1
            )

            logger.info(f"Successfully retrieved {len(invoices)} Meta Ads invoices")
            return invoices

        except (ClientError, AuthenticationError):
            raise
        except Exception as e:
            logger.error(f"Unexpected error retrieving Meta Ads invoices: {e}")
            raise ClientError(
                f"Failed to retrieve Meta Ads invoices: {e}",
                self.provider_name,
            ) from e

    async def _get_client_name_for_invoice(self, invoice_data: Dict[str, Any]) -> str:
        """
        Determine client name for an invoice.

        For Meta Ads, invoices are at business level, so we use the business name
        or fall back to a default naming scheme.

        Args:
            invoice_data: Raw invoice data from API

        Returns:
            Client name to use for the invoice
        """
        # Try to get business name from a separate API call (cached)
        # For now, use a simple naming scheme
        business_id = self.config.business_id
        
        # You could enhance this by calling the business info endpoint
        # and caching the business name for better client identification
        return f"Meta Business {business_id}"

    async def get_business_info(self) -> Dict[str, Any]:
        """
        Retrieve business information for better client naming.

        Returns:
            Dictionary with business information

        Raises:
            ClientError: If business info retrieval fails
        """
        try:
            url = urljoin(self.base_url, f"/{self.config.business_id}")
            params = {
                "access_token": self.config.access_token,
                "fields": "id,name,primary_page,verification_status",
            }

            response = await self._make_request(
                method="GET",
                url=url,
                headers=self._get_base_headers(),
                params=params,
            )

            data = response.json()
            return dict(data)

        except Exception as e:
            logger.warning(f"Failed to retrieve Meta business info: {e}")
            return {"id": self.config.business_id, "name": f"Business {self.config.business_id}"}

    async def list_ad_accounts(self) -> List[Dict[str, Any]]:
        """
        List all ad accounts under the business manager.

        This can be useful for mapping invoices to specific client accounts
        in more sophisticated client identification scenarios.

        Returns:
            List of ad account information dictionaries

        Raises:
            ClientError: If ad accounts retrieval fails
        """
        try:
            url = urljoin(self.base_url, f"/{self.config.business_id}/owned_ad_accounts")
            params = {
                "access_token": self.config.access_token,
                "fields": "id,name,account_status,business,currency",
                "limit": 100,
            }

            accounts = []
            has_more = True

            while has_more:
                response = await self._make_request(
                    method="GET",
                    url=url,
                    headers=self._get_base_headers(),
                    params=params,
                )

                data = response.json()
                accounts.extend(data.get("data", []))

                # Handle pagination
                paging = data.get("paging", {})
                next_url = paging.get("next")
                
                if next_url:
                    cursors = paging.get("cursors", {})
                    after_cursor = cursors.get("after")
                    if after_cursor:
                        params["after"] = after_cursor
                    else:
                        has_more = False
                else:
                    has_more = False

            logger.info(f"Retrieved {len(accounts)} Meta ad accounts")
            return accounts

        except Exception as e:
            logger.error(f"Failed to retrieve Meta ad accounts: {e}")
            raise ClientError(
                f"Failed to retrieve ad accounts: {e}",
                self.provider_name,
            ) from e
