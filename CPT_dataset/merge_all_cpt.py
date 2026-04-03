#!/usr/bin/env python3
"""
merge_all_cpt.py
================
Merge all CPT data sources into a single shuffled JSONL file for training.

Sources:
  1. essay/Merged/combined_fulltext_deduped.jsonl   (food science papers, ~2.1B tokens)
  2. essay/OpenAlex/abstract.jsonl                   (paper abstracts, ~130M tokens)
  3. book/data/wiki_food_cpt.jsonl                   (Wikipedia food articles, ~79M tokens)
  4. general/data/fineweb2_general_cpt.jsonl          (FineWeb general corpus, ~800M tokens)

Strategy:
  - Domain sources (1+2+3) are kept in full
  - General source (4) is truncated so it accounts for exactly 25% of total
  - All sources are tagged with a "source" field for provenance tracking
  - Final output is shuffled to avoid sequential bias during training

Outputs (in total/):
  - cpt_corpus_merged.jsonl       Final merged corpus (shuffled)
  - merge_all_stats.json          Statistics

Usage:
  python merge_all_cpt.py [--general-ratio 0.25] [--seed 42]
"""

import argparse
import json
import random
import sys
import time
from pathlib import Path

# ─────────────────────────────────────────────────────────────────────
# Paths
# ─────────────────────────────────────────────────────────────────────
BASE = Path(__file__).resolve().parent

FULLTEXT    = BASE / "essay" / "Merged" / "combined_fulltext_deduped.jsonl"
ABSTRACTS   = BASE / "essay" / "OpenAlex" / "abstract.jsonl"
WIKI        = BASE / "book" / "data" / "wiki_food_cpt.jsonl"
GENERAL     = BASE / "general" / "data" / "fineweb2_general_cpt.jsonl"

OUT_DIR     = BASE / "total"
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_FILE    = OUT_DIR / "cpt_corpus_merged.jsonl"
STATS_FILE  = OUT_DIR / "merge_all_stats.json"


def estimate_tokens(text: str) -> int:
    return int(len(text.split()) * 1.3)


def load_jsonl_texts(path: Path, source_tag: str, limit: int = 0):
    """Load JSONL file, return list of (text, tokens, source_tag)."""
    records = []
    total_tokens = 0
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            doc = json.loads(line)
            text = doc.get("text", "")
            if not text:
                continue
            tokens = estimate_tokens(text)
            records.append((text, tokens, source_tag))
            total_tokens += tokens
            if 0 < limit <= total_tokens:
                break
    return records, total_tokens


def main():
    parser = argparse.ArgumentParser(description="Merge all CPT sources")
    parser.add_argument("--general-ratio", type=float, default=0.25,
                        help="Target ratio of general corpus (default: 0.25)")
    parser.add_argument("--seed", type=int, default=42,
                        help="Random seed for shuffling (default: 42)")
    args = parser.parse_args()

    t0 = time.time()
    ratio = args.general_ratio
    random.seed(args.seed)

    print(f"General ratio target: {ratio:.0%}")
    print(f"Random seed: {args.seed}")
    print(f"Output: {OUT_FILE}")
    print()

    # ── Step 1: Load domain sources ──
    print("Loading domain sources...")

    print(f"  [1/4] Fulltext papers: {FULLTEXT}")
    fulltext_records, fulltext_tokens = load_jsonl_texts(FULLTEXT, "essay_fulltext")
    print(f"         {len(fulltext_records):,} docs, ~{fulltext_tokens/1e6:.0f}M tokens")

    print(f"  [2/4] Abstracts: {ABSTRACTS}")
    abstract_records, abstract_tokens = load_jsonl_texts(ABSTRACTS, "essay_abstract")
    print(f"         {len(abstract_records):,} docs, ~{abstract_tokens/1e6:.0f}M tokens")

    print(f"  [3/4] Wikipedia: {WIKI}")
    wiki_records, wiki_tokens = load_jsonl_texts(WIKI, "wiki_food")
    print(f"         {len(wiki_records):,} docs, ~{wiki_tokens/1e6:.0f}M tokens")

    domain_total_tokens = fulltext_tokens + abstract_tokens + wiki_tokens
    domain_total_docs = len(fulltext_records) + len(abstract_records) + len(wiki_records)
    print(f"\n  Domain total: {domain_total_docs:,} docs, ~{domain_total_tokens/1e6:.0f}M tokens")

    # ── Step 2: Calculate general corpus budget ──
    # domain = (1 - ratio) of total  →  total = domain / (1-ratio)
    # general = ratio * total
    target_general_tokens = int(domain_total_tokens * ratio / (1 - ratio))
    print(f"\n  General budget (for {ratio:.0%}): ~{target_general_tokens/1e6:.0f}M tokens")

    # ── Step 3: Load general source (with limit) ──
    print(f"  [4/4] FineWeb general: {GENERAL}")
    general_records, general_tokens = load_jsonl_texts(
        GENERAL, "fineweb_general", limit=target_general_tokens
    )
    print(f"         {len(general_records):,} docs, ~{general_tokens/1e6:.0f}M tokens")

    # ── Step 4: Merge and shuffle ──
    all_records = fulltext_records + abstract_records + wiki_records + general_records
    total_tokens = domain_total_tokens + general_tokens
    actual_ratio = general_tokens / total_tokens if total_tokens > 0 else 0

    print(f"\n{'='*60}")
    print(f"Total before shuffle: {len(all_records):,} docs, ~{total_tokens/1e6:.0f}M tokens")
    print(f"Actual general ratio: {actual_ratio:.1%}")
    print(f"\nShuffling...")

    random.shuffle(all_records)

    # ── Step 5: Write output ──
    print(f"Writing {OUT_FILE}...")
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        for text, tokens, source in all_records:
            f.write(json.dumps({"text": text, "source": source}, ensure_ascii=False) + "\n")

    elapsed = time.time() - t0

    # ── Stats ──
    stats = {
        "sources": {
            "essay_fulltext": {
                "docs": len(fulltext_records),
                "estimated_tokens": fulltext_tokens,
                "file": str(FULLTEXT),
            },
            "essay_abstract": {
                "docs": len(abstract_records),
                "estimated_tokens": abstract_tokens,
                "file": str(ABSTRACTS),
            },
            "wiki_food": {
                "docs": len(wiki_records),
                "estimated_tokens": wiki_tokens,
                "file": str(WIKI),
            },
            "fineweb_general": {
                "docs": len(general_records),
                "estimated_tokens": general_tokens,
                "file": str(GENERAL),
            },
        },
        "total_docs": len(all_records),
        "total_estimated_tokens": total_tokens,
        "domain_tokens": domain_total_tokens,
        "general_tokens": general_tokens,
        "general_ratio_target": ratio,
        "general_ratio_actual": round(actual_ratio, 4),
        "random_seed": args.seed,
        "elapsed_seconds": round(elapsed, 1),
        "output_file": str(OUT_FILE),
    }

    with open(STATS_FILE, "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2, ensure_ascii=False)

    print(f"\n{'='*60}")
    print(f"Done in {elapsed:.0f}s")
    print(f"Output: {OUT_FILE.name} ({len(all_records):,} docs)")
    print(f"Stats: {STATS_FILE.name}")
    print()
    print("Composition:")
    for src, info in stats["sources"].items():
        pct = info["estimated_tokens"] / total_tokens * 100
        print(f"  {src:20s}  {info['docs']:>10,} docs  "
              f"~{info['estimated_tokens']/1e6:>7.0f}M tokens  ({pct:.1f}%)")
    print(f"  {'TOTAL':20s}  {len(all_records):>10,} docs  "
          f"~{total_tokens/1e6:>7.0f}M tokens  (100%)")


if __name__ == "__main__":
    main()
