#!/usr/bin/env python3
"""
Precision Food Relevance Filter — Dry-Run + Execute
=====================================================
Enhanced anchor vocabulary covering dietary interventions, nutrient intake,
supplementation, and food-adjacent nutrition research.
"""

import json
import re
import sys
from pathlib import Path
from collections import Counter

CORPUS = Path("data/processed/filtered/food_science_corpus.keep.jsonl")
DRY_RUN = "--execute" not in sys.argv

# ─── Food anchor patterns (case-insensitive) ───
FOOD_ANCHORS = [
    # === Core food terms ===
    r"\bfood\b", r"\bfoods\b", r"\bdiet\b", r"\bdiets\b", r"\bdietary\b",
    r"\bnutrition\b", r"\bnutritional\b", r"\bnutrient\b", r"\bnutrients\b",
    r"\bmeal\b", r"\bmeals\b", r"\beating\b", r"\bfeed\b", r"\bfeeding\b",
    
    # === Dietary interventions & intake (covers Nutrients journal) ===
    r"\bsupplement", r"\bintake\b", r"\bconsumption\b", r"\bingestion\b",
    r"\boral\b.*\badminist", r"\bbioavailab",
    r"\bcalori", r"\benergy.?intake", r"\bappetite\b",
    r"\bfortifi", r"\benrich",  # food fortification
    r"\bdose.?response", r"\bdosage\b",
    r"\bRDA\b", r"\brecommended.?daily",
    r"\bnutriti.*\bstatus\b", r"\bnutriti.*\bdeficien",
    r"\bundernutrition\b", r"\bmalnutrition\b", r"\bovernutrition\b",
    r"\bwean\b", r"\bbreastfe", r"\bbottle.?fe", r"\binfant.?feed",
    r"\bcomplementary.?feed",
    
    # === Food categories ===
    r"\bdairy\b", r"\bmeat\b", r"\bbeef\b", r"\bpork\b", r"\blamb\b",
    r"\bpoultry\b", r"\bchicken\b", r"\bseafood\b", r"\bfish\b", r"\bshrimp\b",
    r"\bvegetable\b", r"\bfruit\b", r"\blegume\b", r"\bbean\b", r"\blentil\b",
    r"\bcereal\b", r"\bgrain\b", r"\bwhole.?grain",
    r"\bbeverage\b", r"\bmilk\b", r"\bcheese\b", r"\byogurt\b",
    r"\bbread\b", r"\brice\b", r"\bwheat\b", r"\bmaize\b", r"\bcorn\b",
    r"\bsoybean\b", r"\bsoy\b", r"\btea\b", r"\bcoffee\b", r"\bcaffeine\b",
    r"\bwine\b", r"\bbeer\b", r"\balcohol\b", r"\bjuice\b",
    r"\begg\b", r"\bhoney\b", r"\bchocolate\b", r"\bcocoa\b",
    r"\bolive\b", r"\bspice\b", r"\bherb\b", r"\bgarlic\b", r"\bginger\b",
    r"\bturmeric\b", r"\bcurcumin\b", r"\bnut\b", r"\bnuts\b",
    r"\bsugar\b", r"\bsalt\b", r"\bvinegar\b", r"\boil\b",
    r"\bsnack\b", r"\bprocessed.?food", r"\bultra.?processed",
    r"\bjunk.?food", r"\bfast.?food", r"\bsoft.?drink",
    
    # === Food science topics ===
    r"\bferment", r"\bflavo[u]?r\b", r"\bsensory\b", r"\btaste\b", r"\baroma\b",
    r"\bcooking\b", r"\bculinary\b", r"\brecipe\b", r"\bbaking\b",
    r"\bfoodborne\b", r"\bfood.?safe", r"\bshelf.?life\b", r"\bspoilage\b",
    r"\bpreservat", r"\bfood.?process", r"\bfood.?packag",
    r"\bfood.?industry\b", r"\bfood.?product",
    r"\bfood.?quality\b", r"\bfood.?secur",
    
    # === Agriculture & crops ===
    r"\bagricult", r"\bcrop\b", r"\bcrops\b", r"\bharvest",
    r"\blivestock\b", r"\baquaculture\b",
    r"\bfarm\b", r"\bfarming\b", r"\borchard\b",
    r"\birrigation\b", r"\bpesticide\b", r"\bherbicide\b",
    r"\borganic.?farm",
    
    # === Food compounds & nutrients ===
    r"\bantioxidant", r"\bphenolic\b", r"\bpolyphenol", r"\bvitamin\b",
    r"\bfatty.?acid", r"\bomega.?3\b", r"\bcarotenoid", r"\bflavonoid",
    r"\banthocyanin", r"\bprobiotic", r"\bprebiotic", r"\bsynbiotic",
    r"\bfiber\b", r"\bfibre\b", r"\bdietary.?fiber",
    r"\bprotein\b", r"\bamino.?acid", r"\bpeptide\b",
    r"\bcarbohydrate", r"\bstarch\b", r"\bgluten\b",
    r"\blactose\b", r"\bsucrose\b", r"\bfructose\b", r"\bglucose\b",
    r"\bascorbic\b", r"\bfolic.?acid\b", r"\bfolate\b",
    r"\biron\b.*\bdeficien", r"\bzinc\b.*\bdeficien",
    r"\bcalcium\b", r"\bmagnesium\b", r"\bselenium\b", r"\biodine\b",
    r"\bcholesterol\b", r"\btriglyceride\b",
    r"\bDHA\b", r"\bEPA\b",
    r"\blycopene\b", r"\bresveratrol\b", r"\bquercetin\b",
    r"\bcapsaicin\b", r"\bsulforaphane\b",
    r"\bbioactive\b", r"\bnueutrical\b", r"\bneutraceutical\b", r"\bnueutrical\b",
    r"\bfunctional.?food\b",
    
    # === Broader nutrition & health ===
    r"\bobesi", r"\boverweight\b", r"\bBMI\b", r"\bbody.?mass",
    r"\bweight.?loss\b", r"\bweight.?gain\b", r"\bweight.?manage",
    r"\bgut.?microbio", r"\bintestinal.?microbio", r"\bgut.?flora\b",
    r"\bdysbiosis\b",
    r"\bmycotoxin", r"\baflatoxin",
    r"\bcontaminat", r"\badulter", r"\bHACCP\b",
    r"\bplant.?based\b", r"\bvegan\b", r"\bvegetarian\b",
    r"\bedible\b", r"\binsect.*\bfood\b",
    r"\bencapsulat", r"\bemulsio", r"\bhydrocolloid",
    r"\bfood.*nanoparticle", r"\bnanoparticle.*food",
    r"\bglycemic\b", r"\bglycaemic\b", r"\bpostprandial\b",
    r"\bsatiety\b", r"\bhunger\b",
    r"\banemia\b", r"\banaemia\b",  # nutritional anemia
    r"\bmetabolic.?syndrome\b", r"\binsulin.?resistan",
    r"\bdiabetes.*diet\b", r"\bdiet.*diabetes\b",
    r"\bcardiovascular.*diet\b", r"\bdiet.*cardiovascular\b",
    
    # === Specific food-related MeSH ===
    r"\bfood.?hyper", r"\bfood.?allerg",
    r"\bceliac\b", r"\bcoeliac\b",
    r"\blactose.?intoler",
    r"\bGMO\b", r"\btransgenic\b",
]

FOOD_RE = re.compile("|".join(FOOD_ANCHORS), re.IGNORECASE)

# Journal-based food relevance (if no text anchor found, check journal)
FOOD_JOURNAL_KEYWORDS = [
    "food", "nutriti", "diet", "dairy", "meat", "cereal", "beverage",
    "appetite", "toxin", "agric", "animal", "poultry", "fish",
    "aquaculture", "plant", "crop", "ferment", "flavor", "flavour",
    "antioxidant", "molecule", "polymer", "sensor", "microorganism",
    "microbiol", "biotechnol", "environ", "public health",
    "veterinar", "chem", "bio",
]

mode = "DRY-RUN" if DRY_RUN else "EXECUTE"
print(f"{'=' * 70}")
print(f"Precision Food Relevance Filter [{mode}]")
print(f"{'=' * 70}")
print(f"Anchor patterns: {len(FOOD_ANCHORS)}")

total = 0
kept_docs = []
flagged = []
journal_saved = 0

with open(CORPUS, encoding="utf-8") as f:
    for line in f:
        doc = json.loads(line)
        total += 1

        title = doc.get("title", "")
        abstract = doc.get("abstract", "")
        keywords = " ".join(doc.get("keywords", []))
        journal = doc.get("journal", "")

        search_text = f"{title} {abstract} {keywords}"
        if FOOD_RE.search(search_text):
            kept_docs.append(line)
            continue

        j_lower = journal.lower()
        if any(kw in j_lower for kw in FOOD_JOURNAL_KEYWORDS):
            kept_docs.append(line)
            journal_saved += 1
            continue

        flagged.append({
            "pmcid": doc.get("pmcid", ""),
            "title": title[:120],
            "journal": journal,
        })

        if total % 50000 == 0:
            print(f"  Processed {total:,}...")

kept_count = total - len(flagged)
print(f"\n{'=' * 70}")
print(f"RESULTS")
print(f"{'=' * 70}")
print(f"Total:    {total:,}")
print(f"Kept:     {kept_count:,} ({kept_count/total*100:.2f}%)")
print(f"  (journal saved: {journal_saved:,})")
print(f"Flagged:  {len(flagged):,} ({len(flagged)/total*100:.2f}%)")

# Top journals of flagged
fj = Counter(d["journal"] for d in flagged)
print(f"\nTop flagged journals:")
for j, c in fj.most_common(15):
    print(f"  {c:>5,}  {j}")

# Sample
print(f"\nSample flagged (first 20):")
for i, d in enumerate(flagged[:20], 1):
    print(f"  {i:2d}. [{d['pmcid']}] {d['title']}")
    print(f"      Journal: {d['journal']}")

# Save flagged list
out = Path("data/processed/filtered/precision_filter_flagged.jsonl")
with open(out, "w") as f:
    for d in flagged:
        f.write(json.dumps(d, ensure_ascii=False) + "\n")
print(f"\nFlagged list: {out}")

if not DRY_RUN:
    import shutil
    bak = CORPUS.with_suffix(".pre_relevance_filter.bak")
    print(f"\nBacking up to {bak.name}...")
    shutil.copy2(CORPUS, bak)
    
    print(f"Writing cleaned corpus...")
    with open(CORPUS, "w", encoding="utf-8") as f:
        for line in kept_docs:
            f.write(line)
    
    import os
    new_size = os.path.getsize(CORPUS)
    print(f"Done! {kept_count:,} articles, {new_size/1e9:.2f} GB")
else:
    print(f"\n[DRY-RUN] No changes made. Re-run with --execute to apply.")
