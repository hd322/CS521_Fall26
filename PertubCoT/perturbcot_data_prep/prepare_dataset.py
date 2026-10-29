#!/usr/bin/env python3
"""Prepare a deterministic GSM8K pilot dataset. Python 3.9+, standard library only."""
import argparse
import hashlib
import json
import re
import unicodedata
import urllib.request
from collections import Counter
from decimal import Decimal
from pathlib import Path

BASE = Path(__file__).resolve().parent
RUNTIME_FIELDS = {"original_id", "question", "split", "group_id"}


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def question_group(question):
    normalized = " ".join(unicodedata.normalize("NFKC", question).casefold().split())
    return sha256(normalized.encode("utf-8"))


def extract_gold(solution):
    """Parse only the terminal #### label; never guess from intermediate numbers."""
    if solution.count("####") != 1:
        raise ValueError("Expected exactly one #### answer marker")
    raw = solution.split("####", 1)[1].strip()
    if not re.fullmatch(r"[+-]?(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d+)?", raw):
        raise ValueError("Invalid final numeric answer: " + repr(raw))
    value = Decimal(raw.replace(",", ""))
    if value == 0:
        return "0"
    normalized = format(value, "f")
    return normalized.rstrip("0").rstrip(".") if "." in normalized else normalized


def rank(seed, namespace, group_id):
    return sha256(f"{seed}|{namespace}|{group_id}".encode("utf-8"))


def select_rows(rows, seed, sample_size, dev_size):
    if not 0 < dev_size < sample_size:
        raise ValueError("Require 0 < dev_size < sample_size")
    unique = {}
    for row in rows:
        unique.setdefault(row["group_id"], row)
    if sample_size > len(unique):
        raise ValueError("Insufficient unique question groups")
    selected = sorted(unique.values(), key=lambda r: (rank(seed, "sample", r["group_id"]), r["original_id"]))[:sample_size]
    dev_groups = {
        r["group_id"] for r in sorted(selected, key=lambda r: rank(seed, "split", r["group_id"]))[:dev_size]
    }
    return sorted(
        [dict(r, split="dev" if r["group_id"] in dev_groups else "test") for r in selected],
        key=lambda r: r["original_id"],
    )


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")


def read_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def validate_outputs(out, source_rows, cfg):
    originals = read_jsonl(out / "offline_eval/originals.jsonl")
    runtime = read_jsonl(out / "runtime/questions.jsonl")
    gold = read_jsonl(out / "offline_eval/gold.jsonl")
    dev = read_jsonl(out / "runtime/dev.jsonl")
    test = read_jsonl(out / "runtime/test.jsonl")
    source_by_id = {r["original_id"]: r for r in source_rows}
    ids = {r["original_id"] for r in originals}
    checks = {
        "sample_count": len(originals) == cfg["sample_size"],
        "unique_original_ids": len(ids) == len(originals),
        "unique_normalized_questions": len({r["group_id"] for r in originals}) == len(originals),
        "split_counts": len(dev) == cfg["dev_size"] and len(test) == cfg["sample_size"] - cfg["dev_size"],
        "no_group_overlap": not ({r["group_id"] for r in dev} & {r["group_id"] for r in test}),
        "split_partition": sorted(dev + test, key=lambda r: r["original_id"]) == runtime,
        "runtime_field_allowlist": all(set(r) == RUNTIME_FIELDS for r in runtime + dev + test),
        "paired_runtime_and_gold_ids": len(runtime) == len(gold) == len(originals) and {r["original_id"] for r in runtime} == {r["original_id"] for r in gold} == ids,
        "runtime_matches_originals": runtime == [{k: r[k] for k in ("original_id", "question", "split", "group_id")} for r in originals],
        "gold_matches_originals": gold == [{k: r[k] for k in ("original_id", "split", "gold_answer")} for r in originals],
        "questions_unchanged": all(r["question"] == source_by_id[r["original_id"]]["question"] for r in originals),
        "solutions_unchanged": all(r["source_solution"] == source_by_id[r["original_id"]]["source_solution"] for r in originals),
        "gold_extraction_valid": all(r["gold_answer"] == extract_gold(r["source_solution"]) for r in originals),
        "source_positions_valid": all(r["source_row_index"] == source_by_id[r["original_id"]]["source_row_index"] for r in originals),
        "selection_reproduces": originals == select_rows(source_rows, cfg["seed"], cfg["sample_size"], cfg["dev_size"]),
    }
    report = {
        "status": "passed" if all(checks.values()) else "failed",
        "checks": checks,
        "source_rows": len(source_rows),
        "selected_originals": len(originals),
        "split_counts": dict(sorted(Counter(r["split"] for r in originals).items())),
        "variants_generated": 0,
        "human_reviewed_originals": 0,
        "limitations": [
            "These are automated structural checks, not human verification of mathematical correctness.",
            "GSM8K supplies no template IDs; normalized exact-duplicate grouping does not guarantee semantic-template separation.",
            "No perturbation variants or model answers have been generated.",
        ],
    }
    write_json(out / "validation_report.json", report)
    if report["status"] != "passed":
        raise ValueError("Output validation failed: " + str(checks))
    return report


def prepare(config_path, output_dir=None, download=False):
    cfg = json.loads(config_path.read_text(encoding="utf-8"))
    if cfg["selection_algorithm"] != "sha256_rank_v1" or cfg["grouping"] != "normalized_question_sha256":
        raise ValueError("Unsupported sampling or grouping algorithm")
    source = config_path.parent / cfg["source_file"]
    if download:
        with urllib.request.urlopen(cfg["source_url"], timeout=60) as response:
            payload = response.read()
    else:
        payload = source.read_bytes()
    if sha256(payload) != cfg["source_sha256"]:
        raise ValueError("Source SHA-256 mismatch; refusing to use changed data")
    if download:
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_bytes(payload)
    raw_rows = [json.loads(line) for line in payload.decode("utf-8").splitlines()]
    if len(raw_rows) != cfg["expected_source_rows"]:
        raise ValueError("Unexpected source row count")
    rows = []
    for index, row in enumerate(raw_rows):
        question, solution = row["question"], row["answer"]
        if not isinstance(question, str) or not question.strip() or not isinstance(solution, str):
            raise ValueError(f"Invalid source row {index}")
        rows.append({
            "original_id": f"gsm8k_{cfg['upstream_split']}_{index:04d}",
            "question": question,
            "gold_answer": extract_gold(solution),
            "source_solution": solution,
            "group_id": question_group(question),
            "source_dataset": cfg["dataset"],
            "source_split": cfg["upstream_split"],
            "source_row_index": index,
            "template_id": None,
            "verification_status": "source_imported_auto_validated",
            "human_review_status": "not_reviewed",
        })
    selected = select_rows(rows, cfg["seed"], cfg["sample_size"], cfg["dev_size"])
    out = output_dir or config_path.parent / "data"
    runtime = [{k: r[k] for k in ("original_id", "question", "split", "group_id")} for r in selected]
    write_jsonl(out / "offline_eval/originals.jsonl", selected)
    write_jsonl(out / "offline_eval/gold.jsonl", [{k: r[k] for k in ("original_id", "split", "gold_answer")} for r in selected])
    write_jsonl(out / "runtime/questions.jsonl", runtime)
    for split in ("dev", "test"):
        write_jsonl(out / f"runtime/{split}.jsonl", [r for r in runtime if r["split"] == split])
    report = validate_outputs(out, rows, cfg)
    preview = ["# GSM8K 50 题离线核对表", "", "包含标准答案，仅用于离线核对，不可作为运行时提示词输入。原题保持英文；未人工复核，尚无扰动变体。", ""]
    for r in selected:
        preview.extend([f"## {r['original_id']} · {r['split']}", "", r["question"], "", f"**标准答案：** {r['gold_answer']}", ""])
    (out / "offline_eval/preview.md").write_text("\n".join(preview), encoding="utf-8")
    files = ["offline_eval/originals.jsonl", "offline_eval/gold.jsonl", "offline_eval/preview.md", "runtime/questions.jsonl", "runtime/dev.jsonl", "runtime/test.jsonl", "validation_report.json"]
    write_json(out / "manifest.json", {
        "config": cfg,
        "config_sha256": sha256(config_path.read_bytes()),
        "script_sha256": sha256(Path(__file__).read_bytes()),
        "source_rows": len(rows),
        "unique_source_groups": len({r["group_id"] for r in rows}),
        "selection_note": "Rank unique normalized-question groups by SHA256(seed|sample|group_id), take first N; independently rank selected groups with namespace split, assign first dev_size to dev. Keep lowest source row for exact duplicates.",
        "id_note": "Locally assigned ID; numeric suffix is the zero-based row index in the pinned official split.",
        "selected_ids": {s: [r["original_id"] for r in selected if r["split"] == s] for s in ("dev", "test")},
        "output_sha256": {f: sha256((out / f).read_bytes()) for f in files},
    })
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=BASE / "config.json")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--download", action="store_true", help="Fetch pinned source again and verify its SHA-256")
    args = parser.parse_args()
    print(json.dumps(prepare(args.config.resolve(), args.output_dir, args.download), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
