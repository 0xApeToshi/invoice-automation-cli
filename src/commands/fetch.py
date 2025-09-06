# src/commands/fetch.py
"""
Fetch command for retrieving invoices from configured providers.

This module implements the main fetch command that orchestrates invoice
retrieval from Meta Ads and Google Ads, downloads PDFs, and provides
comprehensive reporting of the operation results.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, List, Optional, Union

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn
from rich.table import Table

from ..config.settings import get_config, ConfigurationError
from ..models.invoice import Invoice, InvoiceSummary
from ..services.meta_client import MetaAdsClient
from ..services.google_client import GoogleAdsClient
from ..services.download_service import DownloadService
from ..utils.file_utils import FileManager, ClientProviderStructure
from ..utils.logger import get_logger

console = Console()
logger = logging.getLogger(__name__)


def fetch_command(
    start_date: Optional[str] = typer.Option(
        None,
        "--start-date",
        "-s",
        help="Start date (YYYY-MM-DD). Defaults to first day of last month.",
    ),
    end_date: Optional[str] = typer.Option(
        None,
        "--end-date",
        "-e", 
        help="End date (YYYY-MM-DD). Defaults to last day of last month.",
    ),
    provider: str = typer.Option(
        "both",
        "--provider",
        "-p",
        help="Provider to fetch from: meta, google, or both",
    ),
    output_dir: Optional[str] = typer.Option(
        None,
        "--output-dir",
        "-o",
        help="Output directory for invoices. Overrides config setting.",
    ),
    download_pdfs: bool = typer.Option(
        True,
        "--download/--no-download",
        help="Whether to download invoice PDFs",
    ),
    skip_existing: bool = typer.Option(
        True,
        "--skip-existing/--overwrite",
        help="Skip files that already exist",
    ),
    client_filter: Optional[str] = typer.Option(
        None,
        "--client",
        "-c",
        help="Filter for specific client name",
    ),
    debug: bool = typer.Option(
        False,
        "--debug",
        help="Enable debug logging",
    ),
) -> None:
    """
    Fetch invoices from configured advertising providers.
    
    This command retrieves invoices from Meta Ads and/or Google Ads for the
    specified date range, downloads PDFs, and organizes them according to
    the configured folder structure.
    
    Examples:
        invoice-automation fetch --start-date 2024-01-01 --end-date 2024-01-31
        invoice-automation fetch --provider meta --no-download
        invoice-automation fetch --client "Acme Corp" --debug
    """
    try:
        # Load configuration
        config = get_config()
        
        # Setup logging
        log_level = "DEBUG" if debug else config.log_level
        logger_instance = get_logger(
            __name__,
            level=log_level,
            debug=debug or config.debug,
        )
        
        # Validate provider selection
        if provider not in ["meta", "google", "both"]:
            console.print(f"[red]Error: Invalid provider '{provider}'. Must be 'meta', 'google', or 'both'[/red]")
            raise typer.Exit(1)
            
        # Parse and validate dates
        parsed_start_date, parsed_end_date = _parse_date_range(start_date, end_date)
        
        # Determine output directory
        output_path = Path(output_dir) if output_dir else config.output_dir
        output_path.mkdir(parents=True, exist_ok=True)
        
        # Display configuration summary
        _display_configuration_summary(
            parsed_start_date,
            parsed_end_date,
            provider,
            output_path,
            download_pdfs,
            skip_existing,
            client_filter,
            config.get_enabled_providers(),
        )
        
        # Run the fetch operation
        asyncio.run(
            _run_fetch_operation(
                config,
                parsed_start_date,
                parsed_end_date,
                provider,
                output_path,
                download_pdfs,
                skip_existing,
                client_filter,
            )
        )
        
    except ConfigurationError as e:
        console.print(f"[red]Configuration Error: {e}[/red]")
        console.print("\n[yellow]Please check your .env file and ensure all required credentials are set.[/yellow]")
        raise typer.Exit(1)
    except KeyboardInterrupt:
        console.print("\n[yellow]Operation cancelled by user[/yellow]")
        raise typer.Exit(1)
    except Exception as e:
        logger.exception("Unexpected error during fetch operation")
        console.print(f"[red]Unexpected error: {e}[/red]")
        raise typer.Exit(1)


def _parse_date_range(
    start_date: Optional[str], 
    end_date: Optional[str]
) -> tuple[datetime, datetime]:
    """
    Parse and validate the date range for invoice retrieval.
    
    Args:
        start_date: Start date string or None
        end_date: End date string or None
        
    Returns:
        Tuple of (start_datetime, end_datetime)
        
    Raises:
        typer.Exit: If date parsing fails or range is invalid
    """
    try:
        if start_date and end_date:
            parsed_start = datetime.strptime(start_date, "%Y-%m-%d")
            parsed_end = datetime.strptime(end_date, "%Y-%m-%d")
        else:
            # Default to last month
            today = datetime.now()
            first_day_current_month = today.replace(day=1)
            last_day_last_month = first_day_current_month - timedelta(days=1)
            first_day_last_month = last_day_last_month.replace(day=1)
            
            parsed_start = first_day_last_month
            parsed_end = last_day_last_month
            
        # Validate date range
        if parsed_start > parsed_end:
            console.print("[red]Error: Start date must be before or equal to end date[/red]")
            raise typer.Exit(1)
            
        # Warn if date range is very large
        if (parsed_end - parsed_start).days > 365:
            console.print("[yellow]Warning: Date range spans more than a year. This may take a while.[/yellow]")
            
        return parsed_start, parsed_end
        
    except ValueError as e:
        console.print(f"[red]Error: Invalid date format. Use YYYY-MM-DD format. {e}[/red]")
        raise typer.Exit(1)


def _display_configuration_summary(
    start_date: datetime,
    end_date: datetime,
    provider: str,
    output_path: Path,
    download_pdfs: bool,
    skip_existing: bool,
    client_filter: Optional[str],
    enabled_providers: List[str],
) -> None:
    """
    Display a summary of the fetch operation configuration.
    
    Args:
        start_date: Start date for retrieval
        end_date: End date for retrieval
        provider: Selected provider(s)
        output_path: Output directory path
        download_pdfs: Whether PDFs will be downloaded
        skip_existing: Whether existing files will be skipped
        client_filter: Optional client filter
        enabled_providers: List of providers available in config
    """
    # Check if requested providers are available
    requested_providers = [provider] if provider != "both" else ["meta", "google"]
    available_providers = [p for p in requested_providers if p in enabled_providers]
    unavailable_providers = [p for p in requested_providers if p not in enabled_providers]
    
    config_text = f"""[bold blue]Invoice Fetch Configuration[/bold blue]

[bold]Date Range:[/bold] {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}
[bold]Providers:[/bold] {', '.join(available_providers) if available_providers else 'None available'}
[bold]Output Directory:[/bold] {output_path.absolute()}
[bold]Download PDFs:[/bold] {'Yes' if download_pdfs else 'No'}
[bold]Skip Existing:[/bold] {'Yes' if skip_existing else 'No'}"""

    if client_filter:
        config_text += f"\n[bold]Client Filter:[/bold] {client_filter}"
        
    if unavailable_providers:
        config_text += f"\n\n[yellow]Warning: {', '.join(unavailable_providers)} not configured[/yellow]"
        
    console.print(Panel(config_text, title="Configuration"))


async def _run_fetch_operation(
    config: Any,
    start_date: datetime,
    end_date: datetime,
    provider: str,
    output_path: Path,
    download_pdfs: bool,
    skip_existing: bool,
    client_filter: Optional[str],
) -> None:
    """
    Execute the main fetch operation.
    
    Args:
        config: Application configuration
        start_date: Start date for retrieval
        end_date: End date for retrieval
        provider: Selected provider(s)
        output_path: Output directory path
        download_pdfs: Whether to download PDFs
        skip_existing: Whether to skip existing files
        client_filter: Optional client filter
    """
    all_invoices: List[Invoice] = []
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        
        # Determine which providers to fetch from
        providers_to_fetch = []
        if provider in ["meta", "both"] and config.has_meta_config():
            providers_to_fetch.append("meta")
        if provider in ["google", "both"] and config.has_google_config():
            providers_to_fetch.append("google")
            
        if not providers_to_fetch:
            console.print("[red]No configured providers available for the selected option[/red]")
            return
            
        # Create progress tasks
        fetch_task = progress.add_task("Fetching invoices...", total=len(providers_to_fetch))
        
        # Fetch from each provider
        for provider_name in providers_to_fetch:
            invoices = await _fetch_from_provider(
                provider_name,
                config,
                start_date,
                end_date,
                progress,
                fetch_task,
                client_filter,
            )
            all_invoices.extend(invoices)
            
        # Display fetch results
        _display_fetch_results(all_invoices)
        
        # Download PDFs if requested
        if download_pdfs and all_invoices:
            download_task = progress.add_task("Downloading PDFs...", total=len(all_invoices))
            
            file_manager = FileManager(ClientProviderStructure())
            download_service = DownloadService(
                file_manager,
                config.retry,
                config.retry.timeout_seconds,
            )
            
            async with download_service:
                successful, errors = await download_service.download_invoices(
                    all_invoices,
                    output_path,
                    progress,
                    download_task,
                    skip_existing,
                )
                
            _display_download_results(successful, errors, output_path)


async def _fetch_from_provider(
    provider_name: str,
    config: Any,
    start_date: datetime,
    end_date: datetime,
    progress: Progress,
    task_id: Any,
    client_filter: Optional[str],
) -> List[Invoice]:
    """
    Fetch invoices from a specific provider.
    
    Args:
        provider_name: Name of the provider ("meta" or "google")
        config: Application configuration
        start_date: Start date for retrieval
        end_date: End date for retrieval
        progress: Progress bar instance
        task_id: Progress task ID
        client_filter: Optional client filter
        
    Returns:
        List of invoices from the provider
    """
    try:
        client: Union[MetaAdsClient, GoogleAdsClient]
        
        if provider_name == "meta":
            client = MetaAdsClient(
                config.meta,
                retry_config=config.retry,
                timeout_seconds=config.retry.timeout_seconds,
            )
        elif provider_name == "google":
            client = GoogleAdsClient(
                config.google,
                retry_config=config.retry,
                timeout_seconds=config.retry.timeout_seconds,
            )
        else:
            logger.error(f"Unknown provider: {provider_name}")
            return []
            
        async with client:
            invoices = await client.get_invoices(
                start_date,
                end_date,
                progress,
                task_id,
                client_filter,
            )
            
        logger.info(f"Retrieved {len(invoices)} invoices from {provider_name}")
        return invoices
        
    except Exception as e:
        logger.error(f"Failed to fetch from {provider_name}: {e}")
        console.print(f"[red]Failed to fetch from {provider_name}: {e}[/red]")
        return []


def _display_fetch_results(invoices: List[Invoice]) -> None:
    """
    Display the results of invoice fetching.
    
    Args:
        invoices: List of fetched invoices
    """
    if not invoices:
        console.print("[yellow]No invoices found for the specified criteria[/yellow]")
        return
        
    # Create summary
    try:
        summary = InvoiceSummary.from_invoices(invoices)
        
        date_start_str = summary.date_range_start.strftime('%Y-%m-%d') if summary.date_range_start else "N/A"
        date_end_str = summary.date_range_end.strftime('%Y-%m-%d') if summary.date_range_end else "N/A"
        
        summary_text = f"""[bold green]Fetch Results[/bold green]

[bold]Total Invoices:[/bold] {summary.total_count}
[bold]Total Amount:[/bold] {summary.currency} {summary.total_amount:,.2f}
[bold]Date Range:[/bold] {date_start_str} to {date_end_str}"""

        console.print(Panel(summary_text, title="Summary"))
        
        # Create detailed table
        table = Table(title="Invoice Details")
        table.add_column("Provider", style="cyan")
        table.add_column("Client", style="green")
        table.add_column("Date", style="yellow")
        table.add_column("Amount", style="magenta", justify="right")
        table.add_column("Status", style="blue")
        
        for invoice in invoices:
            table.add_row(
                invoice.provider.value.title(),
                invoice.client_name,
                invoice.invoice_date.strftime('%Y-%m-%d'),
                f"{invoice.currency} {invoice.amount:,.2f}",
                invoice.payment_status.value.title(),
            )
            
        console.print(table)
        
    except ValueError as e:
        logger.error(f"Error creating invoice summary: {e}")
        console.print(f"[yellow]Found {len(invoices)} invoices (summary unavailable: {e})[/yellow]")


def _display_download_results(
    successful: List[Invoice],
    errors: List[Any],
    output_path: Path,
) -> None:
    """
    Display the results of PDF downloads.
    
    Args:
        successful: List of successfully downloaded invoices
        errors: List of download errors
        output_path: Output directory path
    """
    total = len(successful) + len(errors)
    success_rate = (len(successful) / total * 100) if total > 0 else 0
    
    result_text = f"""[bold blue]Download Results[/bold blue]

[bold]Total Attempted:[/bold] {total}
[bold]Successful:[/bold] {len(successful)}
[bold]Failed:[/bold] {len(errors)}
[bold]Success Rate:[/bold] {success_rate:.1f}%
[bold]Output Directory:[/bold] {output_path.absolute()}"""

    if errors:
        result_text += f"\n\n[red]Errors:[/red]"
        for error in errors[:5]:  # Show first 5 errors
            result_text += f"\n• {error.invoice_id}: {str(error)}"
        if len(errors) > 5:
            result_text += f"\n• ... and {len(errors) - 5} more"
            
    console.print(Panel(result_text, title="Download Summary"))
