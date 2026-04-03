"""
FoodmoleGPT — Download & Sample General SFT Data (v2)

Downloads and samples from 2 high-quality general SFT datasets,
converts to Alpaca format, and merges into a single file.

Changes from v1:
  - Removed Nemotron entirely (caused identity contamination:
    model outputs "Nemotron here, created by NVIDIA")
  - Increased SmolTalk allocations to compensate for lost 5K:
      smol-magpie-ultra:  5000 → 7000
      openhermes-100k:    2000 → 3000
      numina-cot-100k:    2000 → 2500
      self-oss-instruct:  2000 → 2500
  - SmolTalk subtotal: 15K → 20K
  - Orca AgentInstruct unchanged: 10K
  - Grand total: 30K (unchanged)

Target: ~30K general instruction pairs
  - smoltalk:           20K (diverse instruction following)
  - orca-agentinstruct: 10K (complex reasoning)

Usage:
    python download_general_sft_v2.py
"""

import json
import random
from pathlib import Path
from datetime import datetime
from datasets import load_dataset

SEED = 42
random.seed(SEED)
OUTPUT_DIR = Path(__file__).resolve().parent / "output"


def messages_to_alpaca(messages: list[dict]) -> dict | None:
    """Convert a chat-format message list to Alpaca format.

    Takes the first complete user→assistant turn.
    Supports optional system prompt prepended to instruction.
    """
    system = ""
    user_msg = ""
    assistant_msg = ""

    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content", "")
        if not content or not content.strip():
            continue

        if role == "system" and not user_msg:
            system = content.strip()
        elif role == "user" and not user_msg:
            user_msg = content.strip()
        elif role == "assistant" and user_msg and not assistant_msg:
            assistant_msg = content.strip()
            break

    if not user_msg or not assistant_msg:
        return None

    # Prepend system prompt to instruction if present
    instruction = f"{system}\n\n{user_msg}" if system else user_msg

    # Quality filters
    if len(instruction) < 10 or len(assistant_msg) < 20:
        return None
    if len(assistant_msg) > 8000:  # Skip extremely long outputs
        return None

    return {
        "instruction": instruction,
        "input": "",
        "output": assistant_msg,
    }


def parse_orca_messages(messages_field) -> list[dict] | None:
    """Parse orca-agentinstruct messages field (can be JSON string or list)."""
    if isinstance(messages_field, str):
        try:
            return json.loads(messages_field)
        except json.JSONDecodeError:
            return None
    elif isinstance(messages_field, list):
        return messages_field
    return None


def sample_from_dataset(dataset, n: int) -> list:
    """Randomly sample n items from a HuggingFace dataset."""
    total = len(dataset)
    if total <= n:
        return list(range(total))
    indices = random.sample(range(total), n)
    return indices


# ══════════════════════════════════════════════════════════════════
# 1. SmolTalk — 20K from diverse subsets
# ══════════════════════════════════════════════════════════════════
def download_smoltalk():
    print("=" * 60)
    print("[1/2] SmolTalk — downloading & sampling 20K...")
    print("=" * 60)

    subset_plan = {
        "smol-magpie-ultra":      7000,   # Core general instruction following (increased from 5000)
        "openhermes-100k":        3000,   # Diverse QA (increased from 2000)
        "numina-cot-100k":        2500,   # Math reasoning with CoT (increased from 2000)
        "self-oss-instruct":      2500,   # Code/programming (increased from 2000)
        "metamathqa-50k":         2000,   # Math
        "everyday-conversations": 1000,   # Casual chat
        "smol-constraints":       1000,   # Constrained generation
    }

    results = []
    for subset, n in subset_plan.items():
        print(f"  Loading {subset}...", end=" ", flush=True)
        try:
            ds = load_dataset("HuggingFaceTB/smoltalk", subset, split="train")
            indices = sample_from_dataset(ds, n)
            count = 0
            for idx in indices:
                row = ds[idx]
                msgs = row.get("messages", [])
                alpaca = messages_to_alpaca(msgs)
                if alpaca:
                    alpaca["general_source"] = f"smoltalk/{subset}"
                    results.append(alpaca)
                    count += 1
            print(f"✓ {count}/{n}")
        except Exception as e:
            print(f"✗ Error: {e}")

    print(f"  SmolTalk total: {len(results)}")
    return results


# ══════════════════════════════════════════════════════════════════
# 2. Orca AgentInstruct — 10K from diverse splits
# ══════════════════════════════════════════════════════════════════
def download_orca():
    print()
    print("=" * 60)
    print("[2/2] Orca AgentInstruct — downloading & sampling 10K...")
    print("=" * 60)

    split_plan = {
        "open_domain_qa":       2000,   # General QA
        "analytical_reasoning": 2000,   # Reasoning
        "mcq":                  1500,   # Multiple choice
        "creative_content":     1000,   # Creative writing
        "text_modification":    1000,   # Text editing
        "rc":                   1000,   # Reading comprehension
        "code_":                1000,   # Coding
        "fs_cot_flow":          500,    # Few-shot CoT
    }

    results = []
    for split_name, n in split_plan.items():
        print(f"  Loading {split_name}...", end=" ", flush=True)
        try:
            ds = load_dataset(
                "microsoft/orca-agentinstruct-1M-v1",
                split=split_name,
            )
            indices = sample_from_dataset(ds, n)
            count = 0
            for idx in indices:
                row = ds[idx]
                msgs = parse_orca_messages(row.get("messages", ""))
                if msgs is None:
                    continue
                alpaca = messages_to_alpaca(msgs)
                if alpaca:
                    alpaca["general_source"] = f"orca/{split_name}"
                    results.append(alpaca)
                    count += 1
            print(f"✓ {count}/{n}")
        except Exception as e:
            print(f"✗ Error: {e}")

    print(f"  Orca total: {len(results)}")
    return results


# ══════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════
def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    smoltalk_data = download_smoltalk()
    orca_data = download_orca()

    # Merge all
    all_general = smoltalk_data + orca_data
    random.shuffle(all_general)

    print()
    print("=" * 60)
    print("  WRITING OUTPUT")
    print("=" * 60)

    # Write Alpaca format (for training — no general_source field)
    alpaca_file = OUTPUT_DIR / "general_sft_30k_v2.jsonl"
    with open(alpaca_file, "w", encoding="utf-8") as f:
        for item in all_general:
            record = {
                "instruction": item["instruction"],
                "input": item["input"],
                "output": item["output"],
            }
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    # Write full version with source metadata
    full_file = OUTPUT_DIR / "general_sft_30k_v2_full.jsonl"
    with open(full_file, "w", encoding="utf-8") as f:
        for item in all_general:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    # Stats
    source_counts = {}
    for item in all_general:
        src = item.get("general_source", "unknown")
        top_src = src.split("/")[0]
        source_counts[top_src] = source_counts.get(top_src, 0) + 1

    stats = {
        "generated_at": datetime.now().isoformat(),
        "total": len(all_general),
        "source_distribution": source_counts,
        "seed": SEED,
    }

    stats_file = OUTPUT_DIR / "general_sft_v2_stats.json"
    with open(stats_file, "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2)

    print(f"  Total general SFT pairs: {len(all_general)}")
    print(f"  Source breakdown: {source_counts}")
    print(f"  Output: {alpaca_file}")
    print(f"  Stats:  {stats_file}")
    print("=" * 60)


if __name__ == "__main__":
    main()
