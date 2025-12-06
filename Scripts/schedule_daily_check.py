#!/usr/bin/env python3
"""
Schedule Daily PTR Checks
Runs the daily PTR checker on a schedule (can be run as a service or cron job)
"""

import os
import sys
import logging
import schedule
import time
import subprocess
from datetime import datetime
import argparse

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('schedule_daily_check.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def run_daily_check():
    """Execute the daily PTR checker script"""
    logger.info("="*50)
    logger.info("Starting scheduled daily PTR check")
    logger.info(f"Time: {datetime.now()}")
    logger.info("="*50)
    
    try:
        # Run the daily checker script
        script_path = os.path.join(os.path.dirname(__file__), 'daily_ptr_checker.py')
        
        result = subprocess.run(
            [sys.executable, script_path],
            capture_output=True,
            text=True,
            timeout=3600  # 1 hour timeout
        )
        
        if result.returncode == 0:
            logger.info("Daily check completed successfully")
            logger.info(f"Output:\n{result.stdout}")
        else:
            logger.error(f"Daily check failed with return code: {result.returncode}")
            logger.error(f"Error output:\n{result.stderr}")
            
    except subprocess.TimeoutExpired:
        logger.error("Daily check timed out after 1 hour")
    except Exception as e:
        logger.error(f"Error running daily check: {e}")
        
    logger.info("Scheduled check complete")
    logger.info("="*50)

def setup_schedule(check_time: str = "09:00"):
    """
    Setup the schedule for daily checks
    
    Args:
        check_time: Time to run daily check (HH:MM format)
    """
    logger.info(f"Setting up daily schedule for {check_time}")
    
    # Schedule daily check
    schedule.every().day.at(check_time).do(run_daily_check)
    
    # Also run immediately on startup if requested
    return schedule

def main():
    """Main entry point for scheduler"""
    parser = argparse.ArgumentParser(description='Schedule daily PTR checks')
    parser.add_argument('--time', type=str, default="09:00",
                       help='Time to run daily check (HH:MM format, default: 09:00)')
    parser.add_argument('--run-now', action='store_true',
                       help='Run check immediately on startup')
    parser.add_argument('--once', action='store_true',
                       help='Run once and exit (for cron/systemd)')
    
    args = parser.parse_args()
    
    if args.once:
        # Just run once and exit (useful for cron)
        logger.info("Running single check and exiting")
        run_daily_check()
        sys.exit(0)
    
    # Setup schedule
    setup_schedule(args.time)
    
    # Run immediately if requested
    if args.run_now:
        logger.info("Running initial check on startup")
        run_daily_check()
    
    logger.info("Scheduler started. Press Ctrl+C to stop.")
    logger.info(f"Next check scheduled for: {args.time}")
    
    # Keep running
    try:
        while True:
            schedule.run_pending()
            time.sleep(60)  # Check every minute
    except KeyboardInterrupt:
        logger.info("Scheduler stopped by user")
        sys.exit(0)

if __name__ == "__main__":
    main()
