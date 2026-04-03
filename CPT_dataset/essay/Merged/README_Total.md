# FoodmoleGPT — 合并全文训练语料

## 数据概览

| 指标 | 值 |
|------|------|
| **最终论文数** | **247,441 篇**（全文）|
| **来源** | OpenAlex/peS2o 全文 135,473 篇 + PubMed/PMC 独有全文 112,080 篇 − 112 篇近重复 |
| **JSONL 文件** | `combined_fulltext_deduped.jsonl`（8.7 GB）|
| **格式** | `{"text": "Title: ...\nAuthors: ...\n..."}` |
| **语言** | 英文为主（PubMed 侧含 0.08% 中文） |
| **数据日期** | 2026 年 3 月 26 日 |

---

## 数据来源

| 来源 | 篇数 | 说明 |
|------|------|------|
| OpenAlex / peS2o 全文 | 135,473 | 食品科学领域全文，基于 OpenAlex API（含 DOI） |
| PubMed / PMC 全文 | 167,244 | PMC Open Access 全文（R1 + R2 扩展 + R3 清洗后） |
| PubMed 独有（去重后） | 112,080 | 剔除与 OpenAlex 重叠后保留 |

---

## 处理流程

```
OpenAlex 全文 (135,473 篇)     PubMed/PMC 全文 (167,244 篇)
  (JSONL 内嵌 DOI)                     │
        │                    ┌─────────┴──────────┐
        │                    │ PMC-ids.csv.gz       │
        │                    │ PMCID → DOI 映射      │
        │                    └─────────┬──────────┘
        │                              │
        ├──────── DOI 去重 ────────────┤  → 去除 55,155 篇
        ├──────── 标题去重 ────────────┤  → 去除 9 篇
        │                              │
        │                     PubMed 独有 112,080 篇
        │                              │
        └──────────┬───────────────────┘
                   │ 合并
                   ▼
         combined_fulltext.jsonl (247,553 篇)
                   │
                   ▼ MinHash LSH 文本级去重
                   │  (Jaccard > 0.8, 5-gram, 128 perms)
                   │  → 去除 112 篇近重复
                   ▼
      combined_fulltext_deduped.jsonl (247,441 篇) ✅
```

---

## 去重详情

### 阶段一：元数据级去重（DOI + 标题）

通过 NCBI 官方 `PMC-ids.csv.gz`（1,068 万条 PMCID↔DOI 映射）为 PubMed 记录批量补上 DOI，
再与 OpenAlex JSONL 内嵌的 135,473 个 DOI 和标题做精确匹配去重。

| 指标 | 值 |
|------|------|
| PubMed DOI 匹配率 | 99.6%（166,573 / 167,244）|
| DOI 重复 | 55,155 篇 |
| 标题重复（兜底） | 9 篇 |
| PubMed 独有保留 | 112,080 篇 |

### 阶段二：MinHash LSH 文本级去重

对合并后的 253,611 篇全文用 MinHash + 局部敏感哈希做近重复检测。

| 配置 | 值 |
|------|------|
| MinHash 哈希函数数 | 128 |
| Jaccard 相似度阈值 | 0.8 |
| Shingling 方式 | 5-gram（词级别）|

| 结果 | 值 |
|------|------|
| 近重复聚类 | 104 个（100 个二元组 + 2 个三元组 + 1 个四元组 + 1 个六元组）|
| 移除文档 | 112 篇（0.045%）|
| 最终保留 | **247,441 篇** |
| 耗时 | 约 59 分钟 |

---

## 文件说明

```
Merged/
├── README_Total.md                     # 本文件
├── combined_fulltext_deduped.jsonl     # ✅ 最终训练语料（247,441 篇，8.7 GB）
├── combined_fulltext.jsonl             # 中间文件：合并后去重前（247,553 篇，8.7 GB）
├── pubmed_unique_fulltext.jsonl        # PubMed 独有全文（112,080 篇，3.9 GB）
├── near_duplicates.jsonl               # 34 个近重复聚类详情
├── merge_stats.json                    # 元数据合并统计
└── dedup_stats.json                    # 文本去重统计
```

### JSONL 格式

`combined_fulltext_deduped.jsonl` 中每行一条记录：

```json
{"text": "Title: ...\nAuthors: ...\nYear: ...\nVenue: ...\nKeywords: ...\n\nAbstract:\n...\n\nFull Text:\n..."}
```

> **注意**：OpenAlex 来源的记录包含 Authors / Year / Venue 字段；PubMed 来源的记录包含 Abstract / Keywords 及各正文章节（Introduction、Methods、Results 等）。两者格式略有差异，但均为纯文本 CPT 格式，可直接用于继续预训练。

---

## 复现步骤

```bash
conda activate nus_study

# 前置条件：PMC-ids.csv.gz 已存在于 PubMed/data/
# 若不存在：
# curl -L -o PubMed/data/PMC-ids.csv.gz https://ftp.ncbi.nlm.nih.gov/pub/pmc/PMC-ids.csv.gz

# 1. 元数据合并 + 去重（约 2 分钟）
python3 merge_pubmed_openalex.py

# 2. MinHash LSH 文本级去重（约 94 分钟）
python3 minhash_dedup.py

# 3.（可选）清理中间文件
# rm Merged/combined_fulltext.jsonl
```

> **脚本位置**：`merge_pubmed_openalex.py` 和 `minhash_dedup.py` 均在 `essay/` 目录下（与 OpenAlex、PubMed、Merged 同级）。

---

## 依赖

```
datasketch    # MinHash LSH
```
