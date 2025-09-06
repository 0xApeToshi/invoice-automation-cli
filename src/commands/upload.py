# src/commands/upload.py
"""
Upload command for syncing invoices to Google Drive.

This module implements the upload command that syncs locally downloaded
invoices to Google Drive with configurable folder structures and options.
"""

import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, List, Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn
from rich.table import Table

from ..config.settings import get_config, ConfigurationError
from ..models.invoice import Invoice
from ..services.drive_client import GoogleDriveClient
from ..utils.logger import get_logger

console = Console()
logger = logging.getLogger(__name__)


def upload_command(
    start_date: Optional[str] = typer.Option(
        None,
        "--start-date",
        "-s",
        help="Start date for files to upload (YYYY-MM-DD)",
    ),
    end_date: Optional[str] = typer.Option(
        None,
        "--end-date",
        "-e",
        help="End date for files to upload (YYYY-MM-DD)",
    ),
    provider: str = typer.Option(
        "google-drive",
        "--provider",
        "-p",
        help="Upload provider (currently only 'google-drive')",
    ),
    folder_structure: Optional[str] = typer.Option(
        None,
        "--folder-structure",
        help="Folder organization: date, client, provider, flat",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Show what would be uploaded without actually uploading",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        help="Upload all files, overwriting existing ones",
    ),
    input_dir: Optional[str] = typer.Option(
        None,
        "--input-dir",
        "-i",
        help="Directory to scan for invoices. Defaults to config output_dir.",
    ),
    client_filter: Optional[str] = typer.Option(
        None,
        "--client",
        "-c",
        help="Upload files for specific client only",
    ),
    debug: bool = typer.Option(
        False,
        "--debug",
        help="Enable debug logging",
    ),
) -> None:
    """
    Upload invoice files to cloud storage providers.
    
    This command uploads locally downloaded invoice files to Google Drive
    with configurable folder structures and sync options.
    
    Examples:
        invoice-automation upload
        invoice-automation upload --dry-run --folder-structure date
        invoice-automation upload --start-date 2024-01-01 --client "Acme Corp"
        invoice-automation upload --force --input-dir ./custom-invoices
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
        
        # Validate provider
        if provider != "google-drive":
            console.print(f"[red]Error: Provider '{provider}' not supported. Currently only 'google-drive' is available.[/red]")
            raise typer.Exit(1)
        
        # Check if Google Drive is configured
        if not config.has_google_drive_config():
            console.print("[red]Error: Google Drive not configured.[/red]")
            console.print("Please set up Google Drive credentials in your .env file.")
            console.print("Use 'invoice-automation generate-tokens --provider google-drive' to get started.")
            raise typer.Exit(1)
        
        # Parse dates if provided
        parsed_start_date, parsed_end_date = _parse_date_range(start_date, end_date)
        
        # Determine input directory
        scan_dir = Path(input_dir) if input_dir else config.output_dir
        if not scan_dir.exists():
            console.print(f"[red]Error: Input directory not found: {scan_dir}[/red]")
            raise typer.Exit(1)
        
        # Get folder structure setting - handle the case where google_drive config might be None
        if config.google_drive is not None:
            folder_structure_setting = folder_structure or config.google_drive.folder_structure
        else:
            # This should not happen due to the check above, but provide a fallback
            folder_structure_setting = folder_structure or "client"
        
        # Display configuration summary
        _display_upload_configuration(
            scan_dir,
            provider,
            folder_structure_setting,
            dry_run,
            force,
            parsed_start_date,
            parsed_end_date,
            client_filter,
        )
        
        # Run the upload operation
        asyncio.run(
            _run_upload_operation(
                config,
                scan_dir,
                folder_structure_setting,
                dry_run,
                force,
                parsed_start_date,
                parsed_end_date,
                client_filter,
            )
        )
        
    except ConfigurationError as e:
        console.print(f"[red]Configuration Error: {e}[/red]")
        console.print("\n[yellow]Please check your .env file and ensure Google Drive is configured.[/yellow]")
        raise typer.Exit(1)
    except KeyboardInterrupt:
        console.print("\n[yellow]Operation cancelled by user[/yellow]")
        raise typer.Exit(1)
    except Exception as e:
        logger.exception("Unexpected error during upload operation")
        console.print(f"[red]Unexpected error: {e}[/red]")
        raise typer.Exit(1)


def _parse_date_range(
    start_date: Optional[str], 
    end_date: Optional[str]
) -> tuple[Optional[datetime], Optional[datetime]]:
    """
    Parse and validate the date range for file filtering.
    
    Args:
        start_date: Start date string or None
        end_date: End date string or None
        
    Returns:
        Tuple of (start_datetime, end_datetime) or (None, None)
        
    Raises:
        typer.Exit: If date parsing fails
    """
    try:
        parsed_start = None
        parsed_end = None
        
        if start_date:
            parsed_start = datetime.strptime(start_date, "%Y-%m-%d")
        
        if end_date:
            parsed_end = datetime.strptime(end_date, "%Y-%m-%d")
        
        # Validate date range
        if parsed_start and parsed_end and parsed_start > parsed_end:
            console.print("[red]Error: Start date must be before or equal to end date[/red]")
            raise typer.Exit(1)
            
        return parsed_start, parsed_end
        
    except ValueError as e:
        console.print(f"[red]Error: Invalid date format. Use YYYY-MM-DD format. {e}[/red]")
        raise typer.Exit(1)


def _display_upload_configuration(
    scan_dir: Path,
    provider: str,
    folder_structure: str,
    dry_run: bool,
    force: bool,
    start_date: Optional[datetime],
    end_date: Optional[datetime],
    client_filter: Optional[str],
) -> None:
    """
    Display a summary of the upload operation configuration.
    
    Args:
        scan_dir: Directory to scan for files
        provider: Upload provider
        folder_structure: Folder organization method
        dry_run: Whether this is a dry run
        force: Whether to force upload existing files
        start_date: Optional start date filter
        end_date: Optional end date filter
        client_filter: Optional client filter
    """
    config_text = f"""[bold blue]Upload Configuration[/bold blue]

[bold]Provider:[/bold] {provider.title()}
[bold]Input Directory:[/bold] {scan_dir.absolute()}
[bold]Folder Structure:[/bold] {folder_structure}
[bold]Operation Mode:[/bold] {"Dry Run (no uploads)" if dry_run else "Upload files"}
[bold]Overwrite Policy:[/bold] {"Force overwrite" if force else "Skip existing files"}"""

    if start_date or end_date:
        date_range = ""
        if start_date:
            date_range += start_date.strftime("%Y-%m-%d")
        else:
            date_range += "earliest"
        date_range += " to "
        if end_date:
            date_range += end_date.strftime("%Y-%m-%d")
        else:
            date_range += "latest"
        config_text += f"\n[bold]Date Filter:[/bold] {date_range}"

    if client_filter:
        config_text += f"\n[bold]Client Filter:[/bold] {client_filter}"

    console.print(Panel(config_text, title="Upload Configuration"))


async def _run_upload_operation(
    config: Any,
    scan_dir: Path,
    folder_structure: str,
    dry_run: bool,
    force: bool,
    start_date: Optional[datetime],
    end_date: Optional[datetime],
    client_filter: Optional[str],
) -> None:
    """
    Execute the main upload operation.
    
    Args:
        config: Application configuration
        scan_dir: Directory to scan for files
        folder_structure: Folder organization method
        dry_run: Whether this is a dry run
        force: Whether to force upload existing files
        start_date: Optional start date filter
        end_date: Optional end date filter
        client_filter: Optional client filter
    """
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        
        # Scan for local files
        scan_task = progress.add_task("Scanning for invoice files...", total=1)
        local_files = await _scan_local_files(
            scan_dir, 
            start_date, 
            end_date, 
            client_filter,
            progress,
            scan_task
        )
        
        if not local_files:
            console.print("[yellow]No invoice files found matching the criteria[/yellow]")
            return
        
        console.print(f"\n[green]Found {len(local_files)} files to process[/green]")
        
        # Display files summary
        _display_files_summary(local_files)
        
        if dry_run:
            console.print("\n[yellow]Dry run completed - no files were uploaded[/yellow]")
            return
        
        # Initialize Google Drive client
        drive_client = GoogleDriveClient(
            config.google_drive,
            retry_config=config.retry,
            timeout_seconds=config.retry.timeout_seconds,
        )
        
        # Upload files
        upload_task = progress.add_task("Uploading files...", total=len(local_files))
        
        async with drive_client:
            successful, errors = await drive_client.upload_files(
                local_files,
                folder_structure,
                force,
                progress,
                upload_task,
            )
        
        _display_upload_results(successful, errors)


async def _scan_local_files(
    scan_dir: Path,
    start_date: Optional[datetime],
    end_date: Optional[datetime],
    client_filter: Optional[str],
    progress: Progress,
    task_id: Any,
) -> List[Path]:
    """
    Scan the local directory for invoice files matching the criteria.
    
    Args:
        scan_dir: Directory to scan
        start_date: Optional start date filter
        end_date: Optional end date filter
        client_filter: Optional client filter
        progress: Progress bar instance
        task_id: Progress task ID
        
    Returns:
        List of file paths that match the criteria
    """
    progress.update(task_id, description="Scanning for invoice files...")
    
    # Common invoice file patterns
    patterns = ["*.pdf", "*.txt"]  # PDFs and placeholder text files
    
    found_files: List[Path] = []
    for pattern in patterns:
        found_files.extend(scan_dir.rglob(pattern))
    
    # Filter files based on criteria
    filtered_files = []
    
    for file_path in found_files:
        # Skip if not a file
        if not file_path.is_file():
            continue
        
        # Client filter (check if client name is in the path)
        if client_filter and client_filter.lower() not in str(file_path).lower():
            continue
        
        # Date filter (use file modification time as proxy)
        if start_date or end_date:
            file_time = datetime.fromtimestamp(file_path.stat().st_mtime)
            if start_date and file_time < start_date:
                continue
            if end_date and file_time > end_date:
                continue
        
        filtered_files.append(file_path)
    
    progress.update(task_id, advance=1)
    logger.info(f"Found {len(filtered_files)} files matching criteria")
    
    return filtered_files


def _display_files_summary(files: List[Path]) -> None:
    """
    Display a summary of files to be uploaded.
    
    Args:
        files: List of file paths
    """
    if not files:
        return
    
    # Group files by provider and client
    summary: dict[str, dict[str, int]] = {}
    total_size = 0
    
    for file_path in files:
        try:
            file_size = file_path.stat().st_size
            total_size += file_size
            
            # Extract provider and client from path structure
            # Assuming structure like: base/client/provider/file.pdf
            path_parts = file_path.parts
            if len(path_parts) >= 3:
                client = path_parts[-3]
                provider = path_parts[-2]
            else:
                client = "Unknown"
                provider = "Unknown"
            
            if provider not in summary:
                summary[provider] = {}
            
            summary[provider][client] = summary[provider].get(client, 0) + 1
            
        except (OSError, IndexError):
            # Skip files we can't access or parse
            continue
    
    # Create summary table
    table = Table(title="Files to Upload")
    table.add_column("Provider", style="cyan")
    table.add_column("Client", style="green")
    table.add_column("Files", style="yellow", justify="right")
    
    for provider, clients in summary.items():
        for client, count in clients.items():
            table.add_row(provider.title(), client, str(count))
    
    console.print("\n")
    console.print(table)
    
    # Display total size
    size_mb = total_size / (1024 * 1024)
    console.print(f"\n[bold]Total size:[/bold] {size_mb:.2f} MB ({len(files)} files)")


def _display_upload_results(
    successful: List[Any],
    errors: List[Any],
) -> None:
    """
    Display the results of the upload operation.
    
    Args:
        successful: List of successfully uploaded files
        errors: List of upload errors
    """
    total = len(successful) + len(errors)
    success_rate = (len(successful) / total * 100) if total > 0 else 0
    
    result_text = f"""[bold blue]Upload Results[/bold blue]

[bold]Total Attempted:[/bold] {total}
[bold]Successful:[/bold] {len(successful)}
[bold]Failed:[/bold] {len(errors)}
[bold]Success Rate:[/bold] {success_rate:.1f}%"""

    if errors:
        result_text += f"\n\n[red]Errors:[/red]"
        for error in errors[:5]:  # Show first 5 errors
            result_text += f"\n• {error}"
        if len(errors) > 5:
            result_text += f"\n• ... and {len(errors) - 5} more"
            
    console.print(Panel(result_text, title="Upload Summary"))
    
    if successful:
        console.print(f"\n[green]Successfully uploaded {len(successful)} files to Google Drive![/green]")
    
    if errors:
        console.print(f"\n[yellow]Check the logs for details on failed uploads.[/yellow]")
