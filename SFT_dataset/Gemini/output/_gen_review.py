import json, random

src = '/Users/cody/Workspace/FoodmoleGPT/SFT_dataset/Gemini/output/pilot.jsonl'
dst = '/Users/cody/Workspace/FoodmoleGPT/SFT_dataset/Gemini/output/pilot_review_60.md'

with open(src) as f:
    lines = f.readlines()

total = len(lines)
samples = sorted(random.sample(range(total), 60))

type_labels = {
    'FACTUAL': '事实型',
    'METHODOLOGICAL': '方法型',
    'MECHANISTIC': '机制型',
    'APPLICATION': '应用型',
}

out = []
out.append('# Pilot 数据集人工检查样本（60条）\n\n')
out.append(f'> 源文件：`pilot.jsonl`（共 {total} 条），随机抽取 60 条，按原始索引排序\n\n')
out.append('---\n\n')

for seq, idx in enumerate(samples, 1):
    d = json.loads(lines[idx])
    t = d.get('type', '')
    source = d.get('source', '')
    article_id = d.get('article_id', '')
    instruction = d.get('instruction', '').strip()
    inp = d.get('input', '').strip()
    output = d.get('output', '').strip()

    out.append(f'## 第 {seq} 条  |  索引 #{idx}\n\n')
    out.append(f'| 字段 | 值 |\n')
    out.append(f'|------|----|\n')
    out.append(f'| 类型 | `{t}` {type_labels.get(t, "")} |\n')
    out.append(f'| 来源 | {source} |\n')
    out.append(f'| article_id | `{article_id}` |\n\n')
    out.append(f'### Instruction\n\n{instruction}\n\n')
    if inp:
        out.append(f'### Input\n\n{inp}\n\n')
    out.append(f'### Output\n\n{output}\n\n')
    out.append('---\n\n')

with open(dst, 'w', encoding='utf-8') as f:
    f.writelines(out)

print(f"Done: {dst}")
print(f"Total: {total}, sampled {len(samples)} records, idx range: {samples[0]}~{samples[-1]}")
