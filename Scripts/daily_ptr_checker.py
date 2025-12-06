"""
Daily PTR Pipeline Orchestrator

Steps:
1) Scrape House Financial Disclosure site for PTR filings for a given year
2) Compare against existing `Filings.doc_id` in Supabase to find new filings
3) For each new filing, process the PDF and extract transactions (LLM-backed)
4) Store members, assets, filings, and transactions into Supabase

Usage:
  python daily_ptr_checker.py --year 2025 --limit 5 --headless true

Environment:
  Reads credentials from Scripts/.env via submodules
"""

import os
import sys
import json
import logging
import argparse
from datetime import datetime
from typing import List, Dict, Tuple

# Senate integration imports
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SENATE_DIR = os.path.join(SCRIPT_DIR, 'Senate Script')
if SENATE_DIR not in sys.path:
    sys.path.insert(0, SENATE_DIR)

try:
    import combined_scraper as senate_scraper
    import scanToTextLLM as senate_llm
    from combined_scraper import verify_session, extract_text_from_page, determine_document_type
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options as ChromeOptions
    from selenium.webdriver.chrome.service import Service as ChromeService
    from webdriver_manager.chrome import ChromeDriverManager
except Exception:
    senate_scraper = None
    senate_llm = None

# Local imports
from house_ptr_scraper import HouseDisclosureScraper
from ptr_pdf_processor import process_ptr_pdf
from supabase_db_processor import SupabaseDBProcessor

# Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def build_arg_parser() -> argparse.ArgumentParser:
	parser = argparse.ArgumentParser(description="Run the daily PTR pipeline (House + Senate)")
	parser.add_argument("--year", type=int, default=datetime.now().year, help="Filing year to scrape")
	parser.add_argument("--headless", type=str, default="true", choices=["true", "false"], help="Run Chrome headless")
	parser.add_argument("--limit", type=int, default=10, help="Max number of new filings to process this run")
	parser.add_argument("--max-pages", type=int, default=0, help="Optional cap on pages to scan (0 = all)")
	parser.add_argument("--dry-run", action="store_true", help="Scrape and parse but skip DB writes")
	parser.add_argument("--save-scrape-json", action="store_true", help="Save scraped filings JSON to disk")
	parser.add_argument("--house", type=str, default="true", choices=["true", "false"], help="Include House pipeline")
	parser.add_argument("--senate", type=str, default="true", choices=["true", "false"], help="Include Senate pipeline")
	return parser


def scrape_ptrs(year: int, headless: bool, max_pages: int) -> List[Dict]:
	logger.info(f"Starting scrape for year={year}, headless={headless}, max_pages={'ALL' if max_pages <= 0 else max_pages}")
	scraper = HouseDisclosureScraper(headless=headless)
	filings = scraper.scrape_ptr_filings(
		year=year,
		max_pages=None if max_pages <= 0 else max_pages,
		find_first_ptr=False,
	)
	if filings:
		logger.info(f"Scrape complete: {len(filings)} filings found")
	else:
		logger.warning("Scrape returned no filings")
	return filings


def senate_scrape_links(max_pages: int) -> List[Tuple[str, str, str]]:
	"""Scrape Senate PTR links using existing Senate scraper, returning (doc_id, url, member_name) tuples."""
	if senate_scraper is None:
		logger.warning("Senate scraper not available; skipping Senate scrape")
		return []
	try:
		links = senate_scraper.scrape_all_ptr_links(force_rescrape=False, db_path=":memory:")
		# Normalize
		normalized: List[Tuple[str, str, str]] = []
		for item in links:
			if isinstance(item, tuple) and len(item) == 3:
				normalized.append(item)
			elif isinstance(item, dict):
				normalized.append((item.get('doc_id'), item.get('url'), item.get('member_name')))
		return normalized
	except Exception as e:
		logger.error(f"Senate scraping failed: {e}")
		return []


def senate_links_to_transactions(links: List[Tuple[str, str, str]], headless: bool, max_count: int) -> List[Dict]:
	"""Process Senate links by extracting text with Selenium and parsing via LLM."""
	if senate_llm is None or verify_session is None or extract_text_from_page is None:
		logger.warning("Senate helpers not available; skipping Senate processing")
		return []
	transactions: List[Dict] = []
	# Setup headless Chrome
	chrome_options = ChromeOptions()
	if headless:
		chrome_options.add_argument("--headless=new")
	chrome_options.add_argument("--no-sandbox")
	chrome_options.add_argument("--disable-dev-shm-usage")
	chrome_options.add_argument("--disable-gpu")
	chrome_options.add_argument("--window-size=1920,1080")
	service = ChromeService(ChromeDriverManager().install())
	driver = webdriver.Chrome(service=service, options=chrome_options)
	try:
		# Verify session once
		verify_session(driver, 'https://efdsearch.senate.gov/search/')
		count = 0
		for doc_id, url, member_name in links:
			if not doc_id or not url:
				continue
			if 0 < max_count <= count:
				break
			count += 1
			try:
				driver.get(url)
				text = extract_text_from_page(driver, doc_id)
				if not text.strip():
					logger.info(f"Senate {doc_id}: no text extracted")
					continue
				csv_text = senate_llm.call_llm_api_with_text(text, {'DocID': doc_id, 'Name': member_name, 'URL': url})
				parsed = senate_llm.parse_llm_transactions(csv_text or '', {'DocID': doc_id})
				for t in parsed:
					transactions.append({
						'doc_id': doc_id,
						'member_name': member_name,
						'office': 'Senate',
						'pdf_url': url,
						'ticker': t.get('ticker'),
						'asset_name': t.get('company_name'),
						'transaction_type': t.get('transaction_type_full'),
						'transaction_date': t.get('transaction_date_str'),
						'amount_low': t.get('amount_low'),
						'amount_high': t.get('amount_high'),
						'owner': t.get('owner_code'),
						'comment': t.get('raw_llm_line', '')
					})
				logger.info(f"Senate {doc_id}: extracted {len(parsed)} transaction(s)")
			except Exception as e:
				logger.error(f"Senate {doc_id}: processing failed: {e}")
				continue
	finally:
		driver.quit()
	return transactions


def filter_new_filings(filings: List[Dict], existing_doc_ids: set, limit: int) -> List[Dict]:
	new_filings: List[Dict] = []
	for f in filings:
		doc_id = f.get("doc_id")
		if not doc_id:
			continue
		if doc_id not in existing_doc_ids:
			new_filings.append(f)
			if 0 < limit <= len(new_filings):
				break
	logger.info(f"Filtered new filings: {len(new_filings)} (from {len(filings)} total scraped)")
	return new_filings


def process_filings_to_transactions(new_filings: List[Dict]) -> List[Dict]:
	"""Process each filing PDF, returning flattened transaction records with filing metadata."""
	all_transactions: List[Dict] = []
	for idx, filing in enumerate(new_filings, start=1):
		doc_id = filing.get("doc_id")
		pdf_url = filing.get("pdf_url")
		member_name = filing.get("member_name")
		office = filing.get("office")
		logger.info(f"[{idx}/{len(new_filings)}] Processing filing doc_id={doc_id} member={member_name}")
		try:
			processed = process_ptr_pdf(pdf_url, doc_id) or {}
			transactions = processed.get("transactions", [])
			for t in transactions:
				# Augment transaction with filing metadata expected by DB processor
				tx = dict(t)
				tx["doc_id"] = doc_id
				tx["member_name"] = member_name
				tx["office"] = office
				tx["pdf_url"] = pdf_url
				all_transactions.append(tx)
			logger.info(f"doc_id={doc_id}: extracted {len(transactions)} transaction(s)")
		except Exception as e:
			logger.error(f"Failed processing doc_id={doc_id}: {e}")
	return all_transactions


def persist_transactions(transactions: List[Dict], dry_run: bool) -> Dict:
	if dry_run:
		logger.info("Dry-run enabled: skipping DB writes. Preview of first transaction (if any):")
		if transactions:
			logger.info(json.dumps(transactions[0], indent=2))
		return {"dry_run": True, "transactions": len(transactions)}

	db = SupabaseDBProcessor()
	stats = db.process_transactions_batch(transactions)
	return stats


def main():
	parser = build_arg_parser()
	args = parser.parse_args()

	headless = args.headless.lower() == "true"
	year = args.year
	limit = max(0, args.limit)
	max_pages = int(args.max_pages)
	dry_run = args.dry_run
	include_house = args.house.lower() == 'true'
	include_senate = args.senate.lower() == 'true'

	all_transactions: List[Dict] = []

	# 1) Scrape House (optional)
	filings: List[Dict] = []
	if include_house:
		filings = scrape_ptrs(year=year, headless=headless, max_pages=max_pages)
		if args.save_scrape_json:
			out_path = os.path.join(os.path.dirname(__file__), f"house_scraped_filings_{year}.json")
			with open(out_path, "w") as f:
				json.dump({"year": year, "filings": filings, "scraped_at": datetime.now().isoformat()}, f, indent=2)
			logger.info(f"Saved scraped filings JSON to {out_path}")

	# 2) Fetch existing doc_ids
	try:
		db = SupabaseDBProcessor()
		existing_doc_ids = db.get_existing_doc_ids()
	except Exception as e:
		logger.error(f"Database initialization failed: {e}")
		return

	# 3) House processing
	if include_house and filings:
		new_filings = filter_new_filings(filings, existing_doc_ids, limit)
		if new_filings:
			house_transactions = process_filings_to_transactions(new_filings)
			all_transactions.extend(house_transactions)
		else:
			logger.info("No new House filings to process.")

	# 4) Senate processing
	if include_senate and senate_scraper is not None and senate_llm is not None:
		s_links = senate_scrape_links(max_pages=max_pages)
		if s_links:
			# Filter against existing doc_ids and apply limit remaining
			s_links = [(d,u,m) for (d,u,m) in s_links if d and d not in existing_doc_ids]
			remaining = max(0, limit - len(all_transactions)) if limit > 0 else 0
			max_count = remaining if include_house and remaining > 0 else (limit if limit > 0 else 0)
			senate_transactions = senate_links_to_transactions(s_links, headless=headless, max_count=max_count)
			all_transactions.extend(senate_transactions)
		else:
			logger.info("No Senate links scraped.")

	if not all_transactions:
		logger.info("No transactions extracted - exiting.")
		return

	# 5) Persist combined
	stats = persist_transactions(all_transactions, dry_run=dry_run)
	logger.info(f"Pipeline complete. Summary: {json.dumps(stats, indent=2)}")


if __name__ == "__main__":
	main()
