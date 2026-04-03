"""
FoodmoleGPT - Data Cleaning Pipeline
=====================================
Cleans 1M+ food science papers collected from OpenAlex.

Pipeline:
  Step 1: Basic filtering (no title, language, dedup)
  Step 2: Text cleaning (citations, HTML, Unicode, whitespace)
  Step 3: Abstract quality filtering and labeling
  Step 4: Layered output (full + abstract-only)

Usage:
    conda activate foodmole
    python src/clean_data.py
"""

import re
import unicodedata
from pathlib import Path
from datetime import datetime

import pandas as pd

# =============================================================================
# PATHS
# =============================================================================

INPUT_FILE = Path("D:/FoodmoleGPT/data/raw/openalex_concepts/master_all_concepts.csv")
OUTPUT_DIR = Path("D:/FoodmoleGPT/data/cleaned")

# =============================================================================
# TEXT CLEANING FUNCTIONS
# =============================================================================


def remove_citation_markers(text: str) -> str:
    """Remove citation markers like [1], [2,3], [1-5], [1, 2], (1), (1,2)."""
    if not isinstance(text, str):
        return text
    # [1], [2,3], [1-5], [1, 2, 3], [1,2,3,4]
    text = re.sub(r"\[\s*\d+(?:\s*[,\-–]\s*\d+)*\s*\]", "", text)
    # (1), (1,2), (1-5) — only when clearly citations (short numbers)
    text = re.sub(r"\(\s*\d{1,3}(?:\s*[,\-–]\s*\d{1,3})*\s*\)", "", text)
    return text


def remove_html_tags(text: str) -> str:
    """Remove HTML/XML tags."""
    if not isinstance(text, str):
        return text
    return re.sub(r"<[^>]+>", "", text)


def normalize_unicode(text: str) -> str:
    """Normalize Unicode to NFKC form."""
    if not isinstance(text, str):
        return text
    return unicodedata.normalize("NFKC", text)


def fix_whitespace(text: str) -> str:
    """Collapse multiple whitespace, fix spacing issues."""
    if not isinstance(text, str):
        return text
    # Replace various whitespace chars with space
    text = re.sub(r"[\t\r\n]+", " ", text)
    # Collapse multiple spaces
    text = re.sub(r" {2,}", " ", text)
    # Fix space before punctuation
    text = re.sub(r"\s+([.,;:!?)])", r"\1", text)
    # Fix missing space after punctuation
    text = re.sub(r"([.,;:!?])([A-Za-z])", r"\1 \2", text)
    return text.strip()


def remove_control_chars(text: str) -> str:
    """Remove control characters (except newline/tab which are handled elsewhere)."""
    if not isinstance(text, str):
        return text
    return "".join(c for c in text if unicodedata.category(c)[0] != "C" or c in "\n\t")


def clean_text(text: str) -> str:
    """Apply full text cleaning pipeline to a string."""
    if not isinstance(text, str) or not text.strip():
        return text
    text = remove_html_tags(text)
    text = remove_citation_markers(text)
    text = normalize_unicode(text)
    text = remove_control_chars(text)
    text = fix_whitespace(text)
    return text if text.strip() else None


def normalize_title_for_dedup(title: str) -> str:
    """Normalize title for deduplication comparison."""
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
    print("🧹 FoodmoleGPT - Data Cleaning Pipeline")
    print("=" * 70)
    print(f"   Input:  {INPUT_FILE}")
    print(f"   Output: {OUTPUT_DIR}")
    print(f"   Start:  {start.strftime('%Y-%m-%d %H:%M:%S')}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Load data
    print("\n📂 Loading data...")
    df = pd.read_csv(INPUT_FILE)
    total_raw = len(df)
    print(f"   Loaded: {total_raw:,} rows")

    report = []
    report.append(f"FoodmoleGPT Data Cleaning Report")
    report.append(f"Generated: {start.strftime('%Y-%m-%d %H:%M:%S')}")
    report.append(f"Input: {INPUT_FILE}")
    report.append(f"Raw records: {total_raw:,}")
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

    # 1b. Language filter: keep English + missing language tag
    non_en = df[df["language"].notna() & (df["language"] != "en")]
    non_en_count = len(non_en)
    if non_en_count > 0:
        report.append(f"[Step 1b] Non-English removed: {non_en_count:,}")
        report.append(f"   Languages removed: {non_en['language'].value_counts().head(10).to_dict()}")
    df = df[(df["language"] == "en") | (df["language"].isna())].copy()
    print(f"   Non-English removed: {non_en_count:,}")

    # 1c. Deduplicate by DOI
    before = len(df)
    doi_df = df[df["doi"].notna()]
    doi_dups = doi_df[doi_df.duplicated("doi", keep="first")]
    df = df.drop(doi_dups.index)
    doi_dup_count = len(doi_dups)
    print(f"   DOI duplicates removed: {doi_dup_count:,}")
    report.append(f"[Step 1c] DOI duplicates removed: {doi_dup_count:,}")

    # 1d. Deduplicate by normalized title
    df["_norm_title"] = df["title"].apply(normalize_title_for_dedup)
    before = len(df)
    df = df.drop_duplicates(subset=["_norm_title"], keep="first")
    title_dup_count = before - len(df)
    df = df.drop(columns=["_norm_title"])
    print(f"   Title duplicates removed: {title_dup_count:,}")
    report.append(f"[Step 1d] Title duplicates removed: {title_dup_count:,}")

    after_step1 = len(df)
    print(f"   ➤ After Step 1: {after_step1:,} ({total_raw - after_step1:,} removed)")
    report.append(f"After Step 1: {after_step1:,} (removed {total_raw - after_step1:,})")
    report.append("")

    # =========================================================================
    # STEP 2: TEXT CLEANING
    # =========================================================================
    print("\n" + "=" * 70)
    print("✨ STEP 2: Text Cleaning")

    # Clean title
    print("   Cleaning titles...", flush=True)
    df["title"] = df["title"].apply(clean_text)

    # Clean abstract
    print("   Cleaning abstracts...", flush=True)
    df["abstract"] = df["abstract"].apply(clean_text)

    # Clean keywords
    print("   Cleaning keywords...", flush=True)
    df["keywords"] = df["keywords"].apply(clean_text)

    print("   ✅ Text cleaning complete (citations, HTML, Unicode, whitespace)")
    report.append("[Step 2] Text cleaning applied to title, abstract, keywords")
    report.append("  - Removed citation markers [1], [2,3], [1-5], (1), (1,2)")
    report.append("  - Removed HTML tags")
    report.append("  - Normalized Unicode (NFKC)")
    report.append("  - Fixed whitespace and control characters")
    report.append("")

    # =========================================================================
    # STEP 3: ABSTRACT QUALITY
    # =========================================================================
    print("\n" + "=" * 70)
    print("📊 STEP 3: Abstract Quality Filtering")

    # Calculate abstract stats
    df["has_abstract"] = df["abstract"].notna() & (df["abstract"].str.strip() != "")
    df["abstract_char_count"] = df["abstract"].str.len().fillna(0).astype(int)
    df["abstract_word_count"] = df["abstract"].str.split().str.len().fillna(0).astype(int)

    # Quality labels
    def label_abstract_quality(row):
        if not row["has_abstract"]:
            return "none"
        if row["abstract_char_count"] < 50:
            return "corrupted"
        if row["abstract_char_count"] < 200:
            return "short"
        return "good"

    df["abstract_quality"] = df.apply(label_abstract_quality, axis=1)

    # Remove corrupted abstracts (set to None)
    corrupted = (df["abstract_quality"] == "corrupted").sum()
    df.loc[df["abstract_quality"] == "corrupted", "abstract"] = None
    df.loc[df["abstract_quality"] == "corrupted", "has_abstract"] = False
    df.loc[df["abstract_quality"] == "corrupted", "abstract_quality"] = "none"
    print(f"   Corrupted abstracts (<50 chars) nullified: {corrupted:,}")

    quality_counts = df["abstract_quality"].value_counts()
    for q, n in quality_counts.items():
        print(f"   {q:12}: {n:>10,}")

    report.append(f"[Step 3] Abstract quality assessment:")
    for q, n in quality_counts.items():
        report.append(f"  {q}: {n:,}")
    report.append(f"  Corrupted (<50 chars) nullified: {corrupted:,}")
    report.append("")

    # =========================================================================
    # STEP 4: FINAL OUTPUT
    # =========================================================================
    print("\n" + "=" * 70)
    print("💾 STEP 4: Saving Output")

    # Recalculate tiers
    df["tier"] = df["cited_by_count"].apply(
        lambda x: 1 if x >= 50 else (2 if x >= 10 else 3)
    )
    df["tier_label"] = df["tier"].map({
        1: "high_impact", 2: "medium_impact", 3: "standard"
    })

    # Sort by citation count (most impactful first)
    df = df.sort_values("cited_by_count", ascending=False).reset_index(drop=True)

    # Output 1: Full cleaned dataset
    full_file = OUTPUT_DIR / "master_cleaned.csv"
    df.to_csv(full_file, index=False, encoding="utf-8-sig")
    print(f"   📁 master_cleaned.csv: {len(df):,} rows ({full_file.stat().st_size/1024/1024:.1f} MB)")

    # Output 2: Only papers with good/short abstracts
    df_abs = df[df["has_abstract"]].copy()
    abs_file = OUTPUT_DIR / "master_with_abstract.csv"
    df_abs.to_csv(abs_file, index=False, encoding="utf-8-sig")
    print(f"   📁 master_with_abstract.csv: {len(df_abs):,} rows ({abs_file.stat().st_size/1024/1024:.1f} MB)")

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
        ("Good abstracts (≥200 chars)", (df["abstract_quality"] == "good").sum()),
        ("Short abstracts (50-200)", (df["abstract_quality"] == "short").sum()),
        ("", ""),
        ("Tier 1 (≥50 cites)", (df["tier"] == 1).sum()),
        ("Tier 2 (≥10 cites)", (df["tier"] == 2).sum()),
        ("Tier 3 (<10 cites)", (df["tier"] == 3).sum()),
        ("", ""),
        ("Mean abstract words", f'{df[df.has_abstract]["abstract_word_count"].mean():.0f}'),
        ("Median abstract words", f'{df[df.has_abstract]["abstract_word_count"].median():.0f}'),
    ]

    report.append("=" * 50)
    report.append("FINAL STATISTICS")
    report.append("=" * 50)
    for label, val in stats:
        if label == "":
            print()
            report.append("")
        else:
            line = f"   {label:30} {val:>12,}" if isinstance(val, int) else f"   {label:30} {val:>12}"
            print(line)
            report.append(line)

    print(f"\n   By source (top 15):")
    report.append(f"\nBy source:")
    for c, n in df["primary_concept"].value_counts().head(15).items():
        line = f"      {c:30} {n:>8,}"
        print(line)
        report.append(f"   {line}")

    print(f"\n   Year range: {df['publication_year'].min()}-{df['publication_year'].max()}")

    elapsed = datetime.now() - start
    print(f"\n   Elapsed: {elapsed}")

    # Save report
    report_file = OUTPUT_DIR / "cleaning_report.txt"
    report.append(f"\nElapsed: {elapsed}")
    with open(report_file, "w", encoding="utf-8") as f:
        f.write("\n".join(report))
    print(f"   📄 Report: {report_file}")

    print("\n" + "=" * 70)
    print("✅ Data cleaning complete!")
    print(f"   Full dataset:     {full_file}")
    print(f"   Abstract dataset: {abs_file}")
    print("=" * 70)


if __name__ == "__main__":
    run_cleaning()
