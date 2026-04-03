"""
FoodmoleGPT - Merge Full Text with Metadata
=============================================
Joins OpenAlex metadata + Semantic Scholar Corpus IDs + peS2o full text
into a unified JSONL dataset for LLM training.

Join chain:
  master_cleaned.csv --(DOI)--> doi_to_corpusid.csv --(s2_corpus_id)--> fulltext.jsonl

Output layers:
  1. food_science_merged.jsonl   — papers WITH full text (312K, for training)
  2. food_science_abstract.jsonl — papers with abstract only (354K, supplementary)
  3. merge_report.txt            — statistics report

Usage:
    conda activate foodmole
    python src/merge_fulltext.py
"""

import json
import os
from pathlib import Path
from datetime import datetime
from collections import Counter

import pandas as pd

# =============================================================================
# CONFIGURATION
# =============================================================================

CLEANED_CSV = Path("D:/FoodmoleGPT/data/cleaned/master_cleaned.csv")
ABSTRACT_CSV = Path("D:/FoodmoleGPT/data/cleaned/master_with_abstract.csv")
MAPPING_CSV = Path("D:/FoodmoleGPT/data/fulltext/doi_to_corpusid.csv")
FULLTEXT_JSONL = Path("D:/FoodmoleGPT/data/fulltext/extracted/food_science_fulltext.jsonl")

OUTPUT_DIR = Path("D:/FoodmoleGPT/data/merged")
MERGED_FULLTEXT = OUTPUT_DIR / "food_science_merged.jsonl"
MERGED_ABSTRACT = OUTPUT_DIR / "food_science_abstract.jsonl"
REPORT_FILE = OUTPUT_DIR / "merge_report.txt"
STATS_FILE = OUTPUT_DIR / "merge_stats.json"

# Metadata columns to keep in the merged output
METADATA_COLS = [
    "openalex_id", "doi", "title", "abstract",
    "publication_year", "publication_date", "venue",
    "cited_by_count", "authors", "institutions",
    "keywords", "is_open_access", "type",
    "primary_concept", "abstract_quality",
]


def load_metadata():
    """Load and prepare OpenAlex metadata."""
    print("   Loading metadata from master_cleaned.csv...")
    df = pd.read_csv(CLEANED_CSV, usecols=METADATA_COLS)
    print(f"   Total papers: {len(df):,}")
    print(f"   With DOI: {df['doi'].notna().sum():,}")
    return df


def load_mapping():
    """Load DOI → Corpus ID mapping."""
    print("   Loading DOI → Corpus ID mapping...")
    mapping = pd.read_csv(MAPPING_CSV, usecols=["doi", "s2_corpus_id"], on_bad_lines="skip")
    # Convert Corpus ID from float to clean integer string
    mapping = mapping.dropna(subset=["s2_corpus_id"])
    mapping["s2_corpus_id"] = mapping["s2_corpus_id"].apply(
        lambda x: str(int(float(x)))
    )
    print(f"   Mapped DOIs: {len(mapping):,}")
    return mapping


def load_fulltext_index():
    """Build an index of Corpus ID → full text from the JSONL file.

    Memory-efficient: stores file byte offsets instead of full text.
    Returns a dict mapping corpus_id → byte offset in the JSONL file.
    """
    print("   Building full text index (scanning 11.5 GB JSONL)...")
    index = {}
    offset = 0
    count = 0
    with open(FULLTEXT_JSONL, "r", encoding="utf-8") as f:
        while True:
            line_start = f.tell()
            line = f.readline()
            if not line:
                break
            line = line.strip()
            if not line:
                continue
            try:
                # Only parse the corpus ID (fast partial parse)
                # Find "s2_corpus_id": "XXXXX" without full JSON parse
                idx = line.find('"s2_corpus_id"')
                if idx >= 0:
                    # Extract the value
                    val_start = line.index('"', idx + 15) + 1
                    val_end = line.index('"', val_start)
                    corpus_id = line[val_start:val_end]
                    index[corpus_id] = line_start
                    count += 1
            except (ValueError, json.JSONDecodeError):
                continue

            if count % 50000 == 0:
                print(f"\r      Indexed: {count:,}    ", end="", flush=True)

    print(f"\r      Indexed: {count:,} full text papers    ")
    return index


def read_fulltext_at_offset(offset):
    """Read a single full text record from the JSONL file at a byte offset."""
    with open(FULLTEXT_JSONL, "r", encoding="utf-8") as f:
        f.seek(offset)
        line = f.readline()
        return json.loads(line.strip())


def merge_and_save(metadata_df, mapping_df, fulltext_index):
    """Merge metadata with full text and save as JSONL files."""
    print("\n" + "=" * 70)
    print("🔗 MERGING DATA")
    print("=" * 70)

    # Step 1: Join metadata with DOI mapping
    print("   Step 1: Joining metadata with Corpus ID mapping...")
    merged = metadata_df.merge(mapping_df, on="doi", how="left")
    has_corpus_id = merged["s2_corpus_id"].notna()
    print(f"   Papers with Corpus ID: {has_corpus_id.sum():,}")

    # Step 2: Check which papers have full text
    print("   Step 2: Checking full text availability...")
    merged["has_fulltext"] = merged["s2_corpus_id"].apply(
        lambda x: x in fulltext_index if pd.notna(x) else False
    )
    fulltext_count = merged["has_fulltext"].sum()
    print(f"   Papers with full text: {fulltext_count:,}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Step 3: Write merged JSONL with full text
    print(f"\n   Step 3: Writing merged full text JSONL...")
    ft_written = 0
    year_dist = Counter()
    venue_dist = Counter()
    text_lengths = []

    with open(MERGED_FULLTEXT, "w", encoding="utf-8") as f:
        for _, row in merged[merged["has_fulltext"]].iterrows():
            corpus_id = row["s2_corpus_id"]
            offset = fulltext_index[corpus_id]
            ft_data = read_fulltext_at_offset(offset)

            record = {
                # Identifiers
                "openalex_id": row.get("openalex_id", ""),
                "doi": row.get("doi", ""),
                "s2_corpus_id": corpus_id,
                # Metadata
                "title": row.get("title", ""),
                "abstract": row.get("abstract", "") if pd.notna(row.get("abstract")) else "",
                "publication_year": int(row["publication_year"]) if pd.notna(row.get("publication_year")) else None,
                "venue": row.get("venue", "") if pd.notna(row.get("venue")) else "",
                "cited_by_count": int(row["cited_by_count"]) if pd.notna(row.get("cited_by_count")) else 0,
                "authors": row.get("authors", "") if pd.notna(row.get("authors")) else "",
                "keywords": row.get("keywords", "") if pd.notna(row.get("keywords")) else "",
                "primary_concept": row.get("primary_concept", "") if pd.notna(row.get("primary_concept")) else "",
                "is_open_access": bool(row.get("is_open_access")) if pd.notna(row.get("is_open_access")) else False,
                "type": row.get("type", "") if pd.notna(row.get("type")) else "",
                # Full text
                "full_text": ft_data.get("text", ""),
                "full_text_length": ft_data.get("text_length", 0),
                "full_text_word_count": ft_data.get("word_count", 0),
                "full_text_source": ft_data.get("source", ""),
            }

            f.write(json.dumps(record, ensure_ascii=False) + "\n")
            ft_written += 1

            # Track stats
            yr = record["publication_year"]
            if yr:
                year_dist[yr] += 1
            if record["venue"]:
                venue_dist[record["venue"]] += 1
            text_lengths.append(record["full_text_length"])

            if ft_written % 10000 == 0:
                print(f"\r      Written: {ft_written:,} / {fulltext_count:,}    ",
                      end="", flush=True)

    print(f"\r      Written: {ft_written:,} papers with full text    ")

    # Step 4: Write abstract-only JSONL
    print(f"   Step 4: Writing abstract-only JSONL...")
    abs_written = 0
    has_abstract_no_ft = (
        ~merged["has_fulltext"] &
        merged["abstract"].notna() &
        (merged["abstract"].str.len() > 100)
    )

    with open(MERGED_ABSTRACT, "w", encoding="utf-8") as f:
        for _, row in merged[has_abstract_no_ft].iterrows():
            record = {
                "openalex_id": row.get("openalex_id", ""),
                "doi": row.get("doi", ""),
                "s2_corpus_id": row.get("s2_corpus_id", "") if pd.notna(row.get("s2_corpus_id")) else "",
                "title": row.get("title", ""),
                "abstract": row.get("abstract", ""),
                "publication_year": int(row["publication_year"]) if pd.notna(row.get("publication_year")) else None,
                "venue": row.get("venue", "") if pd.notna(row.get("venue")) else "",
                "cited_by_count": int(row["cited_by_count"]) if pd.notna(row.get("cited_by_count")) else 0,
                "authors": row.get("authors", "") if pd.notna(row.get("authors")) else "",
                "keywords": row.get("keywords", "") if pd.notna(row.get("keywords")) else "",
                "primary_concept": row.get("primary_concept", "") if pd.notna(row.get("primary_concept")) else "",
                "is_open_access": bool(row.get("is_open_access")) if pd.notna(row.get("is_open_access")) else False,
                "type": row.get("type", "") if pd.notna(row.get("type")) else "",
                "full_text": "",
                "full_text_length": 0,
                "full_text_word_count": 0,
                "full_text_source": "",
            }
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
            abs_written += 1

            if abs_written % 50000 == 0:
                print(f"\r      Written: {abs_written:,}    ", end="", flush=True)

    print(f"\r      Written: {abs_written:,} abstract-only papers    ")

    return ft_written, abs_written, year_dist, venue_dist, text_lengths, merged


def generate_report(ft_count, abs_count, year_dist, venue_dist, text_lengths,
                    merged_df, start_time):
    """Generate a statistics report."""
    elapsed = datetime.now() - start_time

    # Compute text stats
    if text_lengths:
        avg_len = sum(text_lengths) / len(text_lengths)
        median_len = sorted(text_lengths)[len(text_lengths) // 2]
        max_len = max(text_lengths)
        min_len = min(text_lengths)
    else:
        avg_len = median_len = max_len = min_len = 0

    total = ft_count + abs_count

    report_lines = [
        "=" * 70,
        "FoodmoleGPT - Data Merge Report",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "=" * 70,
        "",
        "DATASET OVERVIEW",
        "-" * 40,
        f"Total merged papers:          {total:>10,}",
        f"  With full text:             {ft_count:>10,}",
        f"  Abstract only:              {abs_count:>10,}",
        f"Original metadata papers:     {len(merged_df):>10,}",
        "",
        "FULL TEXT STATISTICS",
        "-" * 40,
        f"Average text length (chars):  {avg_len:>10,.0f}",
        f"Median text length (chars):   {median_len:>10,}",
        f"Min text length (chars):      {min_len:>10,}",
        f"Max text length (chars):      {max_len:>10,}",
        "",
        "YEAR DISTRIBUTION (Top 20)",
        "-" * 40,
    ]

    for year, count in sorted(year_dist.items(), reverse=True)[:20]:
        bar = "█" * (count // 2000)
        report_lines.append(f"  {year}: {count:>8,}  {bar}")

    report_lines.extend([
        "",
        "TOP 20 VENUES (Full Text Papers)",
        "-" * 40,
    ])

    for venue, count in venue_dist.most_common(20):
        v = venue[:50] if venue else "(unknown)"
        report_lines.append(f"  {count:>6,}  {v}")

    report_lines.extend([
        "",
        "OUTPUT FILES",
        "-" * 40,
        f"  Full text JSONL:   {MERGED_FULLTEXT}",
        f"  Abstract JSONL:    {MERGED_ABSTRACT}",
    ])

    # File sizes
    for path in [MERGED_FULLTEXT, MERGED_ABSTRACT]:
        if path.exists():
            size = path.stat().st_size
            if size > 1024**3:
                report_lines.append(f"    Size: {size/1024**3:.2f} GB")
            else:
                report_lines.append(f"    Size: {size/1024**2:.1f} MB")

    report_lines.extend([
        "",
        f"Elapsed: {elapsed}",
        "=" * 70,
    ])

    report = "\n".join(report_lines)
    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        f.write(report)

    print(f"\n{report}")

    # Also save machine-readable stats
    stats = {
        "total_papers": total,
        "fulltext_papers": ft_count,
        "abstract_only_papers": abs_count,
        "avg_text_length": round(avg_len),
        "median_text_length": median_len,
        "year_distribution": dict(sorted(year_dist.items())),
        "top_venues": dict(venue_dist.most_common(50)),
        "elapsed_seconds": elapsed.total_seconds(),
    }
    with open(STATS_FILE, "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2, ensure_ascii=False)


def main():
    print("=" * 70)
    print("🔗 FoodmoleGPT - Data Merge Pipeline")
    print("=" * 70)
    start_time = datetime.now()

    # Load data sources
    print("\n📥 LOADING DATA SOURCES")
    print("=" * 70)
    metadata_df = load_metadata()
    mapping_df = load_mapping()
    fulltext_index = load_fulltext_index()

    # Merge and save
    ft_count, abs_count, year_dist, venue_dist, text_lengths, merged_df = \
        merge_and_save(metadata_df, mapping_df, fulltext_index)

    # Report
    generate_report(ft_count, abs_count, year_dist, venue_dist, text_lengths,
                    merged_df, start_time)

    print("\n✅ Merge complete!")


if __name__ == "__main__":
    main()
