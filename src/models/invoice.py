# src/models/invoice.py
"""
Invoice data models for the automation application.

This module defines Pydantic models for representing invoice data
from different providers (Meta Ads, Google Ads) with validation
and standardization across platforms.
"""

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field, field_validator


class InvoiceProvider(str, Enum):
    """Enumeration of supported invoice providers."""
    
    META = "meta"
    GOOGLE = "google"


class PaymentStatus(str, Enum):
    """Enumeration of possible payment statuses."""
    
    PAID = "paid"
    UNPAID = "unpaid"
    OVERDUE = "overdue"
    PENDING = "pending"
    CREDIT = "credit"


class Invoice(BaseModel):
    """
    Standardized invoice representation across providers.
    
    This model normalizes invoice data from different APIs into a
    consistent format for processing and storage.
    """

    id: str = Field(..., description="Unique invoice identifier from provider")
    provider: InvoiceProvider = Field(..., description="Invoice provider (meta/google)")
    client_name: str = Field(..., description="Client or account name")
    invoice_number: Optional[str] = Field(default=None, description="Provider-assigned invoice number")
    invoice_date: datetime = Field(..., description="Date the invoice was issued")
    due_date: Optional[datetime] = Field(default=None, description="Payment due date")
    billing_period_start: Optional[datetime] = Field(default=None, description="Billing period start date")
    billing_period_end: Optional[datetime] = Field(default=None, description="Billing period end date")
    amount: Decimal = Field(..., ge=0, description="Invoice amount")
    currency: str = Field(..., description="Currency code (ISO 4217)")
    payment_status: PaymentStatus = Field(default=PaymentStatus.UNPAID, description="Payment status")
    download_url: Optional[str] = Field(default=None, description="URL to download PDF")
    filename: str = Field(..., description="Generated filename for local storage")
    raw_data: Optional[Dict[str, Any]] = Field(default=None, description="Original API response data")

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, v: str) -> str:
        """
        Validate currency code format.

        Args:
            v: Currency code to validate

        Returns:
            Uppercase currency code

        Raises:
            ValueError: If currency code is invalid
        """
        if not v or len(v) != 3 or not v.isalpha():
            raise ValueError("Currency must be a 3-letter ISO 4217 code")
        return v.upper()

    @field_validator("filename")
    @classmethod
    def validate_filename(cls, v: str) -> str:
        """
        Validate filename format and safety.

        Args:
            v: Filename to validate

        Returns:
            Sanitized filename

        Raises:
            ValueError: If filename is invalid
        """
        if not v:
            raise ValueError("Filename cannot be empty")
        
        # Remove potentially dangerous characters
        dangerous_chars = ["<", ">", ":", '"', "|", "?", "*", "/", "\\"]
        for char in dangerous_chars:
            if char in v:
                raise ValueError(f"Filename contains invalid character: {char}")
        
        return v

    def to_summary(self) -> Dict[str, str]:
        """
        Create a summary dictionary for display purposes.

        Returns:
            Dictionary with key invoice information formatted for display
        """
        return {
            "Provider": self.provider.value.title(),
            "Client": self.client_name,
            "Date": self.invoice_date.strftime("%Y-%m-%d"),
            "Amount": f"{self.currency} {self.amount:,.2f}",
            "Status": self.payment_status.value.title(),
            "Filename": self.filename,
        }

    def get_display_name(self) -> str:
        """
        Get a human-readable display name for the invoice.

        Returns:
            Formatted display name
        """
        return f"{self.provider.value.title()} - {self.client_name} - {self.invoice_date.strftime('%Y-%m-%d')}"

    @classmethod
    def from_meta_response(
        cls,
        data: Dict[str, Any],
        client_name: str = "Meta Ads Account",
    ) -> "Invoice":
        """
        Create an Invoice from Meta Ads API response.

        Args:
            data: Raw Meta Ads API response data
            client_name: Name to use for the client

        Returns:
            Invoice instance created from Meta data

        Raises:
            ValueError: If required fields are missing from response
        """
        try:
            invoice_date = datetime.fromisoformat(data["invoice_date"])
            due_date = None
            if "due_date" in data:
                due_date = datetime.fromisoformat(data["due_date"])

            # Parse amount - Meta returns as string
            amount = Decimal(str(data.get("amount_due", "0")))
            
            # Generate filename
            filename = f"meta_invoice_{data['id']}_{invoice_date.strftime('%Y_%m_%d')}.pdf"

            # Map payment status
            status_mapping = {
                "Paid": PaymentStatus.PAID,
                "Unpaid": PaymentStatus.UNPAID,
                "Overdue": PaymentStatus.OVERDUE,
            }
            payment_status = status_mapping.get(
                data.get("payment_status", "Unpaid"), PaymentStatus.UNPAID
            )

            return cls(
                id=data["id"],
                provider=InvoiceProvider.META,
                client_name=client_name,
                invoice_number=data.get("invoice_number"),
                invoice_date=invoice_date,
                due_date=due_date,
                amount=amount,
                currency=data.get("currency", "USD"),
                payment_status=payment_status,
                download_url=data.get("download_uri"),
                filename=filename,
                raw_data=data,
            )
        except (KeyError, ValueError, TypeError) as e:
            raise ValueError(f"Invalid Meta Ads invoice data: {e}") from e

    @classmethod
    def from_google_response(
        cls,
        data: Dict[str, Any],
        client_name: str = "Google Ads Account",
    ) -> "Invoice":
        """
        Create an Invoice from Google Ads API response.

        Args:
            data: Raw Google Ads API response data
            client_name: Name to use for the client

        Returns:
            Invoice instance created from Google data

        Raises:
            ValueError: If required fields are missing from response
        """
        try:
            invoice_date = datetime.fromisoformat(data["issue_date"])
            
            # Google amounts are in micros (millionths)
            amount_micros = int(data.get("total_amount_micros", 0))
            amount = Decimal(amount_micros) / Decimal("1000000")

            # Parse service date range
            billing_start = None
            billing_end = None
            if "service_date_range" in data:
                range_data = data["service_date_range"]
                if "start_date" in range_data:
                    billing_start = datetime.fromisoformat(range_data["start_date"])
                if "end_date" in range_data:
                    billing_end = datetime.fromisoformat(range_data["end_date"])

            # Generate filename
            filename = f"google_invoice_{data['id']}_{invoice_date.strftime('%Y_%m_%d')}.pdf"

            return cls(
                id=data["id"],
                provider=InvoiceProvider.GOOGLE,
                client_name=client_name,
                invoice_date=invoice_date,
                billing_period_start=billing_start,
                billing_period_end=billing_end,
                amount=amount,
                currency=data.get("currency_code", "USD"),
                payment_status=PaymentStatus.PAID,  # Google invoices are typically paid
                download_url=data.get("pdf_url"),
                filename=filename,
                raw_data=data,
            )
        except (KeyError, ValueError, TypeError) as e:
            raise ValueError(f"Invalid Google Ads invoice data: {e}") from e


class InvoiceSummary(BaseModel):
    """
    Summary statistics for a collection of invoices.
    
    Provides aggregated information about invoices for reporting
    and display purposes.
    """

    total_count: int = Field(..., ge=0, description="Total number of invoices")
    total_amount: Decimal = Field(..., ge=0, description="Total amount across all invoices")
    currency: str = Field(..., description="Primary currency (assumes single currency)")
    providers: list[InvoiceProvider] = Field(..., description="List of providers included")
    date_range_start: Optional[datetime] = Field(default=None, description="Earliest invoice date")
    date_range_end: Optional[datetime] = Field(default=None, description="Latest invoice date")
    by_provider: Dict[str, int] = Field(default_factory=dict, description="Count by provider")
    by_status: Dict[str, int] = Field(default_factory=dict, description="Count by payment status")

    @classmethod
    def from_invoices(cls, invoices: list[Invoice]) -> "InvoiceSummary":
        """
        Create a summary from a list of invoices.

        Args:
            invoices: List of invoices to summarize

        Returns:
            InvoiceSummary with aggregated data

        Raises:
            ValueError: If invoices list is empty or has mixed currencies
        """
        if not invoices:
            raise ValueError("Cannot create summary from empty invoice list")

        # Check for consistent currency
        currencies = {inv.currency for inv in invoices}
        if len(currencies) > 1:
            raise ValueError(f"Mixed currencies not supported: {currencies}")

        currency = currencies.pop()
        total_amount = sum(inv.amount for inv in invoices)
        providers = list({inv.provider for inv in invoices})
        
        dates = [inv.invoice_date for inv in invoices]
        date_range_start = min(dates)
        date_range_end = max(dates)

        # Count by provider
        by_provider: Dict[str, int] = {}
        for inv in invoices:
            provider_name = inv.provider.value
            by_provider[provider_name] = by_provider.get(provider_name, 0) + 1

        # Count by status
        by_status: Dict[str, int] = {}
        for inv in invoices:
            status_name = inv.payment_status.value
            by_status[status_name] = by_status.get(status_name, 0) + 1

        return cls(
            total_count=len(invoices),
            total_amount=Decimal(str(total_amount)),
            currency=currency,
            providers=providers,
            date_range_start=date_range_start,
            date_range_end=date_range_end,
            by_provider=by_provider,
            by_status=by_status,
        )
