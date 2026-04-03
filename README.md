# FoodmoleGPT

> A Food Science Domain Large Language Model

FoodmoleGPT is a domain-specific LLM for food science, built through **Continual Pre-Training (CPT)** and **Supervised Fine-Tuning (SFT)** on open-source base models (Qwen3-8B-Base, LLaMA 3.1 8B).

## Project Structure

```
FoodmoleGPT/
├── CPT_dataset/          # Continual Pre-Training corpus (~3.1B tokens)
│   ├── essay/            # Food science papers (PubMed + OpenAlex)
│   ├── book/             # Wikipedia food articles
│   ├── general/          # FineWeb general corpus (catastrophic-forgetting replay)
│   ├── total/            # Final merged corpus & statistics
│   └── merge_all_cpt.py
├── SFT_dataset/          # Supervised Fine-Tuning data
│   ├── Claude/           # SFT data generated via Claude API
│   ├── Gemini/           # SFT data generated via Gemini API
│   ├── general/          # General-domain SFT data
│   └── final/            # Merged & deduplicated SFT dataset
├── RAG/                  # Retrieval-Augmented Generation knowledge base
│   ├── fda/              # FDA food safety regulations
│   ├── efsa/             # EFSA (EU) food safety documents
│   ├── sfa/              # SFA (Singapore) food standards
│   └── fda_guidance/     # FDA guidance documents (265 docs)
├── LLM_BO/               # LLM-guided Bayesian Optimization for hyperparameters
│   ├── bo/               # BO core algorithms
│   ├── llm_priors/       # LLM-based prior initialization
│   ├── eval/             # Evaluation & plotting
│   └── results/          # Experiment results & figures
└── TRAINING_REPORT.md    # Ablation study training report
```

## CPT Corpus Composition

| Source | Documents | Tokens | Share |
|--------|-----------|--------|-------|
| Food science full-text papers (PubMed + OpenAlex) | 253,569 | ~2,190M | 70.0% |
| Paper abstracts (OpenAlex) | 433,362 | ~180M | 5.8% |
| Wikipedia food articles | 24,479 | ~19M | 0.6% |
| FineWeb general replay | 1,006,172 | ~737M | 23.6% |
| **Total** | **1,717,582** | **~3.1B** | **100%** |

Token counts estimated via tiktoken cl100k_base with stratified sampling (500 global + 300 per-source samples).

## Training Strategy

Ablation study: 4 conditions x 2 base models = 8 experiments.

| Condition | Strategy | Description |
|-----------|----------|-------------|
| A | Base | No training — baseline |
| B | SFT-Only | Instruction tuning only |
| C | CPT-Only | Domain pre-training only |
| D | CPT + SFT | Full pipeline (domain pre-training then instruction tuning) |

Base models: **Qwen3-8B-Base** and **LLaMA 3.1 8B**. See [TRAINING_REPORT.md](TRAINING_REPORT.md) for results.

## Data Pipeline

### CPT Sources
- **PubMed Central**: Full-text open-access papers via food-science MeSH queries + keyword expansion, XML extraction, quality filtering, MinHash near-deduplication
- **OpenAlex API**: Paper abstracts with DOI-level dedup against full-text set
- **Wikipedia**: Three-tier keyword filter (Safe / Ambiguous / Text-only) with regex word-boundary matching
- **FineWeb**: Systematic sampling (1/50) for general-domain replay (~25% token budget)

### SFT Generation
- **Claude API** and **Gemini API**: Domain Q&A pairs generated from food science paper abstracts
- Domain relevance filtering + deduplication for quality control

### RAG Knowledge Base
- FDA food safety guidance (265 documents), FSMA, HACCP, CGMP regulations
- EFSA opinions and scientific guidelines
- SFA (Singapore Food Agency) standards

## Reproducibility

```bash
# 1. Build CPT corpus
cd CPT_dataset/book    && python download_wiki_food.py       # Wikipedia food articles
cd CPT_dataset/general && python download_fineweb2.py        # FineWeb general corpus
cd CPT_dataset         && python merge_all_cpt.py --general-ratio 0.25 --seed 42

# 2. Generate SFT data (requires API keys in .env files)
cd SFT_dataset/Gemini  && python generate_sft.py
cd SFT_dataset/Gemini  && python merge_and_dedup.py
```

**Prerequisites**: Python 3.10+, `datasets`, `tqdm`, `mwparserfromhell`, `tiktoken`, `google-generativeai`, `anthropic`.

## Note

Data files (`.jsonl`, `.xml`, etc.) are excluded from this repository due to size (~82 GB total). Only scripts, documentation, and small metadata files are tracked. To obtain the full dataset, run the reproducibility steps above.
