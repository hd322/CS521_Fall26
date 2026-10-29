# PerturbCoT：Qwen2.5-Math-1.5B 第一轮模型运行

本目录是第三步“运行模型并保存完整实验记录”的可复现交付物。实验使用
`Qwen/Qwen2.5-Math-1.5B`，对 50 道 GSM8K 原题各独立生成 5 次，并对每道题的
4 个语义保持变体各生成 1 次，共 450 次生成。

## 本轮配置

- 原题：50 道
- 变体：200 个（改名、格式变化、无关信息、释义改写各 50 个）
- 原题重复次数：5
- 总生成次数：450
- 采样：`temperature=0.7`、`top_p=0.95`、`top_k=50`
- 最大新 token：512
- 基础随机种子：`202610150000`，每条记录派生独立种子
- 提示：要求逐步推理，并以 `Final answer: <answer>` 结束

运行时输入不含标准答案。标准答案只在下载后的离线评估阶段加入。

## 目录内容

- `merged-results/generations.jsonl`：450 条完整模型记录，包括题目、提示词、原始
  输出、提取答案、token 数、耗时、截断状态和运行状态。
- `merged-results/schedule.jsonl`：固定运行顺序、重复编号和随机种子。
- `merged-results/originals.jsonl`、`variants.jsonl`：运行时输入，不含标准答案。
- `merged-results/config.json`：模型、提示词和生成参数。
- `merged-results/run_qwen.py`：可恢复、可分片的模型运行脚本。
- `merged-results/raw_summary.json`：不使用标准答案的运行质量与成本汇总。
- `offline_evaluation/evaluated_generations.jsonl`：离线加入标准答案后的逐条正确性记录。
- `offline_evaluation/group_summary.jsonl`：按原题汇总的重复采样、变体和答案监控结果。
- `offline_evaluation/metrics.json`：机器可读的总指标。
- `offline_evaluation/run_summary.md`：简要结果说明。
- `evaluate_outputs.py`：离线评估脚本。

## 结果摘要

- 450/450 条记录运行成功；运行 ID 无重复、无缺失。
- 最终答案成功抽取 449/450；失败项为 `gsm8k_test_0049__original__r1`。
- 20 条生成达到 `max_new_tokens=512`。
- 原题第一次回答准确率：25/50 = 50.0%，95% Wilson 区间 36.6%–63.4%。
- 全部 200 个变体准确率：117/200 = 58.5%，95% Wilson 区间 51.6%–65.1%。
- 原题五次采样多数投票准确率：33/50 = 66.0%。
- 只看答案的跨变体监控器在 37/50 组上报警；对原题初始错误的召回率为 100%，
  精确率为 67.6%，正确原题上的误报率为 48.0%。
- 总 token：157,747（输入 46,022；输出 111,725）。
- 单条生成平均耗时：10.68 秒；逐条耗时之和为 4,805.65 秒。并行执行时该总和不等于墙钟时间。

这些结果完成了模型运行和答案级基线。它们尚不能回答 CoT 监控是否优于答案监控；
下一步需要在同一批原始输出上实现 CoT 关系抽取与矛盾判定，再与这里的答案监控器比较。

## 复现评估

```bash
python evaluate_outputs.py \
  --generations merged-results/generations.jsonl \
  --gold /path/to/offline_eval/gold.jsonl \
  --output-dir offline_evaluation
```

`gold.jsonl` 必须只提供给离线评估脚本，不能提供给运行时模型、监控器或验证器。
