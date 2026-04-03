# FoodmoleGPT CPT 语料 — 最终合并数据集

## 数据概览

| 指标 | 值 |
|------|------|
| **输出文件** | `total/cpt_corpus_merged.jsonl` |
| **文档总数** | 1,717,582 |
| **预估 tokens** | ~31 亿（tiktoken cl100k_base 抽样估算） |
| **领域 / 通用 比例** | 75.0% / 25.0% |
| **数据格式** | `{"text": "...", "source": "<tag>"}` |
| **随机种子** | 42 |

本文件是 FoodmoleGPT 项目的最终 CPT（持续预训练）语料，可直接加载到 LLaMA-Factory 进行训练。所有记录已打乱顺序，并附带 `source` 字段标注数据来源。

---

## 数据来源

### 1. 食品科学全文论文 (`essay_fulltext`)

| 指标 | 值 |
|------|------|
| 文档数 | 253,569 |
| 预估 tokens | ~21.9 亿（70.0%） |
| 源文件 | `essay/Merged/combined_fulltext_deduped.jsonl` |

- **来源**：PubMed Central (PMC) Open Access 全文论文，通过食品科学 MeSH 主题词和关键词扩展检索。
- **流水线**：XML 下载 → 文本提取 → 质量过滤 → MinHash 近似去重（跨 PubMed 和 OpenAlex 源）。
- **详情**：见 `essay/Merged/README_Total.md`。

### 2. 论文摘要 (`essay_abstract`)

| 指标 | 值 |
|------|------|
| 文档数 | 433,362 |
| 预估 tokens | ~1.80 亿（5.8%） |
| 源文件 | `essay/OpenAlex/abstract.jsonl` |

- **来源**：OpenAlex API — 食品科学相关论文摘要。
- **格式**：每条记录为 `{"text": "Title: <标题>\n\n<摘要>"}`。
- **重叠**：仅 16 个 DOI 与全文集重叠，两者基本独立。

### 3. 维基百科食品文章 (`wiki_food`)

| 指标 | 值 |
|------|------|
| 文档数 | 24,479 |
| 预估 tokens | ~0.19 亿（0.6%） |
| 源文件 | `book/data/wiki_food_cpt.jsonl` |

- **来源**：HuggingFace Datasets 提供的 `wikimedia/wikipedia` 20231101.en 快照（流式加载）。
- **过滤**：三级关键词系统 + 正则词边界匹配（`\b`）：
  - **Tier 1（安全）**：无歧义多词短语（如 "food science", "cuisine"） → 标题匹配即可。
  - **Tier 2（歧义）**：高歧义短词（如 "oil", "fish", "tea"） → 标题匹配后须正文前 500 字含食品相关确认词。
  - **Tier 3（仅正文）**：标题无关键词但正文含食品特定短语（如 "edible", "food source", "used in cooking"）。
- 排除规则过滤体育、娱乐、政治、军事、基础设施和人物传记类条目。
- **流水线**：`book/download_wiki_food.py` → `wiki_food_cpt.jsonl`（纯文本 CPT 格式）。
- **详情**：见 `book/README_BOOK_ZH.md`。

### 4. FineWeb 通用语料 (`fineweb_general`)

| 指标 | 值 |
|------|------|
| 文档数 | 1,006,172 |
| 预估 tokens | ~7.37 亿（23.6%） |
| 源文件 | `general/data/fineweb2_general_cpt.jsonl` |

- **来源**：`HuggingFaceFW/fineweb` — 高质量、经清洗的英文网络语料（总量 15T+ tokens）。
- **采样**：系统采样（每 50 篇取 1 篇），长度过滤 500–50,000 字符。原始采样约 8 亿 tokens；合并时截断至总量的 25%。
- **用途**：通用领域"回放"数据，防止 CPT 阶段灾难性遗忘。
- **详情**：见 `general/README_GENERAL_ZH.md`。

---

## 组成概览

```
来源                    文档数        Tokens       占比
────────────────────────────────────────────────────────────
essay_fulltext            253,569   ~2,190M       70.0%
essay_abstract            433,362     ~180M        5.8%
wiki_food                  24,479      ~19M        0.6%
fineweb_general         1,006,172     ~737M       23.6%
────────────────────────────────────────────────────────────
合计                    1,717,582   ~3,126M      100.0%
```

领域来源（食品科学论文 + 摘要 + 维基百科）占语料总量的 75%；FineWeb 通用回放语料占 25%。

---

## 合并策略

1. **完整加载领域来源** — 三个领域来源全量纳入，不做采样或截断。
2. **计算通用语料预算** — 按目标比例计算通用语料的 token 预算：
   ```
   通用预算 = 领域 tokens × ratio / (1 − ratio)
            = 23.89 亿 × 0.25 / 0.75
            ≈ 7.96 亿 tokens（word_count×1.3 预算；tiktoken 实测 ≈ 7.37 亿）
   ```
3. **截断通用来源** — 顺序读取 FineWeb JSONL，达到预算时停止。
4. **标注所有记录** — 为每条文档添加 `"source"` 字段，便于下游分析。
5. **打乱顺序** — 以 seed=42 随机打乱所有记录，避免训练时的顺序偏差。
6. **写入输出** — 输出为单个 JSONL 文件 `total/cpt_corpus_merged.jsonl`。

合并脚本：`merge_all_cpt.py`

---

## Token 估算

Token 数量采用 **tiktoken cl100k_base** 分词器进行分层抽样估算（全局 500 条 + 每源 300 条随机样本，seed=42）。全局估算（~30.9 亿）与按源汇总（~31.3 亿）仅差 1.3%。合并脚本内部使用 `词数 × 1.3` 启发式方法计算通用语料预算；tiktoken 实测 token 数约高出 16%。

---

## 输出格式

`cpt_corpus_merged.jsonl` 每行为一个 JSON 对象：

```json
{"text": "完整文档文本...", "source": "essay_fulltext"}
```

`source` 字段取值为以下四种之一：
- `essay_fulltext` — 食品科学全文论文
- `essay_abstract` — 论文摘要
- `wiki_food` — 维基百科食品文章
- `fineweb_general` — FineWeb 通用网络语料

---

## 目录结构

```
CPT_dataset/
├── essay/
│   ├── Merged/
│   │   ├── combined_fulltext_deduped.jsonl    # 去重后全文论文
│   │   └── README_Total.md
│   ├── OpenAlex/
│   │   ├── abstract.jsonl                      # 论文摘要
│   │   └── fulltext.jsonl                      # OpenAlex 全文（已合并至 Merged/）
│   └── PubMed/
│       └── ...                                 # PubMed 流水线脚本与数据
├── book/
│   ├── download_wiki_food.py                   # 维基百科抽取脚本
│   ├── README_BOOK_EN.md
│   ├── README_BOOK_ZH.md
│   └── data/
│       ├── wiki_food_cpt.jsonl                 # 维基百科食品文章（训练格式）
│       └── filter_stats.json
├── general/
│   ├── download_fineweb2.py                    # FineWeb 采样脚本
│   ├── README_GENERAL_EN.md
│   ├── README_GENERAL_ZH.md
│   └── data/
│       ├── fineweb2_general_cpt.jsonl          # FineWeb 通用语料
│       └── sample_stats.json
├── merge_all_cpt.py                            # 最终合并脚本
└── total/
    ├── cpt_corpus_merged.jsonl                 # ← 最终输出（~13 GB）
    ├── merge_all_stats.json                    # 合并统计
    ├── README_TOTAL_EN.md                      # 英文说明
    └── README_TOTAL_ZH.md                      # 本文件
```

---

## 复现步骤

所有脚本具有确定性，可完整复现：

```bash
# 第一步：下载维基百科食品文章（约 15 分钟）
cd CPT_dataset/book
python download_wiki_food.py

# 第二步：采样 FineWeb 通用语料（约 2.3 小时）
cd CPT_dataset/general
python download_fineweb2.py

# 第三步：合并所有来源（约 7 分钟）
cd CPT_dataset
python merge_all_cpt.py --general-ratio 0.25 --seed 42
```

环境依赖：Python 3.10+、`datasets`、`tqdm`、`mwparserfromhell`。

---

## 统计文件

`merge_all_stats.json` 包含：
- 各来源的文档数和 token 估计
- 实际通用语料比例
- 随机种子和运行耗时
- 所有来源和输出的文件路径
