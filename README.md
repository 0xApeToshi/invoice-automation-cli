# Invoice Automation CLI

A professional-grade Python CLI application for automatically retrieving, downloading, organizing, and uploading invoices from Google Ads and Meta Ads (Facebook) APIs with Google Drive integration.

## Features

- **Multi-Provider Support**: Retrieve invoices from both Google Ads and Meta Ads APIs
- **Automated Downloads**: Download invoice PDFs with retry logic and error handling
- **Google Drive Upload**: Automatically sync invoices to Google Drive with configurable organization
- **Flexible Organization**: Configurable folder structures for organizing invoices locally and in the cloud
- **OAuth2 Token Generation**: Built-in tool to generate Google API credentials
- **Robust Error Handling**: Exponential backoff, rate limit handling, and comprehensive logging
- **Type Safety**: Full type hints and mypy compatibility
- **Modern CLI**: Beautiful, interactive command-line interface with progress bars
- **Configuration Management**: Secure environment-based configuration
- **Connection Testing**: Built-in API connection and credential validation

## Prerequisites

### Meta Ads Requirements

- Meta Business Manager account with Finance role or higher
- Business Manager with "Business Manager Owned Normal Credit Line" enabled
- Valid Facebook Graph API access token
- Business ID for your Meta Business Manager

### Google Ads Requirements

- Google Ads account with monthly invoicing enabled (not automatic payments)
- Google Ads API credentials (OAuth2 setup)
- Developer token from Google Ads API
- Customer ID for your Google Ads account

### Google Drive Requirements (Optional)

- Google Cloud Console project with Google Drive API enabled
- OAuth2 credentials (can be shared with Google Ads)
- Access to Google Drive with sufficient storage space

## Installation

1. **Clone the repository**:

   ```bash
   git clone https://github.com/0xApeToshi/invoice-automation-cli
   cd invoice-automation
   ```

2. **Install dependencies**:

   ```bash
   pip install -r requirements.txt
   ```

3. **Install Google OAuth dependencies** (for token generation and Drive upload):

   ```bash
   pip install google-auth-oauthlib
   ```

4. **Set up configuration**:

   ```bash
   cp .env.example .env
   # Edit .env with your API credentials
   ```

## Quick Start

1. **Generate OAuth2 tokens** for Google services:

   ```bash
   # For Google Ads only
   python -m src.main generate-tokens --provider google

   # For Google Drive only
   python -m src.main generate-tokens --provider google-drive

   # For both Google Ads and Drive
   python -m src.main generate-tokens --provider both
   ```

2. **Configure your credentials** by editing the `.env` file:

   ```bash
   # Meta Ads Configuration
   META_BUSINESS_ID=your_business_id
   META_ACCESS_TOKEN=your_access_token
   META_API_VERSION=v21.0

   # Google Ads Configuration
   GOOGLE_CUSTOMER_ID=your_customer_id
   GOOGLE_CLIENT_ID=your_client_id
   GOOGLE_CLIENT_SECRET=your_client_secret
   GOOGLE_REFRESH_TOKEN=your_refresh_token
   GOOGLE_DEVELOPER_TOKEN=your_developer_token

   # Google Drive Configuration (Optional)
   GOOGLE_DRIVE_ENABLED=true
   GOOGLE_DRIVE_CLIENT_ID=your_client_id
   GOOGLE_DRIVE_CLIENT_SECRET=your_client_secret
   GOOGLE_DRIVE_REFRESH_TOKEN=your_refresh_token
   GOOGLE_DRIVE_FOLDER_STRUCTURE=client
   ```

3. **Test your configuration**:

   ```bash
   python -m src.main status
   ```

4. **Fetch invoices**:

   ```bash
   # Fetch invoices for last month
   python -m src.main fetch

   # Fetch invoices for specific date range
   python -m src.main fetch --start-date 2025-01-01 --end-date 2025-01-31

   # Fetch from specific provider only
   python -m src.main fetch --provider meta
   ```

5. **Upload to Google Drive**:

   ```bash
   # Preview what would be uploaded (dry run)
   python -m src.main upload --dry-run

   # Upload all invoices to Google Drive
   python -m src.main upload

   # Upload with specific folder structure
   python -m src.main upload --folder-structure date
   ```

## Usage

### Commands

#### `generate-tokens` - OAuth2 Token Generation

```bash
python -m src.main generate-tokens [OPTIONS]
```

**Options:**

- `--provider, -p`: Provider to generate tokens for (google/google-drive/both)
- `--secrets-file, -s`: Path to client_secret.json from Google Cloud Console
- `--no-validation`: Skip token validation step
- `--debug`: Enable debug logging

**Examples:**

```bash
# Generate tokens for Google Ads
python -m src.main generate-tokens --provider google

# Generate tokens for Google Drive
python -m src.main generate-tokens --provider google-drive

# Generate tokens for both services
python -m src.main generate-tokens --provider both

# Specify client secret file location
python -m src.main generate-tokens --secrets-file client_secret_123.json
```

#### `fetch` - Retrieve Invoices

```bash
python -m src.main fetch [OPTIONS]
```

**Options:**

- `--start-date, -s`: Start date (YYYY-MM-DD)
- `--end-date, -e`: End date (YYYY-MM-DD)  
- `--provider, -p`: Provider to fetch from (meta/google/both)
- `--output-dir, -o`: Output directory for invoices
- `--download/--no-download`: Whether to download PDFs
- `--skip-existing/--overwrite`: Skip existing files
- `--client, -c`: Filter for specific client
- `--debug`: Enable debug logging

**Examples:**

```bash
# Basic usage - fetch last month's invoices
python -m src.main fetch

# Specific date range
python -m src.main fetch --start-date 2025-01-01 --end-date 2025-01-31

# Meta Ads only, no PDF downloads
python -m src.main fetch --provider meta --no-download

# Debug mode with specific output directory
python -m src.main fetch --debug --output-dir ./my-invoices

# Filter for specific client
python -m src.main fetch --client "Acme Corp"
```

#### `upload` - Upload to Google Drive

```bash
python -m src.main upload [OPTIONS]
```

**Options:**

- `--start-date, -s`: Start date for files to upload (YYYY-MM-DD)
- `--end-date, -e`: End date for files to upload (YYYY-MM-DD)
- `--provider, -p`: Upload provider (currently only 'google-drive')
- `--folder-structure`: Folder organization (date/client/provider/flat)
- `--dry-run`: Show what would be uploaded without uploading
- `--force`: Upload all files, overwriting existing ones
- `--input-dir, -i`: Directory to scan for invoices
- `--client, -c`: Upload files for specific client only
- `--debug`: Enable debug logging

**Examples:**

```bash
# Preview upload (dry run)
python -m src.main upload --dry-run

# Upload all invoices
python -m src.main upload

# Upload with date-based folder structure
python -m src.main upload --folder-structure date

# Upload specific date range
python -m src.main upload --start-date 2024-01-01 --end-date 2024-01-31

# Force overwrite existing files
python -m src.main upload --force

# Upload specific client only
python -m src.main upload --client "Acme Corp"
```

#### `status` - Check Configuration

```bash
python -m src.main status [OPTIONS]
```

**Options:**

- `--provider, -p`: Check specific provider (meta/google/google-drive/both)
- `--verbose, -v`: Show detailed configuration
- `--debug`: Enable debug logging

**Examples:**

```bash
# Check all configured providers
python -m src.main status

# Verbose output with configuration details
python -m src.main status --verbose

# Check Meta Ads configuration only
python -m src.main status --provider meta

# Check Google Drive configuration
python -m src.main status --provider google-drive
```

#### `setup` - Interactive Configuration

```bash
python -m src.main setup [OPTIONS]
```

**Options:**

- `--provider, -p`: Provider to set up (meta/google/google-drive/both)
- `--interactive/--non-interactive`: Use setup wizard

## Configuration

### Environment Variables

All configuration is managed through environment variables in a `.env` file:

```bash
# Meta Ads Configuration
META_BUSINESS_ID=your_business_id_here
META_ACCESS_TOKEN=your_access_token_here
META_API_VERSION=v21.0

# Google Ads Configuration
GOOGLE_CUSTOMER_ID=your_customer_id_here
GOOGLE_CLIENT_ID=your_client_id_here
GOOGLE_CLIENT_SECRET=your_client_secret_here
GOOGLE_REFRESH_TOKEN=your_refresh_token_here
GOOGLE_DEVELOPER_TOKEN=your_developer_token_here

# Google Drive Configuration
GOOGLE_DRIVE_ENABLED=true
GOOGLE_DRIVE_CLIENT_ID=your_client_id_here
GOOGLE_DRIVE_CLIENT_SECRET=your_client_secret_here
GOOGLE_DRIVE_REFRESH_TOKEN=your_refresh_token_here
GOOGLE_DRIVE_FOLDER_ID=optional_specific_folder_id
GOOGLE_DRIVE_FOLDER_STRUCTURE=client
GOOGLE_DRIVE_OVERWRITE_EXISTING=false
GOOGLE_DRIVE_SHARE_PERMISSIONS=none

# Application Configuration
OUTPUT_DIR=./invoices
LOG_LEVEL=INFO
MAX_RETRIES=3
RETRY_DELAY=1.0
TIMEOUT_SECONDS=30
DEBUG=false
```

### Folder Structure Options

The application supports multiple folder organization methods:

#### Local Folder Structure (Default: Client/Provider)

```
invoices/
├── Client Name/
│   ├── meta/
│   │   ├── meta_invoice_123_2025_01_15.pdf
│   │   └── meta_invoice_124_2025_01_31.pdf
│   └── google/
│       ├── google_invoice_456_2025_01_15.pdf
│       └── google_invoice_457_2025_01_31.pdf
```

#### Google Drive Folder Structures

1. **Client-based** (`client`):

   ```
   Drive/
   ├── Acme Corp/
   │   ├── Meta/
   │   └── Google/
   └── Other Client/
       ├── Meta/
       └── Google/
   ```

2. **Date-based** (`date`):

   ```
   Drive/
   ├── 2025/
   │   ├── 01/
   │   │   ├── Meta/
   │   │   └── Google/
   │   └── 02/
   └── 2024/
   ```

3. **Provider-based** (`provider`):

   ```
   Drive/
   ├── Meta/
   │   ├── 2025/
   │   └── 2024/
   └── Google/
       ├── 2025/
       └── 2024/
   ```

4. **Flat** (`flat`):

   ```
   Drive/
   ├── meta_invoice_123_2025_01_15.pdf
   ├── google_invoice_456_2025_01_15.pdf
   └── ...
   ```

## OAuth2 Setup Guide

### Getting Google Cloud Credentials

1. **Create Google Cloud Project**:
   - Go to [Google Cloud Console](https://console.cloud.google.com/)
   - Create a new project or select existing one

2. **Enable APIs**:
   - Enable Google Ads API (for invoice fetching)
   - Enable Google Drive API (for uploads)

3. **Create OAuth2 Credentials**:
   - Go to Credentials → Create Credentials → OAuth 2.0 Client IDs
   - Choose "Desktop Application"
   - Download the JSON file (named like `client_secret_xxxxx.apps.googleusercontent.com.json`)

4. **Generate Tokens**:

   ```bash
   python -m src.main generate-tokens --provider both
   ```

## API Requirements

### Meta Ads API

- **Endpoint**: `/{business_id}/business_invoices`
- **Required Permissions**: Finance role on Business Manager
- **Billing Setup**: Business Manager Owned Normal Credit Line
- **Rate Limits**: 200 calls per hour per user
- **Pagination**: Cursor-based with `after` parameter

### Google Ads API  

- **Service**: InvoiceService
- **Method**: ListInvoices
- **Required Setup**: Monthly invoicing (not automatic payments)
- **Authentication**: OAuth2 with refresh tokens
- **Date Range**: Data available from 2019 onward
- **Format**: Requests by year/month combinations

### Google Drive API

- **Service**: Drive API v3
- **Required Scopes**: `drive.file`, `drive.metadata`
- **Authentication**: OAuth2 with refresh tokens
- **Features**: File upload, folder creation, conflict detection
- **Rate Limits**: 1,000 requests per 100 seconds per user

## Development

### Project Structure

```
src/
├── main.py              # CLI entry point
├── config/
│   └── settings.py      # Configuration management
├── models/
│   ├── config.py        # Configuration models
│   └── invoice.py       # Invoice data models
├── services/
│   ├── base_client.py   # Abstract base client
│   ├── meta_client.py   # Meta Ads API client
│   ├── google_client.py # Google Ads API client
│   ├── drive_client.py  # Google Drive API client
│   └── download_service.py # PDF download service
├── commands/
│   ├── fetch.py         # Fetch command implementation
│   ├── status.py        # Status command implementation
│   ├── tokens.py        # Token generation command
│   └── upload.py        # Upload command implementation
└── utils/
    ├── logger.py        # Logging utilities
    ├── retry.py         # Retry logic with backoff
    └── file_utils.py    # File management utilities
```

### Code Quality

The project follows strict development standards:

- **Type Safety**: Full type hints, mypy compliance
- **SOLID Principles**: Clean architecture with dependency injection
- **Error Handling**: Comprehensive exception handling with exponential backoff
- **Logging**: Structured logging with configurable levels
- **Testing**: Unit tests for all components (run with `pytest`)
- **Documentation**: Comprehensive docstrings following Google style

### Running Tests

```bash
# Install development dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Run with coverage
pytest --cov=src

# Type checking
mypy src/

# Code formatting
black src/
ruff check src/
```

## Troubleshooting

### Common Issues

1. **"No providers configured"**
   - Ensure your `.env` file exists and contains valid credentials
   - Run `python -m src.main status` to check configuration

2. **"Authentication failed"**
   - Verify API tokens are valid and not expired
   - Check that accounts have proper permissions (Finance role for Meta, API access for Google)
   - For Google services, ensure OAuth2 tokens are properly generated

3. **"No invoices found"**
   - Ensure accounts have monthly invoicing enabled (required for both providers)
   - Check that the date range contains billing periods
   - Verify business setup meets API requirements

4. **"Google Drive upload failed"**
   - Verify Google Drive API is enabled in Google Cloud Console
   - Check OAuth2 scopes include Drive permissions
   - Ensure sufficient storage space in Google Drive

5. **Download/Upload failures**
   - Check internet connectivity and API rate limits
   - Verify download URLs are accessible
   - Check disk space and file permissions

### Debug Mode

Enable debug mode for detailed logging:

```bash
python -m src.main fetch --debug
python -m src.main upload --debug
python -m src.main generate-tokens --debug
```

This provides comprehensive logging including:

- API request/response details
- Retry attempts and backoff timing
- File operation details
- Configuration validation steps
- OAuth2 flow debugging

### Token Issues

If you encounter OAuth2 token issues:

1. **Revoke existing permissions**:
   - Go to [Google Account Permissions](https://myaccount.google.com/permissions)
   - Revoke access for your application
   - Re-run token generation

2. **Check token scopes**:
   - Ensure tokens were generated with correct scopes for your use case
   - Re-generate tokens with `--provider both` for full functionality

## Security Considerations

- **Never commit `.env` files** to version control
- **Use environment variables** for all sensitive configuration
- **Implement proper access controls** for downloaded invoices
- **Regularly rotate API tokens** according to provider recommendations
- **Monitor API usage** to detect unauthorized access
- **Store Google Drive files** in appropriate folders with proper sharing settings

## Workflows

### Complete Invoice Management Workflow

1. **Setup** (one-time):

   ```bash
   # Generate OAuth2 tokens
   python -m src.main generate-tokens --provider both
   
   # Configure .env file with all credentials
   # Test configuration
   python -m src.main status --verbose
   ```

2. **Regular Invoice Processing**:

   ```bash
   # Fetch invoices
   python -m src.main fetch --start-date 2025-01-01 --end-date 2025-01-31
   
   # Upload to Google Drive
   python -m src.main upload --folder-structure client
   ```

3. **Automation** (cron/scheduled):

   ```bash
   # Monthly automation script
   python -m src.main fetch  # Fetches last month by default
   python -m src.main upload --force  # Upload new files
   ```

## License

MIT License - see LICENSE file for details.

## Support

For issues and feature requests, please create an issue in the project repository.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes with tests
4. Ensure all tests pass and code follows style guidelines
5. Submit a pull request

---

Built with ♥ for agency automation
