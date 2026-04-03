#!/usr/bin/env python3
"""
PMC E-search Collector for FoodmoleGPT Dataset Expansion
=========================================================
Use NCBI E-utilities esearch to collect PMCIDs based on 10 MeSH-based
search strategies from the advisor's PMC_Search_Guide.

Usage:
    python pmc_esearch_collector.py [--dry-run] [--max-per-strategy N]

Author: FoodmoleGPT Team
"""

import json
import logging
import argparse
import time
from pathlib import Path
from typing import Dict, List, Set

from Bio import Entrez
from tqdm import tqdm

import config


# =============================================================================
# 10 MeSH-based Search Strategies (from PMC_Search_Guide.md)
# =============================================================================

SEARCH_STRATEGIES: List[Dict[str, str]] = [
    {
        "id": 1,
        "name": "Food Chemistry",
        "query": (
            '("Food Chemistry"[MeSH Terms] OR "Food Composition"[MeSH Terms]'
            ' OR "Food Functional Ingredients"[Title/Abstract] OR "Polyphenols"[Title/Abstract] OR "Food Antioxidants"[Title/Abstract]'
            ' OR "Flavones"[Title/Abstract] OR "Flavonols"[Title/Abstract] OR "Maillard Reaction"[Title/Abstract] OR "Food Emulsions"[Title/Abstract]'
            ' OR "Food Hydrocolloids"[Title/Abstract] OR ("Chemical reactions"[Title/Abstract] AND "Food"[Title/Abstract]))'
            " AND open access[Filter]"
        ),
    },
    {
        "id": 2,
        "name": "Food Safety and Toxicology",
        "query": (
            '("Food Safety"[MeSH Terms] OR "Food Contamination"[MeSH Terms] OR "Foodborne Diseases"[MeSH Terms]'
            ' OR "Foodborne Pathogens"[Title/Abstract] OR "Food Toxicology"[Title/Abstract] OR "Pesticide Residues"[Title/Abstract]'
            ' OR ("Heavy Metals"[Title/Abstract] AND "Food"[Title/Abstract]) OR "Mycotoxins"[Title/Abstract] OR "Food Allergens"[Title/Abstract]'
            ' OR "Food Adulteration"[Title/Abstract] OR "HACCP"[Title/Abstract] OR "Antimicrobial Resistance in Food"[Title/Abstract])'
            " AND open access[Filter]"
        ),
    },
    {
        "id": 3,
        "name": "Food Nutrition and Health",
        "query": (
            '("Nutrition"[MeSH Terms] OR "Functional Foods"[MeSH Terms] OR "Dietary Supplements"[MeSH Terms]'
            ' OR "Nutraceuticals"[Title/Abstract] OR "Dietary Bioactives"[Title/Abstract] OR "Gut Microbiota"[MeSH Terms]'
            ' OR "Omega-3 Fatty Acids"[MeSH Terms] OR "Mediterranean Diet"[Title/Abstract] OR "Plant-Based Diet"[Title/Abstract]'
            ' OR "Metabolomics and Nutrition"[Title/Abstract] OR "Precision Nutrition"[Title/Abstract] OR "Obesity and Diet"[Title/Abstract])'
            " AND open access[Filter]"
        ),
    },
    {
        "id": 4,
        "name": "Food Flavor and Sensory Science",
        "query": (
            '("Food Flavor"[MeSH Terms] OR "Taste Perception"[MeSH Terms] OR "Food Sensory"[Title/Abstract]'
            ' OR "Flavor"[Title] OR "Flavour"[Title] OR "Food Aroma"[Title/Abstract] OR "Mouthfeel"[Title/Abstract] OR "Volatiles"[Title/Abstract] OR "Taste Molecules"[Title/Abstract] OR "Aroma Molecules"[Title/Abstract] OR "Flavour Molecules"[Title/Abstract]'
            ' OR "Flavor Perception"[Title/Abstract] OR "Flavour Perception"[Title/Abstract] OR "Food Perception"[Title/Abstract] OR "Food Palatability"[Title/Abstract] OR "Molecular Gastronomy"[Title/Abstract])'
            " AND open access[Filter]"
        ),
    },
    {
        "id": 5,
        "name": "Food Processing and Engineering",
        "query": (
            '("Food Processing"[MeSH Terms] OR "Food Engineering"[Title/Abstract] OR "Thermal Processing"[Title/Abstract] OR "Non-Thermal Food Processing"[Title/Abstract]'
            ' OR "High Pressure Processing"[Title/Abstract] OR "Microwave Processing"[Title/Abstract] OR "Freeze Drying"[Title/Abstract] OR "Food Packaging"[Title/Abstract]'
            ' OR "Food Preservation"[MeSH Terms] OR "Food Storage"[Title/Abstract] OR "Food Rheology"[Title/Abstract] OR "Food Nanotechnology"[Title/Abstract] OR "3D Food Printing"[Title/Abstract] OR "Food Emulsion"[Title/Abstract] OR "Ultrasound Processing"[Title/Abstract] OR "Infrared Drying"[Title/Abstract]'
            ' OR "Food Encapsulation"[Title/Abstract])'
            " AND open access[Filter]"
        ),
    },
    {
        "id": 6,
        "name": "Food Microbiology & Biotechnology",
        "query": (
            '("Food Microbiology"[MeSH Terms] OR "Probiotics"[MeSH Terms] OR "Prebiotics"[MeSH Terms]'
            ' OR "Foodborne Microbes"[Title/Abstract] OR "Food Spoilage"[MeSH Terms]'
            ' OR "Food Fermentation"[Title/Abstract] OR "Food Synthetic Biology"[Title/Abstract] OR "Food Biotransformation"[Title/Abstract]'
            ' OR "Food Bioprocessing"[Title/Abstract] OR "Food Enzymes"[Title/Abstract]'
            ' OR ("Amylases"[Title/Abstract] AND "Food"[Title/Abstract]) OR ("Proteases"[Title/Abstract] AND "Food"[Title/Abstract]) OR ("Lipases"[Title/Abstract] AND "Food"[Title/Abstract])'
            ' OR "Biopreservation"[Title/Abstract] OR "Food Microbiome"[Title/Abstract] OR ("CRISPR"[Title/Abstract] AND "Food"[Title/Abstract]) OR ("Genome Editing"[Title/Abstract] AND "Food"[Title/Abstract]) OR ("Genome Editing"[Title/Abstract] AND "Crops"[Title/Abstract]) OR "Gene-edited Crops"[Title/Abstract])'
            " AND open access[Filter]"
        ),
    },
    {
        "id": 7,
        "name": "Food Informatics & AI in Food Science",
        "query": (
            '(("Artificial Intelligence"[MeSH Terms] AND "Food Industry"[MeSH Terms]) OR ("Cheminformatics"[Title/Abstract] AND "Food"[Title/Abstract])'
            ' OR ("Bioinformatics"[Title/Abstract] AND "Food"[Title/Abstract]) OR ("Machine Learning"[Title/Abstract] AND "Food"[Title/Abstract])'
            ' OR ("Blockchain"[Title/Abstract] AND "Food"[Title/Abstract]) OR ("Predictive Modeling"[Title/Abstract] AND "Food"[Title/Abstract])'
            ' OR "Computational Food"[Title/Abstract] OR "Food Computing"[Title/Abstract])'
            " AND open access[Filter]"
        ),
    },
    {
        "id": 8,
        "name": "Food Education & Public Engagement",
        "query": (
            '("Food Education"[Title/Abstract] OR "Food Literacy"[Title/Abstract] OR "Nutrition Education"[MeSH Terms]'
            ' OR "Public Health and Diet"[Title/Abstract] OR "Food System Education"[Title/Abstract] OR "School Nutrition Programs"[MeSH Terms])'
            " AND open access[Filter]"
        ),
    },
    {
        "id": 9,
        "name": "Sustainable Food Systems & Climate Change",
        "query": (
            '(("Life Cycle Assessment"[Title/Abstract] AND "Food"[Title/Abstract]) OR ("Circular Economy"[Title/Abstract] AND "Food"[Title/Abstract])'
            ' OR ("Carbon Footprint"[Title/Abstract] AND "Food"[Title/Abstract]) OR "Sustainable Food Systems"[Title/Abstract]'
            ' OR ("Climate Change"[Title/Abstract] AND "Food"[Title]) OR "Agroecology"[Title/Abstract] OR "Sustainable Packaging"[Title/Abstract]'
            ' OR "Regenerative Agriculture"[Title/Abstract] OR "Sustainable Agriculture"[Title/Abstract])'
            " AND open access[Filter]"
        ),
    },
    {
        "id": 10,
        "name": "Alternative Proteins & Future Foods",
        "query": (
            '("Alternative Proteins"[Title/Abstract] OR "Plant-Based Meat"[Title/Abstract] OR "Cultivated Meat"[Title/Abstract]'
            ' OR "Insect-Based Food"[Title/Abstract] OR "Black Soldier Fly Protein"[Title/Abstract] OR "Macroalgae Proteins"[Title/Abstract]'
            ' OR "Cellular Agriculture"[Title/Abstract] OR "Microbial Protein Production"[Title/Abstract] OR "Protein Sustainability"[Title/Abstract]'
            ' OR "Future Foods"[Title/Abstract] OR "Novel Protein Sources"[Title/Abstract]'
            ' OR "Lab-Grown Meat"[Title/Abstract] OR "Fermentation-Derived Proteins"[Title/Abstract]'
            ' OR "Edible Insects"[Title/Abstract] OR "Sustainable Proteins"[Title/Abstract] OR "Algae-Based Foods"[Title/Abstract])'
            " AND open access[Filter]"
        ),
    },
]


# =============================================================================
# Setup
# =============================================================================

def setup_entrez():
    """Configure Entrez with email and API key."""
    Entrez.email = config.NCBI_EMAIL
    Entrez.tool = config.NCBI_TOOL
    if config.NCBI_API_KEY:
        Entrez.api_key = config.NCBI_API_KEY


def setup_logging() -> logging.Logger:
    logger = logging.getLogger("PMCCollector")
    logger.setLevel(logging.DEBUG)
    logger.handlers = []

    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter("%(asctime)s - %(message)s", datefmt="%H:%M:%S"))
    logger.addHandler(ch)
    return logger


# =============================================================================
# E-search Functions
# =============================================================================

def _api_call(func, *args, max_retries=5, **kwargs):
    """Wrapper with retry / backoff for NCBI API calls."""
    for attempt in range(max_retries):
        try:
            time.sleep(0.15)  # Base rate limit
            return func(*args, **kwargs)
        except Exception as e:
            err_str = str(e)
            if "429" in err_str or "Too Many Requests" in err_str or "503" in err_str:
                wait = min(2 ** attempt * 2, 30)
                logging.getLogger("PMCCollector").warning(
                    f"  Rate-limited (attempt {attempt+1}/{max_retries}), waiting {wait}s..."
                )
                time.sleep(wait)
            else:
                if attempt < max_retries - 1:
                    time.sleep(2)
                else:
                    raise


def esearch_count(query: str) -> int:
    """Get total hit count for a query without fetching IDs."""
    handle = _api_call(Entrez.esearch, db="pmc", term=query, retmax=0, usehistory="n")
    result = Entrez.read(handle)
    handle.close()
    return int(result["Count"])


def _esearch_ids_single(query: str, max_results: int = 9999) -> List[str]:
    """
    Fetch up to max_results PMCIDs via a single esearch call.
    NCBI esearch retmax is capped at 9,999 for PMC.
    """
    retmax = min(max_results, 9999)
    handle = _api_call(Entrez.esearch, db="pmc", term=query, retmax=retmax, usehistory="n")
    result = Entrez.read(handle)
    handle.close()
    ids = result.get("IdList", [])
    return [f"PMC{id_}" for id_ in ids]


def _collect_range(base_query: str, start_year: int, end_year: int,
                   seen: Set[str], all_ids: List[str],
                   logger: logging.Logger = None, depth: int = 0) -> None:
    """
    Recursively collect IDs for a date range.
    If range has ≤ 9999 results, fetch directly.
    Otherwise, split range in half and recurse.
    """
    if start_year == end_year:
        range_query = f'({base_query}) AND ("{start_year}"[pdat])'
    else:
        range_query = (
            f'({base_query}) AND ("{start_year}/01/01"[pdat] : "{end_year}/12/31"[pdat])'
        )

    count = esearch_count(range_query)
    if count == 0:
        return

    if count <= 9999:
        ids = _esearch_ids_single(range_query, count)
        for pid in ids:
            if pid not in seen:
                seen.add(pid)
                all_ids.append(pid)
        if logger:
            logger.info(
                f"  {'  ' * depth}[{start_year}-{end_year}] "
                f"{count:,} hits → total {len(all_ids):,}"
            )
        return

    # Split in half
    if start_year == end_year:
        # Single year but > 9999: split by half-year
        for start_m, end_m in [("01/01", "06/30"), ("07/01", "12/31")]:
            half_q = (
                f'({base_query}) AND '
                f'("{start_year}/{start_m}"[pdat] : "{start_year}/{end_m}"[pdat])'
            )
            half_count = esearch_count(half_q)
            if half_count == 0:
                continue
            if half_count <= 9999:
                ids = _esearch_ids_single(half_q, half_count)
                for pid in ids:
                    if pid not in seen:
                        seen.add(pid)
                        all_ids.append(pid)
                if logger:
                    logger.info(
                        f"  {'  ' * depth}[{start_year} H] "
                        f"{half_count:,} hits → total {len(all_ids):,}"
                    )
            else:
                # Extremely rare: > 9999 in half year, just get 9999
                ids = _esearch_ids_single(half_q, 9999)
                for pid in ids:
                    if pid not in seen:
                        seen.add(pid)
                        all_ids.append(pid)
                if logger:
                    logger.warning(
                        f"  {'  ' * depth}[{start_year} H] "
                        f"capped at 9,999 (actual {half_count:,})"
                    )
        return

    mid = (start_year + end_year) // 2
    _collect_range(base_query, start_year, mid, seen, all_ids, logger, depth + 1)
    _collect_range(base_query, mid + 1, end_year, seen, all_ids, logger, depth + 1)


def esearch_all_ids(query: str, max_results: int = None,
                    logger: logging.Logger = None) -> List[str]:
    """
    Fetch all PMCIDs for a query.

    Uses adaptive date-range splitting for queries > 9,999 hits.
    """
    total = esearch_count(query)

    if max_results:
        effective = min(total, max_results)
    else:
        effective = total

    if logger:
        logger.info(f"  Total count: {total:,}")

    if effective <= 9999:
        if logger:
            logger.info(f"  Fetching {effective:,} IDs (single batch)...")
        return _esearch_ids_single(query, effective)

    # Adaptive subdivision
    if logger:
        logger.info(f"  > 9,999 hits — adaptive date-range splitting...")

    import datetime
    current_year = datetime.datetime.now().year

    all_ids: List[str] = []
    seen: Set[str] = set()

    _collect_range(query, 1900, current_year, seen, all_ids, logger)

    if max_results and len(all_ids) > max_results:
        all_ids = all_ids[:max_results]

    if logger:
        logger.info(f"  Collected {len(all_ids):,} unique IDs")

    return all_ids


def load_existing_pmcids(xml_dir: Path) -> Set[str]:
    """Load PMCIDs of already-downloaded XML files."""
    existing = set()
    if xml_dir.exists():
        for f in xml_dir.glob("PMC*.xml"):
            if f.stat().st_size > 100:
                existing.add(f.stem)  # e.g., "PMC10000368"
    return existing


# =============================================================================
# Main
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Collect PMCIDs via NCBI E-search for dataset expansion"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only show hit counts per strategy, don't fetch IDs",
    )
    parser.add_argument(
        "--max-per-strategy", "-m",
        type=int,
        default=None,
        help="Cap on PMCIDs per strategy (default: no cap)",
    )
    parser.add_argument(
        "--output", "-o",
        type=str,
        default="data/expansion_pmcids.json",
        help="Output JSON file for collected PMCIDs",
    )
    parser.add_argument(
        "--existing-xml-dir",
        type=str,
        default="data/xml",
        help="Directory of existing XMLs to skip (dedup)",
    )
    parser.add_argument(
        "--strategies",
        type=str,
        default=None,
        help="Comma-separated strategy IDs to run (e.g., '1,3,5'). Default: all",
    )
    args = parser.parse_args()

    logger = setup_logging()
    setup_entrez()

    script_dir = Path(__file__).parent

    logger.info("=" * 60)
    logger.info("PMC E-search Collector for Dataset Expansion")
    logger.info("=" * 60)

    # Parse strategy IDs
    if args.strategies:
        selected_ids = set(int(x.strip()) for x in args.strategies.split(","))
        strategies = [s for s in SEARCH_STRATEGIES if s["id"] in selected_ids]
    else:
        strategies = SEARCH_STRATEGIES

    # ── Dry-run mode: just show counts ──
    if args.dry_run:
        logger.info("\n[DRY-RUN] Querying hit counts per strategy...\n")
        total_all = 0
        for s in strategies:
            time.sleep(0.11)
            count = esearch_count(s["query"])
            total_all += count
            logger.info(f"  Strategy {s['id']:2d} | {s['name']:<45s} | {count:>9,} hits")
        logger.info(f"\n  {'TOTAL (with overlaps)':<50s} | {total_all:>9,}")
        logger.info("\nNote: strategies may share overlapping PMCIDs.")
        return

    # ── Full mode: collect all IDs ──
    existing_xml_dir = Path(args.existing_xml_dir)
    if not existing_xml_dir.is_absolute():
        existing_xml_dir = script_dir / existing_xml_dir

    logger.info("Loading existing PMCIDs for dedup...")
    existing_ids = load_existing_pmcids(existing_xml_dir)
    logger.info(f"  Found {len(existing_ids):,} existing XML files")

    all_new_ids: Set[str] = set()
    strategy_stats = []

    for s in strategies:
        logger.info(f"\n{'─' * 50}")
        logger.info(f"Strategy {s['id']}: {s['name']}")
        logger.info(f"{'─' * 50}")

        ids = esearch_all_ids(
            s["query"],
            max_results=args.max_per_strategy,
            logger=logger,
        )
        total_hits = len(ids)

        # Remove already-downloaded
        new_ids = set(ids) - existing_ids
        # Remove already collected by previous strategies
        truly_new = new_ids - all_new_ids
        all_new_ids.update(truly_new)

        stat = {
            "strategy_id": s["id"],
            "strategy_name": s["name"],
            "total_hits": total_hits,
            "after_dedup_existing": len(new_ids),
            "truly_new_unique": len(truly_new),
        }
        strategy_stats.append(stat)

        logger.info(f"  Total hits: {total_hits:,}")
        logger.info(f"  After removing existing: {len(new_ids):,}")
        logger.info(f"  Truly new (cross-strategy dedup): {len(truly_new):,}")

    # ── Save results ──
    output_path = Path(args.output)
    if not output_path.is_absolute():
        output_path = script_dir / output_path

    output_path.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "collection_date": time.strftime("%Y-%m-%d %H:%M:%S"),
        "existing_count": len(existing_ids),
        "max_per_strategy": args.max_per_strategy,
        "total_new_unique": len(all_new_ids),
        "strategy_stats": strategy_stats,
        "pmcids": sorted(all_new_ids),
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    logger.info(f"\n{'=' * 60}")
    logger.info(f"Collection complete!")
    logger.info(f"  Total new unique PMCIDs: {len(all_new_ids):,}")
    logger.info(f"  Saved to: {output_path}")
    logger.info(f"{'=' * 60}")

    # Print summary table
    logger.info("\nStrategy Summary:")
    logger.info(f"  {'ID':>3s} | {'Name':<45s} | {'Hits':>9s} | {'New':>9s}")
    logger.info(f"  {'─' * 3} | {'─' * 45} | {'─' * 9} | {'─' * 9}")
    for stat in strategy_stats:
        logger.info(
            f"  {stat['strategy_id']:3d} | {stat['strategy_name']:<45s} | "
            f"{stat['total_hits']:>9,} | {stat['truly_new_unique']:>9,}"
        )
    logger.info(
        f"  {'':>3s} | {'TOTAL':<45s} | {'':>9s} | {len(all_new_ids):>9,}"
    )


if __name__ == "__main__":
    main()
