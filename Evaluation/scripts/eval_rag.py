#!/usr/bin/env python3
"""RAG evaluation for FoodmoleGPT ablation study.

Retrieves top-k passages from FAISS index, prepends to MCQ prompt,
then evaluates Base models. Reuses eval_mcq.py's model loading and
answer extraction logic.

Usage (inside singularity container on GPU node):
    python eval_rag.py                                    # both base models, all benchmarks
    python eval_rag.py --data cpt_mcq_200.json            # specific benchmark
    python eval_rag.py --top-k 3                          # retrieve 3 passages
    python eval_rag.py qwen3                              # only Qwen3-Base + RAG
"""
import argparse
import json
import os
import re
import sys
import time
import numpy as np
import faiss
import torch
from pathlib import Path

# Reuse components from eval_mcq
from eval_mcq import (
    extract_answer,
    load_model_and_tokenizer,
    build_input,
    QWEN3_BASE,
    LLAMA3_BASE,
)

# ── Paths ────────────────────────────────────────────────────────────────
INDEX_DIR = "/scratch/$USER/foodmole_workspace/data/rag_index"
MCQ_DIR = "/scratch/$USER/foodmole_workspace/data/food_mcq"

# Default benchmarks to evaluate
BENCHMARKS = [
    {"file": "cpt_mcq_200.json", "name": "CPT-MCQ"},
    {"file": "canvas_multiple_171.json", "name": "Canvas-MCQ"},
    {"file": "mmlu_200.json", "name": "MMLU-subset"},
]

CKPT_DIR = "/scratch/$USER/foodmole_workspace/checkpoints"

# RAG models: Base and fine-tuned models with retrieval augmentation
RAG_MODELS = [
    {
        "name": "Qwen3-Base+RAG",
        "base": QWEN3_BASE,
        "adapters": [],
        "trust_remote_code": True,
    },
    {
        "name": "Llama3-Base+RAG",
        "base": LLAMA3_BASE,
        "adapters": [],
        "trust_remote_code": False,
    },
    {
        "name": "Qwen3-CPT+SFT+RAG",
        "base": QWEN3_BASE,
        "adapters": [
            f"{CKPT_DIR}/qwen3-8b-cpt",
            f"{CKPT_DIR}/qwen3-8b-cpt-sft-lora-foodmole",
        ],
        "trust_remote_code": True,
    },
    {
        "name": "Llama3-CPT+SFT+RAG",
        "base": LLAMA3_BASE,
        "adapters": [
            f"{CKPT_DIR}/llama3-8b-cpt",
            f"{CKPT_DIR}/llama3-8b-cpt-sft-lora-foodmole",
        ],
        "trust_remote_code": False,
    },
    {
        "name": "Qwen3-SFT+RAG",
        "base": QWEN3_BASE,
        "adapters": [f"{CKPT_DIR}/qwen3-8b-sft-lora-foodmole"],
        "trust_remote_code": True,
    },
    {
        "name": "Llama3-SFT+RAG",
        "base": LLAMA3_BASE,
        "adapters": [f"{CKPT_DIR}/llama3-8b-sft-lora-foodmole"],
        "trust_remote_code": False,
    },
]

# ── Retrieval ────────────────────────────────────────────────────────────
TOP_K = 5  # number of passages to retrieve


def load_index(index_dir):
    """Load FAISS index and chunk texts."""
    index_path = os.path.join(index_dir, "faiss_index.bin")
    texts_path = os.path.join(index_dir, "chunks.jsonl")
    meta_path = os.path.join(index_dir, "chunk_metadata.json")

    print(f"Loading FAISS index from {index_path}")
    index = faiss.read_index(index_path)
    print(f"  Index: {index.ntotal:,} vectors")

    print(f"Loading chunk texts from {texts_path}")
    chunk_texts = []
    with open(texts_path) as f:
        for line in f:
            chunk_texts.append(json.loads(line))
    print(f"  Loaded {len(chunk_texts):,} chunks")

    with open(meta_path) as f:
        meta = json.load(f)
    print(f"  Index config: {meta}")

    return index, chunk_texts, meta


def load_embed_model(model_name):
    """Load sentence-transformers model for query encoding."""
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(model_name)
    return model


def retrieve(query, embed_model, index, chunk_texts, top_k=TOP_K):
    """Retrieve top-k passages for a query.

    BGE models benefit from a query prefix for asymmetric retrieval.
    """
    # BGE-base uses "Represent this sentence: " prefix for queries
    query_with_prefix = f"Represent this sentence: {query}"
    query_vec = embed_model.encode(
        [query_with_prefix],
        normalize_embeddings=True,
    ).astype(np.float32)

    scores, indices = index.search(query_vec, top_k)
    results = []
    for score, idx in zip(scores[0], indices[0]):
        if idx < len(chunk_texts):
            results.append({
                "text": chunk_texts[idx],
                "score": float(score),
                "chunk_idx": int(idx),
            })
    return results


def format_rag_prompt(question, passages, few_shot_examples=None):
    """Format MCQ prompt with retrieved passages prepended.

    Structure:
        [Retrieved Context]
        ---
        [Instruction + Question]
    """
    # Build context section
    context_parts = ["The following passages may contain relevant information:\n"]
    for i, p in enumerate(passages, 1):
        # Truncate very long passages to keep prompt manageable
        text = p["text"][:1500]
        context_parts.append(f"[Passage {i}]\n{text}\n")

    context = "\n".join(context_parts)

    # MCQ instruction (same as eval_mcq.py)
    instruction = (
        "Based on the passages above and your knowledge, answer the following question. "
        "Select ALL correct options. "
        "Output ONLY the letter(s) of your answer (e.g., A or ABD), nothing else."
    )

    parts = [context, "---", instruction]

    # Few-shot examples (if any)
    if few_shot_examples:
        for ex in few_shot_examples:
            ex_opts = "\n".join(f"{k}. {v}" for k, v in ex["options"].items())
            gt = "".join(sorted(ex["answer"]))
            parts.append(f"\nQuestion: {ex['question']}\n{ex_opts}\n\nAnswer: {gt}")

    # The actual question
    opts = "\n".join(f"{k}. {v}" for k, v in question["options"].items())
    parts.append(f"\nQuestion: {question['question']}\n{opts}\n\nAnswer:")

    return "\n".join(parts)


def evaluate_rag_model(model_config, questions, embed_model, index, chunk_texts,
                       top_k=TOP_K, few_shot_examples=None):
    """Evaluate a single model with RAG on all questions."""
    name = model_config["name"]
    print(f"\n{'=' * 60}")
    print(f"Evaluating: {name} (top-{top_k} retrieval)")
    print(f"{'=' * 60}")

    t0 = time.time()
    model, tokenizer, is_sft = load_model_and_tokenizer(model_config)
    load_time = time.time() - t0
    print(f"  LLM loaded in {load_time:.1f}s")

    results = []
    correct = 0
    t1 = time.time()

    for i, q in enumerate(questions):
        # Retrieve relevant passages
        query = q["question"]
        passages = retrieve(query, embed_model, index, chunk_texts, top_k)

        # Build RAG-augmented prompt
        prompt_text = format_rag_prompt(q, passages, few_shot_examples)
        inputs = build_input(prompt_text, tokenizer, is_sft)
        inputs = {k: v.to(model.device) for k, v in inputs.items()}

        with torch.no_grad():
            outputs = model.generate(
                **inputs,
                max_new_tokens=30,
                do_sample=False,
            )

        generated = tokenizer.decode(
            outputs[0][inputs["input_ids"].shape[1]:],
            skip_special_tokens=True,
        )

        valid_opts = set(q["options"].keys())
        predicted = extract_answer(generated, valid_opts)
        ground_truth = "".join(sorted(q["answer"]))
        is_correct = predicted == ground_truth

        if is_correct:
            correct += 1

        results.append({
            "id": q["id"],
            "question": q["question"][:80],
            "ground_truth": ground_truth,
            "predicted": predicted,
            "raw_output": generated[:200],
            "correct": is_correct,
            "type": q.get("type", "unknown"),
            "category": q.get("category", "unknown"),
            "top_passage_score": passages[0]["score"] if passages else 0,
            "num_passages": len(passages),
        })

        if (i + 1) % 20 == 0:
            print(f"  Progress: {i+1}/{len(questions)} | Acc so far: {correct/(i+1):.1%}")

    eval_time = time.time() - t1

    # Breakdown by type
    single = [r for r in results if r["type"] == "single_choice"]
    multi = [r for r in results if r["type"] == "multiple_choice"]
    single_acc = sum(r["correct"] for r in single) / len(single) if single else 0
    multi_acc = sum(r["correct"] for r in multi) / len(multi) if multi else 0

    # Breakdown by category
    cats = {}
    for r in results:
        cat = r["category"]
        if cat not in cats:
            cats[cat] = {"correct": 0, "total": 0}
        cats[cat]["total"] += 1
        if r["correct"]:
            cats[cat]["correct"] += 1

    accuracy = correct / len(questions)
    print(f"\n  Overall:  {correct}/{len(questions)} = {accuracy:.1%}")
    print(f"  Single:   {sum(r['correct'] for r in single)}/{len(single)} = {single_acc:.1%}")
    print(f"  Multiple: {sum(r['correct'] for r in multi)}/{len(multi)} = {multi_acc:.1%}")
    print(f"  Eval time: {eval_time:.1f}s")
    print(f"  Avg retrieval score: {np.mean([r['top_passage_score'] for r in results]):.3f}")

    # Free GPU memory
    del model
    torch.cuda.empty_cache()

    return {
        "model": name,
        "accuracy": accuracy,
        "single_acc": single_acc,
        "multi_acc": multi_acc,
        "correct": correct,
        "total": len(questions),
        "top_k": top_k,
        "load_time_s": round(load_time, 1),
        "eval_time_s": round(eval_time, 1),
        "per_category": {k: v["correct"] / v["total"] for k, v in sorted(cats.items())},
        "details": results,
    }


def main():
    parser = argparse.ArgumentParser(description="RAG Evaluation for FoodmoleGPT")
    parser.add_argument("filters", nargs="*", help="Model name filters (e.g., qwen3 llama3)")
    parser.add_argument("--data", type=str, default=None,
                        help="Specific MCQ JSON file (basename or full path). If omitted, runs all benchmarks.")
    parser.add_argument("--output", type=str, default=None,
                        help="Output JSON path (default: auto-generated in MCQ dir)")
    parser.add_argument("--top-k", type=int, default=TOP_K, help=f"Number of passages to retrieve (default: {TOP_K})")
    parser.add_argument("--few-shot", type=int, default=0, help="Number of few-shot examples")
    parser.add_argument("--index-dir", default=INDEX_DIR, help="FAISS index directory")
    parser.add_argument("--embed-model", default="BAAI/bge-base-en-v1.5", help="Embedding model for queries")
    args = parser.parse_args()

    # Load retrieval components (shared across all models and benchmarks)
    print("=== Loading retrieval components ===")
    index, chunk_texts, meta = load_index(args.index_dir)
    embed_model = load_embed_model(args.embed_model)
    print(f"  Embed model: {args.embed_model}")

    # Filter models
    models_to_eval = RAG_MODELS
    if args.filters:
        models_to_eval = [m for m in RAG_MODELS
                          if any(f.lower() in m["name"].lower() for f in args.filters)]
    if not models_to_eval:
        print(f"No models matched filters: {args.filters}")
        print(f"Available: {[m['name'] for m in RAG_MODELS]}")
        sys.exit(1)
    print(f"  Models: {[m['name'] for m in models_to_eval]}")

    # Determine benchmarks
    if args.data:
        data_path = args.data if os.path.isabs(args.data) else os.path.join(MCQ_DIR, args.data)
        benchmarks = [{"file": os.path.basename(data_path), "name": Path(data_path).stem, "path": data_path}]
    else:
        benchmarks = [
            {**b, "path": os.path.join(MCQ_DIR, b["file"])}
            for b in BENCHMARKS
        ]

    # Evaluate each benchmark
    for bench in benchmarks:
        data_path = bench["path"]
        if not os.path.exists(data_path):
            print(f"\nWARNING: Skipping {bench['name']} — file not found: {data_path}")
            continue

        with open(data_path) as f:
            questions = json.load(f)
        print(f"\n{'#' * 60}")
        print(f"# Benchmark: {bench['name']} ({len(questions)} questions)")
        print(f"{'#' * 60}")

        # Few-shot setup
        few_shot_examples = None
        eval_questions = questions
        if args.few_shot > 0:
            few_shot_examples = questions[:args.few_shot]
            eval_questions = questions[args.few_shot:]
            print(f"  Few-shot: {args.few_shot} examples, evaluating {len(eval_questions)} questions")

        # Output path
        if args.output:
            output_path = args.output
        else:
            suffix = f"_top{args.top_k}"
            if args.few_shot > 0:
                suffix += f"_{args.few_shot}shot"
            output_path = os.path.join(MCQ_DIR, f"eval_rag_{bench['name'].lower().replace('-', '_')}{suffix}.json")

        # Evaluate each model on this benchmark
        all_results = []
        for model_config in models_to_eval:
            try:
                result = evaluate_rag_model(
                    model_config, eval_questions, embed_model, index, chunk_texts,
                    top_k=args.top_k, few_shot_examples=few_shot_examples,
                )
                all_results.append(result)

                # Incremental save
                existing = {}
                if Path(output_path).exists():
                    with open(output_path) as f:
                        existing = json.load(f)
                save_data = existing if existing else {
                    "eval_date": "",
                    "benchmark": bench["name"],
                    "num_questions": len(eval_questions),
                    "few_shot": args.few_shot,
                    "top_k": args.top_k,
                    "embed_model": args.embed_model,
                    "results": {},
                    "details": {},
                }
                save_data["eval_date"] = time.strftime("%Y-%m-%d %H:%M")
                name = result["model"]
                save_data["results"][name] = {k: v for k, v in result.items() if k != "details"}
                save_data["details"][name] = result["details"]
                with open(output_path, "w") as f:
                    json.dump(save_data, f, indent=2, ensure_ascii=False)
                print(f"  Results saved to {output_path}")
            except Exception as e:
                print(f"\nERROR evaluating {model_config['name']}: {e}")
                import traceback
                traceback.print_exc()
                torch.cuda.empty_cache()

        # Summary for this benchmark
        if all_results:
            print(f"\n{'='*60}")
            print(f"SUMMARY — {bench['name']}")
            print(f"{'='*60}")
            print(f"{'Model':<25} {'Overall':>8} {'Single':>8} {'Multi':>8}")
            print("-" * 55)
            for r in all_results:
                print(f"{r['model']:<25} {r['accuracy']:>7.1%} {r['single_acc']:>7.1%} {r['multi_acc']:>7.1%}")


if __name__ == "__main__":
    main()
