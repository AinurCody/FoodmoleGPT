"""
FoodmoleGPT Round 2 - Full Text Acquisition via S2 + peS2o
===========================================================
Adapted from fetch_fulltext_s2.py for Round 2 data.
Phase 1: Map R2 DOIs → S2 Corpus IDs
Phase 2: Stream peS2o and extract matching full text

Usage:
    conda activate foodmole
    python src/fetch_fulltext_s2_r2.py --phase 1     # DOI → Corpus ID
    python src/fetch_fulltext_s2_r2.py --phase 2     # peS2o full text
    python src/fetch_fulltext_s2_r2.py --phase all    # Both
    python src/fetch_fulltext_s2_r2.py --test         # Test with 10 DOIs
"""

import os
import io
import json
import time
import argparse
import sys
from pathlib import Path
from datetime import datetime

import requests
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# =============================================================================
# CONFIGURATION (Round 2 paths)
# =============================================================================

S2_API_KEY = os.getenv("S2_API_KEY")
S2_BATCH_URL = "https://api.semanticscholar.org/graph/v1/paper/batch"
S2_BATCH_SIZE = 500
S2_DELAY = 1.5

INPUT_CSV = Path("D:/FoodmoleGPT/data/cleaned_r2/master_cleaned_r2.csv")
OUTPUT_DIR = Path("D:/FoodmoleGPT/data/fulltext_r2")
MAPPING_FILE = OUTPUT_DIR / "doi_to_corpusid_r2.csv"
FULLTEXT_DIR = OUTPUT_DIR / "extracted"
PROGRESS_FILE = OUTPUT_DIR / "phase1_progress.json"

MAX_RETRIES = 3
RETRY_WAITS = [5, 15, 30]


# =============================================================================
# PHASE 1: DOI → Corpus ID Mapping
# =============================================================================

def load_progress() -> dict:
    if PROGRESS_FILE.exists():
        with open(PROGRESS_FILE) as f:
            return json.load(f)
    return {"completed_batches": 0, "total_mapped": 0, "total_missing": 0}


def save_progress(progress: dict):
    with open(PROGRESS_FILE, "w") as f:
        json.dump(progress, f)


def batch_lookup_dois(dois: list, fields: str = "paperId,corpusId,externalIds,title,openAccessPdf") -> list:
    """Look up a batch of DOIs via Semantic Scholar batch API."""
    ids = [f"DOI:{doi}" for doi in dois]
    headers = {"x-api-key": S2_API_KEY} if S2_API_KEY else {}
    params = {"fields": fields}

    for attempt in range(MAX_RETRIES + 1):
        try:
            resp = requests.post(
                S2_BATCH_URL,
                json={"ids": ids},
                params=params,
                headers=headers,
                timeout=30,
            )
            if resp.status_code == 200:
                return resp.json()
            elif resp.status_code == 429:
                wait = RETRY_WAITS[min(attempt, len(RETRY_WAITS) - 1)]
                print(f" RATE_LIMIT(wait {wait}s)", end="", flush=True)
                time.sleep(wait)
            else:
                print(f" HTTP_{resp.status_code}", end="", flush=True)
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_WAITS[min(attempt, len(RETRY_WAITS) - 1)])
        except Exception as e:
            err = str(e)[:40]
            if attempt < MAX_RETRIES:
                wait = RETRY_WAITS[min(attempt, len(RETRY_WAITS) - 1)]
                print(f" ERR:{err}(retry {wait}s)", end="", flush=True)
                time.sleep(wait)
            else:
                print(f" FAIL:{err}")
                return [None] * len(dois)

    return [None] * len(dois)


def run_phase1(test_mode: bool = False):
    """Phase 1: Map R2 DOIs to Semantic Scholar Corpus IDs."""
    print("\n" + "=" * 70)
    print("📋 PHASE 1: DOI → Semantic Scholar Corpus ID Mapping (R2)")
    print("=" * 70)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("   Loading R2 cleaned data...")
    df = pd.read_csv(INPUT_CSV, usecols=["openalex_id", "doi", "title"])
    df_with_doi = df[df["doi"].notna()].copy()
    all_dois = df_with_doi["doi"].tolist()

    if test_mode:
        all_dois = all_dois[:10]
        print(f"   🧪 TEST MODE: using {len(all_dois)} DOIs")
    else:
        print(f"   Total DOIs: {len(all_dois):,}")

    progress = load_progress()
    start_batch = progress["completed_batches"]

    batches = [all_dois[i:i + S2_BATCH_SIZE] for i in range(0, len(all_dois), S2_BATCH_SIZE)]
    total_batches = len(batches)

    print(f"   Batches: {total_batches:,} ({S2_BATCH_SIZE} DOIs each)")
    print(f"   Rate: 1 req / {S2_DELAY}s → ETA: {total_batches * S2_DELAY / 60:.0f} min")

    if start_batch > 0:
        print(f"   ✅ Resuming from batch {start_batch}/{total_batches}")

    mode = "a" if start_batch > 0 else "w"
    out_file = open(MAPPING_FILE, mode, encoding="utf-8")
    if mode == "w":
        out_file.write("doi,s2_corpus_id,s2_paper_id,has_open_access_pdf,oa_pdf_url\n")

    mapped = progress["total_mapped"]
    missing = progress["total_missing"]
    start_time = datetime.now()

    for batch_idx in range(start_batch, total_batches):
        batch_dois = batches[batch_idx]
        pct = (batch_idx + 1) / total_batches * 100
        elapsed = (datetime.now() - start_time).total_seconds()
        done_since_resume = batch_idx - start_batch + 1
        if done_since_resume > 1:
            eta_s = elapsed / done_since_resume * (total_batches - batch_idx - 1)
            eta_str = f"ETA {eta_s/60:.0f}min"
        else:
            eta_str = ""

        print(f"\r   Batch {batch_idx+1}/{total_batches} ({pct:.1f}%) | "
              f"Mapped: {mapped:,} | Missing: {missing:,} | {eta_str}    ",
              end="", flush=True)

        results = batch_lookup_dois(batch_dois)

        for doi, result in zip(batch_dois, results):
            if result and result.get("corpusId"):
                corpus_id = result["corpusId"]
                paper_id = result.get("paperId", "")
                has_oa = bool(result.get("openAccessPdf"))
                oa_url = result.get("openAccessPdf", {}).get("url", "") if has_oa else ""
                oa_url = oa_url.replace(",", "%2C")
                out_file.write(f"{doi},{corpus_id},{paper_id},{has_oa},{oa_url}\n")
                mapped += 1
            else:
                missing += 1

        if (batch_idx + 1) % 50 == 0:
            out_file.flush()
            save_progress({
                "completed_batches": batch_idx + 1,
                "total_mapped": mapped,
                "total_missing": missing,
            })

        time.sleep(S2_DELAY)

    out_file.close()
    save_progress({
        "completed_batches": total_batches,
        "total_mapped": mapped,
        "total_missing": missing,
    })

    elapsed = datetime.now() - start_time
    print(f"\n\n   ✅ Phase 1 Complete!")
    print(f"   Mapped:  {mapped:,}")
    print(f"   Missing: {missing:,}")
    print(f"   Output:  {MAPPING_FILE}")
    print(f"   Elapsed: {elapsed}")


# =============================================================================
# PHASE 2: Stream peS2o and Filter
# =============================================================================

def run_phase2():
    """Phase 2: Stream peS2o .zst files and extract matching full text for R2."""
    print("\n" + "=" * 70)
    print("📖 PHASE 2: Streaming peS2o for Full Text Extraction (R2)")
    print("=" * 70)

    if not MAPPING_FILE.exists():
        print("   ❌ Phase 1 mapping file not found. Run Phase 1 first.")
        return

    print("   Loading Corpus ID mapping...")
    mapping_df = pd.read_csv(MAPPING_FILE, usecols=["s2_corpus_id"], on_bad_lines="skip")
    corpus_ids = set()
    for cid in mapping_df["s2_corpus_id"].dropna():
        try:
            corpus_ids.add(str(int(float(cid))))
        except (ValueError, OverflowError):
            pass
    print(f"   Corpus IDs to match: {len(corpus_ids):,}")

    FULLTEXT_DIR.mkdir(parents=True, exist_ok=True)

    try:
        from huggingface_hub import HfApi, hf_hub_download
        import zstandard as zstd
    except ImportError:
        print("   ❌ Missing packages. Run:")
        print("      pip install huggingface_hub zstandard")
        return

    print("   Listing peS2o v3 files on HuggingFace...")
    api = HfApi()
    all_files = api.list_repo_files("allenai/peS2o", repo_type="dataset")
    data_files = sorted([f for f in all_files if "data/v3/train-" in f and f.endswith(".zst")])

    if not data_files:
        data_files = sorted([f for f in all_files if "data/v2/train-" in f])

    if not data_files:
        print("   ❌ No data files found.")
        return

    print(f"   Found {len(data_files)} data files to scan")

    # Resume support
    phase2_progress = OUTPUT_DIR / "phase2_progress.json"
    if phase2_progress.exists():
        with open(phase2_progress) as f:
            p2 = json.load(f)
        start_file_idx = p2.get("completed_files", 0)
        matched = p2.get("matched", 0)
        fulltext_count = p2.get("fulltext_count", 0)
        scanned = p2.get("scanned", 0)
        print(f"   ✅ Resuming from file {start_file_idx}/{len(data_files)}")
    else:
        start_file_idx = 0
        matched = 0
        fulltext_count = 0
        scanned = 0

    out_path = FULLTEXT_DIR / "food_science_fulltext_r2.jsonl"
    out_mode = "a" if start_file_idx > 0 else "w"
    out_file = open(out_path, out_mode, encoding="utf-8")

    start_time = datetime.now()

    for file_idx in range(start_file_idx, len(data_files)):
        file_path = data_files[file_idx]
        file_name = file_path.split("/")[-1]

        print(f"\n   📥 File {file_idx+1}/{len(data_files)}: {file_name}")
        print(f"      Downloading...", end="", flush=True)

        try:
            local_path = hf_hub_download(
                "allenai/peS2o",
                filename=file_path,
                repo_type="dataset",
            )
            print(f" ✅", end="", flush=True)

            file_matched = 0
            file_fulltext = 0
            file_scanned = 0

            dctx = zstd.ZstdDecompressor()
            with open(local_path, "rb") as compressed:
                with dctx.stream_reader(compressed) as reader:
                    text_stream = io.TextIOWrapper(reader, encoding="utf-8", errors="replace")
                    for line in text_stream:
                        line = line.strip()
                        if not line:
                            continue

                        file_scanned += 1
                        try:
                            doc = json.loads(line)
                        except json.JSONDecodeError:
                            continue

                        doc_id = str(doc.get("id", ""))

                        if doc_id in corpus_ids:
                            file_matched += 1
                            source = doc.get("source", "")
                            text = doc.get("text", "")
                            text_len = len(text) if text else 0

                            if "s2orc" in source and text_len > 500:
                                file_fulltext += 1
                                record = {
                                    "s2_corpus_id": doc_id,
                                    "source": source,
                                    "created": doc.get("created", ""),
                                    "text": text,
                                    "text_length": text_len,
                                    "word_count": len(text.split()) if text else 0,
                                }
                                out_file.write(json.dumps(record, ensure_ascii=False) + "\n")

                        if file_scanned % 50000 == 0:
                            print(f"\r      Scanned: {file_scanned:,} | "
                                  f"Matched: {file_matched:,} (fulltext: {file_fulltext:,})    ",
                                  end="", flush=True)

            scanned += file_scanned
            matched += file_matched
            fulltext_count += file_fulltext

            print(f"\r      Done: {file_scanned:,} scanned, "
                  f"{file_matched:,} matched, {file_fulltext:,} fulltext    ")

            out_file.flush()
            with open(phase2_progress, "w") as f:
                json.dump({
                    "completed_files": file_idx + 1,
                    "matched": matched,
                    "fulltext_count": fulltext_count,
                    "scanned": scanned,
                }, f)

            try:
                Path(local_path).unlink()
            except Exception:
                pass

        except Exception as e:
            print(f"\n      ⚠️ Error: {str(e)[:80]}")
            continue

    out_file.close()

    elapsed = datetime.now() - start_time
    print(f"\n\n   ✅ Phase 2 Complete!")
    print(f"   Files processed: {len(data_files):,}")
    print(f"   Scanned:         {scanned:,}")
    print(f"   Matched total:   {matched:,}")
    print(f"   Full text saved: {fulltext_count:,}")
    print(f"   Output:          {out_path}")
    if out_path.exists():
        size_mb = out_path.stat().st_size / 1024 / 1024
        print(f"   Size:            {size_mb:.1f} MB ({size_mb/1024:.2f} GB)")
    print(f"   Elapsed:         {elapsed}")

    stats = {
        "files_processed": len(data_files),
        "scanned": scanned,
        "matched": matched,
        "fulltext": fulltext_count,
        "elapsed_seconds": elapsed.total_seconds(),
    }
    with open(OUTPUT_DIR / "phase2_stats.json", "w") as f:
        json.dump(stats, f, indent=2)


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="FoodmoleGPT R2 Full Text via S2 + peS2o")
    parser.add_argument("--phase", choices=["1", "2", "all"], default="all",
                       help="Which phase to run")
    parser.add_argument("--test", action="store_true",
                       help="Test mode: only 10 DOIs in Phase 1")
    args = parser.parse_args()

    print("=" * 70)
    print("🚀 FoodmoleGPT Round 2 - Full Text Acquisition")
    print("=" * 70)
    print(f"   API Key: {'✅ Loaded' if S2_API_KEY else '❌ Missing (set S2_API_KEY in .env)'}")
    print(f"   Input:   {INPUT_CSV}")
    print(f"   Output:  {OUTPUT_DIR}")

    if not S2_API_KEY:
        print("\n   ⛔ S2 API key not found. Add S2_API_KEY to .env")
        return

    if args.test:
        print("\n   🧪 TEST MODE")
        run_phase1(test_mode=True)
        return

    if args.phase in ("1", "all"):
        run_phase1()

    if args.phase in ("2", "all"):
        run_phase2()

    print("\n" + "=" * 70)
    print("✅ Round 2 full text acquisition complete!")
    print("=" * 70)


if __name__ == "__main__":
    main()
