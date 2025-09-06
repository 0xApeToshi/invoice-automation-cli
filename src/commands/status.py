# src/commands/status.py
"""
Status command for testing provider connections and configuration.

This module implements the status command that tests API connections,
validates configuration, and provides diagnostic information about
the invoice automation setup.
"""

import asyncio
import logging
from typing import Any, Dict, List, Union

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from ..config.settings import get_config, ConfigurationError
from ..services.meta_client import MetaAdsClient
from ..services.google_client import GoogleAdsClient
from ..utils.logger import get_logger

console = Console()
logger = logging.getLogger(__name__)


def status_command(
    provider: str = typer.Option(
        "both",
        "--provider",
        "-p",
        help="Check status for specific provider: meta, google, or both",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Show detailed configuration information",
    ),
    debug: bool = typer.Option(
        False,
        "--debug",
        help="Enable debug logging",
    ),
) -> None:
    """
    Check the status of provider configurations and API connections.
    
    This command tests API connections, validates credentials, and provides
    diagnostic information about the current configuration setup.
    
    Examples:
        invoice-automation status
        invoice-automation status --provider meta --verbose
        invoice-automation status --debug
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
        
        # Display configuration overview
        _display_configuration_overview(config, verbose)
        
        # Test provider connections
        asyncio.run(_test_provider_connections(config, provider))
        
    except ConfigurationError as e:
        console.print(f"[red]Configuration Error: {e}[/red]")
        console.print("\n[yellow]Please check your .env file and ensure all required credentials are set.[/yellow]")
        raise typer.Exit(1)
    except Exception as e:
        logger.exception("Unexpected error during status check")
        console.print(f"[red]Unexpected error: {e}[/red]")
        raise typer.Exit(1)


def _display_configuration_overview(config: Any, verbose: bool) -> None:
    """
    Display an overview of the current configuration.
    
    Args:
        config: Application configuration
        verbose: Whether to show detailed information
    """
    enabled_providers = config.get_enabled_providers()
    
    config_text = f"""[bold blue]Configuration Overview[/bold blue]

[bold]Output Directory:[/bold] {config.output_dir.absolute()}
[bold]Log Level:[/bold] {config.log_level}
[bold]Debug Mode:[/bold] {'Enabled' if config.debug else 'Disabled'}
[bold]Enabled Providers:[/bold] {', '.join(enabled_providers) if enabled_providers else 'None'}"""

    if verbose:
        config_text += f"\n\n[bold]Retry Configuration:[/bold]"
        config_text += f"\n• Max Attempts: {config.retry.max_attempts}"
        config_text += f"\n• Initial Delay: {config.retry.initial_delay}s"
        config_text += f"\n• Max Delay: {config.retry.max_delay}s"
        config_text += f"\n• Timeout: {config.retry.timeout_seconds}s"
        
        if config.has_meta_config():
            config_text += f"\n\n[bold]Meta Ads Configuration:[/bold]"
            config_text += f"\n• Business ID: {config.meta.business_id}"
            config_text += f"\n• API Version: {config.meta.api_version}"
            config_text += f"\n• Access Token: {'●' * 8 + config.meta.access_token[-4:] if len(config.meta.access_token) > 4 else '●' * len(config.meta.access_token)}"
            
        if config.has_google_config():
            config_text += f"\n\n[bold]Google Ads Configuration:[/bold]"
            config_text += f"\n• Customer ID: {config.google.customer_id}"
            config_text += f"\n• Client ID: {config.google.client_id}"
            config_text += f"\n• Developer Token: {'●' * 8 + config.google.developer_token[-4:] if len(config.google.developer_token) > 4 else '●' * len(config.google.developer_token)}"
    
    console.print(Panel(config_text, title="Configuration"))


async def _test_provider_connections(config: Any, provider: str) -> None:
    """
    Test connections to the specified providers.
    
    Args:
        config: Application configuration
        provider: Provider to test ("meta", "google", or "both")
    """
    providers_to_test = []
    
    if provider in ["meta", "both"] and config.has_meta_config():
        providers_to_test.append("meta")
    if provider in ["google", "both"] and config.has_google_config():
        providers_to_test.append("google")
    
    if not providers_to_test:
        console.print("[yellow]No providers configured for testing[/yellow]")
        return
    
    console.print("\n[bold]Testing Provider Connections...[/bold]")
    
    results = []
    
    for provider_name in providers_to_test:
        console.print(f"\nTesting {provider_name.title()} Ads connection...")
        
        try:
            result = await _test_single_provider(provider_name, config)
            results.append(result)
            
            if result["success"]:
                console.print(f"[green]✓[/green] {provider_name.title()} Ads: {result['message']}")
            else:
                console.print(f"[red]✗[/red] {provider_name.title()} Ads: {result['message']}")
                
        except Exception as e:
            logger.error(f"Error testing {provider_name}: {e}")
            console.print(f"[red]✗[/red] {provider_name.title()} Ads: Unexpected error - {e}")
            results.append({
                "provider": provider_name,
                "success": False,
                "message": f"Unexpected error: {e}",
                "details": None,
            })
    
    _display_connection_summary(results)


async def _test_single_provider(provider_name: str, config: Any) -> Dict[str, Any]:
    """
    Test connection to a single provider.
    
    Args:
        provider_name: Name of the provider to test
        config: Application configuration
        
    Returns:
        Dictionary with test results
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
            return {
                "provider": provider_name,
                "success": False,
                "message": f"Unknown provider: {provider_name}",
                "details": None,
            }
        
        async with client:
            success = await client.test_connection()
            
            if success:
                # Get additional details if connection successful
                details = await _get_provider_details(client, provider_name)
                return {
                    "provider": provider_name,
                    "success": True,
                    "message": "Connection successful",
                    "details": details,
                }
            else:
                return {
                    "provider": provider_name,
                    "success": False,
                    "message": "Connection test failed",
                    "details": None,
                }
                
    except Exception as e:
        return {
            "provider": provider_name,
            "success": False,
            "message": str(e),
            "details": None,
        }


async def _get_provider_details(client: Union[MetaAdsClient, GoogleAdsClient], provider_name: str) -> Dict[str, Any]:
    """
    Get additional details about a provider when connection is successful.
    
    Args:
        client: Provider client instance
        provider_name: Name of the provider
        
    Returns:
        Dictionary with provider details
    """
    try:
        if provider_name == "meta" and isinstance(client, MetaAdsClient):
            business_info = await client.get_business_info()
            ad_accounts = await client.list_ad_accounts()
            return {
                "business_name": business_info.get("name", "Unknown"),
                "business_id": business_info.get("id"),
                "ad_accounts_count": len(ad_accounts),
                "verification_status": business_info.get("verification_status"),
            }
        elif provider_name == "google" and isinstance(client, GoogleAdsClient):
            customer_info = await client.get_customer_info()
            billing_setups = await client.list_billing_setups()
            return {
                "customer_name": customer_info.get("descriptiveName", "Unknown"),
                "customer_id": customer_info.get("id"),
                "billing_setups_count": len(billing_setups),
                "currency_code": customer_info.get("currencyCode"),
            }
        else:
            return {}
    except Exception as e:
        logger.warning(f"Failed to get {provider_name} details: {e}")
        return {"error": str(e)}


def _display_connection_summary(results: List[Dict[str, Any]]) -> None:
    """
    Display a summary table of connection test results.
    
    Args:
        results: List of connection test results
    """
    if not results:
        return
    
    table = Table(title="Connection Test Summary")
    table.add_column("Provider", style="cyan")
    table.add_column("Status", style="bold")
    table.add_column("Details", style="dim")
    
    for result in results:
        provider = result["provider"].title()
        
        if result["success"]:
            status = "[green]✓ Connected[/green]"
            details_text = ""
            
            if result.get("details"):
                details = result["details"]
                if result["provider"] == "meta":
                    business_name = details.get("business_name", "Unknown")
                    ad_count = details.get("ad_accounts_count", 0)
                    details_text = f"Business: {business_name}, Ad Accounts: {ad_count}"
                elif result["provider"] == "google":
                    customer_name = details.get("customer_name", "Unknown")
                    billing_count = details.get("billing_setups_count", 0)
                    details_text = f"Customer: {customer_name}, Billing Setups: {billing_count}"
        else:
            status = "[red]✗ Failed[/red]"
            details_text = result["message"]
        
        table.add_row(provider, status, details_text)
    
    console.print("\n")
    console.print(table)
    
    # Overall status
    successful = sum(1 for r in results if r["success"])
    total = len(results)
    
    if successful == total:
        console.print(f"\n[green]All {total} provider(s) connected successfully![/green]")
    elif successful == 0:
        console.print(f"\n[red]All {total} provider(s) failed to connect.[/red]")
    else:
        console.print(f"\n[yellow]{successful}/{total} provider(s) connected successfully.[/yellow]")
