"""
FoodmoleGPT - OpenAlex Literature Data Fetcher
===============================================
Alternative to Scopus using OpenAlex (completely free, no API key required).

OpenAlex is an open catalog of the global research system with 250M+ works.
https://openalex.org/

Usage:
    1. Activate the foodmole conda environment
    2. Run: python src/fetch_openalex.py

Author: FoodmoleGPT Team
"""

import os
import time
from pathlib import Path
from datetime import datetime

import pandas as pd
from tqdm import tqdm
import pyalex
from pyalex import Works

# Configure pyalex with polite pool (recommended)
# Add your email for better rate limits (optional but recommended)
pyalex.config.email = "foodmolegpt@example.com"

print("✅ OpenAlex configured (no API key required!)")

# =============================================================================
# SEARCH CONFIGURATION - Food Science Subdomains
# =============================================================================

SEARCH_CONFIGS = [
    {
        "domain": "food_chemistry",
        "domain_cn": "食品化学",
        "search_terms": ["food chemistry", "bioactive compounds", "lipid oxidation", "maillard reaction"],
        "description": "Research on chemical compounds, reactions, and molecular properties in food systems"
    },
    {
        "domain": "food_engineering", 
        "domain_cn": "食品工程",
        "search_terms": ["food processing", "encapsulation", "thermal processing", "shelf life"],
        "exclude_terms": ["soil", "crop"],
        "description": "Research on food processing technologies, preservation, and engineering methods"
    },
    {
        "domain": "food_microbiology",
        "domain_cn": "食品微生物学", 
        "search_terms": ["food microbiology", "probiotics", "foodborne pathogens", "fermentation"],
        "description": "Research on microorganisms in food, including beneficial and harmful species"
    },
    {
        "domain": "sensory_science",
        "domain_cn": "感官科学",
        "search_terms": ["sensory evaluation", "flavor profile", "texture analysis", "consumer acceptance"],
        "description": "Research on sensory properties, consumer perception, and quality assessment"
    },
    {
        "domain": "food_safety",
        "domain_cn": "食品安全",
        "search_terms": ["food safety", "food contamination", "mycotoxins", "pesticide residue"],
        "description": "Research on food safety hazards, contamination detection, and risk assessment"
    },
    {
        "domain": "nutrition_science",
        "domain_cn": "营养科学",
        "search_terms": ["functional food", "nutraceuticals", "dietary fiber", "antioxidant activity"],
        "description": "Research on nutritional properties, health benefits, and dietary interventions"
    },
]

# =============================================================================
# DATA OUTPUT CONFIGURATION
# =============================================================================

OUTPUT_DIR = Path("data/raw/openalex")
MAX_RESULTS_PER_TERM = 500  # Limit per search term to avoid too many results
MIN_YEAR = 2019  # Only fetch papers from 2019 onwards


def setup_output_directory():
    """Create output directory if it doesn't exist."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"✅ Output directory ready: {OUTPUT_DIR.absolute()}")


def extract_work_data(work) -> dict:
    """Extract relevant fields from an OpenAlex work object."""
    # Get abstract if available
    abstract = None
    if work.get("abstract_inverted_index"):
        # Reconstruct abstract from inverted index
        inverted = work["abstract_inverted_index"]
        abstract_words = [""] * (max(max(v) for v in inverted.values()) + 1)
        for word, positions in inverted.items():
            for pos in positions:
                abstract_words[pos] = word
        abstract = " ".join(abstract_words)
    
    # Get author names
    authors = []
    if work.get("authorships"):
        for authorship in work["authorships"]:
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
    }


def search_openalex(config: dict, max_per_term: int = MAX_RESULTS_PER_TERM) -> pd.DataFrame:
    """
    Search OpenAlex for a specific domain configuration.
    
    Args:
        config: Search configuration dictionary
        max_per_term: Maximum results per search term
    
    Returns:
        DataFrame with search results
    """
    domain = config["domain"]
    print(f"\n{'='*60}")
    print(f"🔍 Searching: {domain} ({config['domain_cn']})")
    
    all_works = []
    seen_ids = set()
    
    for term in config["search_terms"]:
        print(f"   📖 Term: '{term}'")
        
        try:
            # Build query with filters
            query = Works().search(term).filter(
                publication_year=f">{MIN_YEAR - 1}"
            ).sort(cited_by_count="desc")
            
            # Fetch results with pagination
            count = 0
            for page in query.paginate(per_page=100):
                for work in page:
                    if work["id"] not in seen_ids:
                        # Skip if contains excluded terms
                        if "exclude_terms" in config:
                            title = (work.get("title") or "").lower()
                            if any(ex in title for ex in config["exclude_terms"]):
                                continue
                        
                        seen_ids.add(work["id"])
                        all_works.append(extract_work_data(work))
                        count += 1
                        
                        if count >= max_per_term:
                            break
                
                if count >= max_per_term:
                    break
                
                # Be polite to the API
                time.sleep(0.1)
            
            print(f"      ✓ Found {count} works")
            
        except Exception as e:
            print(f"      ❌ Error: {str(e)[:80]}")
    
    if not all_works:
        return pd.DataFrame()
    
    df = pd.DataFrame(all_works)
    df["search_domain"] = domain
    df["fetch_date"] = datetime.now().isoformat()
    
    # Count abstracts
    abstract_count = df["abstract"].notna().sum()
    print(f"   📊 Total: {len(df)} works, {abstract_count} with abstracts ({abstract_count/len(df)*100:.1f}%)")
    
    return df


def save_results(df: pd.DataFrame, domain: str) -> Path:
    """Save search results to CSV file."""
    if df.empty:
        print(f"   ⚠️ No data to save for {domain}")
        return None
    
    output_file = OUTPUT_DIR / f"openalex_{domain}.csv"
    df.to_csv(output_file, index=False, encoding="utf-8-sig")
    print(f"   💾 Saved: {output_file.name} ({len(df):,} records)")
    return output_file


def run_all_searches(max_per_term: int = MAX_RESULTS_PER_TERM):
    """Run all configured searches and save results."""
    print("\n" + "="*60)
    print("🚀 FoodmoleGPT - OpenAlex Data Collection Pipeline")
    print("="*60)
    print(f"   Start time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"   Domains to search: {len(SEARCH_CONFIGS)}")
    print(f"   Max results per term: {max_per_term}")
    print(f"   Minimum year: {MIN_YEAR}")
    
    setup_output_directory()
    
    all_results = []
    total_documents = 0
    
    for config in tqdm(SEARCH_CONFIGS, desc="Processing domains"):
        df = search_openalex(config, max_per_term)
        
        if not df.empty:
            save_results(df, config["domain"])
            all_results.append(df)
            total_documents += len(df)
    
    # Summary
    print("\n" + "="*60)
    print("📊 COLLECTION SUMMARY")
    print("="*60)
    print(f"   Total documents collected: {total_documents:,}")
    print(f"   Domains processed: {len(all_results)}/{len(SEARCH_CONFIGS)}")
    print(f"   Output directory: {OUTPUT_DIR.absolute()}")
    
    # Combine all results
    if all_results:
        master_df = pd.concat(all_results, ignore_index=True)
        
        # Remove duplicates by DOI
        if "doi" in master_df.columns:
            before = len(master_df)
            master_df = master_df.drop_duplicates(subset=["doi"], keep="first")
            print(f"   Duplicates removed: {before - len(master_df)}")
        
        master_file = OUTPUT_DIR / "openalex_all_domains.csv"
        master_df.to_csv(master_file, index=False, encoding="utf-8-sig")
        print(f"   Master file: {master_file.name} ({len(master_df):,} records)")
    
    print(f"\n   End time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*60)
    print("✅ Data collection complete!")
    
    return all_results


if __name__ == "__main__":
    # Run with configurable limits
    # Increase MAX_RESULTS_PER_TERM for more data
    run_all_searches(max_per_term=500)
