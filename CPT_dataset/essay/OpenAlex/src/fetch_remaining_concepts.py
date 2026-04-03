"""
FoodmoleGPT - Collect Remaining Domains (Fixed)
================================================
Collects papers for the 4 remaining food science domains using search-based
approach (concepts.id filter is deprecated in OpenAlex).

Food Chemistry (150K) is already collected - this script skips it.

Usage:
    conda activate foodmole
    python src/fetch_remaining_concepts.py
"""

import time
from pathlib import Path
from datetime import datetime

import pandas as pd
from tqdm import tqdm
import pyalex
from pyalex import Works

pyalex.config.email = "foodmolegpt@example.com"

print("✅ OpenAlex Remaining Domains Collector initialized")

# =============================================================================
# CONFIGURATION
# =============================================================================

OUTPUT_DIR = Path("D:/FoodmoleGPT/data/raw/openalex_concepts")
EXISTING_IDS_FILE = OUTPUT_DIR / "by_concept" / "C185592680_Food_Chemistry.csv"

# Remaining domains to collect (Food Chemistry already done)
DOMAINS = [
    {
        "name": "Food Science",
        "name_cn": "食品科学",
        "search_query": "food science",
        "max_papers": 150000,
    },
    {
        "name": "Food Engineering",
        "name_cn": "食品工程",
        "search_query": "food engineering",
        "max_papers": 100000,
    },
    {
        "name": "Food Microbiology",
        "name_cn": "食品微生物学",
        "search_query": "food microbiology",
        "max_papers": 100000,
    },
    {
        "name": "Nutrition Science",
        "name_cn": "营养科学",
        "search_query": "nutrition science",
        "max_papers": 100000,
    },
]

MIN_YEAR = 2010
MAX_YEAR = 2026
BATCH_SIZE = 200


def extract_work_data(work: dict, domain_name: str) -> dict:
    """Extract relevant fields from an OpenAlex work."""
    abstract = None
    if work.get("abstract_inverted_index"):
        try:
            inverted = work["abstract_inverted_index"]
            if inverted:
                max_pos = max(max(p) for p in inverted.values())
                words = [""] * (max_pos + 1)
                for word, positions in inverted.items():
                    for pos in positions:
                        words[pos] = word
                abstract = " ".join(words)
        except (ValueError, TypeError):
            abstract = None

    authors = []
    if work.get("authorships"):
        for a in work["authorships"][:10]:
            author = a.get("author", {})
            if author.get("display_name"):
                authors.append(author["display_name"])

    keywords = []
    if work.get("concepts"):
        keywords = [c["display_name"] for c in work["concepts"][:10] if c.get("display_name")]

    venue = None
    if work.get("primary_location"):
        source = work["primary_location"].get("source")
        if source:
            venue = source.get("display_name")

    institutions = []
    if work.get("authorships"):
        for a in work["authorships"][:5]:
            for inst in a.get("institutions", [])[:2]:
                if inst.get("display_name"):
                    institutions.append(inst["display_name"])

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
        "institutions": "; ".join(list(set(institutions))[:5]) if institutions else None,
        "keywords": "; ".join(keywords) if keywords else None,
        "is_open_access": work.get("open_access", {}).get("is_oa", False),
        "type": work.get("type"),
        "language": work.get("language"),
        "primary_concept": domain_name,
    }


def collect_domain(
    search_query: str,
    domain_name: str,
    max_papers: int,
    global_seen_ids: set,
) -> pd.DataFrame:
    """Collect papers for a domain using search-based query."""
    print(f"\n{'='*70}")
    print(f"📚 Collecting: {domain_name}")
    print(f"   Search: '{search_query}' | Years: {MIN_YEAR}-{MAX_YEAR} | Max: {max_papers:,}")

    # Build query: search + filter year + require abstract
    query = Works().search(search_query).filter(
        publication_year=f"{MIN_YEAR}-{MAX_YEAR}",
        has_abstract=True,
    ).sort(cited_by_count="desc")

    try:
        total_available = query.count()
        target = min(max_papers, total_available)
        print(f"   Available: {total_available:,} | Target: {target:,}")
    except Exception as e:
        print(f"   ❌ Error getting count: {e}")
        return pd.DataFrame()

    all_works = []
    errors = 0
    pbar = tqdm(total=target, desc=f"   {domain_name[:20]}", unit="papers")

    try:
        for page in query.paginate(per_page=BATCH_SIZE, n_max=max_papers):
            for work in page:
                work_id = work.get("id")
                if work_id and work_id not in global_seen_ids:
                    global_seen_ids.add(work_id)
                    all_works.append(extract_work_data(work, domain_name))
                    pbar.update(1)

                    if len(all_works) >= max_papers:
                        break

            if len(all_works) >= max_papers:
                break

            time.sleep(0.02)

    except Exception as e:
        errors += 1
        print(f"\n   ⚠️ Error during pagination: {str(e)[:100]}")
        print(f"   Collected {len(all_works):,} papers before error")

    pbar.close()

    if not all_works:
        return pd.DataFrame()

    df = pd.DataFrame(all_works)
    df["fetch_date"] = datetime.now().isoformat()

    abstract_count = df["abstract"].notna().sum()
    print(f"   ✅ Collected: {len(df):,} | Abstracts: {abstract_count:,} ({abstract_count/len(df)*100:.1f}%)")

    return df


def main():
    print("\n" + "="*70)
    print("🚀 FoodmoleGPT - Remaining Domains Collection")
    print("="*70)
    print(f"   Start: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"   Output: {OUTPUT_DIR}")
    print(f"   Domains: {len(DOMAINS)}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "by_concept").mkdir(exist_ok=True)

    # Load existing IDs from Food Chemistry to avoid duplicates
    global_seen_ids = set()
    if EXISTING_IDS_FILE.exists():
        existing_df = pd.read_csv(EXISTING_IDS_FILE, usecols=["openalex_id"])
        global_seen_ids = set(existing_df["openalex_id"].tolist())
        print(f"   Loaded {len(global_seen_ids):,} existing IDs from Food Chemistry")

    all_data = []

    for domain in DOMAINS:
        df = collect_domain(
            search_query=domain["search_query"],
            domain_name=domain["name"],
            max_papers=domain["max_papers"],
            global_seen_ids=global_seen_ids,
        )

        if not df.empty:
            # Save per-domain file
            safe_name = domain["name"].replace(" ", "_")
            output_file = OUTPUT_DIR / "by_concept" / f"search_{safe_name}.csv"
            df.to_csv(output_file, index=False, encoding="utf-8-sig")
            print(f"   💾 Saved: {output_file.name} ({len(df):,} records)")
            all_data.append(df)

    # Merge with existing Food Chemistry data and create master file
    print("\n" + "="*70)
    print("📊 CREATING UPDATED MASTER FILE")
    print("="*70)

    if all_data:
        new_df = pd.concat(all_data, ignore_index=True)

        # Load existing Food Chemistry data
        if EXISTING_IDS_FILE.exists():
            existing_df = pd.read_csv(EXISTING_IDS_FILE)
            existing_df["primary_concept"] = "Food Chemistry"
            master_df = pd.concat([existing_df, new_df], ignore_index=True)
        else:
            master_df = new_df

        # Deduplicate
        before = len(master_df)
        master_df = master_df.drop_duplicates(subset=["openalex_id"], keep="first")
        print(f"   Dedup: {before:,} → {len(master_df):,}")

        # Add tier labels
        master_df["tier"] = master_df["cited_by_count"].apply(
            lambda x: 1 if x >= 50 else (2 if x >= 10 else 3)
        )
        master_df["tier_label"] = master_df["tier"].map({
            1: "high_impact", 2: "medium_impact", 3: "standard"
        })

        # Save
        master_file = OUTPUT_DIR / "master_all_concepts.csv"
        master_df.to_csv(master_file, index=False, encoding="utf-8-sig")

        print(f"\n   📊 FINAL STATISTICS:")
        print(f"   Total papers: {len(master_df):,}")
        print(f"   With abstracts: {master_df['abstract'].notna().sum():,}")
        print(f"   Tier 1 (high): {(master_df['tier']==1).sum():,}")
        print(f"   Tier 2 (medium): {(master_df['tier']==2).sum():,}")
        print(f"   Tier 3 (standard): {(master_df['tier']==3).sum():,}")
        print(f"\n   By domain:")
        for concept, count in master_df["primary_concept"].value_counts().items():
            print(f"      {concept}: {count:,}")
        print(f"\n   File: {master_file}")
        print(f"   Size: {master_file.stat().st_size / 1024 / 1024:.1f} MB")

    print(f"\n   End: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*70)
    print("✅ Collection complete!")


if __name__ == "__main__":
    main()
