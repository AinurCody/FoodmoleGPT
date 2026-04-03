"""
FoodmoleGPT - Scopus Literature Data Fetcher
=============================================
This script fetches food science literature metadata from Elsevier Scopus database
using the pybliometrics library.

Usage:
    1. Ensure your API key is set in .env file as PYBLIOMETRICS_API_KEY
    2. Activate the foodmole conda environment
    3. Run: python src/fetch_scopus.py

Author: FoodmoleGPT Team
"""

import os
import sys
from pathlib import Path
from datetime import datetime

import pandas as pd
from dotenv import load_dotenv
from tqdm import tqdm

# Load environment variables from .env file
load_dotenv()

# Initialize pybliometrics
import pybliometrics
pybliometrics.init()

from pybliometrics.scopus import ScopusSearch

print("✅ pybliometrics initialized successfully")

# =============================================================================
# SEARCH CONFIGURATION - Food Science Subdomains
# =============================================================================

SEARCH_CONFIGS = [
    {
        "domain": "food_chemistry",
        "domain_cn": "食品化学",
        "query": 'TITLE-ABS-KEY("food chemistry" OR "bioactive compounds" OR "lipid oxidation" OR "maillard reaction") AND PUBYEAR > 2018',
        "description": "Research on chemical compounds, reactions, and molecular properties in food systems"
    },
    {
        "domain": "food_engineering", 
        "domain_cn": "食品工程",
        "query": 'TITLE-ABS-KEY("food processing" OR "encapsulation" OR "thermal processing" OR "shelf life") AND NOT TITLE-ABS-KEY("soil" OR "crop") AND PUBYEAR > 2018',
        "description": "Research on food processing technologies, preservation, and engineering methods"
    },
    {
        "domain": "food_microbiology",
        "domain_cn": "食品微生物学", 
        "query": 'TITLE-ABS-KEY("food microbiology" OR "probiotics" OR "foodborne pathogens" OR "fermentation") AND PUBYEAR > 2018',
        "description": "Research on microorganisms in food, including beneficial and harmful species"
    },
    {
        "domain": "sensory_science",
        "domain_cn": "感官科学",
        "query": 'TITLE-ABS-KEY("sensory evaluation" OR "flavor profile" OR "texture analysis" OR "consumer acceptance") AND PUBYEAR > 2018',
        "description": "Research on sensory properties, consumer perception, and quality assessment"
    },
    {
        "domain": "food_safety",
        "domain_cn": "食品安全",
        "query": 'TITLE-ABS-KEY("food safety" OR "food contamination" OR "mycotoxins" OR "pesticide residue" OR "heavy metals in food") AND PUBYEAR > 2018',
        "description": "Research on food safety hazards, contamination detection, and risk assessment"
    },
    {
        "domain": "nutrition_science",
        "domain_cn": "营养科学",
        "query": 'TITLE-ABS-KEY("functional food" OR "nutraceuticals" OR "dietary fiber" OR "antioxidant activity" OR "glycemic index") AND PUBYEAR > 2018',
        "description": "Research on nutritional properties, health benefits, and dietary interventions"
    },
]

# =============================================================================
# DATA OUTPUT CONFIGURATION
# =============================================================================

# Output directory for raw Scopus data
OUTPUT_DIR = Path("data/raw/scopus")

# Core fields to extract from Scopus results
CORE_FIELDS = [
    "doi",
    "title", 
    "description",  # This is the abstract field in pybliometrics
    "authkeywords",
    "coverDate",
    "publicationName",
    "citedby_count",
    "author_names",
    "author_afids",
    "affilname",
]


def setup_output_directory():
    """Create output directory if it doesn't exist."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"✅ Output directory ready: {OUTPUT_DIR.absolute()}")


def search_scopus(query: str, domain: str, max_results: int = None) -> pd.DataFrame:
    """
    Execute a Scopus search and return results as DataFrame.
    
    Args:
        query: Scopus search query string
        domain: Name of the research domain (for logging)
        max_results: Maximum number of results to fetch (None for all)
    
    Returns:
        DataFrame with search results
    """
    print(f"\n{'='*60}")
    print(f"🔍 Searching: {domain}")
    print(f"   Query: {query[:80]}...")
    
    try:
        # Execute search with subscriber access to get abstracts
        # subscriber=True: Access to full abstract content
        # view="STANDARD": Includes abstract (description field)
        search = ScopusSearch(
            query=query,
            subscriber=True,
            view="STANDARD",  # STANDARD view includes abstracts
            download=True,
            verbose=False
        )
        
        if search.results is None:
            print(f"   ⚠️ No results found for {domain}")
            return pd.DataFrame()
        
        # Get result count
        result_count = search.get_results_size()
        print(f"   📊 Found {result_count:,} documents")
        
        # Convert to DataFrame
        df = pd.DataFrame(search.results)
        
        # Limit results if specified
        if max_results and len(df) > max_results:
            df = df.head(max_results)
            print(f"   ⚠️ Limited to {max_results} results")
        
        # Rename 'description' to 'abstract' for clarity
        if 'description' in df.columns:
            df = df.rename(columns={'description': 'abstract'})
        
        # Add metadata columns
        df['search_domain'] = domain
        df['fetch_date'] = datetime.now().isoformat()
        
        # Select and reorder columns (keep only what exists)
        available_cols = ['doi', 'title', 'abstract', 'authkeywords', 
                         'coverDate', 'publicationName', 'citedby_count',
                         'author_names', 'affilname', 'search_domain', 'fetch_date']
        cols_to_keep = [c for c in available_cols if c in df.columns]
        df = df[cols_to_keep]
        
        # Count abstracts
        abstract_count = df['abstract'].notna().sum() if 'abstract' in df.columns else 0
        print(f"   📝 Documents with abstracts: {abstract_count:,} ({abstract_count/len(df)*100:.1f}%)")
        
        return df
        
    except Exception as e:
        print(f"   ❌ Error searching {domain}: {str(e)}")
        return pd.DataFrame()


def save_results(df: pd.DataFrame, domain: str) -> Path:
    """
    Save search results to CSV file.
    
    Args:
        df: DataFrame with search results
        domain: Domain name for filename
    
    Returns:
        Path to saved file
    """
    if df.empty:
        print(f"   ⚠️ No data to save for {domain}")
        return None
    
    output_file = OUTPUT_DIR / f"scopus_{domain}.csv"
    df.to_csv(output_file, index=False, encoding='utf-8-sig')
    print(f"   💾 Saved: {output_file} ({len(df):,} records)")
    return output_file


def run_all_searches(max_results_per_domain: int = None):
    """
    Run all configured searches and save results.
    
    Args:
        max_results_per_domain: Optional limit on results per domain
    """
    print("\n" + "="*60)
    print("🚀 FoodmoleGPT - Scopus Data Collection Pipeline")
    print("="*60)
    print(f"   Start time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"   Domains to search: {len(SEARCH_CONFIGS)}")
    if max_results_per_domain:
        print(f"   Max results per domain: {max_results_per_domain:,}")
    
    # Setup output directory
    setup_output_directory()
    
    # Track results
    all_results = []
    total_documents = 0
    
    # Run searches with progress bar
    for config in tqdm(SEARCH_CONFIGS, desc="Processing domains"):
        df = search_scopus(
            query=config["query"],
            domain=config["domain"],
            max_results=max_results_per_domain
        )
        
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
    
    # Combine all results into one master file
    if all_results:
        master_df = pd.concat(all_results, ignore_index=True)
        master_file = OUTPUT_DIR / "scopus_all_domains.csv"
        master_df.to_csv(master_file, index=False, encoding='utf-8-sig')
        print(f"   Master file: {master_file} ({len(master_df):,} records)")
    
    print(f"\n   End time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*60)
    print("✅ Data collection complete!")
    
    return all_results


if __name__ == "__main__":
    # Run with optional limit for testing
    # Set to None to fetch all results (can be thousands of documents)
    # Set to a number (e.g., 100) for testing
    MAX_RESULTS = None  # Change to 100 for testing
    
    run_all_searches(max_results_per_domain=MAX_RESULTS)
