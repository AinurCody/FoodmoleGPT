"""
FoodmoleGPT Round 2 - Food Science Quality Filter
===================================================
Thin wrapper around filter_food.py to apply the same 3-layer filter
(venue whitelist + title keywords + keyword field) to Round 2 merged data.

Usage:
    conda activate foodmole
    python src/filter_food_r2.py
"""

import sys
from pathlib import Path

# Add project root to path so we can import filter_food
sys.path.insert(0, str(Path(__file__).parent))

from filter_food import filter_file

if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# =============================================================================
# R2 PATHS
# =============================================================================

MERGED_FULLTEXT = Path("D:/FoodmoleGPT/data/merged_r2/food_science_merged_r2.jsonl")
MERGED_ABSTRACT = Path("D:/FoodmoleGPT/data/merged_r2/food_science_abstract_r2.jsonl")

OUTPUT_DIR = Path("D:/FoodmoleGPT/data/filtered_r2")
FILTERED_FULLTEXT = OUTPUT_DIR / "food_fulltext_filtered.jsonl"
FILTERED_ABSTRACT = OUTPUT_DIR / "food_abstract_filtered.jsonl"
REPORT_FILE = OUTPUT_DIR / "filter_report_r2.txt"


def main():
    from datetime import datetime

    print("=" * 60)
    print("FoodmoleGPT Round 2 - Dataset Quality Filter")
    print("=" * 60)
    sys.stdout.flush()
    start = datetime.now()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    stats = []

    if MERGED_FULLTEXT.exists():
        s = filter_file(MERGED_FULLTEXT, FILTERED_FULLTEXT, "R2 Full Text")
        stats.append(("fulltext", s))
    else:
        print(f"\n⚠️  R2 fulltext not found: {MERGED_FULLTEXT}")

    if MERGED_ABSTRACT.exists():
        s = filter_file(MERGED_ABSTRACT, FILTERED_ABSTRACT, "R2 Abstract Only")
        stats.append(("abstract", s))
    else:
        print(f"\n⚠️  R2 abstract not found: {MERGED_ABSTRACT}")

    # Summary
    elapsed = datetime.now() - start
    if stats:
        total_kept = sum(s["kept"] for _, s in stats)
        total_removed = sum(s["removed"] for _, s in stats)
        total_all = sum(s["total"] for _, s in stats)

        report_lines = [
            "=" * 60,
            "FoodmoleGPT Round 2 - Filter Report",
            f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "=" * 60,
            "",
            "OVERALL SUMMARY",
            "-" * 40,
            f"Total papers:    {total_all:>10,}",
            f"Kept (food):     {total_kept:>10,} ({total_kept/total_all*100:.1f}%)",
            f"Removed:         {total_removed:>10,} ({total_removed/total_all*100:.1f}%)",
            "",
        ]
        for label, s in stats:
            report_lines.extend([
                f"DATASET: {label.upper()}",
                f"  Total:    {s['total']:>10,}",
                f"  Kept:     {s['kept']:>10,} ({s['kept']/s['total']*100:.1f}%)",
                f"  Removed:  {s['removed']:>10,} ({s['removed']/s['total']*100:.1f}%)",
                "",
            ])

        report_lines.append(f"Elapsed: {elapsed}")
        report = "\n".join(report_lines)
        with open(REPORT_FILE, "w", encoding="utf-8") as f:
            f.write(report)
        print(f"\n{report}")

    print("\n[DONE] Round 2 filter complete!")
    sys.stdout.flush()


if __name__ == "__main__":
    main()
