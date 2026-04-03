#!/usr/bin/env python3
"""
Merge expansion corpus into the main food science corpus.
Deduplicates by PMCID and outputs merge statistics.

Usage:
    python merge_expansion.py [--main-corpus PATH] [--expansion-corpus PATH]

Author: FoodmoleGPT Team
"""

import argparse
import json
import time
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Merge expansion into main corpus")
    parser.add_argument(
        "--main-corpus",
        default="data/processed/filtered/food_science_corpus.keep.jsonl",
        help="Main corpus JSONL",
    )
    parser.add_argument(
        "--expansion-corpus",
        default="data/processed/expansion/filtered/food_science_corpus.keep.jsonl",
        help="Expansion corpus JSONL (post-filtered)",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output merged JSONL (default: overwrite main corpus)",
    )
    args = parser.parse_args()

    script_dir = Path(__file__).parent

    main_path = Path(args.main_corpus)
    if not main_path.is_absolute():
        main_path = script_dir / main_path

    exp_path = Path(args.expansion_corpus)
    if not exp_path.is_absolute():
        exp_path = script_dir / exp_path

    output_path = Path(args.output) if args.output else main_path
    if not output_path.is_absolute():
        output_path = script_dir / output_path

    print(f"Main corpus: {main_path}")
    print(f"Expansion:   {exp_path}")
    print(f"Output:      {output_path}")

    # ── Step 1: Read main corpus PMCIDs ──
    print("\nReading main corpus...")
    t0 = time.time()
    main_pmcids = set()
    main_lines = []

    with open(main_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            main_lines.append(line)
            try:
                doc = json.loads(line)
                pmcid = doc.get("pmcid", "")
                if pmcid:
                    main_pmcids.add(pmcid)
            except json.JSONDecodeError:
                pass

    print(f"  Main articles: {len(main_lines):,} (unique PMCIDs: {len(main_pmcids):,})")

    # ── Step 2: Read expansion, skip duplicates ──
    print("Reading expansion corpus...")
    new_lines = []
    dup_count = 0
    exp_total = 0

    with open(exp_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            exp_total += 1
            try:
                doc = json.loads(line)
                pmcid = doc.get("pmcid", "")
                if pmcid and pmcid in main_pmcids:
                    dup_count += 1
                    continue
                if pmcid:
                    main_pmcids.add(pmcid)
            except json.JSONDecodeError:
                pass
            new_lines.append(line)

    print(f"  Expansion total: {exp_total:,}")
    print(f"  Duplicates skipped: {dup_count:,}")
    print(f"  New articles added: {len(new_lines):,}")

    # ── Step 3: Write merged output ──
    # If output == main path, write to temp first
    if output_path == main_path:
        tmp_path = main_path.with_suffix(".merged.tmp")
    else:
        tmp_path = output_path

    print(f"\nWriting merged corpus to {tmp_path}...")
    with open(tmp_path, "w", encoding="utf-8") as f:
        for line in main_lines:
            f.write(line)
        for line in new_lines:
            f.write(line)

    if output_path == main_path:
        # Backup original
        backup = main_path.with_suffix(".keep.jsonl.bak")
        main_path.rename(backup)
        tmp_path.rename(main_path)
        print(f"  Backup saved: {backup}")

    merged_total = len(main_lines) + len(new_lines)
    elapsed = time.time() - t0

    # ── Stats ──
    stats = {
        "main_articles": len(main_lines),
        "expansion_total": exp_total,
        "duplicates_skipped": dup_count,
        "new_articles_added": len(new_lines),
        "merged_total": merged_total,
        "elapsed_seconds": round(elapsed, 2),
    }

    stats_path = output_path.parent / "merge_expansion_stats.json"
    with open(stats_path, "w") as f:
        json.dump(stats, f, indent=2)

    print(f"\nMerge complete!")
    print(f"  Before: {len(main_lines):,}")
    print(f"  Added:  {len(new_lines):,}")
    print(f"  Total:  {merged_total:,}")
    print(f"  Stats:  {stats_path}")
    print(f"  Time:   {elapsed:.1f}s")


if __name__ == "__main__":
    main()
