"""
FoodmoleGPT Round 2 - Data Cleaning Pipeline
==============================================
Adapted from clean_data.py for Round 2 data.
Adds cross-round DOI dedup against Round 1 master_cleaned.csv.

Usage:
    conda activate foodmole
    python src/clean_data_r2.py
"""

import re
import sys
import unicodedata
from pathlib import Path
from datetime import datetime

import pandas as pd

if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# =============================================================================
# PATHS
# =============================================================================

INPUT_FILE = Path("D:/FoodmoleGPT/data/raw/openalex_r2/master_r2_openalex.csv")
OUTPUT_DIR = Path("D:/FoodmoleGPT/data/cleaned_r2")
R1_CLEANED = Path("D:/FoodmoleGPT/data/cleaned/master_cleaned.csv")

# =============================================================================
# TEXT CLEANING FUNCTIONS (identical to Round 1)
# =============================================================================


def remove_citation_markers(text: str) -> str:
    if not isinstance(text, str):
        return text
    text = re.sub(r"\[\s*\d+(?:\s*[,\-–]\s*\d+)*\s*\]", "", text)
    text = re.sub(r"\(\s*\d{1,3}(?:\s*[,\-–]\s*\d{1,3})*\s*\)", "", text)
    return text


def remove_html_tags(text: str) -> str:
    if not isinstance(text, str):
        return text
    return re.sub(r"<[^>]+>", "", text)


def normalize_unicode(text: str) -> str:
    if not isinstance(text, str):
        return text
    return unicodedata.normalize("NFKC", text)


def fix_whitespace(text: str) -> str:
    if not isinstance(text, str):
        return text
    text = re.sub(r"[\t\r\n]+", " ", text)
    text = re.sub(r" {2,}", " ", text)
    text = re.sub(r"\s+([.,;:!?)])", r"\1", text)
    text = re.sub(r"([.,;:!?])([A-Za-z])", r"\1 \2", text)
    return text.strip()


def remove_control_chars(text: str) -> str:
    if not isinstance(text, str):
        return text
    return "".join(c for c in text if unicodedata.category(c)[0] != "C" or c in "\n\t")


def clean_text(text: str) -> str:
    if not isinstance(text, str) or not text.strip():
        return text
    text = remove_html_tags(text)
    text = remove_citation_markers(text)
    text = normalize_unicode(text)
    text = remove_control_chars(text)
    text = fix_whitespace(text)
    return text if text.strip() else None


def normalize_title_for_dedup(title: str) -> str:
    if not isinstance(title, str):
        return ""
    t = title.lower().strip()
    t = re.sub(r"[^a-z0-9\s]", "", t)
    t = re.sub(r"\s+", " ", t)
    return t


# =============================================================================
# MAIN PIPELINE
# =============================================================================


def run_cleaning():
    start = datetime.now()
    print("=" * 70)
    print("🧹 FoodmoleGPT Round 2 - Data Cleaning Pipeline")
    print("=" * 70)
    print(f"   Input:  {INPUT_FILE}")
    print(f"   Output: {OUTPUT_DIR}")
    print(f"   Start:  {start.strftime('%Y-%m-%d %H:%M:%S')}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Load data
    print("\n📂 Loading Round 2 data...")
    df = pd.read_csv(INPUT_FILE)
    total_raw = len(df)
    print(f"   Loaded: {total_raw:,} rows")

    report = []
    report.append(f"FoodmoleGPT Round 2 Data Cleaning Report")
    report.append(f"Generated: {start.strftime('%Y-%m-%d %H:%M:%S')}")
    report.append(f"Input: {INPUT_FILE}")
    report.append(f"Raw records: {total_raw:,}")
    report.append("")

    # =========================================================================
    # STEP 0: CROSS-ROUND DOI DEDUP (NEW in Round 2)
    # =========================================================================
    print("\n" + "=" * 70)
    print("🔄 STEP 0: Cross-Round DOI Deduplication")

    if R1_CLEANED.exists():
        r1_df = pd.read_csv(R1_CLEANED, usecols=["doi"], dtype=str)
        r1_dois = set(r1_df["doi"].dropna().str.strip().str.lower())
        print(f"   Round 1 DOIs loaded: {len(r1_dois):,}")

        before = len(df)
        df["_doi_lower"] = df["doi"].str.strip().str.lower()
        df = df[~df["_doi_lower"].isin(r1_dois)].copy()
        df = df.drop(columns=["_doi_lower"])
        r1_dup_count = before - len(df)
        print(f"   R1 duplicates removed: {r1_dup_count:,}")
        report.append(f"[Step 0] Cross-round DOI dedup: {r1_dup_count:,} removed")
    else:
        print("   ⚠️  Round 1 cleaned data not found, skipping cross-round dedup")
        report.append("[Step 0] Cross-round dedup skipped (R1 data not found)")

    report.append("")

    # =========================================================================
    # STEP 1: BASIC FILTERING
    # =========================================================================
    print("\n" + "=" * 70)
    print("📋 STEP 1: Basic Filtering")

    # 1a. Remove rows with no title
    no_title = df["title"].isna().sum()
    df = df[df["title"].notna()].copy()
    print(f"   No title removed: {no_title:,}")
    report.append(f"[Step 1a] No title removed: {no_title:,}")

    # 1b. Language filter
    if "language" in df.columns:
        non_en = df[df["language"].notna() & (df["language"] != "en")]
        non_en_count = len(non_en)
        df = df[(df["language"] == "en") | (df["language"].isna())].copy()
        print(f"   Non-English removed: {non_en_count:,}")
        report.append(f"[Step 1b] Non-English removed: {non_en_count:,}")
    else:
        non_en_count = 0

    # 1c. DOI dedup within R2
    before = len(df)
    doi_df = df[df["doi"].notna()]
    doi_dups = doi_df[doi_df.duplicated("doi", keep="first")]
    df = df.drop(doi_dups.index)
    doi_dup_count = len(doi_dups)
    print(f"   DOI duplicates removed: {doi_dup_count:,}")
    report.append(f"[Step 1c] DOI duplicates (within R2) removed: {doi_dup_count:,}")

    # 1d. Title dedup
    df["_norm_title"] = df["title"].apply(normalize_title_for_dedup)
    before = len(df)
    df = df.drop_duplicates(subset=["_norm_title"], keep="first")
    title_dup_count = before - len(df)
    df = df.drop(columns=["_norm_title"])
    print(f"   Title duplicates removed: {title_dup_count:,}")
    report.append(f"[Step 1d] Title duplicates removed: {title_dup_count:,}")

    after_step1 = len(df)
    print(f"   ➤ After Step 1: {after_step1:,}")
    report.append(f"After Step 1: {after_step1:,}")
    report.append("")

    # =========================================================================
    # STEP 2: TEXT CLEANING
    # =========================================================================
    print("\n" + "=" * 70)
    print("✨ STEP 2: Text Cleaning")

    print("   Cleaning titles...", flush=True)
    df["title"] = df["title"].apply(clean_text)
    print("   Cleaning abstracts...", flush=True)
    df["abstract"] = df["abstract"].apply(clean_text)
    print("   Cleaning keywords...", flush=True)
    if "keywords" in df.columns:
        df["keywords"] = df["keywords"].apply(clean_text)
    print("   ✅ Text cleaning complete")
    report.append("[Step 2] Text cleaning applied")
    report.append("")

    # =========================================================================
    # STEP 3: ABSTRACT QUALITY
    # =========================================================================
    print("\n" + "=" * 70)
    print("📊 STEP 3: Abstract Quality Filtering")

    df["has_abstract"] = df["abstract"].notna() & (df["abstract"].str.strip() != "")
    df["abstract_char_count"] = df["abstract"].str.len().fillna(0).astype(int)
    df["abstract_word_count"] = df["abstract"].str.split().str.len().fillna(0).astype(int)

    def label_abstract_quality(row):
        if not row["has_abstract"]:
            return "none"
        if row["abstract_char_count"] < 50:
            return "corrupted"
        if row["abstract_char_count"] < 200:
            return "short"
        return "good"

    df["abstract_quality"] = df.apply(label_abstract_quality, axis=1)

    corrupted = (df["abstract_quality"] == "corrupted").sum()
    df.loc[df["abstract_quality"] == "corrupted", "abstract"] = None
    df.loc[df["abstract_quality"] == "corrupted", "has_abstract"] = False
    df.loc[df["abstract_quality"] == "corrupted", "abstract_quality"] = "none"
    print(f"   Corrupted abstracts (<50 chars) nullified: {corrupted:,}")

    quality_counts = df["abstract_quality"].value_counts()
    for q, n in quality_counts.items():
        print(f"   {q:12}: {n:>10,}")
    report.append(f"[Step 3] Abstract quality: {dict(quality_counts)}")
    report.append("")

    # =========================================================================
    # STEP 4: FINAL OUTPUT
    # =========================================================================
    print("\n" + "=" * 70)
    print("💾 STEP 4: Saving Output")

    df["tier"] = df["cited_by_count"].apply(
        lambda x: 1 if x >= 50 else (2 if x >= 10 else 3)
    )
    df["tier_label"] = df["tier"].map({1: "high_impact", 2: "medium_impact", 3: "standard"})

    df = df.sort_values("cited_by_count", ascending=False).reset_index(drop=True)

    full_file = OUTPUT_DIR / "master_cleaned_r2.csv"
    df.to_csv(full_file, index=False, encoding="utf-8-sig")
    print(f"   📁 master_cleaned_r2.csv: {len(df):,} rows ({full_file.stat().st_size/1024/1024:.1f} MB)")

    df_abs = df[df["has_abstract"]].copy()
    abs_file = OUTPUT_DIR / "master_with_abstract_r2.csv"
    df_abs.to_csv(abs_file, index=False, encoding="utf-8-sig")
    print(f"   📁 master_with_abstract_r2.csv: {len(df_abs):,} rows")

    # =========================================================================
    # FINAL REPORT
    # =========================================================================
    print("\n" + "=" * 70)
    print("📊 FINAL STATISTICS")
    print("=" * 70)

    stats = [
        ("Raw input", total_raw),
        ("After cleaning", len(df)),
        ("Removed total", total_raw - len(df)),
        ("", ""),
        ("With abstract", df["has_abstract"].sum()),
        ("Without abstract", (~df["has_abstract"]).sum()),
    ]

    for label, val in stats:
        if label == "":
            print()
        else:
            line = f"   {label:30} {val:>12,}" if isinstance(val, int) else f"   {label:30} {val:>12}"
            print(line)
            report.append(line)

    elapsed = datetime.now() - start
    print(f"\n   Elapsed: {elapsed}")

    report_file = OUTPUT_DIR / "cleaning_report_r2.txt"
    report.append(f"\nElapsed: {elapsed}")
    with open(report_file, "w", encoding="utf-8") as f:
        f.write("\n".join(report))

    print("\n" + "=" * 70)
    print("✅ Round 2 data cleaning complete!")
    print(f"   Full dataset: {full_file}")
    print("=" * 70)


if __name__ == "__main__":
    run_cleaning()
