import os
import sys
import logging
from io import BytesIO
from typing import Dict, List
import requests
import fitz

# Reuse the robust HOR LLM parsing pipeline
try:
    HOR_DIR = os.path.join(os.path.dirname(__file__), 'HOR Script')
    if HOR_DIR not in sys.path:
        sys.path.insert(0, HOR_DIR)
    from scanToTextLLM import (
        scan_with_openrouter as hor_scan_with_openrouter,
        parse_llm_transactions as hor_parse_llm_transactions,
    )
except Exception:
    hor_scan_with_openrouter = None
    hor_parse_llm_transactions = None


logger = logging.getLogger(__name__)


def _extract_pdf_text(pdf_bytes: bytes) -> str:
    try:
        doc = fitz.open("pdf", pdf_bytes)
        text = []
        for i in range(len(doc)):
            page = doc[i]
            page_text = page.get_text()
            if page_text:
                text.append(page_text)
        return "\n".join(text)
    except Exception as e:
        logger.error(f"PDF text extraction failed: {e}")
        return ""


def _download(pdf_url: str) -> bytes:
    response = requests.get(pdf_url, timeout=60)
    response.raise_for_status()
    return response.content


def _normalize_transactions(llm_csv_text: str, member_data: Dict) -> List[Dict]:
    if hor_parse_llm_transactions is None:
        logger.warning("parse_llm_transactions not available; returning empty transactions")
        return []
    parsed = hor_parse_llm_transactions(llm_csv_text, member_data)
    # Map to Supabase schema fields expected downstream
    normalized: List[Dict] = []
    for t in parsed:
        normalized.append({
            "transaction_date": t.get("transaction_date_str"),
            "ticker": t.get("ticker"),
            "asset_name": t.get("company_name"),
            "transaction_type": t.get("transaction_type_full"),
            "amount_low": t.get("amount_low"),
            "amount_high": t.get("amount_high"),
            "owner": t.get("owner_code"),
            "comment": t.get("raw_llm_line", "")
        })
    return normalized


def process_ptr_pdf(pdf_url: str, doc_id: str) -> Dict:
    """
    Download a House PTR PDF, extract text, run LLM to produce CSV-like rows, normalize for DB.
    Returns { "transactions": [ ... ] }
    """
    logger.info(f"Processing PDF for doc_id={doc_id}")

    # If HOR LLM scanner is available, use it directly (it handles PDF internally)
    if hor_scan_with_openrouter is not None and hor_parse_llm_transactions is not None:
        try:
            llm_csv = hor_scan_with_openrouter(pdf_url, {"DocID": doc_id})
            transactions = _normalize_transactions(llm_csv, {"DocID": doc_id})
            return {"transactions": transactions}
        except Exception as e:
            logger.warning(f"HOR scan_with_openrouter failed, falling back to local text extraction: {e}")

    # Fallback: download PDF and extract text locally, then feed to HOR parser via same interface
    try:
        pdf_bytes = _download(pdf_url)
    except Exception as e:
        logger.error(f"Failed to download PDF: {e}")
        return {"transactions": []}

    text = _extract_pdf_text(pdf_bytes)
    if not text.strip() or hor_parse_llm_transactions is None:
        return {"transactions": []}

    # Build a minimal prompt to mimic HOR behavior: we don't call API here; parser expects CSV text.
    # In absence of API call, we cannot generate CSV; so we return empty.
    logger.info("No LLM CSV available without API. Returning no transactions.")
    return {"transactions": []}
