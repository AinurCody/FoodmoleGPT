# HPC Agent Task: Run LLM Inference for BO Warm-Start

## Goal

Run inference on **two models** (FoodmoleGPT and Qwen3-8B-Base), each selecting 3 candidate formulations from a list of 66. Save the results as JSON files.

## Background

This is for a Bayesian Optimization experiment. We need each LLM to pick 3 "most promising" formulations from 66 candidates, WITHOUT seeing the actual objective values. The LLM's domain knowledge determines which initial points to test.

- **FoodmoleGPT** = Qwen3-8B-Base + CPT LoRA (food science corpus) + SFT LoRA (food science instructions), adapters merged into base weights
- **Qwen3-8B-Base** = vanilla base model without any fine-tuning

## Step-by-step Instructions

### Step 1: Find model paths

Search the HPC filesystem for these two models:

**FoodmoleGPT (merged model):**
- This is a Qwen3-8B model with CPT and SFT LoRA adapters merged into the base weights
- Likely saved via LLaMA-Factory's `llamafactory-cli export` command
- Look in home directory, scratch space, work directory for folders containing "foodmole", "merged", "qwen3_cpt_sft", or similar names
- The directory should contain `config.json`, `tokenizer.json`, and `.safetensors` files
- Common search commands:
  ```bash
  find ~ -maxdepth 5 -name "config.json" -path "*merge*" -o -name "config.json" -path "*foodmole*" 2>/dev/null
  find ~ -maxdepth 5 -name "config.json" -path "*export*" -path "*qwen*" 2>/dev/null
  find /scratch -maxdepth 5 -name "config.json" -path "*merge*" 2>/dev/null
  find /hpctmp -maxdepth 5 -name "config.json" -path "*merge*" 2>/dev/null
  ```

**If the merged model does NOT exist**, you need to merge the adapters first:
1. Find the base Qwen3-8B model path
2. Find the CPT LoRA adapter (look for directories with `adapter_model.safetensors` and training args mentioning `stage: pt`)
3. Find the SFT LoRA adapter (look for `adapter_model.safetensors` with training args mentioning `stage: sft`)
4. Use LLaMA-Factory to merge:
   ```bash
   # First merge CPT adapter into base
   llamafactory-cli export \
     --model_name_or_path <qwen3-8b-base-path> \
     --adapter_name_or_path <cpt-adapter-path> \
     --template qwen3 \
     --finetuning_type lora \
     --export_dir /tmp/qwen3_cpt_merged

   # Then merge SFT adapter on top
   llamafactory-cli export \
     --model_name_or_path /tmp/qwen3_cpt_merged \
     --adapter_name_or_path <sft-adapter-path> \
     --template qwen3 \
     --finetuning_type lora \
     --export_dir /tmp/foodmolegpt_merged
   ```
   Or if there's already a two-stage merged checkpoint, use that directly.

**Qwen3-8B-Base:**
- Look for the original Qwen3-8B or Qwen3-8B-Base download
- Common locations: `~/.cache/huggingface/`, `~/models/`, project directories
- Search: `find ~ -maxdepth 5 -name "config.json" -path "*Qwen3*8B*" 2>/dev/null`

### Step 2: Upload and run the inference script

I'm providing the file `hpc_run_inference.py`. Place it somewhere accessible and run:

```bash
# If using Singularity container:
singularity exec --nv <container.sif> python hpc_run_inference.py \
  --foodmolegpt-path <path-to-foodmolegpt-merged> \
  --qwen3base-path <path-to-qwen3-8b-base> \
  --output-dir ./llm_results

# Or if using conda:
python hpc_run_inference.py \
  --foodmolegpt-path <path-to-foodmolegpt-merged> \
  --qwen3base-path <path-to-qwen3-8b-base> \
  --output-dir ./llm_results
```

This script needs: `torch`, `transformers` (with Qwen3 support). If Singularity container has these, great. Otherwise install: `pip install transformers>=4.40 torch`.

If running on a compute node (not login node), you may need to submit via PBS:
```bash
qsub -I -l select=1:ngpus=1:mem=64gb -l walltime=00:30:00
# then run the python command above
```

### Step 3: Verify outputs

The script produces two JSON files:
- `foodmolegpt_init.json`
- `qwen3base_init.json`

Each should look like:
```json
{
  "model": "foodmolegpt",
  "k": 3,
  "n_candidates": 66,
  "selected": [20, 9, 14],
  "reasoning": "...",
  "raw_response": "..."
}
```

**Verify that:**
1. `selected` contains exactly 3 integers
2. Each index is between 0 and 65
3. No duplicates
4. The reasoning makes food science sense

### Step 4: Output the results

Print the final contents of both JSON files so I can copy them back to my local machine.

## Important Notes

- The script does NOT show the LLM any objective/DPPH values — this is intentional. The LLM must rely on domain knowledge only.
- Use `do_sample=False` (greedy decoding) for reproducibility.
- Single GPU is enough — the 8B model in bf16 uses ~16GB VRAM, well within H200's 141GB.
- If you can't find the merged FoodmoleGPT model, at minimum run Qwen3-base and report what model paths you found.
