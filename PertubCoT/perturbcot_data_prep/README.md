# PerturbCoT：50 道原题准备工具

本交付实现原题准备：从官方 GSM8K 固定版本读取题目，抽取 50 道原题，划分 10 道调参题和 40 道测试题，输出题目、标准答案、原始解答和可复现记录。**不包含扰动变体生成、人工数学核验或模型推理实验。**

## 快速运行

要求 Python 3.9 或更新版本，无第三方依赖。进入本文件所在目录后运行：

```bash
python3 prepare_dataset.py
python3 -m unittest -v test_prepare_dataset.py
```

已附带官方源数据快照，默认完全离线运行。重复运行会覆盖本工具生成的数据文件，并得到字节相同的结果；不要直接在生成文件中记录人工审核意见，审核记录应另存。

需要重新从官方地址下载时运行：

```bash
python3 prepare_dataset.py --download
```

下载使用固定 commit URL，并检查预期 SHA-256，不接受悄悄变动的数据。指定另一个输出目录可保留现有数据：

```bash
python3 prepare_dataset.py --output-dir new_data
```

## 文件说明

| 文件 | 用途 |
| --- | --- |
| `config.json` | 数据版本、抽样种子、数量及扰动类型配置 |
| `prepare_dataset.py` | 数据读取、抽样、划分、答案解析、导出和自动校验 |
| `test_prepare_dataset.py` | 答案解析、去重、异常拒绝及端到端复现测试 |
| `source/gsm8k_test.jsonl` | 官方 1,319 道测试题的完整快照，包含答案 |
| `source/LICENSE.gsm8k` | 官方 MIT 许可证 |
| `data/runtime/questions.jsonl` | 50 道题，不含标准答案或参考解答 |
| `data/runtime/dev.jsonl` | 10 道项目调参题，不含答案 |
| `data/runtime/test.jsonl` | 40 道项目测试题，不含答案 |
| `data/offline_eval/originals.jsonl` | 50 道原题的完整记录，含标准答案、参考解答和来源 |
| `data/offline_eval/gold.jsonl` | 用原题 ID 连接的离线评估标签 |
| `data/offline_eval/preview.md` | 方便阅读的全部 50 道题与答案 |
| `data/manifest.json` | 抽样规则、选中 ID、配置、脚本及输出文件哈希 |
| `data/validation_report.json` | 自动数据校验结果 |
| `test_results.txt` | 本次实际执行的代码测试日志 |

**运行时边界：**后续生成器、监控器和验证器只加载 `data/runtime/`。`source/`、`data/offline_eval/` 及预览文档含标准答案，不可加入运行时提示词。当前是文件与字段层面的分离，未实现进程级权限隔离；接入模型时还需遵守此加载边界。

## 抽样和划分规则

1. 核对官方源文件哈希及 1,319 条记录数，解析每条末尾 `####` 后的数值标签；不猜测答案，不静默跳过失败行。
2. 保持原题英文及参考解答原样。对题目进行 Unicode NFKC、大小写和空白规范化，计算分组哈希，仅用于去重，不修改输出题目。
3. 为每条原题生成 ID：`gsm8k_test_XXXX`。后缀是固定源文件中从 0 开始的行索引，这是本项目分配的 ID，不是上游提供的 ID。
4. 对唯一题目组计算 `SHA256(seed|sample|group_id)`，按哈希排序取前 50 组；重复题保留源文件中第一条。种子固定为 `20261015`，抽样不依赖标准答案。
5. 对选中组独立计算 `SHA256(seed|split|group_id)`，前 10 组归入 `dev`，其余 40 组归入 `test`。按 ID 排序导出。
6. 执行字段、数量、分组互斥、来源一致性、答案提取及可复现性检查，生成报告与清单。

哈希排序定义了明确的确定性抽样规则，不依赖 Python 的随机库实现。更改种子或规模会改变选择或划分，应视为新的数据版本，在查看模型结果前固定。

## 记录字段

`originals.jsonl` 每行包含：

- `original_id`：可追溯原题 ID。
- `question`：未修改的原题文本。
- `gold_answer`：规范化十进制字符串；保留字符串格式，避免浮点误差。
- `source_solution`：原始参考解答，包括末尾答案标记，仅用于离线核对。
- `split`：本项目 `dev` 或 `test`。
- `group_id`：规范化题目的 SHA-256；后续四个变体继承该 ID 与划分。
- `source_dataset`、`source_split`、`source_row_index`：上游数据来源与位置。
- `template_id`：当前为 null，上游未提供模板 ID。
- `verification_status`：`source_imported_auto_validated`，只表示导入与结构校验通过。
- `human_review_status`：`not_reviewed`，不冒充人工核验。

运行时文件使用字段白名单，仅输出 `original_id`、`question`、`split`、`group_id`。

## 解读限制与后续步骤

- 本项目的 `dev` 和 `test` 都从官方 `test` split 抽取，是 50 题先导实验的局部划分。使用其中 10 题调参后，不得把结果宣传为在完整官方测试集上进行的标准 GSM8K 测评。
- GSM8K 没有提供模板 ID。当前检查能够阻止规范化后的重复题跨组，不能保证语义相似模板不跨集合。若后续发现共享模板，应先建立模板标注并重新按模板划分；若使用 GSM-Symbolic，须采用其模板分组。
- 来源答案未逐条重新求解，也没有人工审查其数学正确性。自动校验通过不等于数学条件或标准答案已经人工核验。
- 未按题目是否含人名筛选，以免预先引入筛选偏差。下一步生成实体改名变体时，需逐条检查可改名的实体；没有合适实体的题目应记录不可适用状态，若决定替换原题，须按预先固定的规则形成新的数据版本。
- 下一步为每道题制作四种变体，继承原题组与划分，在单独审核记录中检查题意、条件和答案不变。当前没有生成 200 条占位变体，也未调用被测模型。
- 本次模型 API 调用数为 0；完整基础求解阶段预计 450 次生成，尚未运行。

## 数据来源与许可

官方仓库：[openai/grade-school-math](https://github.com/openai/grade-school-math)。

固定版本：[3101c7d5072418e28b9008a6636bde82a006892c](https://github.com/openai/grade-school-math/tree/3101c7d5072418e28b9008a6636bde82a006892c)。

源数据 SHA-256：`3730d312f6e3440559ace48831e51066acaca737f6eabec99bccb9e4b3c39d14`。

上游数据随 MIT 许可证提供，已保留其完整许可证与版权声明。模型与监控器的选择不属于本次数据准备实现。
