# FoodmoleGPT — 维基百科食品及邻近领域语料

## 数据概览

| 指标 | 值 |
|------|------|
| **来源** | 英文维基百科（2023-11-01 快照，HuggingFace 预处理版） |
| **数据集** | `wikimedia/wikipedia`，配置 `20231101.en` |
| **筛选策略** | 标题关键词匹配 + 正文开头关键词匹配 |
| **目标 tokens** | ~600–800M |
| **输出格式** | `{"text": "Title: ...\nSource: Wikipedia\n\n..."}` |
| **用途** | 教材/百科风格知识语料，用于食品领域 CPT |

---

## 领域覆盖

筛选覆盖 **食品科学核心 + 邻近学科**：

| 领域 | 示例 |
|------|------|
| 食品科学 | 食品安全、食品化学、食品加工、食品技术 |
| 营养学 | 维生素、矿物质、膳食补充剂、宏量/微量营养素 |
| 农业 | 作物学、园艺、水产养殖、畜牧业 |
| 食品微生物学 | 发酵、益生菌、食源性病原体 |
| 生物化学交叉 | 酶、蛋白质、脂质、碳水化合物、氨基酸 |
| 食品品类 | 乳制品、肉类、海鲜、谷物、果蔬、香料、饮料 |
| 烹饪与菜系 | 烹饪技法、各地菜系 |

---

## 复现步骤

### 环境准备

```bash
conda activate nus_study
pip install datasets mwparserfromhell tqdm
```

### 运行

```bash
cd /Users/cody/Workspace/FoodmoleGPT/CPT_dataset/book

# 默认目标 ~800M tokens
python download_wiki_food.py

# 或指定目标 token 数
python download_wiki_food.py --max-tokens 600000000
```

### 输出文件

```
book/
├── README_BOOK_EN.md
├── README_BOOK_ZH.md
├── download_wiki_food.py
└── data/
    ├── wiki_food_raw.jsonl       # 原始筛选结果（含匹配方式元数据）
    ├── wiki_food_cpt.jsonl       # CPT 训练格式（可直接用于训练）
    └── filter_stats.json         # 筛选统计
```

---

## 筛选机制

1. **标题匹配**（高精度）：标题包含 ~120 个食品相关关键词（如 food、nutrition、dairy、fermentation、agriculture 等）
2. **正文匹配**（兜底）：文章前 500 字符包含 ~40 个领域专用短语（如 food science、dietary intake、shelf life 等）
3. **排除过滤**：标题含体育、影视、音乐等无关词的文章被排除
4. **短文过滤**：正文不足 200 字符的词条被跳过

---

## Token 估算

Token 数按 `词数 × 1.3` 估算（英文 BPE 分词器的常用近似值）。如需精确计数，请在生成后用目标模型的 tokenizer 重新统计。
