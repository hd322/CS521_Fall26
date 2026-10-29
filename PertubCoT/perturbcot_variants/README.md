# PerturbCoT 第二步：配对变体数据集

本目录完成 50 道 GSM8K 原题的四类答案保持型扰动，共生成 200 个变体。每个变体继承原题 ID、分组、数据划分和离线标准答案。运行时文件不包含标准答案或 GSM8K 参考解答。

## 已实现的生成方法

| 类型 | 实现 | 一致性约束 |
| --- | --- | --- |
| `paraphrase` | 按题目显式重写最后的提问句 | 前面的条件文本逐字不变；数字序列不变；所求数量不变 |
| `entity_rename` | 按题目显式执行全局实体替换 | 每个指定源实体全部替换；数字、关系和角色不变 |
| `format_change` | 原条件句改为项目符号，最后一句置于 `Question` 区域 | 每个原句逐字保留且顺序不变 |
| `irrelevant_information` | 在题末追加不含数字的固定背景句 | 原题全文逐字保留；新增句不参与数学关系 |

生成器拒绝以下情况：输入文件哈希改变、题目规格未完整覆盖 50 道题、变体数量或类型错误、数字序列变化、实体未完整替换、格式变体遗漏原句、无关信息不是精确追加、未知审核 ID 或无效审核决定。

## 运行

要求 Python 3.9 或更新版本，无第三方依赖。在本目录运行：

```bash
python3 prepare_variants.py
python3 -m unittest -v test_prepare_variants.py
```

生成规则位于 `variant_specs.py`。修改规则后必须重新逐条检查，重新运行 `record_review.py` 记录审核决定，再运行生成器。每条决定绑定变体文本的 SHA-256，旧决定与新文本不匹配时生成器会拒绝导出。

## 输出文件

| 文件 | 内容 |
| --- | --- |
| `data/offline_eval/paired_variants.jsonl` | 200 条完整配对记录，包含标准答案和变换记录 |
| `data/offline_eval/paired_variants.csv` | 同一数据的表格版本 |
| `data/offline_eval/review_preview.md` | 按原题分组的可读审核文档 |
| `data/runtime/variants.jsonl` | 可供模型运行的 200 个变体，不含标准答案 |
| `data/runtime/dev.jsonl` | 10 个调参原题对应的 40 个变体 |
| `data/runtime/test.jsonl` | 40 个测试原题对应的 160 个变体 |
| `data/validation_report.json` | 数量、类型、一致性及审核统计 |
| `data/manifest.json` | 输入、脚本、规则、审核文件及输出哈希 |
| `review_decisions.jsonl` | 200 条 Codex 逐项审核决定 |
| `test_results.txt` | 本次实际测试日志 |

完整离线记录的核心字段为：

- `original_id`、`original_question`、`variant_id`、`variant_question`；
- `perturbation_type`、`gold_answer`、`split`、`group_id`；
- `verification_status`、`independent_human_review_status`；
- `transform_record`：改写尾句、实体替换、保留句子或新增句的机器可查记录。

## 核验状态如何理解

全部 200 个变体通过自动结构检查，并由 Codex 逐题检查题意、数学条件、提问目标和答案不变，状态为 `passed_automatic_and_codex_review`。这不是独立的人类标注，因此 `independent_human_review_status` 保持 `pending`。正式论文实验前，建议由一位不了解生成过程的人工复核者检查 `review_preview.md`，并单独记录同意、修改或拒绝；不要直接覆盖当前审核记录。

六道原题没有人名或专名，其 `entity_rename` 使用一致的普通实体替换，例如 `potatoes → turnips`。这些记录可以通过 `transform_record` 识别。如研究定义要求实体改名严格限于专名，应在预注册中排除这六题的该扰动，或预先替换原题后创建新数据版本。

## 当前结果

- 50 道原题，每题 4 个变体，共 200 条；
- 40 条调参变体，160 条测试变体；
- 每类扰动各 50 条；
- 200 条均进入运行时数据；
- 所有标准答案只出现在 `offline_eval`；
- 还没有运行被测模型、监控器或验证器。
