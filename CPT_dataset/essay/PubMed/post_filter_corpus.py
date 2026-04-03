#!/usr/bin/env python3
"""
Post-filter food science corpus with stricter rules.

Rule:
  Drop document if:
    - cancer-like terms appear in title/abstract/text, and
    - no food anchor appears in title/abstract/keywords.
"""

import argparse
import json
import random
import re
import time
from pathlib import Path
from typing import Dict, List


CANCER_RE = re.compile(
    r"\b(cancer|tumou?r|oncolog|neoplas|carcinoma|malignan)\w*\b", re.IGNORECASE
)

FOOD_ANCHOR_RE = re.compile(
    r"\b(food|diet|dietary|nutrition|nutrient|intake|feeding|beverage|meat|dairy|"
    r"milk|fruit|vegetable|grain|cereal|fish|seafood|ferment|probiotic|prebiotic|"
    r"polyphenol|vitamin|fatty acid|carbohydrate|fiber|fibre)\w*\b",
    re.IGNORECASE,
)

FOOD_JOURNAL_RE = re.compile(
    r"food|nutri|diet|agric|meat|dairy|bever|cereal|grain|fish|crop|appetite",
    re.IGNORECASE,
)


def update_reservoir(
    reservoir: List[Dict], item: Dict, seen_count: int, sample_size: int, rng: random.Random
) -> None:
    """Reservoir sampling for stable-size random examples."""
    if sample_size <= 0:
        return
    if len(reservoir) < sample_size:
        reservoir.append(item)
        return
    idx = rng.randint(0, seen_count - 1)
    if idx < sample_size:
        reservoir[idx] = item


def main() -> None:
    parser = argparse.ArgumentParser(description="Post-filter food science corpus JSONL")
    parser.add_argument(
        "--input",
        default="data/processed/intermediate/food_science_corpus.raw.jsonl",
        help="Input JSONL path",
    )
    parser.add_argument(
        "--out-dir",
        default="data/processed/filtered",
        help="Output directory",
    )
    parser.add_argument(
        "--sample-size",
        type=int,
        default=200,
        help="Sample size per bucket for manual inspection",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for sample reproducibility",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    keep_path = out_dir / "food_science_corpus.keep.jsonl"
    drop_path = out_dir / "food_science_corpus.drop.jsonl"
    stats_path = out_dir / "post_filter_stats.json"
    samples_path = out_dir / "post_filter_samples.json"

    rng = random.Random(args.seed)
    t0 = time.time()

    counters = {
        "total_docs": 0,
        "parse_errors": 0,
        "kept_docs": 0,
        "dropped_docs": 0,
        "has_cancer_terms": 0,
        "has_food_anchor_title_abstract_keywords": 0,
        "no_food_anchor_title_abstract_keywords": 0,
        "cancer_and_food_anchor": 0,
        "cancer_and_no_food_anchor": 0,
        "cancer_no_anchor_food_like_journal": 0,
        "cancer_no_anchor_non_food_like_journal": 0,
    }

    bucket_seen = {
        "cancer_with_food_anchor": 0,
        "cancer_without_food_anchor": 0,
        "non_cancer_without_food_anchor": 0,
    }
    samples = {
        "cancer_with_food_anchor": [],
        "cancer_without_food_anchor": [],
        "non_cancer_without_food_anchor": [],
    }

    with (
        input_path.open("r", encoding="utf-8", errors="ignore") as fin,
        keep_path.open("w", encoding="utf-8") as fkeep,
        drop_path.open("w", encoding="utf-8") as fdrop,
    ):
        for idx, line in enumerate(fin, start=1):
            counters["total_docs"] += 1
            try:
                doc = json.loads(line)
            except json.JSONDecodeError:
                counters["parse_errors"] += 1
                continue

            title = doc.get("title", "") or ""
            abstract = doc.get("abstract", "") or ""
            text = doc.get("text", "") or ""
            keywords = " ".join(doc.get("keywords", []) or [])
            journal = doc.get("journal", "") or ""

            cancer_blob = " ".join([title, abstract, text])
            anchor_blob = " ".join([title, abstract, keywords])

            has_cancer = bool(CANCER_RE.search(cancer_blob))
            has_anchor = bool(FOOD_ANCHOR_RE.search(anchor_blob))
            is_food_journal = bool(FOOD_JOURNAL_RE.search(journal))

            if has_cancer:
                counters["has_cancer_terms"] += 1
            if has_anchor:
                counters["has_food_anchor_title_abstract_keywords"] += 1
            else:
                counters["no_food_anchor_title_abstract_keywords"] += 1

            if has_cancer and has_anchor:
                counters["cancer_and_food_anchor"] += 1
                bucket = "cancer_with_food_anchor"
            elif has_cancer and not has_anchor:
                counters["cancer_and_no_food_anchor"] += 1
                bucket = "cancer_without_food_anchor"
                if is_food_journal:
                    counters["cancer_no_anchor_food_like_journal"] += 1
                else:
                    counters["cancer_no_anchor_non_food_like_journal"] += 1
            elif (not has_cancer) and (not has_anchor):
                bucket = "non_cancer_without_food_anchor"
            else:
                bucket = None

            should_drop = has_cancer and (not has_anchor)
            if should_drop:
                counters["dropped_docs"] += 1
                fdrop.write(line)
            else:
                counters["kept_docs"] += 1
                fkeep.write(line)

            if bucket:
                bucket_seen[bucket] += 1
                sample_item = {
                    "pmcid": doc.get("pmcid", ""),
                    "journal": journal,
                    "title": title,
                    "keywords": doc.get("keywords", []) or [],
                    "drop": should_drop,
                }
                update_reservoir(
                    samples[bucket], sample_item, bucket_seen[bucket], args.sample_size, rng
                )

            if idx % 10000 == 0:
                elapsed = time.time() - t0
                print(
                    f"[progress] {idx:,} docs | kept={counters['kept_docs']:,} "
                    f"drop={counters['dropped_docs']:,} | {elapsed:.1f}s"
                )

    elapsed = time.time() - t0
    counters["elapsed_seconds"] = round(elapsed, 2)

    total = counters["total_docs"] or 1
    counters["drop_ratio"] = round(counters["dropped_docs"] / total, 6)
    cancer_total = counters["has_cancer_terms"] or 1
    counters["cancer_drop_ratio"] = round(
        counters["cancer_and_no_food_anchor"] / cancer_total, 6
    )

    payload = {
        "input_path": str(input_path),
        "keep_path": str(keep_path),
        "drop_path": str(drop_path),
        "stats": counters,
        "bucket_seen": bucket_seen,
    }
    stats_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    samples_path.write_text(json.dumps(samples, ensure_ascii=False, indent=2), encoding="utf-8")

    print("[done]")
    print(f"keep: {keep_path}")
    print(f"drop: {drop_path}")
    print(f"stats: {stats_path}")
    print(f"samples: {samples_path}")
    print(f"elapsed: {elapsed:.1f}s")


if __name__ == "__main__":
    main()
