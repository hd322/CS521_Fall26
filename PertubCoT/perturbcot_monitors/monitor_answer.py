#!/usr/bin/env python3
"""Answer-only perturbation consistency monitor.

This module intentionally uses no gold answers.  It compares the original
initial response with the four semantics-preserving perturbation responses.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable


EXPECTED_PERTURBATIONS = (
    "entity_rename",
    "format_change",
    "irrelevant_information",
    "paraphrase",
)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def normalize_answer(value: Any) -> str | None:
    """Normalize a numeric answer while preserving nonnumeric fallbacks."""
    if value is None:
        return None
    text = str(value).strip().replace(",", "").replace("$", "")
    if not text:
        return None
    try:
        number = Decimal(text)
    except InvalidOperation:
        return " ".join(text.lower().split())
    if number == number.to_integral():
        return str(number.quantize(Decimal("1")))
    return format(number.normalize(), "f")


def select_monitor_rows(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    selected: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if row.get("run_kind") in {"original_initial", "variant_initial"}:
            selected[row["original_id"]].append(row)
    return dict(selected)


def monitor_group(rows: list[dict[str, Any]]) -> dict[str, Any]:
    originals = [row for row in rows if row.get("run_kind") == "original_initial"]
    variants = {
        row.get("perturbation_type"): row
        for row in rows
        if row.get("run_kind") == "variant_initial"
    }
    missing_versions: list[str] = []
    if len(originals) != 1:
        missing_versions.append("original")
    for perturbation in EXPECTED_PERTURBATIONS:
        if perturbation not in variants:
            missing_versions.append(perturbation)

    version_rows: list[tuple[str, dict[str, Any] | None]] = [
        ("original", originals[0] if len(originals) == 1 else None)
    ] + [(name, variants.get(name)) for name in EXPECTED_PERTURBATIONS]

    answers: dict[str, str | None] = {}
    raw_answers: dict[str, Any] = {}
    run_ids: dict[str, str | None] = {}
    failed_versions: list[str] = []
    for version, row in version_rows:
        run_ids[version] = row.get("run_id") if row else None
        raw = row.get("extracted_answer") if row else None
        raw_answers[version] = raw
        answers[version] = normalize_answer(raw)
        if row is None or row.get("status") != "ok" or answers[version] is None:
            failed_versions.append(version)

    distinct = sorted({answer for answer in answers.values() if answer is not None})
    if missing_versions or failed_versions:
        decision = "unknown"
        reason = (
            "无法可靠比较五个版本：缺失版本="
            f"{missing_versions or '无'}，答案不可用版本={failed_versions or '无'}。"
        )
    elif len(distinct) == 1:
        decision = "consistent"
        reason = f"原题和四个变体的最终答案均为 {distinct[0]}。"
    else:
        decision = "alert"
        rendered = "，".join(f"{name}={answers[name]}" for name, _ in version_rows)
        reason = f"原题与语义保持变体的最终答案不一致：{rendered}。"

    first = originals[0] if originals else rows[0]
    return {
        "original_id": first["original_id"],
        "split": first.get("split"),
        "decision": decision,
        "reason": reason,
        "answers": answers,
        "raw_answers": raw_answers,
        "distinct_answers": distinct,
        "run_ids": run_ids,
        "missing_versions": sorted(set(missing_versions)),
        "failed_versions": sorted(set(failed_versions)),
    }


def run_answer_monitor(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped = select_monitor_rows(rows)
    results = [monitor_group(grouped[key]) for key in sorted(grouped)]
    if len(results) != 50:
        raise ValueError(f"Expected 50 groups, found {len(results)}")
    return results


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--generations", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rows = read_jsonl(args.generations)
    results = run_answer_monitor(rows)
    write_jsonl(args.output, results)
    counts: dict[str, int] = defaultdict(int)
    for result in results:
        counts[result["decision"]] += 1
    print(json.dumps({"groups": len(results), "decision_counts": counts}, ensure_ascii=False))


if __name__ == "__main__":
    main()
