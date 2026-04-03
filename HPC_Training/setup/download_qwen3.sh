#!/bin/bash
# =============================================================================
# download_qwen3.sh
# Download Qwen/Qwen3-8B-Base from HuggingFace to huggingface_cache
# Usage: bash scripts/download_qwen3.sh
# Safe to run on login node (network I/O only, no GPU computation)
# =============================================================================

set -e

IMAGE="/app1/common/singularity-img/hopper/pytorch/pytorch_26.01-py3.sif"
PYTHON="/scratch/$USER/virtualenvs/foodmole/bin/python"
HF_CACHE="/scratch/$USER/huggingface_cache"
MODEL_DIR="$HF_CACHE/hub/models--Qwen--Qwen3-8B-Base"

source /app1/ebapps/ebenv_hopper.sh
module load singularity

echo "=== Downloading Qwen/Qwen3-8B-Base ==="
singularity exec -e "$IMAGE" bash << EOF
export HF_HOME=$HF_CACHE
export TRANSFORMERS_CACHE=$HF_CACHE/hub

$PYTHON -c "
from huggingface_hub import snapshot_download
snapshot_download(
    'Qwen/Qwen3-8B-Base',
    local_dir='$MODEL_DIR',
    local_dir_use_symlinks=False,
)
print('Download complete.')
"

echo "=== Files in model directory ==="
ls -lh $MODEL_DIR/
EOF

echo "=== download_qwen3.sh done ==="
