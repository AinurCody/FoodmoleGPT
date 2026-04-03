# FoodmoleGPT — OpenAlex 食品科学论文采集流水线

## 项目概述

本模块为 FoodmoleGPT（食品科学领域大语言模型）的 **论文采集与处理** 流水线。通过两轮数据采集（R1 多策略混合 + R2 期刊定向），经过清洗、全文获取、过滤、文本质量清洗和格式化，最终产出 **578,956 篇** 食品科学文献的结构化训练数据（含 **145,594 篇全文**，**433,362 篇摘要**），总大小约 **5.8 GB**。

> 详细的技术文档、面试要点和设计决策见：[`docs/data_pipeline.md`](docs/data_pipeline.md)

---

## 目录结构

```
CPT_dataset/essay/OpenAlex/          # 本目录
├── .env                             # API Key (S2_API_KEY)
├── .gitignore
├── README.md                        # 本文件（中文）
├── README_EN.md                     # 英文版说明
├── docs/
│   └── data_pipeline.md             # 完整技术文档（11 章）
├── src/                             # 采集与处理脚本
│   ├── # ---- Round 1 ----
│   ├── fetch_openalex.py            # R1 关键词搜索采集
│   ├── fetch_openalex_bulk.py       # R1 批量采集
│   ├── fetch_openalex_concepts.py   # R1 Concept ID 采集
│   ├── fetch_remaining_concepts.py  # R1 补充采集
│   ├── fetch_expand_topics.py       # R1 细分领域扩展
│   ├── fetch_hybrid.py              # R1 混合策略采集
│   ├── fetch_scopus.py              # Scopus 采集（备用）
│   ├── clean_data.py                # R1 数据清洗
│   ├── fetch_fulltext_s2.py         # R1 全文获取 (S2 + peS2o)
│   ├── merge_fulltext.py            # R1 元数据+全文合并
│   ├── filter_food.py               # 三层食品科学过滤器（R1+R2 共用）
│   ├── format_training.py           # R1 训练格式转换
│   ├── # ---- Round 2 ----
│   ├── fetch_openalex_r2.py         # R2 期刊定向采集（75 个核心期刊）
│   ├── clean_data_r2.py             # R2 数据清洗
│   ├── fetch_fulltext_s2_r2.py      # R2 全文获取
│   ├── merge_fulltext_r2.py         # R2 合并
│   ├── filter_food_r2.py            # R2 过滤（兜底）
│   ├── clean_text_quality.py        # 文本质量清洗（表格/mojibake/Unicode）
│   ├── format_training_r2.py        # R2 格式化 + R1+R2 合并
│   └── audit_purity.py              # 纯净度审计工具
├── fulltext.jsonl                   # ★ 全文训练数据 — 145,594 篇 (5.1 GB)
├── abstract.jsonl                   # ★ 摘要训练数据 — 433,362 篇 (715 MB)
└── doi_fulltext_only.txt            # 全文论文 DOI 列表（用于跨源去重）
```

> **注**：原始采集阶段的中间数据（raw/cleaned/filtered 等）保留在源机器上，未迁移。本目录只保留最终输出数据和完整的脚本与文档，可完整复现。

---

## 数据处理全流程

### Round 1：多策略混合采集

| 阶段 | 脚本 | 说明 | 结果 |
|------|------|------|------|
| 采集 | `fetch_openalex*.py` 等 | 关键词+Concept ID 多策略混合 | ~1,040,000 篇 |
| 清洗 | `clean_data.py` | DOI/标题去重、HTML清洗、Unicode修复 | 1,033,239 篇 |
| 全文 | `fetch_fulltext_s2.py` | S2 Batch API + peS2o 136文件扫描 | 312,533 篇全文 |
| 合并 | `merge_fulltext.py` | 元数据+全文 → JSONL | 11.74 GB |
| 过滤 | `filter_food.py` | 三层过滤（期刊/标题/关键词） | 91,889 全文 + 81,248 摘要 |
| 格式化 | `format_training.py` | JSONL `{"text": "..."}` | **173,137 篇** |

**R1 核心问题**：OpenAlex Concept 标签的低相关度噪声导致 ~76% 为非食品论文，需重过滤。

### Round 2：期刊定向采集

| 阶段 | 脚本 | 说明 | 结果 |
|------|------|------|------|
| 采集 | `fetch_openalex_r2.py` | 75 个食品科学核心期刊 Source ID 定向 | 791,793 篇 |
| 清洗 | `clean_data_r2.py` | 同 R1 流程 + 跨轮 DOI 去重 | 766,316 篇 |
| 全文 | `fetch_fulltext_s2_r2.py` | Phase 1: 98.4% DOI→ID; Phase 2: peS2o | 53,726 篇全文 |
| 合并 | `merge_fulltext_r2.py` | 元数据+全文 → JSONL | 1.8 GB |
| 过滤 | `filter_food_r2.py` | 三层过滤兜底（期刊定向已 >99% 纯净） | 53,705 全文 + 352,114 摘要 |
| 质量清洗 | `clean_text_quality.py` | 表格残留/mojibake/Unicode数学 修复 | 21 条修改 |
| 格式化 | `format_training_r2.py` | 格式化 + R1+R2 合并 | **405,819 篇** |

**R2 核心改进**：从"标签查询+下游过滤"改为"源头期刊控制"，纯净度从 24% 提升到 >99%。

### 合并与最终输出

```
format_training_r2.py --merge
  R1: fulltext_train + fulltext_val → 合并
  R2: fulltext.jsonl                → 直接追加
  输出: training_combined/fulltext.jsonl  (145,594 records, 5.10 GB)
        training_combined/abstract.jsonl  (433,362 records, 715 MB)
```

所有论文均写入 1 次，无重复采样，无 train/val 分割（合并后再统一抽取验证集）。

---

## 数据规模汇总

| 维度 | R1 | R2 | 合并 |
|------|----|----|------|
| 原始采集 | ~1,040,000 | 791,793 | — |
| 全文论文 | 91,889 | 53,705 | **145,594** |
| 摘要论文 | 81,248 | 352,114 | **433,362** |
| **总唯一论文** | **173,137** | **405,819** | **578,956** |
| **磁盘大小** | ~3.4 GB | ~2.4 GB | **~5.8 GB** |

### SCImago 期刊分层（R2）

基于 SCImago Journal Rank 2024（Food Science, category 1106），75 个期刊映射到 Q1/Q2/Q3 层级。Tier 信息通过 Venue 字段隐式保留，可按需筛选（如 SFT 仅用 Q1 数据）。

| Quartile | 期刊数 | R2 论文数 |
|----------|--------|-----------|
| Q1 | 47 | 322,081 |
| Q2 | 26 | 81,281 |
| Q3 | 2 | 2,457 |

---

## 训练数据格式

每行一个 JSON 对象：

```json
{"text": "Title: Polyphenol-protein interactions in food matrices\nAuthors: Zhang Y; Li X; Wang H\nYear: 2024\nVenue: Food Chemistry\nKeywords: polyphenols;proteins;binding\n\nAbstract:\nThis study investigated...\n\nFull Text:\nIntroduction\nPolyphenols are..."}
```

| 指标 | 全文论文 | 摘要论文 |
|------|----------|----------|
| 平均字符数 | ~35,500 | ~1,700 |
| 平均词数 | ~5,400 | ~243 |

---

## 运行命令

```powershell
conda activate foodmole

# ======== Round 1 ========
python src/fetch_openalex_concepts.py      # 采集
python src/clean_data.py                   # 清洗
python src/fetch_fulltext_s2.py --phase 1  # DOI→Corpus ID
python src/fetch_fulltext_s2.py --phase 2  # peS2o 全文
python src/merge_fulltext.py               # 合并
python src/filter_food.py                  # 过滤
python src/format_training.py              # 格式化

# ======== Round 2 ========
python src/fetch_openalex_r2.py            # 期刊定向采集
python src/clean_data_r2.py                # 清洗
python src/fetch_fulltext_s2_r2.py --phase 1  # DOI→Corpus ID
python src/fetch_fulltext_s2_r2.py --phase 2  # peS2o 全文
python src/merge_fulltext_r2.py            # 合并
python src/filter_food_r2.py               # 过滤（兜底）
python src/clean_text_quality.py           # 文本质量清洗
python src/format_training_r2.py           # 格式化
python src/format_training_r2.py --merge   # R1+R2 合并
```

## 依赖

```
pandas
requests
python-dotenv
zstandard
huggingface_hub
```

## 注意事项

- 最终训练数据约 **5.8 GB**，完整复现流程（含 peS2o 下载等中间数据）需 **30+ GB** 磁盘空间
- Phase 2 下载 peS2o 需稳定网络连接，共 136 个文件（~700 MB/文件）
- Semantic Scholar API Key 需在 `.env` 中配置：`S2_API_KEY=xxx`
- 所有处理脚本均为流式处理（O(1) 内存），不会导致内存溢出
- R1 数据存在 ~25% 非食品论文噪声（来自多学科期刊），R2 期刊定向数据纯净度 >99%
- 本目录下的 `fulltext.jsonl` 和 `abstract.jsonl` 即为最终输出，可直接用于下游合并与训练
