# FoodmoleGPT — FineWeb-2 General Domain Corpus

## Overview

| Item | Value |
|------|-------|
| **Source** | FineWeb (HuggingFaceFW) — high-quality English web corpus |
| **Dataset** | `HuggingFaceFW/fineweb` (English-only; FineWeb-2 is multilingual w/o English) |
| **Sampling** | Systematic sampling (1 in every N documents) |
| **Target tokens** | ~800M (≈20% of total CPT corpus) |
| **Output format** | `{"text": "..."}` |
| **Purpose** | General-domain "replay" corpus to prevent catastrophic forgetting during CPT |

---

## Why FineWeb?

- Extensively cleaned and deduplicated web corpus (15T+ tokens total)
- Quality filtering pipeline: URL filtering, language detection, perplexity filtering, deduplication
- Community-recognized as one of the highest-quality open English web corpora
- Streaming support — no need to download the full dataset

---

## Reproduction Steps

### Prerequisites

```bash
conda activate nus_study
pip install datasets tqdm
```

### Run

```bash
cd /Users/cody/Workspace/FoodmoleGPT/CPT_dataset/general

# Default: ~800M tokens, sample rate 1/50
python download_fineweb2.py

# Custom target and sample rate
python download_fineweb2.py --max-tokens 600000000 --sample-rate 100
```

### Output files

```
general/
├── README_GENERAL_EN.md
├── README_GENERAL_ZH.md
├── download_fineweb2.py
└── data/
    ├── fineweb2_general_cpt.jsonl    # CPT-ready format (for training)
    └── sample_stats.json             # Sampling statistics
```

---

## Sampling Strategy

- **Systematic sampling**: Keep every N-th document (default N=50)
- **Length filter**: Skip documents shorter than 500 chars or longer than 50,000 chars
- **No domain filter**: This is intentionally general-purpose to preserve broad knowledge

This approach gives a representative spread across FineWeb's diverse web content while keeping the corpus manageable.

---

## Token Estimation

Token count is estimated as `word_count × 1.3` (standard approximation for English text with a BPE tokenizer). For exact counts, use the target model's tokenizer after generation.
