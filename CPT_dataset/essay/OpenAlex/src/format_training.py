"""
FoodmoleGPT - Training Format Conversion & Train/Val Split (v2)
================================================================
Memory-efficient version: uses two-pass approach to avoid loading
all 12GB of text into memory at once.

Pass 1: Read input, assign train/val, write directly to output files
Pass 2: (none needed — single pass is sufficient with pre-computed splits)

Output format (one JSON per line):
  {"text": "Title: ...\nAuthors: ...\nAbstract: ...\n\n<full_text>"}

Usage:
    conda activate foodmole
    python src/format_training.py

    # Or run in background (won't be killed if IDE closes):
    # Start-Process -NoNewWindow python -ArgumentList "src/format_training.py" -RedirectStandardOutput "format_log.txt" -RedirectStandardError "format_err.txt"
"""

import json
import os
import random
import sys
from pathlib import Path
from datetime import datetime
from collections import Counter

# Force UTF-8 stdout for background process compatibility on Windows
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if sys.stderr.encoding != 'utf-8':
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# =============================================================================
# CONFIG
# =============================================================================

MERGED_FULLTEXT = Path("D:/FoodmoleGPT/data/filtered/food_fulltext_filtered.jsonl")
MERGED_ABSTRACT = Path("D:/FoodmoleGPT/data/filtered/food_abstract_filtered.jsonl")

OUTPUT_DIR = Path("D:/FoodmoleGPT/data/training")
REPORT_FILE = OUTPUT_DIR / "format_report.txt"

VAL_RATIO = 0.02  # 2% for validation
RANDOM_SEED = 42

MIN_FULLTEXT_CHARS = 2000
MIN_ABSTRACT_CHARS = 100


# =============================================================================
# TEXT FORMATTING
# =============================================================================

def format_fulltext_record(doc: dict) -> str:
    """Format a full-text paper into a structured pretraining document."""
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
    """Format an abstract-only paper into a structured pretraining document."""
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
# STREAMING PROCESSOR (memory-efficient)
# =============================================================================

def count_lines(path):
    """Count lines in a file without loading it all into memory."""
    count = 0
    with open(path, "r", encoding="utf-8") as f:
        for _ in f:
            count += 1
    return count


def process_file_streaming(input_path, format_fn, prefix, min_chars):
    """Process a JSONL file into training format using streaming.

    Two-pass approach:
      Pass 1: Count lines to pre-generate train/val assignment
      Pass 2: Read, format, and write directly (one record at a time)

    Memory usage: O(1) — only one record in memory at a time.
    """
    print(f"\n   [FILE] Processing: {input_path.name}")
    sys.stdout.flush()

    # Pass 1: Count total lines for pre-computed split assignment
    print("      Pass 1: Counting records...")
    sys.stdout.flush()
    total_lines = count_lines(input_path)
    print(f"      Total lines: {total_lines:,}")
    sys.stdout.flush()

    # Pre-generate train/val assignment (bool array: True = val)
    random.seed(RANDOM_SEED)
    is_val = [random.random() < VAL_RATIO for _ in range(total_lines)]

    # Pass 2: Stream through, format, and write directly
    print("      Pass 2: Formatting and writing...")
    sys.stdout.flush()
    train_path = OUTPUT_DIR / f"{prefix}_train.jsonl"
    val_path = OUTPUT_DIR / f"{prefix}_val.jsonl"

    train_count = 0
    val_count = 0
    skipped_short = 0
    skipped_empty = 0
    text_lengths = []
    word_counts = []
    year_dist = Counter()

    with open(train_path, "w", encoding="utf-8") as f_train, \
         open(val_path, "w", encoding="utf-8") as f_val, \
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

            # Write to train or val based on pre-computed assignment
            if is_val[i]:
                f_val.write(record_json)
                val_count += 1
            else:
                f_train.write(record_json)
                train_count += 1

            # Track stats (lightweight — just lengths, not full text)
            text_lengths.append(len(text))
            word_counts.append(len(text.split()))
            yr = doc.get("publication_year")
            if yr:
                year_dist[yr] += 1

            if (i + 1) % 10000 == 0:
                print(f"\r      Processed: {i+1:,} / {total_lines:,}    ", end="")
                sys.stdout.flush()

    print(f"\r      Done: {train_count + val_count:,} valid records "
          f"(skipped: {skipped_short} short, {skipped_empty} empty)")
    print(f"      Train: {train_count:,} -> {train_path.name}")
    print(f"      Val:   {val_count:,} -> {val_path.name}")
    sys.stdout.flush()

    # Show file sizes
    for p in [train_path, val_path]:
        size = p.stat().st_size
        if size > 1024**3:
            print(f"        {p.name}: {size/1024**3:.2f} GB")
        else:
            print(f"        {p.name}: {size/1024**2:.1f} MB")
    sys.stdout.flush()

    return {
        "prefix": prefix,
        "total": train_count + val_count,
        "train": train_count,
        "val": val_count,
        "skipped_short": skipped_short,
        "skipped_empty": skipped_empty,
        "avg_chars": sum(text_lengths) // len(text_lengths) if text_lengths else 0,
        "median_chars": sorted(text_lengths)[len(text_lengths) // 2] if text_lengths else 0,
        "avg_words": sum(word_counts) // len(word_counts) if word_counts else 0,
        "median_words": sorted(word_counts)[len(word_counts) // 2] if word_counts else 0,
        "year_dist": year_dist,
        "train_path": str(train_path),
        "val_path": str(val_path),
    }


def generate_report(stats_list, start_time):
    """Generate a report."""
    elapsed = datetime.now() - start_time

    lines = [
        "=" * 70,
        "FoodmoleGPT - Training Data Format Report",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "=" * 70,
        "",
    ]

    total_train = sum(s["train"] for s in stats_list)
    total_val = sum(s["val"] for s in stats_list)

    lines.extend([
        "OVERALL SUMMARY",
        "-" * 40,
        f"Total training records:     {total_train:>10,}",
        f"Total validation records:   {total_val:>10,}",
        f"Total records:              {total_train + total_val:>10,}",
        f"Val ratio:                  {VAL_RATIO*100:.0f}%",
        "",
    ])

    for s in stats_list:
        lines.extend([
            f"DATASET: {s['prefix'].upper()}",
            "-" * 40,
            f"Valid records:     {s['total']:>10,}",
            f"  Train:           {s['train']:>10,}",
            f"  Val:             {s['val']:>10,}",
            f"  Skipped (short): {s['skipped_short']:>10,}",
            f"  Skipped (empty): {s['skipped_empty']:>10,}",
            f"Avg text length:   {s['avg_chars']:>10,} chars ({s['avg_words']:,} words)",
            f"Median length:     {s['median_chars']:>10,} chars ({s['median_words']:,} words)",
            "",
        ])

    lines.extend([
        "OUTPUT FILES",
        "-" * 40,
    ])
    for s in stats_list:
        for key in ["train_path", "val_path"]:
            p = Path(s[key])
            size = p.stat().st_size
            if size > 1024**3:
                lines.append(f"  {p.name}: {size/1024**3:.2f} GB")
            else:
                lines.append(f"  {p.name}: {size/1024**2:.1f} MB")

    lines.extend([
        "",
        "FORMAT",
        "-" * 40,
        'Each line: {"text": "<structured_text>"}',
        "",
        "Template (full text):",
        "  Title: ... | Authors: ... | Year: ... | Venue: ... | Keywords: ...",
        "  Abstract: <abstract>",
        "  Full Text: <full_text>",
        "",
        "Template (abstract only):",
        "  Title: ... | Authors: ... | Year: ... | Venue: ... | Keywords: ...",
        "  Abstract: <abstract>",
        "",
        f"Elapsed: {elapsed}",
        "=" * 70,
    ])

    report = "\n".join(lines)
    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"\n{report}")
    sys.stdout.flush()

    stats_json = {
        "total_train": total_train,
        "total_val": total_val,
        "val_ratio": VAL_RATIO,
        "datasets": [{k: v for k, v in s.items() if k != "year_dist"}
                     for s in stats_list],
        "elapsed_seconds": elapsed.total_seconds(),
    }
    with open(OUTPUT_DIR / "format_stats.json", "w", encoding="utf-8") as f:
        json.dump(stats_json, f, indent=2, ensure_ascii=False)


def main():
    print("=" * 70)
    print("FoodmoleGPT - Training Format Conversion (v2 Streaming)")
    print("=" * 70)
    sys.stdout.flush()
    start_time = datetime.now()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    stats_list = []

    if MERGED_FULLTEXT.exists():
        stats = process_file_streaming(
            MERGED_FULLTEXT, format_fulltext_record,
            "fulltext", MIN_FULLTEXT_CHARS,
        )
        stats_list.append(stats)

    if MERGED_ABSTRACT.exists():
        stats = process_file_streaming(
            MERGED_ABSTRACT, format_abstract_record,
            "abstract", MIN_ABSTRACT_CHARS,
        )
        stats_list.append(stats)

    generate_report(stats_list, start_time)
    print("\n[DONE] Training format conversion complete!")
    sys.stdout.flush()


if __name__ == "__main__":
    main()
