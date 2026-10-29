# PerturbCoT 第四步：答案与 CoT 监控器

本目录在同一批 450 条 Qwen2.5-Math-1.5B 输出上实现两个监控器。运行时监控不读取标准答案；`evaluate_monitors.py` 只在监控结束后离线加入金标准。

## 实现

- `monitor_answer.py`：比较原题首次答案和四个语义保持变体答案，输出 `alert`、`consistent` 或 `unknown`。
- `monitor_cot.py`：抽取显式数值方程，检查原题算术错误、共享操作数上的冲突，以及无关信息新增数字是否进入计算。
- `evaluate_monitors.py`：在离线阶段评估初始错误检测能力，并生成待人工核验的 30 题分层样本。
- `monitor_spec.md`：判定规则、允许的等价变化和已知限制。
- `test_monitors.py`：答案规范化、答案报警、方程抽取、分数表达式、交换顺序和舍入等价测试。

## 运行

```bash
python monitor_answer.py \
  --generations ../perturbcot_qwen25_math_15b_results/merged-results/generations.jsonl \
  --output results/answer_monitor.jsonl

python monitor_cot.py \
  --generations ../perturbcot_qwen25_math_15b_results/merged-results/generations.jsonl \
  --output-dir results/runtime

python evaluate_monitors.py \
  --monitor-results results/runtime/monitor_results.jsonl \
  --gold ../perturbcot_data_prep/data/offline_eval/gold.jsonl \
  --generations ../perturbcot_qwen25_math_15b_results/merged-results/generations.jsonl \
  --output-dir results/offline_evaluation

python test_monitors.py
```

## 第一版结果

| 指标 | 答案监控 | CoT 独立信号 | 答案＋CoT |
| --- | ---: | ---: | ---: |
| 报警 | 37 | 4 | 37 |
| TP | 25 | 4 | 25 |
| FP | 12 | 0 | 12 |
| 对全部初始错误的召回率 | 100% | 16% | 100% |
| 报警精确率 | 67.6% | 100% | 67.6% |
| unknown | 0 | 20 | 4 |

CoT 的 4 个报警都是实际初始错误，但全部已被答案监控发现，因此没有新增真阳性。CoT 第一版没有制造新的报警误报，但组合后把 4 个答案一致且初始正确的题组标记为 `unknown`。结果说明显式方程检查很精确但覆盖不足，当前没有证据表明它优于答案监控。

`human_audit.csv` 已准备 30 个分层案例，判断栏保持空白，状态均为 `pending_human_review`。在独立人工填写之前，不能声称完成了监控器语义准确性的人工验证。

## 输出

- `results/answer_monitor.jsonl`：监控器 A 的 50 个题组结果。
- `results/runtime/monitor_results.jsonl`：A、CoT 独立信号和组合判定，不含标准答案。
- `results/runtime/cot_relations.jsonl`：每个版本抽取的方程与关系。
- `results/runtime/runtime_summary.json`：运行时决策和成本统计。
- `results/offline_evaluation/evaluated_monitor_results.jsonl`：离线加入正确性标签后的完整结果。
- `results/offline_evaluation/monitor_metrics.json`：全部、dev 和 test 指标。
- `results/offline_evaluation/monitor_summary.md`：简要结果。
- `results/offline_evaluation/human_audit.csv`：待独立人工核验表。
