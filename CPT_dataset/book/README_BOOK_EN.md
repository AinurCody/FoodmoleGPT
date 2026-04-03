# FoodmoleGPT — Wikipedia Food & Adjacent Domain Corpus

## Overview

| Item | Value |
|------|-------|
| **Source** | English Wikipedia (2023-11-01 snapshot via HuggingFace) |
| **Dataset** | `wikimedia/wikipedia`, config `20231101.en` |
| **Filter strategy** | Title keyword matching + opening-paragraph keyword matching |
| **Target tokens** | ~600–800M |
| **Output format** | `{"text": "Title: ...\nSource: Wikipedia\n\n..."}` |
| **Purpose** | Textbook-style knowledge for food science CPT |

---

## Domain Coverage

The filter covers **food science core + adjacent domains**:

| Domain | Examples |
|--------|----------|
| Food science | Food safety, food chemistry, food processing, food technology |
| Nutrition | Vitamins, minerals, dietary supplements, macronutrients |
| Agriculture | Crop science, horticulture, aquaculture, animal husbandry |
| Food microbiology | Fermentation, probiotics, foodborne pathogens |
| Biochemistry overlap | Enzymes, proteins, lipids, carbohydrates, amino acids |
| Food products | Dairy, meat, seafood, grains, fruits, vegetables, spices, beverages |
| Cooking & cuisine | Culinary techniques, regional cuisines |

---

## Reproduction Steps

### Prerequisites

```bash
conda activate nus_study
pip install datasets mwparserfromhell tqdm
```

### Run

```bash
cd /Users/cody/Workspace/FoodmoleGPT/CPT_dataset/book

# Default: target ~800M tokens
python download_wiki_food.py

# Or specify a custom target
python download_wiki_food.py --max-tokens 600000000
```

### Output files

```
book/
├── README_BOOK_EN.md
├── README_BOOK_ZH.md
├── download_wiki_food.py
└── data/
    ├── wiki_food_raw.jsonl       # Raw filtered articles with metadata
    ├── wiki_food_cpt.jsonl       # CPT-ready format (for training)
    └── filter_stats.json         # Filtering statistics
```

---

## How Filtering Works

1. **Title matching** (high precision): Article title is checked against ~120 food-related keywords (e.g., "food", "nutrition", "dairy", "fermentation", "agriculture")
2. **Text matching** (catch stragglers): First 500 characters checked against ~40 domain-specific phrases (e.g., "food science", "dietary intake", "shelf life")
3. **Exclusion filter**: Titles containing irrelevant terms (sports, films, music, etc.) are excluded
4. **Stub removal**: Articles shorter than 200 characters are skipped

---

## Token Estimation

Token count is estimated as `word_count × 1.3` (standard approximation for English text with a BPE tokenizer). For exact counts, use the target model's tokenizer after generation.
