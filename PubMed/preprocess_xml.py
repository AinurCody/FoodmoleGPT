#!/usr/bin/env python3
"""
PMC XML Preprocessor for FoodmoleGPT
======================================
Convert PMC XML articles to clean text for LLM training.

Extracts:
  - Title, Abstract, Body text (all sections)
  - Figure and Table captions (contain experimental conclusions!)
  - Keywords

Output formats:
  - JSONL: one JSON object per article (for fine-tuning)
  - TXT: plain text (for pretraining)

Usage:
    python preprocess_xml.py [OPTIONS]

Author: FoodmoleGPT Team
"""

import os
import sys
import json
import re
import logging
import argparse
from pathlib import Path
from typing import Dict, List, Optional
from multiprocessing import Pool, cpu_count
from functools import partial

import xml.etree.ElementTree as ET
from tqdm import tqdm


# =============================================================================
# XML Parsing
# =============================================================================

def get_text(elem) -> str:
    """Recursively extract all text from an XML element, including tails."""
    if elem is None:
        return ""
    parts = []
    if elem.text:
        parts.append(elem.text)
    for child in elem:
        # Skip certain elements
        tag = child.tag.lower() if isinstance(child.tag, str) else ""
        if tag in ("xref", "ext-link", "uri"):
            # Keep text content of references but skip the tag
            if child.text:
                parts.append(child.text)
        elif tag in ("graphic", "media", "inline-graphic"):
            # Skip image references
            pass
        elif tag == "sup":
            if child.text:
                parts.append(child.text)
        elif tag == "sub":
            if child.text:
                parts.append(child.text)
        else:
            parts.append(get_text(child))
        if child.tail:
            parts.append(child.tail)
    return "".join(parts)


def extract_title(meta) -> str:
    """Extract article title."""
    title_elem = meta.find(".//article-title")
    if title_elem is not None:
        return get_text(title_elem).strip()
    return ""


def extract_abstract(meta) -> str:
    """Extract abstract text."""
    abstract = meta.find(".//abstract")
    if abstract is None:
        return ""
    
    # Handle structured abstracts (with sections)
    sections = abstract.findall(".//sec")
    if sections:
        parts = []
        for sec in sections:
            sec_title = sec.find("title")
            title_text = get_text(sec_title).strip() if sec_title is not None else ""
            paragraphs = sec.findall(".//p")
            body_text = " ".join(get_text(p).strip() for p in paragraphs)
            if title_text and body_text:
                parts.append(f"{title_text}: {body_text}")
            elif body_text:
                parts.append(body_text)
        return " ".join(parts)
    else:
        # Simple abstract
        paragraphs = abstract.findall(".//p")
        if paragraphs:
            return " ".join(get_text(p).strip() for p in paragraphs)
        return get_text(abstract).strip()


def extract_keywords(meta) -> List[str]:
    """Extract keywords."""
    keywords = []
    for kwd in meta.findall(".//kwd"):
        text = get_text(kwd).strip()
        if text:
            keywords.append(text)
    return keywords


def extract_body(article) -> List[Dict[str, str]]:
    """Extract body sections with titles."""
    body = article.find(".//body")
    if body is None:
        return []
    
    sections = []
    
    # Skip sections that are not useful for training
    skip_titles = {
        "competing interests", "conflict of interest", "conflicts of interest",
        "credit authorship contribution statement", "authorship contribution",
        "declaration of competing interest", "author contributions",
        "funding", "acknowledgements", "acknowledgments", "acknowledgment",
        "data availability", "supplementary material", "supplementary data",
        "abbreviations", "ethics statement", "ethical approval",
    }
    
    def process_section(sec, depth=0):
        sec_title_elem = sec.find("title")
        sec_title = get_text(sec_title_elem).strip() if sec_title_elem is not None else ""
        
        # Skip irrelevant sections
        if sec_title.lower() in skip_titles:
            return
        
        # Get paragraphs in this section (not nested sections)
        paragraphs = []
        for child in sec:
            if child.tag == "p":
                text = get_text(child).strip()
                if text:
                    paragraphs.append(text)
            elif child.tag == "sec":
                # Process nested sections
                process_section(child, depth + 1)
        
        if paragraphs:
            section_text = " ".join(paragraphs)
            sections.append({
                "title": sec_title,
                "text": section_text,
            })
    
    for sec in body.findall("sec"):
        process_section(sec)
    
    # Handle body without sections (direct paragraphs)
    if not sections:
        paragraphs = []
        for p in body.findall("p"):
            text = get_text(p).strip()
            if text:
                paragraphs.append(text)
        if paragraphs:
            sections.append({
                "title": "",
                "text": " ".join(paragraphs),
            })
    
    return sections


def extract_figure_captions(article) -> List[str]:
    """Extract figure captions (often contain experimental conclusions)."""
    captions = []
    for fig in article.iter("fig"):
        label_elem = fig.find("label")
        caption_elem = fig.find("caption")
        
        if caption_elem is not None:
            label = get_text(label_elem).strip() if label_elem is not None else ""
            caption_text = get_text(caption_elem).strip()
            if caption_text and len(caption_text) > 10:
                if label:
                    captions.append(f"{label}: {caption_text}")
                else:
                    captions.append(caption_text)
    return captions


def extract_table_captions(article) -> List[str]:
    """Extract table captions."""
    captions = []
    for tw in article.iter("table-wrap"):
        label_elem = tw.find("label")
        caption_elem = tw.find("caption")
        
        if caption_elem is not None:
            label = get_text(label_elem).strip() if label_elem is not None else ""
            caption_text = get_text(caption_elem).strip()
            if caption_text and len(caption_text) > 10:
                if label:
                    captions.append(f"{label}: {caption_text}")
                else:
                    captions.append(caption_text)
    return captions


def extract_journal(meta) -> str:
    """Extract journal name."""
    journal = meta.find(".//{http://www.w3.org/1999/xlink}journal-title")
    if journal is None:
        journal = meta.find(".//journal-title")
    return get_text(journal).strip() if journal is not None else ""


def extract_pmcid(meta) -> str:
    """Extract PMC ID."""
    for aid in meta.findall(".//article-id"):
        if aid.get("pub-id-type") == "pmc":
            return f"PMC{aid.text}" if aid.text else ""
    return ""


# =============================================================================
# Text Cleaning
# =============================================================================

def clean_text(text: str) -> str:
    """Clean extracted text."""
    if not text:
        return ""
    
    # Replace multiple whitespace with single space
    text = re.sub(r'\s+', ' ', text)
    
    # Remove citation markers like [1], [1,2], [1-3]
    text = re.sub(r'\[[\d,\s\-–]+\]', '', text)
    
    # Remove excessive periods
    text = re.sub(r'\.{2,}', '.', text)
    
    # Fix spacing around punctuation
    text = re.sub(r'\s+([.,;:!?])', r'\1', text)
    
    # Remove leading/trailing whitespace
    text = text.strip()
    
    return text


# =============================================================================
# Main Processing
# =============================================================================

def process_single_xml(xml_path: str) -> Optional[Dict]:
    """
    Process a single XML file and return structured data.
    
    Returns None if the file is invalid or too short.
    """
    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
        
        article = root.find(".//article")
        if article is None:
            return None
        
        meta = article.find(".//article-meta")
        if meta is None:
            return None
        
        # Extract all fields
        title = clean_text(extract_title(meta))
        abstract = clean_text(extract_abstract(meta))
        keywords = extract_keywords(meta)
        journal = extract_journal(root.find(".//journal-meta") or meta)
        pmcid = extract_pmcid(meta) or Path(xml_path).stem
        
        body_sections = extract_body(article)
        fig_captions = [clean_text(c) for c in extract_figure_captions(article)]
        table_captions = [clean_text(c) for c in extract_table_captions(article)]
        
        # Build full text
        full_text_parts = []
        
        if title:
            full_text_parts.append(f"Title: {title}")
        
        if abstract:
            full_text_parts.append(f"\nAbstract: {abstract}")
        
        if keywords:
            full_text_parts.append(f"\nKeywords: {', '.join(keywords)}")
        
        for section in body_sections:
            sec_title = section["title"]
            sec_text = clean_text(section["text"])
            if sec_title:
                full_text_parts.append(f"\n{sec_title}\n{sec_text}")
            else:
                full_text_parts.append(f"\n{sec_text}")
        
        if fig_captions:
            full_text_parts.append("\nFigure Descriptions:")
            for cap in fig_captions:
                full_text_parts.append(f"  {cap}")
        
        if table_captions:
            full_text_parts.append("\nTable Descriptions:")
            for cap in table_captions:
                full_text_parts.append(f"  {cap}")
        
        full_text = "\n".join(full_text_parts)
        
        # Skip if too short (less than 500 chars of body text)
        body_text_len = sum(len(s["text"]) for s in body_sections)
        if body_text_len < 500:
            return None
        
        return {
            "pmcid": pmcid,
            "title": title,
            "abstract": abstract,
            "keywords": keywords,
            "journal": journal,
            "sections": [{"title": s["title"], "text": clean_text(s["text"])} 
                        for s in body_sections],
            "figure_captions": fig_captions,
            "table_captions": table_captions,
            "full_text": full_text,
            "text_length": len(full_text),
        }
        
    except Exception as e:
        return None


def main():
    parser = argparse.ArgumentParser(
        description="Preprocess PMC XML articles for LLM training"
    )
    parser.add_argument(
        "--input-dir", "-i",
        type=str,
        default="data/xml",
        help="Directory containing XML files"
    )
    parser.add_argument(
        "--output-dir", "-o",
        type=str,
        default="data/processed",
        help="Output directory"
    )
    parser.add_argument(
        "--format", "-f",
        choices=["jsonl", "txt", "both"],
        default="both",
        help="Output format"
    )
    parser.add_argument(
        "--workers", "-w",
        type=int,
        default=None,
        help="Number of parallel workers (default: CPU count)"
    )
    parser.add_argument(
        "--max-files", "-n",
        type=int,
        default=None,
        help="Max files to process (for testing)"
    )
    
    args = parser.parse_args()
    
    # Setup
    script_dir = Path(__file__).parent
    input_dir = Path(args.input_dir)
    if not input_dir.is_absolute():
        input_dir = script_dir / input_dir
    
    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = script_dir / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    
    num_workers = args.workers or max(1, cpu_count() - 1)
    
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(message)s",
    )
    logger = logging.getLogger("Preprocessor")
    
    logger.info("=" * 60)
    logger.info("PMC XML Preprocessor for FoodmoleGPT")
    logger.info("=" * 60)
    logger.info(f"Input: {input_dir}")
    logger.info(f"Output: {output_dir}")
    logger.info(f"Workers: {num_workers}")
    
    # Get XML files
    xml_files = sorted(input_dir.glob("PMC*.xml"))
    if args.max_files:
        xml_files = xml_files[:args.max_files]
    
    logger.info(f"Found {len(xml_files):,} XML files")
    
    if not xml_files:
        logger.error("No XML files found!")
        return
    
    # Process in parallel
    logger.info(f"Processing with {num_workers} workers...")
    
    xml_paths = [str(f) for f in xml_files]
    
    results = []
    skipped = 0
    errors = 0
    
    with Pool(num_workers) as pool:
        for result in tqdm(
            pool.imap_unordered(process_single_xml, xml_paths, chunksize=100),
            total=len(xml_paths),
            desc="Processing",
            unit="xml"
        ):
            if result is not None:
                results.append(result)
            else:
                skipped += 1
    
    logger.info(f"\nProcessing complete!")
    logger.info(f"  Successful: {len(results):,}")
    logger.info(f"  Skipped (too short/invalid): {skipped:,}")
    
    # Sort by PMCID
    results.sort(key=lambda x: x["pmcid"])
    
    # Calculate stats
    total_chars = sum(r["text_length"] for r in results)
    avg_chars = total_chars // len(results) if results else 0
    
    logger.info(f"\nText Statistics:")
    logger.info(f"  Total text: {total_chars / 1e6:.1f} M characters")
    logger.info(f"  Average per article: {avg_chars:,} characters")
    logger.info(f"  Estimated tokens: ~{total_chars // 4 / 1e6:.1f} M tokens")
    
    # Save outputs
    if args.format in ("jsonl", "both"):
        jsonl_path = output_dir / "food_science_corpus.jsonl"
        logger.info(f"\nWriting JSONL to {jsonl_path}...")
        with open(jsonl_path, "w", encoding="utf-8") as f:
            for r in tqdm(results, desc="Writing JSONL", unit="doc"):
                # Write compact version for training
                doc = {
                    "pmcid": r["pmcid"],
                    "title": r["title"],
                    "abstract": r["abstract"],
                    "keywords": r["keywords"],
                    "journal": r["journal"],
                    "text": r["full_text"],
                }
                f.write(json.dumps(doc, ensure_ascii=False) + "\n")
        logger.info(f"  Size: {jsonl_path.stat().st_size / 1e9:.2f} GB")
    
    if args.format in ("txt", "both"):
        txt_path = output_dir / "food_science_corpus.txt"
        logger.info(f"\nWriting TXT to {txt_path}...")
        with open(txt_path, "w", encoding="utf-8") as f:
            for r in tqdm(results, desc="Writing TXT", unit="doc"):
                f.write(r["full_text"])
                f.write("\n\n" + "=" * 40 + "\n\n")  # Document separator
        logger.info(f"  Size: {txt_path.stat().st_size / 1e9:.2f} GB")
    
    # Save stats
    stats = {
        "total_articles": len(results),
        "skipped_articles": skipped,
        "total_characters": total_chars,
        "avg_characters": avg_chars,
        "estimated_tokens": total_chars // 4,
    }
    stats_path = output_dir / "corpus_stats.json"
    with open(stats_path, "w") as f:
        json.dump(stats, f, indent=2)
    
    logger.info(f"\nDone! Output saved to: {output_dir}")


if __name__ == "__main__":
    main()
