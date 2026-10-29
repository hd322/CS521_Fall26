#!/usr/bin/env python3
"""Offline evaluation for answer-only and answer-plus-CoT monitors."""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from monitor_answer import read_jsonl


def wilson(successes: int, total: int, z: float = 1.96) -> dict[str, float | None]:
    if total == 0:
        return {"low": None, "high": None}
    proportion = successes / total
    denominator = 1 + z * z / total
    center = (proportion + z * z / (2 * total)) / denominator
    margin = z * math.sqrt(
        proportion * (1 - proportion) / total + z * z / (4 * total * total)
    ) / denominator
    return {"low": center - margin, "high": center + margin}


def confusion(rows: list[dict[str, Any]], decision_path: tuple[str, ...]) -> dict[str, Any]:
    counts = Counter()
    for row in rows:
        value: Any = row
        for key in decision_path:
            value = value[key]
        decision = value
        actual_error = not row["original_initial_correct"]
        if decision == "unknown":
            counts["unknown"] += 1
            counts["unknown_positive" if actual_error else "unknown_negative"] += 1
            continue
        predicted_error = decision == "alert"
        if predicted_error and actual_error:
            counts["true_positive"] += 1
        elif predicted_error:
            counts["false_positive"] += 1
        elif actual_error:
            counts["false_negative"] += 1
        else:
            counts["true_negative"] += 1

    tp, fp = counts["true_positive"], counts["false_positive"]
    fn, tn = counts["false_negative"], counts["true_negative"]
    unknown_positive = counts["unknown_positive"]
    unknown_negative = counts["unknown_negative"]
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn + unknown_positive) if tp + fn + unknown_positive else None
    decided_recall = tp / (tp + fn) if tp + fn else None
    specificity = tn / (tn + fp) if tn + fp else None
    fpr = fp / (fp + tn + unknown_negative) if fp + tn + unknown_negative else None
    decided_fpr = fp / (fp + tn) if fp + tn else None
    coverage = (tp + fp + fn + tn) / len(rows) if rows else None
    return {
        "true_positive": tp,
        "false_positive": fp,
        "false_negative": fn,
        "true_negative": tn,
        "unknown": counts["unknown"],
        "unknown_positive": unknown_positive,
        "unknown_negative": unknown_negative,
        "coverage": coverage,
        "precision": precision,
        "recall": recall,
        "decided_recall": decided_recall,
        "specificity": specificity,
        "false_positive_rate": fpr,
        "decided_false_positive_rate": decided_fpr,
        "recall_wilson_95": wilson(tp, tp + fn + unknown_positive),
        "false_positive_rate_wilson_95": wilson(fp, fp + tn + unknown_negative),
    }


def build_audit_sample(
    rows: list[dict[str, Any]], generation_by_run: dict[str, dict[str, Any]], limit: int = 30
) -> list[dict[str, Any]]:
    """Create a deterministic, stratified sheet for later human review."""
    buckets: dict[str, list[dict[str, Any]]] = {
        "answer_alert": [],
        "cot_only_alert": [],
        "unknown": [],
        "consistent": [],
    }
    for row in rows:
        answer = row["answer_monitor"]["decision"]
        cot = row["cot_monitor"]["decision"]
        if answer == "alert":
            bucket = "answer_alert"
        elif cot == "alert":
            bucket = "cot_only_alert"
        elif answer == "unknown" or cot == "unknown":
            bucket = "unknown"
        else:
            bucket = "consistent"
        buckets[bucket].append(row)

    targets = {
        "answer_alert": 12,
        "cot_only_alert": 6,
        "unknown": 6,
        "consistent": 6,
    }
    selected: list[tuple[str, dict[str, Any]]] = []
    used: set[str] = set()
    for bucket in ("answer_alert", "cot_only_alert", "unknown", "consistent"):
        for row in sorted(buckets[bucket], key=lambda item: item["original_id"])[
            : targets[bucket]
        ]:
            selected.append((bucket, row))
            used.add(row["original_id"])
    if len(selected) < limit:
        for row in sorted(rows, key=lambda item: item["original_id"]):
            if row["original_id"] not in used:
                selected.append(("fill", row))
                used.add(row["original_id"])
            if len(selected) == limit:
                break

    audit: list[dict[str, Any]] = []
    for bucket, row in selected[:limit]:
        original_run = row["answer_monitor"]["run_ids"].get("original")
        original = generation_by_run.get(original_run or "", {})
        conflict_variant = (
            row["relation_conflicts"][0]["variant"] if row["relation_conflicts"] else None
        )
        conflict_run = (
            row["answer_monitor"]["run_ids"].get(conflict_variant)
            if conflict_variant
            else None
        )
        variant = generation_by_run.get(conflict_run or "", {})
        audit.append(
            {
                "original_id": row["original_id"],
                "split": row["split"],
                "sample_bucket": bucket,
                "gold_label_offline": "initial_error"
                if not row["original_initial_correct"]
                else "initial_correct",
                "answer_decision": row["answer_monitor"]["decision"],
                "cot_decision": row["cot_monitor"]["decision"],
                "combined_decision": row["answer_plus_cot_monitor"]["decision"],
                "machine_reason": row["cot_monitor"]["reason"],
                "question": original.get("question", ""),
                "original_cot_excerpt": (original.get("raw_output") or "")[:1200],
                "comparison_version": conflict_variant or "",
                "comparison_cot_excerpt": (variant.get("raw_output") or "")[:1200],
                "human_relation_judgment": "",
                "human_alert_judgment": "",
                "human_notes": "",
                "review_status": "pending_human_review",
            }
        )
    return audit


def write_csv(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    rows = list(rows)
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def evaluate(
    monitor_rows: list[dict[str, Any]],
    gold_rows: list[dict[str, Any]],
    generations: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any], list[dict[str, Any]]]:
    gold = {row["original_id"]: str(row["gold_answer"]) for row in gold_rows}
    evaluated: list[dict[str, Any]] = []
    for row in monitor_rows:
        original_id = row["original_id"]
        if original_id not in gold:
            raise ValueError(f"Missing gold answer for {original_id}")
        initial = row["answer_monitor"]["answers"].get("original")
        enriched = dict(row)
        enriched["gold_answer"] = gold[original_id]
        enriched["original_initial_answer"] = initial
        enriched["original_initial_correct"] = initial == gold[original_id]
        evaluated.append(enriched)

    split_rows = {
        "all": evaluated,
        "dev": [row for row in evaluated if row["split"] == "dev"],
        "test": [row for row in evaluated if row["split"] == "test"],
    }
    monitor_paths = {
        "answer_only": ("answer_monitor", "decision"),
        "cot_signal_only": ("cot_monitor", "decision"),
        "answer_plus_cot": ("answer_plus_cot_monitor", "decision"),
    }
    metrics: dict[str, Any] = {
        "groups": len(evaluated),
        "split_counts": {name: len(rows) for name, rows in split_rows.items()},
        "initial_errors": {
            name: sum(not row["original_initial_correct"] for row in rows)
            for name, rows in split_rows.items()
        },
        "monitors": {},
    }
    for monitor_name, path in monitor_paths.items():
        metrics["monitors"][monitor_name] = {
            split: confusion(rows, path) for split, rows in split_rows.items()
        }

    answer_alerts = {
        row["original_id"]
        for row in evaluated
        if row["answer_monitor"]["decision"] == "alert"
    }
    combined_alerts = {
        row["original_id"]
        for row in evaluated
        if row["answer_plus_cot_monitor"]["decision"] == "alert"
    }
    cot_only_ids = sorted(combined_alerts - answer_alerts)
    metrics["incremental_cot_signal"] = {
        "cot_only_alerts": len(cot_only_ids),
        "cot_only_alert_ids": cot_only_ids,
        "additional_true_positives": sum(
            not row["original_initial_correct"]
            for row in evaluated
            if row["original_id"] in cot_only_ids
        ),
        "additional_false_positives": sum(
            row["original_initial_correct"]
            for row in evaluated
            if row["original_id"] in cot_only_ids
        ),
    }
    metrics["case_sets"] = {
        "answer_monitor_success": [
            row["original_id"]
            for row in evaluated
            if not row["original_initial_correct"]
            and row["answer_monitor"]["decision"] == "alert"
        ],
        "cot_additional_useful": [
            row["original_id"]
            for row in evaluated
            if not row["original_initial_correct"]
            and row["answer_monitor"]["decision"] != "alert"
            and row["cot_monitor"]["decision"] == "alert"
        ],
        "answer_disagreement_but_initial_correct": [
            row["original_id"]
            for row in evaluated
            if row["original_initial_correct"]
            and row["answer_monitor"]["decision"] == "alert"
        ],
        "all_answers_consistent_but_initial_wrong": [
            row["original_id"]
            for row in evaluated
            if not row["original_initial_correct"]
            and row["answer_monitor"]["decision"] == "consistent"
        ],
    }
    by_run = {row["run_id"]: row for row in generations}
    audit = build_audit_sample(evaluated, by_run)
    return evaluated, metrics, audit


def render_summary(metrics: dict[str, Any]) -> str:
    answer = metrics["monitors"]["answer_only"]["all"]
    combined = metrics["monitors"]["answer_plus_cot"]["all"]
    cot = metrics["monitors"]["cot_signal_only"]["all"]
    incremental = metrics["incremental_cot_signal"]

    def pct(value: float | None) -> str:
        return "N/A" if value is None else f"{100 * value:.1f}%"

    return f"""# PerturbCoT 监控器第一版结果

- 评估题组：{metrics['groups']}（dev={metrics['split_counts']['dev']}，test={metrics['split_counts']['test']}）
- 原题初始错误：{metrics['initial_errors']['all']}
- 答案监控：TP={answer['true_positive']}，FP={answer['false_positive']}，FN={answer['false_negative']}，TN={answer['true_negative']}，召回率={pct(answer['recall'])}，精确率={pct(answer['precision'])}
- CoT 独立信号：TP={cot['true_positive']}，FP={cot['false_positive']}，unknown={cot['unknown']}
- 答案＋CoT：TP={combined['true_positive']}，FP={combined['false_positive']}，FN={combined['false_negative']}，TN={combined['true_negative']}，召回率={pct(combined['recall'])}，精确率={pct(combined['precision'])}
- CoT 新增报警：{incremental['cot_only_alerts']}；新增抓到错误={incremental['additional_true_positives']}；新增误报={incremental['additional_false_positives']}

CoT 监控器是确定性、可解释的第一版，只检查显式数值方程、共享操作数上的运算/结果冲突、原题算术错误，以及无关信息版本对新增数字的使用。它允许不同步骤和不同等价解法；没有可比较关系时返回 `unknown`。人工核验表中的判断列仍为空，必须由人工填写后才能报告监控器本身的语义判定准确率。
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--monitor-results", type=Path, required=True)
    parser.add_argument("--gold", type=Path, required=True)
    parser.add_argument("--generations", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    evaluated, metrics, audit = evaluate(
        read_jsonl(args.monitor_results),
        read_jsonl(args.gold),
        read_jsonl(args.generations),
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    with (args.output_dir / "evaluated_monitor_results.jsonl").open(
        "w", encoding="utf-8"
    ) as handle:
        for row in evaluated:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    (args.output_dir / "monitor_metrics.json").write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (args.output_dir / "monitor_summary.md").write_text(
        render_summary(metrics), encoding="utf-8"
    )
    write_csv(args.output_dir / "human_audit.csv", audit)
    print(json.dumps(metrics, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
