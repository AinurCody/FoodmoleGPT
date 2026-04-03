# FoodmoleGPT — OpenAlex Food Science Paper Collection Pipeline

## Overview

This module is the **paper collection and processing** pipeline for FoodmoleGPT (a food-science domain LLM). Through two rounds of data collection (R1: multi-strategy hybrid + R2: journal-targeted), followed by cleaning, full-text retrieval, filtering, text quality cleaning, and formatting, it produces **578,956** structured food science publications (**145,594 full-text** + **433,362 abstracts**), totaling approximately **5.8 GB**.

> For detailed technical documentation, interview talking points, and design decisions, see: [`docs/data_pipeline.md`](docs/data_pipeline.md)

---

## Directory Structure

```
CPT_dataset/essay/OpenAlex/          # This directory
├── .env                             # API Key (S2_API_KEY)
├── .gitignore
├── README.md                        # Chinese README
├── README_EN.md                     # This file (English)
├── docs/
│   └── data_pipeline.md             # Full technical documentation (11 chapters)
├── src/                             # Collection & processing scripts
│   ├── # ---- Round 1 ----
│   ├── fetch_openalex.py            # R1 keyword search collection
│   ├── fetch_openalex_bulk.py       # R1 bulk collection
│   ├── fetch_openalex_concepts.py   # R1 Concept ID collection
│   ├── fetch_remaining_concepts.py  # R1 supplementary collection
│   ├── fetch_expand_topics.py       # R1 sub-domain expansion
│   ├── fetch_hybrid.py              # R1 hybrid strategy collection
│   ├── fetch_scopus.py              # Scopus collection (backup)
│   ├── clean_data.py                # R1 data cleaning
│   ├── fetch_fulltext_s2.py         # R1 full-text retrieval (S2 + peS2o)
│   ├── merge_fulltext.py            # R1 metadata + full-text merge
│   ├── filter_food.py               # Three-layer food science filter (shared by R1+R2)
│   ├── format_training.py           # R1 training format conversion
│   ├── # ---- Round 2 ----
│   ├── fetch_openalex_r2.py         # R2 journal-targeted collection (75 core journals)
│   ├── clean_data_r2.py             # R2 data cleaning
│   ├── fetch_fulltext_s2_r2.py      # R2 full-text retrieval
│   ├── merge_fulltext_r2.py         # R2 merge
│   ├── filter_food_r2.py            # R2 filtering (safety net)
│   ├── clean_text_quality.py        # Text quality cleaning (tables/mojibake/Unicode)
│   ├── format_training_r2.py        # R2 formatting + R1+R2 merge
│   └── audit_purity.py              # Purity audit tool
├── fulltext.jsonl                   # Full-text training data — 145,594 papers (5.1 GB)
├── abstract.jsonl                   # Abstract training data — 433,362 papers (715 MB)
└── doi_fulltext_only.txt            # Full-text DOI list (for cross-source deduplication)
```

> **Note**: Intermediate data from the collection pipeline (raw/cleaned/filtered directories) remains on the source machine. This directory contains only the final output data plus all scripts and documentation needed for full reproducibility.

---

## Data Processing Pipeline

### Round 1: Multi-Strategy Hybrid Collection

| Stage | Script | Description | Result |
|-------|--------|-------------|--------|
| Collection | `fetch_openalex*.py` etc. | Keyword + Concept ID multi-strategy hybrid | ~1,040,000 papers |
| Cleaning | `clean_data.py` | DOI/title dedup, HTML cleaning, Unicode fix | 1,033,239 papers |
| Full-text | `fetch_fulltext_s2.py` | S2 Batch API + peS2o 136-file scan | 312,533 full-text |
| Merge | `merge_fulltext.py` | Metadata + full-text to JSONL | 11.74 GB |
| Filtering | `filter_food.py` | Three-layer filter (journal/title/keyword) | 91,889 full-text + 81,248 abstracts |
| Formatting | `format_training.py` | JSONL `{"text": "..."}` | **173,137 papers** |

**R1 Key Issue**: Low relevance of OpenAlex Concept tags caused ~76% non-food noise, requiring heavy downstream filtering.

### Round 2: Journal-Targeted Collection

| Stage | Script | Description | Result |
|-------|--------|-------------|--------|
| Collection | `fetch_openalex_r2.py` | 75 food science core journals via Source ID | 791,793 papers |
| Cleaning | `clean_data_r2.py` | Same as R1 + cross-round DOI dedup | 766,316 papers |
| Full-text | `fetch_fulltext_s2_r2.py` | Phase 1: 98.4% DOI-to-ID; Phase 2: peS2o | 53,726 full-text |
| Merge | `merge_fulltext_r2.py` | Metadata + full-text to JSONL | 1.8 GB |
| Filtering | `filter_food_r2.py` | Three-layer safety net (journal-targeted already >99% pure) | 53,705 full-text + 352,114 abstracts |
| Quality | `clean_text_quality.py` | Table residue/mojibake/Unicode math fix | 21 records modified |
| Formatting | `format_training_r2.py` | Formatting + R1+R2 merge | **405,819 papers** |

**R2 Key Improvement**: Shifted from "tag-based query + downstream filtering" to "source journal control", improving purity from 24% to >99%.

### Merge and Final Output

```
format_training_r2.py --merge
  R1: fulltext_train + fulltext_val → merged
  R2: fulltext.jsonl                → appended
  Output: fulltext.jsonl  (145,594 records, 5.10 GB)
          abstract.jsonl  (433,362 records, 715 MB)
```

Every paper is written exactly once — no duplicate sampling, no train/val split (validation set is extracted after downstream merging).

---

## Data Summary

| Metric | R1 | R2 | Combined |
|--------|----|----|----------|
| Raw collected | ~1,040,000 | 791,793 | — |
| Full-text papers | 91,889 | 53,705 | **145,594** |
| Abstract-only papers | 81,248 | 352,114 | **433,362** |
| **Total unique papers** | **173,137** | **405,819** | **578,956** |
| **Disk size** | ~3.4 GB | ~2.4 GB | **~5.8 GB** |

### SCImago Journal Tiers (R2)

Based on SCImago Journal Rank 2024 (Food Science, category 1106), 75 journals are mapped to Q1/Q2/Q3 tiers. Tier info is implicitly preserved via the Venue field, enabling downstream filtering (e.g., using only Q1 data for SFT).

| Quartile | Journals | R2 Papers |
|----------|----------|-----------|
| Q1 | 47 | 322,081 |
| Q2 | 26 | 81,281 |
| Q3 | 2 | 2,457 |

---

## Training Data Format

Each line is a JSON object:

```json
{"text": "Title: Polyphenol-protein interactions in food matrices\nAuthors: Zhang Y; Li X; Wang H\nYear: 2024\nVenue: Food Chemistry\nKeywords: polyphenols;proteins;binding\n\nAbstract:\nThis study investigated...\n\nFull Text:\nIntroduction\nPolyphenols are..."}
```

| Metric | Full-text | Abstract-only |
|--------|-----------|---------------|
| Avg characters | ~35,500 | ~1,700 |
| Avg words | ~5,400 | ~243 |

---

## Reproduction Commands

```bash
# ======== Round 1 ========
python src/fetch_openalex_concepts.py      # Collection
python src/clean_data.py                   # Cleaning
python src/fetch_fulltext_s2.py --phase 1  # DOI → Corpus ID
python src/fetch_fulltext_s2.py --phase 2  # peS2o full-text
python src/merge_fulltext.py               # Merge
python src/filter_food.py                  # Filtering
python src/format_training.py              # Formatting

# ======== Round 2 ========
python src/fetch_openalex_r2.py            # Journal-targeted collection
python src/clean_data_r2.py                # Cleaning
python src/fetch_fulltext_s2_r2.py --phase 1  # DOI → Corpus ID
python src/fetch_fulltext_s2_r2.py --phase 2  # peS2o full-text
python src/merge_fulltext_r2.py            # Merge
python src/filter_food_r2.py               # Filtering (safety net)
python src/clean_text_quality.py           # Text quality cleaning
python src/format_training_r2.py           # Formatting
python src/format_training_r2.py --merge   # R1+R2 merge
```

## Dependencies

```
pandas
requests
python-dotenv
zstandard
huggingface_hub
```

## Notes

- Final training data is approximately **5.8 GB**; full reproduction (including peS2o downloads) requires **30+ GB** of disk space.
- Phase 2 peS2o download requires a stable network connection: 136 files (~700 MB each).
- Semantic Scholar API Key must be configured in `.env`: `S2_API_KEY=xxx`.
- All processing scripts use streaming (O(1) memory) and will not cause OOM.
- R1 data contains ~25% non-food noise (from multidisciplinary journals); R2 journal-targeted data purity is >99%.
- The `fulltext.jsonl` and `abstract.jsonl` in this directory are the final outputs, ready for downstream merging and training.
