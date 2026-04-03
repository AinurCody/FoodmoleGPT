"""
FoodmoleGPT — Merge & Deduplicate SFT Data

Merges OpenAlex + PubMed outputs, performs:
1. Exact dedup (identical instructions)
2. Near-duplicate dedup (MinHash + Jaccard similarity on instruction text)
3. Quality filters (length, language)
4. Exports final dataset in LLaMA-Factory Alpaca JSONL format

Usage:
    python merge_and_dedup.py
    python merge_and_dedup.py --similarity-threshold 0.85
"""

import json
import re
import hashlib
import argparse
import random
from pathlib import Path
from collections import defaultdict
from datetime import datetime

# ── Paths ──────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "output"
OPENALEX_FILE = OUTPUT_DIR / "openalex.jsonl"
PUBMED_FILE = OUTPUT_DIR / "pubmed.jsonl"
FINAL_DIR = BASE_DIR / "final"

# ── MinHash config ─────────────────────────────────────────────────
NUM_HASHES = 128
NGRAM_SIZE = 3
SIMILARITY_THRESHOLD = 0.80  # Pairs above this are considered near-duplicates
NUM_BANDS = 32               # LSH bands for efficient near-dedup
ROWS_PER_BAND = NUM_HASHES // NUM_BANDS  # 4 rows per band


def load_jsonl(path: Path) -> list[dict]:
    with open(path, "r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def char_ngrams(text: str, n: int = NGRAM_SIZE) -> set[str]:
    """Extract character n-grams from text."""
    text = text.lower().strip()
    text = re.sub(r'\s+', ' ', text)
    if len(text) < n:
        return {text}
    return {text[i:i+n] for i in range(len(text) - n + 1)}


def minhash_signature(ngrams: set[str], num_hashes: int = NUM_HASHES) -> list[int]:
    """Compute MinHash signature for a set of n-grams."""
    if not ngrams:
        return [0] * num_hashes

    sig = [float('inf')] * num_hashes
    for gram in ngrams:
        gram_bytes = gram.encode('utf-8')
        for i in range(num_hashes):
            h = int(hashlib.md5(gram_bytes + i.to_bytes(4, 'big')).hexdigest(), 16)
            if h < sig[i]:
                sig[i] = h
    return sig


def jaccard_from_signatures(sig1: list[int], sig2: list[int]) -> float:
    """Estimate Jaccard similarity from MinHash signatures."""
    matches = sum(1 for a, b in zip(sig1, sig2) if a == b)
    return matches / len(sig1)


def lsh_buckets(signature: list[int], num_bands: int = NUM_BANDS) -> list[str]:
    """Compute LSH bucket keys for a signature."""
    buckets = []
    for band in range(num_bands):
        start = band * ROWS_PER_BAND
        end = start + ROWS_PER_BAND
        band_slice = tuple(signature[start:end])
        bucket_key = hashlib.md5(str(band_slice).encode()).hexdigest()
        buckets.append(f"b{band}_{bucket_key}")
    return buckets


def normalize_type(t: str) -> str:
    """Normalize question type labels."""
    t = t.strip().upper()
    # Fix common variants
    if t in ("ANALYSIS", "ANALYZE"):
        return "ANALYTICAL"
    if t in ("METHODOLOGIC", "METHOD"):
        return "METHODOLOGICAL"
    if t in ("SYNTHESIZE", "PREDICT"):
        return "SYNTHESIS"
    if t in ("APPLY", "PRACTICAL"):
        return "APPLICATION"
    if t in ("FACT", "KNOWLEDGE", "RECALL"):
        return "FACTUAL"
    if t in ("MECHANISM", "EXPLAIN"):
        return "MECHANISTIC"
    valid = {"FACTUAL", "MECHANISTIC", "ANALYTICAL", "METHODOLOGICAL", "APPLICATION", "SYNTHESIS"}
    return t if t in valid else "OTHER"


def main():
    parser = argparse.ArgumentParser(description="Merge and deduplicate SFT data")
    parser.add_argument("--similarity-threshold", type=float, default=SIMILARITY_THRESHOLD,
                        help=f"Jaccard threshold for near-dedup (default: {SIMILARITY_THRESHOLD})")
    args = parser.parse_args()

    sim_threshold = args.similarity_threshold
    print(f"[1/6] Loading data...")

    openalex_data = load_jsonl(OPENALEX_FILE)
    pubmed_data = load_jsonl(PUBMED_FILE)
    total_raw = len(openalex_data) + len(pubmed_data)
    print(f"  OpenAlex: {len(openalex_data)}")
    print(f"  PubMed:   {len(pubmed_data)}")
    print(f"  Total:    {total_raw}")

    # ── Step 2: Merge ──────────────────────────────────────────────
    print(f"\n[2/6] Merging...")
    all_pairs = openalex_data + pubmed_data
    random.seed(42)
    random.shuffle(all_pairs)  # Shuffle to interleave sources
    print(f"  Merged: {len(all_pairs)}")

    # ── Step 3: Exact dedup ────────────────────────────────────────
    print(f"\n[3/6] Exact dedup (identical instructions)...")
    seen_exact = set()
    after_exact = []
    exact_dupes = 0
    for p in all_pairs:
        key = p["instruction"].strip().lower()
        if key not in seen_exact:
            seen_exact.add(key)
            after_exact.append(p)
        else:
            exact_dupes += 1
    print(f"  Removed: {exact_dupes} exact duplicates")
    print(f"  Remaining: {len(after_exact)}")

    # ── Step 4: Quality filter ─────────────────────────────────────
    print(f"\n[4/6] Quality filtering...")
    filtered = []
    filter_stats = defaultdict(int)
    for p in after_exact:
        inst = p["instruction"].strip()
        out = p["output"].strip()

        # Minimum instruction length
        if len(inst) < 20:
            filter_stats["instruction_too_short"] += 1
            continue
        # Minimum output length
        if len(out) < 100:
            filter_stats["output_too_short"] += 1
            continue
        # Max output length (avoid degenerate cases)
        if len(out) > 5000:
            filter_stats["output_too_long"] += 1
            continue
        # Trivial questions
        inst_lower = inst.lower()
        if any(x in inst_lower for x in ["who are the authors", "what journal", "what year was this published"]):
            filter_stats["trivial_question"] += 1
            continue

        # Normalize type
        p["type"] = normalize_type(p.get("type", "OTHER"))

        filtered.append(p)

    removed_quality = len(after_exact) - len(filtered)
    print(f"  Removed: {removed_quality} (detail: {dict(filter_stats)})")
    print(f"  Remaining: {len(filtered)}")

    # ── Step 5: Near-duplicate dedup (MinHash LSH) ─────────────────
    print(f"\n[5/6] Near-duplicate dedup (MinHash, threshold={sim_threshold})...")
    print(f"  Computing signatures...")

    signatures = []
    for p in filtered:
        ngrams = char_ngrams(p["instruction"])
        sig = minhash_signature(ngrams)
        signatures.append(sig)

    # LSH: build bucket index
    print(f"  Building LSH index ({NUM_BANDS} bands)...")
    bucket_index = defaultdict(list)  # bucket_key -> [indices]
    for idx, sig in enumerate(signatures):
        for bk in lsh_buckets(sig):
            bucket_index[bk].append(idx)

    # Find candidate pairs from buckets, verify with Jaccard
    print(f"  Finding near-duplicate candidates...")
    to_remove = set()
    checked_pairs = set()
    near_dup_count = 0

    for bk, indices in bucket_index.items():
        if len(indices) < 2:
            continue
        # Only check pairs within bucket (limit to reasonable size)
        bucket_items = indices[:100]  # Cap bucket size to avoid O(n^2)
        for i in range(len(bucket_items)):
            if bucket_items[i] in to_remove:
                continue
            for j in range(i + 1, len(bucket_items)):
                if bucket_items[j] in to_remove:
                    continue
                pair_key = (min(bucket_items[i], bucket_items[j]),
                            max(bucket_items[i], bucket_items[j]))
                if pair_key in checked_pairs:
                    continue
                checked_pairs.add(pair_key)

                sim = jaccard_from_signatures(signatures[bucket_items[i]],
                                              signatures[bucket_items[j]])
                if sim >= sim_threshold:
                    # Remove the second one (keep first occurrence)
                    to_remove.add(bucket_items[j])
                    near_dup_count += 1

    after_neardup = [p for idx, p in enumerate(filtered) if idx not in to_remove]
    print(f"  Candidate pairs checked: {len(checked_pairs)}")
    print(f"  Near-duplicates removed: {near_dup_count}")
    print(f"  Remaining: {len(after_neardup)}")

    # ── Step 6: Export ─────────────────────────────────────────────
    print(f"\n[6/6] Exporting final dataset...")
    FINAL_DIR.mkdir(parents=True, exist_ok=True)

    # Alpaca JSONL (for LLaMA-Factory)
    final_alpaca = FINAL_DIR / "foodmole_sft_100k.jsonl"
    with open(final_alpaca, "w", encoding="utf-8") as f:
        for p in after_neardup:
            record = {
                "instruction": p["instruction"],
                "input": p.get("input", ""),
                "output": p["output"],
            }
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    # Full version with metadata (for analysis)
    final_full = FINAL_DIR / "foodmole_sft_100k_full.jsonl"
    with open(final_full, "w", encoding="utf-8") as f:
        for p in after_neardup:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")

    # Stats report
    type_counts = defaultdict(int)
    source_counts = defaultdict(int)
    for p in after_neardup:
        type_counts[p.get("type", "OTHER")] += 1
        source_counts[p.get("source", "unknown")] += 1

    stats = {
        "generated_at": datetime.now().isoformat(),
        "raw_total": total_raw,
        "after_exact_dedup": len(after_exact),
        "after_quality_filter": len(filtered),
        "after_near_dedup": len(after_neardup),
        "final_count": len(after_neardup),
        "exact_duplicates_removed": exact_dupes,
        "quality_filtered": removed_quality,
        "near_duplicates_removed": near_dup_count,
        "similarity_threshold": sim_threshold,
        "type_distribution": dict(sorted(type_counts.items(), key=lambda x: -x[1])),
        "source_distribution": dict(source_counts),
        "filter_details": dict(filter_stats),
    }

    stats_file = FINAL_DIR / "dataset_stats.json"
    with open(stats_file, "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2, ensure_ascii=False)

    # Print summary
    print(f"\n{'='*60}")
    print(f"  FINAL DATASET SUMMARY")
    print(f"{'='*60}")
    print(f"  Raw pairs:              {total_raw:>8}")
    print(f"  After exact dedup:      {len(after_exact):>8}  (-{exact_dupes})")
    print(f"  After quality filter:   {len(filtered):>8}  (-{removed_quality})")
    print(f"  After near-dedup:       {len(after_neardup):>8}  (-{near_dup_count})")
    print(f"  ─────────────────────────────────")
    print(f"  FINAL COUNT:            {len(after_neardup):>8}")
    print(f"")
    print(f"  Source distribution:")
    for s, c in sorted(source_counts.items()):
        print(f"    {s:12s}: {c:>6} ({c/len(after_neardup)*100:.1f}%)")
    print(f"")
    print(f"  Type distribution:")
    for t, c in sorted(type_counts.items(), key=lambda x: -x[1]):
        print(f"    {t:16s}: {c:>6} ({c/len(after_neardup)*100:.1f}%)")
    print(f"")
    print(f"  Output files:")
    print(f"    {final_alpaca}")
    print(f"    {final_full}")
    print(f"    {stats_file}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
