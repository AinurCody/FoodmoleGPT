"""
FoodmoleGPT - Dataset Quality Filter
======================================
Filters non-food-science papers from the merged dataset using multi-layer matching:

Layer 1: Venue whitelist (food/nutrition/agriculture journals)
Layer 2: Title keyword matching (food-specific terms)
Layer 3: Keywords field matching (food-specific terms)

A paper passes if ANY layer matches.

Usage:
    conda activate foodmole
    python src/filter_food.py
"""

import json
import sys
import re
from pathlib import Path
from datetime import datetime
from collections import Counter

if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# =============================================================================
# CONFIG
# =============================================================================

MERGED_FULLTEXT = Path("D:/FoodmoleGPT/data/merged/food_science_merged.jsonl")
MERGED_ABSTRACT = Path("D:/FoodmoleGPT/data/merged/food_science_abstract.jsonl")

OUTPUT_DIR = Path("D:/FoodmoleGPT/data/filtered")
FILTERED_FULLTEXT = OUTPUT_DIR / "food_fulltext_filtered.jsonl"
FILTERED_ABSTRACT = OUTPUT_DIR / "food_abstract_filtered.jsonl"
REPORT_FILE = OUTPUT_DIR / "filter_report.txt"

# =============================================================================
# LAYER 1: VENUE WHITELIST
# =============================================================================
# Substrings that identify food/nutrition/agriculture journals.
# Matched case-insensitively against the venue field.

VENUE_WHITELIST = [
    # --- Core food science ---
    "food", "foods",
    "journal of agricultural",
    "cereal",
    "dairy", "milk",
    "meat science", "meat technol",
    "poultry science",
    "aquaculture",
    "fisheries",
    # --- Nutrition ---
    "nutrition", "nutrient", "nutrients",
    "dietetic", "diet",
    "obesity",
    "appetite",
    "eating behav",
    # --- Beverages ---
    "beverage",
    "brewing", "brewer",
    "wine", "vitis", "viticult", "enolog",
    "ferment",
    # --- Agriculture / Crop ---
    "agriculture", "agricultural",
    "agronomy", "agronomic",
    "crop", "horticultur",
    "postharvest", "post-harvest",
    "animal science", "animal feed",
    "livestock",
    "veterinar",
    # --- Specific food journals (common names) ---
    "lwt",
    "innov food",
    "compr rev food",
    "trends in food",
    "crit rev food",
    "starch",
    "carbohydrate polymer",
    "carbohydrate research",
    "lipid",
    "fett", # German journal
    "grasas y aceites",
    "eur food res",
    "ital j food",
    "czech j food",
    "j food eng",
    "j food sci",
    "j food prot",
    "j food process",
    "j food comp",
    "food hydrocolloid",
    "food chem",
    "food control",
    "food microbiol",
    "food biophys",
    "food bioproc",
    "food bioprocess",
    "food res int",
    "food research int",
    "food funct",
    "food packag",
    "food addit",
    "food anal",
    "food qual",
    "food saf",
    "food secur",
    "food policy",
    "international dairy",
    "j dairy",
    "j cereal",
    # --- Plant / Bio related that are food-adjacent ---
    "phytochem",
    "flavour fragr",
    "j essent oil",
    "j oleo",
    "j am oil chem",
    "oleagineux",
    "j sci food agric",
    "nahrung",
    # --- Broader bio that often has food papers ---
    "appl microbiol biotechnol",
    "process biochem",
    "bioresource technol",
    "enzyme microb technol",
    "j biotechnol",
    "biotechnol bioeng",
    "j appl microbiol",
    # --- Packaging ---
    "packaging technol",
    "food packaging",
]

# =============================================================================
# LAYER 2 & 3: TITLE / KEYWORDS MATCHING
# =============================================================================
# Food-specific terms matched against title (Layer 2) and keywords field (Layer 3).

FOOD_TERMS = [
    # ---- Core food science ----
    "food", "foods", "foodborne", "food-borne", "food-grade",
    "food science", "food technol", "food engineer", "food chem",
    "food safety", "food quality", "food processing", "food product",
    "food preserv", "food packag", "food fortif", "food addit",
    "food suppl", "food spoil", "food waste", "food loss",
    "food authenticat", "food adulter", "food fraud",
    "food matrix", "food system", "food industr",
    "food security", "food insecurity",
    # ---- Nutrition / Diet ----
    "nutrition", "nutritional", "nutrient", "malnutrition", "undernutrition",
    "diet ", "diet,", "diets", "dietary",
    "eating habit", "eating pattern", "eating disorder", "eating behav",
    "calori", "kilocalori", "energy intake",
    "glycemic index", "glycaemic", "glycemic load",
    "recommended daily", "daily intake", "tolerable upper",
    "deficiency", "biofortif",
    # ---- Macronutrients ----
    "carbohydrate", "starch", "amylose", "amylopectin",
    "dietary fiber", "dietary fibre", "resistant starch",
    "gluten", "celiac", "coeliac",
    "protein isolate", "protein hydrolysate", "protein digest",
    "plant protein", "animal protein", "soy protein", "whey protein",
    "casein", "collagen peptide", "gelatin",
    "lipid", "triglyceride", "phospholipid",
    "fatty acid", "saturated fat", "unsaturated fat", "trans fat",
    "omega-3", "omega-6", "oleic acid", "linoleic", "linolenic",
    "cholesterol", "phytosterol",
    # ---- Micronutrients ----
    "vitamin a", "vitamin b", "vitamin c", "vitamin d", "vitamin e", "vitamin k",
    "retinol", "thiamin", "riboflavin", "niacin", "folate", "folic acid",
    "ascorbic acid", "tocopherol", "carotenoid", "beta-carotene", "lycopene",
    "mineral", "iron absorpt", "iron deficien", "zinc deficien",
    "calcium absorpt", "iodine", "selenium",
    "trace element",
    # ---- Food products / commodities ----
    "dairy", "milk", "cheese", "yogurt", "yoghurt", "butter", "cream", "kefir",
    "meat", "beef", "pork", "lamb", "poultry", "chicken", "turkey",
    "sausage", "salami", "ham ",
    "fish ", "fishes", "seafood", "shellfish", "shrimp", "crab",
    "salmon", "tuna", "tilapia", "catfish", "codfish",
    "egg ", "eggs",
    "bread", "flour", "dough", "bakery", "baking", "pastry", "noodle", "pasta",
    "rice ", "wheat", "corn ", "maize", "barley", "oat ", "oats",
    "sorghum", "millet", "quinoa", "buckwheat", "rye ",
    "fruit", "apple", "grape", "citrus", "orange", "lemon", "lime",
    "banana", "mango", "papaya", "pineapple", "strawberr", "blueberr",
    "raspberr", "blackberr", "cranberr", "cherry", "cherries",
    "peach", "plum", "apricot", "avocado", "kiwi", "fig ", "figs",
    "pomegranate", "persimmon", "guava", "lychee", "melon", "watermelon",
    "vegetable", "tomato", "potato", "carrot", "onion", "garlic",
    "lettuce", "spinach", "cabbage", "broccoli", "cauliflower",
    "pepper", "chili", "chilli", "cucumber", "zucchini", "pumpkin",
    "mushroom", "truffle",
    "soybean", "soy ", "tofu", "tempeh", "miso",
    "legume", "bean", "lentil", " pea ", "peas", "chickpea",
    "nut ", "nuts", "almond", "walnut", "peanut", "cashew", "pistachio",
    "seed ", "seeds", "sesame", "flaxseed", "chia seed", "sunflower seed",
    "olive oil", "canola oil", "sunflower oil", "palm oil", "coconut oil",
    "cooking oil", "vegetable oil", "edible oil",
    "wine", "beer", "brewing", "juice", "beverage",
    "tea ", " tea,", " tea.", "green tea", "black tea",
    "coffee", "cocoa", "chocolate",
    "honey", "sugar", "sweetener", "sucrose", "glucose", "fructose", "lactose",
    "syrup", "molasses", "jaggery",
    "spice", "herb", "turmeric", "cinnamon", "curcumin",
    "ginger", "saffron", "oregano", "basil", "thyme", "rosemary",
    # ---- Food processing ----
    "shelf life", "shelf-life",
    "pasteuriz", "steriliz", "homogeniz",
    "blanching", "scalding",
    "ferment", "lactic acid bacteria", "sourdough",
    "emulsion", "emulsif", "nanoemulsion", "microemulsion",
    "encapsulat", "microencapsul", "nanoencapsul",
    "extrusion", "extruded",
    "dehydrat", "freeze-dr", "spray-dr", "oven-dr", "sun-dr",
    "osmotic dehydrat",
    "refrigerat", "cold storage", "frozen food", "cold chain",
    "canning", "canned food", "retort",
    "smoking", "smoked food",
    "edible film", "edible coating",
    "food irradiat", "high pressure process", "ohmic heating",
    "ultrasound process", "pulsed electric field",
    "supercritical fluid extract", "supercritical co2",
    "modified atmosphere packag", "active packaging", "intelligent packaging",
    # ---- Food components / bioactives ----
    "polyphenol", "flavonoid", "anthocyanin", "proanthocyanidin",
    "phenolic compound", "phenolic content", "total phenol",
    "tannin", "catechin", "quercetin", "rutin", "resveratrol",
    "antioxidant activity", "antioxidant capacity", "radical scaveng",
    "dpph", "abts", "orac", "frap",
    "pectin", "chitosan", "alginate", "carrageenan",
    "guar gum", "xanthan", "locust bean gum", "arabic gum", "gum arabic",
    "cellulose", "hemicellulose", "lignin",
    "essential oil",
    "bioactive peptide", "bioactive compound",
    "lecithin", "saponin", "alkaloid",
    "prebiotic", "probiotic", "synbiotic", "postbiotic",
    "inulin", "fructooligosaccharide", "galactooligosaccharide",
    # ---- Food safety / toxicology ----
    "salmonella", "listeria", "e. coli", "campylobacter", "clostridium",
    "staphylococcus aureus", "bacillus cereus", "vibrio",
    "mycotoxin", "aflatoxin", "ochratoxin", "fumonisin", "deoxynivalenol",
    "pesticide residue", "heavy metal", "lead contamina", "cadmium",
    "acrylamide", "benzo[a]pyrene", "heterocyclic amine",
    "biogenic amine", "histamine",
    "food contam", "food poison", "food allerg", "allergen",
    "food intoleran", "anaphyla",
    "haccp", "food hygien", "food regulat",
    "maximum residue limit", "acceptable daily intake",
    # ---- Sensory / quality ----
    "sensory", "organoleptic",
    "texture", "mouthfeel", "crispness", "firmness", "hardness",
    "flavor", "flavour", "aroma", "off-flavor", "off-flavour",
    "taste", "bitterness", "sweetness", "umami", "sourness", "saltiness",
    "odor", "odour", "volatile compound",
    "color ", "colour", "browning", "maillard",
    "rheolog", "viscosity", "viscoelastic",
    "water activity", "water holding capacity",
    # ---- Gut / digestive health ----
    "gut microbi", "intestinal microbi", "gut health",
    "gut-brain", "microbiota-gut",
    "gastrointestin", "digest",
    "bioaccessib", "bioavailability of nutrient",
    "bioavailability of iron", "bioavailability of zinc",
    "bioavailability of calcium", "bioavailability of polyphenol",
    "bioavailability of carotenoid", "bioavailability of vitamin",
    # ---- Agriculture / post-harvest ----
    "post-harvest", "postharvest",
    "crop quality", "grain quality",
    "animal feed", "feed additive", "silage",
    "aquaculture", "fishery", "fisheries",
    "edible insect", "entomophagy",
    # ---- Cooking / culinary ----
    "cooking", "culinary", "cuisine", "recipe", "meal plan",
    "frying", "deep-fry", "roasting", "grilling", "boiling", "steaming",
    "sous vide", "microwave cooking",
    "snack", "confection", "candy",
    # ---- Specific analytical methods in food ----
    "food analysis", "food composition",
    "proximate analysis",
    "kjeldahl",  # protein measurement
    "soxhlet",   # fat extraction
    "aw ",        # water activity
]


def _normalize(text):
    """Lowercase and normalize whitespace."""
    return " " + re.sub(r'\s+', ' ', text.lower().strip()) + " "


def is_food_venue(venue):
    """Layer 1: Check if venue/journal is food-related."""
    if not venue:
        return False
    v = venue.lower()
    return any(kw in v for kw in VENUE_WHITELIST)


def is_food_title(title):
    """Layer 2: Check if title contains food-specific terms."""
    if not title:
        return False
    t = _normalize(title)
    return any(kw in t for kw in FOOD_TERMS)


def is_food_keywords(keywords):
    """Layer 3: Check if keywords field contains food-specific terms."""
    if not keywords:
        return False
    k = _normalize(keywords)
    return any(kw in k for kw in FOOD_TERMS)


def filter_file(input_path, output_path, label):
    """Filter a JSONL file, keeping only food-science papers."""
    print(f"\n{'='*60}")
    print(f"Filtering: {label}")
    print(f"{'='*60}")
    sys.stdout.flush()

    total = 0
    kept = 0
    removed = 0
    match_layers = Counter()  # which layer(s) matched
    removed_venues = Counter()
    removed_concepts = Counter()
    removed_samples = []

    with open(input_path, "r", encoding="utf-8") as f_in, \
         open(output_path, "w", encoding="utf-8") as f_out:

        for line in f_in:
            doc = json.loads(line.strip())
            total += 1

            venue = doc.get("venue", "")
            title = doc.get("title", "")
            keywords = doc.get("keywords", "")

            l1 = is_food_venue(venue)
            l2 = is_food_title(title)
            l3 = is_food_keywords(keywords)

            if l1 or l2 or l3:
                kept += 1
                f_out.write(line)
                # Track which layer(s) matched
                layers = []
                if l1: layers.append("venue")
                if l2: layers.append("title")
                if l3: layers.append("keywords")
                match_layers["+".join(layers)] += 1
            else:
                removed += 1
                if venue:
                    removed_venues[venue] += 1
                removed_concepts[doc.get("primary_concept", "")] += 1
                if len(removed_samples) < 15:
                    removed_samples.append({
                        "title": title[:80],
                        "venue": venue[:50],
                        "concept": doc.get("primary_concept", ""),
                    })

            if total % 50000 == 0:
                print(f"  Processed: {total:,} (kept: {kept:,}, removed: {removed:,})")
                sys.stdout.flush()

    pct_kept = kept / total * 100 if total else 0
    print(f"\nResults:")
    print(f"  Total: {total:,}")
    print(f"  Kept: {kept:,} ({pct_kept:.1f}%)")
    print(f"  Removed: {removed:,} ({100-pct_kept:.1f}%)")

    print(f"\nMatch layer breakdown:")
    for layers, count in match_layers.most_common():
        print(f"  {count:>8,}  {layers}")

    print(f"\nTop removed venues:")
    for v, c in removed_venues.most_common(15):
        print(f"  {c:>6,}  {v[:60]}")

    print(f"\nTop removed concepts:")
    for c, n in removed_concepts.most_common(10):
        print(f"  {n:>6,}  {c}")

    print(f"\nSample removed papers:")
    for s in removed_samples:
        print(f"  [{s['concept']}] {s['title']}")
        print(f"    Venue: {s['venue']}")

    sys.stdout.flush()
    return {"total": total, "kept": kept, "removed": removed,
            "match_layers": dict(match_layers)}


def main():
    print("=" * 60)
    print("FoodmoleGPT - Dataset Quality Filter")
    print("=" * 60)
    sys.stdout.flush()
    start = datetime.now()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    stats = []

    if MERGED_FULLTEXT.exists():
        s = filter_file(MERGED_FULLTEXT, FILTERED_FULLTEXT, "Full Text (312K)")
        stats.append(("fulltext", s))

    if MERGED_ABSTRACT.exists():
        s = filter_file(MERGED_ABSTRACT, FILTERED_ABSTRACT, "Abstract Only (408K)")
        stats.append(("abstract", s))

    # Summary
    elapsed = datetime.now() - start
    total_kept = sum(s["kept"] for _, s in stats)
    total_removed = sum(s["removed"] for _, s in stats)
    total_all = sum(s["total"] for _, s in stats)

    report_lines = [
        "=" * 60,
        "FoodmoleGPT - Filter Report",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "=" * 60,
        "",
        "OVERALL SUMMARY",
        "-" * 40,
        f"Total papers:    {total_all:>10,}",
        f"Kept (food):     {total_kept:>10,} ({total_kept/total_all*100:.1f}%)",
        f"Removed:         {total_removed:>10,} ({total_removed/total_all*100:.1f}%)",
        "",
    ]
    for label, s in stats:
        report_lines.extend([
            f"DATASET: {label.upper()}",
            "-" * 40,
            f"  Total:    {s['total']:>10,}",
            f"  Kept:     {s['kept']:>10,} ({s['kept']/s['total']*100:.1f}%)",
            f"  Removed:  {s['removed']:>10,} ({s['removed']/s['total']*100:.1f}%)",
            "",
        ])

    report_lines.extend([
        "OUTPUT FILES",
        "-" * 40,
        f"  {FILTERED_FULLTEXT}",
        f"  {FILTERED_ABSTRACT}",
        "",
        f"Elapsed: {elapsed}",
        "=" * 60,
    ])

    report = "\n".join(report_lines)
    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"\n{report}")
    print("\n[DONE] Filter complete!")
    sys.stdout.flush()


if __name__ == "__main__":
    main()
