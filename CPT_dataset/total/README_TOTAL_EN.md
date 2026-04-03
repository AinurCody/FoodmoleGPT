# FoodmoleGPT CPT Corpus — Final Merged Dataset

## Overview

| Item | Value |
|------|-------|
| **Output file** | `total/cpt_corpus_merged.jsonl` |
| **Total documents** | 1,717,582 |
| **Estimated tokens** | ~3.1B (tiktoken cl100k_base, sampled) |
| **Domain / General split** | 75.0% / 25.0% |
| **Format** | `{"text": "...", "source": "<tag>"}` |
| **Shuffle seed** | 42 |

This file is the final CPT (Continual Pre-Training) corpus for FoodmoleGPT, ready to be loaded into LLaMA-Factory for training. All records are shuffled and tagged with a `source` field for provenance tracking.

---

## Data Sources

### 1. Food Science Full-text Papers (`essay_fulltext`)

| Item | Value |
|------|-------|
| Documents | 253,569 |
| Estimated tokens | ~2,190M (70.0%) |
| Source file | `essay/Merged/combined_fulltext_deduped.jsonl` |

- **Origin**: Full-text papers from PubMed Central (PMC) Open Access, queried via food-science MeSH terms and keyword expansion.
- **Pipeline**: XML download → text extraction → quality filtering → MinHash near-deduplication (across PubMed + OpenAlex sources).
- **Details**: See `essay/Merged/README_Total.md`.

### 2. Paper Abstracts (`essay_abstract`)

| Item | Value |
|------|-------|
| Documents | 433,362 |
| Estimated tokens | ~180M (5.8%) |
| Source file | `essay/OpenAlex/abstract.jsonl` |

- **Origin**: OpenAlex API — abstracts of food-science-related publications.
- **Format**: Each record is `{"text": "Title: <title>\n\n<abstract>"}`.
- **Overlap**: Only 16 DOIs overlap with the full-text set; effectively independent.

### 3. Wikipedia Food Articles (`wiki_food`)

| Item | Value |
|------|-------|
| Documents | 24,479 |
| Estimated tokens | ~19M (0.6%) |
| Source file | `book/data/wiki_food_cpt.jsonl` |

- **Origin**: `wikimedia/wikipedia` 20231101.en snapshot via HuggingFace Datasets (streaming).
- **Filtering**: Three-tier keyword system with regex word-boundary matching (`\b`):
  - **Tier 1 (Safe)**: Unambiguous multi-word phrases (e.g., "food science", "cuisine") — title match alone is sufficient.
  - **Tier 2 (Ambiguous)**: Short common words (e.g., "oil", "fish", "tea") — title match accepted only if the opening text also contains a food-related confirmation keyword.
  - **Tier 3 (Text-only)**: Articles with generic titles but food-specific opening text (e.g., "edible", "food source", "used in cooking").
- Exclusion rules filter sports, entertainment, politics, military, infrastructure, and biography articles.
- **Pipeline**: `book/download_wiki_food.py` → `wiki_food_cpt.jsonl` (text-only CPT format).
- **Details**: See `book/README_BOOK_EN.md`.

### 4. FineWeb General Corpus (`fineweb_general`)

| Item | Value |
|------|-------|
| Documents | 1,006,172 |
| Estimated tokens | ~737M (23.6%) |
| Source file | `general/data/fineweb2_general_cpt.jsonl` |

- **Origin**: `HuggingFaceFW/fineweb` — high-quality, cleaned English web corpus (15T+ tokens total).
- **Sampling**: Systematic sampling (every 50th document), length filter 500–50,000 chars. Originally sampled ~800M tokens; truncated to 25% of total during merge.
- **Purpose**: General-domain "replay" data to prevent catastrophic forgetting during CPT.
- **Details**: See `general/README_GENERAL_EN.md`.

---

## Composition Summary

```
Source                  Documents     Tokens        Share
────────────────────────────────────────────────────────────
essay_fulltext            253,569   ~2,190M       70.0%
essay_abstract            433,362     ~180M        5.8%
wiki_food                  24,479      ~19M        0.6%
fineweb_general         1,006,172     ~737M       23.6%
────────────────────────────────────────────────────────────
TOTAL                   1,717,582   ~3,126M      100.0%
```

Domain sources (food science papers + abstracts + Wikipedia) account for 75% of the corpus; the FineWeb general replay corpus accounts for exactly 25%.

---

## Merge Strategy

1. **Load domain sources in full** — all three domain sources are included without sampling or truncation.
2. **Budget the general corpus** — calculate the token budget so that general = 25% of the final total:
   ```
   general_budget = domain_tokens × ratio / (1 − ratio)
                  = 2,389M × 0.25 / 0.75
                  ≈ 796M tokens (word_count×1.3 budget; actual tiktoken ≈ 737M)
   ```
3. **Truncate general source** — read the FineWeb JSONL sequentially and stop when the token budget is reached.
4. **Tag all records** — add a `"source"` field to every document for downstream analysis.
5. **Shuffle** — randomly shuffle all records (seed=42) to avoid sequential bias during training.
6. **Write output** — single JSONL file at `total/cpt_corpus_merged.jsonl`.

Merge script: `merge_all_cpt.py`

---

## Token Estimation

Token counts are estimated via **tiktoken cl100k_base** tokenizer with stratified sampling (500 global + 300 per-source random samples, seed=42). The global estimate (~3.09B) and per-source sum (~3.13B) agree within 1.3%. The merge script internally uses a `word_count × 1.3` heuristic to budget the general corpus ratio; actual token counts by tiktoken are ~16% higher.

---

## Output Format

Each line in `cpt_corpus_merged.jsonl` is a JSON object:

```json
{"text": "Full document text here...", "source": "essay_fulltext"}
```

The `source` field takes one of four values:
- `essay_fulltext` — full-text food science papers
- `essay_abstract` — paper abstracts
- `wiki_food` — Wikipedia food articles
- `fineweb_general` — FineWeb general web corpus

---

## Directory Structure

```
CPT_dataset/
├── essay/
│   ├── Merged/
│   │   ├── combined_fulltext_deduped.jsonl    # Deduplicated full-text papers
│   │   └── README_Total.md
│   ├── OpenAlex/
│   │   ├── abstract.jsonl                      # Paper abstracts
│   │   └── fulltext.jsonl                      # OpenAlex full-text (merged into Merged/)
│   └── PubMed/
│       └── ...                                 # PubMed pipeline scripts & data
├── book/
│   ├── download_wiki_food.py                   # Wikipedia extraction script
│   ├── README_BOOK_EN.md
│   ├── README_BOOK_ZH.md
│   └── data/
│       ├── wiki_food_cpt.jsonl                 # Wikipedia food articles (CPT-ready)
│       └── filter_stats.json
├── general/
│   ├── download_fineweb2.py                    # FineWeb sampling script
│   ├── README_GENERAL_EN.md
│   ├── README_GENERAL_ZH.md
│   └── data/
│       ├── fineweb2_general_cpt.jsonl          # FineWeb general corpus
│       └── sample_stats.json
├── merge_all_cpt.py                            # Final merge script
└── total/
    ├── cpt_corpus_merged.jsonl                 # ← FINAL OUTPUT (~13 GB)
    ├── merge_all_stats.json                    # Merge statistics
    ├── README_TOTAL_EN.md                      # This file
    └── README_TOTAL_ZH.md                      # Chinese version
```

---

## Reproducibility

All scripts are deterministic and reproducible:

```bash
# Step 1: Download Wikipedia food articles (~15 min)
cd CPT_dataset/book
python download_wiki_food.py

# Step 2: Sample FineWeb general corpus (~2.3 hours)
cd CPT_dataset/general
python download_fineweb2.py

# Step 3: Merge all sources (~7 min)
cd CPT_dataset
python merge_all_cpt.py --general-ratio 0.25 --seed 42
```

Prerequisites: Python 3.10+, `datasets`, `tqdm`, `mwparserfromhell`.

---

## Statistics File

`merge_all_stats.json` contains:
- Per-source document counts and token estimates
- Actual general ratio achieved
- Random seed and elapsed time
- File paths for all sources and outputs
