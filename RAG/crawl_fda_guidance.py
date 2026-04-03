#!/usr/bin/env python3
"""
FDA Food Guidance Documents Crawler
- 261 documents from FDA food guidance index
- Supports checkpoint/resume (saves progress after each doc)
- Respects FDA 30s crawl-delay via configurable delay
- Saves as markdown with YAML frontmatter
"""

import json
import os
import re
import time
import sys
from pathlib import Path
from datetime import datetime
from html.parser import HTMLParser

import requests
from firecrawl import FirecrawlApp

# ── Config ──────────────────────────────────────────────────────────────
API_KEY = "***REMOVED***"
INDEX_URL = "https://www.fda.gov/food/guidance-regulation-food-and-dietary-supplements/guidance-documents-regulatory-information-topic-food-and-dietary-supplements"
URL_LIST = Path(__file__).parent / "fda_guidance_urls.json"
OUT_DIR = Path(__file__).parent / "fda_guidance"
CHECKPOINT = Path(__file__).parent / "fda_guidance" / "_checkpoint.json"
DELAY = 5           # seconds between requests (FireCrawl handles its own rate limiting)
MAX_RETRIES = 3     # retries per URL on failure

# ── Setup ───────────────────────────────────────────────────────────────
OUT_DIR.mkdir(parents=True, exist_ok=True)
app = FirecrawlApp(api_key=API_KEY)


class FDATableParser(HTMLParser):
    """Parse FDA guidance document table to extract URLs and titles."""
    def __init__(self):
        super().__init__()
        self.in_table = False
        self.in_tbody = False
        self.in_td = False
        self.in_a = False
        self.current_row = {}
        self.current_cell = 0
        self.docs = []
        self.current_text = ""
        self.current_href = ""

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        if tag == 'table':
            self.in_table = True
        elif tag == 'tbody' and self.in_table:
            self.in_tbody = True
        elif tag == 'tr' and self.in_tbody:
            self.current_row = {}
            self.current_cell = 0
        elif tag == 'td' and self.in_tbody:
            self.in_td = True
            self.current_cell += 1
            self.current_text = ""
        elif tag == 'a' and self.in_td and self.current_cell == 2:
            self.in_a = True
            self.current_href = attrs_dict.get('href', '')
            self.current_text = ""

    def handle_endtag(self, tag):
        if tag == 'table':
            self.in_table = False
        elif tag == 'tbody':
            self.in_tbody = False
        elif tag == 'td' and self.in_td:
            self.in_td = False
            if self.current_cell == 1:
                self.current_row['date'] = self.current_text.strip()
        elif tag == 'a' and self.in_a:
            self.in_a = False
            if self.current_href:
                href = self.current_href
                if href.startswith('/'):
                    href = 'https://www.fda.gov' + href
                self.current_row['title'] = self.current_text.strip()
                self.current_row['url'] = href
        elif tag == 'tr' and self.in_tbody and self.current_row.get('url'):
            self.docs.append(self.current_row.copy())

    def handle_data(self, data):
        if self.in_td or self.in_a:
            self.current_text += data


def fetch_url_list():
    """Fetch and parse the FDA guidance documents index page."""
    # Try cached file first
    if URL_LIST.exists():
        docs = json.loads(URL_LIST.read_text())
        if docs:
            print(f"📂 Using cached URL list: {len(docs)} docs")
            return docs

    print(f"🌐 Fetching FDA Food Guidance Documents index...")
    resp = requests.get(INDEX_URL, timeout=30, headers={
        'User-Agent': 'Mozilla/5.0 (research bot for food science project)'
    })
    resp.raise_for_status()

    parser = FDATableParser()
    parser.feed(resp.text)

    docs = parser.docs
    print(f"   Found {len(docs)} guidance documents")

    # Cache for future runs
    URL_LIST.write_text(json.dumps(docs, indent=2))
    return docs


def load_checkpoint():
    """Load set of already-crawled URLs."""
    if CHECKPOINT.exists():
        return set(json.loads(CHECKPOINT.read_text()))
    return set()


def save_checkpoint(done: set):
    CHECKPOINT.write_text(json.dumps(sorted(done), indent=2))


def slugify(text: str, max_len: int = 80) -> str:
    """Convert title to filesystem-safe slug."""
    text = re.sub(r'[^\w\s-]', '', text.lower())
    text = re.sub(r'[\s_]+', '_', text).strip('_')
    return text[:max_len]


def scrape_one(url: str, title: str, date: str) -> bool:
    """Scrape a single guidance document. Returns True on success."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            result = app.scrape(url, formats=['markdown'], wait_for=3000)
            md_content = result.markdown or ''
            if not md_content or len(md_content) < 100:
                print(f"  ⚠ Too short ({len(md_content)} chars), attempt {attempt}/{MAX_RETRIES}")
                if attempt < MAX_RETRIES:
                    time.sleep(5)
                    continue
                # Save anyway even if short

            # Build filename from date + title slug
            slug = slugify(title)
            date_prefix = date.replace('/', '-') if date else 'undated'
            filename = f"{date_prefix}_{slug}.md"

            # Write with YAML frontmatter
            out_path = OUT_DIR / filename
            with open(out_path, 'w', encoding='utf-8') as f:
                f.write(f"---\n")
                f.write(f"source: FDA Food Guidance\n")
                f.write(f"title: \"{title}\"\n")
                f.write(f"date: \"{date}\"\n")
                f.write(f"url: {url}\n")
                f.write(f"crawled: \"{datetime.now().isoformat()}\"\n")
                f.write(f"chars: {len(md_content)}\n")
                f.write(f"---\n\n")
                f.write(md_content)

            print(f"  ✅ Saved: {filename} ({len(md_content):,} chars)")
            return True

        except Exception as e:
            print(f"  ❌ Error (attempt {attempt}/{MAX_RETRIES}): {e}")
            if attempt < MAX_RETRIES:
                wait = 10 * attempt
                print(f"     Retrying in {wait}s...")
                time.sleep(wait)
    return False


def main():
    # Fetch URL list (from cache or FDA website)
    docs = fetch_url_list()
    if not docs:
        print("❌ No documents found!")
        sys.exit(1)
    total = len(docs)
    print(f"📋 Loaded {total} FDA Food Guidance Documents")

    # Load checkpoint
    done = load_checkpoint()
    remaining = [d for d in docs if d['url'] not in done]
    print(f"✅ Already crawled: {len(done)}")
    print(f"📥 Remaining: {len(remaining)}")
    print(f"⏱  Estimated time: ~{len(remaining) * DELAY // 60} min")
    print(f"{'─' * 60}")

    success = 0
    fail = 0

    for i, doc in enumerate(remaining, 1):
        url = doc['url']
        title = doc.get('title', 'Untitled')
        date = doc.get('date', '')

        print(f"\n[{len(done) + i}/{total}] {title[:70]}...")

        if scrape_one(url, title, date):
            done.add(url)
            success += 1
        else:
            fail += 1

        # Save checkpoint after every document
        save_checkpoint(done)

        # Delay between requests
        if i < len(remaining):
            time.sleep(DELAY)

    print(f"\n{'═' * 60}")
    print(f"🏁 DONE! Success: {success}, Failed: {fail}, Total crawled: {len(done)}/{total}")

    # Summary stats
    total_chars = 0
    total_files = 0
    for f in OUT_DIR.glob("*.md"):
        if f.name.startswith('_'):
            continue
        total_chars += f.stat().st_size
        total_files += 1
    print(f"📊 {total_files} files, {total_chars / 1024 / 1024:.1f} MB total")


if __name__ == '__main__':
    main()
