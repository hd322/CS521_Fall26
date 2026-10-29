# PerturbCoT 项目进度更新

**更新时间：** 2026-10-16  
**当前实验：** Qwen2.5-Math-1.5B，50 道 GSM8K 原题，200 个语义保持变体

## 总体状态

第一版小规模实验已完成范围定义、题目准备、四类变体生成、450 次模型推理，以及答案监控器和确定性 CoT 方程监控器。统一验证器、完整公平对照、干预后准确率、正式图表和最终项目报告尚未完成。

| 步骤 | 状态 | 当前结论 |
| --- | --- | --- |
| 1. 研究目标和范围 | 已完成 | 三个研究问题、四类答案保持扰动和 50 题试运行范围已固定 |
| 2. 题目和变体 | 试运行数据完成 | 50 原题、200 变体通过自动检查和 Codex 复核；独立人工复核待完成 |
| 3. 模型运行 | 已完成 | 450/450 次生成成功，原始输出与成本记录齐全 |
| 4. 两个监控器 | 第一版代码完成 | 答案监控有效但误报高；显式方程 CoT 监控精确但覆盖不足；人工核验待完成 |
| 5. 统一验证步骤 | 未实现 | 只有设计说明，尚无验证器运行代码和答案更新结果 |
| 6. 公平对照实验 | 部分完成 | 基础模型、重复投票、答案监控和答案＋CoT 检测已得到；随机/始终/触发验证未运行 |
| 7. 效果与案例评估 | 部分完成 | 已评估初始准确率、稳定性、监控检测和成本；尚无验证干预结果、图和完整案例集 |
| 8. 最终交付物 | 部分完成 | 数据、代码、配置、原始记录和阶段说明齐全；最终报告、验证结果、图表和演示未完成 |

## 1. 确定研究目标和第一版范围

**状态：已完成。**

已固定三个研究问题：扰动对答案与推理的影响、CoT 检查相对答案检查的增量价值，以及触发验证后的准确率与成本。第一版只使用释义改写、实体改名、格式变化和添加无关信息，不包含数值扰动。

**输出：**

- [`experiment_scope.md`](experiment_scope.md)：一页实验范围、研究问题、数据规模、监控与验证口径。

## 2. 准备题目并生成经过检查的变体

**状态：试运行数据完成，独立人工复核待完成。**

从固定版本的 GSM8K test 集中按 SHA-256 排名确定性抽取 50 道原题，划分为 10 道 dev 和 40 道 test。同一原题的全部变体保持在同一集合。共生成 200 个变体，每类 50 个。运行时文件不含标准答案。

所有变体通过结构检查和 Codex 语义复核；`independent_human_review_status` 仍为 `pending`，因此不能将当前状态描述成独立人工核验完成。

**输出：**

- [`perturbcot_data_prep/`](perturbcot_data_prep/)：原题抽取脚本、50 道原题、dev/test 划分、离线金标准和验证报告。
- [`perturbcot_variants/`](perturbcot_variants/)：变体生成代码、一致性规格、200 条配对变体、运行时无答案数据、审核记录和测试。
- [`perturbcot_variants/data/offline_eval/paired_variants.jsonl`](perturbcot_variants/data/offline_eval/paired_variants.jsonl)：完整配对数据。
- [`perturbcot_variants/data/runtime/variants.jsonl`](perturbcot_variants/data/runtime/variants.jsonl)：运行时变体。
- [`step2_summary.md`](step2_summary.md)：第二步完成说明和限制。

## 3. 运行模型并保存完整实验记录

**状态：已完成。**

使用 Qwen2.5-Math-1.5B：50 道原题各生成 5 次，200 个变体各生成 1 次，共 450 次。固定 `temperature=0.7`、`top_p=0.95`、`top_k=50`、`max_new_tokens=512` 和逐条随机种子。各版本独立运行，不共享历史回答。

450 条记录全部为 `status=ok`，无重复或缺失；449 条成功抽取答案，20 条达到长度上限并保留。运行时记录不含标准答案。总成本为 46,022 输入 token、111,725 输出 token，逐条耗时之和为 4,805.65 秒。

**输出：**

- [`perturbcot_model_run/`](perturbcot_model_run/)：可恢复、可分片的运行脚本与配置。
- [`perturbcot_qwen25_math_15b_results/merged-results/generations.jsonl`](perturbcot_qwen25_math_15b_results/merged-results/generations.jsonl)：450 条完整原始生成记录。
- [`perturbcot_qwen25_math_15b_results/offline_evaluation/`](perturbcot_qwen25_math_15b_results/offline_evaluation/)：逐条离线正确性、按题汇总和总体指标。
- [`perturbcot_qwen25_math_15b_results.zip`](perturbcot_qwen25_math_15b_results.zip)：第三步完整压缩包。

## 4. 实现两个监控器

**状态：第一版代码与机器评估完成，独立人工核验待完成。**

监控器 A 比较原题首次答案和四个变体答案。监控器 B 在相同输出上抽取显式数值方程，分别记录原题算术错误、共享操作数上的结果冲突、变体算术错误和无关数字使用。不同顺序、舍入差异和结果相同的等价写法不报警；没有可靠关系时输出 `unknown`。

运行时监控不读取标准答案。离线评估阶段才将报警与原题首次答案的正确性连接。

**输出：**

- [`perturbcot_monitors/monitor_answer.py`](perturbcot_monitors/monitor_answer.py)：监控器 A。
- [`perturbcot_monitors/monitor_cot.py`](perturbcot_monitors/monitor_cot.py)：CoT 关系抽取与监控器 B。
- [`perturbcot_monitors/monitor_spec.md`](perturbcot_monitors/monitor_spec.md)：规则、等价处理和限制。
- [`perturbcot_monitors/results/runtime/monitor_results.jsonl`](perturbcot_monitors/results/runtime/monitor_results.jsonl)：不含金标准的 50 组监控结果和具体理由。
- [`perturbcot_monitors/results/runtime/cot_relations.jsonl`](perturbcot_monitors/results/runtime/cot_relations.jsonl)：抽取出的方程和关系。
- [`perturbcot_monitors/results/offline_evaluation/monitor_metrics.json`](perturbcot_monitors/results/offline_evaluation/monitor_metrics.json)：全部、dev 和 test 指标。
- [`perturbcot_monitors/results/offline_evaluation/human_audit.csv`](perturbcot_monitors/results/offline_evaluation/human_audit.csv)：30 题分层人工核验表，当前均为 `pending_human_review`。

## 5. 实现统一的额外验证步骤

**状态：未实现。**

范围文档已经规定初版使用“根据原题独立重新求解、每题最多一次”的验证方案，并要求验证器不能访问标准答案。尚缺：验证提示词、运行脚本、接受验证答案的规则实现、失败处理和实际验证输出。

**当前相关设计：** [`experiment_scope.md`](experiment_scope.md)。

## 6. 设置公平的对照实验

**状态：部分完成。**

已经获得基础单次准确率、原题五次投票、答案监控和答案＋CoT 检测结果。尚未实现随机验证、监控触发验证、始终验证，也没有在相近验证预算下比较最终准确率。监控阈值仍是第一版确定性规则，没有在 dev 集完成正式选择和冻结。

**已有输出：**

- [`perturbcot_qwen25_math_15b_results/offline_evaluation/metrics.json`](perturbcot_qwen25_math_15b_results/offline_evaluation/metrics.json)：基础和重复投票结果。
- [`perturbcot_monitors/results/offline_evaluation/monitor_metrics.json`](perturbcot_monitors/results/offline_evaluation/monitor_metrics.json)：答案与 CoT 检测对比。

## 7. 评估效果并解释案例

**状态：部分完成。**

已统计原题初始准确率、重复投票准确率、扰动准确率、稳定性、监控混淆矩阵、置信区间、token 和耗时。已自动列出答案监控成功、答案分歧但初始答案正确、CoT 新增有效信息、答案一致但仍错误四类案例集合。后两类在本批样本中为空。

尚未完成验证前后准确率、错题修正数、正确改错数、验证触发成本、正式结果图和经过人工确认的案例叙述。

**已有输出：**

- [`perturbcot_monitors/results/offline_evaluation/evaluated_monitor_results.jsonl`](perturbcot_monitors/results/offline_evaluation/evaluated_monitor_results.jsonl)
- [`perturbcot_monitors/results/offline_evaluation/monitor_summary.md`](perturbcot_monitors/results/offline_evaluation/monitor_summary.md)
- [`perturbcot_monitors/results/offline_evaluation/human_audit.csv`](perturbcot_monitors/results/offline_evaluation/human_audit.csv)

## 8. 整理最终交付物

**状态：部分完成。**

现有交付物包括实验范围、变体规格、配对数据、生成代码、450 条原始输出、运行配置、监控代码、阶段指标和校验信息。尚缺统一验证器、完整对照实验、结果图、正式案例集、端到端演示和最终项目报告。

## 当前分析 Summary

### 模型与扰动稳定性

- 原题首次准确率为 25/50，即 50.0%，95% Wilson 区间为 36.6%–63.4%。
- 原题五次多数投票准确率为 33/50，即 66.0%，说明重复采样能纠正部分随机错误。
- 只有 16/50 个原题组在五次重复采样中答案完全稳定。
- 200 个变体中只有 89 个答案与原题首次答案相同，匹配率为 44.5%。输入扰动造成的输出变化很大，但这部分变化也混合了模型自身的采样波动。
- 变体准确率分别为：实体改名 54%、格式变化 52%、无关信息 62%、释义改写 66%。50 题样本的区间较宽，不能把这些排序解释成稳定的扰动难度结论。

### 监控器结果

- 答案监控对 37/50 题报警，抓到全部 25 个初始错误：TP=25、FP=12、FN=0、TN=13，召回率 100%，精确率 67.6%，正确题误报率 48%。
- CoT 独立信号对 4/50 题报警，这 4 题的原始答案都错误，因此机器离线标签下精确率为 100%。但它只抓到 25 个错误中的 4 个，总体召回率为 16%；20/50 题因缺少可比较的显式关系而为 `unknown`。
- CoT 的 4 个报警全部已经被答案监控发现，新增真阳性为 0，新增误报也为 0。答案＋CoT 的报警集合因此与答案监控相同。
- 组合监控把 4 个答案一致且原始答案正确的题组从 `consistent` 降为 `unknown`，覆盖率从 100% 降到 92%，没有提高错误检测。

### 当前能回答与不能回答的问题

RQ1 已有初步答案：Qwen2.5-Math-1.5B 在这些输入扰动和重复采样下都表现出较强不稳定性。答案不一致是高召回但高误报的风险信号。

RQ2 的第一版结果不支持 CoT 有增量优势。显式方程检查能给出准确、可解释的错误理由，例如“`80 - 220 + 23 = 83`，实际为 `-117`”，但覆盖率太低，而且没有发现答案监控漏掉的错误。这不是最终否定结论，因为当前解析器无法理解大量纯自然语言关系，独立人工审核也未完成。

RQ3 尚不能回答，因为验证器和验证对照实验尚未运行。

### 建议的下一步

1. 先由独立人工完成 30 题监控审核表，并优先检查 4 个 CoT 报警、20 个 `unknown` 和答案监控的 12 个误报。
2. 根据 dev 集人工结果改进 CoT 关系表示，使其覆盖纯自然语言关系，同时保持 `unknown` 机制；规则冻结后只在 test 集报告结果。
3. 实现统一独立验证器和固定答案更新规则，再运行随机验证、答案监控验证、答案＋CoT 验证和始终验证。
4. 在当前 50 题流程完整跑通以前，不建议扩展到 200 题或第二个模型。
