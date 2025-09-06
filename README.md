# Invoice Automation CLI

A professional-grade Python CLI application for automatically retrieving, downloading, and organizing invoices from Google Ads and Meta Ads (Facebook) APIs.

## Features

- **Multi-Provider Support**: Retrieve invoices from both Google Ads and Meta Ads APIs
- **Automated Downloads**: Download invoice PDFs with retry logic and error handling
- **Flexible Organization**: Configurable folder structures for organizing invoices
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

3. **Set up configuration**:

   ```bash
   cp .env.example .env
   # Edit .env with your API credentials
   ```

## Quick Start

1. **Configure your credentials** by editing the `.env` file:

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
   ```

2. **Test your configuration**:

   ```bash
   python -m src.main status
   ```

3. **Fetch invoices**:

   ```bash
   # Fetch invoices for last month
   python -m src.main fetch

   # Fetch invoices for specific date range
   python -m src.main fetch --start-date 2025-01-01 --end-date 2025-01-31

   # Fetch from specific provider only
   python -m src.main fetch --provider meta
   ```

## Usage

### Commands

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

#### `status` - Check Configuration

```bash
python -m src.main status [OPTIONS]
```

**Options:**

- `--provider, -p`: Check specific provider (meta/google/both)
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
```

#### `setup` - Interactive Configuration

```bash
python -m src.main setup [OPTIONS]
```

**Options:**

- `--provider, -p`: Provider to set up (meta/google/both)
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

# Application Configuration
OUTPUT_DIR=./invoices
LOG_LEVEL=INFO
MAX_RETRIES=3
RETRY_DELAY=1.0
TIMEOUT_SECONDS=30
DEBUG=false
```

### Folder Structure

Invoices are organized using a configurable folder structure. The default structure is:

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
│   └── download_service.py # PDF download service
├── commands/
│   ├── fetch.py         # Fetch command implementation
│   └── status.py        # Status command implementation
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

3. **"No invoices found"**
   - Ensure accounts have monthly invoicing enabled (required for both providers)
   - Check that the date range contains billing periods
   - Verify business setup meets API requirements

4. **Download failures**
   - Check internet connectivity and API rate limits
   - Verify download URLs are accessible
   - Check disk space and file permissions

### Debug Mode

Enable debug mode for detailed logging:

```bash
python -m src.main fetch --debug
```

This provides comprehensive logging including:

- API request/response details
- Retry attempts and backoff timing
- File operation details
- Configuration validation steps

## Security Considerations

- **Never commit `.env` files** to version control
- **Use environment variables** for all sensitive configuration
- **Implement proper access controls** for downloaded invoices
- **Regularly rotate API tokens** according to provider recommendations
- **Monitor API usage** to detect unauthorized access

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
