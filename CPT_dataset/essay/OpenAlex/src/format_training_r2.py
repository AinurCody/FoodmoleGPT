"""
FoodmoleGPT Round 2 - Training Format Conversion & R1+R2 Merge
================================================================
Formats R2 filtered data into training JSONL.
Also provides a merge step to combine R1 + R2 training data.

Usage:
    conda activate foodmole

    # Format R2 data only
    python src/format_training_r2.py

    # Merge R1 + R2 training data into combined set
    python src/format_training_r2.py --merge
"""

import json
import sys
import argparse
from pathlib import Path
from datetime import datetime
from collections import Counter

if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if sys.stderr.encoding != 'utf-8':
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# =============================================================================
# CONFIG
# =============================================================================

# Round 2 cleaned data (output of clean_text_quality.py)
# Falls back to filtered data if cleaned versions don't exist yet
_CLEANED_FULLTEXT = Path("D:/FoodmoleGPT/data/filtered_r2_cleaned/food_fulltext_cleaned.jsonl")
_CLEANED_ABSTRACT = Path("D:/FoodmoleGPT/data/filtered_r2_cleaned/food_abstract_cleaned.jsonl")
_FILTERED_FULLTEXT = Path("D:/FoodmoleGPT/data/filtered_r2/food_fulltext_filtered.jsonl")
_FILTERED_ABSTRACT = Path("D:/FoodmoleGPT/data/filtered_r2/food_abstract_filtered.jsonl")

R2_FULLTEXT = _CLEANED_FULLTEXT if _CLEANED_FULLTEXT.exists() else _FILTERED_FULLTEXT
R2_ABSTRACT = _CLEANED_ABSTRACT if _CLEANED_ABSTRACT.exists() else _FILTERED_ABSTRACT

R2_OUTPUT_DIR = Path("D:/FoodmoleGPT/data/training_r2")

# Round 1 training data (for merge)
R1_TRAINING_DIR = Path("D:/FoodmoleGPT/data/training")
COMBINED_DIR = Path("D:/FoodmoleGPT/data/training_combined")

REPORT_FILE = R2_OUTPUT_DIR / "format_report_r2.txt"

MIN_FULLTEXT_CHARS = 2000
MIN_ABSTRACT_CHARS = 100

# Tier-based repeat sampling DISABLED — all records written once.
# (Previously: Q1×3, Q2×2, Q3/Q4×1; removed per user request.)
TIER_REPEAT = {"Q1": 1, "Q2": 1, "Q3": 1, "Q4": 1}

JOURNAL_TIER = {
    "Journal of Agricultural and Food Chemistry": "Q1",
    "Food Chemistry": "Q1",
    "Journal of Animal Science": "Q1",
    "Nutrients": "Q1",
    "Journal of Dairy Science": "Q1",
    "Poultry Science": "Q1",
    "Aquaculture": "Q1",
    "Journal of Nutrition": "Q1",
    "Journal of Food Science": "Q1",
    "Foods": "Q1",
    "Journal of the Science of Food and Agriculture": "Q1",
    "Carbohydrate Polymers": "Q1",
    "American Journal of Clinical Nutrition": "Q1",
    "LWT": "Q1",
    "Food Research International": "Q1",
    "British Journal Of Nutrition": "Q1",
    "Food and Chemical Toxicology": "Q1",
    "Food Hydrocolloids": "Q1",
    "Food Control": "Q1",
    "Journal of Food Engineering": "Q1",
    "International Journal of Food Microbiology": "Q1",
    "Meat Science": "Q1",
    "Food & Function": "Q1",
    "Food Bioscience": "Q1",
    "Journal of Food Composition and Analysis": "Q1",
    "European Food Research and Technology": "Q1",
    "Journal of Functional Foods": "Q1",
    "Postharvest Biology and Technology": "Q1",
    "Nutrition Research": "Q1",
    "The Journal of Nutritional Biochemistry": "Q1",
    "International Dairy Journal": "Q1",
    "Journal of Cereal Science": "Q1",
    "Trends in Food Science & Technology": "Q1",
    "Critical Reviews in Food Science and Nutrition": "Q1",
    "Food Quality and Preference": "Q1",
    "European Journal of Nutrition": "Q1",
    "Food and Bioprocess Technology": "Q1",
    "Innovative Food Science & Emerging Technologies": "Q1",
    "Food Chemistry X": "Q1",
    "International Journal of Food Sciences and Nutrition": "Q1",
    "Food Science and Human Wellness": "Q1",
    "Food Packaging and Shelf Life": "Q1",
    "Comprehensive Reviews in Food Science and Food Safety": "Q1",
    "Current Research in Food Science": "Q1",
    "Food Reviews International": "Q1",
    "Food Frontiers": "Q1",
    "Advances in food and nutrition research": "Q1",
    "Phytochemistry": "Q2",
    "Carbohydrate Research": "Q2",
    "Journal of the American Oil Chemists Society": "Q2",
    "Journal of Food Protection": "Q2",
    "The Journal of Agricultural Science": "Q2",
    "Lipids": "Q2",
    "Journal of Food Processing and Preservation": "Q2",
    "Journal of Food Science and Technology": "Q2",
    "Drying Technology": "Q2",
    "Journal of Dairy Research": "Q2",
    "Journal of the Institute of Brewing": "Q2",
    "Journal of Essential Oil Research": "Q2",
    "Journal of Food Process Engineering": "Q2",
    "Food Analytical Methods": "Q2",
    "American Journal of Enology and Viticulture": "Q2",
    "Cereal Chemistry": "Q2",
    "Flavour and Fragrance Journal": "Q2",
    "Food and Bioproducts Processing": "Q2",
    "Foodborne Pathogens and Disease": "Q2",
    "Journal of Texture Studies": "Q2",
    "Food Additives & Contaminants": "Q2",
    "Journal of Food Safety": "Q2",
    "Journal of the American Society of Brewing Chemists": "Q2",
    "Journal of Sensory Studies": "Q2",
    "Polish Journal of Food and Nutrition Sciences": "Q2",
    "NFS Journal": "Q2",
    "Czech Journal of Food Sciences": "Q3",
    "Italian Journal of Food Science": "Q3",
}


# =============================================================================
# TEXT FORMATTING (identical to Round 1)
# =============================================================================

def format_fulltext_record(doc: dict) -> str:
    parts = []
    if doc.get("title"):
        parts.append(f"Title: {doc['title']}")
    if doc.get("authors"):
        parts.append(f"Authors: {doc['authors']}")
    if doc.get("publication_year"):
        parts.append(f"Year: {doc['publication_year']}")
    if doc.get("venue"):
        parts.append(f"Venue: {doc['venue']}")
    if doc.get("keywords"):
        parts.append(f"Keywords: {doc['keywords']}")

    abstract = doc.get("abstract", "")
    if abstract and len(abstract) > 50:
        parts.append("")
        parts.append("Abstract:")
        parts.append(abstract.strip())

    full_text = doc.get("full_text", "")
    if full_text:
        parts.append("")
        parts.append("Full Text:")
        parts.append(full_text.strip())

    return "\n".join(parts)


def format_abstract_record(doc: dict) -> str:
    parts = []
    if doc.get("title"):
        parts.append(f"Title: {doc['title']}")
    if doc.get("authors"):
        parts.append(f"Authors: {doc['authors']}")
    if doc.get("publication_year"):
        parts.append(f"Year: {doc['publication_year']}")
    if doc.get("venue"):
        parts.append(f"Venue: {doc['venue']}")
    if doc.get("keywords"):
        parts.append(f"Keywords: {doc['keywords']}")

    abstract = doc.get("abstract", "")
    if abstract and len(abstract) > 50:
        parts.append("")
        parts.append("Abstract:")
        parts.append(abstract.strip())

    return "\n".join(parts)


# =============================================================================
# STREAMING PROCESSOR
# =============================================================================

def count_lines(path):
    count = 0
    with open(path, "r", encoding="utf-8") as f:
        for _ in f:
            count += 1
    return count


def process_file_streaming(input_path, format_fn, prefix, min_chars, output_dir):
    print(f"\n   [FILE] Processing: {input_path.name}")
    sys.stdout.flush()

    print("      Counting records...")
    sys.stdout.flush()
    total_lines = count_lines(input_path)
    print(f"      Total lines: {total_lines:,}")
    sys.stdout.flush()

    print("      Formatting and writing...")
    sys.stdout.flush()
    out_path = output_dir / f"{prefix}.jsonl"

    written = 0
    skipped_short = 0
    skipped_empty = 0
    text_lengths = []
    word_counts = []
    tier_stats = Counter()

    with open(out_path, "w", encoding="utf-8") as f_out, \
         open(input_path, "r", encoding="utf-8") as f_in:

        for i, line in enumerate(f_in):
            doc = json.loads(line.strip())
            text = format_fn(doc)

            if not text:
                skipped_empty += 1
                continue
            if len(text) < min_chars:
                skipped_short += 1
                continue

            record_json = json.dumps({"text": text}, ensure_ascii=False) + "\n"

            # Track tier (for reporting only, no repeat sampling)
            venue = doc.get("venue", "")
            tier = JOURNAL_TIER.get(venue, "unknown")
            tier_stats[tier] += 1

            f_out.write(record_json)
            written += 1

            text_lengths.append(len(text))
            word_counts.append(len(text.split()))

            if (i + 1) % 10000 == 0:
                print(f"\r      Processed: {i+1:,} / {total_lines:,}    ", end="")
                sys.stdout.flush()

    print(f"\r      Done: {written:,} records "
          f"(skipped: {skipped_short} short, {skipped_empty} empty)")
    print(f"      Output: {out_path.name}")
    print(f"      Tier distribution:")
    for tier in ["Q1", "Q2", "Q3", "Q4", "unknown"]:
        if tier_stats[tier] > 0:
            print(f"        {tier}: {tier_stats[tier]:>8,}")
    sys.stdout.flush()

    size = out_path.stat().st_size
    if size > 1024**3:
        print(f"        {out_path.name}: {size/1024**3:.2f} GB")
    else:
        print(f"        {out_path.name}: {size/1024**2:.1f} MB")
    sys.stdout.flush()

    return {
        "prefix": prefix,
        "total": written,
        "skipped_short": skipped_short,
        "skipped_empty": skipped_empty,
        "tier_stats": dict(tier_stats),
        "avg_chars": sum(text_lengths) // len(text_lengths) if text_lengths else 0,
        "median_chars": sorted(text_lengths)[len(text_lengths) // 2] if text_lengths else 0,
        "avg_words": sum(word_counts) // len(word_counts) if word_counts else 0,
        "median_words": sorted(word_counts)[len(word_counts) // 2] if word_counts else 0,
    }


# =============================================================================
# MERGE R1 + R2
# =============================================================================

def merge_training_data():
    """Merge Round 1 and Round 2 training data into combined directory.

    R1 has separate train/val files; R2 has single files (no val split).
    All are merged into single files per type (fulltext.jsonl, abstract.jsonl).
    The user will do their own train/val split after merging.
    """
    print("\n" + "=" * 70)
    print("MERGING R1 + R2 TRAINING DATA")
    print("=" * 70)

    COMBINED_DIR.mkdir(parents=True, exist_ok=True)

    for prefix in ["fulltext", "abstract"]:
        combined_path = COMBINED_DIR / f"{prefix}.jsonl"
        print(f"\n   Merging {prefix}...")
        total = 0

        with open(combined_path, "w", encoding="utf-8") as f_out:
            # R1: concatenate train + val into one
            for suffix in ["_train.jsonl", "_val.jsonl"]:
                r1_path = R1_TRAINING_DIR / f"{prefix}{suffix}"
                if r1_path.exists():
                    count = 0
                    with open(r1_path, "r", encoding="utf-8") as f_in:
                        for line in f_in:
                            f_out.write(line)
                            count += 1
                    print(f"      R1 {r1_path.name}: {count:,} records")
                    total += count

            # R2: single file
            r2_path = R2_OUTPUT_DIR / f"{prefix}.jsonl"
            if r2_path.exists():
                count = 0
                with open(r2_path, "r", encoding="utf-8") as f_in:
                    for line in f_in:
                        f_out.write(line)
                        count += 1
                print(f"      R2 {r2_path.name}: {count:,} records")
                total += count
            else:
                print(f"      R2: not found ({r2_path})")

        size = combined_path.stat().st_size
        if size > 1024**3:
            print(f"      Combined: {total:,} records ({size/1024**3:.2f} GB)")
        else:
            print(f"      Combined: {total:,} records ({size/1024**2:.1f} MB)")

    print(f"\n   Output: {COMBINED_DIR}")
    print("   Merge complete!")


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="FoodmoleGPT R2 Format + Merge")
    parser.add_argument("--merge", action="store_true",
                       help="Also merge R1 + R2 training data")
    args = parser.parse_args()

    print("=" * 70)
    print("FoodmoleGPT Round 2 - Training Format Conversion")
    print("=" * 70)
    sys.stdout.flush()
    start_time = datetime.now()

    R2_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    stats_list = []

    if R2_FULLTEXT.exists():
        stats = process_file_streaming(
            R2_FULLTEXT, format_fulltext_record,
            "fulltext", MIN_FULLTEXT_CHARS, R2_OUTPUT_DIR,
        )
        stats_list.append(stats)
    else:
        print(f"\n   ⚠️ R2 fulltext file not found: {R2_FULLTEXT}")

    if R2_ABSTRACT.exists():
        stats = process_file_streaming(
            R2_ABSTRACT, format_abstract_record,
            "abstract", MIN_ABSTRACT_CHARS, R2_OUTPUT_DIR,
        )
        stats_list.append(stats)
    else:
        print(f"\n   ⚠️ R2 abstract file not found: {R2_ABSTRACT}")

    # Report
    if stats_list:
        total_records = sum(s["total"] for s in stats_list)

        report_lines = [
            "=" * 70,
            "FoodmoleGPT Round 2 - Training Data Format Report",
            f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "=" * 70,
            "",
            f"Total records:   {total_records:>10,}",
            "(No tier repeats, no val split — single file per type)",
            "",
        ]
        for s in stats_list:
            report_lines.extend([
                f"DATASET: {s['prefix'].upper()}",
                f"  Records: {s['total']:,}",
                f"  Avg: {s['avg_chars']:,} chars ({s['avg_words']:,} words)",
                "",
            ])

        report = "\n".join(report_lines)
        with open(REPORT_FILE, "w", encoding="utf-8") as f:
            f.write(report)
        print(f"\n{report}")

    # Merge if requested
    if args.merge:
        merge_training_data()

    elapsed = datetime.now() - start_time
    print(f"\nElapsed: {elapsed}")
    print("[DONE] Round 2 training format conversion complete!")
    sys.stdout.flush()


if __name__ == "__main__":
    main()
