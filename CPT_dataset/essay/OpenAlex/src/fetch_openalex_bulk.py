"""
FoodmoleGPT - Bulk OpenAlex Data Collector
==========================================
Collects 100K+ food science papers with tiered quality labeling.

Tiers:
- Tier 1 (core): High-citation papers with abstracts (already collected)
- Tier 2 (extended): Medium-citation papers with abstracts
- Tier 3 (supplementary): All papers including those without abstracts

Usage:
    conda activate foodmole
    python src/fetch_openalex_bulk.py

Output: D:\FoodmoleGPT\data\raw\openalex\
"""

import os
import time
from pathlib import Path
from datetime import datetime

import pandas as pd
from tqdm import tqdm
import pyalex
from pyalex import Works

# Configure pyalex
pyalex.config.email = "foodmolegpt@example.com"

print("✅ OpenAlex Bulk Collector initialized")

# =============================================================================
# CONFIGURATION
# =============================================================================

# Output directory on D: drive (more space)
OUTPUT_DIR = Path("D:/FoodmoleGPT/data/raw/openalex")

# Expanded search configuration for 100K+ papers
SEARCH_CONFIGS = [
    # ----- FOOD CHEMISTRY -----
    {
        "domain": "food_chemistry",
        "domain_cn": "食品化学",
        "search_terms": [
            "food chemistry",
            "bioactive compounds",
            "lipid oxidation", 
            "maillard reaction",
            "food antioxidants",
            "polyphenols food",
            "food proteins",
            "food lipids",
            "flavor compounds",
            "food pigments",
        ],
    },
    # ----- FOOD ENGINEERING -----
    {
        "domain": "food_engineering", 
        "domain_cn": "食品工程",
        "search_terms": [
            "food processing",
            "encapsulation",
            "thermal processing",
            "shelf life",
            "food drying",
            "food extrusion",
            "high pressure processing",
            "pulsed electric field food",
            "food packaging",
            "food preservation",
        ],
        "exclude_terms": ["soil", "crop", "agriculture"],
    },
    # ----- FOOD MICROBIOLOGY -----
    {
        "domain": "food_microbiology",
        "domain_cn": "食品微生物学", 
        "search_terms": [
            "food microbiology",
            "probiotics",
            "foodborne pathogens",
            "fermentation food",
            "lactic acid bacteria",
            "food spoilage",
            "antimicrobial food",
            "starter cultures",
            "food biopreservation",
            "yeast food",
        ],
    },
    # ----- SENSORY SCIENCE -----
    {
        "domain": "sensory_science",
        "domain_cn": "感官科学",
        "search_terms": [
            "sensory evaluation",
            "flavor profile",
            "texture analysis",
            "consumer acceptance",
            "food preference",
            "taste perception",
            "aroma food",
            "mouthfeel",
            "sensory panel",
            "hedonic rating",
        ],
    },
    # ----- FOOD SAFETY -----
    {
        "domain": "food_safety",
        "domain_cn": "食品安全",
        "search_terms": [
            "food safety",
            "food contamination",
            "mycotoxins",
            "pesticide residue",
            "heavy metals food",
            "food allergens",
            "food adulteration",
            "foodborne illness",
            "food hygiene",
            "food toxicology",
        ],
    },
    # ----- NUTRITION SCIENCE -----
    {
        "domain": "nutrition_science",
        "domain_cn": "营养科学",
        "search_terms": [
            "functional food",
            "nutraceuticals",
            "dietary fiber",
            "antioxidant activity",
            "glycemic index",
            "bioavailability nutrients",
            "food fortification",
            "protein digestibility",
            "lipid metabolism",
            "gut microbiota food",
        ],
    },
    # ----- FOOD ANALYSIS -----
    {
        "domain": "food_analysis",
        "domain_cn": "食品分析",
        "search_terms": [
            "food analysis",
            "chromatography food",
            "spectroscopy food",
            "food authentication",
            "food quality control",
            "sensory analysis",
            "food traceability",
            "metabolomics food",
            "proteomics food",
        ],
    },
    # ----- DAIRY SCIENCE -----
    {
        "domain": "dairy_science",
        "domain_cn": "乳品科学",
        "search_terms": [
            "dairy products",
            "milk proteins",
            "cheese processing",
            "yogurt fermentation",
            "lactose",
            "whey protein",
            "casein",
        ],
    },
    # ----- MEAT SCIENCE -----
    {
        "domain": "meat_science",
        "domain_cn": "肉类科学",
        "search_terms": [
            "meat quality",
            "meat processing",
            "meat preservation",
            "meat tenderness",
            "curing meat",
            "meat color",
        ],
    },
    # ----- PLANT-BASED FOODS -----
    {
        "domain": "plant_based_foods",
        "domain_cn": "植物基食品",
        "search_terms": [
            "plant-based protein",
            "meat alternatives",
            "plant-based milk",
            "legume protein",
            "soy protein",
            "pea protein",
        ],
    },
]

# Collection parameters
MIN_YEAR = 2015  # Expanded from 2019 to 2015
MAX_RESULTS_TIER2 = 2000  # Per search term for Tier 2
MAX_RESULTS_TIER3 = 3000  # Per search term for Tier 3 (includes no-abstract)


def setup_output_directory():
    """Create output directories."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "tier2").mkdir(exist_ok=True)
    (OUTPUT_DIR / "tier3").mkdir(exist_ok=True)
    print(f"✅ Output directory ready: {OUTPUT_DIR}")


def extract_work_data(work, tier: int) -> dict:
    """Extract relevant fields from an OpenAlex work object."""
    # Get abstract if available
    abstract = None
    if work.get("abstract_inverted_index"):
        inverted = work["abstract_inverted_index"]
        if inverted:
            abstract_words = [""] * (max(max(v) for v in inverted.values()) + 1)
            for word, positions in inverted.items():
                for pos in positions:
                    abstract_words[pos] = word
            abstract = " ".join(abstract_words)
    
    # Get author names
    authors = []
    if work.get("authorships"):
        for authorship in work["authorships"][:10]:  # Limit to 10 authors
            if authorship.get("author") and authorship["author"].get("display_name"):
                authors.append(authorship["author"]["display_name"])
    
    # Get keywords/concepts
    keywords = []
    if work.get("concepts"):
        keywords = [c["display_name"] for c in work["concepts"][:10]]
    
    # Get publication venue
    venue = None
    if work.get("primary_location") and work["primary_location"].get("source"):
        venue = work["primary_location"]["source"].get("display_name")
    
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
        "keywords": "; ".join(keywords) if keywords else None,
        "is_open_access": work.get("open_access", {}).get("is_oa", False),
        "type": work.get("type"),
        "tier": tier,
        "tier_label": {1: "core_high_citation", 2: "extended_with_abstract", 3: "supplementary"}[tier],
    }


def collect_tier2_data(config: dict, max_per_term: int = MAX_RESULTS_TIER2) -> pd.DataFrame:
    """
    Collect Tier 2 data: medium-citation papers with abstracts.
    Sorted by publication date (recent first) instead of citation count.
    """
    domain = config["domain"]
    print(f"\n{'='*60}")
    print(f"📚 [Tier 2] {domain} ({config['domain_cn']})")
    
    all_works = []
    seen_ids = set()
    
    for term in config["search_terms"]:
        print(f"   📖 '{term}'", end=" ", flush=True)
        
        try:
            # Sort by publication date (recent first) for Tier 2
            query = Works().search(term).filter(
                publication_year=f">{MIN_YEAR - 1}",
                has_abstract=True  # Only papers with abstracts
            ).sort(publication_date="desc")
            
            count = 0
            for page in query.paginate(per_page=200):
                for work in page:
                    if work["id"] not in seen_ids:
                        if "exclude_terms" in config:
                            title = (work.get("title") or "").lower()
                            if any(ex in title for ex in config["exclude_terms"]):
                                continue
                        
                        seen_ids.add(work["id"])
                        all_works.append(extract_work_data(work, tier=2))
                        count += 1
                        
                        if count >= max_per_term:
                            break
                
                if count >= max_per_term:
                    break
                
                time.sleep(0.05)  # Rate limiting
            
            print(f"✓ {count}")
            
        except Exception as e:
            print(f"✗ {str(e)[:40]}")
    
    if not all_works:
        return pd.DataFrame()
    
    df = pd.DataFrame(all_works)
    df["search_domain"] = domain
    df["fetch_date"] = datetime.now().isoformat()
    
    print(f"   📊 Total: {len(df)} works")
    return df


def collect_tier3_data(config: dict, max_per_term: int = MAX_RESULTS_TIER3) -> pd.DataFrame:
    """
    Collect Tier 3 data: all papers including those without abstracts.
    Largest volume for pre-training.
    """
    domain = config["domain"]
    print(f"\n{'='*60}")
    print(f"📦 [Tier 3] {domain} ({config['domain_cn']})")
    
    all_works = []
    seen_ids = set()
    
    for term in config["search_terms"]:
        print(f"   📖 '{term}'", end=" ", flush=True)
        
        try:
            # No abstract filter, sorted by publication date
            query = Works().search(term).filter(
                publication_year=f">{MIN_YEAR - 1}"
            ).sort(publication_date="desc")
            
            count = 0
            for page in query.paginate(per_page=200):
                for work in page:
                    if work["id"] not in seen_ids:
                        if "exclude_terms" in config:
                            title = (work.get("title") or "").lower()
                            if any(ex in title for ex in config["exclude_terms"]):
                                continue
                        
                        seen_ids.add(work["id"])
                        all_works.append(extract_work_data(work, tier=3))
                        count += 1
                        
                        if count >= max_per_term:
                            break
                
                if count >= max_per_term:
                    break
                
                time.sleep(0.05)
            
            print(f"✓ {count}")
            
        except Exception as e:
            print(f"✗ {str(e)[:40]}")
    
    if not all_works:
        return pd.DataFrame()
    
    df = pd.DataFrame(all_works)
    df["search_domain"] = domain
    df["fetch_date"] = datetime.now().isoformat()
    
    print(f"   📊 Total: {len(df)} works")
    return df


def run_bulk_collection(collect_tier2=True, collect_tier3=True):
    """
    Run bulk data collection for Tier 2 and Tier 3.
    Tier 1 data is already collected separately.
    """
    print("\n" + "="*70)
    print("🚀 FoodmoleGPT - Bulk Data Collection (100K+ target)")
    print("="*70)
    print(f"   Start time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"   Output: {OUTPUT_DIR}")
    print(f"   Domains: {len(SEARCH_CONFIGS)}")
    print(f"   Year range: {MIN_YEAR}+")
    
    setup_output_directory()
    
    all_tier2 = []
    all_tier3 = []
    
    for config in tqdm(SEARCH_CONFIGS, desc="Domains"):
        # Collect Tier 2
        if collect_tier2:
            df2 = collect_tier2_data(config)
            if not df2.empty:
                output_file = OUTPUT_DIR / "tier2" / f"tier2_{config['domain']}.csv"
                df2.to_csv(output_file, index=False, encoding="utf-8-sig")
                all_tier2.append(df2)
                print(f"   💾 Saved: {output_file.name}")
        
        # Collect Tier 3
        if collect_tier3:
            df3 = collect_tier3_data(config)
            if not df3.empty:
                output_file = OUTPUT_DIR / "tier3" / f"tier3_{config['domain']}.csv"
                df3.to_csv(output_file, index=False, encoding="utf-8-sig")
                all_tier3.append(df3)
                print(f"   💾 Saved: {output_file.name}")
    
    # Create master files
    print("\n" + "="*70)
    print("📊 CREATING MASTER FILES")
    print("="*70)
    
    if all_tier2:
        master_tier2 = pd.concat(all_tier2, ignore_index=True)
        master_tier2 = master_tier2.drop_duplicates(subset=["openalex_id"], keep="first")
        master_file = OUTPUT_DIR / "tier2_all_domains.csv"
        master_tier2.to_csv(master_file, index=False, encoding="utf-8-sig")
        print(f"   Tier 2 master: {len(master_tier2):,} records")
    
    if all_tier3:
        master_tier3 = pd.concat(all_tier3, ignore_index=True)
        master_tier3 = master_tier3.drop_duplicates(subset=["openalex_id"], keep="first")
        master_file = OUTPUT_DIR / "tier3_all_domains.csv"
        master_tier3.to_csv(master_file, index=False, encoding="utf-8-sig")
        print(f"   Tier 3 master: {len(master_tier3):,} records")
    
    # Final summary
    total = (len(master_tier2) if all_tier2 else 0) + (len(master_tier3) if all_tier3 else 0)
    print(f"\n   Total new records: {total:,}")
    print(f"   End time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*70)
    print("✅ Bulk collection complete!")


if __name__ == "__main__":
    # Run collection - this will take significant time
    # Set to False to skip a tier if you want to run partially
    run_bulk_collection(
        collect_tier2=True,  # ~50K papers with abstracts
        collect_tier3=True   # ~50K+ papers including no-abstract
    )
