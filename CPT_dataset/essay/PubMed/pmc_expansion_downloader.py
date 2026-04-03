#!/usr/bin/env python3
"""
PMC Expansion Downloader for FoodmoleGPT
==========================================
Download new food science articles as XML for dataset expansion.
Reads PMCID list from pmc_esearch_collector.py output.

Usage:
    python pmc_expansion_downloader.py [--max-results N]

Author: FoodmoleGPT Team
"""

import json
import sys
import time
import logging
import argparse
import threading
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Set
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


def setup_entrez():
    Entrez.email = config.NCBI_EMAIL
    Entrez.tool = config.NCBI_TOOL
    if config.NCBI_API_KEY:
        Entrez.api_key = config.NCBI_API_KEY


def setup_logging(log_dir: Path) -> logging.Logger:
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "expansion_download.log"

    logger = logging.getLogger("PMCExpansionDownloader")
    logger.setLevel(logging.DEBUG)
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


def load_progress(path: Path) -> Dict:
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return {"downloaded": [], "failed": [], "last_updated": None}


def save_progress(path: Path, progress: Dict):
    progress["last_updated"] = datetime.now().isoformat()
    with open(path, "w") as f:
        json.dump(progress, f)


def download_xml(
    pmc_num: str, output_dir: Path, rate_limiter: RateLimiter, logger: logging.Logger
) -> tuple:
    """Download a single article XML via Entrez efetch (thread-safe)."""
    pmcid = f"PMC{pmc_num}"
    output_file = output_dir / f"{pmcid}.xml"

    if output_file.exists() and output_file.stat().st_size > 100:
        return (pmcid, True, "already exists")

    for attempt in range(config.MAX_RETRIES):
        try:
            rate_limiter.wait()
            handle = Entrez.efetch(db="pmc", id=pmc_num, rettype="xml", retmode="xml")
            content = handle.read()
            handle.close()

            if not content or len(content) < 200:
                if attempt < config.MAX_RETRIES - 1:
                    time.sleep(1)
                    continue
                return (pmcid, False, "empty response")

            content_str = content.decode("utf-8", errors="ignore")[:500]
            if "<error>" in content_str.lower() or "id not found" in content_str.lower():
                return (pmcid, False, "article not available via API")

            with open(output_file, "wb") as f:
                f.write(content)
            return (pmcid, True, None)

        except Exception as e:
            if attempt < config.MAX_RETRIES - 1:
                time.sleep(1)
            else:
                return (pmcid, False, str(e))

    return (pmcid, False, "max retries exceeded")


def main():
    parser = argparse.ArgumentParser(
        description="Download expansion XML files from PMC"
    )
    parser.add_argument(
        "--pmcids-file",
        type=str,
        default="data/expansion_pmcids.json",
        help="JSON file with PMCID list (from pmc_esearch_collector.py)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="data/xml_expansion",
        help="Output directory for new XML files",
    )
    parser.add_argument(
        "--max-results", "-n",
        type=int,
        default=None,
        help="Max articles to download",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=8,
        help="Number of download threads",
    )
    args = parser.parse_args()

    script_dir = Path(__file__).parent
    pmcids_path = Path(args.pmcids_file)
    if not pmcids_path.is_absolute():
        pmcids_path = script_dir / pmcids_path

    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = script_dir / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    logs_dir = script_dir / config.OUTPUT_DIR / config.LOGS_DIR
    logger = setup_logging(logs_dir)
    setup_entrez()

    logger.info("=" * 60)
    logger.info("PMC Expansion Downloader")
    logger.info("=" * 60)

    # Load PMCIDs
    if not pmcids_path.exists():
        logger.error(f"PMCIDs file not found: {pmcids_path}")
        logger.error("Run pmc_esearch_collector.py first!")
        sys.exit(1)

    with open(pmcids_path) as f:
        data = json.load(f)

    pmcids = data["pmcids"]
    logger.info(f"Loaded {len(pmcids):,} PMCIDs from {pmcids_path.name}")

    if args.max_results:
        pmcids = pmcids[: args.max_results]
        logger.info(f"Capped to {len(pmcids):,} articles")

    # Progress
    progress_file = output_dir.parent / "expansion_download_progress.json"
    progress = load_progress(progress_file)

    downloaded_set: Set[str] = set(progress["downloaded"])
    failed_set: Set[str] = set(progress["failed"])

    # Also check files on disk
    existing = set()
    for f in output_dir.glob("PMC*.xml"):
        if f.stat().st_size > 100:
            existing.add(f.stem)
    downloaded_set.update(existing)

    # Filter
    to_download = [
        pid for pid in pmcids
        if pid not in downloaded_set and pid not in failed_set
    ]

    if not to_download:
        logger.info("All articles already downloaded!")
        return

    rate_limiter = RateLimiter(max_per_second=9.0)

    logger.info(f"To download: {len(to_download):,}")
    logger.info(f"Previously downloaded: {len(downloaded_set):,}")
    logger.info(f"Workers: {args.workers} threads")

    success_count = 0
    fail_count = 0
    progress_lock = threading.Lock()

    pbar = tqdm(total=len(to_download), desc="Downloading", unit="xml")

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {}
        for pid in to_download:
            pmc_num = pid.replace("PMC", "")
            fut = executor.submit(download_xml, pmc_num, output_dir, rate_limiter, logger)
            futures[fut] = pid

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

                if (success_count + fail_count) % 500 == 0:
                    progress["downloaded"] = list(downloaded_set)
                    progress["failed"] = list(failed_set)
                    save_progress(progress_file, progress)

    pbar.close()

    progress["downloaded"] = list(downloaded_set)
    progress["failed"] = list(failed_set)
    save_progress(progress_file, progress)

    logger.info(f"\nDownload complete!")
    logger.info(f"  Successful: {success_count:,}")
    logger.info(f"  Failed: {fail_count:,}")
    logger.info(f"  Total in directory: {len(downloaded_set):,}")


if __name__ == "__main__":
    main()
