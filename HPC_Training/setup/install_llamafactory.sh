#!/bin/bash
# =============================================================================
# install_llamafactory.sh
# 在登录节点通过 Singularity 容器创建 virtualenv 并安装 LLaMA-Factory
# 容器：pytorch_26.01-py3.sif（Python 3.12.3，PyTorch 预装）
# 用法：bash scripts/install_llamafactory.sh
# =============================================================================

set -e

IMAGE="/app1/common/singularity-img/hopper/pytorch/pytorch_26.01-py3.sif"
VENV="/scratch/$USER/virtualenvs/foodmole"
LLAMAFACTORY_DIR="/scratch/$USER/LLaMA-Factory"

echo "=== Step 1: 加载 Singularity 模块 ==="
source /app1/ebapps/ebenv_hopper.sh
module load singularity

echo "=== Step 2: 在容器内创建 virtualenv 并安装 LLaMA-Factory ==="
singularity exec -e "$IMAGE" bash << 'EOF'
set -e

VENV="/scratch/$USER/virtualenvs/foodmole"
LLAMAFACTORY_DIR="/scratch/$USER/LLaMA-Factory"

# 检查已有 venv 的 Python 版本是否匹配，不匹配则删除重建
if [ -d "$VENV" ]; then
    VENV_PYTHON="$VENV/bin/python"
    if [ ! -x "$VENV_PYTHON" ] || ! "$VENV_PYTHON" --version &>/dev/null; then
        echo "--- 旧 virtualenv 不可用（Python 版本不兼容），删除重建 ---"
        rm -rf "$VENV"
    else
        VENV_VER=$("$VENV_PYTHON" -c "import sys; print(sys.version_info[:2])")
        echo "--- virtualenv 已存在，Python 版本：$VENV_VER ---"
    fi
fi

if [ ! -d "$VENV" ]; then
    echo "--- 创建 virtualenv (--system-site-packages): $VENV ---"
    python -m venv --system-site-packages "$VENV"
fi

source "$VENV/bin/activate"

# 克隆 LLaMA-Factory
if [ ! -d "$LLAMAFACTORY_DIR" ]; then
    echo "--- 克隆 LLaMA-Factory ---"
    git clone --depth 1 https://github.com/hiyouga/LLaMA-Factory.git "$LLAMAFACTORY_DIR"
else
    echo "--- LLaMA-Factory 目录已存在，跳过克隆 ---"
fi

# 安装 LLaMA-Factory
# 不用 extras：torch 已由容器提供，modelscope 不需要（我们用 HuggingFace）
echo "--- 安装 LLaMA-Factory 核心依赖 ---"
cd "$LLAMAFACTORY_DIR"

# 第一步：仅安装 LLaMA-Factory 本体（不递归安装 extras）
pip install --timeout 120 -e "." --no-deps

# 第二步：手动安装实际需要的依赖（排除 modelscope/tensorflow）
pip install --timeout 120 \
    "transformers>=4.51.0,<=5.2.0" \
    "datasets>=2.16.0,<4.1.0" \
    "accelerate>=1.3.0,<=1.11.0" \
    "peft>=0.18.0,<=0.18.1" \
    "trl>=0.18.0,<=0.24.0" \
    sentencepiece \
    tiktoken \
    protobuf \
    scipy \
    rouge-score \
    nltk \
    jieba \
    av \
    torchaudio

echo ""
echo "=== 验证安装 ==="
llamafactory-cli version
python -c "import torch; print(f'PyTorch: {torch.__version__}, CUDA: {torch.version.cuda}')"
echo "=== 安装完成 ==="
EOF

echo "=== install_llamafactory.sh 执行完毕 ==="
