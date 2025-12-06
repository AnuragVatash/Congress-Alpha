import re
import requests
import os
import json
import datetime
import base64
import time
from io import BytesIO
import logging # Added for better logging
import csv
from io import StringIO
import fitz
from rate_limiter import rate_limited_api_call
from db_processor import get_db_connection, get_existing_doc_ids

# Configure basic logging if not already configured at a higher level
# If your main script configures logging, this might be redundant or could be adjusted.
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s')

from dotenv import load_dotenv

# Prefer Scripts/.env if available, fallback to secrets.json
scripts_env = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env')
if os.path.exists(scripts_env):
    load_dotenv(scripts_env)

api_key = os.getenv('OPENROUTER_API_KEY')
if not api_key:
    # Get the absolute path to secrets.json
    secrets_path = os.path.join(os.path.dirname(__file__), "gitignore", "secrets.json")
    try:
        with open(secrets_path) as f:
            secrets = json.load(f)
        api_key = secrets.get("OPENROUTER_API_KEY")
        if not api_key:
            logging.warning(f"OPENROUTER_API_KEY not found in env or {secrets_path}. LLM will be skipped.")
    except FileNotFoundError:
        logging.warning(f"Secrets file not found at {secrets_path}. LLM will be skipped.")
    except json.JSONDecodeError:
        logging.warning(f"Could not decode JSON from {secrets_path}. LLM will be skipped.")


# OpenRouter API endpoint
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"

# Track documents where text extraction fails
text_extraction_failures = set()

# Track documents where API response was cut off due to length
length_limit_failures = set()

# Track generation IDs for each document
generation_ids = {}

def save_text_extraction_failures():
    """Save text extraction failures to a JSON file."""
    try:
        filepath = os.path.join(os.path.dirname(__file__), 'text_extraction_failures.json')
        with open(filepath, 'w') as f:
            json.dump(list(text_extraction_failures), f)
        logging.info(f"Saved {len(text_extraction_failures)} HOR text extraction failures")
    except Exception as e:
        logging.error(f"Error saving text extraction failures: {e}")

def load_text_extraction_failures():
    """Load text extraction failures from JSON file."""
    global text_extraction_failures
    try:
        filepath = os.path.join(os.path.dirname(__file__), 'text_extraction_failures.json')
        with open(filepath, 'r') as f:
            text_extraction_failures = set(json.load(f))
        logging.info(f"Loaded {len(text_extraction_failures)} HOR text extraction failures")
    except FileNotFoundError:
        logging.info("No existing HOR text extraction failures file found")
    except Exception as e:
        logging.error(f"Error loading text extraction failures: {e}")

def save_generation_ids():
    """Save generation IDs to a JSON file."""
    try:
        filepath = os.path.join(os.path.dirname(__file__), 'generation_ids.json')
        with open(filepath, 'w') as f:
            json.dump(generation_ids, f)
        logging.info(f"Saved {len(generation_ids)} HOR generation IDs")
    except Exception as e:
        logging.error(f"Error saving generation IDs: {e}")

def load_generation_ids():
    """Load generation IDs from JSON file."""
    global generation_ids
    try:
        filepath = os.path.join(os.path.dirname(__file__), 'generation_ids.json')
        with open(filepath, 'r') as f:
            generation_ids = json.load(f)
        logging.info(f"Loaded {len(generation_ids)} HOR generation IDs")
    except FileNotFoundError:
        logging.info("No existing HOR generation IDs file found")
    except Exception as e:
        logging.error(f"Error loading generation IDs: {e}")

def save_length_limit_failures():
    """Save length limit failures to a JSON file."""
    try:
        filepath = os.path.join(os.path.dirname(__file__), 'length_limit_failures.json')
        with open(filepath, 'w') as f:
            json.dump(list(length_limit_failures), f)
        logging.info(f"Saved {len(length_limit_failures)} HOR length limit failures")
    except Exception as e:
        logging.error(f"Error saving length limit failures: {e}")

def load_length_limit_failures():
    """Load length limit failures from JSON file."""
    global length_limit_failures
    try:
        filepath = os.path.join(os.path.dirname(__file__), 'length_limit_failures.json')
        with open(filepath, 'r') as f:
            length_limit_failures = set(json.load(f))
        logging.info(f"Loaded {len(length_limit_failures)} HOR length limit failures")
    except FileNotFoundError:
        logging.info("No existing HOR length limit failures file found")
    except Exception as e:
        logging.error(f"Error loading length limit failures: {e}")

# Load all tracking data on startup
load_generation_ids()
load_text_extraction_failures()
load_length_limit_failures()

def parse_amount_range(amount_range_str):
    if not amount_range_str:
        return None, None
    
    # If amount_range_str is a list, join it back together
    if isinstance(amount_range_str, list):
        amount_range_str = ''.join(amount_range_str)
    
    # First split on the dash
    if '-' in amount_range_str:
        parts = amount_range_str.split('-')
        if len(parts) == 2:
            try:
                # Clean up each part separately
                low_str = parts[0].replace('$', '').replace(' ', '').replace(',', '')
                high_str = parts[1].replace('$', '').replace(' ', '').replace(',', '')
                low = int(low_str)
                high = int(high_str)
                return low, high
            except ValueError:
                pass
    
    # Handle "Over" case
    m = re.match(r'Over\s*([\d,]+)', amount_range_str, re.IGNORECASE)
    if m:
        try:
            low = int(m.group(1).replace(',', ''))
            return low, None
        except ValueError:
            pass
    
    # Handle single value
    try:
        cleaned = amount_range_str.replace('$', '').replace(' ', '').replace(',', '')
        val = int(cleaned)
        return val, val
    except ValueError:
        pass
    
    return None, None

def parse_llm_transactions(text: str, member_data: dict) -> list:
    """
    Parses the structured text (expected CSV format) returned by the LLM.
    Args:
        text (str): The text output from the LLM.
        member_data (dict): Metadata about the filer (mainly for DocID logging).
    Returns:
        list: A list of transaction dictionaries, structured for db_processor.py.
    """
    doc_id = member_data.get('DocID', 'Unknown DocID')
    
    # Check for special cases first
    text = text.strip()
    if text == "NO_TRANSACTIONS_FOUND":
        logging.info(f"[{doc_id}] LLM reported no transactions found in document")
        return []
    elif text == "DOCUMENT_UNREADABLE":
        logging.warning(f"[{doc_id}] LLM reported document is unreadable")
        return []
    elif text == "NO_TEXT_FOUND":
        logging.warning(f"[{doc_id}] LLM reported no text could be extracted from document")
        return []
    
    transactions = []
    # Filter out potential introductory lines or Markdown fences
    lines = [line for line in text.strip().split("\n") if line.strip() and not line.strip().startswith("```")]

    logging.info(f"[{doc_id}] Parsing {len(lines)} lines from LLM output using CSV reader.")

    for i, line_content in enumerate(lines):
        original_line_for_logging = line_content
        try:
            # Clean up the line by removing [ST] and other bracketed content
            cleaned_line = re.sub(r'\s*\[[^\]]+\]\s*', ' ', line_content)
            
            # Use Python's built-in CSV reader which handles quoted fields
            csv_file_like_object = StringIO(cleaned_line)
            reader = csv.reader(csv_file_like_object, quotechar='"', delimiter=',', skipinitialspace=True)
            parts = next(reader)  # Read the single line

            # Skip lines that are clearly not transaction data
            if len(parts) < 5 or any(part.lower().startswith(('there are no', 'i am unable', 'no transaction')) for part in parts):
                continue

            # Extract the core fields we need
            owner_code = parts[0].strip() if len(parts) > 0 else ""
            
            # Combine all parts between owner_code and transaction type as asset description
            asset_description_raw = ""
            transaction_type_code = ""
            transaction_date_str = ""
            notification_date_str = ""
            amount_range_str = ""
            
            # Find the transaction type (P, S, or E)
            for j, part in enumerate(parts[1:], 1):
                if part.strip().upper() in ['P', 'S', 'E']:
                    transaction_type_code = part.strip().upper()
                    # Everything before this is asset description
                    asset_description_raw = ','.join(parts[1:j]).strip()
                    # Everything after this should be dates and amount
                    remaining_parts = parts[j+1:]
                    if len(remaining_parts) >= 3:
                        transaction_date_str = remaining_parts[0].strip()
                        notification_date_str = remaining_parts[1].strip()
                        # Join all remaining parts for amount range
                        amount_range_str = ''.join(remaining_parts[2:]).strip()
                    break

            if not transaction_type_code:
                logging.warning(f"[{doc_id}] Could not find transaction type in line: {original_line_for_logging}")
                continue

            # 1. Parse Asset Description (Company Name and Ticker)
            ticker_match = re.search(r'\(([^)]+)\)$', asset_description_raw)
            ticker = None
            company_name = asset_description_raw.strip()

            if ticker_match:
                potential_ticker = ticker_match.group(1).strip()
                if re.fullmatch(r'[A-Z0-9\.]+', potential_ticker):
                    ticker = potential_ticker
                    company_name = asset_description_raw[:ticker_match.start()].strip()
                else:
                    logging.debug(f"[{doc_id}] Text in parentheses '{potential_ticker}' not treated as ticker for: {asset_description_raw}")
            else:
                last_word_match = re.search(r'\s([A-Z0-9\.]{1,5})$', asset_description_raw)
                if last_word_match:
                    potential_ticker_last_word = last_word_match.group(1).strip()
                    if re.fullmatch(r'[A-Z0-9\.]+', potential_ticker_last_word) and len(potential_ticker_last_word) <= 5:
                        ticker = potential_ticker_last_word
                        company_name = asset_description_raw[:last_word_match.start()].strip()

            if not company_name:
                logging.warning(f"[{doc_id}] Could not determine company name from '{asset_description_raw}' in line: {original_line_for_logging}. Using raw description.")
                company_name = asset_description_raw

            # 2. Map Transaction Type Code
            transaction_type_code_upper = transaction_type_code.upper()
            # Clean up transaction type by removing (partial) and any other parenthetical content
            transaction_type_code_cleaned = re.sub(r'\s*\([^)]*\)', '', transaction_type_code_upper).strip()
            if transaction_type_code_cleaned == 'P':
                transaction_type_full = 'Purchase'
            elif transaction_type_code_cleaned == 'S':
                transaction_type_full = 'Sale'
            elif transaction_type_code_cleaned == 'E':
                transaction_type_full = 'Exchange'
            else:
                transaction_type_full = "Unknown"
                logging.warning(f"[{doc_id}] Unknown transaction type code '{transaction_type_code}' (cleaned: '{transaction_type_code_cleaned}') in line: {original_line_for_logging}")

            # 3. Parse Amount Range
            amount_low = None
            amount_high = None
            amount_low, amount_high = parse_amount_range(amount_range_str)

            # 4. Basic Date Validation
            if not re.match(r'\d{1,2}[/-]\d{1,2}[/-]\d{2,4}', transaction_date_str):
                logging.warning(f"[{doc_id}] Invalid transaction date format '{transaction_date_str}' in line: {original_line_for_logging}")
            if not re.match(r'\d{1,2}[/-]\d{1,2}[/-]\d{2,4}', notification_date_str):
                logging.warning(f"[{doc_id}] Invalid notification date format '{notification_date_str}' in line: {original_line_for_logging}")

            transaction_data = {
                "owner_code": owner_code,
                "company_name": company_name,
                "ticker": ticker,
                "transaction_type_full": transaction_type_full,
                "transaction_date_str": transaction_date_str,
                "notification_date_str": notification_date_str,
                "amount_low": amount_low,
                "amount_high": amount_high,
                "raw_llm_line": original_line_for_logging
            }
            transactions.append(transaction_data)

        except csv.Error as e:
            logging.error(f"[{doc_id}] CSV parsing error on line {i+1}: '{original_line_for_logging}'. Error: {e}")
            error_filepath = os.path.join(os.path.dirname(__file__), "hor_llm_parse_errors.txt")
            with open(error_filepath, "a", encoding="utf-8") as f_err:
                f_err.write(f"--- CSV Error parsing at {datetime.datetime.now()} for DocID: {doc_id} ---\n")
                f_err.write(f"Line: {original_line_for_logging}\n")
                f_err.write(f"Error: {e}\n")
                f_err.write("---\n")
        except Exception as e:
            logging.error(f"[{doc_id}] General error parsing LLM output line {i+1}: '{original_line_for_logging}'. Error: {e}", exc_info=True)
            error_filepath = os.path.join(os.path.dirname(__file__), "hor_llm_parse_errors.txt")
            with open(error_filepath, "a", encoding="utf-8") as f_err:
                f_err.write(f"--- General Error parsing at {datetime.datetime.now()} for DocID: {doc_id} ---\n")
                f_err.write(f"Line: {original_line_for_logging}\n")
                f_err.write(f"Error: {e}\n")
                f_err.write("---\n")

    logging.info(f"[{doc_id}] Successfully parsed {len(transactions)} transactions from LLM output.")
    return transactions


# Function to call OpenRouter API with the entire PDF
def scan_with_openrouter(pdf_url: str, member_data: dict):
    """
    Extracts raw text from PDF and uses OpenRouter to convert to CSV format.
    If text extraction fails, the document ID is tracked and returns NO_TEXT_FOUND.
    Args:
        pdf_url (str): The URL of the PDF file or a BytesIO object containing the PDF content.
        member_data (dict): Metadata about the filer.
    Returns:
        str: The raw LLM output containing CSV formatted transactions or error message.
    """
    if not api_key:
        logging.warning("Skipping OpenRouter: API key not available.")
        return "NO_TRANSACTIONS_FOUND"

    doc_id = member_data.get('DocID', 'Unknown DocID')
    llm_output = ""
    pdf_link = pdf_url if isinstance(pdf_url, str) else "BytesIO object"
    
    # Create filing record first if it doesn't exist
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Check if filing exists
        cursor.execute('SELECT filing_id FROM Filings WHERE doc_id = ?', (doc_id,))
        result = cursor.fetchone()
        filing_id = result[0] if result else None
        
        if not filing_id:
            logging.info(f"[{doc_id}] Creating filing record for API request tracking")
            # Get member name from member_data
            first_name = member_data.get('First', '')
            last_name = member_data.get('Last', '')
            member_name = f"{first_name} {last_name}".strip() if first_name or last_name else member_data.get('Officename', '').strip()
            
            if not member_name:
                member_name = "Unknown Member"
            
            # Create member record
            cursor.execute("INSERT INTO Members (name) VALUES (?)", (member_name,))
            member_id = cursor.lastrowid
            
            # Create filing record
            cursor.execute("""
                INSERT INTO Filings (member_id, doc_id, url, filing_date)
                VALUES (?, ?, ?, ?)
            """, (member_id, doc_id, pdf_link, None))
            filing_id = cursor.lastrowid
            conn.commit()
            logging.info(f"[{doc_id}] Created filing record with ID: {filing_id}")
    except Exception as e:
        logging.error(f"[{doc_id}] Error creating filing record: {e}", exc_info=True)
    finally:
        if 'conn' in locals():
            conn.close()

    try:
        # Handle both URL and BytesIO input
        if isinstance(pdf_url, str):
            # Download PDF content from URL
            response = requests.get(pdf_url, stream=True)
            response.raise_for_status()
            pdf_content = BytesIO(response.content)
        else:
            # Assume it's already a BytesIO object
            pdf_content = pdf_url

        # Open PDF with PyMuPDF
        doc = fitz.open("pdf", pdf_content.read())
        
        # Extract raw text from all pages
        raw_text = ""
        for page_num in range(len(doc)):
            page = doc[page_num]
            page_text = page.get_text()
            if page_text.strip():
                raw_text += page_text + "\n"

        # Check if we successfully extracted text
        if not raw_text.strip():
            logging.warning(f"[{doc_id}] No text could be extracted from PDF. Adding to text extraction failures.")
            text_extraction_failures.add(doc_id)
            save_text_extraction_failures()  # Save the updated set of failures
            
            # Store text extraction failure in API_Requests
            try:
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute('SELECT filing_id FROM Filings WHERE doc_id = ?', (doc_id,))
                result = cursor.fetchone()
                filing_id = result[0] if result else None
                
                if filing_id:
                    logging.info(f"[{doc_id}] Storing text extraction failure in API_Requests")
                    cursor.execute('''
                        INSERT INTO API_Requests (
                            filing_id, doc_id, model, max_tokens,
                            text_length, approx_tokens, response_status, error_message,
                            pdf_link, raw_text, llm_response
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        filing_id, doc_id, "text_extraction_failure",
                        0, 0, 0, 0, "No text could be extracted from PDF",
                        pdf_link, "", "NO_TEXT_FOUND"
                    ))
                    conn.commit()
                    logging.info(f"[{doc_id}] Successfully stored text extraction failure")
                else:
                    logging.warning(f"[{doc_id}] No filing_id found for text extraction failure")
            except Exception as e:
                logging.error(f"[{doc_id}] Error storing text extraction failure: {e}", exc_info=True)
            finally:
                if 'conn' in locals():
                    conn.close()
                    
            return "NO_TEXT_FOUND"

        logging.info(f"[{doc_id}] Successfully extracted text from PDF, sending text to OpenRouter.")
        
        # Calculate approximate token count (4 characters per token)
        text_length = len(raw_text)
        approx_tokens = text_length // 4
        
        # Set max_tokens based on text length
        # Base limit is 4096 tokens, double it for longer documents
        max_tokens = 8192 if text_length > 25000 else 4096
        
        logging.info(f"[{doc_id}] Text length: {text_length} characters, approx {approx_tokens} tokens. Setting max_tokens to {max_tokens}")
        
        # Prepare prompt for OpenRouter to convert raw text to CSV
        system_instruction = """You are an expert data extraction assistant. Your task is to meticulously analyze financial disclosure document text and extract specific transaction details. Adhere strictly to the formatting and rules provided."""
        
        static_prompt = """**Task Objective:**
Identify and extract all financial transactions from the provided text. Format each transaction as a single line in a CSV (Comma Separated Values) structure.

**CSV Output Format (Strict Order - 6 Columns):**
1.  **Owner Code:** (e.g., SP, DC, JT, or leave blank if not specified for the filer themselves). This code indicates the owner of the asset.
2.  **Asset Description:** The full name of the asset, including any ticker symbol found in parentheses (e.g., Microsoft Corporation (MSFT), Some Bond Fund). If a ticker is present, include it.
3.  **Transaction Type Code:** A single letter: 'P' for Purchase, 'S' for Sale, or 'E' for Exchange.
4.  **Transaction Date:** The date the transaction occurred, formatted as MM/DD/YYYY.
5.  **Notification Date:** The date the transaction was reported or notified, formatted as MM/DD/YYYY.
6.  **Amount Range:** The transaction value range (e.g., $1,001 - $15,000, $50,000, Over $1,000,000).

**Critical Processing Rules - Adhere Strictly:**
*   **Rule 1: Literal Extraction:** Only extract transaction data that is explicitly and clearly visible in the text. Do NOT infer, guess, or create data not present.
*   **Rule 2: Column Integrity:** Ensure each CSV row has exactly 6 comma-separated values corresponding to the columns above.
*   **Rule 3: Ticker Inclusion:** If a ticker symbol (e.g., MSFT, AAPL) is part of the asset description in the text, include it within parentheses at the end of the Asset Description field.
*   **Rule 4: Date Format:** All dates MUST be in MM/DD/YYYY format. If a date is in a different format in the text, attempt to convert it. If conversion is not possible or the date is unclear, you may have to omit the transaction.
*   **Rule 5: Blank Owner Code:** If the owner is the filer and no specific code (SP, DC, JT) is shown for a transaction, leave the 'Owner Code' field blank (i.e., ``,Asset Description,...`).
*   **Rule 6: Handling Commas within Fields:** If an 'Asset Description' or 'Amount Range' naturally contains a comma, enclose that entire field in double quotes. For example: `SP,"Big Company, LLC (BCLLC)",P,01/01/2024,01/05/2024,"$1,001,000 - $5,000,000"`
*   **Rule 7: No Transactions Found:** If, after careful analysis of the text, you find NO discernible financial transactions, your entire output should be the single line: `NO_TRANSACTIONS_FOUND`
*   **Rule 8: Unclear/Corrupted Data:** If the text is too unclear or appears corrupted, output the single line: `DOCUMENT_UNREADABLE`
*   **Rule 9: No Extra Text:** Your final output should ONLY be the CSV data lines, or one of the special strings (`NO_TRANSACTIONS_FOUND`, `DOCUMENT_UNREADABLE`). Do not include any headers, explanations, introductions, or summaries.

Text to process:
"""
        static_prompt += raw_text

        payload = {
            "model": "google/gemini-2.0-flash-001",
            "messages": [
                {
                    "role": "system",
                    "content": system_instruction
                },
                {
                    "role": "user",
                    "content": static_prompt
                }
            ],
            "max_tokens": max_tokens,
            "temperature": 0.1,
            "provider": {
                "only": ["Google AI Studio"]
            }
        }

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "http://localhost:3000",
            "X-Title": "HOR Committee Financial Disclosures Scraper"
        }

        logging.info(f"[{doc_id}] Sending to OpenRouter API with max_tokens={max_tokens}...")
        
        try:
            # Use rate-limited API call
            response = rate_limited_api_call(
                OPENROUTER_API_URL,
                headers=headers,
                json=payload,
                timeout=60
            )

            # Get filing_id from database
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute('SELECT filing_id FROM Filings WHERE doc_id = ?', (doc_id,))
            result = cursor.fetchone()
            filing_id = result[0] if result else None

            if response.status_code == 200:
                response_data = response.json()
                if "choices" in response_data and len(response_data["choices"]) > 0:
                    choice = response_data["choices"][0]
                    csv_text = choice["message"]["content"]
                    
                    # Store the generation ID
                    generation_id = response_data.get("id")
                    if generation_id:
                        generation_ids[doc_id] = generation_id
                        save_generation_ids()
                        logging.info(f"[{doc_id}] Stored generation ID: {generation_id}")
                    
                    # Check if response was cut off due to length
                    finish_reason = choice.get("finish_reason")
                    if finish_reason == "length":
                        logging.warning(f"[{doc_id}] API response was cut off due to length limit. Adding to length limit failures.")
                        length_limit_failures.add(doc_id)
                        save_length_limit_failures()
                    
                    # Store API request information
                    if filing_id:
                        logging.info(f"[{doc_id}] Storing successful API request in database")
                        cursor.execute('''
                            INSERT INTO API_Requests (
                                filing_id, doc_id, generation_id, model, max_tokens,
                                text_length, approx_tokens, finish_reason, response_status,
                                pdf_link, raw_text, llm_response
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ''', (
                            filing_id, doc_id, generation_id, payload["model"],
                            max_tokens, text_length, approx_tokens,
                            finish_reason, response.status_code,
                            pdf_link, raw_text, csv_text
                        ))
                        conn.commit()
                        logging.info(f"[{doc_id}] Successfully stored API request")
                    else:
                        logging.warning(f"[{doc_id}] No filing_id found for successful API request")
                    
                    logging.info(f"[{doc_id}] Received CSV response:\n{csv_text[:200]}...")
                    
                    # Store the raw LLM output
                    llm_output = csv_text
                    logging.info(f"[{doc_id}] Successfully received LLM response.")
                else:
                    error_detail = response_data.get('error', {}).get('message', 'No content in choices.')
                    logging.error(f"[{doc_id}] No valid response content. Detail: {error_detail}")
                    llm_output = "DOCUMENT_UNREADABLE"
                    
                    # Store failed API request
                    if filing_id:
                        logging.info(f"[{doc_id}] Storing failed API request in database")
                        cursor.execute('''
                            INSERT INTO API_Requests (
                                filing_id, doc_id, model, max_tokens,
                                text_length, approx_tokens, response_status, error_message,
                                pdf_link, raw_text, llm_response
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ''', (
                            filing_id, doc_id, payload["model"],
                            max_tokens, text_length, approx_tokens,
                            response.status_code, error_detail,
                            pdf_link, raw_text, "DOCUMENT_UNREADABLE"
                        ))
                        conn.commit()
                        logging.info(f"[{doc_id}] Successfully stored failed API request")
                    else:
                        logging.warning(f"[{doc_id}] No filing_id found for failed API request")
            else:
                logging.error(f"[{doc_id}] Error calling OpenRouter API: {response.status_code} - {response.text}")
                llm_output = "DOCUMENT_UNREADABLE"
                
                # Store failed API request
                if filing_id:
                    logging.info(f"[{doc_id}] Storing API error in database")
                    cursor.execute('''
                        INSERT INTO API_Requests (
                            filing_id, doc_id, model, max_tokens,
                            text_length, approx_tokens, response_status, error_message,
                            pdf_link, raw_text, llm_response
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        filing_id, doc_id, payload["model"],
                        max_tokens, text_length, approx_tokens,
                        response.status_code, response.text,
                        pdf_link, raw_text, "DOCUMENT_UNREADABLE"
                    ))
                    conn.commit()
                    logging.info(f"[{doc_id}] Successfully stored API error")
                else:
                    logging.warning(f"[{doc_id}] No filing_id found for API error")

        except requests.exceptions.Timeout:
            logging.error(f"[{doc_id}] Timeout error during OpenRouter request.")
            llm_output = "DOCUMENT_UNREADABLE"
            _store_error_in_db(doc_id, "Timeout error", pdf_link, raw_text, "DOCUMENT_UNREADABLE")
                
        except requests.exceptions.RequestException as req_err:
            logging.error(f"[{doc_id}] Network error during OpenRouter request: {req_err}")
            llm_output = "DOCUMENT_UNREADABLE"
            _store_error_in_db(doc_id, f"Network error: {str(req_err)}", pdf_link, raw_text, "DOCUMENT_UNREADABLE")
                
        finally:
            if 'conn' in locals():
                conn.close()

    except fitz.fitz.EmptyFileError:
        logging.error(f"[{doc_id}] Error: Empty PDF file")
        llm_output = "DOCUMENT_UNREADABLE"
        _store_error_in_db(doc_id, "Empty PDF file", pdf_link, "", "DOCUMENT_UNREADABLE")
    except fitz.fitz.FileDataError:
        logging.error(f"[{doc_id}] Error: Invalid PDF data")
        llm_output = "DOCUMENT_UNREADABLE"
        _store_error_in_db(doc_id, "Invalid PDF data", pdf_link, "", "DOCUMENT_UNREADABLE")
    except fitz.fitz.FileNotFoundError:
        logging.error(f"[{doc_id}] Error: PDF file not found")
        llm_output = "DOCUMENT_UNREADABLE"
        _store_error_in_db(doc_id, "PDF file not found", pdf_link, "", "DOCUMENT_UNREADABLE")
    except requests.exceptions.RequestException as req_err:
        logging.error(f"[{doc_id}] Network error during PDF download: {req_err}")
        llm_output = "DOCUMENT_UNREADABLE"
        _store_error_in_db(doc_id, f"Network error during PDF download: {req_err}", pdf_link, "", "DOCUMENT_UNREADABLE")
    except Exception as e:
        logging.error(f"[{doc_id}] Error processing PDF with OpenRouter API: {e}", exc_info=True)
        llm_output = "DOCUMENT_UNREADABLE"
        _store_error_in_db(doc_id, f"Error processing PDF: {str(e)}", pdf_link, "", "DOCUMENT_UNREADABLE")

    return llm_output

def _store_error_in_db(doc_id: str, error_message: str, pdf_link: str, raw_text: str, llm_response: str):
    """Helper function to store error information in the database."""
    try:
        logging.info(f"[{doc_id}] Attempting to store error in database: {error_message}")
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # First check if we have a filing_id
        cursor.execute('SELECT filing_id FROM Filings WHERE doc_id = ?', (doc_id,))
        result = cursor.fetchone()
        filing_id = result[0] if result else None
        
        if filing_id:
            logging.info(f"[{doc_id}] Found filing_id: {filing_id}, inserting error record")
            cursor.execute('''
                INSERT INTO API_Requests (
                    filing_id, doc_id, model, max_tokens,
                    text_length, approx_tokens, response_status, error_message,
                    pdf_link, raw_text, llm_response
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                filing_id, doc_id, "error",
                0, len(raw_text), len(raw_text) // 4,
                0, error_message,
                pdf_link, raw_text, llm_response
            ))
            conn.commit()
            logging.info(f"[{doc_id}] Successfully stored error in database")
        else:
            logging.warning(f"[{doc_id}] No filing_id found in database, cannot store error")
    except Exception as e:
        logging.error(f"[{doc_id}] Error storing error information in database: {e}", exc_info=True)
    finally:
        if 'conn' in locals():
            conn.close()

# Example Usage (reflects new output structure of parse_llm_transactions)
if __name__ == '__main__':
    # Create a dummy PDF in memory for testing
    try:
        pdf_content = b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Count 1/Kids[3 0 R]>>endobj\n3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R/Resources<<>>>>endobj\nxref\n0 4\n0000000000 65535 f\n0000000010 00000 n\n0000000059 00000 n\n0000000118 00000 n\ntrailer<</Size 4/Root 1 0 R>>\nstartxref\n198\n%%EOF"
        dummy_pdf_file = BytesIO(pdf_content)
        logging.info("Created dummy PDF for testing scan_with_openrouter.")
    except Exception as e:
        logging.error(f"Could not create dummy PDF: {e}")
        dummy_pdf_file = BytesIO()

    sample_member_data_for_api_call = {
        'DocID': 'API_TEST_DOC_001',
        # Other member_data fields aren't directly used by scan_with_openrouter beyond DocID
    }

    if api_key:
        logging.info(f"\nAttempting API call with DocID: {sample_member_data_for_api_call['DocID']} using google/gemini-2.0-flash-001...")
        # For a real test, replace `dummy_pdf_file` with BytesIO from a real PDF:
        # with open("path/to/your/test.pdf", "rb") as f:
        #     real_pdf_bytesio = BytesIO(f.read())
        # transactions_result_api = scan_with_openrouter(real_pdf_bytesio, sample_member_data_for_api_call)
        transactions_result_api = scan_with_openrouter(dummy_pdf_file, sample_member_data_for_api_call)

        if transactions_result_api:
            logging.info(f"\n[API TEST SUCCESS] Extracted {len(transactions_result_api)} transactions:")
            for tx in transactions_result_api:
                print(json.dumps(tx, indent=2))
        else:
            logging.info("\n[API TEST INFO] No transactions extracted or an error occurred during API call.")
    else:
        logging.warning("\n[API TEST SKIPPED] API key not found. Skipping API call test.")

    # Print any text extraction failures
    if text_extraction_failures:
        logging.info("\nDocuments where text extraction failed:")
        for doc_id in text_extraction_failures:
            logging.info(f"- {doc_id}")

    # Print any length limit failures
    if length_limit_failures:
        logging.info("\nDocuments where API response was cut off due to length limit:")
        for doc_id in length_limit_failures:
            logging.info(f"- {doc_id}")

    # Test parse_llm_transactions directly
    logging.info("\n--- Testing parse_llm_transactions directly ---")
    sample_llm_csv_output = """
SP,Microsoft Corporation (MSFT),P,01/15/2024,01/20/2024,$1,001 - $15,000
JT,Some Bond Fund,S,02/10/2024,02/15/2024,$15,001 - $50,000
DC,Advanced Micro Devices, Inc. (AMD),P,03/01/2024,03/05/2024,$50,000
,No Ticker Corp,E,04/01/2024,04/05/2024,$1,000,001 - $5,000,000
SP,Bad Date Inc (BDI),P,13/01/2024,01/30/2024,$1 - $1,000
SP,OnlyCompanyName,S,05/05/2024,05/10/2024,$1 - $1,000
SP,Company With (Parens In Name) Corp (CWPC),P,06/01/2024,06/05/2024,$1000-$2000
SP,International Business Machines IBM, S, 07/01/2024, 07/05/2024, $100,001-$250,000
SP,Vanguard Total Stock Market Index Fund ETF Shares (VTI),P,08/01/2024,08/05/2024,Over $1,000,000
    """
    sample_member_data_for_parse = {'DocID': 'PARSE_TEST_002'}
    parsed_transactions = parse_llm_transactions(sample_llm_csv_output, sample_member_data_for_parse)

    if parsed_transactions:
        logging.info(f"Successfully parsed {len(parsed_transactions)} transactions directly:")
        for tx in parsed_transactions:
            print(json.dumps(tx, indent=2))
    else:
        logging.info("Direct parsing test yielded no transactions.")