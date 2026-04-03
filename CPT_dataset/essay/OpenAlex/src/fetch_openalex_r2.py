"""
FoodmoleGPT - Round 2 OpenAlex Journal-First Collector
=======================================================
Precision-first approach: collects papers directly from food science journals
using OpenAlex Source (journal) IDs instead of Concept IDs.

Key improvements over Round 1:
  - Source-level queries = entire journals, near 100% food-science purity
  - DOI deduplication against Round 1 data (master_cleaned.csv)
  - Resumable per-journal progress tracking

Usage:
    conda activate foodmole
    python src/fetch_openalex_r2.py              # Full collection
    python src/fetch_openalex_r2.py --test       # Test mode (50 papers/journal)

Output: D:\\FoodmoleGPT\\data\\raw\\openalex_r2\\
"""

import sys
import time
import json
import argparse
from pathlib import Path
from datetime import datetime
from typing import Optional

import pandas as pd
from tqdm import tqdm
import pyalex
from pyalex import Works

if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# Configure pyalex with polite pool
pyalex.config.email = "foodmolegpt@example.com"

# =============================================================================
# JOURNAL CONFIGURATION
# =============================================================================
# ~80 core food science journals with OpenAlex Source IDs.
# These are queried directly, guaranteeing high food-science purity.
#
# Source IDs are from OpenAlex (format: S<number>).
# You can verify any ID at: https://api.openalex.org/sources/S<number>

JOURNAL_CONFIGS = [
    # ---- Core Food Science ----
    # All Source IDs verified via OpenAlex Sources search API (2026-03-05)
    {"id": "S23579880",    "name": "Journal of Food Science"},
    {"id": "S98026630",    "name": "Food Chemistry"},
    {"id": "S38919146",    "name": "Food Research International"},
    {"id": "S134644764",   "name": "Journal of Agricultural and Food Chemistry"},
    {"id": "S26760650",    "name": "LWT"},
    {"id": "S89023782",    "name": "Trends in Food Science & Technology"},
    {"id": "S70620193",    "name": "Critical Reviews in Food Science and Nutrition"},
    {"id": "S336866",      "name": "Comprehensive Reviews in Food Science and Food Safety"},
    {"id": "S119525064",   "name": "Food Control"},
    {"id": "S168584722",   "name": "Food Hydrocolloids"},
    {"id": "S2737939966",  "name": "Foods"},
    {"id": "S181365921",   "name": "Food and Bioprocess Technology"},
    {"id": "S137362610",   "name": "Journal of Food Engineering"},
    {"id": "S66401815",    "name": "Journal of Food Protection"},
    {"id": "S194662844",   "name": "Food Quality and Preference"},
    {"id": "S25323420",    "name": "Journal of Food Composition and Analysis"},
    {"id": "S2483688756",  "name": "Food & Function"},
    {"id": "S132626406",   "name": "International Journal of Food Microbiology"},
    {"id": "S2764902628",  "name": "Food Science and Human Wellness"},
    {"id": "S2764726840",  "name": "Food Bioscience"},
    {"id": "S84231135",    "name": "Food and Chemical Toxicology"},
    {"id": "S169454776",   "name": "European Food Research and Technology"},
    {"id": "S206298197",   "name": "Journal of the Science of Food and Agriculture"},
    {"id": "S130676932",   "name": "Innovative Food Science & Emerging Technologies"},
    {"id": "S190445914",   "name": "Food Analytical Methods"},
    {"id": "S4210176327",  "name": "Food Additives & Contaminants"},
    {"id": "S4210169910",  "name": "Journal of Food Science and Technology"},
    {"id": "S188241495",   "name": "Journal of Food Processing and Preservation"},
    {"id": "S4210189394",  "name": "Food Chemistry X"},
    {"id": "S4210236938",  "name": "Current Research in Food Science"},
    {"id": "S4210228674",  "name": "Food Frontiers"},
    {"id": "S106123072",   "name": "Food Reviews International"},

    # ---- Meat / Dairy / Poultry ----
    {"id": "S9483105",     "name": "Meat Science"},
    {"id": "S28349394",    "name": "Journal of Dairy Science"},
    {"id": "S184773532",   "name": "International Dairy Journal"},
    {"id": "S133896805",   "name": "Poultry Science"},
    {"id": "S72684844",    "name": "Journal of Animal Science"},
    {"id": "S159932305",   "name": "Journal of Dairy Research"},

    # ---- Cereal / Grain ----
    {"id": "S2456228",     "name": "Journal of Cereal Science"},
    {"id": "S4210216257",  "name": "Cereal Chemistry"},

    # ---- Beverages / Fermentation ----
    {"id": "S74940757",    "name": "Journal of the Institute of Brewing"},
    {"id": "S192057034",   "name": "Journal of the American Society of Brewing Chemists"},
    {"id": "S14903550",    "name": "American Journal of Enology and Viticulture"},

    # ---- Nutrition ----
    {"id": "S110785341",   "name": "Nutrients"},
    {"id": "S88153332",    "name": "Journal of Nutrition"},
    {"id": "S4218381",     "name": "British Journal Of Nutrition"},
    {"id": "S71285955",    "name": "American Journal of Clinical Nutrition"},
    {"id": "S4210183135",  "name": "European Journal of Nutrition"},
    {"id": "S58312864",    "name": "International Journal of Food Sciences and Nutrition"},
    {"id": "S123713480",   "name": "Nutrition Research"},
    {"id": "S2764750965",  "name": "Advances in food and nutrition research"},
    {"id": "S548917",      "name": "The Journal of Nutritional Biochemistry"},

    # ---- Food Safety ----
    {"id": "S132853619",   "name": "Foodborne Pathogens and Disease"},
    {"id": "S146621905",   "name": "Journal of Food Safety"},

    # ---- Food Engineering / Packaging ----
    {"id": "S151747869",   "name": "Journal of Food Process Engineering"},
    {"id": "S115749436",   "name": "Food and Bioproducts Processing"},
    {"id": "S196498761",   "name": "Drying Technology"},
    {"id": "S2764480744",  "name": "Food Packaging and Shelf Life"},

    # ---- Agriculture / Postharvest ----
    {"id": "S70397842",    "name": "Postharvest Biology and Technology"},
    {"id": "S38637062",    "name": "Journal of the American Oil Chemists Society"},
    {"id": "S12429487",    "name": "The Journal of Agricultural Science"},
    {"id": "S104261359",   "name": "Aquaculture"},
    {"id": "S107471828",   "name": "Journal of Texture Studies"},
    {"id": "S21693283",    "name": "Journal of Sensory Studies"},

    # ---- Carbohydrate / Lipid / Bioactive ----
    {"id": "S64311837",    "name": "Carbohydrate Polymers"},
    {"id": "S34126442",    "name": "Carbohydrate Research"},
    {"id": "S8548135",     "name": "Journal of Functional Foods"},
    {"id": "S2898411350",  "name": "NFS Journal"},

    # ---- Food Chemistry adjacent ----
    {"id": "S88226677",    "name": "Phytochemistry"},
    {"id": "S83413509",    "name": "Flavour and Fragrance Journal"},
    {"id": "S88454195",    "name": "Journal of Essential Oil Research"},
    {"id": "S115623499",   "name": "Lipids"},

    # ---- Regional food journals ----
    {"id": "S20400310",    "name": "Italian Journal of Food Science"},
    {"id": "S13692971",    "name": "Czech Journal of Food Sciences"},
    {"id": "S2736999800",  "name": "Polish Journal of Food and Nutrition Sciences"},
]


# =============================================================================
# PATHS
# =============================================================================

OUTPUT_DIR = Path("D:/FoodmoleGPT/data/raw/openalex_r2")
R1_CLEANED = Path("D:/FoodmoleGPT/data/cleaned/master_cleaned.csv")
PROGRESS_FILE = OUTPUT_DIR / "progress.json"

# Pagination
BATCH_SIZE = 200


# =============================================================================
# HELPERS
# =============================================================================

def load_existing_dois() -> set:
    """Load all DOIs from Round 1 cleaned data to skip duplicates."""
    if not R1_CLEANED.exists():
        print("  ⚠️  Round 1 master_cleaned.csv not found, no dedup will be applied")
        return set()

    print(f"  Loading Round 1 DOIs from {R1_CLEANED}...")
    df = pd.read_csv(R1_CLEANED, usecols=["doi"], dtype=str)
    dois = set(df["doi"].dropna().str.strip().str.lower())
    print(f"  ✅ Loaded {len(dois):,} existing DOIs for dedup")
    return dois


def load_progress() -> dict:
    """Load per-journal progress for resumability."""
    if PROGRESS_FILE.exists():
        with open(PROGRESS_FILE, "r") as f:
            return json.load(f)
    return {"completed_journals": [], "total_new": 0, "total_skipped_dup": 0}


def save_progress(progress: dict):
    """Save progress."""
    with open(PROGRESS_FILE, "w") as f:
        json.dump(progress, f, indent=2)


def extract_work_data(work: dict, journal_name: str) -> dict:
    """Extract relevant fields from an OpenAlex work (same schema as Round 1)."""
    # Reconstruct abstract from inverted index
    abstract = None
    if work.get("abstract_inverted_index"):
        try:
            inverted = work["abstract_inverted_index"]
            if inverted:
                max_pos = max(max(positions) for positions in inverted.values())
                abstract_words = [""] * (max_pos + 1)
                for word, positions in inverted.items():
                    for pos in positions:
                        abstract_words[pos] = word
                abstract = " ".join(abstract_words)
        except (ValueError, TypeError):
            abstract = None

    # Author names (limit to 10)
    authors = []
    if work.get("authorships"):
        for authorship in work["authorships"][:10]:
            author = authorship.get("author", {})
            if author.get("display_name"):
                authors.append(author["display_name"])

    # Concepts/keywords
    keywords = []
    if work.get("concepts"):
        keywords = [c["display_name"] for c in work["concepts"][:10]
                    if c.get("display_name")]

    # Venue
    venue = None
    if work.get("primary_location"):
        source = work["primary_location"].get("source")
        if source:
            venue = source.get("display_name")

    # Institutions
    institutions = []
    if work.get("authorships"):
        for authorship in work["authorships"][:5]:
            for inst in authorship.get("institutions", [])[:2]:
                if inst.get("display_name"):
                    institutions.append(inst["display_name"])

    return {
        "openalex_id": work.get("id", "").replace("https://openalex.org/", ""),
        "doi": (work.get("doi", "").replace("https://doi.org/", "")
                if work.get("doi") else None),
        "title": work.get("title"),
        "abstract": abstract,
        "publication_year": work.get("publication_year"),
        "publication_date": work.get("publication_date"),
        "venue": venue,
        "cited_by_count": work.get("cited_by_count", 0),
        "authors": "; ".join(authors) if authors else None,
        "institutions": "; ".join(list(set(institutions))[:5]) if institutions else None,
        "keywords": "; ".join(keywords) if keywords else None,
        "is_open_access": work.get("open_access", {}).get("is_oa", False),
        "type": work.get("type"),
        "language": work.get("language"),
        "primary_concept": journal_name,  # Re-use field, stores source journal
    }


# =============================================================================
# COLLECTION
# =============================================================================

def collect_by_journal(
    source_id: str,
    journal_name: str,
    existing_dois: set,
    require_abstract: bool = True,
    max_papers: Optional[int] = None,
) -> pd.DataFrame:
    """
    Collect all papers from a specific OpenAlex journal/source.

    Args:
        source_id: OpenAlex Source ID (e.g., "S134246888")
        journal_name: Human-readable journal name
        existing_dois: Set of DOIs to skip (Round 1 dedup)
        require_abstract: If True, only collect papers with abstracts
        max_papers: Max papers per journal (None = unlimited)

    Returns:
        DataFrame of new (non-duplicate) papers
    """
    print(f"\n{'='*70}")
    print(f"📚 {journal_name}")
    print(f"   Source ID: {source_id}")

    all_works = []
    seen_ids = set()
    skipped_dup = 0

    # Build query — filter by source (journal)
    query = Works().filter(
        primary_location={"source": {"id": source_id}},
    )

    if require_abstract:
        query = query.filter(has_abstract=True)

    # Sort by citation count (most impactful first)
    query = query.sort(cited_by_count="desc")

    try:
        total_available = query.count()
        target = min(max_papers, total_available) if max_papers else total_available
        print(f"   Available: {total_available:,} | Target: {target:,}")
        sys.stdout.flush()

        pbar = tqdm(total=target, desc=f"   {journal_name[:30]}", unit="papers")

        for page in query.paginate(per_page=BATCH_SIZE, n_max=max_papers or 10_000_000):
            for work in page:
                work_id = work.get("id")
                if not work_id or work_id in seen_ids:
                    continue
                seen_ids.add(work_id)

                # DOI dedup against Round 1
                doi_raw = work.get("doi")
                if doi_raw:
                    doi_clean = doi_raw.replace("https://doi.org/", "").strip().lower()
                    if doi_clean in existing_dois:
                        skipped_dup += 1
                        pbar.update(1)
                        continue

                all_works.append(extract_work_data(work, journal_name))
                pbar.update(1)

                if max_papers and (len(all_works) + skipped_dup) >= max_papers:
                    break

            if max_papers and (len(all_works) + skipped_dup) >= max_papers:
                break

            time.sleep(0.02)  # Rate limiting

        pbar.close()

    except Exception as e:
        print(f"   ❌ Error: {str(e)[:120]}")
        return pd.DataFrame(), skipped_dup

    if not all_works:
        print(f"   ✅ 0 new papers (skipped {skipped_dup:,} duplicates)")
        return pd.DataFrame(), skipped_dup

    df = pd.DataFrame(all_works)
    df["fetch_date"] = datetime.now().isoformat()

    abstract_count = df["abstract"].notna().sum()
    print(f"   ✅ New: {len(df):,} papers | Abstracts: {abstract_count:,} | Skipped dups: {skipped_dup:,}")

    return df, skipped_dup


def run_collection(
    require_abstract: bool = True,
    max_per_journal: Optional[int] = None,
    test_mode: bool = False,
):
    """
    Main collection loop: iterate through all journals.

    Args:
        require_abstract: Only collect papers with abstracts
        max_per_journal: Max papers per journal (None = unlimited)
        test_mode: If True, collect only 50 papers per journal
    """
    if test_mode:
        max_per_journal = 50
        print("\n⚠️  TEST MODE: limited to 50 papers per journal\n")

    print("=" * 70)
    print("🚀 FoodmoleGPT Round 2 - Journal-First Collection")
    print("=" * 70)
    print(f"   Start:       {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"   Journals:    {len(JOURNAL_CONFIGS)}")
    print(f"   Output:      {OUTPUT_DIR}")
    print(f"   Abstracts:   {'required' if require_abstract else 'optional'}")
    print(f"   Max/journal: {max_per_journal or 'unlimited'}")
    sys.stdout.flush()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "by_journal").mkdir(exist_ok=True)

    # Load Round 1 DOIs for dedup
    existing_dois = load_existing_dois()

    # Load progress for resume
    progress = load_progress()
    completed = set(progress["completed_journals"])
    total_new = progress["total_new"]
    total_skipped = progress["total_skipped_dup"]

    if completed:
        print(f"\n   ⏩ Resuming: {len(completed)} journals already completed")
        print(f"      Previously collected: {total_new:,} new, {total_skipped:,} skipped")

    all_data = []

    for i, journal in enumerate(JOURNAL_CONFIGS, 1):
        jid = journal["id"]
        jname = journal["name"]

        if jid in completed:
            print(f"\n   [{i}/{len(JOURNAL_CONFIGS)}] ⏭️  {jname} (already done)")
            continue

        print(f"\n   [{i}/{len(JOURNAL_CONFIGS)}]", end="")

        df, skipped = collect_by_journal(
            source_id=jid,
            journal_name=jname,
            existing_dois=existing_dois,
            require_abstract=require_abstract,
            max_papers=max_per_journal,
        )

        if not df.empty:
            # Save individual journal file
            safe_name = jname.replace(" ", "_").replace("/", "_").replace(":", "")[:50]
            output_file = OUTPUT_DIR / "by_journal" / f"{jid}_{safe_name}.csv"
            df.to_csv(output_file, index=False, encoding="utf-8-sig")

            # Add DOIs from this batch to dedup set so future journals skip them too
            new_dois = df["doi"].dropna().str.strip().str.lower()
            existing_dois.update(new_dois)

            all_data.append(df)
            total_new += len(df)

        total_skipped += skipped

        # Update progress
        completed.add(jid)
        progress["completed_journals"] = list(completed)
        progress["total_new"] = total_new
        progress["total_skipped_dup"] = total_skipped
        save_progress(progress)

    # ---------- Master file ----------
    print("\n" + "=" * 70)
    print("📊 CREATING MASTER FILE")
    print("=" * 70)

    if all_data:
        master_df = pd.concat(all_data, ignore_index=True)

        # Final dedup by openalex_id (cross-journal duplicates are unlikely but possible)
        before = len(master_df)
        master_df = master_df.drop_duplicates(subset=["openalex_id"], keep="first")
        if before != len(master_df):
            print(f"   Cross-journal dedup: {before:,} → {len(master_df):,}")

        # Citation tier
        master_df["tier"] = master_df["cited_by_count"].apply(
            lambda x: 1 if x >= 50 else (2 if x >= 10 else 3)
        )

        master_file = OUTPUT_DIR / "master_r2_openalex.csv"
        master_df.to_csv(master_file, index=False, encoding="utf-8-sig")

        print(f"\n   📊 ROUND 2 STATISTICS:")
        print(f"   Total new papers:     {len(master_df):,}")
        print(f"   With abstracts:       {master_df['abstract'].notna().sum():,}")
        print(f"   With DOI:             {master_df['doi'].notna().sum():,}")
        print(f"   Skipped (R1 dedup):   {total_skipped:,}")
        print(f"   Tier 1 (≥50 cites):   {(master_df['tier'] == 1).sum():,}")
        print(f"   Tier 2 (≥10 cites):   {(master_df['tier'] == 2).sum():,}")
        print(f"   Tier 3 (<10 cites):   {(master_df['tier'] == 3).sum():,}")
        print(f"\n   Top journals:")
        for jname, count in master_df["primary_concept"].value_counts().head(15).items():
            print(f"      {count:>8,}  {jname}")
        print(f"\n   Master file: {master_file}")
        print(f"   File size: {master_file.stat().st_size / 1024 / 1024:.1f} MB")
    else:
        print("   ⚠️  No new papers collected")

    print(f"\n   End time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)
    print("✅ Round 2 collection complete!")
    sys.stdout.flush()


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="FoodmoleGPT Round 2 Collection")
    parser.add_argument("--test", action="store_true",
                        help="Test mode: 50 papers per journal")
    parser.add_argument("--max-per-journal", type=int, default=None,
                        help="Max papers per journal (default: unlimited)")
    parser.add_argument("--no-abstract", action="store_true",
                        help="Also collect papers without abstracts")
    args = parser.parse_args()

    run_collection(
        require_abstract=not args.no_abstract,
        max_per_journal=args.max_per_journal,
        test_mode=args.test,
    )
