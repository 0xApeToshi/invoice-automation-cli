# src/commands/tokens.py
"""
Token generation command for Google OAuth2 credentials.

This module implements the tokens command that helps users generate
the required OAuth2 credentials for Google Ads API and Google Drive integration.
"""

import glob
import json
import logging
from pathlib import Path
from typing import Optional, Tuple

import typer
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt

from ..utils.logger import get_logger

console = Console()
logger = logging.getLogger(__name__)


def tokens_command(
    secrets_file: Optional[str] = typer.Option(
        None,
        "--secrets-file",
        "-s",
        help="Path to client_secret.json from Google Cloud Console",
    ),
    provider: str = typer.Option(
        "google",
        "--provider",
        "-p",
        help="Provider to generate tokens for: google, google-drive, or both",
    ),
    no_validation: bool = typer.Option(
        False,
        "--no-validation",
        help="Skip token validation step",
    ),
    debug: bool = typer.Option(
        False,
        "--debug",
        help="Enable debug logging",
    ),
) -> None:
    """
    Generate OAuth2 tokens for API authentication.
    
    This command helps you generate the required OAuth2 credentials for
    Google Ads API and/or Google Drive integration. It will open a browser 
    window for authentication and provide you with the tokens needed for 
    your .env file.
    
    Prerequisites for Google:
    1. Create a project in Google Cloud Console
    2. Enable the Google Ads API and/or Google Drive API
    3. Create OAuth 2.0 Client ID credentials (Desktop Application)
    4. Download the client_secret.json file
    
    Examples:
        invoice-automation generate-tokens --provider google
        invoice-automation generate-tokens --provider google-drive
        invoice-automation generate-tokens --provider both
        invoice-automation generate-tokens -s /path/to/client_secret.json --debug
    """
    try:
        # Setup logging
        logger_instance = get_logger(
            __name__,
            level="DEBUG" if debug else "INFO",
            debug=debug,
        )
        
        # Validate provider
        valid_providers = {"google", "google-drive", "both"}
        if provider not in valid_providers:
            console.print(f"[red]Error: Provider '{provider}' not supported. Must be one of: {', '.join(valid_providers)}[/red]")
            raise typer.Exit(1)
        
        # Display introduction
        _display_introduction(provider)
        
        # Get secrets file path
        secrets_path = _get_secrets_file_path(secrets_file)
        
        # Generate tokens
        client_id, client_secret, refresh_token = _generate_google_tokens(
            secrets_path, provider, no_validation
        )
        
        # Display results
        _display_token_results(client_id, client_secret, refresh_token, provider)
        
    except KeyboardInterrupt:
        console.print("\n[yellow]Operation cancelled by user[/yellow]")
        raise typer.Exit(1)
    except Exception as e:
        logger.exception("Error during token generation")
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


def _display_introduction(provider: str) -> None:
    """
    Display introduction and prerequisites for token generation.
    
    Args:
        provider: The provider for which tokens are being generated
    """
    services = []
    apis_needed = []
    
    if provider in ["google", "both"]:
        services.append("Google Ads API")
        apis_needed.append("Google Ads API")
    
    if provider in ["google-drive", "both"]:
        services.append("Google Drive API")
        apis_needed.append("Google Drive API")
    
    services_text = " and ".join(services)
    apis_text = " and ".join(apis_needed)
    
    intro_text = f"""[bold blue]OAuth2 Token Generator for {services_text}[/bold blue]

This command will help you generate the OAuth2 credentials needed for
{services_text} integration.

[bold]What you'll need:[/bold]
• Google Cloud Console project with {apis_text} enabled
• OAuth 2.0 Client ID credentials (Desktop Application type)
• The client_secret.json file downloaded from Google Cloud Console

[bold]What this will do:[/bold]
• Open a browser window for Google authentication
• Request appropriate permissions for selected services
• Generate your OAuth2 refresh token
• Provide credentials ready for your .env file

[yellow]Make sure you sign in with the Google account that has access to your services![/yellow]"""

    console.print(Panel(intro_text, title="Token Generation"))


def _get_secrets_file_path(secrets_file: Optional[str]) -> Path:
    """
    Get and validate the secrets file path.
    
    Args:
        secrets_file: Optional path to secrets file
        
    Returns:
        Validated Path object
        
    Raises:
        typer.Exit: If file not found or invalid
    """
    if secrets_file:
        secrets_path = Path(secrets_file)
    else:
        # Try to find client secret files using glob patterns
        patterns = [
            "client_secret*.json",
            "client_secrets*.json",
            "*client_secret*.json",
            "google_client_secret*.json",
        ]
        
        found_files = []
        for pattern in patterns:
            matches = glob.glob(pattern)
            found_files.extend(matches)
        
        # Remove duplicates and sort
        found_files = sorted(list(set(found_files)))
        
        if len(found_files) == 1:
            secrets_path = Path(found_files[0])
            console.print(f"[green]Found secrets file: {secrets_path}[/green]")
        elif len(found_files) > 1:
            console.print(f"[yellow]Found multiple client secret files:[/yellow]")
            for i, file in enumerate(found_files, 1):
                console.print(f"  {i}. {file}")
            
            choice = Prompt.ask(
                "Please select which file to use",
                choices=[str(i) for i in range(1, len(found_files) + 1)],
                default="1"
            )
            secrets_path = Path(found_files[int(choice) - 1])
        else:
            console.print("[yellow]No client secret files found automatically.[/yellow]")
            console.print("Looking for files matching patterns like:")
            console.print("  • client_secret_xxxxx.apps.googleusercontent.com.json")
            console.print("  • client_secret.json")
            console.print("  • client_secrets.json")
            
            file_input = Prompt.ask(
                "Please enter the path to your client secret file",
                default="client_secret.json"
            )
            secrets_path = Path(file_input)
    
    # Validate file exists
    if not secrets_path.exists():
        console.print(f"[red]Error: Secrets file not found: {secrets_path}[/red]")
        console.print("\n[yellow]To get this file:[/yellow]")
        console.print("1. Go to Google Cloud Console")
        console.print("2. Navigate to Credentials > Create Credentials > OAuth 2.0 Client IDs")
        console.print("3. Choose 'Desktop Application'")
        console.print("4. Download the JSON file")
        raise typer.Exit(1)
    
    # Validate file format
    try:
        with open(secrets_path, "r") as f:
            secrets = json.load(f)
        
        if "installed" not in secrets and "web" not in secrets:
            console.print(f"[red]Error: Invalid client secrets file format.[/red]")
            console.print("The file should contain either 'installed' or 'web' configuration.")
            raise typer.Exit(1)
            
    except json.JSONDecodeError:
        console.print(f"[red]Error: Invalid JSON in secrets file: {secrets_path}[/red]")
        raise typer.Exit(1)
    
    return secrets_path


def _generate_google_tokens(
    secrets_path: Path, 
    provider: str,
    no_validation: bool
) -> Tuple[str, str, str]:
    """
    Generate Google OAuth2 tokens using the provided secrets file.
    
    Args:
        secrets_path: Path to the client secrets JSON file
        provider: Provider type to determine scopes
        no_validation: Whether to skip token validation
        
    Returns:
        Tuple of (client_id, client_secret, refresh_token)
        
    Raises:
        ImportError: If required packages are not installed
        Exception: If OAuth flow fails
    """
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow  # type: ignore
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
    except ImportError:
        console.print("[red]Error: Required packages not installed.[/red]")
        console.print("Please install them with: [cyan]pip install google-auth-oauthlib[/cyan]")
        raise typer.Exit(1)
    
    # Determine scopes based on provider
    scopes = []
    if provider in ["google", "both"]:
        scopes.append("https://www.googleapis.com/auth/adwords")
    
    if provider in ["google-drive", "both"]:
        scopes.extend([
            "https://www.googleapis.com/auth/drive.file",
            "https://www.googleapis.com/auth/drive.metadata"
        ])
    
    console.print(f"\n[bold]Starting OAuth2 flow for: {', '.join(scopes)}[/bold]")
    console.print("A browser window will open for authentication.")
    
    try:
        # Create the OAuth2 flow
        flow = InstalledAppFlow.from_client_secrets_file(
            str(secrets_path),
            scopes
        )
        
        # Run the flow - this will open a browser window
        credentials = flow.run_local_server(
            port=0,  # Use random available port
            access_type="offline",  # Ensures we get a refresh token
            prompt="consent"  # Forces consent screen to ensure refresh token
        )
        
        if not credentials.refresh_token:
            console.print("[red]No refresh token received.[/red]")
            console.print("This might happen if you've already authorized this application.")
            console.print("Try revoking access at https://myaccount.google.com/permissions and run this command again.")
            raise typer.Exit(1)
        
        # Extract credentials
        client_config = flow.client_config
        client_id = client_config["client_id"]
        client_secret = client_config["client_secret"]
        refresh_token = credentials.refresh_token
        
        console.print("[green]✓ OAuth2 flow completed successfully[/green]")
        
        # Validate tokens unless skipped
        if not no_validation:
            console.print("\n[bold]Validating tokens...[/bold]")
            
            try:
                # Create credentials object and test refresh
                test_credentials = Credentials(  # type: ignore
                    token=None,
                    refresh_token=refresh_token,
                    client_id=client_id,
                    client_secret=client_secret,
                    token_uri="https://oauth2.googleapis.com/token",
                    scopes=scopes
                )
                
                request = Request()  # type: ignore
                test_credentials.refresh(request)
                console.print("[green]✓ Token validation successful[/green]")
                
            except Exception as e:
                console.print(f"[yellow]⚠ Token validation failed: {e}[/yellow]")
                console.print("Tokens might still work, but there could be an issue.")
        
        return client_id, client_secret, refresh_token
        
    except Exception as e:
        console.print(f"[red]OAuth flow failed: {e}[/red]")
        raise


def _display_token_results(client_id: str, client_secret: str, refresh_token: str, provider: str) -> None:
    """
    Display the generated tokens in a format ready for .env file.
    
    Args:
        client_id: OAuth2 client ID
        client_secret: OAuth2 client secret
        refresh_token: OAuth2 refresh token
        provider: Provider type that was configured
    """
    # Create the .env content based on provider
    env_content_lines = ["# Google OAuth2 Configuration (generated by invoice-automation)"]
    
    if provider in ["google", "both"]:
        env_content_lines.extend([
            "",
            "# Google Ads API Configuration",
            f"GOOGLE_CLIENT_ID={client_id}",
            f"GOOGLE_CLIENT_SECRET={client_secret}",
            f"GOOGLE_REFRESH_TOKEN={refresh_token}",
            "",
            "# Still needed for Google Ads (get these separately):",
            "# GOOGLE_CUSTOMER_ID=your_google_ads_customer_id",
            "# GOOGLE_DEVELOPER_TOKEN=your_google_ads_developer_token"
        ])
    
    if provider in ["google-drive", "both"]:
        env_content_lines.extend([
            "",
            "# Google Drive Configuration",
            "GOOGLE_DRIVE_ENABLED=true",
            f"GOOGLE_DRIVE_CLIENT_ID={client_id}",
            f"GOOGLE_DRIVE_CLIENT_SECRET={client_secret}",
            f"GOOGLE_DRIVE_REFRESH_TOKEN={refresh_token}",
            "",
            "# Optional Google Drive settings:",
            "# GOOGLE_DRIVE_FOLDER_ID=your_specific_folder_id",
            "# GOOGLE_DRIVE_FOLDER_STRUCTURE=client  # date, client, provider, flat",
            "# GOOGLE_DRIVE_OVERWRITE_EXISTING=false",
            "# GOOGLE_DRIVE_SHARE_PERMISSIONS=none  # none, view, edit"
        ])
    
    if provider == "both":
        env_content_lines.extend([
            "",
            "# Note: Same OAuth2 credentials work for both Google Ads and Google Drive",
            "# You can also use the GOOGLE_* variables for Drive if you prefer:"
        ])
    
    env_content = "\n".join(env_content_lines)

    results_text = f"""[bold green]SUCCESS! Your Google OAuth2 credentials have been generated.[/bold green]

[bold]Generated Credentials:[/bold]
• Client ID: {client_id[:20]}...
• Client Secret: {client_secret[:10]}...
• Refresh Token: {refresh_token[:20]}...

[bold]Provider Configured:[/bold] {provider}

[bold]Next Steps:[/bold]
1. Add these credentials to your .env file (see below)"""
    
    if provider in ["google", "both"]:
        results_text += "\n2. Get your Google Ads Customer ID from https://ads.google.com"
        results_text += "\n3. Apply for Google Ads API access to get your Developer Token"
    
    if provider in ["google-drive", "both"]:
        results_text += "\n4. Test Google Drive upload with 'invoice-automation upload --dry-run'"
    
    results_text += "\n5. Run 'invoice-automation status' to test your configuration"

    results_text += f"\n\n[bold]Add to your .env file:[/bold]\n{env_content}"

    console.print(Panel(results_text, title="Token Generation Complete"))
    
    # Offer to save to file
    save_to_file = typer.confirm(
        "\nWould you like to save these credentials to a file?",
        default=True
    )
    
    if save_to_file:
        filename = Prompt.ask(
            "Enter filename",
            default="google_credentials.env"
        )
        
        try:
            with open(filename, "w") as f:
                f.write(env_content)
            console.print(f"[green]✓ Credentials saved to {filename}[/green]")
            console.print(f"You can copy these lines to your main .env file.")
        except Exception as e:
            console.print(f"[red]Failed to save file: {e}[/red]")
