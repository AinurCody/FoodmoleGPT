[English](DATA_README_EN.md) | **中文**

---

# FoodmoleGPT — PMC 食品科学语料数据文档

## 1. 数据概览

| 指标 | 数值 |
|------|------|
| **第一轮** — 初筛有效文章 | **105,159 篇**（有效） + 1,503 篇（跳过） |
| **第一轮** — 二次筛查后保留 | **93,657 篇** |
| **第二轮（扩充）** — 新增有效文章 | **81,401 篇**（有效） + 1,224 篇（跳过） |
| **第二轮（扩充）** — 筛查后保留 | **77,103 篇** |
| **合并总数**（清洗前） | **170,760 篇** |
| **第三轮（质量清洗）** — 剔除 | 3,516 篇（骸科期刊 661 + 文本 <1K 173 + 无食品锚点 2,682） |
| **最终总数** | **167,244 篇** |
| 原始 XML（两轮合计） | 106,662 + 82,625 = **189,287** 个文件，约 26 GB |
| 最终 JSONL 训练数据 | **6.51 GB** (`food_science_corpus.keep.jsonl`) |
| 最终预估 Token 数 | **~16 亿 tokens** |
| 最终平均每篇 | ~36,800 字符 |
| 语言 | 99.92% 英文，0.08% 中文 |
| 第一轮采集日期 | 2026 年 2 月 10 日 |
| 第二轮扩充日期 | 2026 年 3 月 5 日 |
| 第三轮清洗日期 | 2026 年 3 月 5 日 |

---

## 2. 数据来源

### 2.1 来源数据库

**PubMed Central (PMC)** — 美国国立卫生研究院 (NIH) 旗下的生命科学全文文献数据库。

- 官网：https://www.ncbi.nlm.nih.gov/pmc/
- 数据子集：**PMC Open Access Subset**（开放获取子集）
- 许可：文章均为开放获取，允许文本挖掘和学术研究使用
- 来源文件列表：`oa_file_list.csv`（从 NCBI FTP 下载的全部开放获取文章索引）

### 2.2 API 接口

使用 NCBI **Entrez E-utilities API** 获取文章全文 XML：
- 接口：`Entrez.efetch(db="pmc", rettype="xml")`
- 认证：使用 NCBI API Key（10 requests/second）
- 工具标识：`FoodmoleGPT-Downloader`

---

## 3. 筛选方法

### 3.1 筛选策略

采用 **关键词匹配** 方法，对 `oa_file_list.csv` 中每篇文章的 `Article Citation`（文章引用信息，包含标题和期刊名）进行大小写不敏感的关键词匹配。

### 3.2 筛选关键词（共 6 类）

```
Core Food Science:
  food, nutrition, diet, dietary, nutrient

Food Categories:
  dairy, meat, beef, pork, poultry, chicken, seafood, fish,
  vegetable, fruit, cereal, grain, beverage, milk, cheese,
  yogurt, bread, rice

Food Science Topics:
  ferment, flavor, flavour, sensory, taste, cooking, culinary, recipe

Food Safety & Quality:
  foodborne, food safety, food contamination, preserv, shelf life, spoilage

Food Processing & Agriculture:
  food processing, food technology, food packaging, agricult, crop,
  harvest, livestock

Specific Compounds & Journals:
  antioxidant, phenolic, polyphenol, vitamin, fatty acid, protein,
  carbohydrate, fiber, fibre, j food, food res, food chem, food sci,
  meat sci, dairy sci, cereal, appetite, nutrients, foods, beverages
```

### 3.3 初筛结果（关键词匹配）

- 扫描总量：**7,583,353** 篇 PMC 开放获取文章
- 匹配文章：**106,659** 篇（命中率 1.4%）
- 有效文章：**105,159** 篇（经预处理后，排除正文过短的文章）

### 3.4 二次筛查结果（主题去噪）

为减少“医学强相关但食品弱相关”样本，增加二次筛查规则：

- 触发癌症词：`cancer/tumor/oncology/neoplasm/carcinoma/malignant`
- 食品锚点检测范围：标题 + 摘要 + 关键词
- 剔除规则：命中癌症词且无食品锚点 -> 剔除

结果：

- 二次筛查输入：**105,159** 篇
- 保留：**93,657** 篇
- 剔除：**11,502** 篇（占全量 10.94%）
- 最终默认训练集路径：`data/processed/filtered/food_science_corpus.keep.jsonl`

---

## 4. 下载方法

### 4.1 下载流程

```
oa_file_list.csv（NCBI FTP）
    │
    ▼ 关键词匹配筛选
106,659 篇食品科学文章 ID
    │
    ▼ Entrez efetch API（XML 格式）
106,662 个 XML 文件（15 GB）
```

### 4.2 技术细节

| 配置项 | 值 |
|--------|-----|
| 下载工具 | `pmc_downloader_xml.py`（Python + Biopython） |
| 并发方式 | ThreadPoolExecutor（8 线程） |
| 速率限制 | 9 requests/second（NCBI 限制 10 req/s） |
| 重试机制 | 每篇最多 3 次重试 |
| 断点续传 | ✅ 支持（基于进度文件 + 磁盘文件检测） |
| 下载失败数 | **0 篇** |

### 4.3 下载格式

下载的是 **JATS XML**（Journal Article Tag Suite）格式，这是 PMC 的标准结构化全文格式，包含：

- 文章元数据（标题、作者、期刊、DOI）
- 结构化摘要
- 正文章节（Introduction, Methods, Results, Discussion, Conclusion）
- 图表 caption（图注和表注）
- 关键词
- 参考文献

> **注意**：XML 中仅包含文本内容和图片引用路径，不含图片二进制数据。

---

## 5. 预处理方法

### 5.1 预处理流程

```
106,662 个 XML 文件
    │
    ▼ preprocess_xml.py（多进程解析）
    │
    ├─▶ 提取内容：标题、摘要、关键词、正文、图表 caption
    ├─▶ 文本清洗：去除引用标记[1][2]、修复空格、去除无效字符
    ├─▶ 过滤：跳过正文 < 500 字符的文章（1,503 篇）
    └─▶ 跳过无关章节：致谢、利益冲突声明、作者贡献、伦理声明等
    │
    ▼
data/processed/intermediate/food_science_corpus.raw.jsonl（中间产物）
    │
    ▼ post_filter_corpus.py（二次筛查）
    │
    ├─▶ 保留：food_science_corpus.keep.jsonl
    ├─▶ 剔除：food_science_corpus.drop.jsonl
    └─▶ 统计：post_filter_stats.json + post_filter_samples.json
```

### 5.2 跳过的章节类型

以下章节被判定为与领域知识无关，在提取时被过滤：

```
competing interests, conflict of interest, conflicts of interest,
credit authorship contribution statement, author contributions,
funding, acknowledgements, acknowledgments,
data availability, supplementary material, supplementary data,
abbreviations, ethics statement, ethical approval
```

### 5.3 提取的内容

每篇文章提取以下信息：

```
Title: [文章标题]

Abstract: [摘要全文]

Keywords: [关键词列表]

Introduction
[引言正文...]

Materials and Methods
[方法正文...]

Results and Discussion
[结果讨论正文...]

Conclusion
[结论正文...]

Figure Descriptions:
  Figure 1: [图注描述，通常包含实验结果的定量总结]
  Figure 2: [...]

Table Descriptions:
  Table 1: [表注描述]
```

### 5.4 处理性能

| 指标 | 值 |
|------|-----|
| 处理工具 | `preprocess_xml.py`（Python multiprocessing） |
| 并行进程数 | 9（CPU 核心数 - 1） |
| 处理速度 | ~1,195 篇/秒 |
| 总处理时间 | **1 分 29 秒** |

---

## 6. 输出文件说明（筛后版本）

### 6.1 `data/processed/filtered/food_science_corpus.keep.jsonl`（3.3 GB）

最终可直接用于训练/检索的语料文件，每行一个 JSON 对象，字段如下：

```json
{
  "pmcid": "PMC10000368",
  "title": "Gas Chromatography...",
  "abstract": "Patients with galactosemia...",
  "keywords": ["galactosemia", "galactose content", ...],
  "journal": "Journal of Food Composition and Analysis",
  "text": "Title: Gas Chromatography...\n\nAbstract: ...\n\nIntroduction\n..."
}
```

**适用场景**：SFT、RAG、领域继续预训练

### 6.2 `data/processed/filtered/food_science_corpus.drop.jsonl`（449 MB）

二次筛查剔除集合（用于审计/复核），规则为“癌症相关且无食品锚点”。

### 6.3 `data/processed/filtered/post_filter_stats.json`

二次筛查统计结果（保留/剔除计数、比例、分桶统计）。

### 6.4 `data/processed/filtered/post_filter_samples.json`

三类样本抽检集（每类 reservoir sampling），用于人工质量复核。

---

## 7. 数据质量抽样

随机抽取 3 篇文章的质量检查结果：

| 序号 | PMCID | 标题 | 文本长度 |
|------|-------|------|---------|
| 1 | PMC10201332 | COVID-19 mobility restrictions... associated with higher retail food prices | 51,832 chars |
| 2 | PMC10935437 | Reply to Curtis, L. Comment on "Magner et al. Sulforaphane Treatment..." | 3,373 chars |
| 3 | PMC8614712 | Polyphenols from Blumea laciniata Extended the Lifespan... | 31,191 chars |

---

## 8. 文件结构

```
PubMed/
├── config.py                         # NCBI API 配置
├── pmc_downloader_xml.py             # 第一轮下载（关键词匹配 oa_file_list.csv）
├── pmc_esearch_collector.py          # 第二轮 PMCID 收集器（10 条 MeSH 策略）
├── pmc_expansion_downloader.py       # 第二轮 XML 下载器
├── merge_expansion.py                # 合并扩充数据到主语料
├── preprocess_xml.py                 # 预处理脚本（XML → JSONL）
├── post_filter_corpus.py             # 二次筛查脚本（主题去噪）
├── food_relevance_filter.py          # 第三轮精准食品相关性过滤器（225 个锚点词）
├── PMC_Search_Guide.md               # 导师提供的 MeSH 检索策略
├── requirements.txt                  # Python 依赖
├── DATA_README_EN.md                 # 本文档（英文）
├── DATA_README_ZH.md                 # 本文档（中文）
└── data/
    ├── xml/                          # 第一轮原始 XML（106,662 篇，约 15 GB）
    ├── xml_expansion/                # 第二轮原始 XML（82,625 篇，约 11 GB）
    ├── expansion_pmcids.json         # 第二轮收集的 PMCID（82,632 个）
    ├── processed/
    │   ├── intermediate/             # 第一轮预处理中间产物
    │   ├── filtered/                 # 最终清洗训练数据
    │   │   ├── food_science_corpus.keep.jsonl  # 主训练集（6.51 GB，167,244 篇）
    │   │   ├── food_science_corpus.drop.jsonl  # 剔除集
    │   │   ├── precision_filter_flagged.jsonl  # 第三轮剔除记录
    │   │   ├── merge_expansion_stats.json      # 合并统计
    │   │   └── post_filter_stats.json          # 筛查统计
    │   └── expansion/                # 第二轮预处理产物
    │       ├── intermediate/
    │       └── filtered/
    ├── food_articles_xml.json         # 第一轮筛选出的文章 ID
    ├── download_xml_progress.json     # 第一轮下载进度
    ├── expansion_download_progress.json  # 第二轮下载进度
    └── logs/
```

---

## 9. 复现方法

### 第一轮（关键词匹配）

```bash
conda activate foodmole
pip install -r requirements.txt

# 1. 下载 oa_file_list.csv
wget https://ftp.ncbi.nlm.nih.gov/pub/pmc/oa_file_list.csv

# 2. 配置 config.py（设置邮箱和 API Key）

# 3. 下载 XML
python pmc_downloader_xml.py

# 4. 预处理
python preprocess_xml.py

# 5. 二次筛查
python post_filter_corpus.py \
  --input data/processed/intermediate/food_science_corpus.raw.jsonl \
  --out-dir data/processed/filtered
```

### 第二轮（MeSH 策略扩充）

```bash
# 1. 通过 10 条 MeSH 检索策略收集新 PMCID
python pmc_esearch_collector.py          # 输出 data/expansion_pmcids.json

# 2. 下载扩充 XML
python pmc_expansion_downloader.py       # 输出到 data/xml_expansion/

# 3. 预处理扩充数据
python preprocess_xml.py -i data/xml_expansion -o data/processed/expansion -f jsonl

# 4. 二次筛查扩充数据
python post_filter_corpus.py \
  --input data/processed/expansion/intermediate/food_science_corpus.raw.jsonl \
  --out-dir data/processed/expansion/filtered

# 5. 合并到主语料
python merge_expansion.py
```

### 第三轮（质量清洗）

```bash
# 精准食品相关性过滤（剔除无关文章）
python food_relevance_filter.py --execute
```

默认读取路径（训练/RAG）：

`data/processed/filtered/food_science_corpus.keep.jsonl`

---

## 10. 第二轮扩充详情（2026 年 3 月 5 日）

### 10.1 检索策略

使用 **NCBI E-utilities `esearch`** 配合导师提供的 10 条 MeSH 策略（详见 `PMC_Search_Guide.md`），替代第一轮的 `oa_file_list.csv` 关键词匹配。每条策略均以 `AND open access[Filter]` 限制为 OA 文章。

### 10.2 各策略检索结果

| # | 策略 | 命中总数 | 新增唯一 |
|---|------|---------|----------|
| 1 | 食品化学 | 26,913 | 20,833 |
| 2 | 食品安全与毒理学 | 16,709 | 14,116 |
| 3 | 食品营养与健康 | 35,611 | 25,624 |
| 4 | 食品风味与感官科学 | 7,007 | 4,605 |
| 5 | 食品加工与工程 | 7,526 | 4,940 |
| 6 | 食品微生物与生物技术 | 19,188 | 5,554 |
| 7 | 食品信息学与 AI | 2,841 | 2,019 |
| 8 | 食品教育与公众参与 | 358 | 260 |
| 9 | 可持续食品体系 | 5,361 | 4,139 |
| 10 | 替代蛋白与未来食品 | 1,149 | 542 |
| | **总计（跨策略去重后）** | | **82,632** |

### 10.3 处理结果

| 步骤 | 数量 |
|------|------|
| 收集新 PMCID | 82,632 |
| 已下载 XML | 82,625 (99.99%) |
| 预处理后有效 | 81,401（跳过 1,224 篇过短/无效） |
| 主题筛查后保留 | 77,103（剔除 4,298 = 5.28%） |
| 与第一轮重复 | 0 |
| **新增至主语料** | **77,103** |

---

## 11. 第三轮质量验证与清洗（2026 年 3 月 5 日）

### 11.1 质量验证

对合并后的 170,760 篇语料进行了全面质量分析：

**期刊分布**：3,737 个唯一期刊。Top 5 均为食品科学期刊（Nutrients 19.85%、Foods 13.54%、Antioxidants 4.74%）。发现 **J Hip Preservation Surgery**（661 篇）为系统性泄漏 — 纯骨科期刊，可能由“hip”匹配“rosehip”（玫瑰果）导致。

**文本长度分布**：中位数 34,273 字符，81.78% 在 10K–50K 范围内。仅 0.10% 文章 < 1K 字符（可能为社论/短信），0.04% > 200K 字符。

**关键词频率**：高频关键词均与食品相关（polyphenols、nutrition、probiotics、gut microbiota）。少量医学关键词（cancer 0.56%、cardiovascular 0.53%）多处于食品–健康交叉研究中。

**语言分布**：99.92% 英文，0.08% 中文（132 篇）。

### 11.2 清洗步骤

| 步骤 | 剔除 | 剩余 |
|------|------|------|
| 起始（合并语料） | — | 170,760 |
| 剔除 J Hip Preservation Surgery | 661 | 170,099 |
| 剔除文本 < 1K 字符 | 173 | 169,926 |
| 精准食品相关性过滤（225 个锚点词） | 2,682 | **167,244** |

### 11.3 精准食品相关性过滤器

脚本：`food_relevance_filter.py`

检查每篇文章的 **标题 + 摘要 + 关键词** 是否包含食品相关锚点词（225 个正则模式）。无食品锚点且期刊名也无食品相关性的文章被标记剔除。

锚点词类别包括：
- 核心食品词汇（food、diet、nutrition、meal、eating）
- 膳食干预（supplement、intake、consumption、bioavailability、calorie）
- 食品类别（dairy、meat、seafood、fruit、vegetable、beverage 等）
- 食品科学主题（fermentation、flavor、shelf life、food safety）
- 农业（crop、farming、livestock、aquaculture）
- 食品化合物（antioxidant、polyphenol、vitamin、fatty acid、probiotic）
- 广义营养（obesity、BMI、gut microbiota、glycemic、satiety、anemia）

被剔除文章主要来自：Nutrients (305)、Protein & Cell (260)、Scientific Reports (197)、Particle & Fibre Toxicology (124)。

### 11.4 最终语料

| 指标 | 数值 |
|------|------|
| **总计文章** | **167,244** |
| 语料大小 | 6.51 GB |
| 预估 Token 数 | ~16 亿 |
| 语言 | 99.92% 英文 |
| 人工审查（100 篇随机抽样） | ✅ 通过 |
