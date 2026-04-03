#!/usr/bin/env python3
"""
merge_pubmed_openalex.py
========================
Stage 1: Metadata-level dedup (DOI + title) and merge PubMed + OpenAlex
fulltext corpora into a single JSONL for CPT training.

Inputs:
  - OpenAlex/fulltext.jsonl              (articles, {"text": "...", "doi": "...", ...})
  - PubMed/data/processed/filtered/food_science_corpus.keep.jsonl
                                         (167,244 articles, {pmcid, title, ..., text})
  - PubMed/data/PMC-ids.csv.gz          (PMCID→DOI mapping from NCBI)

Outputs (in Merged/):
  - combined_fulltext.jsonl              (merged corpus before MinHash dedup)
  - pubmed_unique_fulltext.jsonl         (PubMed-only articles kept)
  - merge_stats.json                     (statistics)
"""

import csv
import gzip
import json
import re
import sys
import unicodedata
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE = Path(__file__).resolve().parent

OPENALEX_JSONL = BASE / "OpenAlex" / "fulltext.jsonl"

PUBMED_JSONL   = BASE / "PubMed" / "data" / "processed" / "filtered" / "food_science_corpus.keep.jsonl"
PMC_IDS_GZ     = BASE / "PubMed" / "data" / "PMC-ids.csv.gz"

OUT_DIR        = BASE / "Merged"
OUT_COMBINED   = OUT_DIR / "combined_fulltext.jsonl"
OUT_PUBMED_UNQ = OUT_DIR / "pubmed_unique_fulltext.jsonl"
OUT_STATS      = OUT_DIR / "merge_stats.json"


def normalize_doi(doi: str) -> str:
    """Lowercase + strip whitespace for DOI comparison."""
    return doi.strip().lower()


def normalize_title(title: str) -> str:
    """Normalize title for fuzzy matching: lowercase, strip punctuation/spaces."""
    t = title.strip().lower()
    t = unicodedata.normalize("NFKD", t)
    t = re.sub(r"[^a-z0-9 ]", "", t)       # keep only alphanum + space
    t = re.sub(r"\s+", " ", t).strip()
    return t


def extract_title_from_openalex_text(text: str) -> str:
    """Extract the title line from OpenAlex text field (first line after 'Title: ')."""
    for line in text.split("\n"):
        line = line.strip()
        if line.startswith("Title:"):
            return line[len("Title:"):].strip()
    return ""


# ---------------------------------------------------------------------------
# Step 1: Load OpenAlex DOI set & title set
# ---------------------------------------------------------------------------
def load_openalex_dois_and_titles():
    print("[1/4] Loading OpenAlex DOIs and titles ...")
    dois = set()
    titles = set()

    with open(OPENALEX_JSONL, "r") as f_jsonl:
        for jsonl_line in f_jsonl:
            rec = json.loads(jsonl_line)

            doi = normalize_doi(rec.get("doi", ""))
            if doi:
                dois.add(doi)

            raw_title = extract_title_from_openalex_text(rec["text"])
            nt = normalize_title(raw_title)
            if nt:
                titles.add(nt)

    print(f"       OpenAlex DOIs: {len(dois):,}")
    print(f"       OpenAlex titles: {len(titles):,}")
    return dois, titles


# ---------------------------------------------------------------------------
# Step 2: Build PMCID → DOI mapping from PMC-ids.csv.gz
# ---------------------------------------------------------------------------
def load_pmcid_to_doi():
    print("[2/4] Loading PMCID→DOI mapping from PMC-ids.csv.gz ...")
    mapping = {}
    with gzip.open(PMC_IDS_GZ, "rt", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            pmcid = row["PMCID"].strip()
            doi = row["DOI"].strip()
            if pmcid and doi:
                mapping[pmcid] = normalize_doi(doi)
    print(f"       PMCID→DOI entries: {len(mapping):,}")
    return mapping


# ---------------------------------------------------------------------------
# Step 3: Deduplicate PubMed against OpenAlex, write PubMed-unique
# ---------------------------------------------------------------------------
def dedup_pubmed(oa_dois, oa_titles, pmcid2doi):
    print("[3/4] Deduplicating PubMed against OpenAlex ...")

    total = 0
    doi_matched = 0
    doi_missing = 0
    title_matched = 0
    kept = 0

    with open(PUBMED_JSONL, "r") as fin, \
         open(OUT_PUBMED_UNQ, "w") as fout:

        for line in fin:
            total += 1
            rec = json.loads(line)
            pmcid = rec["pmcid"]
            title = rec.get("title", "")

            # Try DOI dedup
            doi = pmcid2doi.get(pmcid, "")
            if not doi:
                doi_missing += 1

            if doi and doi in oa_dois:
                doi_matched += 1
                continue

            # Try title dedup
            nt = normalize_title(title)
            if nt and nt in oa_titles:
                title_matched += 1
                continue

            # Unique — keep, output in training format {"text": "..."}
            out_rec = {"text": rec["text"]}
            fout.write(json.dumps(out_rec, ensure_ascii=False) + "\n")
            kept += 1

    stats = {
        "pubmed_total": total,
        "pubmed_doi_found": total - doi_missing,
        "pubmed_doi_missing": doi_missing,
        "removed_by_doi": doi_matched,
        "removed_by_title": title_matched,
        "pubmed_unique_kept": kept,
    }
    print(f"       PubMed total:        {total:,}")
    print(f"       DOI coverage:        {total - doi_missing:,} / {total:,}  "
          f"({(total - doi_missing) / total * 100:.1f}%)")
    print(f"       Removed by DOI:      {doi_matched:,}")
    print(f"       Removed by title:    {title_matched:,}")
    print(f"       PubMed unique kept:  {kept:,}")
    return stats


# ---------------------------------------------------------------------------
# Step 4: Concatenate OpenAlex fulltext + PubMed unique → combined JSONL
# ---------------------------------------------------------------------------
def merge_corpora():
    print("[4/4] Merging into combined JSONL ...")
    oa_count = 0
    with open(OUT_COMBINED, "w") as fout:
        # Write all OpenAlex records (strip extra fields, keep only {"text": ...})
        with open(OPENALEX_JSONL, "r") as fin:
            for line in fin:
                rec = json.loads(line)
                out_rec = {"text": rec["text"]}
                fout.write(json.dumps(out_rec, ensure_ascii=False) + "\n")
                oa_count += 1

        # Append PubMed unique records (already {"text": ...} format)
        pm_count = 0
        with open(OUT_PUBMED_UNQ, "r") as fin:
            for line in fin:
                fout.write(line)
                pm_count += 1

    total = oa_count + pm_count
    print(f"       OpenAlex articles:   {oa_count:,}")
    print(f"       PubMed unique:       {pm_count:,}")
    print(f"       Combined total:      {total:,}")
    return oa_count, pm_count, total


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    oa_dois, oa_titles = load_openalex_dois_and_titles()
    pmcid2doi = load_pmcid_to_doi()
    dedup_stats = dedup_pubmed(oa_dois, oa_titles, pmcid2doi)
    oa_count, pm_count, combined_total = merge_corpora()

    # Save stats
    stats = {
        **dedup_stats,
        "openalex_fulltext": oa_count,
        "combined_before_minhash": combined_total,
    }
    with open(OUT_STATS, "w") as f:
        json.dump(stats, f, indent=2, ensure_ascii=False)
    print(f"\n✓ Stats saved to {OUT_STATS}")
    print(f"✓ Combined JSONL: {OUT_COMBINED}  ({combined_total:,} articles)")
    print("  Next step: run minhash_dedup.py")


if __name__ == "__main__":
    main()
