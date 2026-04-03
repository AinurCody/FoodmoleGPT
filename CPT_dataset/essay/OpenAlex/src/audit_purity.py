"""Tier-specific purity audit."""
import sys, json, re, random
from collections import Counter
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

random.seed(99)

FOOD_TERMS = [
    r'\bfood\b', r'\bnutrition\b', r'\bnutrient\b', r'\bdietary\b', r'\bdiet\b',
    r'\bcooking\b', r'\bbaking\b', r'\bfrying\b', r'\bferment', r'\bpasteuriz',
    r'\bprotein\b', r'\blipid\b', r'\bfat\b', r'\bcarbohydrate\b', r'\bstarch\b',
    r'\bcellulose\b', r'\bpectin\b', r'\bpolysaccharide\b', r'\bchitin\b', r'\bchitosan\b',
    r'\bantioxidant\b', r'\bpolyphenol\b', r'\bflavonoid\b', r'\bvitamin\b',
    r'\bphenolic\b', r'\bcarotenoid\b', r'\btocopherol\b', r'\bascorbic\b',
    r'\bmilk\b', r'\bcheese\b', r'\byogurt\b', r'\bdairy\b', r'\bwhey\b', r'\bcasein\b',
    r'\bmeat\b', r'\bbeef\b', r'\bpork\b', r'\bchicken\b', r'\bpoultry\b', r'\bsausage\b',
    r'\bfish\b', r'\bseafood\b', r'\bshrimp\b', r'\bsalmon\b', r'\baquaculture\b',
    r'\bfruit\b', r'\bvegetable\b', r'\brice\b', r'\bwheat\b', r'\bmaize\b', r'\bcorn\b',
    r'\bsoybean\b', r'\bolive\b', r'\btomato\b', r'\bpotato\b', r'\bgrape\b',
    r'\bbread\b', r'\bflour\b', r'\bcereal\b', r'\bgrain\b', r'\bbarley\b', r'\boat\b',
    r'\bbeverage\b', r'\bwine\b', r'\bbeer\b', r'\bjuice\b', r'\btea\b', r'\bcoffee\b',
    r'\bchocolate\b', r'\bcocoa\b', r'\bsugar\b', r'\bhoney\b', r'\bsyrup\b',
    r'\bpackaging\b', r'\bshelf.life\b', r'\bspoilage\b', r'\bpreservat',
    r'\bpathogen\b', r'\bsalmonella\b', r'\blisteria\b', r'\be\.?\s*coli\b',
    r'\baflatoxin\b', r'\bmycotoxin\b', r'\bpesticide\b', r'\bcontaminat',
    r'\bfood.safety\b', r'\bhaccp\b', r'\bfoodborne\b',
    r'\bemulsion\b', r'\bencapsulat', r'\bgel\b', r'\bhydrogel\b', r'\bnanoparticle\b',
    r'\brheolog', r'\btextur', r'\bviscos', r'\bsensor[iy]\b',
    r'\bprobiotic\b', r'\bprebiotic\b', r'\bgut\b', r'\bmicrobiome\b', r'\bmicrobiota\b',
    r'\bobesity\b', r'\bdiabetes\b', r'\bcholesterol\b', r'\bglycemic\b',
    r'\bdrying\b', r'\bfreeze.dry', r'\bspray.dry', r'\bextrusion\b', r'\bhigh.pressure\b',
    r'\bextract', r'\bessential.oil\b', r'\baroma\b', r'\bflavor\b', r'\bflavour\b',
    r'\bbioactive\b', r'\bbioaccessib', r'\bdigestib',
    r'\banimal.science\b', r'\blivestock\b', r'\bfeed\b', r'\bbroiler\b',
    r'\bruminant\b', r'\bswine\b', r'\bcattle\b', r'\begg\b',
    r'\bcrop\b', r'\bharvest\b', r'\bpost.harvest\b', r'\bstor(?:age|ed|ing)\b',
    r'\birradiat', r'\bultrasound\b', r'\bmicrowave\b',
    r'\bgluten\b', r'\ballergen\b', r'\blactose\b',
    r'\bfunctional.food\b', r'\bnutraceutical\b', r'\bsupplement\b',
]
FOOD_RE = re.compile('|'.join(FOOD_TERMS), re.IGNORECASE)

JOURNAL_TIER = {
    "Journal of Agricultural and Food Chemistry": "Q1", "Food Chemistry": "Q1",
    "Journal of Animal Science": "Q1", "Nutrients": "Q1", "Journal of Dairy Science": "Q1",
    "Poultry Science": "Q1", "Aquaculture": "Q1", "Journal of Nutrition": "Q1",
    "Journal of Food Science": "Q1", "Foods": "Q1",
    "Journal of the Science of Food and Agriculture": "Q1", "Carbohydrate Polymers": "Q1",
    "American Journal of Clinical Nutrition": "Q1", "LWT": "Q1",
    "Food Research International": "Q1", "British Journal Of Nutrition": "Q1",
    "Food and Chemical Toxicology": "Q1", "Food Hydrocolloids": "Q1",
    "Food Control": "Q1", "Journal of Food Engineering": "Q1",
    "International Journal of Food Microbiology": "Q1", "Meat Science": "Q1",
    "Food & Function": "Q1", "Food Bioscience": "Q1",
    "Journal of Food Composition and Analysis": "Q1",
    "European Food Research and Technology": "Q1",
    "Journal of Functional Foods": "Q1", "Postharvest Biology and Technology": "Q1",
    "Nutrition Research": "Q1", "The Journal of Nutritional Biochemistry": "Q1",
    "International Dairy Journal": "Q1", "Journal of Cereal Science": "Q1",
    "Trends in Food Science & Technology": "Q1",
    "Critical Reviews in Food Science and Nutrition": "Q1",
    "Food Quality and Preference": "Q1", "European Journal of Nutrition": "Q1",
    "Food and Bioprocess Technology": "Q1",
    "Innovative Food Science & Emerging Technologies": "Q1",
    "Food Chemistry X": "Q1", "International Journal of Food Sciences and Nutrition": "Q1",
    "Food Science and Human Wellness": "Q1", "Food Packaging and Shelf Life": "Q1",
    "Comprehensive Reviews in Food Science and Food Safety": "Q1",
    "Current Research in Food Science": "Q1", "Food Reviews International": "Q1",
    "Food Frontiers": "Q1", "Advances in food and nutrition research": "Q1",
}

RE_TITLE = re.compile(r'^Title: (.+)$', re.MULTILINE)
RE_VENUE = re.compile(r'^Venue: (.+)$', re.MULTILINE)
RE_KW = re.compile(r'^Keywords: (.+)$', re.MULTILINE)

FT = 'D:/FoodmoleGPT/data/training_combined/fulltext_train.jsonl'
AB = 'D:/FoodmoleGPT/data/training_combined/abstract_train.jsonl'

def scan_and_audit(path, sample_per_tier, label):
    """Single-pass: classify into tiers, sample, audit."""
    # Collect records by tier
    by_tier = {"Q1": [], "unknown": []}
    with open(path, 'r', encoding='utf-8') as f:
        for i, line in enumerate(f):
            doc = json.loads(line.strip())
            text = doc['text']
            vm = RE_VENUE.search(text)
            venue = vm.group(1).strip() if vm else ''
            tier = JOURNAL_TIER.get(venue)
            if tier == 'Q1':
                by_tier['Q1'].append(i)
            elif tier is None:
                by_tier['unknown'].append(i)

    # Sample from each tier
    results = {}
    for tier_name, indices in by_tier.items():
        n = min(sample_per_tier, len(indices))
        sampled = set(random.sample(indices, n))

        food_match = 0
        non_food = []
        with open(path, 'r', encoding='utf-8') as f:
            for i, line in enumerate(f):
                if i not in sampled:
                    continue
                doc = json.loads(line.strip())
                text = doc['text']
                tm = RE_TITLE.search(text)
                vm = RE_VENUE.search(text)
                km = RE_KW.search(text)
                combined = ""
                if tm: combined += tm.group(1) + " "
                if vm: combined += vm.group(1) + " "
                if km: combined += km.group(1)
                if FOOD_RE.search(combined):
                    food_match += 1
                else:
                    t = tm.group(1)[:80] if tm else '?'
                    v = vm.group(1) if vm else '?'
                    non_food.append((t, v))

        pct = food_match / n * 100 if n > 0 else 0
        results[tier_name] = (len(indices), n, food_match, pct, non_food)
        print(f"\n  {label} [{tier_name}]: {len(indices):,} total, sampled {n}")
        print(f"    Food match: {food_match} / {n} ({pct:.1f}%)")
        if non_food[:5]:
            for t, v in non_food[:5]:
                print(f"      [{v}] {t}")

    return results

print("=" * 60)
print("TIER-SPECIFIC PURITY AUDIT")
print("=" * 60)

r1 = scan_and_audit(FT, 1000, "fulltext_train")
r2 = scan_and_audit(AB, 1500, "abstract_train")

# Summary
q1_sampled = r1['Q1'][1] + r2['Q1'][1]
q1_match = r1['Q1'][2] + r2['Q1'][2]
unk_sampled = r1['unknown'][1] + r2['unknown'][1]
unk_match = r1['unknown'][2] + r2['unknown'][2]

print(f"\n{'='*60}")
print(f"Q1 PURITY:       {q1_match} / {q1_sampled} ({q1_match/q1_sampled*100:.1f}%)")
print(f"UNKNOWN PURITY:  {unk_match} / {unk_sampled} ({unk_match/unk_sampled*100:.1f}%)")
print(f"{'='*60}")
