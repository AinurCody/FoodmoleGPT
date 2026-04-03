"""
FoodmoleGPT — SFT Instruction Pair Generator (Gemini API)

Generates diverse food science Q&A instruction pairs from CPT corpus articles
using Google Gemini API. Outputs in Alpaca format for LLaMA-Factory.

Supports both synchronous (pilot) and async concurrent (production) modes.

Usage:
    # Pilot test: 50 from each source (sync)
    python generate_sft.py --pilot

    # Production: 50K pairs from OpenAlex, 10 concurrent
    python generate_sft.py --source openalex --target-pairs 50000

    # Production: 50K pairs from PubMed, 20 concurrent
    python generate_sft.py --source pubmed --target-pairs 50000 --concurrency 20

    # Both sources at once
    python generate_sft.py --source both --target-pairs 100000

    # Custom model
    python generate_sft.py --source openalex --target-pairs 50000 --model gemini-3.1-flash-lite-preview
"""

import os
import sys
import json
import time
import random
import hashlib
import argparse
import asyncio
import logging
from pathlib import Path
from datetime import datetime

from dotenv import load_dotenv
from google import genai
from google.genai.types import GenerateContentConfig

# ── Paths ──────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
OPENALEX_PATH = BASE_DIR.parent.parent / "CPT_dataset/essay/OpenAlex/fulltext.jsonl"
PUBMED_PATH = BASE_DIR.parent.parent / "CPT_dataset/essay/PubMed/data/processed/filtered/food_science_corpus.keep.jsonl"
OUTPUT_DIR = BASE_DIR / "output"
LOG_DIR = BASE_DIR / "logs"

# ── Default model ─────────────────────────────────────────────────
DEFAULT_MODEL = "gemini-3.1-flash-lite-preview"

# ── Generation config ─────────────────────────────────────────────
MAX_INPUT_CHARS = 80_000       # Truncate articles longer than this (~20K tokens)
QA_PER_ARTICLE = 5             # Number of QA pairs to generate per article
MAX_RETRIES = 3                # Retries per article on API failure
RETRY_BACKOFF = 2.0            # Exponential backoff multiplier
PROGRESS_SAVE_INTERVAL = 20   # Save progress every N articles

# ── Prompt Template ────────────────────────────────────────────────
SYSTEM_PROMPT = """\
You are a food science professor creating diverse instructional Q&A pairs \
for training a domain-specific language model. Your questions must be \
grounded in the provided research article and cover different cognitive \
levels and question styles."""

def build_user_prompt(article_text: str, n_pairs: int = QA_PER_ARTICLE) -> str:
    return f"""\
Below is a food science research article. Generate exactly {n_pairs} high-quality \
English Q&A pairs based on its content.

REQUIREMENTS:
1. Each Q&A pair must be self-contained — the question should be answerable \
WITHOUT needing the original article.
2. The answer must be detailed (100-400 words), accurate, and grounded in \
the article's content. Do NOT hallucinate facts not present in the article.
3. Generate a DIVERSE MIX of question types. You MUST use at least 3 \
different types from the list below:

   - FACTUAL: "What is/are...", "Define...", "List the..." — tests recall of \
specific facts, definitions, or enumerations from the article.
   - MECHANISTIC: "Explain the mechanism by which...", "How does X affect Y..." \
— requires explaining biological, chemical, or physical processes.
   - ANALYTICAL: "Compare and contrast...", "What are the advantages and \
disadvantages of...", "Analyze the relationship between..." — requires \
critical thinking and synthesis.
   - METHODOLOGICAL: "Describe the experimental approach used to...", \
"What analytical technique would you use to..." — focuses on research methods, \
instruments, and experimental design.
   - APPLICATION: "How could this finding be applied to...", "Suggest a \
strategy to..." — connects research to practical food science problems.
   - SYNTHESIS: "Based on these findings, what would you predict if...", \
"How do these results relate to the broader field of..." — integrates \
knowledge and requires higher-order thinking.

4. Questions should cover DIFFERENT sections/topics of the article, not \
cluster around one finding.
5. Do NOT generate trivial questions (e.g., "Who are the authors?", \
"What journal published this?").

OUTPUT FORMAT — Return a JSON array with exactly {n_pairs} objects:
```json
[
  {{
    "instruction": "Your question here",
    "input": "",
    "output": "Your detailed answer here",
    "type": "FACTUAL|MECHANISTIC|ANALYTICAL|METHODOLOGICAL|APPLICATION|SYNTHESIS"
  }}
]
```

ARTICLE:
{article_text}"""


# ── Logging setup ──────────────────────────────────────────────────
def setup_logging(log_dir: Path, tag: str = "") -> logging.Logger:
    log_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    logger = logging.getLogger("sft_gen")
    logger.setLevel(logging.INFO)

    # Avoid duplicate handlers on re-runs
    if logger.handlers:
        logger.handlers.clear()

    fh = logging.FileHandler(log_dir / f"generate_{tag}_{ts}.log", encoding="utf-8")
    fh.setLevel(logging.INFO)
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)

    fmt = logging.Formatter("[%(asctime)s] %(levelname)s — %(message)s", "%H:%M:%S")
    fh.setFormatter(fmt)
    ch.setFormatter(fmt)
    logger.addHandler(fh)
    logger.addHandler(ch)
    return logger


# ── Helper functions ───────────────────────────────────────────────
def article_id(record: dict, source: str) -> str:
    """Generate a unique ID for an article."""
    if source == "pubmed":
        return record.get("pmcid", hashlib.md5(record["text"][:500].encode()).hexdigest())
    else:
        return hashlib.md5(record["text"][:500].encode()).hexdigest()


def truncate_article(text: str, max_chars: int = MAX_INPUT_CHARS) -> str:
    """Truncate article text to fit within token limits."""
    if len(text) <= max_chars:
        return text
    cut = text[:max_chars].rfind("\n\n")
    if cut > max_chars * 0.8:
        return text[:cut] + "\n\n[...truncated...]"
    return text[:max_chars] + "\n\n[...truncated...]"


def load_progress(progress_file: Path) -> set:
    """Load set of already-processed article IDs."""
    if progress_file.exists():
        with open(progress_file, "r") as f:
            return set(json.loads(f.read()))
    return set()


def save_progress(progress_file: Path, processed_ids: set):
    with open(progress_file, "w") as f:
        f.write(json.dumps(sorted(processed_ids)))


def sample_articles(path: Path, n: int, seed: int = 42) -> list[dict]:
    """Reservoir sample n articles from a JSONL file."""
    random.seed(seed)
    reservoir = []
    with open(path, "r", encoding="utf-8") as f:
        for i, line in enumerate(f):
            record = json.loads(line)
            if i < n:
                reservoir.append(record)
            else:
                j = random.randint(0, i)
                if j < n:
                    reservoir[j] = record
    random.shuffle(reservoir)
    return reservoir[:n]


def parse_gemini_response(response_text: str) -> list[dict] | None:
    """Parse Gemini response into list of QA dicts."""
    text = response_text.strip()

    # Strip markdown code fences if present
    if text.startswith("```"):
        first_nl = text.index("\n")
        text = text[first_nl + 1:]
    if text.endswith("```"):
        text = text[:-3].rstrip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("[")
        end = text.rfind("]")
        if start != -1 and end != -1 and end > start:
            try:
                data = json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                return None
        else:
            return None

    if not isinstance(data, list):
        return None

    valid = []
    for item in data:
        if not isinstance(item, dict):
            continue
        if "instruction" not in item or "output" not in item:
            continue
        if len(item["instruction"].strip()) < 10:
            continue
        if len(item["output"].strip()) < 50:
            continue
        valid.append({
            "instruction": item["instruction"].strip(),
            "input": item.get("input", "").strip(),
            "output": item["output"].strip(),
            "type": item.get("type", "UNKNOWN").strip().upper(),
        })

    return valid if valid else None


# ══════════════════════════════════════════════════════════════════
# ASYNC CONCURRENT GENERATION
# ══════════════════════════════════════════════════════════════════

async def async_generate_for_article(
    client: genai.Client,
    model_name: str,
    article_text: str,
    n_pairs: int,
    semaphore: asyncio.Semaphore,
    logger: logging.Logger,
) -> list[dict] | None:
    """Async: call Gemini to generate QA pairs for one article."""
    truncated = truncate_article(article_text)
    prompt = build_user_prompt(truncated, n_pairs)

    async with semaphore:
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = await client.aio.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=GenerateContentConfig(
                        system_instruction=SYSTEM_PROMPT,
                        temperature=0.7,
                        max_output_tokens=4096,
                        response_mime_type="application/json",
                    ),
                )

                if not response.text:
                    logger.warning(f"  Empty response (attempt {attempt})")
                    await asyncio.sleep(RETRY_BACKOFF ** attempt)
                    continue

                pairs = parse_gemini_response(response.text)
                if pairs is None:
                    logger.warning(f"  Parse failed (attempt {attempt})")
                    await asyncio.sleep(RETRY_BACKOFF ** attempt)
                    continue

                return pairs

            except Exception as e:
                err_msg = str(e)
                logger.warning(f"  API error (attempt {attempt}): {err_msg[:150]}")
                if "429" in err_msg or "quota" in err_msg.lower() or "RESOURCE_EXHAUSTED" in err_msg:
                    wait = RETRY_BACKOFF ** attempt * 10
                    logger.info(f"  Rate limited, waiting {wait:.0f}s...")
                    await asyncio.sleep(wait)
                elif "503" in err_msg or "UNAVAILABLE" in err_msg:
                    wait = RETRY_BACKOFF ** attempt * 5
                    await asyncio.sleep(wait)
                else:
                    await asyncio.sleep(RETRY_BACKOFF ** attempt)

    return None


async def process_article(
    idx: int,
    total: int,
    record: dict,
    source: str,
    client: genai.Client,
    model_name: str,
    n_pairs: int,
    semaphore: asyncio.Semaphore,
    results_queue: asyncio.Queue,
    logger: logging.Logger,
):
    """Process a single article and put results in the queue."""
    aid = article_id(record, source)
    title = record.get("title", record["text"][:80].split("\n")[0])

    pairs = await async_generate_for_article(
        client, model_name, record["text"], n_pairs, semaphore, logger
    )

    if pairs is not None:
        for p in pairs:
            p["source"] = source
            p["article_id"] = aid
        logger.info(f"[{idx+1}/{total}] ✓ {source} | {len(pairs)} pairs | {title[:50]}")
    else:
        logger.error(f"[{idx+1}/{total}] ✗ FAILED | {source} | {title[:50]}")

    await results_queue.put((aid, source, title, pairs))


async def results_writer(
    results_queue: asyncio.Queue,
    output_file: Path,
    progress_file: Path,
    stats: dict,
    processed_ids: set,
    total_articles: int,
    logger: logging.Logger,
):
    """Background task: consume results from queue, write to disk."""
    count = 0
    with open(output_file, "a", encoding="utf-8") as fout:
        while True:
            item = await results_queue.get()
            if item is None:  # Sentinel to stop
                break

            aid, source, title, pairs = item
            processed_ids.add(aid)

            if pairs is None:
                stats["failed"] += 1
                stats["errors"].append({"id": aid, "source": source, "title": title[:100]})
            else:
                for p in pairs:
                    fout.write(json.dumps(p, ensure_ascii=False) + "\n")
                fout.flush()
                stats["total_pairs"] += len(pairs)
                for p in pairs:
                    t = p.get("type", "UNKNOWN")
                    stats["type_counts"][t] = stats["type_counts"].get(t, 0) + 1

            stats["processed"] += 1
            count += 1

            # Progress save + periodic status
            if count % PROGRESS_SAVE_INTERVAL == 0:
                save_progress(progress_file, processed_ids)
                elapsed = (datetime.now() - datetime.fromisoformat(stats["started_at"])).total_seconds()
                rate = stats["processed"] / elapsed * 3600 if elapsed > 0 else 0
                logger.info(
                    f"── Progress: {stats['processed']}/{total_articles} articles | "
                    f"{stats['total_pairs']} pairs | "
                    f"{rate:.0f} articles/hr | "
                    f"failed: {stats['failed']} ──"
                )

            results_queue.task_done()

    # Final save
    save_progress(progress_file, processed_ids)


async def run_async(args):
    """Main async production runner."""
    tag = args.source if args.source != "both" else "both"
    logger = setup_logging(LOG_DIR, tag=tag)
    load_dotenv(BASE_DIR / ".env")

    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        logger.error("GOOGLE_API_KEY not found in .env")
        sys.exit(1)

    client = genai.Client(api_key=api_key)
    model_name = args.model or DEFAULT_MODEL
    n_pairs = args.qa_per_article
    concurrency = args.concurrency

    logger.info(f"Model: {model_name}")
    logger.info(f"Concurrency: {concurrency}")
    logger.info(f"QA per article: {n_pairs}")

    # Determine sources and article counts
    if args.source == "both":
        target_per_source = args.target_pairs // 2
        articles_per_source = target_per_source // n_pairs
        sources = [
            ("openalex", OPENALEX_PATH, articles_per_source),
            ("pubmed", PUBMED_PATH, articles_per_source),
        ]
        out_tag = "both"
    else:
        articles_needed = args.target_pairs // n_pairs
        if args.source == "openalex":
            sources = [("openalex", OPENALEX_PATH, articles_needed)]
        else:
            sources = [("pubmed", PUBMED_PATH, articles_needed)]
        out_tag = args.source

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_file = OUTPUT_DIR / f"{out_tag}.jsonl"
    stats_file = OUTPUT_DIR / f"{out_tag}_stats.json"
    progress_file = OUTPUT_DIR / f"{out_tag}_progress.json"

    processed_ids = load_progress(progress_file)
    logger.info(f"Resuming with {len(processed_ids)} already processed articles")

    # Sample articles
    all_articles = []
    for src_name, src_path, n in sources:
        logger.info(f"Sampling {n} articles from {src_name}...")
        articles = sample_articles(src_path, n, seed=args.seed)
        for a in articles:
            a["_source"] = src_name
        all_articles.extend(articles)
        logger.info(f"  Got {len(articles)} articles")

    # Filter already-processed
    todo = []
    for record in all_articles:
        src = record["_source"]
        aid = article_id(record, src)
        if aid not in processed_ids:
            todo.append(record)
    logger.info(f"Articles to process: {len(todo)} (skipping {len(all_articles) - len(todo)} already done)")

    total_target = args.target_pairs
    logger.info(f"Target: {total_target} instruction pairs from {len(all_articles)} articles")

    # Stats
    stats = {
        "model": model_name,
        "concurrency": concurrency,
        "qa_per_article": n_pairs,
        "target_pairs": total_target,
        "started_at": datetime.now().isoformat(),
        "total_articles": len(all_articles),
        "processed": 0,
        "failed": 0,
        "total_pairs": 0,
        "type_counts": {},
        "errors": [],
    }

    # Semaphore for rate limiting
    semaphore = asyncio.Semaphore(concurrency)
    results_queue = asyncio.Queue()

    # Start the writer task
    writer_task = asyncio.create_task(
        results_writer(
            results_queue, output_file, progress_file,
            stats, processed_ids, len(todo), logger
        )
    )

    # Launch all article tasks
    total = len(todo)
    tasks = []
    for idx, record in enumerate(todo):
        src = record.pop("_source")
        task = asyncio.create_task(
            process_article(
                idx, total, record, src,
                client, model_name, n_pairs,
                semaphore, results_queue, logger
            )
        )
        tasks.append(task)

    # Wait for all generation tasks
    await asyncio.gather(*tasks)

    # Signal writer to stop
    await results_queue.put(None)
    await writer_task

    # Final stats
    stats["finished_at"] = datetime.now().isoformat()
    elapsed = (datetime.fromisoformat(stats["finished_at"]) -
               datetime.fromisoformat(stats["started_at"])).total_seconds()
    stats["elapsed_seconds"] = round(elapsed, 1)
    stats["articles_per_hour"] = round(stats["processed"] / elapsed * 3600, 1) if elapsed > 0 else 0

    with open(stats_file, "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2, ensure_ascii=False)

    logger.info("=" * 60)
    logger.info(f"DONE in {elapsed/3600:.1f} hours")
    logger.info(f"Processed: {stats['processed']}, Failed: {stats['failed']}")
    logger.info(f"Total QA pairs: {stats['total_pairs']}")
    logger.info(f"Type distribution: {json.dumps(stats['type_counts'], indent=2)}")
    logger.info(f"Throughput: {stats['articles_per_hour']:.0f} articles/hr")
    logger.info(f"Output: {output_file}")


# ══════════════════════════════════════════════════════════════════
# SYNC PILOT MODE (kept for quick testing)
# ══════════════════════════════════════════════════════════════════

def sync_generate_for_article(client, model_name, article_text, n_pairs, logger):
    """Synchronous version for pilot testing."""
    truncated = truncate_article(article_text)
    prompt = build_user_prompt(truncated, n_pairs)

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    temperature=0.7,
                    max_output_tokens=4096,
                    response_mime_type="application/json",
                ),
            )
            if not response.text:
                logger.warning(f"  Empty response (attempt {attempt})")
                time.sleep(RETRY_BACKOFF ** attempt)
                continue
            pairs = parse_gemini_response(response.text)
            if pairs is None:
                logger.warning(f"  Parse failed (attempt {attempt})")
                time.sleep(RETRY_BACKOFF ** attempt)
                continue
            return pairs
        except Exception as e:
            err_msg = str(e)
            logger.warning(f"  API error (attempt {attempt}): {err_msg[:200]}")
            if "429" in err_msg or "quota" in err_msg.lower():
                time.sleep(RETRY_BACKOFF ** attempt * 5)
            else:
                time.sleep(RETRY_BACKOFF ** attempt)
    return None


def run_pilot(args):
    """Synchronous pilot mode: 50 from each source."""
    logger = setup_logging(LOG_DIR, tag="pilot")
    load_dotenv(BASE_DIR / ".env")

    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        logger.error("GOOGLE_API_KEY not found in .env")
        sys.exit(1)

    client = genai.Client(api_key=api_key)
    model_name = args.model or DEFAULT_MODEL
    n_pairs = args.qa_per_article

    logger.info(f"=== PILOT MODE === Model: {model_name}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_file = OUTPUT_DIR / "pilot.jsonl"
    stats_file = OUTPUT_DIR / "pilot_stats.json"
    progress_file = OUTPUT_DIR / "pilot_progress.json"

    processed_ids = load_progress(progress_file)

    sources = [
        ("openalex", OPENALEX_PATH, 50),
        ("pubmed", PUBMED_PATH, 50),
    ]

    all_articles = []
    for src_name, src_path, n in sources:
        logger.info(f"Sampling {n} from {src_name}...")
        articles = sample_articles(src_path, n, seed=args.seed)
        for a in articles:
            a["_source"] = src_name
        all_articles.extend(articles)

    stats = {
        "model": model_name, "qa_per_article": n_pairs,
        "started_at": datetime.now().isoformat(),
        "total_articles": len(all_articles),
        "processed": 0, "failed": 0, "total_pairs": 0,
        "type_counts": {}, "errors": [],
    }

    with open(output_file, "a", encoding="utf-8") as fout:
        for idx, record in enumerate(all_articles):
            src = record.pop("_source")
            aid = article_id(record, src)
            if aid in processed_ids:
                logger.info(f"[{idx+1}/{len(all_articles)}] Skip {aid}")
                continue
            title = record.get("title", record["text"][:80].split("\n")[0])
            logger.info(f"[{idx+1}/{len(all_articles)}] {src} | {title[:60]}...")

            pairs = sync_generate_for_article(client, model_name, record["text"], n_pairs, logger)
            if pairs is None:
                stats["failed"] += 1
                stats["errors"].append({"id": aid, "source": src, "title": title[:100]})
            else:
                for p in pairs:
                    p["source"] = src
                    p["article_id"] = aid
                    fout.write(json.dumps(p, ensure_ascii=False) + "\n")
                stats["total_pairs"] += len(pairs)
                for p in pairs:
                    t = p.get("type", "UNKNOWN")
                    stats["type_counts"][t] = stats["type_counts"].get(t, 0) + 1
                logger.info(f"  {len(pairs)} pairs | {[p['type'] for p in pairs]}")

            stats["processed"] += 1
            processed_ids.add(aid)
            save_progress(progress_file, processed_ids)
            time.sleep(0.5)

    stats["finished_at"] = datetime.now().isoformat()
    with open(stats_file, "w") as f:
        json.dump(stats, f, indent=2, ensure_ascii=False)

    logger.info(f"Done! {stats['processed']} articles, {stats['total_pairs']} pairs, {stats['failed']} failed")


# ══════════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Generate SFT instruction pairs from food science articles",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python generate_sft.py --pilot
  python generate_sft.py --source openalex --target-pairs 50000
  python generate_sft.py --source both --target-pairs 100000 --concurrency 20
        """,
    )
    parser.add_argument("--pilot", action="store_true",
                        help="Pilot mode: 50 articles from each source (sync)")
    parser.add_argument("--source", choices=["openalex", "pubmed", "both"],
                        help="Data source for production run")
    parser.add_argument("--target-pairs", type=int, default=50000,
                        help="Target number of instruction pairs (default: 50000)")
    parser.add_argument("--qa-per-article", type=int, default=QA_PER_ARTICLE,
                        help=f"QA pairs per article (default: {QA_PER_ARTICLE})")
    parser.add_argument("--concurrency", type=int, default=10,
                        help="Max concurrent API requests (default: 10)")
    parser.add_argument("--model", type=str, default=None,
                        help=f"Gemini model (default: {DEFAULT_MODEL})")
    parser.add_argument("--seed", type=int, default=42,
                        help="Random seed for sampling (default: 42)")

    args = parser.parse_args()

    if not args.pilot and not args.source:
        parser.error("Either --pilot or --source is required")

    if args.pilot:
        run_pilot(args)
    else:
        asyncio.run(run_async(args))


if __name__ == "__main__":
    main()
