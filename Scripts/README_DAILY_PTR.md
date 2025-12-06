# Daily PTR Checker System

## Overview

This system automatically checks for new House of Representatives Periodic Transaction Reports (PTRs) and processes them into a Supabase database. It scrapes the House disclosure website, extracts transaction data using LLM processing, and uploads the results to your database.

## Components

### 1. `house_ptr_scraper.py`

- Scrapes the House disclosure website for PTR filings
- Uses Selenium for web automation
- Filters for PTR documents only
- Saves scraped filing metadata

### 2. `ptr_pdf_processor.py`

- Downloads PDF files from filing URLs
- Extracts text from PDFs using PyMuPDF
- Uses OpenRouter LLM API to extract structured transaction data
- Parses LLM responses into transaction records

### 3. `supabase_db_processor.py`

- Manages database operations with Supabase
- Creates/updates members, assets, filings, and transactions
- Handles deduplication and caching
- Provides database statistics

### 4. `daily_ptr_checker.py`

- Main orchestrator script
- Coordinates the entire pipeline
- Tracks processing state
- Generates reports
- Handles batch processing

### 5. `schedule_daily_check.py`

- Scheduler for automated daily runs
- Can run as a service or cron job
- Configurable check times
- Logging and error handling

## Installation

### Prerequisites

- Python 3.8 or higher
- Chrome browser installed
- ChromeDriver (for Selenium)

### Setup Steps

1. **Install Python dependencies:**

```bash
cd Scripts
pip install -r requirements.txt
```

2. **Install ChromeDriver:**

```bash
# On Linux/Mac with wget
wget https://chromedriver.storage.googleapis.com/LATEST_RELEASE
wget https://chromedriver.storage.googleapis.com/$(cat LATEST_RELEASE)/chromedriver_linux64.zip
unzip chromedriver_linux64.zip

# Or download manually from: https://chromedriver.chromium.org/
```

3. **Configure environment variables:**
   Create a `.env` file in the Scripts directory:

```env
# OpenRouter API Key for LLM processing
OPENROUTER_API_KEY=your_openrouter_api_key_here

# Supabase Configuration
SUPABASE_URL=your_supabase_url_here
SUPABASE_KEY=your_supabase_anon_key_here

# Optional: Direct database connection
DATABASE_URL=your_database_url_here
```

## Usage

### Manual Run

Run the daily checker manually:

```bash
# Check current year
python daily_ptr_checker.py

# Check specific year
python daily_ptr_checker.py --year 2024

# Force process all filings (ignore existing records)
python daily_ptr_checker.py --force-all

# Custom batch size
python daily_ptr_checker.py --batch-size 5
```

### Scheduled Runs

#### Option 1: Python Scheduler

Run continuously with built-in scheduler:

```bash
# Run daily at 9:00 AM
python schedule_daily_check.py --time 09:00

# Run immediately on startup then daily
python schedule_daily_check.py --run-now

# Run once (for cron/systemd)
python schedule_daily_check.py --once
```

#### Option 2: Cron Job

Add to crontab for daily execution:

```bash
# Edit crontab
crontab -e

# Add daily run at 9 AM
0 9 * * * cd /path/to/Scripts && python schedule_daily_check.py --once
```

#### Option 3: Systemd Service

Create a systemd service for Linux systems:

```ini
[Unit]
Description=Daily PTR Checker Service
After=network.target

[Service]
Type=simple
User=your_user
WorkingDirectory=/path/to/Scripts
ExecStart=/usr/bin/python3 /path/to/Scripts/schedule_daily_check.py
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

## Output Files

The system generates several output files:

- `daily_ptr_checker_YYYYMMDD.log` - Daily execution logs
- `daily_ptr_report_YYYYMMDD_HHMMSS.txt` - Summary reports
- `house_scraped_filings.json` - Scraped filing metadata
- `extracted_transactions.json` - Extracted transaction data
- `processed_doc_ids.json` - Tracking of processed documents
- `daily_checker_state.json` - System state persistence

## Database Schema

The system works with the following Supabase tables:

### Members

- `member_id` (primary key)
- `name` (unique)
- `chamber` (House/Senate)
- `party`
- `state`

### Filings

- `filing_id` (primary key)
- `member_id` (foreign key)
- `doc_id` (unique)
- `url`
- `filing_date`
- `verified`

### Assets

- `asset_id` (primary key)
- `ticker`
- `company_name`
- `ticker_clean`
- `company_clean`

### Transactions

- `transaction_id` (primary key)
- `filing_id` (foreign key)
- `asset_id` (foreign key)
- `transaction_type` (Purchase/Sale)
- `transaction_date`
- `amount_range_low`
- `amount_range_high`
- `owner_code`

## Monitoring

### Check Logs

```bash
# View today's log
tail -f daily_ptr_checker_$(date +%Y%m%d).log

# View scheduler log
tail -f schedule_daily_check.log
```

### Database Statistics

The system reports database statistics after each run:

- Total members
- Total filings
- Total transactions
- Total assets

### Error Handling

- Failed PDF downloads are logged and skipped
- LLM API errors trigger retries with exponential backoff
- Database errors are logged but don't stop processing
- Each batch is processed independently

## Troubleshooting

### Common Issues

1. **Selenium errors:**

   - Ensure ChromeDriver is installed and in PATH
   - Check Chrome browser is installed
   - Try running with `headless=False` for debugging

2. **LLM API errors:**

   - Verify OPENROUTER_API_KEY is set correctly
   - Check API credit balance
   - Monitor rate limits

3. **Database errors:**

   - Verify Supabase credentials
   - Check network connectivity
   - Ensure tables exist with correct schema

4. **PDF processing errors:**
   - Some PDFs may be scanned images (OCR not implemented)
   - Check PyMuPDF installation
   - Monitor disk space for downloads

## API Rate Limits

The system implements rate limiting:

- 2-second delay between LLM API calls
- 5-second pause between processing batches
- Exponential backoff on rate limit errors

## Security Notes

- Store API keys in `.env` file (never commit to git)
- Use read-only database keys where possible
- Implement IP whitelisting on Supabase
- Monitor API usage and costs

## Future Enhancements

Potential improvements:

- Add Senate PTR scraping
- Implement OCR for scanned PDFs
- Add email notifications for new filings
- Create web dashboard for monitoring
- Implement data validation and quality checks
- Add support for amendments and corrections

## Support

For issues or questions:

1. Check the logs for error messages
2. Verify all dependencies are installed
3. Ensure environment variables are set
4. Test each component individually

## License

This system is provided as-is for educational and research purposes.
