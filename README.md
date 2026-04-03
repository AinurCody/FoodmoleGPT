# FoodmoleGPT

Food science domain LLM via continual pre-training, supervised fine-tuning, and retrieval-augmented generation. Systematic ablation study comparing CPT, SFT, RAG, and their combinations on two base models (Qwen3-8B and Llama3.1-8B).

## Key Results (CPT-MCQ, 218 food science questions)

| Method | Qwen3-8B | Llama3.1-8B |
|--------|----------|-------------|
| Base | 76.6% | 69.3% |
| Base + RAG | 80.7% | 73.9% |
| SFT-Only | 83.5% | 28.9% |
| CPT + SFT | 86.2% | 62.8% |
| SFT + RAG | 89.0% | 65.1% |
| **CPT + SFT + RAG** | **92.2%** | 72.5% |
| Claude Sonnet 4.6 (baseline) | 97.7% | — |

**Takeaway**: Each component (CPT, SFT, RAG) adds independent value. The full CPT+SFT+RAG pipeline closes the gap to within 5.5pp of a frontier commercial model, while MMLU degradation is only 1.5pp.

## Pipeline

```
                    ┌─────────────┐
                    │  CPT Corpus │  1.72M docs, 3.12B tokens
                    │  (75% food  │  (OpenAlex + PubMed/PMC + FineWeb)
                    │  25% general)│
                    └──────┬──────┘
                           │
              ┌────────────▼────────────┐
              │  Continual Pre-Training │  LoRA r=64, lr=5e-5, 1 epoch
              │  (LLaMA-Factory)        │
              └────────────┬────────────┘
                           │
              ┌────────────▼────────────┐
              │  Supervised Fine-Tuning │  122K instruction pairs
              │  (LLaMA-Factory, LoRA)  │  LoRA r=64, lr=2e-4, 3 epochs
              └────────────┬────────────┘
                           │
    ┌──────────────────────▼──────────────────────┐
    │           RAG (Retrieval-Augmented)          │
    │  BGE-base-en-v1.5 → FAISS (5.5M vectors)   │
    │  Paragraph-aware chunking, 512 tok, 128 overlap │
    └─────────────────────────────────────────────┘
```

## Project Structure

```
FoodmoleGPT/
├── configs/              # LLaMA-Factory YAML training configs
├── scripts/
│   ├── training/         # PBS job scripts for CPT & SFT
│   ├── eval/             # MCQ evaluation scripts
│   ├── rag/              # RAG index building
│   └── setup/            # Environment & model download
├── analysis/             # Visualization notebooks
├── results/              # Evaluation results (not included, see below)
└── docs/                 # Experiment plan
```

## Training Details

| Stage | Data | Qwen3-8B | Llama3.1-8B |
|-------|------|----------|-------------|
| CPT | 3.12B tokens (75% food science + 25% general) | ~8h, 2×H200 | ~7h, 2×H200 |
| SFT | 122,717 food science instruction pairs | ~3h, 2×H200 | ~4h, 2×H200 |
| RAG Index | 1.72M docs → 5.5M chunks → FAISS | 2h, 1×H200 | — |

## Evaluation

Three benchmarks:
- **CPT-MCQ** (218 questions): Gemini-generated from CPT corpus, tests domain knowledge
- **Canvas MCQ** (170 questions): University food science course, tests undergrad-level knowledge
- **MMLU subset** (204 questions): 6 general subjects, tests catastrophic forgetting

Settings: 0-shot, 5-shot, RAG (top-5 retrieval), and combinations.

## Data & Results

Training data, evaluation datasets, and result JSONs are not included in this repository:
- **CPT corpus**: Proprietary academic full-text from OpenAlex/PubMed
- **SFT data**: FoodEarth dataset (see [Zenodo](https://zenodo.org/records/14892842))
- **Evaluation results**: Contain proprietary exam questions; available upon request

## Environment

- **GPU**: NVIDIA H200 (143GB VRAM)
- **Framework**: [LLaMA-Factory](https://github.com/hiyouga/LLaMA-Factory) 0.9.5
- **Container**: Singularity (PyTorch 2.6, CUDA 13.1, Python 3.12)
- **Scheduler**: PBS on NUS Hopper HPC
- **Embedding**: BAAI/bge-base-en-v1.5
- **Vector Store**: FAISS IndexFlatIP
