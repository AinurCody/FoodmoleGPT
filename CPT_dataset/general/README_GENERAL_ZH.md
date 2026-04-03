# FoodmoleGPT — FineWeb-2 通用领域语料

## 数据概览

| 指标 | 值 |
|------|------|
| **来源** | FineWeb（HuggingFaceFW）— 高质量英文网络语料 |
| **数据集** | `HuggingFaceFW/fineweb`（纯英文版；FineWeb-2 是多语言版但不含英文） |
| **采样方式** | 系统采样（每 N 篇取 1 篇） |
| **目标 tokens** | ~800M（占 CPT 总语料约 20%） |
| **输出格式** | `{"text": "..."}` |
| **用途** | 通用领域"回放"语料，防止 CPT 阶段灾难性遗忘 |

---

## 为什么选择 FineWeb？

- 经过充分清洗和去重的网络语料（总量 15T+ tokens）
- 质量过滤流水线：URL 过滤、语言检测、困惑度过滤、去重
- 社区公认的最高质量开源英文网络语料之一
- 支持 streaming 模式 — 无需下载全量数据

---

## 复现步骤

### 环境准备

```bash
conda activate nus_study
pip install datasets tqdm
```

### 运行

```bash
cd /Users/cody/Workspace/FoodmoleGPT/CPT_dataset/general

# 默认：~800M tokens，采样率 1/50
python download_fineweb2.py

# 自定义目标和采样率
python download_fineweb2.py --max-tokens 600000000 --sample-rate 100
```

### 输出文件

```
general/
├── README_GENERAL_EN.md
├── README_GENERAL_ZH.md
├── download_fineweb2.py
└── data/
    ├── fineweb2_general_cpt.jsonl    # CPT 训练格式（可直接用于训练）
    └── sample_stats.json             # 采样统计
```

---

## 采样策略

- **系统采样**：每 N 篇文档取 1 篇（默认 N=50）
- **长度过滤**：跳过不足 500 字符或超过 50,000 字符的文档
- **不做领域过滤**：刻意保持通用性，保留广泛知识

这种方式能均匀覆盖 FineWeb 的多样化网页内容，同时控制语料规模。

---

## Token 估算

Token 数按 `词数 × 1.3` 估算（英文 BPE 分词器的常用近似值）。如需精确计数，请在生成后用目标模型的 tokenizer 重新统计。
