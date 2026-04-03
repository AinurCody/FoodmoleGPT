#!/usr/bin/env python3
"""
Crawl food safety regulatory content from FDA, EFSA, and SFA using FireCrawl API.
Saves markdown content for RAG indexing.
"""

import os
import json
import time
import hashlib
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
from firecrawl import FirecrawlApp

# ── Config ────────────────────────────────────────────────────────────────────
load_dotenv()
API_KEY = os.getenv("FIRECRAWL_API_KEY", "")
if not API_KEY:
    raise RuntimeError("FIRECRAWL_API_KEY not set. Add it to .env or export it.")
OUTPUT_DIR = Path(__file__).parent
SCRAPE_OPTS = {"formats": ["markdown"]}
DELAY = 2  # seconds between requests to stay under rate limits

app = FirecrawlApp(api_key=API_KEY)

# ── Target URLs ───────────────────────────────────────────────────────────────
# Each entry: (agency, category, url)
TARGETS = [
    # ======================= FDA (US) =======================
    # FSMA - Food Safety Modernization Act
    ("FDA", "FSMA", "https://www.fda.gov/food/food-safety-modernization-act-fsma/full-text-food-safety-modernization-act-fsma"),
    ("FDA", "FSMA_Preventive_Controls_Human", "https://www.fda.gov/food/food-safety-modernization-act-fsma/fsma-final-rule-preventive-controls-human-food"),
    ("FDA", "FSMA_Preventive_Controls_Animal", "https://www.fda.gov/food/food-safety-modernization-act-fsma/fsma-final-rule-preventive-controls-animal-food"),
    ("FDA", "FSMA_Produce_Safety", "https://www.fda.gov/food/food-safety-modernization-act-fsma/fsma-final-rule-standards-produce-safety"),
    ("FDA", "FSMA_Foreign_Supplier", "https://www.fda.gov/food/food-safety-modernization-act-fsma/fsma-final-rule-foreign-supplier-verification-programs"),
    ("FDA", "FSMA_Sanitary_Transport", "https://www.fda.gov/food/food-safety-modernization-act-fsma/fsma-final-rule-sanitary-transportation-human-and-animal-food"),
    ("FDA", "FSMA_Intentional_Adulteration", "https://www.fda.gov/food/food-safety-modernization-act-fsma/fsma-final-rule-mitigation-strategies-protect-food-against-intentional-adulteration"),
    # HACCP
    ("FDA", "HACCP_Overview", "https://www.fda.gov/food/guidance-regulation-food-and-dietary-supplements/hazard-analysis-critical-control-point-haccp"),
    ("FDA", "HACCP_Principles", "https://www.fda.gov/food/haccp-principles-application-guidelines/haccp-principles-application-guidelines"),
    # Food Additives
    ("FDA", "Food_Additives_Overview", "https://www.fda.gov/food/food-ingredients-packaging/food-additives-petitions"),
    ("FDA", "Color_Additives", "https://www.fda.gov/industry/color-additives"),
    ("FDA", "GRAS_Overview", "https://www.fda.gov/food/food-ingredients-packaging/generally-recognized-safe-gras"),
    # CGMP
    ("FDA", "CGMP", "https://www.fda.gov/food/guidance-regulation-food-and-dietary-supplements/current-good-manufacturing-practices-cgmps-food-and-dietary-supplements"),
    # Labeling
    ("FDA", "Food_Labeling", "https://www.fda.gov/food/food-labeling-nutrition/food-labeling-guide"),
    ("FDA", "Nutrition_Facts_Label", "https://www.fda.gov/food/food-labeling-nutrition/changes-nutrition-facts-label"),
    # Allergens
    ("FDA", "Food_Allergens", "https://www.fda.gov/food/food-allergies/food-allergen-labeling-and-consumer-protection-act-2004-questions-and-answers"),
    # Contaminants
    ("FDA", "Chemical_Contaminants", "https://www.fda.gov/food/chemicals-metals-pesticides-food/chemical-contaminants"),
    ("FDA", "Pesticides", "https://www.fda.gov/food/chemicals-metals-pesticides-food/pesticides"),
    ("FDA", "Heavy_Metals", "https://www.fda.gov/food/chemicals-metals-pesticides-food/metals-and-your-food"),
    # Dietary Supplements
    ("FDA", "Dietary_Supplements", "https://www.fda.gov/food/dietary-supplements"),

    # ======================= EFSA (EU) =======================
    # Food Additives
    ("EFSA", "Additives_Overview", "https://www.efsa.europa.eu/en/topics/topic/food-additives"),
    ("EFSA", "Safety_Assessment_Additives", "https://www.efsa.europa.eu/en/topics/topic/safety-assessment-food-additives"),
    # Contaminants
    ("EFSA", "Contaminants", "https://www.efsa.europa.eu/en/topics/topic/contaminants-food-and-feed"),
    ("EFSA", "Acrylamide", "https://www.efsa.europa.eu/en/topics/topic/acrylamide"),
    ("EFSA", "PFAS", "https://www.efsa.europa.eu/en/topics/topic/per-and-polyfluoroalkyl-substances-pfas"),
    ("EFSA", "Mycotoxins", "https://www.efsa.europa.eu/en/topics/topic/mycotoxins"),
    # Novel Foods
    ("EFSA", "Novel_Foods", "https://www.efsa.europa.eu/en/topics/topic/novel-food"),
    # Nutrition
    ("EFSA", "Nutrition", "https://www.efsa.europa.eu/en/topics/topic/nutrition"),
    ("EFSA", "Health_Claims", "https://www.efsa.europa.eu/en/topics/topic/health-claims"),
    # Biological Hazards
    ("EFSA", "Biological_Hazards", "https://www.efsa.europa.eu/en/topics/topic/biological-hazards"),
    ("EFSA", "Salmonella", "https://www.efsa.europa.eu/en/topics/topic/salmonella"),
    ("EFSA", "Listeria", "https://www.efsa.europa.eu/en/topics/topic/listeria"),
    # Pesticides
    ("EFSA", "Pesticides", "https://www.efsa.europa.eu/en/topics/topic/pesticides"),
    # GMO
    ("EFSA", "GMO", "https://www.efsa.europa.eu/en/topics/topic/gmo"),
    # Food Contact Materials
    ("EFSA", "Food_Contact_Materials", "https://www.efsa.europa.eu/en/topics/topic/food-contact-materials"),

    # ======================= SFA (Singapore) =======================
    ("SFA", "Food_Safety", "https://www.sfa.gov.sg/food-information/risk-at-a-glance"),
    ("SFA", "Food_Regulations", "https://www.sfa.gov.sg/food-information/food-regulations"),
    ("SFA", "Food_Additives", "https://www.sfa.gov.sg/food-information/food-regulations/food-additives"),
    ("SFA", "Food_Labelling", "https://www.sfa.gov.sg/food-information/food-regulations/food-labelling-guidelines"),
    ("SFA", "Import_Export", "https://www.sfa.gov.sg/food-import-export"),
    ("SFA", "Food_Standards", "https://www.sfa.gov.sg/food-information/food-regulations/food-standards"),
    ("SFA", "Contaminants_Limits", "https://www.sfa.gov.sg/food-information/food-regulations/maximum-levels-of-contaminants"),
    ("SFA", "Microbiological_Standards", "https://www.sfa.gov.sg/food-information/food-regulations/microbiological-standards-for-food"),
    ("SFA", "Pesticide_MRLs", "https://www.sfa.gov.sg/food-information/food-regulations/maximum-residue-limits-for-pesticides"),
    ("SFA", "Novel_Food", "https://www.sfa.gov.sg/food-information/risk-at-a-glance/novel-food"),
]

# ── Helpers ────────────────────────────────────────────────────────────────────
def safe_filename(agency: str, category: str) -> str:
    return f"{agency}_{category}.md"

def doc_id(url: str) -> str:
    return hashlib.md5(url.encode()).hexdigest()[:12]

def scrape_one(agency: str, category: str, url: str) -> dict | None:
    """Scrape a single URL, return metadata dict or None on failure."""
    fname = safe_filename(agency, category)
    outpath = OUTPUT_DIR / agency.lower() / fname
    outpath.parent.mkdir(parents=True, exist_ok=True)

    if outpath.exists() and outpath.stat().st_size > 100:
        print(f"  ⏭ SKIP (exists): {fname}")
        return None

    try:
        result = app.scrape(url, formats=["markdown"])
        md = result.markdown or ""
        title = (getattr(result.metadata, "title", None) or category).strip() if result.metadata else category

        if not md or len(md.strip()) < 50:
            print(f"  ⚠ EMPTY: {url}")
            return None

        # Write markdown file
        header = f"---\nsource: {agency}\ncategory: {category}\nurl: {url}\ntitle: {title}\nscraped_at: {datetime.now().isoformat()}\n---\n\n"
        outpath.write_text(header + md, encoding="utf-8")

        info = {
            "agency": agency,
            "category": category,
            "url": url,
            "title": title,
            "file": str(outpath.relative_to(OUTPUT_DIR)),
            "chars": len(md),
            "doc_id": doc_id(url),
        }
        print(f"  ✅ {fname} ({len(md):,} chars)")
        return info

    except Exception as e:
        print(f"  ❌ FAIL: {url} — {e}")
        return None

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print(f"FoodmoleGPT RAG — Regulatory Content Crawler")
    print(f"Targets: {len(TARGETS)} pages across FDA/EFSA/SFA")
    print(f"Output:  {OUTPUT_DIR}")
    print("=" * 60)

    results = []
    for i, (agency, category, url) in enumerate(TARGETS, 1):
        print(f"[{i}/{len(TARGETS)}] {agency}/{category}")
        info = scrape_one(agency, category, url)
        if info:
            results.append(info)
        if i < len(TARGETS):
            time.sleep(DELAY)

    # Write manifest
    manifest_path = OUTPUT_DIR / "manifest.json"
    manifest = {
        "scraped_at": datetime.now().isoformat(),
        "total_pages": len(results),
        "total_chars": sum(r["chars"] for r in results),
        "by_agency": {},
        "documents": results,
    }
    for agency in ["FDA", "EFSA", "SFA"]:
        agency_docs = [r for r in results if r["agency"] == agency]
        manifest["by_agency"][agency] = {
            "pages": len(agency_docs),
            "chars": sum(r["chars"] for r in agency_docs),
        }
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    print("\n" + "=" * 60)
    print(f"Done! Scraped {len(results)} pages")
    for agency in ["FDA", "EFSA", "SFA"]:
        a = manifest["by_agency"].get(agency, {})
        print(f"  {agency}: {a.get('pages', 0)} pages, {a.get('chars', 0):,} chars")
    print(f"\nManifest: {manifest_path}")

if __name__ == "__main__":
    main()
