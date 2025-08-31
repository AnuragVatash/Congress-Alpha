"""
House of Representatives Financial Disclosure Scraper
Scrapes PTR (Periodic Transaction Report) filings from the House disclosures website
"""

import logging
import time
import json
import os
from datetime import datetime
from typing import List, Dict, Set, Optional
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class HouseDisclosureScraper:
    """Scraper for House of Representatives financial disclosures"""
    
    def __init__(self, headless: bool = True):
        """
        Initialize the scraper
        
        Args:
            headless: Whether to run Chrome in headless mode
        """
        self.base_url = "https://disclosures-clerk.house.gov/FinancialDisclosure"
        self.headless = headless
        self.driver = None
        self.scraped_filings = []
        
    def _setup_driver(self):
        """Setup Chrome WebDriver with appropriate options"""
        chrome_options = Options()
        if self.headless:
            chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920,1080")
        
        # User agent to appear more like a real browser
        chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        
        # Use webdriver-manager to install and manage the correct ChromeDriver
        service = Service(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service, options=chrome_options)
        logger.info("Chrome WebDriver initialized")
        
    def _close_driver(self):
        """Close the WebDriver"""
        if self.driver:
            self.driver.quit()
            self.driver = None
            logger.info("Chrome WebDriver closed")
            
    def navigate_to_search(self) -> bool:
        """
        Navigate to the search page
        
        Returns:
            True if successful, False otherwise
        """
        try:
            # Go to main page
            self.driver.get(self.base_url)
            time.sleep(2)  # Wait for page to load
            
            # Click on Search tab
            search_button = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//a[@data-view='ViewSearch']"))
            )
            search_button.click()
            time.sleep(2)
            
            logger.info("Navigated to search page")
            return True
            
        except TimeoutException:
            logger.error("Failed to navigate to search page - timeout")
            return False
        except Exception as e:
            logger.error(f"Error navigating to search page: {e}")
            return False
            
    def search_by_year(self, year: int) -> bool:
        """
        Search for filings by year
        
        Args:
            year: Year to search for (e.g., 2025)
            
        Returns:
            True if search successful, False otherwise
        """
        try:
            # Wait for and select year dropdown
            year_select = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.ID, "FilingYear"))
            )
            
            # Select the year
            select = Select(year_select)
            select.select_by_value(str(year))
            time.sleep(1)
            
            # Click search button
            search_button = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//button[@type='submit' and contains(@class, 'btn-library')]"))
            )
            search_button.click()
            
            # Wait for results to load
            time.sleep(3)
            
            logger.info(f"Searched for year {year}")
            return True
            
        except TimeoutException:
            logger.error(f"Timeout searching for year {year}")
            return False
        except Exception as e:
            logger.error(f"Error searching for year {year}: {e}")
            return False
            
    def sort_by_filing_type(self) -> bool:
        """
        Sort results by filing type to find PTRs
        
        Returns:
            True if successful, False otherwise
        """
        try:
            # Click on Filing column header to sort
            filing_header = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//th[contains(text(), 'Filing')]"))
            )
            filing_header.click()
            time.sleep(2)
            
            logger.info("Sorted by filing type")
            return True
            
        except TimeoutException:
            logger.error("Failed to sort by filing type - timeout")
            return False
        except Exception as e:
            logger.error(f"Error sorting by filing type: {e}")
            return False
            
    def extract_ptr_filings_from_page(self) -> List[Dict]:
        """
        Extract PTR filing information from the current page
        
        Returns:
            List of filing dictionaries
        """
        filings = []
        
        try:
            # Wait for table to be present
            table = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.XPATH, "//table[contains(@class, 'library-table')]"))
            )
            
            # Get all rows
            rows = table.find_elements(By.XPATH, ".//tbody/tr")
            
            for row in rows:
                try:
                    # Get filing type
                    filing_type_element = row.find_element(By.XPATH, ".//td[@data-label='Filing']")
                    filing_type = filing_type_element.text.strip()
                    
                    # Only process PTR filings
                    if 'PTR' in filing_type.upper():
                        # Get member name and link
                        name_element = row.find_element(By.XPATH, ".//td[@data-label='Name']/a")
                        member_name = name_element.text.strip()
                        pdf_link = name_element.get_attribute('href')
                        
                        # Extract doc_id from link
                        # Format: public_disc/ptr-pdfs/2025/20026537.pdf
                        doc_id = None
                        if pdf_link and '.pdf' in pdf_link:
                            doc_id = pdf_link.split('/')[-1].replace('.pdf', '')
                        
                        # Get other fields
                        office = row.find_element(By.XPATH, ".//td[@data-label='Office']").text.strip()
                        filing_year = row.find_element(By.XPATH, ".//td[@data-label='Filing Year']").text.strip()
                        
                        filing = {
                            'doc_id': doc_id,
                            'member_name': member_name,
                            'pdf_url': pdf_link,
                            'filing_type': filing_type,
                            'office': office,
                            'filing_year': filing_year,
                            'scraped_at': datetime.now().isoformat()
                        }
                        
                        filings.append(filing)
                        logger.debug(f"Found PTR filing: {doc_id} - {member_name}")
                        
                except NoSuchElementException:
                    continue
                except Exception as e:
                    logger.warning(f"Error extracting row data: {e}")
                    continue
                    
            logger.info(f"Extracted {len(filings)} PTR filings from current page")
            return filings
            
        except TimeoutException:
            logger.error("Timeout waiting for table")
            return []
        except Exception as e:
            logger.error(f"Error extracting filings: {e}")
            return []
            
    def navigate_pages(self, max_pages: Optional[int] = None, find_first_ptr: bool = False) -> List[Dict]:
        """
        Navigate through all pages and extract PTR filings
        
        Args:
            max_pages: Maximum number of pages to process (None for all)
            find_first_ptr: If True, stop after finding the first PTR filing.
            
        Returns:
            List of all PTR filings found
        """
        all_filings = []
        page_num = 1
        
        while True:
            if max_pages and page_num > max_pages:
                logger.info(f"Reached maximum page limit ({max_pages})")
                break
                
            logger.info(f"Processing page {page_num}")
            
            # Extract filings from current page
            page_filings = self.extract_ptr_filings_from_page()
            all_filings.extend(page_filings)
            
            # Try to go to next page
            try:
                # Check if there's a next button
                next_button = self.driver.find_element(
                    By.XPATH, 
                    "//a[contains(@class, 'paginate_button') and contains(@class, 'next') and not(contains(@class, 'disabled'))]"
                )
                
                # Use a JavaScript click which is more robust
                self.driver.execute_script("arguments[0].click();", next_button)
                time.sleep(2)  # Wait for page to load
                page_num += 1
                
                # If find_first_ptr is True, check if we found a PTR filing
                if find_first_ptr and page_filings:
                    for filing in page_filings:
                        if filing['doc_id']:
                            logger.info(f"Found PTR filing on page {page_num - 1}: {filing['doc_id']}")
                            return all_filings # Return immediately if find_first_ptr is True
                            
            except NoSuchElementException:
                logger.info("No more pages to process")
                break
            except Exception as e:
                logger.error(f"Error navigating to next page: {e}")
                break
                
        logger.info(f"Processed {page_num} pages, found {len(all_filings)} total PTR filings")
        return all_filings
        
    def scrape_ptr_filings(self, year: int = 2025, max_pages: Optional[int] = None, find_first_ptr: bool = False) -> List[Dict]:
        """
        Main method to scrape PTR filings for a given year
        
        Args:
            year: Year to scrape (default: 2025)
            max_pages: Maximum number of pages to process (None for all)
            find_first_ptr: If True, stop after finding the first PTR filing.
            
        Returns:
            List of PTR filing dictionaries
        """
        logger.info(f"Starting scrape for year {year}")
        
        try:
            # Setup driver
            self._setup_driver()
            
            # Navigate to search page
            if not self.navigate_to_search():
                raise Exception("Failed to navigate to search page")
                
            # Search for the specified year
            if not self.search_by_year(year):
                raise Exception(f"Failed to search for year {year}")
                
            # Sort by filing type
            if not self.sort_by_filing_type():
                logger.warning("Failed to sort by filing type, continuing anyway")
                
            # Extract filings from all pages
            self.scraped_filings = self.navigate_pages(max_pages=max_pages, find_first_ptr=find_first_ptr)
            
            return self.scraped_filings
            
        except Exception as e:
            logger.error(f"Scraping failed: {e}")
            return []
            
        finally:
            # Always close the driver
            self._close_driver()
            
    def save_scraped_filings(self, filepath: str = None):
        """
        Save scraped filings to a JSON file
        
        Args:
            filepath: Path to save file (default: house_scraped_filings.json)
        """
        if not filepath:
            filepath = os.path.join(os.path.dirname(__file__), 'house_scraped_filings.json')
            
        try:
            with open(filepath, 'w') as f:
                json.dump({
                    'scrape_timestamp': datetime.now().isoformat(),
                    'total_filings': len(self.scraped_filings),
                    'filings': self.scraped_filings
                }, f, indent=2)
                
            logger.info(f"Saved {len(self.scraped_filings)} filings to {filepath}")
            
        except Exception as e:
            logger.error(f"Error saving filings: {e}")
            
    def load_scraped_filings(self, filepath: str = None) -> List[Dict]:
        """
        Load previously scraped filings from JSON file
        
        Args:
            filepath: Path to load file from
            
        Returns:
            List of filing dictionaries
        """
        if not filepath:
            filepath = os.path.join(os.path.dirname(__file__), 'house_scraped_filings.json')
            
        try:
            with open(filepath, 'r') as f:
                data = json.load(f)
                self.scraped_filings = data.get('filings', [])
                logger.info(f"Loaded {len(self.scraped_filings)} filings from {filepath}")
                return self.scraped_filings
        except FileNotFoundError:
            logger.warning(f"File not found: {filepath}")
            return []
        except Exception as e:
            logger.error(f"Error loading filings: {e}")
            return []

    def get_new_filings(self, existing_doc_ids: Set[str]) -> List[Dict]:
        """
        Filter scraped filings to only include new ones
        
        Args:
            existing_doc_ids: Set of document IDs already in database
            
        Returns:
            List of new filing dictionaries
        """
        new_filings = []
        for filing in self.scraped_filings:
            if filing['doc_id'] and filing['doc_id'] not in existing_doc_ids:
                new_filings.append(filing)
                
        logger.info(f"Found {len(new_filings)} new filings out of {len(self.scraped_filings)} total")
        return new_filings

if __name__ == "__main__":
    # Test the scraper
    scraper = HouseDisclosureScraper(headless=False)
    
    # Scrape until we find the first PTR filing for the current year
    logger.info("Searching for the first PTR filing of 2025. This might take a moment...")
    filings = scraper.scrape_ptr_filings(year=2025, find_first_ptr=True)
    
    # Save to file
    scraper.save_scraped_filings()
    
    print(f"Scraped {len(filings)} PTR filings")
    if filings:
        print("Sample filing:", json.dumps(filings[0], indent=2))
