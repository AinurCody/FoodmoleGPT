"""
FoodmoleGPT - Text Quality Cleaning
====================================
Cleans PDF extraction artifacts from filtered JSONL data:
  1. Table remnants (number grids, border lines, tab-separated data)
  2. Unicode math blocks (𝑅𝑀𝑆𝐸 → RMSE)
  3. Garbled/mojibake text segments
  4. Excessive whitespace / blank lines
  5. Short/empty records after cleaning

Reads from filtered_r2/ and writes cleaned versions for format_training_r2.py.

Usage:
    conda activate foodmole
    python src/clean_text_quality.py
"""

import json
import re
import sys
from pathlib import Path
from datetime import datetime

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# =============================================================================
# PATHS
# =============================================================================

INPUT_DIR = Path("D:/FoodmoleGPT/data/filtered_r2")
OUTPUT_DIR = Path("D:/FoodmoleGPT/data/filtered_r2_cleaned")

FULLTEXT_IN = INPUT_DIR / "food_fulltext_filtered.jsonl"
ABSTRACT_IN = INPUT_DIR / "food_abstract_filtered.jsonl"

FULLTEXT_OUT = OUTPUT_DIR / "food_fulltext_cleaned.jsonl"
ABSTRACT_OUT = OUTPUT_DIR / "food_abstract_cleaned.jsonl"

REPORT_FILE = OUTPUT_DIR / "cleaning_report.txt"

MIN_FULLTEXT_AFTER_CLEAN = 500   # chars
MIN_ABSTRACT_AFTER_CLEAN = 50    # chars

# =============================================================================
# CLEANING PATTERNS
# =============================================================================

# 1. Table number grids: 6+ numbers (int or float) separated by whitespace
#    e.g. "16 25  2  0  1  19  4  6  8  6  19  6  11  21"
RE_TABLE_NUMS = re.compile(
    r"^[ \t]*(?:\d+\.?\d*(?:[eE][+-]?\d+)?[ \t]+){5,}\d+\.?\d*(?:[eE][+-]?\d+)?[ \t]*$",
    re.MULTILINE,
)

# 2. Table borders: +---+---+ or |---|---| or ═══════ or ─────────
RE_TABLE_BORDER = re.compile(
    r"^[ \t]*(?:[+|][-=]+){2,}[+|]?[ \t]*$"
    r"|^[ \t]*[-─━═]{10,}[ \t]*$",
    re.MULTILINE,
)

# 3. Tab-separated data rows (4+ columns): tab-delimited short cells
RE_TAB_TABLE = re.compile(
    r"^[^\t\n]{0,30}(?:\t[^\t\n]{0,30}){3,}$",
    re.MULTILINE,
)

# 4. Unicode Mathematical Alphanumeric Symbols (U+1D400..U+1D7FF)
#    These are italic/bold/script variants used in some PDFs for formulas.
#    Map them back to ASCII equivalents.
_MATH_RANGES = [
    (0x1D400, 0x1D419, ord("A")),  # Bold A-Z
    (0x1D41A, 0x1D433, ord("a")),  # Bold a-z
    (0x1D434, 0x1D44D, ord("A")),  # Italic A-Z
    (0x1D44E, 0x1D467, ord("a")),  # Italic a-z
    (0x1D468, 0x1D481, ord("A")),  # Bold Italic A-Z
    (0x1D482, 0x1D49B, ord("a")),  # Bold Italic a-z
    (0x1D49C, 0x1D4B5, ord("A")),  # Script A-Z (partial)
    (0x1D4B6, 0x1D4CF, ord("a")),  # Script a-z
    (0x1D4D0, 0x1D4E9, ord("A")),  # Bold Script A-Z
    (0x1D4EA, 0x1D503, ord("a")),  # Bold Script a-z
    (0x1D7CE, 0x1D7D7, ord("0")),  # Bold digits 0-9
    (0x1D7D8, 0x1D7E1, ord("0")),  # Double-struck digits
    (0x1D7E2, 0x1D7EB, ord("0")),  # Sans-serif digits
    (0x1D7EC, 0x1D7F5, ord("0")),  # Sans-serif bold digits
    (0x1D7F6, 0x1D7FF, ord("0")),  # Monospace digits
]

_MATH_MAP = {}
for start, end, base in _MATH_RANGES:
    for cp in range(start, end + 1):
        _MATH_MAP[chr(cp)] = chr(base + (cp - start))

RE_MATH_CHARS = re.compile(
    "[" + "".join(re.escape(c) for c in _MATH_MAP.keys()) + "]"
)

# 5. Mojibake patterns: common CJK-encoded Greek letter artifacts
MOJIBAKE_MAP = {
    "尾": "\u03B2",   # β
    "伪": "\u03B1",   # α
    "纬": "\u03B3",   # γ
    "未": "\u03B4",   # δ
    "渭": "\u03BC",   # μ
    "蟺": "\u03C0",   # π
    "蠁": "\u03C6",   # φ
    "蠂": "\u03C7",   # χ
    "蠅": "\u03C9",   # ω
    "螝": "\u0394",   # Δ
    "鈭": "\u2212",   # −
    "垎": "\u0394",   # Δ (part of mojibake ΔΔ)
    "聽": " ",        # NBSP mojibake
}

# 6. Control characters (except \n \r \t)
RE_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

# 7. Excessive blank lines (3+ consecutive)
RE_MULTI_BLANK = re.compile(r"\n{4,}")


# =============================================================================
# CLEANING FUNCTIONS
# =============================================================================

def normalize_math_unicode(text: str) -> str:
    """Replace Unicode math alphanumeric symbols with ASCII equivalents."""
    return RE_MATH_CHARS.sub(lambda m: _MATH_MAP.get(m.group(), m.group()), text)


def fix_mojibake(text: str) -> str:
    """Fix known CJK mojibake patterns for Greek letters."""
    for bad, good in MOJIBAKE_MAP.items():
        if bad in text:
            text = text.replace(bad, good)
    return text


def remove_table_segments(text: str) -> str:
    """Remove lines that look like table data, borders, or tab-separated rows."""
    text = RE_TABLE_NUMS.sub("", text)
    text = RE_TABLE_BORDER.sub("", text)
    text = RE_TAB_TABLE.sub("", text)
    return text


def clean_whitespace(text: str) -> str:
    """Normalize whitespace: remove control chars, collapse blank lines."""
    text = RE_CONTROL.sub("", text)
    text = RE_MULTI_BLANK.sub("\n\n\n", text)
    # Remove trailing whitespace on each line
    text = "\n".join(line.rstrip() for line in text.split("\n"))
    return text.strip()


def clean_full_text(text: str) -> str:
    """Apply all cleaning steps to a full_text field."""
    text = fix_mojibake(text)
    text = normalize_math_unicode(text)
    text = remove_table_segments(text)
    text = clean_whitespace(text)
    return text


def clean_abstract(text: str) -> str:
    """Light cleaning for abstract field."""
    text = fix_mojibake(text)
    text = normalize_math_unicode(text)
    text = RE_CONTROL.sub("", text)
    return text.strip()


# =============================================================================
# MAIN PROCESSOR
# =============================================================================

def process_file(input_path: Path, output_path: Path, mode: str) -> dict:
    """
    Process a JSONL file, cleaning text fields.
    mode: 'fulltext' or 'abstract'
    """
    print(f"\n  Processing: {input_path.name}")
    sys.stdout.flush()

    # Count total
    total = sum(1 for _ in open(input_path, "r", encoding="utf-8"))
    print(f"    Total records: {total:,}")
    sys.stdout.flush()

    kept = 0
    dropped_short = 0
    modified = 0

    with open(input_path, "r", encoding="utf-8") as f_in, \
         open(output_path, "w", encoding="utf-8") as f_out:

        for i, line in enumerate(f_in):
            doc = json.loads(line.strip())

            if mode == "fulltext":
                original_ft = doc.get("full_text", "")
                cleaned_ft = clean_full_text(original_ft) if original_ft else ""

                # Also clean abstract if present
                original_ab = doc.get("abstract", "")
                cleaned_ab = clean_abstract(original_ab) if original_ab else ""

                if len(cleaned_ft) < MIN_FULLTEXT_AFTER_CLEAN:
                    dropped_short += 1
                    continue

                was_modified = (cleaned_ft != original_ft) or (cleaned_ab != original_ab)
                if was_modified:
                    modified += 1

                doc["full_text"] = cleaned_ft
                doc["full_text_length"] = len(cleaned_ft)
                doc["full_text_word_count"] = len(cleaned_ft.split())
                if original_ab:
                    doc["abstract"] = cleaned_ab

            else:  # abstract mode
                original_ab = doc.get("abstract", "")
                cleaned_ab = clean_abstract(original_ab) if original_ab else ""

                if len(cleaned_ab) < MIN_ABSTRACT_AFTER_CLEAN:
                    dropped_short += 1
                    continue

                was_modified = cleaned_ab != original_ab
                if was_modified:
                    modified += 1

                doc["abstract"] = cleaned_ab

            f_out.write(json.dumps(doc, ensure_ascii=False) + "\n")
            kept += 1

            if (i + 1) % 50000 == 0:
                print(f"\r    Processed: {i+1:,} / {total:,}    ", end="")
                sys.stdout.flush()

    print(f"\r    Done: {kept:,} kept, {dropped_short} dropped (too short), "
          f"{modified:,} modified")
    sys.stdout.flush()

    return {
        "total": total,
        "kept": kept,
        "dropped_short": dropped_short,
        "modified": modified,
    }


def main():
    print("=" * 60)
    print("FoodmoleGPT - Text Quality Cleaning")
    print("=" * 60)
    sys.stdout.flush()

    start = datetime.now()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    all_stats = []

    # Process fulltext
    if FULLTEXT_IN.exists():
        stats = process_file(FULLTEXT_IN, FULLTEXT_OUT, "fulltext")
        all_stats.append(("fulltext", stats))
    else:
        print(f"\n  Fulltext not found: {FULLTEXT_IN}")

    # Process abstract
    if ABSTRACT_IN.exists():
        stats = process_file(ABSTRACT_IN, ABSTRACT_OUT, "abstract")
        all_stats.append(("abstract", stats))
    else:
        print(f"\n  Abstract not found: {ABSTRACT_IN}")

    elapsed = datetime.now() - start

    # Report
    report_lines = [
        "=" * 60,
        "FoodmoleGPT - Text Quality Cleaning Report",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "=" * 60,
        "",
        "Cleaning operations applied:",
        "  1. Mojibake fix (CJK-encoded Greek letters)",
        "  2. Unicode math normalization (U+1D400..1D7FF -> ASCII)",
        "  3. Table remnant removal (number grids, borders, tab-rows)",
        "  4. Control character removal",
        "  5. Whitespace normalization (collapse blank lines)",
        "  6. Drop records with full_text < 500 chars after cleaning",
        "",
    ]

    for label, stats in all_stats:
        pct_mod = stats["modified"] / stats["total"] * 100 if stats["total"] else 0
        report_lines.extend([
            f"DATASET: {label.upper()}",
            f"  Input:     {stats['total']:>10,}",
            f"  Kept:      {stats['kept']:>10,}",
            f"  Dropped:   {stats['dropped_short']:>10,}",
            f"  Modified:  {stats['modified']:>10,} ({pct_mod:.2f}%)",
            "",
        ])

    report_lines.append(f"Elapsed: {elapsed}")
    report = "\n".join(report_lines)

    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"\n{report}")
    print(f"\nOutput: {OUTPUT_DIR}")
    print("[DONE] Text quality cleaning complete!")
    sys.stdout.flush()


if __name__ == "__main__":
    main()
