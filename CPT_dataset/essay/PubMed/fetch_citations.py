#!/usr/bin/env python3
"""
Semantic Scholar Citation Fetcher
==================================
Fetches citation counts for the PMC food science corpus
using Semantic Scholar's batch API endpoint.

Steps:
  1. Convert PMCIDs → PMIDs via NCBI E-utilities (batch)
  2. Query S2 batch endpoint for citation counts (500/request)
  3. Save results back to corpus with citation metadata

Usage:
  python fetch_citations.py [--resume]
"""

import json
import os
import time
import sys
import urllib.request
import urllib.error
import urllib.parse
from pathlib import Path
from xml.etree import ElementTree

# ─── Configuration ───
CORPUS = Path("data/processed/filtered/food_science_corpus.keep.jsonl")
OUTPUT = Path("data/processed/filtered/citation_data.json")
PROGRESS = Path("data/processed/filtered/citation_progress.json")
PMCID_CACHE = Path("data/processed/filtered/pmcid_to_pmid_cache.json")

# Load API key from .env
env_path = Path(__file__).parent / ".env"
S2_API_KEY = ""
if env_path.exists():
    for line in env_path.read_text().splitlines():
        if line.startswith("S2_API_KEY="):
            S2_API_KEY = line.split("=", 1)[1].strip()
if not S2_API_KEY:
    print("ERROR: S2_API_KEY not found in .env")
    sys.exit(1)

# Rate limit: 1.2 seconds between requests
RATE_LIMIT = 1.2
S2_BATCH_SIZE = 500  # max 500 per batch request
NCBI_BATCH_SIZE = 200  # NCBI converter batch size

# NCBI config (reuse existing config if available)
try:
    from config import NCBI_EMAIL, NCBI_API_KEY
except ImportError:
    NCBI_EMAIL = "foodmolegpt@example.com"
    NCBI_API_KEY = None


def load_pmcids():
    """Load all PMCIDs from corpus."""
    pmcids = []
    with open(CORPUS) as f:
        for line in f:
            doc = json.loads(line)
            pmcids.append(doc.get("pmcid", ""))
    return pmcids


def convert_pmcid_to_pmid_batch(pmcids):
    """Convert PMCIDs to PMIDs using NCBI ID Converter API (batch).
    Results are cached to disk for resume."""
    print(f"\n{'=' * 60}")
    print(f"Step 1: Converting {len(pmcids):,} PMCIDs → PMIDs via NCBI")
    print(f"{'=' * 60}")
    
    # Load cache if exists
    pmc_to_pmid = {}
    if PMCID_CACHE.exists():
        with open(PMCID_CACHE) as f:
            pmc_to_pmid = json.load(f)
        print(f"  Loaded cache: {len(pmc_to_pmid):,} PMIDs")
    
    # Only convert uncached PMCIDs
    remaining = [p for p in pmcids if p not in pmc_to_pmid]
    if not remaining:
        print(f"  All {len(pmcids):,} PMCIDs already cached!")
        return pmc_to_pmid
    
    print(f"  Remaining to convert: {len(remaining):,}")
    total = len(remaining)
    
    for i in range(0, total, NCBI_BATCH_SIZE):
        batch = remaining[i:i+NCBI_BATCH_SIZE]
        ids_str = ",".join(batch)
        
        url = "https://www.ncbi.nlm.nih.gov/pmc/utils/idconv/v1.0/"
        params = {
            "ids": ids_str,
            "format": "json",
            "tool": "FoodmoleGPT",
            "email": NCBI_EMAIL,
        }
        if NCBI_API_KEY:
            params["api_key"] = NCBI_API_KEY
        
        query = urllib.parse.urlencode(params)
        full_url = f"{url}?{query}"
        
        for attempt in range(3):
            try:
                req = urllib.request.Request(full_url)
                with urllib.request.urlopen(req, timeout=30) as resp:
                    data = json.loads(resp.read().decode())
                
                for rec in data.get("records", []):
                    pmcid = rec.get("pmcid", "")
                    pmid = rec.get("pmid", "")
                    if pmcid and pmid:
                        pmc_to_pmid[pmcid] = pmid
                
                break
            except Exception as e:
                if attempt < 2:
                    time.sleep(2 ** attempt)
                else:
                    print(f"  WARN: Failed batch at {i}: {e}")
        
        if (i + NCBI_BATCH_SIZE) % 5000 == 0 or i + NCBI_BATCH_SIZE >= total:
            print(f"  Converted {min(i+NCBI_BATCH_SIZE, total):,}/{total:,} "
                  f"({len(pmc_to_pmid):,} PMIDs found)")
            # Save cache periodically
            with open(PMCID_CACHE, "w") as f:
                json.dump(pmc_to_pmid, f)
        
        # NCBI rate limit: 10/sec with API key, 3/sec without
        time.sleep(0.15 if NCBI_API_KEY else 0.4)
    
    # Final cache save
    with open(PMCID_CACHE, "w") as f:
        json.dump(pmc_to_pmid, f)
    
    print(f"  Done: {len(pmc_to_pmid):,} PMIDs (cached to {PMCID_CACHE.name})")
    return pmc_to_pmid


def fetch_citations_batch(pmids_list, pmc_to_pmid_reverse):
    """Fetch citation counts from Semantic Scholar batch API."""
    print(f"\n{'=' * 60}")
    print(f"Step 2: Fetching citations for {len(pmids_list):,} papers from S2")
    print(f"{'=' * 60}")
    
    results = {}  # pmcid -> {citationCount, year, ...}
    total = len(pmids_list)
    not_found = 0
    
    for i in range(0, total, S2_BATCH_SIZE):
        batch_pmids = pmids_list[i:i+S2_BATCH_SIZE]
        batch_ids = [f"PMID:{pmid}" for pmid in batch_pmids]
        
        url = "https://api.semanticscholar.org/graph/v1/paper/batch"
        params = "?fields=citationCount,year,externalIds"
        
        payload = json.dumps({"ids": batch_ids}).encode()
        
        for attempt in range(3):
            try:
                req = urllib.request.Request(
                    url + params,
                    data=payload,
                    headers={
                        "x-api-key": S2_API_KEY,
                        "Content-Type": "application/json",
                    },
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=60) as resp:
                    data = json.loads(resp.read().decode())
                
                for j, paper in enumerate(data):
                    pmid = batch_pmids[j]
                    pmcid = pmc_to_pmid_reverse.get(pmid, "")
                    
                    if paper is None:
                        not_found += 1
                        continue
                    
                    results[pmcid] = {
                        "citationCount": paper.get("citationCount", 0),
                        "year": paper.get("year"),
                        "s2_id": paper.get("paperId", ""),
                    }
                
                break
            except urllib.error.HTTPError as e:
                if e.code == 429:
                    wait = min(30, 2 ** (attempt + 2))
                    print(f"  Rate limited, waiting {wait}s...")
                    time.sleep(wait)
                elif attempt < 2:
                    time.sleep(2 ** attempt)
                else:
                    print(f"  WARN: Failed batch at {i}: {e}")
            except Exception as e:
                if attempt < 2:
                    time.sleep(2 ** attempt)
                else:
                    print(f"  WARN: Failed batch at {i}: {e}")
        
        if (i + S2_BATCH_SIZE) % 5000 == 0 or i + S2_BATCH_SIZE >= total:
            print(f"  Fetched {min(i+S2_BATCH_SIZE, total):,}/{total:,} "
                  f"({len(results):,} found, {not_found:,} not in S2)")
            
            # Save results & progress incrementally
            with open(OUTPUT, "w") as f:
                json.dump(results, f, ensure_ascii=False)
            with open(PROGRESS, "w") as f:
                json.dump({
                    "fetched": len(results),
                    "not_found": not_found,
                    "total": total,
                    "last_batch": i,
                }, f)
        
        time.sleep(RATE_LIMIT)
    
    print(f"\n  Done: {len(results):,} papers with citations, {not_found:,} not found")
    return results


def main():
    resume = "--resume" in sys.argv
    
    print(f"{'=' * 60}")
    print("Semantic Scholar Citation Fetcher")
    print(f"{'=' * 60}")
    print(f"Corpus: {CORPUS}")
    print(f"API Key: {S2_API_KEY[:8]}...")
    print(f"Rate limit: {RATE_LIMIT}s per request")
    
    # Load PMCIDs
    pmcids = load_pmcids()
    print(f"Total articles: {len(pmcids):,}")
    
    # Check for existing S2 results (for resume)
    existing_results = {}
    if OUTPUT.exists():
        with open(OUTPUT) as f:
            existing_results = json.load(f)
        print(f"Existing S2 results: {len(existing_results):,}")
    
    if len(existing_results) >= len(pmcids):
        print("All citations already fetched!")
        return
    
    # Step 1: PMCID → PMID
    pmc_to_pmid = convert_pmcid_to_pmid_batch(pmcids)
    
    # Reverse mapping: PMID → PMCID
    pmid_to_pmc = {v: k for k, v in pmc_to_pmid.items()}
    pmids_list = list(pmc_to_pmid.values())
    
    # Step 2: Fetch citations
    results = fetch_citations_batch(pmids_list, pmid_to_pmc)
    
    # Merge with existing
    results.update(existing_results)
    
    # Save
    with open(OUTPUT, "w") as f:
        json.dump(results, f, ensure_ascii=False)
    
    # Summary stats
    citations = [r["citationCount"] for r in results.values()]
    citations.sort()
    n = len(citations)
    
    print(f"\n{'=' * 60}")
    print("CITATION STATISTICS")
    print(f"{'=' * 60}")
    print(f"  Total papers with data: {n:,}")
    print(f"  Min:    {citations[0]:>8,}")
    print(f"  25th%:  {citations[n//4]:>8,}")
    print(f"  Median: {citations[n//2]:>8,}")
    print(f"  Mean:   {sum(citations)//n:>8,}")
    print(f"  75th%:  {citations[n*3//4]:>8,}")
    print(f"  95th%:  {citations[n*95//100]:>8,}")
    print(f"  Max:    {citations[-1]:>8,}")
    print(f"\n  Output: {OUTPUT}")
    
    # Year stats
    years = [r["year"] for r in results.values() if r.get("year")]
    if years:
        from collections import Counter
        yc = Counter(years)
        print(f"\n  Year range: {min(years)}-{max(years)}")
        print(f"  Top years: {', '.join(f'{y}({c:,})' for y, c in yc.most_common(5))}")


if __name__ == "__main__":
    main()
