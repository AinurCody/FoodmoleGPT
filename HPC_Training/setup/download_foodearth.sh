#!/bin/bash
# =============================================================================
# download_foodearth.sh
# 从 Zenodo 下载 FoodEarth 数据集并解压
# 用法：bash scripts/download_foodearth.sh
# 可在登录节点直接运行（网络 I/O，不占 CPU）
# =============================================================================

set -e

DATA_DIR="/scratch/$USER/foodmole_workspace/data"
ZIP_FILE="$DATA_DIR/FoodEarth-Complete.zip"
ZENODO_URL="https://zenodo.org/records/14892842/files/FoodEarth-Complete.zip?download=1"

echo "=== 下载 FoodEarth-Complete.zip (589 MB) ==="
wget -c --progress=bar:force \
    -O "$ZIP_FILE" \
    "$ZENODO_URL"

echo "=== 解压到 $DATA_DIR/FoodEarth/ ==="
unzip -o "$ZIP_FILE" -d "$DATA_DIR/FoodEarth/"

echo "=== 解压结果 ==="
ls -lh "$DATA_DIR/FoodEarth/"

echo "=== 完成 ==="
