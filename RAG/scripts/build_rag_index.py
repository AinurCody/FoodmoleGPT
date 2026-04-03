#!/usr/bin/env python3
"""Build FAISS index from CPT corpus for RAG evaluation.

Chunking strategy (paragraph-aware with overlap):
1. Parse each document: extract title + abstract + full text
2. Abstract → standalone chunk (high-density summary)
3. Full text → split by paragraphs → group into ~512-token chunks
4. 128-token overlap between consecutive chunks
5. Each chunk prefixed with paper title for retrieval context

Usage (inside singularity container on GPU node):
    python build_rag_index.py                          # full corpus
    python build_rag_index.py --max-docs 10000         # subset for testing
    python build_rag_index.py --batch-size 512         # larger batch (more VRAM)
"""
import argparse
import json
import os
import re
import time
import numpy as np
import faiss
from pathlib import Path

# ── Paths ────────────────────────────────────────────────────────────────
CORPUS_PATH = "/scratch/$USER/foodmole_workspace/data/cpt_corpus_merged.jsonl"
INDEX_DIR = "/scratch/$USER/foodmole_workspace/data/rag_index"

# ── Chunking parameters ─────────────────────────────────────────────────
CHUNK_SIZE = 512       # target tokens per chunk
CHUNK_OVERLAP = 128    # overlap tokens between consecutive chunks
EMBED_MODEL = "BAAI/bge-base-en-v1.5"  # 768-dim, good for English retrieval
EMBED_BATCH_SIZE = 256


def parse_document(text, source=""):
    """Parse a CPT corpus document into title, abstract, and body sections.

    Handles multiple formats:
    - essay_fulltext: Title + Abstract + Full Text (structured)
    - essay_abstract: Title + Abstract only
    - wiki_food: Title + body text
    - fineweb_general: plain text (no structured fields)
    """
    title = ""
    abstract = ""
    body = ""

    if text.startswith("Title:"):
        # Structured document (essay_*, wiki_food)
        m = re.match(r"Title:\s*(.+?)(?:\n|$)", text)
        if m:
            title = m.group(1).strip()

        m = re.search(r"Abstract:\s*\n?(.*?)(?:\nFull Text:|\nKeywords:|\Z)", text, re.DOTALL)
        if m:
            abstract = m.group(1).strip()

        m = re.search(r"Full Text:\s*\n?(.*)", text, re.DOTALL)
        if m:
            body = m.group(1).strip()

        # For wiki_food or docs without Full Text: use everything after metadata as body
        if not body and not abstract:
            # Strip metadata lines (Title, Authors, Year, Venue, Keywords) and use rest
            lines = text.split("\n")
            body_lines = []
            past_meta = False
            for line in lines:
                if past_meta:
                    body_lines.append(line)
                elif not re.match(r"^(Title|Authors|Year|Venue|Keywords):", line):
                    past_meta = True
                    body_lines.append(line)
            body = "\n".join(body_lines).strip()
    else:
        # Unstructured text (fineweb_general): entire text is body
        body = text.strip()

    return title, abstract, body


def split_into_paragraphs(text):
    """Split text into paragraphs (by double newline or single newline with indent)."""
    # Split on double newlines first
    paragraphs = re.split(r"\n\s*\n", text)
    # Filter out empty paragraphs and strip whitespace
    paragraphs = [p.strip() for p in paragraphs if p.strip()]
    return paragraphs


def estimate_tokens(text):
    """Rough token count: ~0.75 tokens per whitespace-delimited word for English text.
    More accurate than len/4 for academic text with long words."""
    return int(len(text.split()) * 1.3)


def chunk_document(text, doc_idx, source=""):
    """Chunk a single document into retrieval-ready passages.

    Returns list of dicts: {"text": ..., "doc_idx": ..., "chunk_type": ...}
    """
    title, abstract, body = parse_document(text, source)
    chunks = []
    prefix = f"Title: {title}\n" if title else ""

    # Chunk 1: Abstract as standalone chunk (if non-trivial)
    if abstract and estimate_tokens(abstract) > 30:
        chunks.append({
            "text": f"{prefix}Abstract: {abstract}",
            "doc_idx": doc_idx,
            "chunk_type": "abstract",
        })

    # Chunk 2+: Body text split into paragraph-aware chunks with overlap
    if body:
        paragraphs = split_into_paragraphs(body)
        if not paragraphs:
            return chunks

        # Build chunks by accumulating paragraphs up to CHUNK_SIZE tokens
        current_paras = []
        current_tokens = 0

        for para in paragraphs:
            para_tokens = estimate_tokens(para)

            # If a single paragraph exceeds chunk size, split by sentences
            if para_tokens > CHUNK_SIZE:
                # Flush current buffer first
                if current_paras:
                    chunk_text = prefix + "\n\n".join(current_paras)
                    chunks.append({
                        "text": chunk_text,
                        "doc_idx": doc_idx,
                        "chunk_type": "fulltext",
                    })
                    # Keep overlap: last paragraph(s) worth ~CHUNK_OVERLAP tokens
                    current_paras, current_tokens = _keep_overlap(current_paras)

                # Split long paragraph by sentences
                sentences = re.split(r"(?<=[.!?])\s+", para)
                sent_buf = []
                sent_tokens = 0
                for sent in sentences:
                    st = estimate_tokens(sent)
                    if sent_tokens + st > CHUNK_SIZE and sent_buf:
                        chunk_text = prefix + " ".join(sent_buf)
                        chunks.append({
                            "text": chunk_text,
                            "doc_idx": doc_idx,
                            "chunk_type": "fulltext",
                        })
                        # Overlap: keep last few sentences
                        overlap_buf = []
                        overlap_t = 0
                        for s in reversed(sent_buf):
                            st2 = estimate_tokens(s)
                            if overlap_t + st2 > CHUNK_OVERLAP:
                                break
                            overlap_buf.insert(0, s)
                            overlap_t += st2
                        sent_buf = overlap_buf
                        sent_tokens = overlap_t
                    sent_buf.append(sent)
                    sent_tokens += st
                # Remaining sentences go back into the paragraph buffer
                if sent_buf:
                    current_paras = [" ".join(sent_buf)]
                    current_tokens = sent_tokens
                continue

            # Normal case: accumulate paragraphs
            if current_tokens + para_tokens > CHUNK_SIZE and current_paras:
                chunk_text = prefix + "\n\n".join(current_paras)
                chunks.append({
                    "text": chunk_text,
                    "doc_idx": doc_idx,
                    "chunk_type": "fulltext",
                })
                # Keep overlap
                current_paras, current_tokens = _keep_overlap(current_paras)

            current_paras.append(para)
            current_tokens += para_tokens

        # Flush remaining
        if current_paras:
            chunk_text = prefix + "\n\n".join(current_paras)
            chunks.append({
                "text": chunk_text,
                "doc_idx": doc_idx,
                "chunk_type": "fulltext",
            })

    return chunks


def _keep_overlap(paragraphs):
    """Keep trailing paragraphs that fit within CHUNK_OVERLAP tokens."""
    overlap_paras = []
    overlap_tokens = 0
    for para in reversed(paragraphs):
        pt = estimate_tokens(para)
        if overlap_tokens + pt > CHUNK_OVERLAP:
            break
        overlap_paras.insert(0, para)
        overlap_tokens += pt
    return overlap_paras, overlap_tokens


def main():
    parser = argparse.ArgumentParser(description="Build FAISS index for RAG")
    parser.add_argument("--corpus", default=CORPUS_PATH, help="Path to JSONL corpus")
    parser.add_argument("--output-dir", default=INDEX_DIR, help="Directory for index output")
    parser.add_argument("--max-docs", type=int, default=0, help="Limit docs (0 = all)")
    parser.add_argument("--batch-size", type=int, default=EMBED_BATCH_SIZE, help="Embedding batch size")
    parser.add_argument("--model", default=EMBED_MODEL, help="Sentence-transformers model name")
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)

    # ── Step 1: Chunk corpus ─────────────────────────────────────────────
    print(f"=== Step 1: Chunking corpus ===")
    print(f"  Corpus: {args.corpus}")
    print(f"  Chunk size: {CHUNK_SIZE} tokens, overlap: {CHUNK_OVERLAP} tokens")

    all_chunks = []
    t0 = time.time()
    with open(args.corpus) as f:
        for i, line in enumerate(f):
            if args.max_docs and i >= args.max_docs:
                break
            doc = json.loads(line)
            chunks = chunk_document(doc["text"], i, doc.get("source", ""))
            all_chunks.extend(chunks)
            if (i + 1) % 100_000 == 0:
                print(f"  Processed {i+1:,} docs → {len(all_chunks):,} chunks ({time.time()-t0:.0f}s)")

    num_docs = i + 1 if not args.max_docs else min(args.max_docs, i + 1)
    print(f"  Done: {num_docs:,} docs → {len(all_chunks):,} chunks ({time.time()-t0:.0f}s)")
    print(f"  Avg chunks/doc: {len(all_chunks)/max(num_docs,1):.1f}")

    # Save chunk texts + metadata (for retrieval at eval time)
    chunk_texts = [c["text"] for c in all_chunks]
    chunk_meta = [{"doc_idx": c["doc_idx"], "chunk_type": c["chunk_type"]} for c in all_chunks]

    meta_path = os.path.join(args.output_dir, "chunk_metadata.json")
    print(f"  Saving metadata to {meta_path}")
    with open(meta_path, "w") as f:
        json.dump({
            "num_docs": num_docs,
            "num_chunks": len(all_chunks),
            "chunk_size": CHUNK_SIZE,
            "chunk_overlap": CHUNK_OVERLAP,
            "embed_model": args.model,
        }, f, indent=2)

    # Save chunk texts as newline-delimited file (memory-efficient)
    texts_path = os.path.join(args.output_dir, "chunks.jsonl")
    print(f"  Saving {len(chunk_texts):,} chunk texts to {texts_path}")
    with open(texts_path, "w") as f:
        for text in chunk_texts:
            f.write(json.dumps(text, ensure_ascii=False) + "\n")

    del all_chunks, chunk_meta  # free memory before embedding

    # ── Step 2: Embed chunks & build FAISS index (batched, memory-efficient) ─
    print(f"\n=== Step 2: Embed + build FAISS index ({len(chunk_texts):,} chunks) ===")
    print(f"  Model: {args.model}")
    print(f"  Batch size: {args.batch_size}")
    print(f"  Strategy: encode in batches → add to FAISS incrementally (low peak RAM)")

    from sentence_transformers import SentenceTransformer

    embed_model = SentenceTransformer(args.model)
    dim = embed_model.get_sentence_embedding_dimension()
    print(f"  Model loaded, dim={dim}")

    # Initialize FAISS index (inner product = cosine sim when vectors are normalized)
    index = faiss.IndexFlatIP(dim)

    t1 = time.time()
    ENCODE_BATCH = 50_000  # encode this many chunks at a time, then add to index & free

    for batch_start in range(0, len(chunk_texts), ENCODE_BATCH):
        batch_end = min(batch_start + ENCODE_BATCH, len(chunk_texts))
        batch_texts = chunk_texts[batch_start:batch_end]

        embeddings = embed_model.encode(
            batch_texts,
            batch_size=args.batch_size,
            show_progress_bar=True,
            normalize_embeddings=True,
        )
        embeddings = np.array(embeddings, dtype=np.float32)
        index.add(embeddings)

        elapsed = time.time() - t1
        rate = batch_end / elapsed if elapsed > 0 else 0
        print(f"  Embedded {batch_end:,}/{len(chunk_texts):,} "
              f"({elapsed:.0f}s, {rate:.0f} chunks/s, index={index.ntotal:,})")
        del embeddings  # free batch memory

    embed_time = time.time() - t1
    print(f"  Total embed time: {embed_time:.0f}s ({len(chunk_texts)/embed_time:.0f} chunks/s)")
    print(f"  FAISS index: {index.ntotal:,} vectors, dim={dim}")

    # Save index
    index_path = os.path.join(args.output_dir, "faiss_index.bin")
    faiss.write_index(index, index_path)
    index_size_mb = os.path.getsize(index_path) / 1024 / 1024
    print(f"  Saved to {index_path} ({index_size_mb:.0f} MB)")

    # ── Summary ──────────────────────────────────────────────────────────
    total_time = time.time() - t0
    print(f"\n{'='*60}")
    print(f"DONE in {total_time:.0f}s ({total_time/60:.1f} min)")
    print(f"  Docs:       {num_docs:,}")
    print(f"  Chunks:     {len(chunk_texts):,}")
    print(f"  Index:      {index_path} ({index_size_mb:.0f} MB)")
    print(f"  Metadata:   {meta_path}")
    print(f"  Chunk texts: {texts_path}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
