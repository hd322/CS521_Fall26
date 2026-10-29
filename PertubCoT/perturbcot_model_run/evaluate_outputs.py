#!/usr/bin/env python3
"""Join runtime generations with offline gold data and summarize the pilot run."""
import argparse
import json
import math
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation
from fractions import Fraction
from pathlib import Path


BASE = Path(__file__).resolve().parent


def read_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def normalize_number(value):
    if value is None:
        return None
    text = str(value).strip().replace("$", "").replace(",", "")
    percent = text.endswith("%")
    if percent:
        text = text[:-1]
    try:
        if "/" in text:
            fraction = Fraction(text)
            number = Decimal(fraction.numerator) / Decimal(fraction.denominator)
        else:
            number = Decimal(text)
    except (InvalidOperation, ValueError, ZeroDivisionError):
        return text.lower()
    normalized = format(number, "f") if number else "0"
    if "." in normalized:
        normalized = normalized.rstrip("0").rstrip(".")
    return normalized + ("%" if percent else "")


def wilson(successes, total, z=1.959963984540054):
    if total == 0:
        return None
    p = successes / total
    denominator = 1 + z * z / total
    center = (p + z * z / (2 * total)) / denominator
    half = z * math.sqrt((p * (1 - p) + z * z / (4 * total)) / total) / denominator
    return {"low": center - half, "high": center + half}


def accuracy_block(rows):
    total = len(rows)
    correct = sum(row["is_correct"] for row in rows)
    return {
        "correct": correct,
        "total": total,
        "accuracy": correct / total if total else None,
        "wilson_95": wilson(correct, total),
    }


def majority_answer(rows):
    answers = [row["extracted_answer_normalized"] for row in rows if row["extracted_answer_normalized"] is not None]
    if not answers:
        return None, True
    counts = Counter(answers)
    top_count = max(counts.values())
    winners = sorted(answer for answer, count in counts.items() if count == top_count)
    return (winners[0] if len(winners) == 1 else None), len(winners) != 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--generations", type=Path, required=True)
    parser.add_argument(
        "--gold",
        type=Path,
        default=BASE.parent / "perturbcot_data_prep" / "data" / "offline_eval" / "gold.jsonl",
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    generations = read_jsonl(args.generations)
    gold = {row["original_id"]: normalize_number(row["gold_answer"]) for row in read_jsonl(args.gold)}
    if len(generations) != 450:
        raise ValueError(f"Expected 450 generation rows, got {len(generations)}")
    run_ids = [row["run_id"] for row in generations]
    if len(set(run_ids)) != len(run_ids):
        raise ValueError("Duplicate run_id values in generations")
    missing_gold = sorted({row["original_id"] for row in generations} - set(gold))
    if missing_gold:
        raise ValueError(f"Missing gold answers for: {missing_gold}")

    evaluated = []
    for row in generations:
        prediction = normalize_number(row.get("extracted_answer"))
        expected = gold[row["original_id"]]
        evaluated.append({
            **row,
            "extracted_answer_normalized": prediction,
            "gold_answer": expected,
            "is_correct": prediction is not None and prediction == expected,
        })

    by_original = defaultdict(list)
    for row in evaluated:
        by_original[row["original_id"]].append(row)

    baseline = [row for row in evaluated if row["run_kind"] == "original_initial"]
    repeats = [row for row in evaluated if row["version_type"] == "original"]
    variants = [row for row in evaluated if row["version_type"] == "variant"]
    perturbation_metrics = {}
    for perturbation in sorted({row["perturbation_type"] for row in variants}):
        subset = [row for row in variants if row["perturbation_type"] == perturbation]
        perturbation_metrics[perturbation] = accuracy_block(subset)

    vote_correct = 0
    vote_ties_or_missing = 0
    stochastic_stable = 0
    answer_monitor_alerts = 0
    monitor_tp = monitor_fp = monitor_fn = monitor_tn = 0
    variant_matches_original = 0
    variant_comparisons = 0
    group_records = []
    for original_id, rows in sorted(by_original.items()):
        original_rows = sorted(
            (row for row in rows if row["version_type"] == "original"),
            key=lambda row: row["repeat_index"],
        )
        variant_rows = sorted(
            (row for row in rows if row["version_type"] == "variant"),
            key=lambda row: row["perturbation_type"],
        )
        initial = original_rows[0]
        vote, tie = majority_answer(original_rows)
        vote_ties_or_missing += int(tie)
        vote_correct += int(vote is not None and vote == gold[original_id])
        repeat_answers = [row["extracted_answer_normalized"] for row in original_rows]
        repeat_stable = len(set(repeat_answers)) == 1 and repeat_answers[0] is not None
        stochastic_stable += int(repeat_stable)

        monitored_rows = [initial, *variant_rows]
        monitored_answers = [row["extracted_answer_normalized"] for row in monitored_rows]
        alert = None in monitored_answers or len(set(monitored_answers)) > 1
        answer_monitor_alerts += int(alert)
        if alert and not initial["is_correct"]:
            monitor_tp += 1
        elif alert and initial["is_correct"]:
            monitor_fp += 1
        elif not alert and not initial["is_correct"]:
            monitor_fn += 1
        else:
            monitor_tn += 1
        matches = sum(
            row["extracted_answer_normalized"] is not None
            and row["extracted_answer_normalized"] == initial["extracted_answer_normalized"]
            for row in variant_rows
        )
        variant_matches_original += matches
        variant_comparisons += len(variant_rows)
        group_records.append({
            "original_id": original_id,
            "gold_answer": gold[original_id],
            "original_initial_answer": initial["extracted_answer_normalized"],
            "original_initial_correct": initial["is_correct"],
            "repeat_answers": repeat_answers,
            "repeat_stable": repeat_stable,
            "repeat_majority_answer": vote,
            "repeat_majority_correct": vote is not None and vote == gold[original_id],
            "answer_monitor_alert": alert,
            "variant_answers": {
                row["perturbation_type"]: row["extracted_answer_normalized"] for row in variant_rows
            },
        })

    status_counts = Counter(row.get("status") for row in evaluated)
    extraction_success = sum(bool(row.get("answer_extraction_success")) for row in evaluated)
    truncated = sum(bool(row.get("truncated")) for row in evaluated)
    total_input_tokens = sum(row.get("input_tokens") or 0 for row in evaluated)
    total_output_tokens = sum(row.get("output_tokens") or 0 for row in evaluated)
    total_latency = sum(row.get("latency_seconds") or 0 for row in evaluated)
    summary = {
        "records": len(evaluated),
        "unique_run_ids": len(set(run_ids)),
        "unique_originals": len(by_original),
        "status_counts": dict(status_counts),
        "answer_extraction": {
            "success": extraction_success,
            "failed": len(evaluated) - extraction_success,
            "success_rate": extraction_success / len(evaluated),
        },
        "truncated": truncated,
        "accuracy": {
            "original_initial": accuracy_block(baseline),
            "all_original_generations": accuracy_block(repeats),
            "all_variants": accuracy_block(variants),
            "by_perturbation": perturbation_metrics,
            "five_sample_majority": {
                "correct": vote_correct,
                "total": len(by_original),
                "accuracy": vote_correct / len(by_original),
                "ties_or_missing": vote_ties_or_missing,
                "wilson_95": wilson(vote_correct, len(by_original)),
            },
        },
        "stability": {
            "original_repeat_groups_fully_stable": stochastic_stable,
            "original_repeat_groups_total": len(by_original),
            "original_repeat_stability_rate": stochastic_stable / len(by_original),
            "variant_answers_matching_original_initial": variant_matches_original,
            "variant_comparisons": variant_comparisons,
            "variant_match_rate": variant_matches_original / variant_comparisons,
            "answer_only_monitor_alert_groups": answer_monitor_alerts,
            "answer_only_monitor_alert_rate": answer_monitor_alerts / len(by_original),
            "answer_only_monitor_detection": {
                "true_positive": monitor_tp,
                "false_positive": monitor_fp,
                "false_negative": monitor_fn,
                "true_negative": monitor_tn,
                "precision": monitor_tp / (monitor_tp + monitor_fp) if monitor_tp + monitor_fp else None,
                "recall": monitor_tp / (monitor_tp + monitor_fn) if monitor_tp + monitor_fn else None,
                "false_positive_rate": monitor_fp / (monitor_fp + monitor_tn) if monitor_fp + monitor_tn else None,
            },
        },
        "cost": {
            "input_tokens": total_input_tokens,
            "output_tokens": total_output_tokens,
            "total_tokens": total_input_tokens + total_output_tokens,
            "summed_generation_latency_seconds": total_latency,
            "mean_generation_latency_seconds": total_latency / len(evaluated),
        },
    }

    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "evaluated_generations.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in evaluated), encoding="utf-8"
    )
    (args.output_dir / "group_summary.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in group_records), encoding="utf-8"
    )
    write_json(args.output_dir / "metrics.json", summary)
    baseline_metrics = summary["accuracy"]["original_initial"]
    variant_metrics = summary["accuracy"]["all_variants"]
    vote_metrics = summary["accuracy"]["five_sample_majority"]
    report = f"""# Qwen2.5-Math-1.5B pilot run summary

- Records: {summary['records']} ({summary['unique_originals']} original problems)
- Successful answer extraction: {extraction_success}/{len(evaluated)}
- Truncated generations: {truncated}
- Original initial accuracy: {baseline_metrics['correct']}/{baseline_metrics['total']} ({baseline_metrics['accuracy']:.1%})
- Variant accuracy: {variant_metrics['correct']}/{variant_metrics['total']} ({variant_metrics['accuracy']:.1%})
- Five-sample majority accuracy: {vote_metrics['correct']}/{vote_metrics['total']} ({vote_metrics['accuracy']:.1%})
- Original repeat groups with one stable answer: {stochastic_stable}/{len(by_original)} ({stochastic_stable / len(by_original):.1%})
- Variant answers matching the original initial answer: {variant_matches_original}/{variant_comparisons} ({variant_matches_original / variant_comparisons:.1%})
- Answer-only monitor alerts: {answer_monitor_alerts}/{len(by_original)} ({answer_monitor_alerts / len(by_original):.1%})
- Total tokens: {total_input_tokens + total_output_tokens:,} ({total_input_tokens:,} input + {total_output_tokens:,} output)
- Summed generation latency: {total_latency:.1f} seconds

The answer-only alert treats a group as unstable when the original initial answer and its four perturbation answers are not all present and numerically identical. Standard answers are joined only in this offline evaluation step.
"""
    (args.output_dir / "run_summary.md").write_text(report, encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
