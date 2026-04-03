#!/usr/bin/env python3
"""
PMC Food Science XML Downloader
================================
Download food science articles as XML only (no images/attachments).
Uses oa_file_list.csv to ensure articles exist, then fetches XML via Entrez API.

Estimated size: ~15-25 GB for 100k+ articles (vs 750GB for tar.gz)

Usage:
    python pmc_downloader_xml.py [OPTIONS]

Author: FoodmoleGPT Team
"""

import os
import sys
import csv
import json
import time
import logging
import argparse
import threading
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Set, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

from Bio import Entrez
from tqdm import tqdm

import config


class RateLimiter:
    """Thread-safe rate limiter for NCBI API requests."""
    
    def __init__(self, max_per_second: float = 9.0):
        self.min_interval = 1.0 / max_per_second
        self.lock = threading.Lock()
        self.last_time = 0.0
    
    def wait(self):
        with self.lock:
            now = time.monotonic()
            elapsed = now - self.last_time
            if elapsed < self.min_interval:
                time.sleep(self.min_interval - elapsed)
            self.last_time = time.monotonic()


# =============================================================================
# Configuration
# =============================================================================

# Keywords for filtering (case-insensitive matching in Article Citation)
FOOD_KEYWORDS = [
    # Core food science
    "food", "nutrition", "diet", "dietary", "nutrient",
    # Food categories
    "dairy", "meat", "beef", "pork", "poultry", "chicken",
    "seafood", "fish", "vegetable", "fruit", "cereal", "grain",
    "beverage", "milk", "cheese", "yogurt", "bread", "rice",
    # Food science topics
    "ferment", "flavor", "flavour", "sensory", "taste",
    "cooking", "culinary", "recipe",
    # Food safety & quality
    "foodborne", "food safety", "food contamination",
    "preserv", "shelf life", "spoilage",
    # Food processing
    "food processing", "food technology", "food packaging",
    # Agriculture related
    "agricult", "crop", "harvest", "livestock",
    # Specific compounds
    "antioxidant", "phenolic", "polyphenol", "vitamin",
    "fatty acid", "protein", "carbohydrate", "fiber", "fibre",
    # Journals (food-specific journals)
    "j food", "food res", "food chem", "food sci",
    "meat sci", "dairy sci", "cereal", "appetite",
    "nutrients", "foods", "beverages",
]


# =============================================================================
# Setup
# =============================================================================

def setup_logging(log_dir: Path) -> logging.Logger:
    """Configure logging."""
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "download_xml.log"
    
    logger = logging.getLogger("PMCDownloaderXML")
    logger.setLevel(logging.DEBUG)
    
    # Clear existing handlers
    logger.handlers = []
    
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
    
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter("%(message)s"))
    
    logger.addHandler(fh)
    logger.addHandler(ch)
    
    return logger


def setup_entrez():
    """Configure Entrez with email and API key."""
    Entrez.email = config.NCBI_EMAIL
    Entrez.tool = config.NCBI_TOOL
    if config.NCBI_API_KEY:
        Entrez.api_key = config.NCBI_API_KEY


# =============================================================================
# Filter Functions
# =============================================================================

def matches_food_keywords(citation: str) -> bool:
    """Check if article citation matches food science keywords."""
    citation_lower = citation.lower()
    return any(kw.lower() in citation_lower for kw in FOOD_KEYWORDS)


def filter_food_articles(csv_path: Path, logger: logging.Logger,
                         max_articles: Optional[int] = None) -> List[Dict]:
    """Filter oa_file_list.csv for food science articles."""
    logger.info(f"Reading {csv_path}...")
    
    food_articles = []
    total_rows = 0
    
    with open(csv_path, 'r', encoding='utf-8', errors='ignore') as f:
        reader = csv.DictReader(f)
        
        for row in tqdm(reader, desc="Filtering articles", unit="row"):
            total_rows += 1
            
            citation = row.get('Article Citation', '')
            
            if matches_food_keywords(citation):
                pmcid = row.get('Accession ID', '')
                # Extract numeric ID (remove 'PMC' prefix)
                pmc_num = pmcid.replace('PMC', '') if pmcid.startswith('PMC') else pmcid
                
                food_articles.append({
                    'pmcid': pmcid,
                    'pmc_num': pmc_num,
                    'pmid': row.get('PMID', ''),
                    'citation': citation,
                    'license': row.get('License', ''),
                })
                
                if max_articles and len(food_articles) >= max_articles:
                    break
    
    logger.info(f"Scanned {total_rows:,} articles")
    logger.info(f"Found {len(food_articles):,} food science articles")
    
    return food_articles


# =============================================================================
# Download Functions
# =============================================================================

def load_progress(progress_file: Path) -> Dict:
    """Load download progress."""
    if progress_file.exists():
        with open(progress_file, 'r') as f:
            return json.load(f)
    return {"downloaded": [], "failed": [], "last_updated": None}


def save_progress(progress_file: Path, progress: Dict):
    """Save download progress."""
    progress["last_updated"] = datetime.now().isoformat()
    with open(progress_file, 'w') as f:
        json.dump(progress, f)


def download_xml(pmc_num: str, output_dir: Path, 
                 rate_limiter: RateLimiter, logger: logging.Logger) -> tuple:
    """
    Download a single article XML via Entrez efetch (thread-safe).
    
    Returns: (pmcid, success, error_message)
    """
    pmcid = f"PMC{pmc_num}"
    output_file = output_dir / f"{pmcid}.xml"
    
    # Skip if already exists
    if output_file.exists() and output_file.stat().st_size > 100:
        return (pmcid, True, "already exists")
    
    for attempt in range(config.MAX_RETRIES):
        try:
            # Rate limit before each request
            rate_limiter.wait()
            
            # Fetch XML via Entrez
            handle = Entrez.efetch(
                db="pmc",
                id=pmc_num,
                rettype="xml",
                retmode="xml"
            )
            content = handle.read()
            handle.close()
            
            # Check if valid XML
            if not content or len(content) < 200:
                if attempt < config.MAX_RETRIES - 1:
                    time.sleep(1)
                    continue
                return (pmcid, False, "empty response")
            
            # Check for error messages in response
            content_str = content.decode('utf-8', errors='ignore')[:500]
            if '<error>' in content_str.lower() or 'id not found' in content_str.lower():
                return (pmcid, False, "article not available via API")
            
            # Save XML
            with open(output_file, 'wb') as f:
                f.write(content)
            
            return (pmcid, True, None)
            
        except Exception as e:
            if attempt < config.MAX_RETRIES - 1:
                time.sleep(1)
            else:
                return (pmcid, False, str(e))
    
    return (pmcid, False, "max retries exceeded")


def download_articles(articles: List[Dict], output_dir: Path,
                     progress: Dict, progress_file: Path,
                     logger: logging.Logger,
                     num_workers: int = 8) -> Dict:
    """Download articles concurrently with progress tracking."""
    output_dir.mkdir(parents=True, exist_ok=True)
    
    downloaded_set: Set[str] = set(progress["downloaded"])
    failed_set: Set[str] = set(progress["failed"])
    
    # Also check existing files on disk (in case progress file is incomplete)
    existing_files = set()
    for f in output_dir.glob("PMC*.xml"):
        if f.stat().st_size > 100:
            existing_files.add(f.stem)
    downloaded_set.update(existing_files)
    
    # Filter out already processed
    to_download = [
        a for a in articles 
        if a['pmcid'] not in downloaded_set and a['pmcid'] not in failed_set
    ]
    
    if not to_download:
        logger.info("All articles already downloaded!")
        return progress
    
    # Rate limiter: 9 req/s (leave margin under NCBI's 10 req/s limit)
    rate_limiter = RateLimiter(max_per_second=9.0)
    
    logger.info(f"Downloading {len(to_download):,} XML files...")
    logger.info(f"Previously downloaded: {len(downloaded_set):,}")
    logger.info(f"Previously failed: {len(failed_set):,}")
    logger.info(f"Workers: {num_workers} threads")
    logger.info(f"Rate limit: 9 requests/second")
    
    success_count = 0
    fail_count = 0
    progress_lock = threading.Lock()
    
    pbar = tqdm(total=len(to_download), desc="Downloading", unit="xml")
    
    with ThreadPoolExecutor(max_workers=num_workers) as executor:
        futures = {
            executor.submit(
                download_xml, a['pmc_num'], output_dir, rate_limiter, logger
            ): a for a in to_download
        }
        
        for future in as_completed(futures):
            pmcid, success, error = future.result()
            
            with progress_lock:
                if success:
                    downloaded_set.add(pmcid)
                    success_count += 1
                else:
                    failed_set.add(pmcid)
                    fail_count += 1
                    logger.debug(f"{pmcid}: {error}")
                
                pbar.update(1)
                pbar.set_postfix(ok=success_count, fail=fail_count)
                
                # Save progress every 500 articles
                if (success_count + fail_count) % 500 == 0:
                    progress["downloaded"] = list(downloaded_set)
                    progress["failed"] = list(failed_set)
                    save_progress(progress_file, progress)
    
    pbar.close()
    
    # Final save
    progress["downloaded"] = list(downloaded_set)
    progress["failed"] = list(failed_set)
    save_progress(progress_file, progress)
    
    logger.info(f"\nDownload complete!")
    logger.info(f"  Successful: {success_count:,}")
    logger.info(f"  Failed: {fail_count:,}")
    logger.info(f"  Total downloaded: {len(downloaded_set):,}")


# =============================================================================
# Main
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Download food science articles as XML from PMC"
    )
    parser.add_argument(
        "--csv", "-c",
        type=str,
        default="../post_training_dataset/oa_file_list.csv",
        help="Path to oa_file_list.csv"
    )
    parser.add_argument(
        "--max-results", "-n",
        type=int,
        default=None,
        help="Maximum number of articles"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be downloaded"
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume from previous session"
    )
    parser.add_argument(
        "--output-dir", "-o",
        type=str,
        default=None,
        help="Output directory"
    )
    
    args = parser.parse_args()
    
    # Setup
    script_dir = Path(__file__).parent
    output_base = Path(args.output_dir) if args.output_dir else script_dir / config.OUTPUT_DIR
    xml_dir = output_base / "xml"
    logs_dir = output_base / config.LOGS_DIR
    
    xml_dir.mkdir(parents=True, exist_ok=True)
    logger = setup_logging(logs_dir)
    setup_entrez()
    
    logger.info("=" * 60)
    logger.info("PMC Food Science XML Downloader")
    logger.info("=" * 60)
    logger.info(f"Output: {xml_dir}")
    logger.info(f"API Key: {'Yes (10 req/s)' if config.NCBI_API_KEY else 'No (3 req/s)'}")
    
    # Check email
    if config.NCBI_EMAIL == "your_email@example.com":
        logger.error("Please set your email in config.py!")
        sys.exit(1)
    
    # CSV path
    csv_path = Path(args.csv)
    if not csv_path.is_absolute():
        csv_path = script_dir / csv_path
    
    if not csv_path.exists():
        logger.error(f"CSV not found: {csv_path}")
        sys.exit(1)
    
    # Progress and articles files
    progress_file = output_base / "download_xml_progress.json"
    articles_file = output_base / "food_articles_xml.json"
    
    # Filter or load
    if args.resume and articles_file.exists():
        logger.info("Loading previously filtered articles...")
        with open(articles_file, 'r') as f:
            articles = json.load(f)
        logger.info(f"Loaded {len(articles):,} articles")
    else:
        articles = filter_food_articles(csv_path, logger, args.max_results)
        with open(articles_file, 'w') as f:
            json.dump(articles, f)
    
    if not articles:
        logger.warning("No articles found!")
        return
    
    # Estimate size
    est_size_gb = len(articles) * 0.15 / 1024  # ~150KB per XML
    logger.info(f"Estimated download size: ~{est_size_gb:.1f} GB")
    
    if args.dry_run:
        logger.info("\n[DRY RUN] Would download:")
        for a in articles[:10]:
            logger.info(f"  - {a['pmcid']}: {a['citation'][:50]}...")
        if len(articles) > 10:
            logger.info(f"  ... and {len(articles) - 10:,} more")
        return
    
    # Download
    progress = load_progress(progress_file)
    download_articles(articles, xml_dir, progress, progress_file, logger)
    
    logger.info(f"\nDone! XML files saved to: {xml_dir}")


if __name__ == "__main__":
    main()
