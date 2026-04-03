"""
FoodmoleGPT Round 2 - Merge Full Text with Metadata
=====================================================
Adapted from merge_fulltext.py for Round 2 data.

Usage:
    conda activate foodmole
    python src/merge_fulltext_r2.py
"""

import json
import sys
from pathlib import Path
from datetime import datetime
from collections import Counter

import pandas as pd

if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# =============================================================================
# CONFIGURATION (Round 2 paths)
# =============================================================================

CLEANED_CSV = Path("D:/FoodmoleGPT/data/cleaned_r2/master_cleaned_r2.csv")
MAPPING_CSV = Path("D:/FoodmoleGPT/data/fulltext_r2/doi_to_corpusid_r2.csv")
FULLTEXT_JSONL = Path("D:/FoodmoleGPT/data/fulltext_r2/extracted/food_science_fulltext_r2.jsonl")

OUTPUT_DIR = Path("D:/FoodmoleGPT/data/merged_r2")
MERGED_FULLTEXT = OUTPUT_DIR / "food_science_merged_r2.jsonl"
MERGED_ABSTRACT = OUTPUT_DIR / "food_science_abstract_r2.jsonl"
REPORT_FILE = OUTPUT_DIR / "merge_report_r2.txt"

METADATA_COLS = [
    "openalex_id", "doi", "title", "abstract",
    "publication_year", "publication_date", "venue",
    "cited_by_count", "authors", "institutions",
    "keywords", "is_open_access", "type",
    "primary_concept", "abstract_quality",
]


def load_metadata():
    print("   Loading R2 metadata...")
    # Only load columns that exist (R2 may not have all R1 cols)
    df = pd.read_csv(CLEANED_CSV)
    available = [c for c in METADATA_COLS if c in df.columns]
    df = df[available]
    print(f"   Total papers: {len(df):,}")
    print(f"   With DOI: {df['doi'].notna().sum():,}")
    return df


def load_mapping():
    print("   Loading DOI → Corpus ID mapping...")
    mapping = pd.read_csv(MAPPING_CSV, usecols=["doi", "s2_corpus_id"], on_bad_lines="skip")
    mapping = mapping.dropna(subset=["s2_corpus_id"])
    mapping["s2_corpus_id"] = mapping["s2_corpus_id"].apply(
        lambda x: str(int(float(x)))
    )
    print(f"   Mapped DOIs: {len(mapping):,}")
    return mapping


def load_fulltext_index():
    print("   Building full text index...")
    index = {}
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
                idx = line.find('"s2_corpus_id"')
                if idx >= 0:
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
    with open(FULLTEXT_JSONL, "r", encoding="utf-8") as f:
        f.seek(offset)
        line = f.readline()
        return json.loads(line.strip())


def merge_and_save(metadata_df, mapping_df, fulltext_index):
    print("\n" + "=" * 70)
    print("🔗 MERGING R2 DATA")
    print("=" * 70)

    print("   Joining metadata with Corpus ID mapping...")
    merged = metadata_df.merge(mapping_df, on="doi", how="left")
    has_corpus_id = merged["s2_corpus_id"].notna()
    print(f"   Papers with Corpus ID: {has_corpus_id.sum():,}")

    print("   Checking full text availability...")
    merged["has_fulltext"] = merged["s2_corpus_id"].apply(
        lambda x: x in fulltext_index if pd.notna(x) else False
    )
    fulltext_count = merged["has_fulltext"].sum()
    print(f"   Papers with full text: {fulltext_count:,}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Write full text JSONL
    print(f"\n   Writing merged full text JSONL...")
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
                "openalex_id": row.get("openalex_id", ""),
                "doi": row.get("doi", ""),
                "s2_corpus_id": corpus_id,
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
                "full_text": ft_data.get("text", ""),
                "full_text_length": ft_data.get("text_length", 0),
                "full_text_word_count": ft_data.get("word_count", 0),
                "full_text_source": ft_data.get("source", ""),
            }

            f.write(json.dumps(record, ensure_ascii=False) + "\n")
            ft_written += 1

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

    # Write abstract-only JSONL
    print(f"   Writing abstract-only JSONL...")
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

    return ft_written, abs_written, year_dist, venue_dist, text_lengths


def main():
    print("=" * 70)
    print("🔗 FoodmoleGPT Round 2 - Data Merge Pipeline")
    print("=" * 70)
    start_time = datetime.now()

    metadata_df = load_metadata()
    mapping_df = load_mapping()
    fulltext_index = load_fulltext_index()

    ft_count, abs_count, year_dist, venue_dist, text_lengths = \
        merge_and_save(metadata_df, mapping_df, fulltext_index)

    # Report
    total = ft_count + abs_count
    report_lines = [
        "=" * 70,
        "FoodmoleGPT Round 2 - Merge Report",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "=" * 70,
        "",
        f"Total merged papers:          {total:>10,}",
        f"  With full text:             {ft_count:>10,}",
        f"  Abstract only:              {abs_count:>10,}",
        "",
        "Top venues:",
    ]
    for venue, count in venue_dist.most_common(15):
        report_lines.append(f"  {count:>6,}  {venue[:50]}")

    report = "\n".join(report_lines)
    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"\n{report}")

    elapsed = datetime.now() - start_time
    print(f"\nElapsed: {elapsed}")
    print("✅ Round 2 merge complete!")


if __name__ == "__main__":
    main()
