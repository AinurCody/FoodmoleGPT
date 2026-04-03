"""
FoodmoleGPT — Domain Relevance Filter

Filters SFT instruction pairs to keep only food-science-relevant entries.

Strategy:
  1. Broad positive keyword matching (food science, nutrition, agriculture, etc.)
  2. If instruction+output contains ≥1 positive keyword → KEEP
  3. If zero positive keywords → flag as OFF-TOPIC → REMOVE

Usage:
    python domain_filter.py
    python domain_filter.py --dry-run    # preview without writing
"""

import json
import re
import argparse
from pathlib import Path
from collections import defaultdict

BASE_DIR = Path(__file__).resolve().parent
INPUT_FILE = BASE_DIR / "final" / "foodmole_sft_100k_full.jsonl"
OUTPUT_KEPT = BASE_DIR / "final" / "foodmole_sft_filtered.jsonl"          # Alpaca format
OUTPUT_KEPT_FULL = BASE_DIR / "final" / "foodmole_sft_filtered_full.jsonl"  # With metadata
OUTPUT_REMOVED = BASE_DIR / "final" / "domain_filter_removed.jsonl"
STATS_FILE = BASE_DIR / "final" / "domain_filter_stats.json"

# ── Positive keywords: food science & related fields ───────────────
# An entry is KEPT if instruction+output matches ≥1 of these (case-insensitive)
POSITIVE_KEYWORDS = [
    # Core food science
    r"\bfood\b", r"\bfoods\b", r"\bdietary\b", r"\bdiet\b", r"\bdiets\b",
    r"\bnutrition\b", r"\bnutritional\b", r"\bnutrient\b", r"\bnutrients\b",
    r"\bmalnutrition\b", r"\bmicronutrient\b", r"\bmacronutrient\b",
    r"\bcalori[ec]", r"\bvitamin\b", r"\bmineral\b",
    r"\bfood\s*safety\b", r"\bfoodborne\b", r"\bfood\s*processing\b",
    r"\bfood\s*quality\b", r"\bshelf[- ]life\b", r"\bfood\s*preservation\b",
    r"\bfood\s*packaging\b", r"\bfood\s*additive\b",

    # Macronutrients
    r"\bprotein\b", r"\bproteins\b", r"\bamino acid\b",
    r"\bcarbohydrate\b", r"\bstarch\b", r"\bsugar\b", r"\bsucrose\b",
    r"\bglucose\b", r"\bfructose\b", r"\bgalactose\b", r"\blactose\b",
    r"\bfiber\b", r"\bfibre\b", r"\bcellulose\b", r"\bpectin\b",
    r"\bfat\b", r"\bfats\b", r"\blipid\b", r"\bfatty acid\b",
    r"\bcholesterol\b", r"\btriglyceride\b", r"\boil\b",
    r"\bomega-3\b", r"\bomega-6\b", r"\bDHA\b", r"\bEPA\b",

    # Micronutrients & bioactive compounds
    r"\bpolyphenol", r"\bflavonoid", r"\banthocyanin", r"\bcatechin",
    r"\bcarotenoid", r"\blycopene\b", r"\bbeta-carotene\b",
    r"\bantioxidant", r"\bphenolic", r"\btannin", r"\bsaponin",
    r"\bisoflavone", r"\bquercetin\b", r"\bresveratrol\b", r"\bcurcumin\b",
    r"\bprobiot", r"\bprebiot", r"\bsynbiot",
    r"\biron\b", r"\bzinc\b", r"\bcalcium\b", r"\biodine\b",
    r"\bselenium\b", r"\bfolate\b", r"\bfolic acid\b",

    # Food processing & technology
    r"\bferment", r"\bpasteuriz", r"\bsteriliz",
    r"\bdrying\b", r"\bfreeze[- ]dr", r"\bspray[- ]dr",
    r"\bextrusion\b", r"\bhomogeniz", r"\bemulsif", r"\bemulsion",
    r"\bencapsulat", r"\bnanoparticle", r"\bnano[-]?emulsion",
    r"\bbaking\b", r"\broasting\b", r"\bcooking\b", r"\bfrying\b",
    r"\bgrilling\b", r"\bsmoking\b", r"\bcanning\b", r"\bblanching\b",
    r"\bhigh[- ]pressure\b", r"\bHPP\b", r"\birradiat",
    r"\bmaillard\b", r"\bglycat", r"\bcrosslinking\b",
    r"\btextur", r"\bviscosity\b", r"\brheolog", r"\bgel\b",

    # Food categories
    r"\bmeat\b", r"\bbeef\b", r"\bpork\b", r"\bchicken\b", r"\bpoultry\b",
    r"\bfish\b", r"\bseafood\b", r"\bshrimp\b", r"\bsalmon\b", r"\btuna\b",
    r"\bmilk\b", r"\bdairy\b", r"\bcheese\b", r"\byogurt\b", r"\bwhey\b",
    r"\bcasein\b", r"\blacto\b",
    r"\bbread\b", r"\bflour\b", r"\bwheat\b", r"\brice\b", r"\bcorn\b",
    r"\bmaize\b", r"\bbarley\b", r"\boat\b", r"\bsorghum\b", r"\bmillet\b",
    r"\bcereal\b", r"\bgrain\b",
    r"\bfruit\b", r"\bvegetable\b", r"\bberry\b", r"\bapple\b", r"\bgrape\b",
    r"\btomato\b", r"\bpotato\b", r"\bonion\b", r"\bgarlic\b",
    r"\blegume\b", r"\bbean\b", r"\bsoy\b", r"\bpea\b", r"\blentil\b",
    r"\bnut\b", r"\bpeanut\b", r"\balmond\b", r"\bwalnut\b",
    r"\btea\b", r"\bcoffee\b", r"\bcocoa\b", r"\bchocolate\b",
    r"\bwine\b", r"\bbeer\b", r"\bbeverage\b", r"\bjuice\b",
    r"\bhoney\b", r"\bspice\b", r"\bherb\b", r"\bvinegar\b",
    r"\begg\b", r"\bsausage\b",

    # Agriculture & farming
    r"\bagricultur", r"\bcrop\b", r"\bharvest", r"\byield\b",
    r"\birrigation\b", r"\bfertiliz", r"\bpesticid", r"\bherbicid",
    r"\blivestock\b", r"\bcattle\b", r"\bswine\b", r"\bpig\b",
    r"\bbroiler", r"\blayer\b", r"\baquacultur", r"\bfisheries\b",
    r"\bfeed\b", r"\bsilage\b", r"\bforage\b", r"\bpasture\b",
    r"\bgermplasm\b", r"\bcultivar", r"\bbreeding\b",

    # Food microbiology
    r"\bsalmonella\b", r"\blisteria\b", r"\be\.\s*coli\b",
    r"\bstaphylococcus\b", r"\bbacillus\b", r"\bclostridium\b",
    r"\bcampylobacter\b", r"\bvibrio\b",
    r"\blactic acid bact", r"\bLAB\b", r"\blactobacill",
    r"\bbifidobact", r"\bsaccharomyces\b", r"\byeast\b",
    r"\bmycotoxin", r"\baflatoxin", r"\bochratoxin",
    r"\bbiofilm\b", r"\bspoilage\b", r"\bcontaminat",
    r"\bpathogen",

    # Nutrition & health (diet-related)
    r"\bobesi", r"\boverweight\b", r"\bBMI\b", r"\bbody mass\b",
    r"\bdiabet", r"\binsulin\b", r"\bglycemi", r"\bblood sugar\b",
    r"\bcardiovascular\b", r"\bhypertens", r"\bblood pressure\b",
    r"\bgut\s*microbi", r"\bmicrobiome\b", r"\bmicrobiota\b",
    r"\bmetabolic syndrome\b", r"\binflammation\b", r"\binflammatory\b",
    r"\bimmun",
    r"\ballerg", r"\bceliac\b", r"\bgluten\b",
    r"\bbreast\s*feed", r"\bbreast\s*milk\b", r"\binfant\s*formula\b",
    r"\bsupplement", r"\bnueuraceutical", r"\bfunctional food",
    r"\bbioavailab",
    r"\beating\b", r"\bappetite\b", r"\bsatiet", r"\bhunger\b",
    r"\bconsumption\b", r"\bintake\b", r"\bingestion\b",

    # Sensory science
    r"\bsensory\b", r"\bflavor\b", r"\bflavour\b", r"\baroma\b",
    r"\btaste\b", r"\bpalat\b", r"\btexture\b", r"\bmouthfeel\b",
    r"\bodor\b", r"\bodour\b",

    # Analytical methods (food-specific)
    r"\bHPLC\b", r"\bGC-MS\b", r"\bLC-MS\b",
    r"\bfood analysis\b", r"\bproximate\b",

    # Food safety & toxicology
    r"\bacrylamide\b", r"\bnitrate\b", r"\bnitrite\b", r"\bnitrosamine\b",
    r"\bheavy metal", r"\bcadmium\b", r"\blead\b", r"\barsenic\b",
    r"\bmercury\b", r"\bpesticid", r"\bresidue\b",
    r"\bHACCP\b", r"\bGMP\b",
    r"\bfood label", r"\bfood regulat",

    # Bioactive & functional
    r"\bbioactiv", r"\bphytochemical", r"\bnueutical",
    r"\bextract",  # plant/food extract
    r"\bessential oil",
]

# Compile patterns for efficiency
_pos_patterns = [re.compile(p, re.IGNORECASE) for p in POSITIVE_KEYWORDS]


def has_domain_relevance(text: str) -> tuple[bool, list[str]]:
    """Check if text contains food science keywords. Returns (is_relevant, matched_keywords)."""
    matched = []
    for pattern in _pos_patterns:
        if pattern.search(text):
            matched.append(pattern.pattern)
            if len(matched) >= 2:  # Early exit: 2 matches = definitely relevant
                return True, matched
    return len(matched) > 0, matched


def main():
    parser = argparse.ArgumentParser(description="Filter SFT data for food science domain relevance")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing files")
    args = parser.parse_args()

    print("[1/3] Loading data...")
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        all_pairs = [json.loads(line) for line in f if line.strip()]
    print(f"  Loaded: {len(all_pairs)}")

    print("[2/3] Filtering...")
    kept = []
    removed = []
    for p in all_pairs:
        # Check instruction + output combined
        combined = p["instruction"] + " " + p["output"]
        relevant, matches = has_domain_relevance(combined)
        if relevant:
            kept.append(p)
        else:
            p["_removal_reason"] = "no_domain_keywords"
            removed.append(p)

    print(f"  Kept:    {len(kept)}")
    print(f"  Removed: {len(removed)}")

    # Stats
    removed_by_source = defaultdict(int)
    for p in removed:
        removed_by_source[p.get("source", "unknown")] += 1

    kept_type_counts = defaultdict(int)
    kept_source_counts = defaultdict(int)
    for p in kept:
        kept_type_counts[p.get("type", "OTHER")] += 1
        kept_source_counts[p.get("source", "unknown")] += 1

    stats = {
        "input_count": len(all_pairs),
        "kept_count": len(kept),
        "removed_count": len(removed),
        "removal_rate": f"{len(removed)/len(all_pairs)*100:.2f}%",
        "removed_by_source": dict(removed_by_source),
        "kept_type_distribution": dict(sorted(kept_type_counts.items(), key=lambda x: -x[1])),
        "kept_source_distribution": dict(kept_source_counts),
    }

    print(f"\n[3/3] Results:")
    print(f"  Input:       {stats['input_count']:>8}")
    print(f"  Kept:        {stats['kept_count']:>8}")
    print(f"  Removed:     {stats['removed_count']:>8} ({stats['removal_rate']})")
    print(f"  By source:   {dict(removed_by_source)}")
    print()
    print(f"  Kept type distribution:")
    for t, c in sorted(kept_type_counts.items(), key=lambda x: -x[1]):
        print(f"    {t:16s}: {c:>6} ({c/len(kept)*100:.1f}%)")

    if args.dry_run:
        print("\n  [DRY RUN] No files written.")
        # Show some removed examples
        print(f"\n  Sample removed entries ({min(10, len(removed))}):")
        for p in removed[:10]:
            print(f"    - {p['instruction'][:100]}...")
        return

    # Write outputs
    print(f"\n  Writing files...")

    # Alpaca format (for LLaMA-Factory)
    with open(OUTPUT_KEPT, "w", encoding="utf-8") as f:
        for p in kept:
            record = {
                "instruction": p["instruction"],
                "input": p.get("input", ""),
                "output": p["output"],
            }
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    # Full format with metadata
    with open(OUTPUT_KEPT_FULL, "w", encoding="utf-8") as f:
        for p in kept:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")

    # Removed entries (for review)
    with open(OUTPUT_REMOVED, "w", encoding="utf-8") as f:
        for p in removed:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")

    # Stats
    with open(STATS_FILE, "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2, ensure_ascii=False)

    print(f"  ✓ {OUTPUT_KEPT}")
    print(f"  ✓ {OUTPUT_KEPT_FULL}")
    print(f"  ✓ {OUTPUT_REMOVED}")
    print(f"  ✓ {STATS_FILE}")


if __name__ == "__main__":
    main()
