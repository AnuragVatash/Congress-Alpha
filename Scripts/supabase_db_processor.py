"""
Supabase Database Processor
Handles database operations for uploading congressional trading data to Supabase
"""

import os
import logging
from typing import Dict, List, Optional, Set, Tuple
from datetime import datetime
from supabase import create_client, Client
from dotenv import load_dotenv
import json

# Load environment variables
load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Supabase configuration
SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_KEY')

if not SUPABASE_URL or not SUPABASE_KEY:
    logger.error("Supabase credentials not found in environment variables")

class SupabaseDBProcessor:
    """Handles all database operations with Supabase"""
    
    def __init__(self):
        """Initialize the Supabase client"""
        if not SUPABASE_URL or not SUPABASE_KEY:
            raise ValueError("Supabase credentials not configured")
            
        self.supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
        logger.info("Supabase client initialized")
        
        # Cache for members and assets to avoid repeated lookups
        self.member_cache = {}
        self.asset_cache = {}
        
    def get_or_create_member(self, member_name: str, office: str = None) -> Optional[int]:
        """
        Get or create a member in the database
        
        Args:
            member_name: Full name of the member
            office: Office/chamber (House/Senate)
            
        Returns:
            member_id or None if failed
        """
        # Check cache first
        if member_name in self.member_cache:
            return self.member_cache[member_name]
            
        try:
            # Try to find existing member
            response = self.supabase.table('Members').select('member_id').eq('name', member_name).execute()
            
            if response.data and len(response.data) > 0:
                member_id = response.data[0]['member_id']
                self.member_cache[member_name] = member_id
                logger.debug(f"Found existing member: {member_name} (ID: {member_id})")
                return member_id
                
            # Create new member
            chamber = 'House' if office and 'House' in office else 'Senate' if office and 'Senate' in office else None
            
            new_member = {
                'name': member_name,
                'chamber': chamber
            }
            
            response = self.supabase.table('Members').insert(new_member).execute()
            
            if response.data and len(response.data) > 0:
                member_id = response.data[0]['member_id']
                self.member_cache[member_name] = member_id
                logger.info(f"Created new member: {member_name} (ID: {member_id})")
                return member_id
                
        except Exception as e:
            logger.error(f"Error getting/creating member {member_name}: {e}")
            
        return None
        
    def get_or_create_asset(self, ticker: str, company_name: str) -> Optional[int]:
        """
        Get or create an asset in the database
        
        Args:
            ticker: Stock ticker symbol
            company_name: Company name
            
        Returns:
            asset_id or None if failed
        """
        # Create cache key
        cache_key = f"{ticker}:{company_name}"
        if cache_key in self.asset_cache:
            return self.asset_cache[cache_key]
            
        try:
            # Try to find existing asset
            response = self.supabase.table('Assets').select('asset_id').eq('ticker', ticker).eq('company_name', company_name).execute()
            
            if response.data and len(response.data) > 0:
                asset_id = response.data[0]['asset_id']
                self.asset_cache[cache_key] = asset_id
                logger.debug(f"Found existing asset: {ticker} - {company_name} (ID: {asset_id})")
                return asset_id
                
            # Create new asset
            new_asset = {
                'ticker': ticker,
                'ticker_clean': ticker.upper().strip(),
                'company_name': company_name,
                'company_clean': company_name.strip()
            }
            
            response = self.supabase.table('Assets').insert(new_asset).execute()
            
            if response.data and len(response.data) > 0:
                asset_id = response.data[0]['asset_id']
                self.asset_cache[cache_key] = asset_id
                logger.info(f"Created new asset: {ticker} - {company_name} (ID: {asset_id})")
                return asset_id
                
        except Exception as e:
            logger.error(f"Error getting/creating asset {ticker} - {company_name}: {e}")
            
        return None
        
    def get_existing_doc_ids(self) -> Set[str]:
        """
        Get all existing document IDs from the database
        
        Returns:
            Set of document IDs already in the database
        """
        doc_ids = set()
        
        try:
            # Query all filings
            response = self.supabase.table('Filings').select('doc_id').execute()
            
            if response.data:
                doc_ids = {filing['doc_id'] for filing in response.data}
                logger.info(f"Found {len(doc_ids)} existing document IDs in database")
                
        except Exception as e:
            logger.error(f"Error getting existing doc IDs: {e}")
            
        return doc_ids
        
    def create_filing(self, doc_id: str, member_id: int, pdf_url: str, filing_date: str = None) -> Optional[int]:
        """
        Create a new filing record
        
        Args:
            doc_id: Document ID
            member_id: Member ID from database
            pdf_url: URL of the PDF
            filing_date: Date of filing (optional)
            
        Returns:
            filing_id or None if failed
        """
        try:
            # Check if filing already exists
            response = self.supabase.table('Filings').select('filing_id').eq('doc_id', doc_id).execute()
            
            if response.data and len(response.data) > 0:
                filing_id = response.data[0]['filing_id']
                logger.debug(f"Filing already exists: {doc_id} (ID: {filing_id})")
                return filing_id
                
            # Create new filing
            new_filing = {
                'doc_id': doc_id,
                'member_id': member_id,
                'url': pdf_url,
                'verified': True  # Mark as verified since we're processing it
            }
            
            if filing_date:
                new_filing['filing_date'] = filing_date
                
            response = self.supabase.table('Filings').insert(new_filing).execute()
            
            if response.data and len(response.data) > 0:
                filing_id = response.data[0]['filing_id']
                logger.info(f"Created new filing: {doc_id} (ID: {filing_id})")
                return filing_id
                
        except Exception as e:
            logger.error(f"Error creating filing {doc_id}: {e}")
            
        return None
        
    def create_transaction(self, transaction_data: Dict, filing_id: int, asset_id: int) -> bool:
        """
        Create a new transaction record
        
        Args:
            transaction_data: Transaction data dictionary
            filing_id: Filing ID from database
            asset_id: Asset ID from database
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Map owner to owner_code
            owner_map = {
                'Self': 'S',
                'Spouse': 'SP',
                'Joint': 'JT',
                'Dependent': 'DC',
                'Child': 'DC'
            }
            owner_code = owner_map.get(transaction_data.get('owner', ''), transaction_data.get('owner', ''))
            
            # Create transaction record
            new_transaction = {
                'filing_id': filing_id,
                'asset_id': asset_id,
                'owner_code': owner_code,
                'transaction_type': transaction_data.get('transaction_type'),
                'transaction_date': transaction_data.get('transaction_date'),
                'amount_range_low': transaction_data.get('amount_low'),
                'amount_range_high': transaction_data.get('amount_high'),
                'raw_llm_csv_line': transaction_data.get('comment', '')
            }
            
            response = self.supabase.table('Transactions').insert(new_transaction).execute()
            
            if response.data:
                logger.debug(f"Created transaction: {transaction_data.get('ticker')} - {transaction_data.get('transaction_type')}")
                return True
                
        except Exception as e:
            logger.error(f"Error creating transaction: {e}")
            
        return False
        
    def process_transactions_batch(self, transactions: List[Dict]) -> Dict[str, int]:
        """
        Process a batch of transactions and upload to database
        
        Args:
            transactions: List of transaction dictionaries
            
        Returns:
            Dictionary with counts of processed items
        """
        stats = {
            'members_created': 0,
            'assets_created': 0,
            'filings_created': 0,
            'transactions_created': 0,
            'errors': 0
        }
        
        # Group transactions by filing for efficiency
        filings_map = {}
        for transaction in transactions:
            doc_id = transaction.get('doc_id')
            if doc_id not in filings_map:
                filings_map[doc_id] = {
                    'member_name': transaction.get('member_name'),
                    'office': transaction.get('office'),
                    'pdf_url': transaction.get('pdf_url'),
                    'transactions': []
                }
            filings_map[doc_id]['transactions'].append(transaction)
            
        # Process each filing
        for doc_id, filing_data in filings_map.items():
            try:
                # Get or create member
                member_id = self.get_or_create_member(
                    filing_data['member_name'],
                    filing_data['office']
                )
                
                if not member_id:
                    logger.error(f"Failed to get/create member for {filing_data['member_name']}")
                    stats['errors'] += 1
                    continue
                    
                # Create filing
                filing_id = self.create_filing(
                    doc_id,
                    member_id,
                    filing_data['pdf_url']
                )
                
                if not filing_id:
                    logger.error(f"Failed to create filing for {doc_id}")
                    stats['errors'] += 1
                    continue
                    
                stats['filings_created'] += 1
                
                # Process transactions for this filing
                for transaction in filing_data['transactions']:
                    try:
                        # Get or create asset
                        asset_id = self.get_or_create_asset(
                            transaction.get('ticker', ''),
                            transaction.get('asset_name', '')
                        )
                        
                        if not asset_id:
                            logger.error(f"Failed to get/create asset for {transaction.get('ticker')}")
                            stats['errors'] += 1
                            continue
                            
                        # Create transaction
                        if self.create_transaction(transaction, filing_id, asset_id):
                            stats['transactions_created'] += 1
                        else:
                            stats['errors'] += 1
                            
                    except Exception as e:
                        logger.error(f"Error processing transaction: {e}")
                        stats['errors'] += 1
                        
            except Exception as e:
                logger.error(f"Error processing filing {doc_id}: {e}")
                stats['errors'] += 1
                
        logger.info(f"Batch processing complete: {stats}")
        return stats
        
    def get_recent_transactions(self, limit: int = 10) -> List[Dict]:
        """
        Get recent transactions from the database
        
        Args:
            limit: Number of transactions to retrieve
            
        Returns:
            List of transaction dictionaries
        """
        try:
            response = self.supabase.table('Transactions').select(
                '*, Filings(doc_id, Members(name)), Assets(ticker, company_name)'
            ).order('created_at', desc=True).limit(limit).execute()
            
            if response.data:
                return response.data
                
        except Exception as e:
            logger.error(f"Error getting recent transactions: {e}")
            
        return []
        
    def get_member_stats(self) -> Dict[str, int]:
        """
        Get statistics about members and transactions
        
        Returns:
            Dictionary with various statistics
        """
        stats = {
            'total_members': 0,
            'total_filings': 0,
            'total_transactions': 0,
            'total_assets': 0
        }
        
        try:
            # Get counts from each table
            members_response = self.supabase.table('Members').select('member_id', count='exact').execute()
            stats['total_members'] = members_response.count if members_response else 0
            
            filings_response = self.supabase.table('Filings').select('filing_id', count='exact').execute()
            stats['total_filings'] = filings_response.count if filings_response else 0
            
            transactions_response = self.supabase.table('Transactions').select('transaction_id', count='exact').execute()
            stats['total_transactions'] = transactions_response.count if transactions_response else 0
            
            assets_response = self.supabase.table('Assets').select('asset_id', count='exact').execute()
            stats['total_assets'] = assets_response.count if assets_response else 0
            
        except Exception as e:
            logger.error(f"Error getting database stats: {e}")
            
        return stats

if __name__ == "__main__":
    # Test the database processor
    db = SupabaseDBProcessor()
    
    # Get existing doc IDs
    existing_ids = db.get_existing_doc_ids()
    print(f"Found {len(existing_ids)} existing documents in database")
    
    # Get database stats
    stats = db.get_member_stats()
    print(f"Database stats: {json.dumps(stats, indent=2)}")
    
    # Test transaction creation with sample data
    test_transaction = {
        'doc_id': 'TEST_001',
        'member_name': 'Test Member',
        'office': 'House',
        'pdf_url': 'https://example.com/test.pdf',
        'ticker': 'AAPL',
        'asset_name': 'Apple Inc.',
        'transaction_type': 'Purchase',
        'transaction_date': '2025-01-01',
        'amount_low': 1001,
        'amount_high': 15000,
        'owner': 'Self'
    }
    
    # Process the test transaction
    # result = db.process_transactions_batch([test_transaction])
    # print(f"Test transaction result: {json.dumps(result, indent=2)}")
