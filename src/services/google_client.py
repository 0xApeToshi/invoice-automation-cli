"""
Google Ads API client for invoice retrieval.

This module implements the Google Ads API client for retrieving invoices
from Google Ads accounts with monthly invoicing enabled. Handles OAuth2
token refresh, API authentication, and the specific requirements of the
Google Ads invoice service.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin

import httpx
from rich.progress import Progress, TaskID

from ..models.config import GoogleAdsConfig
from ..models.invoice import Invoice
from ..utils.retry import async_retry_with_backoff
from .base_client import AuthenticationError, BaseInvoiceClient, ClientError

logger = logging.getLogger(__name__)


class GoogleAdsClient(BaseInvoiceClient):
    """
    Client for Google Ads API invoice operations.
    
    Implements invoice retrieval from Google Ads accounts using the
    InvoiceService with proper OAuth2 token management and error handling.
    """

    def __init__(self, config: GoogleAdsConfig, **kwargs: Any) -> None:
        """
        Initialize Google Ads client.

        Args:
            config: Google Ads configuration with OAuth2 credentials
            **kwargs: Additional arguments passed to base client
        """
        super().__init__(**kwargs)
        self.config = config
        self.base_url = "https://googleads.googleapis.com/v16"
        self._access_token: Optional[str] = None

    def _get_base_headers(self) -> Dict[str, str]:
        """
        Get base headers for Google Ads API requests.

        Returns:
            Dictionary of headers including developer token and content type
        """
        headers = {
            "Content-Type": "application/json",
            "developer-token": self.config.developer_token,
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
                # Convert to form data
                params=data,
            )

            token_data = response.json()
            
            access_token = token_data.get("access_token")
            if not access_token or not isinstance(access_token, str):
                raise AuthenticationError(
                    f"Token refresh failed: {token_data.get('error_description', 'Unknown error')}",
                    self.provider_name,
                )

            # Type narrowing: we've confirmed access_token is a str above
            access_token_str: str = access_token
            self._access_token = access_token_str
            logger.debug("Google Ads access token refreshed successfully")
            return access_token_str

        except Exception as e:
            logger.error(f"Failed to refresh Google Ads access token: {e}")
            raise AuthenticationError(
                f"Google Ads token refresh failed: {e}",
                self.provider_name,
            ) from e

    async def test_connection(self) -> bool:
        """
        Test connection to Google Ads API.

        Attempts to retrieve customer information to verify authentication
        and API accessibility.

        Returns:
            True if connection test passes, False otherwise
        """
        try:
            await self._refresh_access_token()
            
            url = urljoin(self.base_url, f"/customers/{self.config.customer_id}")
            
            response = await self._make_request(
                method="GET",
                url=url,
                headers=self._get_base_headers(),
            )

            data = response.json()
            customer_name = data.get("descriptiveName", "Unknown")
            logger.info(f"Google Ads connection test successful for customer: {customer_name}")
            return True

        except (ClientError, AuthenticationError) as e:
            logger.error(f"Google Ads connection test failed: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error during Google Ads connection test: {e}")
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
        Retrieve Google Ads invoices for the specified date range.

        Note: Google Ads invoices are retrieved by year/month, so this method
        will iterate through the months in the date range.

        Args:
            start_date: Start of date range for invoice retrieval
            end_date: End of date range for invoice retrieval
            progress: Rich progress bar for user feedback
            task_id: Task ID for progress updates
            client_filter: Optional filter for specific client/account

        Returns:
            List of Invoice objects from Google Ads

        Raises:
            ClientError: If invoice retrieval fails
            AuthenticationError: If authentication is invalid
        """
        self._update_progress(
            progress, task_id, "Refreshing Google Ads token...", 0
        )

        await self._refresh_access_token()

        self._update_progress(
            progress, task_id, "Fetching Google Ads invoices...", 0
        )

        invoices: List[Invoice] = []
        
        # Generate list of year/month combinations to query
        months_to_query = self._generate_month_range(start_date, end_date)
        
        for year, month in months_to_query:
            month_name = datetime(year, month, 1).strftime("%B")
            self._update_progress(
                progress, task_id, f"Fetching Google Ads invoices for {month_name} {year}..."
            )

            try:
                month_invoices = await self._get_invoices_for_month(year, month, client_filter)
                invoices.extend(month_invoices)
                
                logger.debug(f"Retrieved {len(month_invoices)} invoices for {month_name} {year}")
                
            except Exception as e:
                logger.warning(f"Failed to retrieve invoices for {month_name} {year}: {e}")
                # Continue with other months rather than failing completely
                continue

        # Filter by actual date range since we might get invoices outside the range
        filtered_invoices = [
            inv for inv in invoices
            if start_date.date() <= inv.invoice_date.date() <= end_date.date()
        ]

        self._update_progress(
            progress, 
            task_id, 
            f"Completed Google Ads: {len(filtered_invoices)} invoices retrieved",
            advance=1
        )

        logger.info(f"Successfully retrieved {len(filtered_invoices)} Google Ads invoices")
        return filtered_invoices

    def _generate_month_range(self, start_date: datetime, end_date: datetime) -> List[Tuple[int, int]]:
        """
        Generate list of (year, month) tuples for the date range.

        Args:
            start_date: Start of date range
            end_date: End of date range

        Returns:
            List of (year, month) tuples to query
        """
        months = []
        current = start_date.replace(day=1)  # Start from first day of month
        
        while current <= end_date:
            months.append((current.year, current.month))
            
            # Move to next month
            if current.month == 12:
                current = current.replace(year=current.year + 1, month=1)
            else:
                current = current.replace(month=current.month + 1)
                
        return months

    async def _get_invoices_for_month(
        self, 
        year: int, 
        month: int, 
        client_filter: Optional[str] = None
    ) -> List[Invoice]:
        """
        Retrieve invoices for a specific year and month.

        Args:
            year: Year to retrieve invoices for
            month: Month to retrieve invoices for (1-12)
            client_filter: Optional filter for specific client/account

        Returns:
            List of Invoice objects for the month

        Raises:
            ClientError: If invoice retrieval fails
        """
        try:
            # Google Ads API uses month names in uppercase
            month_names = [
                "JANUARY", "FEBRUARY", "MARCH", "APRIL", "MAY", "JUNE",
                "JULY", "AUGUST", "SEPTEMBER", "OCTOBER", "NOVEMBER", "DECEMBER"
            ]
            month_name = month_names[month - 1]

            url = urljoin(
                self.base_url, 
                f"/customers/{self.config.customer_id}/invoices:listInvoices"
            )

            # Construct billing setup resource name
            billing_setup = f"customers/{self.config.customer_id}/billingSetups/-"

            request_data = {
                "customerId": self.config.customer_id,
                "billingSetup": billing_setup,
                "issueYear": str(year),
                "issueMonth": month_name,
            }

            retry_config = self._create_retry_config()

            @async_retry_with_backoff(retry_config)
            async def make_invoice_request() -> httpx.Response:
                return await self._make_request(
                    method="POST",
                    url=url,
                    headers=self._get_base_headers(),
                    json_data=request_data,
                    raise_for_status=True,
                )

            response = await make_invoice_request()
            data = response.json()
            
            # Handle API errors
            if "error" in data:
                error_info = data["error"]
                error_code = error_info.get("code", "unknown")
                error_message = error_info.get("message", "Unknown error")
                
                if error_code in ["UNAUTHENTICATED", "PERMISSION_DENIED"]:
                    raise AuthenticationError(
                        f"Google Ads authentication failed: {error_message}",
                        self.provider_name,
                    )
                else:
                    raise ClientError(
                        f"Google Ads API error {error_code}: {error_message}",
                        self.provider_name,
                    )

            # Process invoice data
            invoices = []
            invoice_data = data.get("invoices", [])
            
            for raw_invoice in invoice_data:
                try:
                    # Determine client name
                    client_name = await self._get_client_name_for_invoice(raw_invoice, client_filter)
                    
                    invoice = Invoice.from_google_response(raw_invoice, client_name)
                    invoices.append(invoice)
                    
                    logger.debug(f"Processed Google invoice: {invoice.id}")
                    
                except ValueError as e:
                    logger.warning(f"Skipping invalid Google invoice data: {e}")
                    continue

            return invoices

        except (ClientError, AuthenticationError):
            raise
        except Exception as e:
            logger.error(f"Unexpected error retrieving Google Ads invoices for {month}/{year}: {e}")
            raise ClientError(
                f"Failed to retrieve Google Ads invoices for {month}/{year}: {e}",
                self.provider_name,
            ) from e

    async def _get_client_name_for_invoice(
        self, 
        invoice_data: Dict[str, Any], 
        client_filter: Optional[str]
    ) -> str:
        """
        Determine client name for an invoice.

        Args:
            invoice_data: Raw invoice data from API
            client_filter: Optional client filter to use

        Returns:
            Client name to use for the invoice
        """
        if client_filter:
            return client_filter
            
        # Try to get customer information for better naming
        customer_id = self.config.customer_id
        
        # You could enhance this by calling the customer info endpoint
        # and caching customer names for better client identification
        return f"Google Ads {customer_id}"

    async def get_customer_info(self) -> Dict[str, Any]:
        """
        Retrieve customer information for better client naming.

        Returns:
            Dictionary with customer information

        Raises:
            ClientError: If customer info retrieval fails
        """
        try:
            url = urljoin(self.base_url, f"/customers/{self.config.customer_id}")
            
            response = await self._make_request(
                method="GET",
                url=url,
                headers=self._get_base_headers(),
            )

            data = response.json()
            return dict(data)

        except Exception as e:
            logger.warning(f"Failed to retrieve Google customer info: {e}")
            return {
                "resourceName": f"customers/{self.config.customer_id}",
                "descriptiveName": f"Customer {self.config.customer_id}",
            }

    async def list_billing_setups(self) -> List[Dict[str, Any]]:
        """
        List billing setups for the customer account.

        This can be useful for understanding how invoicing is configured
        and for more sophisticated invoice retrieval scenarios.

        Returns:
            List of billing setup information dictionaries

        Raises:
            ClientError: If billing setups retrieval fails
        """
        try:
            # Use Google Ads API query language (GAQL) to get billing setups
            query = f"""
                SELECT 
                    billing_setup.id,
                    billing_setup.status,
                    billing_setup.payments_account,
                    billing_setup.payments_account_info.payments_account_id,
                    billing_setup.payments_account_info.payments_account_name
                FROM billing_setup 
                WHERE billing_setup.status = 'APPROVED'
            """

            url = urljoin(self.base_url, f"/customers/{self.config.customer_id}/googleAds:search")
            
            request_data = {
                "query": query,
                "pageSize": 100,
            }

            response = await self._make_request(
                method="POST",
                url=url,
                headers=self._get_base_headers(),
                json_data=request_data,
            )

            data = response.json()
            billing_setups = data.get("results", [])
            
            logger.info(f"Retrieved {len(billing_setups)} Google Ads billing setups")
            return list(billing_setups)

        except Exception as e:
            logger.error(f"Failed to retrieve Google Ads billing setups: {e}")
            raise ClientError(
                f"Failed to retrieve billing setups: {e}",
                self.provider_name,
            ) from e
