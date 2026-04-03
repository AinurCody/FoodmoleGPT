#!/usr/bin/env python3
"""
download_fineweb2.py
====================
Sample high-quality English text from FineWeb (HuggingFaceFW) for use as
general-domain "replay" corpus during Continual Pre-Training (CPT).

Note: FineWeb (original) is English-only; FineWeb-2 is multilingual without
English. We use the original FineWeb for the English general corpus.

Strategy:
  Stream from HuggingFace, sample every N-th document to get a representative
  spread across the dataset, convert to CPT JSONL format, stop at target tokens.

Outputs (in general/data/):
  - fineweb2_general_cpt.jsonl    CPT-ready format {"text": "..."}
  - sample_stats.json             Statistics

Usage:
  python download_fineweb2.py [--max-tokens TARGET_TOKENS] [--sample-rate RATE]

Requires:  pip install datasets tqdm
"""

import argparse
import json
import sys
import time
from pathlib import Path

from datasets import load_dataset
from tqdm import tqdm

# ─────────────────────────────────────────────────────────────────────
# Paths
# ─────────────────────────────────────────────────────────────────────
BASE = Path(__file__).resolve().parent
OUT_DIR = BASE / "data"
OUT_DIR.mkdir(parents=True, exist_ok=True)

CPT_JSONL = OUT_DIR / "fineweb2_general_cpt.jsonl"
STATS_FILE = OUT_DIR / "sample_stats.json"

# ─────────────────────────────────────────────────────────────────────
# Quality filters
# ─────────────────────────────────────────────────────────────────────
MIN_TEXT_LEN = 500       # skip very short docs
MAX_TEXT_LEN = 50_000    # skip abnormally long docs (likely boilerplate)


def estimate_tokens(text: str) -> int:
    """Rough estimate: ~1.3 tokens per whitespace word for English."""
    return int(len(text.split()) * 1.3)


def main():
    parser = argparse.ArgumentParser(description="Sample FineWeb-2 for general CPT corpus")
    parser.add_argument("--max-tokens", type=int, default=800_000_000,
                        help="Target token count (default: 800M)")
    parser.add_argument("--sample-rate", type=int, default=50,
                        help="Keep 1 in every N documents (default: 50)")
    parser.add_argument("--min-len", type=int, default=MIN_TEXT_LEN,
                        help="Minimum text length in chars (default: 500)")
    args = parser.parse_args()

    target_tokens = args.max_tokens
    sample_rate = args.sample_rate

    print(f"Target: ~{target_tokens/1e6:.0f}M tokens")
    print(f"Sample rate: 1/{sample_rate}")
    print(f"Output dir: {OUT_DIR}")

    # ── Load FineWeb (streaming) ──
    # Note: FineWeb (original) is English-only; FineWeb-2 is multilingual
    # without English. We use the original FineWeb for English general corpus.
    print("\nLoading FineWeb dataset (streaming)...")
    ds = load_dataset(
        "HuggingFaceFW/fineweb",
        name="default",
        split="train",
        streaming=True,
    )

    kept = 0
    scanned = 0
    total_tokens = 0
    skipped_short = 0
    skipped_long = 0
    skipped_sample = 0
    t0 = time.time()

    with open(CPT_JSONL, "w", encoding="utf-8") as f_out:
        for doc in tqdm(ds, desc="Scanning FineWeb-2", unit=" docs"):
            scanned += 1
            text = doc.get("text", "")

            # Length filters
            if len(text) < args.min_len:
                skipped_short += 1
                continue
            if len(text) > MAX_TEXT_LEN:
                skipped_long += 1
                continue

            # Subsample
            if scanned % sample_rate != 0:
                skipped_sample += 1
                continue

            # Write CPT format
            f_out.write(json.dumps({"text": text}, ensure_ascii=False) + "\n")

            tokens = estimate_tokens(text)
            total_tokens += tokens
            kept += 1

            if kept % 5000 == 0:
                elapsed = time.time() - t0
                print(f"  [{elapsed:.0f}s] Kept {kept:,} docs, scanned {scanned:,}, "
                      f"~{total_tokens/1e6:.0f}M tokens so far...")

            if total_tokens >= target_tokens:
                print(f"\nReached target of ~{target_tokens/1e6:.0f}M tokens. Stopping.")
                break

    elapsed = time.time() - t0

    stats = {
        "docs_scanned": scanned,
        "docs_kept": kept,
        "skipped_short": skipped_short,
        "skipped_long": skipped_long,
        "skipped_sample": skipped_sample,
        "sample_rate": sample_rate,
        "estimated_tokens": total_tokens,
        "target_tokens": target_tokens,
        "elapsed_seconds": round(elapsed, 1),
        "output_cpt": str(CPT_JSONL),
    }

    with open(STATS_FILE, "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2, ensure_ascii=False)

    print(f"\n{'='*60}")
    print(f"Done in {elapsed:.0f}s")
    print(f"Scanned: {scanned:,}")
    print(f"Kept: {kept:,}")
    print(f"Estimated tokens: ~{total_tokens/1e6:.0f}M")
    print(f"Output: {CPT_JSONL.name}")


if __name__ == "__main__":
    main()
