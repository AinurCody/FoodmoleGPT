**English** | [中文](DATA_README_ZH.md)

---

# FoodmoleGPT — PMC Food Science Corpus Data Documentation

## 1. Data Overview

| Metric | Value |
|------|------|
| **Round 1** — Initial Valid Articles | **105,159** (Valid) + 1,503 (Skipped) |
| **Round 1** — Kept After Post-filter | **93,657** |
| **Round 2 (Expansion)** — New Valid Articles | **81,401** (Valid) + 1,224 (Skipped) |
| **Round 2 (Expansion)** — Kept After Post-filter | **77,103** |
| **Merged Total** (before cleaning) | **170,760** |
| **Round 3 (Quality Cleaning)** — Removed | 3,516 (Hip Surgery 661 + text <1K 173 + no food anchor 2,682) |
| **Final Total** | **167,244** |
| Raw XML (Round 1 + 2) | 106,662 + 82,625 = **189,287** files, ~26 GB |
| Final JSONL Training Data | **6.51 GB** (`food_science_corpus.keep.jsonl`) |
| Final Estimated Tokens | **~1.6 billion tokens** |
| Final Average per Article | ~36,800 characters |
| Language | 99.92% English, 0.08% Chinese |
| Round 1 Collection Date | February 10, 2026 |
| Round 2 Expansion Date | March 5, 2026 |
| Round 3 Cleaning Date | March 5, 2026 |

---

## 2. Data Source

### 2.1 Source Database

**PubMed Central (PMC)** — A free full-text archive of biomedical and life sciences journal literature at the U.S. National Institutes of Health's National Library of Medicine (NIH/NLM).

- Website: https://www.ncbi.nlm.nih.gov/pmc/
- Data Subset: **PMC Open Access Subset**
- License: Articles are open access, allowing text mining and academic research use.
- Source File List: `oa_file_list.csv` (Index of all open access articles downloaded from NCBI FTP)

### 2.2 API Interface

Used NCBI **Entrez E-utilities API** to fetch full-text XML:
- Interface: `Entrez.efetch(db="pmc", rettype="xml")`
- Authentication: Using NCBI API Key (10 requests/second)
- Tool Identifier: `FoodmoleGPT-Downloader`

---

## 3. Filtering and Screening

### 3.1 Screening Strategy

Adopted a **Keyword Matching** approach, performing case-insensitive keyword matching on the `Article Citation` (including title and journal name) for each article in `oa_file_list.csv`.

### 3.2 Screening Keywords (6 Categories)

```
Core Food Science:
  food, nutrition, diet, dietary, nutrient

Food Categories:
  dairy, meat, beef, pork, poultry, chicken, seafood, fish,
  vegetable, fruit, cereal, grain, beverage, milk, cheese,
  yogurt, bread, rice

Food Science Topics:
  ferment, flavor, flavour, sensory, taste, cooking, culinary, recipe

Food Safety & Quality:
  foodborne, food safety, food contamination, preserv, shelf life, spoilage

Food Processing & Agriculture:
  food processing, food technology, food packaging, agricult, crop,
  harvest, livestock

Specific Compounds & Journals:
  antioxidant, phenolic, polyphenol, vitamin, fatty acid, protein,
  carbohydrate, fiber, fibre, j food, food res, food chem, food sci,
  meat sci, dairy sci, cereal, appetite, nutrients, foods, beverages
```

### 3.3 Initial Screening Results

- Total Scanned: **7,583,353** PMC Open Access articles
- Matched Articles: **106,659** (Hit rate 1.4%)
- Valid Articles: **105,159** (After preprocessing and excluding articles with short body text)

### 3.4 Post-filter Results (Topic Denoising)

To reduce medically strong but food-weak samples, a second-pass filter was added:

- Cancer triggers: `cancer/tumor/oncology/neoplasm/carcinoma/malignant`
- Food anchor scope: title + abstract + keywords
- Drop rule: cancer trigger hit and no food anchor -> drop

Results:

- Post-filter input: **105,159**
- Kept: **93,657**
- Dropped: **11,502** (10.94% of all valid docs)
- Final default training path: `data/processed/filtered/food_science_corpus.keep.jsonl`

---

## 4. Download Method

### 4.1 Download Workflow

```
oa_file_list.csv (NCBI FTP)
    │
    ▼ Keyword Matching Screening
106,659 Food Science Article IDs
    │
    ▼ Entrez efetch API (XML Format)
106,662 XML Files (15 GB)
```

### 4.2 Technical Details

| Configuration | Value |
|--------|-----|
| Downloader Tool | `pmc_downloader_xml.py` (Python + Biopython) |
| Concurrency | ThreadPoolExecutor (8 threads) |
| Rate Limit | 9 requests/second (NCBI limit 10 req/s) |
| Retry Mechanism | Max 3 retries per article |
| Resume Capability | ✅ Supported (Based on progress file + disk file detection) |
| Failed Downloads | **0** |

### 4.3 Download Format

Downloaded in **JATS XML** (Journal Article Tag Suite) format, which is the standard structured full-text format for PMC, containing:

- Article Metadata (Title, Authors, Journal, DOI)
- Structured Abstract
- Body Sections (Introduction, Methods, Results, Discussion, Conclusion)
- Figure/Table Captions
- Keywords
- References

> **Note**: XML contains only text content and image reference paths, not binary image data.

---

## 5. Preprocessing Method

### 5.1 Preprocessing Workflow

```
106,662 XML Files
    │
    ▼ preprocess_xml.py (Multi-process parsing)
    │
    ├─▶ Extraction: Title, Abstract, Keywords, Body, Figure/Table Captions
    ├─▶ Cleaning: Remove citation markers [1][2], fix spacing, remove invalid chars
    ├─▶ Filtering: Skip articles with body text < 500 chars (1,503 articles)
    └─▶ Skip Irrelevant Sections: Acknowledgements, Conflicts of Interest, Author Contributions, Ethics Statements, etc.
    │
    ▼
data/processed/intermediate/food_science_corpus.raw.jsonl (intermediate)
    │
    ▼ post_filter_corpus.py (second-pass screening)
    │
    ├─▶ keep: food_science_corpus.keep.jsonl
    ├─▶ drop: food_science_corpus.drop.jsonl
    └─▶ stats: post_filter_stats.json + post_filter_samples.json
```

### 5.2 Skipped Section Types

The following sections were determined to be irrelevant to domain knowledge and were filtered out during extraction:

```
competing interests, conflict of interest, conflicts of interest,
credit authorship contribution statement, author contributions,
funding, acknowledgements, acknowledgments,
data availability, supplementary material, supplementary data,
abbreviations, ethics statement, ethical approval
```

### 5.3 Extracted Content

The following information is extracted for each article:

```
Title: [Article Title]

Abstract: [Full Abstract]

Keywords: [List of Keywords]

Introduction
[Introduction Text...]

Materials and Methods
[Methods Text...]

Results and Discussion
[Results and Discussion Text...]

Conclusion
[Conclusion Text...]

Figure Descriptions:
  Figure 1: [Figure caption, usually containing quantitative summary of results]
  Figure 2: [...]

Table Descriptions:
  Table 1: [Table caption]
```

### 5.4 Processing Performance

| Metric | Value |
|------|-----|
| Processing Tool | `preprocess_xml.py` (Python multiprocessing) |
| Parallel Processes | 9 (CPU cores - 1) |
| Processing Speed | ~1,195 articles/sec |
| Total Time | **1 min 29 sec** |

---

## 6. Output File Description (Post-filtered)

### 6.1 `data/processed/filtered/food_science_corpus.keep.jsonl` (6.51 GB)

Final training/retrieval dataset. Each line is a JSON object:

```json
{
  "pmcid": "PMC10000368",
  "title": "Gas Chromatography...",
  "abstract": "Patients with galactosemia...",
  "keywords": ["galactosemia", "galactose content", ...],
  "journal": "Journal of Food Composition and Analysis",
  "text": "Title: Gas Chromatography...\n\nAbstract: ...\n\nIntroduction\n..."
}
```

**Use Cases**: SFT, RAG, domain continual pre-training

### 6.2 `data/processed/filtered/food_science_corpus.drop.jsonl` (449 MB)

Dropped set for audit/review. Rule: cancer-related and no food anchors.

### 6.3 `data/processed/filtered/post_filter_stats.json`

Post-filter summary metrics (keep/drop counts, ratios, bucketed stats).

### 6.4 `data/processed/filtered/post_filter_samples.json`

Reservoir-sampled manual review examples across 3 buckets.

---

## 7. Data Quality Sampling

Quality check results from 3 randomly selected articles:

| No. | PMCID | Title | Text Length |
|------|-------|------|---------|
| 1 | PMC10201332 | COVID-19 mobility restrictions... associated with higher retail food prices | 51,832 chars |
| 2 | PMC10935437 | Reply to Curtis, L. Comment on "Magner et al. Sulforaphane Treatment..." | 3,373 chars |
| 3 | PMC8614712 | Polyphenols from Blumea laciniata Extended the Lifespan... | 31,191 chars |

---

## 8. File Structure

```
PubMed/
├── config.py                         # NCBI API Configuration
├── pmc_downloader_xml.py             # Round 1 Downloader (keyword match on oa_file_list.csv)
├── pmc_esearch_collector.py          # Round 2 PMCID Collector (10 MeSH strategies)
├── pmc_expansion_downloader.py       # Round 2 XML Downloader
├── merge_expansion.py                # Merge expansion into main corpus
├── preprocess_xml.py                 # Preprocessing Script (XML → JSONL)
├── post_filter_corpus.py             # Post-filter Script (Topic Denoising)
├── food_relevance_filter.py          # Round 3 Precision Food Relevance Filter (225 anchors)
├── PMC_Search_Guide.md               # Advisor's MeSH search strategies
├── requirements.txt                  # Python Dependencies
├── DATA_README_EN.md                 # This Document (English)
├── DATA_README_ZH.md                 # This Document (Chinese)
└── data/
    ├── xml/                          # Round 1 Raw XML (106,662 articles, ~15 GB)
    ├── xml_expansion/                # Round 2 Raw XML (82,625 articles, ~11 GB)
    ├── expansion_pmcids.json         # Round 2 collected PMCIDs (82,632)
    ├── processed/
    │   ├── intermediate/             # Round 1 preprocess intermediate
    │   ├── filtered/                 # Final Cleaned Training Data
    │   │   ├── food_science_corpus.keep.jsonl  # Main corpus (6.51 GB, 167,244 articles)
    │   │   ├── food_science_corpus.drop.jsonl  # Dropped set
    │   │   ├── precision_filter_flagged.jsonl  # Round 3 removed articles log
    │   │   ├── merge_expansion_stats.json      # Merge statistics
    │   │   └── post_filter_stats.json          # Filter statistics
    │   └── expansion/                # Round 2 preprocess outputs
    │       ├── intermediate/
    │       └── filtered/
    ├── food_articles_xml.json         # Round 1 Screened Article IDs
    ├── download_xml_progress.json     # Round 1 Download Progress
    ├── expansion_download_progress.json  # Round 2 Download Progress
    └── logs/
```

---

## 9. Reproduction Steps

### Round 1 (Keyword-based)

```bash
conda activate foodmole
pip install -r requirements.txt

# 1. Download oa_file_list.csv
wget https://ftp.ncbi.nlm.nih.gov/pub/pmc/oa_file_list.csv

# 2. Configure config.py (Set Email and API Key)

# 3. Download XML
python pmc_downloader_xml.py

# 4. Preprocess
python preprocess_xml.py

# 5. Post-filter
python post_filter_corpus.py \
  --input data/processed/intermediate/food_science_corpus.raw.jsonl \
  --out-dir data/processed/filtered
```

### Round 2 (MeSH Expansion)

```bash
# 1. Collect new PMCIDs via 10 MeSH search strategies
python pmc_esearch_collector.py          # outputs data/expansion_pmcids.json

# 2. Download expansion XMLs
python pmc_expansion_downloader.py       # outputs to data/xml_expansion/

# 3. Preprocess expansion
python preprocess_xml.py -i data/xml_expansion -o data/processed/expansion -f jsonl

# 4. Post-filter expansion
python post_filter_corpus.py \
  --input data/processed/expansion/intermediate/food_science_corpus.raw.jsonl \
  --out-dir data/processed/expansion/filtered

# 5. Merge into main corpus
python merge_expansion.py
```

### Round 3 (Quality Cleaning)

```bash
# Precision food relevance filter (removes non-food articles)
python food_relevance_filter.py --execute
```

Default dataset path for training/RAG:

`data/processed/filtered/food_science_corpus.keep.jsonl`

---

## 10. Round 2 Expansion Details (March 5, 2026)

### 10.1 Search Strategy

Used **NCBI E-utilities `esearch`** with 10 MeSH-based search strategies (see `PMC_Search_Guide.md`) instead of keyword matching on `oa_file_list.csv`. Each strategy used `AND open access[Filter]` to restrict to OA articles.

### 10.2 Strategy Results

| # | Strategy | Total Hits | New Unique |
|---|----------|-----------|------------|
| 1 | Food Chemistry | 26,913 | 20,833 |
| 2 | Food Safety & Toxicology | 16,709 | 14,116 |
| 3 | Food Nutrition & Health | 35,611 | 25,624 |
| 4 | Food Flavor & Sensory Science | 7,007 | 4,605 |
| 5 | Food Processing & Engineering | 7,526 | 4,940 |
| 6 | Food Microbiology & Biotechnology | 19,188 | 5,554 |
| 7 | Food Informatics & AI | 2,841 | 2,019 |
| 8 | Food Education & Public Engagement | 358 | 260 |
| 9 | Sustainable Food Systems | 5,361 | 4,139 |
| 10 | Alternative Proteins & Future Foods | 1,149 | 542 |
| | **Total (cross-strategy dedup)** | | **82,632** |

### 10.3 Processing Results

| Step | Count |
|------|-------|
| New PMCIDs collected | 82,632 |
| XMLs downloaded | 82,625 (99.99%) |
| Valid after preprocessing | 81,401 (skipped 1,224 short/invalid) |
| Kept after post-filter | 77,103 (dropped 4,298 = 5.28%) |
| Duplicates with Round 1 | 0 |
| **Added to main corpus** | **77,103** |

---

## 11. Round 3 Quality Validation & Cleaning (March 5, 2026)

### 11.1 Quality Validation

Ran comprehensive quality analysis on the merged 170,760-article corpus:

**Journal Distribution**: 3,737 unique journals. Top 5 are food science journals (Nutrients 19.85%, Foods 13.54%, Antioxidants 4.74%). Identified **J Hip Preservation Surgery** (661 articles) as a systematic leak — a pure orthopedics journal likely matched via the term "hip" (from "rosehip").

**Text Length Distribution**: Median 34,273 chars, 81.78% in the 10K–50K range. Only 0.10% articles < 1K chars (editorial/letter) and 0.04% > 200K chars.

**Keyword Frequency**: Top keywords are food-relevant (polyphenols, nutrition, probiotics, gut microbiota). Some medical keywords present (cancer 0.56%, cardiovascular 0.53%) but mostly in food–health crossover contexts.

**Language Distribution**: 99.92% English, 0.08% Chinese (132 articles).

### 11.2 Cleaning Steps

| Step | Removed | Remaining |
|------|---------|----------|
| Start (merged corpus) | — | 170,760 |
| Remove J Hip Preservation Surgery | 661 | 170,099 |
| Remove text < 1K chars | 173 | 169,926 |
| Precision food relevance filter (225 anchors) | 2,682 | **167,244** |

### 11.3 Precision Food Relevance Filter

Script: `food_relevance_filter.py`

Checks each article's **title + abstract + keywords** for food-related anchor patterns (225 regex patterns). Articles with no food anchor and no food-related journal name are flagged for removal.

Anchor categories include:
- Core food terms (food, diet, nutrition, meal, eating)
- Dietary interventions (supplement, intake, consumption, bioavailability, calorie)
- Food categories (dairy, meat, seafood, fruit, vegetable, beverage, etc.)
- Food science topics (fermentation, flavor, shelf life, food safety)
- Agriculture (crop, farming, livestock, aquaculture)
- Food compounds (antioxidant, polyphenol, vitamin, fatty acid, probiotic)
- Broader nutrition (obesity, BMI, gut microbiota, glycemic, satiety, anemia)

Removed articles were predominantly from: Nutrients (305), Protein & Cell (260), Scientific Reports (197), Particle & Fibre Toxicology (124).

### 11.4 Final Corpus

| Metric | Value |
|--------|-------|
| **Total articles** | **167,244** |
| Corpus size | 6.51 GB |
| Estimated tokens | ~1.6 billion |
| Language | 99.92% English |
| Manual review (100 random samples) | ✅ Approved |
