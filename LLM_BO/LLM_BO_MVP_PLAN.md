# FoodmoleGPT × Bayesian Optimization — 干湿闭环 MVP 计划

> **核心命题**：证明 FoodmoleGPT 作为领域先验，能让同一个 BO 在 published food experiment benchmark 上比 base model 和 vanilla BO 更快收敛。

---

## 一、实验设计总览

### 科学问题

在固定候选池 + 固定 gold search space 的离散回溯验证（retrospective replay）中，领域微调后的 LLM（FoodmoleGPT）生成的 warm-start 初始点，是否比未微调基座（Qwen3-base）和随机初始化带来更快的 BO 收敛？

### 实验矩阵（按优先级）

| 优先级 | 方法 | LLM | Init 来源 | 说明 |
|--------|------|-----|----------|------|
| **P0** | Random Search | — | 随机选 k 个 | 下界 baseline |
| **P0** | Vanilla BO | — | 随机选 k 个 | 标准 GP-EI baseline |
| **P0** | Qwen3-base init → BO | Qwen3-8B-Base | LLM 选 k 个 | 未微调基座先验 |
| **P0** | FoodmoleGPT init → BO | Qwen3-CPT+SFT | LLM 选 k 个 | 领域微调先验 |
| P1 | Gemini Flash init → BO | Gemini Flash | LLM 选 k 个 | 通用商用 LLM（有余力再做） |

### 评估指标（按优先级）

| 优先级 | 指标 | 定义 |
|--------|------|------|
| **P0** | **Rounds to 90% of published best** | 达到 published best × 0.9 所需的迭代轮数 |
| **P0** | **Final best value at budget T** | 在固定总轮数 T 后的 best-so-far |
| **P0** | **Init quality** | 初始 k 个点的平均目标值 |
| **P0** | **Top-quartile hit rate** | LLM 选出的 k 个初始点中，落在真实前 25% 的比例 |
| P1 | Order robustness | 候选点顺序打乱 3-5 次后，模型选点的稳定性（Jaccard 相似度） |

### 关键术语约定

- ❌ 不说"找到了最优配方"
- ✅ 说 **published best** / **best observed in the published study** / **retrospective benchmark**
- ❌ 不说 regret curve（除非画的是 published_best - best_so_far）
- ✅ 说 **best-so-far curve**

---

## 二、数据集

### 主数据集

**论文**：Sahraee et al. (2022). *Application of mixture design methodology for development of high antioxidant fruity functional beverage.* Food Sci Nutr, 10(7), 2245–2254.

- **PMC**：PMC9281929（Open Access, CC BY 4.0）
- **设计**：Mixture Design，14 组配方
- **变量**：3 个连续变量
  - CE（豆蔻精油，ml/100ml）
  - GE（姜提取物，ml/100ml）
  - HS（木槿溶液，ml/100ml）
- **响应值（主目标）**：DPPH 抑制率（%），范围 76.09%–90.84%
- **响应值（辅助）**：Total Phenol, Anthocyanin, Flavonoid, Vitamin C
- **数据提取**：从论文 Table 2 手工整理

### 候选池规模

- 14 个点 → 留 k=3 做 init → 11 轮 BO 迭代
- 每组实验重复 10-20 次取均值（不同 random seed）

### 备选数据集（如需更多数据点）

- Fakhri et al. (2023). Foods, 12(17), 3265. DOI: 10.3390/foods12173265
  - 3 变量（叶黄素/薄荷/青柠），CDM 设计，更多数据点

---

## 三、技术栈

| 组件 | 选择 | 理由 |
|------|------|------|
| BO 引擎 | **BoTorch**（GPyTorch + PyTorch） | 面试分量高，GP + EI 标准实现 |
| LLM 调用 | **缓存 JSON** | FoodmoleGPT / Qwen3-base 在 Hopper 跑一次推理，结果存 JSON；不搞服务化 |
| 通用 LLM | Gemini Flash API（P1） | 已有 key，可选 |
| 数据处理 | pandas DataFrame | 候选池就是一个表 |
| 可视化 | matplotlib | best-so-far 曲线 + box plot + bar chart |
| 运行环境 | MacBook 本地 | BO 本身纯 CPU，秒级完成 |

---

## 四、核心代码架构

```
foodmole-bo/
├── data/
│   ├── candidates.csv                 # 论文实验数据（手工整理）
│   └── gold_search_space.json         # 变量范围（从论文抄）
├── llm_priors/
│   ├── generate_prior.py              # Hopper 上跑，生成 LLM 选点结果
│   ├── foodmolegpt_init.json          # FoodmoleGPT 选的 k 个初始点
│   ├── qwen3base_init.json            # Qwen3-base 选的 k 个初始点
│   └── gemini_init.json               # （P1）Gemini 选的 k 个初始点
├── bo/
│   ├── discrete_replay.py             # 离散回溯 BO 主循环
│   ├── gp_model.py                    # GP surrogate + EI acquisition
│   └── baselines.py                   # Random Search 实现
├── eval/
│   ├── metrics.py                     # 4 个指标计算
│   └── plot.py                        # best-so-far 曲线 + box plot
├── results/
│   └── ...                            # 实验结果 JSON + 图
└── README.md
```

### 离散回溯 BO 核心逻辑

```python
class DiscreteReplayBO:
    def __init__(self, candidate_pool_df, objective_col, init_indices):
        self.pool = candidate_pool_df
        self.obj_col = objective_col
        self.observed = list(init_indices)
        self.unobserved = [i for i in range(len(candidate_pool_df))
                          if i not in init_indices]

    def step(self):
        # 1. 从 observed 点拟合 GP（BoTorch SingleTaskGP）
        # 2. 对 unobserved 点计算 EI（ExpectedImprovement）
        # 3. 选 EI argmax，移入 observed
        # 4. 返回该点的真实目标值（查表）
        pass

    def run(self, n_rounds):
        best_so_far = [max(self.pool.iloc[self.observed][self.obj_col])]
        for _ in range(n_rounds):
            val = self.step()
            best_so_far.append(max(best_so_far[-1], val))
        return best_so_far
```

---

## 五、LLM Prompt 设计

### Warm-start prompt（固定 gold search space，只选初始点）

```
你是一个食品科学专家。以下是 {N} 个功能饮料候选配方，
每个配方包含三种植物提取物的添加量：
- CE（豆蔻精油，ml/100ml）
- GE（姜提取物，ml/100ml）
- HS（木槿溶液，ml/100ml）

候选配方列表：
{候选池表格，只有成分列，不给目标值}

目标是最大化 DPPH 自由基清除率（抗氧化活性）。

请从中选出最值得优先实验的 {k} 个配方编号，并简要说明理由。
要求考虑：
- 各成分在文献中已知的抗氧化活性贡献
- 成分间可能的协同或拮抗效应
- 已有研究中功能饮料的常见有效浓度区间

只输出 JSON：{"selected": [编号], "reasoning": "..."}
```

**注意**：
- ❌ 不提成本效益（数据里没有）
- ❌ 不让 LLM 定义搜索空间（固定 gold space）
- ✅ 只让 LLM 从候选池里选 k 个点

### LLM 推理执行方式

在 Hopper 上写一个简单脚本：

```bash
# 在 Hopper login node 上，进入容器
# 加载 FoodmoleGPT checkpoint（已有的 Qwen3-CPT+SFT LoRA）
# 跑一次推理，输出 JSON
python llm_priors/generate_prior.py \
    --model foodmolegpt \
    --candidates data/candidates.csv \
    --k 3 \
    --output llm_priors/foodmolegpt_init.json

# 同理跑 Qwen3-base
python llm_priors/generate_prior.py \
    --model qwen3-base \
    --candidates data/candidates.csv \
    --k 3 \
    --output llm_priors/qwen3base_init.json
```

结果缓存成 JSON 后 scp 回本地，后续所有实验在 MacBook 上跑。

---

## 六、三天执行计划

### Day 1 — 数据 + Baseline（必须完成）

| 时段 | 任务 | 产出 |
|------|------|------|
| 上午 | ① 打开 PMC9281929，从 Table 2 提取 14 行数据 → `candidates.csv` | CSV 文件 |
| | ② 从论文 Methods 提取变量范围 → `gold_search_space.json` | JSON 文件 |
| | ③ 安装 BoTorch（`pip install botorch`） | 环境就绪 |
| 下午 | ④ 实现 `DiscreteReplayBO` 类 | 主循环代码 |
| | ⑤ 实现 Random Search baseline | baseline 代码 |
| | ⑥ 跑 Random + Vanilla BO（随机 init），各 20 次 | 两条 baseline 曲线 |
| 晚上 | ⑦ 画第一版 best-so-far 曲线，确认 BO > Random | 验证图 |
| | ⑧ 如果 BO 没显著优于 Random → 数据集不合适，换备选 | 止损检查 |

**Day 1 止损门槛**：如果 Vanilla BO 的 best-so-far 曲线和 Random 几乎重合，说明 14 个点的目标值区分度不够，立即换数据集。

### Day 2 — LLM 接入 + 主实验（必须完成）

| 时段 | 任务 | 产出 |
|------|------|------|
| 上午 | ① 写 prompt 模板 | prompt 文件 |
| | ② 在 Hopper 上跑 Qwen3-base 推理 → 缓存 JSON | `qwen3base_init.json` |
| | ③ 在 Hopper 上跑 FoodmoleGPT 推理 → 缓存 JSON | `foodmolegpt_init.json` |
| | ④ scp 回本地 | JSON 文件到位 |
| 下午 | ⑤ 解析 JSON → 提取 init indices | 解析代码 |
| | ⑥ 跑 Qwen3-base init → BO，20 次 | 第三条线 |
| | ⑦ 跑 FoodmoleGPT init → BO，20 次 | 第四条线 |
| 晚上 | ⑧ 画四条线的 best-so-far 曲线（**主图**） | **核心产出** |
| | ⑨ 计算 4 个指标：rounds to 90%, final best, init quality, top-quartile hit rate | 指标表 |

**Day 2 交付物**：一张四条线的 best-so-far 曲线 + 一个指标对比表。有这两样东西，简历就能写了。

### Day 3 — 补充 + 整理（可选，有余力再做）

| 优先级 | 任务 | 说明 |
|--------|------|------|
| P1-a | Gemini Flash init → BO | 如果想加通用 LLM 对比线 |
| P1-b | Order robustness | 打乱候选顺序 3-5 次，重新跑 LLM，算选点 Jaccard 相似度 |
| P1-c | Search space proposal 实验 | 让各 LLM 自己提变量范围，与 gold space 比 coverage |
| P2 | 换第二个数据集做 cross-task 验证 | 证明结论不是 dataset-specific |
| **必做** | **整理图表 + 1 页实验总结** | **简历素材** |

---

## 七、可视化清单

### 主图（Day 2 必出）

1. **Best-so-far curve**（x: 迭代轮数, y: best observed DPPH）
   - 4 条线：Random / Vanilla BO / Qwen3-base→BO / FoodmoleGPT→BO
   - 实线 = 均值，阴影 = 标准差（20 次重复）
   - 水平虚线 = published best

2. **Init quality bar chart**
   - 每种方法的初始 k 个点的平均 DPPH
   - 加误差棒

### 补充图（Day 3 可选）

3. **Top-quartile hit rate bar chart**
4. **Final best value box plot**（4 种方法 × 20 次重复）
5. **Order robustness heatmap**（如果做了）

---

## 八、简历更新

跑完后新增一条 bullet（接在现有消融研究后面）：

```
- **LLM 引导的配方优化框架**：基于 BORA 思路搭建 LLM-guided 
  Bayesian Optimization 实验设计框架（BoTorch, GP-EI），
  在食品配方 published benchmark 上做离散回溯验证；
  以 FoodmoleGPT 生成 warm-start 先验，
  较 Qwen3 基座提升收敛速度 X%，
  较随机初始化提升 Y%，
  Top-quartile hit rate 达 Z%，
  验证领域微调对闭环实验设计的增益
```

### 面试话术要点

1. **为什么做这个**："通用 LLM 在食品配方优化中缺乏领域先验，我们想验证领域微调能否提升 BO 的 warm-start 质量"
2. **怎么验证**："在 published RSM 实验数据上做离散回溯，固定搜索空间只比先验质量，控制变量干净"
3. **核心发现**："FoodmoleGPT 选出的初始点更接近 published best，使 BO 在 N 轮内达到 90% of published best，比基座快 X 轮"
4. **局限性**（主动说，加分）："目前是回溯验证，没有真实湿实验闭环；候选池仅 14 个点，统计功效有限；下一步计划接入真实实验室"

---

## 九、风险与应对

| 风险 | 应对 |
|------|------|
| 14 个点太少，BO 和 Random 无显著差异 | Day 1 晚检查，不行就换备选数据集（Foods 2023 那篇） |
| FoodmoleGPT 和 Qwen3-base 选的点一样 | 检查 prompt 是否给了足够的领域上下文；尝试调 temperature |
| Hopper 队列拥堵，推理任务排不上 | 推理只需几分钟 GPU 时间，用交互式 qsub 或者本地跑 4-bit 量化 |
| BoTorch GP 在 14 个点上拟合不稳定 | 调 GP kernel lengthscale prior；或者退化到 scikit-optimize |
| LLM 输出格式不是 JSON | 在 prompt 里加 few-shot 示例；加 JSON 解析 fallback |

---

*计划版本 v1 · 基于同学 7 点修正建议 · {date}*
