[English](DATA_README_EN.md) | **中文**

---

# FoodmoleGPT — PMC 食品科学语料数据文档

## 1. 数据概览

| 指标 | 数值 |
|------|------|
| 文章总数 | **105,159 篇**（有效） + 1,503 篇（跳过） |
| 原始 XML | 106,662 个文件，约 15 GB |
| JSONL 训练数据 | 3.7 GB |
| TXT 训练数据 | 3.5 GB |
| 总字符数 | 37.8 亿字符 |
| 预估 Token 数 | **~9.46 亿 tokens** |
| 平均每篇 | ~35,967 字符 |
| 语言 | 英文为主 |
| 数据采集日期 | 2026 年 2 月 10 日 |

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

### 3.3 筛选结果

- 扫描总量：**7,583,353** 篇 PMC 开放获取文章
- 匹配文章：**106,659** 篇（命中率 1.4%）
- 有效文章：**105,159** 篇（经预处理后，排除正文过短的文章）

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
food_science_corpus.jsonl + food_science_corpus.txt
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

## 6. 输出文件说明

### 6.1 `food_science_corpus.jsonl`（3.7 GB）

每行一个 JSON 对象，包含以下字段：

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

**适用场景**：Supervised Fine-tuning (SFT)、RAG 检索增强生成

### 6.2 `food_science_corpus.txt`（3.5 GB）

纯文本格式，文章之间用 `========================================` 分隔。

**适用场景**：Continual Pre-training（持续预训练）、Domain-adaptive Pre-training

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
├── pmc_downloader_xml.py             # 下载脚本（多线程+断点续传）
├── preprocess_xml.py                 # 预处理脚本（XML → JSONL/TXT）
├── requirements.txt                  # Python 依赖
├── DATA_README.md                    # 本文档
└── data/
    ├── xml/                          # 原始 XML 文件 (106,662 篇, ~15 GB)
    │   ├── PMC10000368.xml
    │   ├── PMC10000371.xml
    │   └── ...
    ├── processed/                    # 预处理后的训练数据
    │   ├── food_science_corpus.jsonl  # JSONL 格式 (3.7 GB)
    │   ├── food_science_corpus.txt    # TXT 格式 (3.5 GB)
    │   └── corpus_stats.json          # 语料统计
    ├── food_articles_xml.json         # 筛选出的文章 ID 列表
    ├── download_xml_progress.json     # 下载进度记录
    └── logs/
        └── download_xml.log           # 下载日志
```

---

## 9. 复现方法

```bash
# 1. 安装依赖
conda activate foodmole
pip install -r requirements.txt

# 2. 下载 oa_file_list.csv（需从 NCBI FTP 获取）
wget https://ftp.ncbi.nlm.nih.gov/pub/pmc/oa_file_list.csv

# 3. 配置 config.py（设置邮箱和 API Key）

# 4. 下载 XML
python pmc_downloader_xml.py

# 5. 预处理
python preprocess_xml.py
```
