#!/usr/bin/env python3
"""
minhash_dedup.py
================
Stage 2: MinHash LSH near-duplicate detection on the merged corpus.

Input:
  - Merged/combined_fulltext.jsonl

Output:
  - Merged/combined_fulltext_deduped.jsonl  (final training corpus)
  - Merged/near_duplicates.jsonl            (duplicate cluster details)
  - Merged/dedup_stats.json                 (statistics)
"""

import json
import sys
import time
from pathlib import Path
from collections import defaultdict

from datasketch import MinHash, MinHashLSH

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
NUM_PERM  = 128          # number of hash functions
THRESHOLD = 0.8          # Jaccard similarity threshold
SHINGLE_K = 5            # k-gram (word-level)
LOG_EVERY = 10_000       # progress log interval

BASE      = Path(__file__).resolve().parent
IN_JSONL  = BASE / "Merged" / "combined_fulltext.jsonl"
OUT_JSONL = BASE / "Merged" / "combined_fulltext_deduped.jsonl"
OUT_DUPS  = BASE / "Merged" / "near_duplicates.jsonl"
OUT_STATS = BASE / "Merged" / "dedup_stats.json"


def log(msg):
    print(msg, flush=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def text_to_shingles(text: str, k: int = SHINGLE_K):
    """Convert text to word-level k-grams."""
    words = text.lower().split()
    if len(words) < k:
        return set(words)
    return {" ".join(words[i:i+k]) for i in range(len(words) - k + 1)}


def build_minhash(shingles):
    m = MinHash(num_perm=NUM_PERM)
    for s in shingles:
        m.update(s.encode("utf-8"))
    return m


def extract_title_snippet(text: str, max_len: int = 120) -> str:
    """Extract a short snippet for logging."""
    for line in text.split("\n"):
        line = line.strip()
        if line.startswith("Title:"):
            return line[:max_len]
    return text[:max_len]


def fmt_elapsed(seconds):
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}h{m:02d}m{s:02d}s"
    return f"{m}m{s:02d}s"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    t0 = time.time()
    log(f"MinHash LSH Dedup  (perms={NUM_PERM}, threshold={THRESHOLD}, "
        f"shingle_k={SHINGLE_K})")
    log(f"Input:  {IN_JSONL}\n")

    # -----------------------------------------------------------------------
    # Pass 1: Build MinHash signatures & insert into LSH index
    #         Also store signatures as compact hashvalue arrays (not objects)
    # -----------------------------------------------------------------------
    log("[1/3] Building MinHash signatures & LSH index ...")
    lsh = MinHashLSH(threshold=THRESHOLD, num_perm=NUM_PERM)
    hashvalues = []    # idx -> numpy array (compact storage)
    snippets = []      # idx -> title snippet (for logging)
    total = 0
    t1 = time.time()

    with open(IN_JSONL, "r") as f:
        for idx, line in enumerate(f):
            rec = json.loads(line)
            text = rec["text"]
            shingles = text_to_shingles(text)
            mh = build_minhash(shingles)

            # Store compact hashvalues (numpy array, ~1 KB each)
            hashvalues.append(mh.hashvalues.copy())
            snippets.append(extract_title_snippet(text))

            try:
                lsh.insert(str(idx), mh)
            except ValueError:
                pass  # exact duplicate minhash — will be caught in query

            total += 1
            if total % LOG_EVERY == 0:
                elapsed = time.time() - t1
                rate = total / elapsed
                log(f"       ... {total:>9,} indexed  "
                    f"({rate:,.0f} art/s, {fmt_elapsed(elapsed)})")

    elapsed1 = time.time() - t1
    log(f"       Total indexed: {total:,}  ({fmt_elapsed(elapsed1)})")

    # -----------------------------------------------------------------------
    # Pass 2: Query LSH to find near-duplicate clusters
    # -----------------------------------------------------------------------
    log("\n[2/3] Querying for near-duplicates ...")
    t2 = time.time()

    parent = list(range(total))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for idx in range(total):
        # Reconstruct MinHash from stored hashvalues
        mh = MinHash(num_perm=NUM_PERM, hashvalues=hashvalues[idx])
        candidates = lsh.query(mh)
        for c in candidates:
            c_idx = int(c)
            if c_idx != idx:
                union(idx, c_idx)

        if (idx + 1) % LOG_EVERY == 0:
            elapsed = time.time() - t2
            rate = (idx + 1) / elapsed
            log(f"       ... {idx + 1:>9,} queried  "
                f"({rate:,.0f} art/s, {fmt_elapsed(elapsed)})")

    elapsed2 = time.time() - t2
    log(f"       Query done: {total:,} articles  ({fmt_elapsed(elapsed2)})")

    # Free memory
    del hashvalues
    del lsh

    # Build clusters (size > 1)
    clusters = defaultdict(list)
    for i in range(total):
        r = find(i)
        clusters[r].append(i)

    dup_clusters = {r: members for r, members in clusters.items()
                    if len(members) > 1}
    log(f"       Near-duplicate clusters: {len(dup_clusters)}")

    # For each cluster, keep the first (lowest index) article, remove rest
    to_remove = set()
    cluster_details = []
    for root, members in sorted(dup_clusters.items()):
        members.sort()
        keep = members[0]
        remove = members[1:]
        to_remove.update(remove)
        cluster_details.append({
            "cluster_size": len(members),
            "keep_idx": keep,
            "keep_title": snippets[keep],
            "remove_indices": remove,
            "remove_titles": [snippets[i] for i in remove],
        })

    log(f"       Articles to remove: {len(to_remove)}")

    # Save cluster details
    with open(OUT_DUPS, "w") as f:
        for c in cluster_details:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    log(f"       Cluster details → {OUT_DUPS}")

    # -----------------------------------------------------------------------
    # Pass 3: Write deduplicated output
    # -----------------------------------------------------------------------
    log(f"\n[3/3] Writing deduplicated JSONL ...")
    t3 = time.time()
    kept = 0
    with open(IN_JSONL, "r") as fin, open(OUT_JSONL, "w") as fout:
        for idx, line in enumerate(fin):
            if idx not in to_remove:
                fout.write(line)
                kept += 1
            if (idx + 1) % LOG_EVERY == 0:
                log(f"       ... {idx + 1:>9,} processed, {kept:,} kept")

    removed = total - kept
    elapsed3 = time.time() - t3
    total_elapsed = time.time() - t0

    log(f"\n       Total input:    {total:,}")
    log(f"       Removed:        {removed:,}  ({removed / total * 100:.4f}%)")
    log(f"       Final kept:     {kept:,}")
    log(f"       Write time:     {fmt_elapsed(elapsed3)}")
    log(f"       Total time:     {fmt_elapsed(total_elapsed)}")

    # --- Save stats ---
    size_dist = defaultdict(int)
    for c in cluster_details:
        size_dist[c["cluster_size"]] += 1

    stats = {
        "minhash_config": {
            "num_perm": NUM_PERM,
            "threshold": THRESHOLD,
            "shingle_k": SHINGLE_K,
        },
        "input_total": total,
        "near_dup_clusters": len(dup_clusters),
        "cluster_size_distribution": {str(k): v for k, v in sorted(size_dist.items())},
        "removed": removed,
        "final_kept": kept,
        "elapsed_seconds": round(total_elapsed, 1),
    }
    with open(OUT_STATS, "w") as f:
        json.dump(stats, f, indent=2, ensure_ascii=False)

    log(f"\n✓ Stats saved to {OUT_STATS}")
    log(f"✓ Final corpus: {OUT_JSONL}  ({kept:,} articles)")


if __name__ == "__main__":
    main()
