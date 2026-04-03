"""
FoodmoleGPT - OpenAlex Concept-Based Collector
===============================================
High-volume data collection using OpenAlex Concept IDs.
Designed for 32B model post-training (50万+ papers target).

Concept IDs used:
- C300806122: Food Science
- C185592680: Food Chemistry (核心)
- C159062612: Food Engineering
- C107768578: Food Microbiology
- C2776043033: Nutrition

Usage:
    conda activate foodmole
    python src/fetch_openalex_concepts.py

Output: D:\FoodmoleGPT\data\raw\openalex_concepts\
"""

import time
from pathlib import Path
from datetime import datetime
from typing import Optional

import pandas as pd
from tqdm import tqdm
import pyalex
from pyalex import Works

# Configure pyalex with polite pool
pyalex.config.email = "foodmolegpt@example.com"

print("✅ OpenAlex Concept-Based Collector initialized")

# =============================================================================
# CONCEPT CONFIGURATION
# =============================================================================

# Food Science related OpenAlex Concept IDs
CONCEPT_CONFIGS = [
    {
        "id": "C300806122",
        "name": "Food Science",
        "name_cn": "食品科学",
        "priority": 1,  # Core concept
    },
    {
        "id": "C185592680",
        "name": "Food Chemistry",
        "name_cn": "食品化学",
        "priority": 1,  # Core concept
    },
    {
        "id": "C159062612",
        "name": "Food Engineering",
        "name_cn": "食品工程",
        "priority": 1,
    },
    {
        "id": "C107768578",
        "name": "Food Microbiology",
        "name_cn": "食品微生物学",
        "priority": 1,
    },
    {
        "id": "C2776043033",
        "name": "Nutrition",
        "name_cn": "营养学",
        "priority": 2,  # Broader concept
    },
]

# =============================================================================
# COLLECTION PARAMETERS
# =============================================================================

# Output directory
OUTPUT_DIR = Path("D:/FoodmoleGPT/data/raw/openalex_concepts")

# Year range
MIN_YEAR = 2010  # Collect from 2010 onwards
MAX_YEAR = 2026  # Up to current

# Target limits (set to None for no limit)
MAX_PAPERS_PER_CONCEPT = 200000  # 20万 per concept
MAX_TOTAL_PAPERS = 1000000       # 总计最多 100万

# Batch size for pagination
BATCH_SIZE = 200


def setup_output_directory():
    """Create output directories."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "by_concept").mkdir(exist_ok=True)
    (OUTPUT_DIR / "by_year").mkdir(exist_ok=True)
    print(f"✅ Output directory: {OUTPUT_DIR}")


def extract_work_data(work: dict, concept_name: str) -> dict:
    """Extract relevant fields from an OpenAlex work."""
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
    
    # Extract author names (limit to 10)
    authors = []
    if work.get("authorships"):
        for authorship in work["authorships"][:10]:
            author = authorship.get("author", {})
            if author.get("display_name"):
                authors.append(author["display_name"])
    
    # Extract concepts/keywords
    keywords = []
    if work.get("concepts"):
        keywords = [c["display_name"] for c in work["concepts"][:10] if c.get("display_name")]
    
    # Extract venue
    venue = None
    if work.get("primary_location"):
        source = work["primary_location"].get("source")
        if source:
            venue = source.get("display_name")
    
    # Extract institutions
    institutions = []
    if work.get("authorships"):
        for authorship in work["authorships"][:5]:
            for inst in authorship.get("institutions", [])[:2]:
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
        "primary_concept": concept_name,
    }


def collect_by_concept(
    concept_id: str,
    concept_name: str,
    require_abstract: bool = True,
    max_papers: Optional[int] = None,
    year_start: int = MIN_YEAR,
    year_end: int = MAX_YEAR,
) -> pd.DataFrame:
    """
    Collect papers for a specific OpenAlex concept.
    
    Args:
        concept_id: OpenAlex concept ID (e.g., "C185592680")
        concept_name: Human-readable concept name
        require_abstract: If True, only collect papers with abstracts
        max_papers: Maximum number of papers to collect (None for no limit)
        year_start: Start year (inclusive)
        year_end: End year (inclusive)
    
    Returns:
        DataFrame with collected papers
    """
    print(f"\n{'='*70}")
    print(f"📚 Collecting: {concept_name} ({concept_id})")
    print(f"   Years: {year_start}-{year_end} | Abstract required: {require_abstract}")
    if max_papers:
        print(f"   Max papers: {max_papers:,}")
    
    all_works = []
    seen_ids = set()
    
    # Build query
    query = Works().filter(
        concepts={"id": concept_id},
        publication_year=f"{year_start}-{year_end}",
    )
    
    if require_abstract:
        query = query.filter(has_abstract=True)
    
    # Sort by citation count (most impactful first)
    query = query.sort(cited_by_count="desc")
    
    try:
        # Get total count
        total_available = query.count()
        target = min(max_papers, total_available) if max_papers else total_available
        print(f"   Available: {total_available:,} | Target: {target:,}")
        
        # Paginate through results with explicit n_max to avoid default limit
        pbar = tqdm(total=target, desc=f"   {concept_name[:20]}", unit="papers")
        
        for page in query.paginate(per_page=BATCH_SIZE, n_max=max_papers or 10000000):
            for work in page:
                work_id = work.get("id")
                if work_id and work_id not in seen_ids:
                    seen_ids.add(work_id)
                    all_works.append(extract_work_data(work, concept_name))
                    pbar.update(1)
                    
                    if max_papers and len(all_works) >= max_papers:
                        break
            
            if max_papers and len(all_works) >= max_papers:
                break
            
            time.sleep(0.02)  # Rate limiting
        
        pbar.close()
        
    except Exception as e:
        print(f"   ❌ Error: {str(e)[:100]}")
        return pd.DataFrame()
    
    if not all_works:
        return pd.DataFrame()
    
    df = pd.DataFrame(all_works)
    df["fetch_date"] = datetime.now().isoformat()
    
    # Statistics
    abstract_count = df["abstract"].notna().sum()
    print(f"   ✅ Collected: {len(df):,} papers | With abstracts: {abstract_count:,} ({abstract_count/len(df)*100:.1f}%)")
    
    return df


def collect_all_concepts(
    require_abstract: bool = True,
    max_per_concept: int = MAX_PAPERS_PER_CONCEPT,
    max_total: int = MAX_TOTAL_PAPERS,
):
    """
    Collect papers from all configured concepts.
    
    Args:
        require_abstract: Only collect papers with abstracts
        max_per_concept: Max papers per concept
        max_total: Max total papers across all concepts
    """
    print("\n" + "="*70)
    print("🚀 FoodmoleGPT - Concept-Based Bulk Collection")
    print("="*70)
    print(f"   Start time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"   Output: {OUTPUT_DIR}")
    print(f"   Concepts: {len(CONCEPT_CONFIGS)}")
    print(f"   Year range: {MIN_YEAR}-{MAX_YEAR}")
    print(f"   Require abstract: {require_abstract}")
    print(f"   Max per concept: {max_per_concept:,}")
    print(f"   Max total: {max_total:,}")
    
    setup_output_directory()
    
    all_data = []
    global_seen_ids = set()
    total_collected = 0
    
    for concept in CONCEPT_CONFIGS:
        if max_total and total_collected >= max_total:
            print(f"\n⚠️ Reached total limit ({max_total:,}), stopping collection")
            break
        
        # Adjust max for this concept based on remaining quota
        remaining_quota = max_total - total_collected if max_total else None
        concept_limit = min(max_per_concept, remaining_quota) if remaining_quota else max_per_concept
        
        df = collect_by_concept(
            concept_id=concept["id"],
            concept_name=concept["name"],
            require_abstract=require_abstract,
            max_papers=concept_limit,
        )
        
        if not df.empty:
            # Remove global duplicates
            before = len(df)
            df = df[~df["openalex_id"].isin(global_seen_ids)]
            global_seen_ids.update(df["openalex_id"].tolist())
            
            if before != len(df):
                print(f"   Deduped: {before} → {len(df)} (removed {before - len(df)} duplicates)")
            
            # Save individual concept file
            output_file = OUTPUT_DIR / "by_concept" / f"{concept['id']}_{concept['name'].replace(' ', '_')}.csv"
            df.to_csv(output_file, index=False, encoding="utf-8-sig")
            print(f"   💾 Saved: {output_file.name}")
            
            all_data.append(df)
            total_collected += len(df)
    
    # Create master file
    print("\n" + "="*70)
    print("📊 CREATING MASTER FILE")
    print("="*70)
    
    if all_data:
        master_df = pd.concat(all_data, ignore_index=True)
        
        # Final deduplication by DOI (if available) or openalex_id
        before = len(master_df)
        master_df = master_df.drop_duplicates(subset=["openalex_id"], keep="first")
        print(f"   Final deduplication: {before:,} → {len(master_df):,}")
        
        # Add tier label based on citation count
        master_df["tier"] = master_df["cited_by_count"].apply(
            lambda x: 1 if x >= 50 else (2 if x >= 10 else 3)
        )
        master_df["tier_label"] = master_df["tier"].map({
            1: "high_impact",
            2: "medium_impact", 
            3: "standard"
        })
        
        # Save master file
        master_file = OUTPUT_DIR / "master_all_concepts.csv"
        master_df.to_csv(master_file, index=False, encoding="utf-8-sig")
        
        # Statistics
        print(f"\n   📊 FINAL STATISTICS:")
        print(f"   Total papers: {len(master_df):,}")
        print(f"   With abstracts: {master_df['abstract'].notna().sum():,}")
        print(f"   With DOI: {master_df['doi'].notna().sum():,}")
        print(f"   Tier 1 (high impact): {(master_df['tier'] == 1).sum():,}")
        print(f"   Tier 2 (medium impact): {(master_df['tier'] == 2).sum():,}")
        print(f"   Tier 3 (standard): {(master_df['tier'] == 3).sum():,}")
        print(f"\n   By concept:")
        for concept, count in master_df["primary_concept"].value_counts().items():
            print(f"      {concept}: {count:,}")
        print(f"\n   Master file: {master_file}")
        print(f"   File size: {master_file.stat().st_size / 1024 / 1024:.1f} MB")
    
    print(f"\n   End time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*70)
    print("✅ Collection complete!")
    
    return master_df if all_data else pd.DataFrame()


if __name__ == "__main__":
    # ==========================================================================
    # COLLECTION SETTINGS
    # ==========================================================================
    # Adjust these parameters based on your needs:
    #
    # For ~50万 papers with abstracts:
    #   max_per_concept=150000, max_total=500000
    #
    # For ~100万 papers (including no-abstract):
    #   require_abstract=False, max_per_concept=300000, max_total=1000000
    # ==========================================================================
    
    collect_all_concepts(
        require_abstract=True,      # Only papers with abstracts
        max_per_concept=150000,     # 15万 per concept
        max_total=500000,           # 50万 total target
    )
