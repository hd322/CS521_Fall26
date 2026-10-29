# PerturbCoT 第三步运行包

该运行包使用固定的本地模型 `Qwen/Qwen2.5-Math-1.5B`，对 50 道原题各采样 5 次，并对 200 个变体各采样 1 次，总计 450 次独立生成。上传输入只含运行时题目，不含标准答案或 GSM8K 参考解答。

固定生成参数为 `temperature=0.7`、`top_p=0.95`、`top_k=50`、`max_new_tokens=512`。每条记录使用独立且可复现的种子。提示词要求给出逐步推理，并以 `Final answer: <answer>` 结束。

运行命令：

```bash
/home/haod6/.conda/envs/dlcv/bin/python run_qwen.py --output-dir smoke_results --limit 2
/home/haod6/.conda/envs/dlcv/bin/python run_qwen.py --output-dir results
```

脚本逐条追加并强制写盘，可在中断后使用相同命令恢复；已完成的 `run_id` 会被跳过。输出包含完整提示词、原始生成、答案提取结果、token 数、耗时、截断和错误状态。

如需把任务切成多个互不重叠的分片，可使用 `--start` 与 `--limit`：

```bash
/home/haod6/.conda/envs/dlcv/bin/python run_qwen.py --output-dir shard1 --start 113 --limit 113
```

运行结束后，在本地使用离线标准答案评估。这个步骤会生成逐条带正确性标签的记录、按原题汇总的稳定性记录和总指标：

```bash
python evaluate_outputs.py \
  --generations results/generations.jsonl \
  --output-dir results/offline_evaluation
```
