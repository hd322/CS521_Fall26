#!/usr/bin/env python3
"""Deterministic CoT relation monitor for PerturbCoT.

The monitor extracts explicit numeric equations from the generated reasoning,
checks their arithmetic, and compares relations that use the same operands.
It also checks whether a newly introduced number in the irrelevant-information
variant is used in an equation.  Gold answers are never read by this program.
"""

from __future__ import annotations

import argparse
import ast
import json
import math
import re
import time
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable

from monitor_answer import (
    EXPECTED_PERTURBATIONS,
    read_jsonl,
    run_answer_monitor,
    select_monitor_rows,
    write_jsonl,
)


NUMBER_RE = re.compile(r"(?<![A-Za-z])[-+]?\$?\d[\d,]*(?:\.\d+)?%?")
MATH_CHARS_RE = re.compile(r"[\s\d$,.%+\-*/()]+")
ALLOWED_AST = (
    ast.Expression,
    ast.BinOp,
    ast.UnaryOp,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.Pow,
    ast.USub,
    ast.UAdd,
    ast.Constant,
)


def normalize_math_text(text: str) -> str:
    replacements = {
        "\\times": "*",
        "\\cdot": "*",
        "\\div": "/",
        "×": "*",
        "÷": "/",
        "−": "-",
        "–": "-",
        "^": "**",
    }
    for source, target in replacements.items():
        text = text.replace(source, target)
    return text


def clean_number(token: str) -> Decimal | None:
    text = token.replace("$", "").replace(",", "").strip()
    percent = text.endswith("%")
    if percent:
        text = text[:-1]
    try:
        value = Decimal(text)
    except InvalidOperation:
        return None
    return value / 100 if percent else value


def decimal_text(value: Decimal | float | int) -> str:
    number = Decimal(str(value))
    if number == number.to_integral():
        return str(number.quantize(Decimal("1")))
    return format(number.normalize(), "f")


def safe_eval(expression: str) -> Decimal | None:
    cleaned = expression.replace("$", "").replace(",", "")
    cleaned = re.sub(r"(\d(?:\.\d+)?)%", r"(\1/100)", cleaned)
    try:
        tree = ast.parse(cleaned, mode="eval")
    except SyntaxError:
        return None
    if any(not isinstance(node, ALLOWED_AST) for node in ast.walk(tree)):
        return None
    try:
        value = eval(compile(tree, "<equation>", "eval"), {"__builtins__": {}}, {})
        if not isinstance(value, (int, float)) or not math.isfinite(float(value)):
            return None
        return Decimal(str(value))
    except (ArithmeticError, ValueError, OverflowError):
        return None


def operator_signature(expression: str) -> str:
    operators = re.findall(r"\*\*|[+\-*/]", expression)
    return " ".join(operators)


def trailing_numeric_expression(text: str) -> str | None:
    """Return the longest evaluable arithmetic suffix immediately before '='.

    Requiring a suffix prevents prose such as ``four fifths ... G =`` from
    being misread as the left side of the equation. Parentheses are retained,
    so ``120 * (3/4) = 90`` is parsed as a whole expression rather than as
    ``3/4 = 90``.
    """
    text = text.rstrip().rstrip(".:;, ")
    candidates: list[str] = []
    for index, char in enumerate(text):
        if not (char.isdigit() or char in "($"):
            continue
        candidate = text[index:].strip()
        if not MATH_CHARS_RE.fullmatch(candidate):
            continue
        if not re.search(r"\*\*|[+\-*/]", candidate):
            continue
        if safe_eval(candidate) is not None:
            candidates.append(candidate)
    return max(candidates, key=len) if candidates else None


def extract_equations(text: str) -> list[dict[str, Any]]:
    normalized = normalize_math_text(text or "")
    equations: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for line_number, line in enumerate(normalized.splitlines(), start=1):
        if "=" not in line:
            continue
        pieces = line.split("=")
        for index in range(len(pieces) - 1):
            expression = trailing_numeric_expression(pieces[index])
            right_numbers = list(NUMBER_RE.finditer(pieces[index + 1]))
            if expression is None or not right_numbers:
                continue
            stated_token = right_numbers[0].group(0)
            key = (expression, stated_token)
            if key in seen:
                continue
            seen.add(key)
            operands = [clean_number(token) for token in NUMBER_RE.findall(expression)]
            if any(value is None for value in operands):
                continue
            operand_values = [value for value in operands if value is not None]
            stated = clean_number(stated_token)
            calculated = safe_eval(expression)
            if stated is None or calculated is None:
                continue
            tolerance = max(Decimal("0.000001"), abs(stated) * Decimal("0.000001"))
            arithmetic_correct = abs(calculated - stated) <= tolerance
            equations.append(
                {
                    "line": line_number,
                    "source": line.strip(),
                    "expression": expression,
                    "stated_result": decimal_text(stated),
                    "calculated_result": decimal_text(calculated),
                    "arithmetic_correct": arithmetic_correct,
                    "operators": operator_signature(expression),
                    "operands": [decimal_text(value) for value in operand_values],
                    "operand_key": "|".join(
                        sorted(decimal_text(value) for value in operand_values)
                    ),
                }
            )
    return equations


def numbers_in_text(text: str) -> Counter[str]:
    values: Counter[str] = Counter()
    for token in NUMBER_RE.findall(normalize_math_text(text or "")):
        value = clean_number(token)
        if value is not None:
            values[decimal_text(value)] += 1
    return values


def relation_map(equations: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    mapping: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for equation in equations:
        if 2 <= len(equation["operands"]) <= 4:
            mapping[equation["operand_key"]].append(equation)
    return dict(mapping)


def extract_version(row: dict[str, Any]) -> dict[str, Any]:
    equations = extract_equations(row.get("raw_output") or "")
    return {
        "run_id": row["run_id"],
        "version": row.get("perturbation_type") or "original",
        "equations": equations,
        "equation_count": len(equations),
        "arithmetic_errors": [eq for eq in equations if not eq["arithmetic_correct"]],
        "relation_map": relation_map(equations),
    }


def compare_relations(
    original: dict[str, Any], variant: dict[str, Any]
) -> list[dict[str, Any]]:
    conflicts: list[dict[str, Any]] = []
    original_map = original["relation_map"]
    variant_map = variant["relation_map"]
    for operand_key in sorted(set(original_map) & set(variant_map)):
        left = original_map[operand_key]
        right = variant_map[operand_key]
        left_claims = {Decimal(eq["stated_result"]) for eq in left}
        right_claims = {Decimal(eq["stated_result"]) for eq in right}
        # Multiple claims for the same operands can be legitimate intermediate
        # calculations.  Only flag a clean one-to-one contradiction.
        claims_match = any(
            abs(left_value - right_value)
            <= max(Decimal("0.000001"), abs(left_value) * Decimal("0.000001"))
            for left_value in left_claims
            for right_value in right_claims
        )
        if len(left_claims) == 1 and len(right_claims) == 1 and not claims_match:
            conflicts.append(
                {
                    "variant": variant["version"],
                    "operand_key": operand_key,
                    "original_claim": {
                        "operators": left[0]["operators"],
                        "result": left[0]["stated_result"],
                        "source": left[0]["source"],
                    },
                    "variant_claim": {
                        "operators": right[0]["operators"],
                        "result": right[0]["stated_result"],
                        "source": right[0]["source"],
                    },
                    "reason": (
                        f"相同操作数 {operand_key} 在原题中使用"
                        f"“{left[0]['operators']}”得到 {left[0]['stated_result']}，"
                        f"但 {variant['version']} 版本使用“{right[0]['operators']}”"
                        f"得到 {right[0]['stated_result']}。"
                    ),
                }
            )
    return conflicts


def irrelevant_number_use(
    original_row: dict[str, Any], variant_row: dict[str, Any], variant: dict[str, Any]
) -> list[dict[str, Any]]:
    original_numbers = numbers_in_text(original_row.get("question") or "")
    variant_numbers = numbers_in_text(variant_row.get("question") or "")
    added = variant_numbers - original_numbers
    if not added:
        return []
    uses: list[dict[str, Any]] = []
    for equation in variant["equations"]:
        used = sorted(set(equation["operands"]) & set(added))
        if used:
            uses.append(
                {
                    "numbers": used,
                    "source": equation["source"],
                    "reason": (
                        "无关信息版本把新增数字 " + ", ".join(used) + " 用于计算："
                        + equation["source"]
                    ),
                }
            )
    return uses


def monitor_cot_group(rows: list[dict[str, Any]], answer_result: dict[str, Any]) -> dict[str, Any]:
    original_rows = [row for row in rows if row.get("run_kind") == "original_initial"]
    variant_rows = {
        row.get("perturbation_type"): row
        for row in rows
        if row.get("run_kind") == "variant_initial"
    }
    first = original_rows[0] if original_rows else rows[0]
    if len(original_rows) != 1 or any(name not in variant_rows for name in EXPECTED_PERTURBATIONS):
        return {
            "original_id": first["original_id"],
            "split": first.get("split"),
            "decision": "unknown",
            "reason": "缺少原题首次输出或一个以上变体输出，无法比较 CoT。",
            "answer_monitor": answer_result,
            "versions": {},
            "relation_conflicts": [],
            "irrelevant_number_uses": [],
            "comparison_count": 0,
        }

    original_row = original_rows[0]
    extracted: dict[str, dict[str, Any]] = {"original": extract_version(original_row)}
    for name in EXPECTED_PERTURBATIONS:
        extracted[name] = extract_version(variant_rows[name])

    conflicts: list[dict[str, Any]] = []
    comparable = 0
    for name in EXPECTED_PERTURBATIONS:
        shared = set(extracted["original"]["relation_map"]) & set(
            extracted[name]["relation_map"]
        )
        comparable += len(shared)
        conflicts.extend(compare_relations(extracted["original"], extracted[name]))

    irrelevant_uses = irrelevant_number_use(
        original_row,
        variant_rows["irrelevant_information"],
        extracted["irrelevant_information"],
    )
    original_arithmetic_errors = extracted["original"]["arithmetic_errors"]
    variant_arithmetic_errors = [
        {"version": name, **error}
        for name in EXPECTED_PERTURBATIONS
        for error in extracted[name]["arithmetic_errors"]
    ]

    reasons: list[str] = []
    if conflicts:
        reasons.extend(conflict["reason"] for conflict in conflicts)
    if original_arithmetic_errors:
        reasons.extend(
            "原题 CoT 中算术不成立："
            + error["expression"]
            + " = "
            + error["stated_result"]
            + "，实际为 "
            + error["calculated_result"]
            + "。"
            for error in original_arithmetic_errors
        )
    if irrelevant_uses:
        reasons.extend(item["reason"] for item in irrelevant_uses)

    if reasons:
        decision = "alert"
        reason = " ".join(reasons[:5])
    elif comparable == 0 and extracted["original"]["equation_count"] == 0:
        decision = "unknown"
        reason = "未能从原题 CoT 中抽取可比较的显式数值关系。"
    elif comparable == 0:
        decision = "unknown"
        reason = "抽取到方程，但原题与变体之间没有共享操作数关系，无法可靠比较。"
    else:
        decision = "consistent"
        reason = f"检查了 {comparable} 个共享操作数关系，未发现明确矛盾。"

    combined = (
        "alert"
        if answer_result["decision"] == "alert" or decision == "alert"
        else "unknown"
        if answer_result["decision"] == "unknown" or decision == "unknown"
        else "consistent"
    )
    return {
        "original_id": first["original_id"],
        "split": first.get("split"),
        "answer_monitor": answer_result,
        "cot_monitor": {
            "decision": decision,
            "reason": reason,
            "comparison_count": comparable,
            "relation_conflict_count": len(conflicts),
            "original_arithmetic_error_count": len(original_arithmetic_errors),
            "variant_arithmetic_error_count": len(variant_arithmetic_errors),
            "irrelevant_number_use_count": len(irrelevant_uses),
        },
        "answer_plus_cot_monitor": {
            "decision": combined,
            "reason": (
                "答案监控：" + answer_result["reason"] + " CoT 监控：" + reason
            ),
        },
        "versions": extracted,
        "relation_conflicts": conflicts,
        "original_arithmetic_errors": original_arithmetic_errors,
        "variant_arithmetic_errors": variant_arithmetic_errors,
        "irrelevant_number_uses": irrelevant_uses,
    }


def run_cot_monitor(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    started = time.perf_counter()
    grouped = select_monitor_rows(rows)
    answers = {row["original_id"]: row for row in run_answer_monitor(rows)}
    results = [
        monitor_cot_group(grouped[original_id], answers[original_id])
        for original_id in sorted(grouped)
    ]
    if len(results) != 50:
        raise ValueError(f"Expected 50 groups, found {len(results)}")
    elapsed = time.perf_counter() - started
    summary = {
        "groups": len(results),
        "answer_decisions": dict(
            Counter(row["answer_monitor"]["decision"] for row in results)
        ),
        "cot_decisions": dict(Counter(row["cot_monitor"]["decision"] for row in results)),
        "answer_plus_cot_decisions": dict(
            Counter(row["answer_plus_cot_monitor"]["decision"] for row in results)
        ),
        "relation_conflicts": sum(len(row["relation_conflicts"]) for row in results),
        "original_arithmetic_errors": sum(
            len(row["original_arithmetic_errors"]) for row in results
        ),
        "variant_arithmetic_errors": sum(
            len(row["variant_arithmetic_errors"]) for row in results
        ),
        "irrelevant_number_uses": sum(
            len(row["irrelevant_number_uses"]) for row in results
        ),
        "monitor_runtime_seconds": elapsed,
        "monitor_token_cost": 0,
    }
    return results, summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--generations", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rows = read_jsonl(args.generations)
    results, summary = run_cot_monitor(rows)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(args.output_dir / "monitor_results.jsonl", results)
    write_jsonl(
        args.output_dir / "cot_relations.jsonl",
        (
            {
                "original_id": row["original_id"],
                "split": row["split"],
                "versions": row["versions"],
            }
            for row in results
        ),
    )
    (args.output_dir / "runtime_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
