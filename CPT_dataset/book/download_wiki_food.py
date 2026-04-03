#!/usr/bin/env python3
"""
download_wiki_food.py
=====================
Download English Wikipedia articles related to food science and adjacent
domains, then convert them to CPT-ready JSONL format.

Strategy:
  Uses HuggingFace `wikimedia/wikipedia` (pre-parsed plain text) and filters
  articles by keyword matching on title + text opening, since the HF dataset
  does not expose MediaWiki categories.

  Keywords are split into two tiers:
    Tier 1 — SAFE keywords: unambiguous terms; title match alone is sufficient.
    Tier 2 — AMBIGUOUS keywords: short / common words (oil, fish, tea, …);
             title match is accepted ONLY if the opening text also contains
             at least one TEXT_KEYWORD confirming food-related context.
    Tier 3 — TEXT-ONLY: articles whose title does not match but whose opening
             500 chars contain a food-science multi-word phrase.

  All matching uses regex word-boundary (\\b) to avoid substring false
  positives (e.g. "tea" ≠ "team", "herb" ≠ "Herbert").

Outputs (in book/data/):
  - wiki_food_cpt.jsonl        CPT-ready format {"text": "Title: ...\\n\\n..."}
  - filter_stats.json          Statistics

Usage:
  python download_wiki_food.py [--max-tokens TARGET_TOKENS]

Requires:  pip install datasets tqdm
"""

import argparse
import json
import re
import sys
import time
from pathlib import Path

from datasets import load_dataset
from tqdm import tqdm

# ─────────────────────────────────────────────────────────────────────
# Paths
# ─────────────────────────────────────────────────────────────────────
BASE = Path(__file__).resolve().parent
OUT_DIR = BASE / "data"
OUT_DIR.mkdir(parents=True, exist_ok=True)

CPT_JSONL = OUT_DIR / "wiki_food_cpt.jsonl"
STATS_FILE = OUT_DIR / "filter_stats.json"

# ─────────────────────────────────────────────────────────────────────
# Tier 1 — SAFE title keywords (unambiguous, title match is sufficient)
# ─────────────────────────────────────────────────────────────────────
SAFE_TITLE_KEYWORDS = {
    # Food science core (multi-word or unique)
    "food science", "food safety", "food processing", "food preservation",
    "food chemistry", "food technology", "food engineering", "food microbiology",
    "food industry", "food production", "food packaging", "food storage",
    "food labeling", "food labelling", "food poisoning", "food allergy",
    "food allergies", "food additive", "food additives", "food coloring",
    "food regulation", "food quality", "food contamination",
    "foodborne", "food-borne",
    "organic food",
    # Nutrition (unambiguous)
    "nutrition", "nutritional", "nutrient", "nutrients",
    "malnutrition", "undernutrition", "overnutrition",
    "dietary supplement", "dietary fiber", "dietary fibre",
    "calorie", "calories",
    # Cuisine / cooking (unambiguous)
    "cuisine", "cuisines", "culinary",
    "cooking", "baking", "roasting", "frying", "grilling", "steaming",
    "fermentation", "fermented",
    # Dairy (unambiguous)
    "dairy", "cheese", "yogurt", "yoghurt",
    # Meat (unambiguous)
    "seafood", "shellfish", "poultry",
    "beef", "pork", "veal",
    # Grains & legumes (unambiguous)
    "cereal grain", "soybean", "legume", "legumes",
    # Processed food terms
    "bread", "pasta", "noodle", "noodles", "flour",
    "chocolate", "cocoa", "candy",
    "olive oil", "palm oil", "vegetable oil", "cooking oil",
    "additive", "additives", "preservative", "preservatives",
    "pesticide", "pesticides", "herbicide", "fungicide",
    "genetically modified food", "gmo food",
    # Food processing / safety
    "pasteurization", "pasteurisation", "sterilization",
    "canning", "freeze-drying", "dehydration",
    # Microbiology / biochemistry (unambiguous)
    "probiotic", "probiotics", "prebiotic", "prebiotics",
    "antioxidant", "antioxidants",
    "carbohydrate", "carbohydrates", "starch",
    "lipid", "lipids", "fatty acid", "cholesterol", "triglyceride",
    "gluten", "lactose", "casein", "whey",
    "amino acid",
    # Agriculture (unambiguous multi-word)
    "agriculture", "agricultural", "agronomy", "agronomic",
    "horticulture", "horticultural",
    "aquaculture", "livestock",
    "cattle", "swine", "pig farming",
    "poultry farming", "animal husbandry",
    "crop production", "crop science", "crop rotation",
    "food crop", "food crops",
    # Beverage (unambiguous)
    "beverage", "beverages",
}

# ─────────────────────────────────────────────────────────────────────
# Tier 2 — AMBIGUOUS title keywords
#   These are short, common English words that frequently appear in
#   non-food contexts (oil = petroleum; tea = team; rice = surname; …).
#   If one of these matches the TITLE, we additionally require at least
#   one TEXT_KEYWORD in the opening text to confirm food relevance.
# ─────────────────────────────────────────────────────────────────────
AMBIGUOUS_TITLE_KEYWORDS = {
    "fish", "fishing", "fishery", "fisheries",
    "oil", "fat", "fats",
    "tea", "coffee", "beer", "wine", "juice",
    "milk", "butter", "cream", "egg", "eggs",
    "meat", "chicken", "lamb", "salmon", "tuna", "shrimp",
    "fruit", "fruits", "vegetable", "vegetables",
    "grain", "grains", "cereal", "cereals",
    "wheat", "rice", "corn", "maize", "barley", "oat", "oats",
    "soy", "lentil", "bean", "beans", "pea", "peas",
    "spice", "spices", "herb", "herbs", "seasoning",
    "sugar", "sweetener", "honey",
    "vitamin", "vitamins", "mineral",
    "protein", "enzyme", "enzymes",
    "diet", "diets", "dietary",
    "crop", "crops", "harvest", "irrigation",
    "cellulose", "fiber", "fibre",
    "metabolism",
}

# ─────────────────────────────────────────────────────────────────────
# TEXT_KEYWORDS — matched in first 500 chars of article body.
#   Used for:
#   (a) confirming ambiguous title matches (Tier 2)
#   (b) catching articles with generic titles (Tier 3, text-only pass)
# ─────────────────────────────────────────────────────────────────────
TEXT_KEYWORDS = {
    # Food science (high precision multi-word phrases)
    "food science", "food safety", "food processing", "food industry",
    "food chemistry", "food technology", "food engineering",
    "food preservation", "food production", "food quality",
    "food contamination", "foodborne pathogen", "foodborne illness",
    "food source", "food plant", "food fish", "food crop",
    # Nutrition
    "nutritional value", "dietary intake", "dietary supplement",
    # Context signals — words/phrases that strongly indicate food relevance
    "edible", "consumable", "human consumption",
    "eaten raw", "eaten as", "eaten cooked", "eaten fresh",
    "cooked as", "cooking", "culinary", "cuisine",
    "ingredient in", "used in cooking",
    # Agriculture — food-specific
    "food crop", "crop production", "crop yield",
    "livestock feed", "animal feed",
    "dairy farming", "poultry farming",
    # Food processing
    "fermentation process", "lactic acid bacteria",
    "shelf life", "expiration date", "best before",
    "food additive", "food coloring", "food colouring",
    "food regulation", "food standard", "codex alimentarius",
    "usda", "fda food", "efsa",
    # Beverage — food-specific
    "brewed", "distilled", "fermented beverage",
}

# ─────────────────────────────────────────────────────────────────────
# Exclusion patterns — matched on title, blocks even a keyword match
# ─────────────────────────────────────────────────────────────────────
TITLE_EXCLUDE = {
    # Sports
    "football", "soccer", "basketball", "baseball", "cricket",
    "volleyball", "rugby", "tennis", "hockey", "golf",
    "championship", "championships", "trophy", "league",
    "olympic", "olympics", "world cup", "tournament",
    "racing", "race", "marathon", "sprint",
    "team season", "season results", "medal",
    # Entertainment
    "film", "movie", "album", "song", "band", "musician",
    "singer", "actor", "actress", "tv series", "television",
    "video game", "anime", "manga", "novel",
    # Politics & military
    "politician", "election", "political party", "parliament",
    "military", "battle", "war of", "regiment", "battalion",
    # Science (non-food)
    "asteroid", "galaxy", "nebula", "constellation", "star system",
    # Infrastructure
    "railway", "railroad", "highway", "motorway", "airport",
    "station", "bridge",
    # Geography (generic)
    "river", "mountain", "island", "county", "district", "province",
    "municipality",
    # People (indicators)
    "born ", "footballer", "cricketer", "cyclist", "swimmer",
    "chess player", "bishop of", "archbishop",
}


# ─────────────────────────────────────────────────────────────────────
# Compile regex patterns (with word boundaries)
# ─────────────────────────────────────────────────────────────────────
def _compile_set(keywords):
    """Compile a set of keywords into a single alternation regex with \\b."""
    # Sort by length descending so longer phrases match first
    sorted_kw = sorted(keywords, key=len, reverse=True)
    escaped = [re.escape(kw) for kw in sorted_kw]
    pattern = r"\b(?:" + "|".join(escaped) + r")\b"
    return re.compile(pattern, re.IGNORECASE)


RE_SAFE_TITLE = _compile_set(SAFE_TITLE_KEYWORDS)
RE_AMBIGUOUS_TITLE = _compile_set(AMBIGUOUS_TITLE_KEYWORDS)
RE_TEXT = _compile_set(TEXT_KEYWORDS)
RE_EXCLUDE = _compile_set(TITLE_EXCLUDE)


# ─────────────────────────────────────────────────────────────────────
# Matching logic
# ─────────────────────────────────────────────────────────────────────
def _is_excluded(title: str) -> bool:
    return bool(RE_EXCLUDE.search(title))


def _match(title: str, text: str) -> str | None:
    """
    Returns the match tier label or None.
      "safe_title"      — Tier 1 (unambiguous title keyword)
      "ambiguous_title"  — Tier 2 (ambiguous title keyword + text confirmation)
      "text_only"       — Tier 3 (text-only keyword match)
    """
    if _is_excluded(title):
        return None

    # Tier 1: safe title keyword
    if RE_SAFE_TITLE.search(title):
        return "safe_title"

    # Tier 2: ambiguous title keyword + text confirmation
    if RE_AMBIGUOUS_TITLE.search(title):
        snippet = text[:500]
        if RE_TEXT.search(snippet):
            return "ambiguous_title"
        return None  # title matched but no text confirmation → reject

    # Tier 3: text-only
    snippet = text[:500]
    if RE_TEXT.search(snippet):
        return "text_only"

    return None


def estimate_tokens(text: str) -> int:
    return int(len(text.split()) * 1.3)


def format_cpt(title: str, text: str) -> str:
    return f"Title: {title}\nSource: Wikipedia\n\n{text}"


def main():
    parser = argparse.ArgumentParser(description="Download & filter Wikipedia food articles")
    parser.add_argument("--max-tokens", type=int, default=800_000_000,
                        help="Target token count (default: 800M)")
    args = parser.parse_args()

    target_tokens = args.max_tokens
    print(f"Target: ~{target_tokens / 1e6:.0f}M tokens")
    print(f"Output dir: {OUT_DIR}")

    print("\nLoading Wikipedia dataset (streaming)...")
    ds = load_dataset("wikimedia/wikipedia", "20231101.en", split="train", streaming=True)

    kept = 0
    skipped = 0
    excluded = 0
    total_tokens = 0
    tier_counts = {"safe_title": 0, "ambiguous_title": 0, "text_only": 0}
    t0 = time.time()

    with open(CPT_JSONL, "w", encoding="utf-8") as f_cpt:

        for article in tqdm(ds, desc="Scanning Wikipedia", unit=" articles"):
            title = article.get("title", "")
            text = article.get("text", "")

            if len(text) < 200:
                skipped += 1
                continue

            tier = _match(title, text)
            if tier is None:
                skipped += 1
                continue

            tier_counts[tier] += 1

            cpt_text = format_cpt(title, text)
            f_cpt.write(json.dumps({"text": cpt_text}, ensure_ascii=False) + "\n")

            tokens = estimate_tokens(cpt_text)
            total_tokens += tokens
            kept += 1

            if kept % 10000 == 0:
                elapsed = time.time() - t0
                print(f"  [{elapsed:.0f}s] Kept {kept:,} articles, "
                      f"~{total_tokens / 1e6:.0f}M tokens so far...")

            if total_tokens >= target_tokens:
                print(f"\nReached target of ~{target_tokens / 1e6:.0f}M tokens. Stopping.")
                break

    elapsed = time.time() - t0

    stats = {
        "articles_kept": kept,
        "articles_skipped": skipped,
        "tier_safe_title": tier_counts["safe_title"],
        "tier_ambiguous_title": tier_counts["ambiguous_title"],
        "tier_text_only": tier_counts["text_only"],
        "estimated_tokens": total_tokens,
        "target_tokens": target_tokens,
        "elapsed_seconds": round(elapsed, 1),
        "output_cpt": str(CPT_JSONL),
    }

    with open(STATS_FILE, "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2, ensure_ascii=False)

    print(f"\n{'=' * 60}")
    print(f"Done in {elapsed:.0f}s")
    print(f"Articles kept:  {kept:,}")
    print(f"  Tier 1 (safe title):     {tier_counts['safe_title']:,}")
    print(f"  Tier 2 (ambiguous+text): {tier_counts['ambiguous_title']:,}")
    print(f"  Tier 3 (text only):      {tier_counts['text_only']:,}")
    print(f"Estimated tokens: ~{total_tokens / 1e6:.0f}M")
    print(f"Skipped: {skipped:,}")
    print(f"File: {CPT_JSONL.name}")
    print(f"Stats: {STATS_FILE.name}")


if __name__ == "__main__":
    main()
