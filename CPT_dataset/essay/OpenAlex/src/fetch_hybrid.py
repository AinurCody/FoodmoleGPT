"""
FoodmoleGPT - Hybrid Collection Script
=======================================
Step 1: Tests which OpenAlex Concept IDs still return data
Step 2: Uses working Concept IDs + search fallback for maximum coverage
Step 3: Deduplicates against existing 303K papers

Rate limiting: Uses conservative delays to avoid hitting daily limits.
OpenAlex credits reset at midnight UTC (8:00 AM Beijing time).

Usage:
    conda activate foodmole
    python src/fetch_hybrid.py

Output: D:\FoodmoleGPT\data\raw\openalex_concepts\
"""

import time
import requests
from pathlib import Path
from datetime import datetime
from typing import Optional

import pandas as pd
from tqdm import tqdm
import pyalex
from pyalex import Works

pyalex.config.email = "foodmolegpt@example.com"

# =============================================================================
# CONFIGURATION
# =============================================================================

OUTPUT_DIR = Path("D:/FoodmoleGPT/data/raw/openalex_concepts")
CONCEPT_DIR = OUTPUT_DIR / "by_concept"

MIN_YEAR = 2010
MAX_YEAR = 2026
BATCH_SIZE = 200

# Conservative delay between pages to avoid rate limits (seconds)
PAGE_DELAY = 0.1

# Max retries for network errors
MAX_RETRIES = 3
RETRY_WAITS = [15, 45, 90]

# =============================================================================
# CONCEPT IDS TO TEST
# =============================================================================

CANDIDATE_CONCEPTS = [
    # Original 5
    ("C300806122", "Food Science"),
    ("C185592680", "Food Chemistry"),
    ("C159062612", "Food Engineering"),
    ("C107768578", "Food Microbiology"),
    ("C2776043033", "Nutrition"),
    # Extended food science concepts
    ("C71475641", "Food Safety"),
    ("C166467938", "Fermentation"),
    ("C523546767", "Shelf Life"),
    ("C2778554886", "Functional Food"),
    ("C8860382", "Probiotic"),
    ("C134362898", "Antioxidant"),
    ("C173007530", "Milk"),
    ("C41008148", "Sensory Evaluation"),
    ("C97355855", "Fatty Acid"),
    ("C86339819", "Starch"),
    ("C6999642", "Packaging and Labeling"),
    ("C126322002", "Emulsion"),
    ("C153294291", "Vitamin"),
    ("C502942594", "Bioavailability"),
    ("C2776276882", "Polyphenol"),
    ("C2779356", "Protein"),
    ("C55493867", "Antibacterial"),
]

# Search terms as fallback for domains not covered by working concepts
FALLBACK_SEARCH_TERMS = [
    # Food Microbiology
    ("probiotics gut health", "food_microbiology", 10000),
    ("lactic acid bacteria fermentation", "food_microbiology", 10000),
    ("foodborne pathogen detection", "food_microbiology", 10000),
    ("food spoilage microorganisms", "food_microbiology", 8000),
    ("fermented food microbiome", "food_microbiology", 8000),
    ("listeria salmonella food contamination", "food_microbiology", 8000),
    # Nutrition
    ("nutraceuticals health benefits", "nutrition", 10000),
    ("dietary fiber prebiotic", "nutrition", 10000),
    ("bioavailability nutrients absorption", "nutrition", 8000),
    ("food fortification micronutrient", "nutrition", 8000),
    ("glycemic index diabetes food", "nutrition", 8000),
    ("gut microbiota diet", "nutrition", 10000),
    ("omega-3 fatty acids health", "nutrition", 8000),
    # Food Safety
    ("mycotoxin contamination cereals", "food_safety", 8000),
    ("pesticide residue fruit vegetable", "food_safety", 8000),
    ("heavy metal contamination food", "food_safety", 8000),
    ("food allergen detection", "food_safety", 8000),
    ("food adulteration authentication", "food_safety", 8000),
    # Food Engineering
    ("high pressure processing food", "food_engineering", 8000),
    ("ultrasound food processing", "food_engineering", 8000),
    ("microencapsulation food ingredient", "food_engineering", 8000),
    ("spray drying food powder", "food_engineering", 8000),
    ("nanoemulsion food delivery", "food_engineering", 8000),
    ("cold plasma food decontamination", "food_engineering", 5000),
    # Food Analysis
    ("HPLC food analysis", "food_analysis", 8000),
    ("mass spectrometry food metabolomics", "food_analysis", 8000),
    ("NIR spectroscopy food quality", "food_analysis", 8000),
    ("biosensor food detection", "food_analysis", 8000),
    # Dairy
    ("cheese ripening microbiology", "dairy", 5000),
    ("yogurt probiotic fermentation", "dairy", 5000),
    ("whey protein isolate", "dairy", 8000),
    # Meat & Seafood
    ("meat quality tenderness", "meat_seafood", 8000),
    ("fish freshness quality storage", "meat_seafood", 5000),
    ("aquaculture fish nutrition", "meat_seafood", 5000),
    # Plant-based
    ("plant-based meat alternative protein", "plant_based", 5000),
    ("edible insect protein food", "plant_based", 5000),
    # Cereal & Bakery
    ("wheat flour gluten bread", "cereal_bakery", 8000),
    ("starch modification food", "cereal_bakery", 5000),
    # Oils
    ("edible oil oxidation stability", "oils_fats", 5000),
    ("olive oil quality phenolic", "oils_fats", 5000),
    ("essential oil food preservation", "oils_fats", 5000),
    # Packaging
    ("active intelligent food packaging", "food_packaging", 5000),
    ("biodegradable food packaging", "food_packaging", 5000),
    ("edible film coating food", "food_packaging", 5000),
    # Sensory
    ("sensory evaluation food product", "sensory", 5000),
    ("flavor volatile compound food", "sensory", 5000),
]


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def check_rate_limit() -> bool:
    """Check if API is available (not rate-limited)."""
    try:
        r = requests.get(
            "https://api.openalex.org/works",
            params={"search": "food", "per_page": "1", "mailto": "foodmolegpt@example.com"},
            timeout=10,
        )
        if r.status_code == 429:
            data = r.json()
            retry_after = data.get("retryAfter", 0)
            hours = retry_after / 3600
            print(f"   ❌ Rate limited. Resets in {hours:.1f} hours (midnight UTC / 8:00 AM Beijing)")
            return False
        return r.status_code == 200
    except Exception as e:
        print(f"   ❌ Connection error: {str(e)[:60]}")
        return False


def load_existing_ids() -> set:
    """Load all existing openalex_ids from previously collected files."""
    seen = set()
    if not CONCEPT_DIR.exists():
        return seen
    for f in CONCEPT_DIR.glob("*.csv"):
        try:
            df = pd.read_csv(f, usecols=["openalex_id"])
            seen.update(df["openalex_id"].tolist())
            print(f"   {f.name}: {len(df):,} IDs")
        except Exception:
            pass
    return seen


def extract_work_data(work: dict, source_label: str) -> dict:
    """Extract fields from an OpenAlex work."""
    abstract = None
    if work.get("abstract_inverted_index"):
        try:
            inv = work["abstract_inverted_index"]
            if inv:
                words = [""] * (max(max(p) for p in inv.values()) + 1)
                for w, positions in inv.items():
                    for pos in positions:
                        words[pos] = w
                abstract = " ".join(words)
        except (ValueError, TypeError):
            pass

    authors = []
    if work.get("authorships"):
        for a in work["authorships"][:10]:
            name = a.get("author", {}).get("display_name")
            if name:
                authors.append(name)

    keywords = []
    if work.get("concepts"):
        keywords = [c["display_name"] for c in work["concepts"][:10] if c.get("display_name")]

    venue = None
    if work.get("primary_location") and work["primary_location"].get("source"):
        venue = work["primary_location"]["source"].get("display_name")

    institutions = set()
    if work.get("authorships"):
        for a in work["authorships"][:5]:
            for inst in a.get("institutions", [])[:2]:
                if inst.get("display_name"):
                    institutions.add(inst["display_name"])

    return {
        "openalex_id": work.get("id", "").replace("https://openalex.org/", ""),
        "doi": work.get("doi", "").replace("https://doi.org/", "") if work.get("doi") else None,
        "title": work.get("title"),
        "abstract": abstract,
        "publication_year": work.get("publication_year"),
        "publication_date": work.get("publication_date"),
        "venue": venue,
        "cited_by_count": work.get("cited_by_count", 0),
        "authors": "; ".join(authors) if authors else None,
        "institutions": "; ".join(list(institutions)[:5]) if institutions else None,
        "keywords": "; ".join(keywords) if keywords else None,
        "is_open_access": work.get("open_access", {}).get("is_oa", False),
        "type": work.get("type"),
        "language": work.get("language"),
        "primary_concept": source_label,
    }


def collect_with_retry(query_builder_fn, max_papers: int, source_label: str, seen_ids: set) -> list:
    """Generic collection function with retry logic."""
    for attempt in range(MAX_RETRIES + 1):
        try:
            query = query_builder_fn()
            results = []

            for page in query.paginate(per_page=BATCH_SIZE, n_max=max_papers * 2):
                for work in page:
                    wid = work.get("id")
                    if wid and wid not in seen_ids:
                        seen_ids.add(wid)
                        results.append(extract_work_data(work, source_label))
                        if len(results) >= max_papers:
                            return results

                if len(results) >= max_papers:
                    break
                time.sleep(PAGE_DELAY)

            return results

        except Exception as e:
            err = str(e)
            if attempt < MAX_RETRIES and ("Connection" in err or "Timeout" in err or "HTTP" in err or "429" in err):
                wait = RETRY_WAITS[attempt]
                print(f" RETRY({attempt+1}/{MAX_RETRIES}, {wait}s)", end="", flush=True)
                time.sleep(wait)
            else:
                print(f" ERR:{err[:60]}")
                return []

    return []


# =============================================================================
# STEP 1: TEST CONCEPT IDS
# =============================================================================

def test_concept_ids() -> list:
    """Test which concept IDs return data. Returns list of (id, name, count)."""
    print("\n" + "=" * 70)
    print("🔍 STEP 1: Testing Concept IDs")
    print("=" * 70)

    working = []

    for cid, name in CANDIDATE_CONCEPTS:
        print(f"   {name:25}", end=" ", flush=True)
        try:
            count = Works().filter(
                concepts={"id": cid},
                publication_year=f"{MIN_YEAR}-{MAX_YEAR}",
                has_abstract=True,
            ).count()

            if count > 0:
                print(f"✅ {count:>10,} papers")
                working.append((cid, name, count))
            else:
                print(f"❌ 0 papers")

            time.sleep(0.2)  # Gentle rate limiting

        except Exception as e:
            err = str(e)
            if "429" in err or "Rate" in err:
                print(f"⚠️ Rate limited — stopping test")
                break
            print(f"❌ {str(e)[:40]}")

    print(f"\n   Working concepts: {len(working)}/{len(CANDIDATE_CONCEPTS)}")
    return working


# =============================================================================
# STEP 2: HYBRID COLLECTION
# =============================================================================

def collect_by_concept(cid: str, name: str, max_papers: int, seen_ids: set) -> list:
    """Collect papers using a Concept ID filter."""
    def build_query():
        return Works().filter(
            concepts={"id": cid},
            publication_year=f"{MIN_YEAR}-{MAX_YEAR}",
            has_abstract=True,
        ).sort(cited_by_count="desc")

    return collect_with_retry(build_query, max_papers, name, seen_ids)


def collect_by_search(term: str, domain: str, max_papers: int, seen_ids: set) -> list:
    """Collect papers using search query."""
    def build_query():
        return Works().search(term).filter(
            publication_year=f"{MIN_YEAR}-{MAX_YEAR}",
            has_abstract=True,
        ).sort(cited_by_count="desc")

    return collect_with_retry(build_query, max_papers, domain, seen_ids)


def run_hybrid_collection(working_concepts: list, seen_ids: set) -> list:
    """Run hybrid collection: concept IDs first, then search fallback."""
    print("\n" + "=" * 70)
    print("🚀 STEP 2: Hybrid Collection")
    print("=" * 70)

    all_results = []

    # Part A: Collect from working Concept IDs
    # Skip Food Chemistry (already have 150K)
    skip_concepts = {"C185592680"}  # Food Chemistry already collected
    concept_results = []

    for cid, name, available in working_concepts:
        if cid in skip_concepts:
            print(f"\n   ⏭️ Skipping {name} (already collected)")
            continue

        max_papers = min(100000, available)  # Cap at 100K per concept
        print(f"\n   📚 [Concept] {name} (target: {max_papers:,})", flush=True)

        results = collect_by_concept(cid, name, max_papers, seen_ids)
        if results:
            concept_results.extend(results)
            print(f"   ✅ {len(results):,} new papers")

            # Save intermediate
            df = pd.DataFrame(results)
            df["fetch_date"] = datetime.now().isoformat()
            safe = name.replace(" ", "_")
            df.to_csv(CONCEPT_DIR / f"hybrid_concept_{safe}.csv", index=False, encoding="utf-8-sig")

    all_results.extend(concept_results)
    print(f"\n   Concept phase: {len(concept_results):,} papers")

    # Part B: Search-based fallback for remaining domains
    # Figure out which domains already have good coverage
    covered_domains = set()
    for _, name, _ in working_concepts:
        covered_domains.add(name.lower())

    print(f"\n   📖 Starting search-based collection...")
    search_results = []

    for term, domain, max_papers in FALLBACK_SEARCH_TERMS:
        print(f"   🔍 '{term}' ({domain})", end=" ", flush=True)
        results = collect_by_search(term, domain, max_papers, seen_ids)
        if results:
            search_results.extend(results)
            print(f"→ {len(results):,} new")
        else:
            print(f"→ 0")

    if search_results:
        df = pd.DataFrame(search_results)
        df["fetch_date"] = datetime.now().isoformat()
        df.to_csv(CONCEPT_DIR / "hybrid_search_fallback.csv", index=False, encoding="utf-8-sig")

    all_results.extend(search_results)
    print(f"\n   Search phase: {len(search_results):,} papers")

    return all_results


# =============================================================================
# STEP 3: BUILD MASTER FILE
# =============================================================================

def build_master_file():
    """Combine all collected data into one master file."""
    print("\n" + "=" * 70)
    print("📊 STEP 3: Building Master File")
    print("=" * 70)

    all_dfs = []
    for f in sorted(CONCEPT_DIR.glob("*.csv")):
        try:
            df = pd.read_csv(f)
            all_dfs.append(df)
            print(f"   {f.name}: {len(df):,}")
        except Exception:
            pass

    if not all_dfs:
        print("   No data files found!")
        return

    master = pd.concat(all_dfs, ignore_index=True)
    before = len(master)
    master = master.drop_duplicates(subset=["openalex_id"], keep="first")
    print(f"\n   Dedup: {before:,} → {len(master):,}")

    # Tier labels
    master["tier"] = master["cited_by_count"].apply(
        lambda x: 1 if x >= 50 else (2 if x >= 10 else 3)
    )
    master["tier_label"] = master["tier"].map({
        1: "high_impact", 2: "medium_impact", 3: "standard"
    })

    master_file = OUTPUT_DIR / "master_all_concepts.csv"
    master.to_csv(master_file, index=False, encoding="utf-8-sig")

    print(f"\n   📊 FINAL STATISTICS:")
    print(f"   Total:     {len(master):,}")
    print(f"   Abstracts: {master['abstract'].notna().sum():,}")
    print(f"   DOI:       {master['doi'].notna().sum():,}")
    print(f"   Tier 1:    {(master['tier']==1).sum():,}")
    print(f"   Tier 2:    {(master['tier']==2).sum():,}")
    print(f"   Tier 3:    {(master['tier']==3).sum():,}")
    print(f"\n   By source:")
    for c, n in master["primary_concept"].value_counts().head(25).items():
        print(f"      {c:30} {n:>8,}")
    print(f"\n   File: {master_file}")
    print(f"   Size: {master_file.stat().st_size / 1024 / 1024:.1f} MB")


# =============================================================================
# MAIN
# =============================================================================

def main():
    print("\n" + "=" * 70)
    print("🚀 FoodmoleGPT - Hybrid Data Collection")
    print("=" * 70)
    start = datetime.now()
    print(f"   Time: {start.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"   Output: {OUTPUT_DIR}")

    # Pre-flight: check rate limit
    print("\n   Checking API availability...")
    if not check_rate_limit():
        print("\n   ⛔ API is rate-limited. Please try again after 8:00 AM Beijing time.")
        print("   Run: python src/fetch_hybrid.py")
        return

    print("   ✅ API available!\n")

    CONCEPT_DIR.mkdir(parents=True, exist_ok=True)

    # Load existing data for deduplication
    print("📂 Loading existing data:")
    seen_ids = load_existing_ids()
    print(f"   Total existing: {len(seen_ids):,}\n")

    # Step 1: Test Concept IDs
    working_concepts = test_concept_ids()

    # Step 2: Hybrid collection
    if working_concepts or FALLBACK_SEARCH_TERMS:
        new_results = run_hybrid_collection(working_concepts, seen_ids)
        print(f"\n   🆕 Total new papers: {len(new_results):,}")

    # Step 3: Build master file
    build_master_file()

    elapsed = datetime.now() - start
    print(f"\n   Elapsed: {elapsed}")
    print("=" * 70)
    print("✅ Hybrid collection complete!")


if __name__ == "__main__":
    main()
