**English** | [中文](DATA_README_ZH.md)

---

# FoodmoleGPT — PMC Food Science Corpus Data Documentation

## 1. Data Overview

| Metric | Value |
|------|------|
| Total Articles | **105,159** (Valid) + 1,503 (Skipped) |
| Raw XML | 106,662 files, ~15 GB |
| JSONL Training Data | 3.7 GB |
| TXT Training Data | 3.5 GB |
| Total Characters | 3.78 billion characters |
| Estimated Tokens | **~946 million tokens** |
| Average per Article | ~35,967 characters |
| Language | Primarily English |
| Data Collection Date | February 10, 2026 |

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

### 3.3 Screening Results

- Total Scanned: **7,583,353** PMC Open Access articles
- Matched Articles: **106,659** (Hit rate 1.4%)
- Valid Articles: **105,159** (After preprocessing and excluding articles with short body text)

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
food_science_corpus.jsonl + food_science_corpus.txt
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

## 6. Output File Description

### 6.1 `food_science_corpus.jsonl` (3.7 GB)

Each line is a JSON object containing the following fields:

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

**Use Cases**: Supervised Fine-tuning (SFT), RAG (Retrieval-Augmented Generation)

### 6.2 `food_science_corpus.txt` (3.5 GB)

Plain text format, with articles separated by `========================================`.

**Use Cases**: Continual Pre-training, Domain-adaptive Pre-training

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
├── pmc_downloader_xml.py             # Downloader Script (Multi-threaded + Resume Support)
├── preprocess_xml.py                 # Preprocessing Script (XML → JSONL/TXT)
├── requirements.txt                  # Python Dependencies
├── DATA_README.md                    # This Document
└── data/
    ├── xml/                          # Raw XML Files (106,662 articles, ~15 GB)
    │   ├── PMC10000368.xml
    │   ├── PMC10000371.xml
    │   └── ...
    ├── processed/                    # Processed Training Data
    │   ├── food_science_corpus.jsonl  # JSONL Format (3.7 GB)
    │   ├── food_science_corpus.txt    # TXT Format (3.5 GB)
    │   └── corpus_stats.json          # Corpus Statistics
    ├── food_articles_xml.json         # List of Screened Article IDs
    ├── download_xml_progress.json     # Download Progress Record
    └── logs/
        └── download_xml.log           # Download Logs
```

---

## 9. Reproduction Steps

```bash
# 1. Install Dependencies
conda activate foodmole
pip install -r requirements.txt

# 2. Download oa_file_list.csv (Need to fetch from NCBI FTP)
wget https://ftp.ncbi.nlm.nih.gov/pub/pmc/oa_file_list.csv

# 3. Configure config.py (Set Email and API Key)

# 4. Download XML
python pmc_downloader_xml.py

# 5. Preprocess
python preprocess_xml.py
```
