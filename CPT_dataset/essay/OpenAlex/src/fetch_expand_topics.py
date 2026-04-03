"""
FoodmoleGPT - Expanded Topic Collection
========================================
Uses fine-grained search terms to collect papers in sub-domains
that were missed by broad queries (due to deduplication).

Loads existing IDs from all previously collected files to avoid duplicates.

Usage:
    conda activate foodmole
    python src/fetch_expand_topics.py
"""

import time
from pathlib import Path
from datetime import datetime

import pandas as pd
from tqdm import tqdm
import pyalex
from pyalex import Works

pyalex.config.email = "foodmolegpt@example.com"

print("✅ Expanded Topic Collector initialized")

# =============================================================================
# CONFIGURATION
# =============================================================================

OUTPUT_DIR = Path("D:/FoodmoleGPT/data/raw/openalex_concepts")
CONCEPT_DIR = OUTPUT_DIR / "by_concept"

MIN_YEAR = 2010
MAX_YEAR = 2026
BATCH_SIZE = 200

# Fine-grained search terms organized by sub-domain
# Each term targets a specific niche to maximize unique papers
TOPIC_GROUPS = [
    # ===== FOOD MICROBIOLOGY =====
    {
        "group": "food_microbiology",
        "group_cn": "食品微生物学",
        "terms": [
            ("probiotics gut health", 15000),
            ("lactic acid bacteria fermentation", 15000),
            ("foodborne pathogen detection", 15000),
            ("food spoilage microorganisms", 10000),
            ("fermented food microbiome", 10000),
            ("antimicrobial food packaging", 8000),
            ("starter culture dairy", 8000),
            ("biopreservation food", 5000),
            ("yeast fermentation wine beer", 8000),
            ("listeria salmonella campylobacter food", 10000),
            ("food biofilm", 5000),
            ("bacteriophage food safety", 5000),
        ],
    },
    # ===== NUTRITION & DIETETICS =====
    {
        "group": "nutrition_dietetics",
        "group_cn": "营养与膳食学",
        "terms": [
            ("functional food bioactive", 15000),
            ("nutraceuticals health benefits", 10000),
            ("dietary fiber prebiotic", 10000),
            ("antioxidant activity polyphenol", 15000),
            ("bioavailability nutrients absorption", 8000),
            ("food fortification micronutrient", 8000),
            ("omega-3 fatty acids health", 8000),
            ("glycemic index diabetes food", 8000),
            ("protein digestibility amino acid", 8000),
            ("vitamin deficiency supplementation", 8000),
            ("gut microbiota diet", 15000),
            ("obesity diet intervention", 10000),
        ],
    },
    # ===== FOOD ENGINEERING (expanded) =====
    {
        "group": "food_engineering_expanded",
        "group_cn": "食品工程(扩展)",
        "terms": [
            ("high pressure processing food", 8000),
            ("pulsed electric field food treatment", 5000),
            ("ultrasound food processing", 8000),
            ("microencapsulation food ingredient", 8000),
            ("spray drying food", 8000),
            ("extrusion food snack", 5000),
            ("ohmic heating food", 3000),
            ("supercritical fluid extraction food", 5000),
            ("membrane filtration food", 5000),
            ("cold plasma food decontamination", 5000),
            ("3D printing food", 3000),
            ("nanoemulsion food delivery", 8000),
        ],
    },
    # ===== FOOD SAFETY (expanded) =====
    {
        "group": "food_safety_expanded",
        "group_cn": "食品安全(扩展)",
        "terms": [
            ("mycotoxin contamination cereals", 10000),
            ("pesticide residue fruit vegetable", 10000),
            ("heavy metal contamination food", 10000),
            ("food allergen detection", 8000),
            ("food adulteration authentication", 10000),
            ("antibiotic resistance food animal", 8000),
            ("acrylamide food processing", 5000),
            ("aflatoxin milk grain", 8000),
            ("food irradiation safety", 5000),
            ("HACCP food quality management", 5000),
            ("bisphenol food contact material", 5000),
            ("microplastics food contamination", 5000),
        ],
    },
    # ===== FOOD ANALYSIS & QUALITY =====
    {
        "group": "food_analysis",
        "group_cn": "食品分析与质量",
        "terms": [
            ("HPLC food analysis", 8000),
            ("mass spectrometry food metabolomics", 8000),
            ("NIR spectroscopy food quality", 8000),
            ("electronic nose tongue food", 5000),
            ("hyperspectral imaging food", 5000),
            ("PCR food authentication", 5000),
            ("biosensor food detection", 8000),
            ("rheology food texture", 5000),
            ("food proteomics", 5000),
            ("NMR food analysis", 5000),
        ],
    },
    # ===== DAIRY SCIENCE =====
    {
        "group": "dairy_science",
        "group_cn": "乳品科学",
        "terms": [
            ("cheese ripening microbiology", 8000),
            ("yogurt probiotic fermentation", 8000),
            ("whey protein isolate concentrate", 8000),
            ("casein micelle milk", 5000),
            ("milk pasteurization quality", 5000),
            ("goat sheep milk products", 5000),
            ("dairy allergy lactose intolerance", 5000),
        ],
    },
    # ===== MEAT & SEAFOOD SCIENCE =====
    {
        "group": "meat_seafood",
        "group_cn": "肉类与水产科学",
        "terms": [
            ("meat quality tenderness color", 8000),
            ("meat curing nitrite", 5000),
            ("poultry processing safety", 5000),
            ("fish freshness quality", 8000),
            ("seafood preservation storage", 5000),
            ("meat protein oxidation", 5000),
            ("aquaculture fish nutrition", 8000),
        ],
    },
    # ===== PLANT-BASED & NOVEL FOODS =====
    {
        "group": "plant_based_novel",
        "group_cn": "植物基与新型食品",
        "terms": [
            ("plant-based meat alternative", 8000),
            ("soy protein isolate", 5000),
            ("pea protein food application", 5000),
            ("edible insect protein", 5000),
            ("algae spirulina food", 5000),
            ("cultured meat cell-based", 5000),
            ("plant-based milk oat almond", 5000),
        ],
    },
    # ===== CEREAL & BAKERY SCIENCE =====
    {
        "group": "cereal_bakery",
        "group_cn": "谷物与烘焙科学",
        "terms": [
            ("wheat flour gluten bread", 10000),
            ("starch modification food", 8000),
            ("rice quality milling", 5000),
            ("sourdough fermentation bread", 5000),
            ("celiac disease gluten-free", 5000),
            ("cereal bioactive compound", 5000),
        ],
    },
    # ===== OILS & FATS =====
    {
        "group": "oils_fats",
        "group_cn": "油脂科学",
        "terms": [
            ("edible oil oxidation stability", 8000),
            ("olive oil quality phenolic", 8000),
            ("trans fat hydrogenation", 5000),
            ("lipid digestion emulsion", 5000),
            ("essential oil food preservation", 8000),
        ],
    },
    # ===== FOOD PACKAGING =====
    {
        "group": "food_packaging",
        "group_cn": "食品包装",
        "terms": [
            ("active intelligent food packaging", 8000),
            ("biodegradable food packaging", 8000),
            ("edible film coating food", 8000),
            ("chitosan food packaging", 5000),
            ("modified atmosphere packaging food", 5000),
            ("nanocomposite food packaging", 5000),
        ],
    },
    # ===== SENSORY & CONSUMER SCIENCE =====
    {
        "group": "sensory_consumer",
        "group_cn": "感官与消费者科学",
        "terms": [
            ("sensory evaluation food product", 8000),
            ("consumer acceptance food", 8000),
            ("flavor volatile compound food", 8000),
            ("texture mouthfeel food", 5000),
            ("food neophobia preference", 3000),
        ],
    },
]


def load_existing_ids() -> set:
    """Load all existing openalex_ids from previously collected files."""
    seen = set()
    if not CONCEPT_DIR.exists():
        return seen

    for csv_file in CONCEPT_DIR.glob("*.csv"):
        try:
            df = pd.read_csv(csv_file, usecols=["openalex_id"])
            seen.update(df["openalex_id"].tolist())
            print(f"   Loaded {len(df):,} IDs from {csv_file.name}")
        except Exception as e:
            print(f"   ⚠️ Could not load {csv_file.name}: {e}")

    return seen


def extract_work_data(work: dict, group_name: str) -> dict:
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
        "primary_concept": group_name,
    }


def collect_term(search_term: str, max_papers: int, group_name: str, seen_ids: set) -> list:
    """Collect papers for a single search term with retry logic."""
    MAX_RETRIES = 3
    RETRY_WAITS = [10, 30, 60]  # seconds

    for attempt in range(MAX_RETRIES + 1):
        try:
            query = Works().search(search_term).filter(
                publication_year=f"{MIN_YEAR}-{MAX_YEAR}",
                has_abstract=True,
            ).sort(cited_by_count="desc")

            results = []
            for page in query.paginate(per_page=BATCH_SIZE, n_max=max_papers * 2):
                for work in page:
                    wid = work.get("id")
                    if wid and wid not in seen_ids:
                        seen_ids.add(wid)
                        results.append(extract_work_data(work, group_name))

                        if len(results) >= max_papers:
                            return results

                if len(results) >= max_papers:
                    break

                time.sleep(0.05)  # Slightly longer delay between pages

            return results

        except Exception as e:
            err_msg = str(e)
            if attempt < MAX_RETRIES and ("Connection" in err_msg or "Timeout" in err_msg or "HTTP" in err_msg):
                wait = RETRY_WAITS[attempt]
                print(f" RETRY({attempt+1}/{MAX_RETRIES}, wait {wait}s)", end="", flush=True)
                time.sleep(wait)
            else:
                print(f" ERR:{err_msg[:50]}")
                return []


def main():
    print("\n" + "=" * 70)
    print("🚀 FoodmoleGPT - Expanded Topic Collection")
    print("=" * 70)
    start = datetime.now()
    print(f"   Start: {start.strftime('%Y-%m-%d %H:%M:%S')}")

    CONCEPT_DIR.mkdir(parents=True, exist_ok=True)

    # Load existing IDs
    print("\n📂 Loading existing data for deduplication:")
    seen_ids = load_existing_ids()
    print(f"   Total existing IDs: {len(seen_ids):,}")

    all_group_dfs = []

    for group in TOPIC_GROUPS:
        group_name = group["group"]
        print(f"\n{'='*70}")
        print(f"📚 {group['group_cn']} ({group_name})")
        print(f"   Terms: {len(group['terms'])}")

        group_works = []

        for term, max_n in group["terms"]:
            print(f"   🔍 '{term}' (max {max_n:,})", end=" ", flush=True)
            results = collect_term(term, max_n, group_name, seen_ids)
            group_works.extend(results)
            print(f"→ {len(results):,} new")

        if group_works:
            df = pd.DataFrame(group_works)
            df["fetch_date"] = datetime.now().isoformat()

            # Save group file
            out = CONCEPT_DIR / f"expanded_{group_name}.csv"
            df.to_csv(out, index=False, encoding="utf-8-sig")
            print(f"   💾 {out.name}: {len(df):,} papers")
            all_group_dfs.append(df)
        else:
            print(f"   ⚠️ No new papers collected")

    # Build updated master file
    print("\n" + "=" * 70)
    print("📊 BUILDING UPDATED MASTER FILE")
    print("=" * 70)

    # Load all existing concept files
    all_dfs = []
    for f in sorted(CONCEPT_DIR.glob("*.csv")):
        try:
            df = pd.read_csv(f)
            all_dfs.append(df)
        except Exception:
            pass

    if all_dfs:
        master = pd.concat(all_dfs, ignore_index=True)
        before = len(master)
        master = master.drop_duplicates(subset=["openalex_id"], keep="first")
        print(f"   Dedup: {before:,} → {len(master):,}")

        # Tier labels by citation
        master["tier"] = master["cited_by_count"].apply(
            lambda x: 1 if x >= 50 else (2 if x >= 10 else 3)
        )
        master["tier_label"] = master["tier"].map({
            1: "high_impact", 2: "medium_impact", 3: "standard"
        })

        master_file = OUTPUT_DIR / "master_all_concepts.csv"
        master.to_csv(master_file, index=False, encoding="utf-8-sig")

        print(f"\n   📊 FINAL STATISTICS:")
        print(f"   Total papers:  {len(master):,}")
        print(f"   With abstract: {master['abstract'].notna().sum():,}")
        print(f"   With DOI:      {master['doi'].notna().sum():,}")
        print(f"   Tier 1 (≥50):  {(master['tier']==1).sum():,}")
        print(f"   Tier 2 (≥10):  {(master['tier']==2).sum():,}")
        print(f"   Tier 3 (<10):  {(master['tier']==3).sum():,}")
        print(f"\n   By domain:")
        for c, n in master["primary_concept"].value_counts().head(20).items():
            print(f"      {c:30} {n:>8,}")
        print(f"\n   Master: {master_file}")
        print(f"   Size:   {master_file.stat().st_size / 1024 / 1024:.1f} MB")

    elapsed = datetime.now() - start
    print(f"\n   Elapsed: {elapsed}")
    print("=" * 70)
    print("✅ Expanded collection complete!")


if __name__ == "__main__":
    main()
