#!/usr/bin/env python3
"""Generate and validate four answer-preserving variants for 50 GSM8K questions."""
import argparse
import csv
import hashlib
import io
import json
import re
from collections import Counter
from pathlib import Path

from variant_specs import ENTITY_REPLACEMENTS, IRRELEVANT_SENTENCE, PARAPHRASED_TAILS

BASE = Path(__file__).resolve().parent
NUMBER_RE = re.compile(r"\d+(?:,\d{3})*(?:\.\d+)?%?")
RUNTIME_FIELDS = {
    "variant_id", "original_id", "group_id", "split", "perturbation_type",
    "original_question", "variant_question", "verification_status"
}


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def read_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


def sentence_spans(text):
    """Split on whitespace following terminal punctuation; preserve sentence text."""
    starts = [0] + [m.end() for m in re.finditer(r"(?<=[.!?])\s+", text)]
    spans = []
    for start, end in zip(starts, starts[1:] + [len(text)]):
        sentence = text[start:end].strip()
        if sentence:
            spans.append(sentence)
    return spans


def paraphrase(original_id, question):
    sentences = sentence_spans(question)
    if not sentences:
        raise ValueError(f"No sentences for {original_id}")
    old_tail = sentences[-1]
    new_tail = PARAPHRASED_TAILS[original_id]
    start = question.rfind(old_tail)
    if start < 0 or question[start:] != old_tail:
        raise ValueError(f"Could not isolate final question for {original_id}")
    return question[:start] + new_tail, {"original_tail": old_tail, "replacement_tail": new_tail}


def rename_entities(original_id, question):
    variant = question
    applied = []
    for source, target in ENTITY_REPLACEMENTS[original_id]:
        count = variant.count(source)
        if count == 0:
            raise ValueError(f"Missing entity token {source!r} in {original_id}")
        variant = variant.replace(source, target)
        applied.append({"source": source, "target": target, "count": count})
    return variant, {"replacements": applied}


def change_format(question):
    sentences = sentence_spans(question)
    if not sentences:
        raise ValueError("Format transform requires text")
    if len(sentences) == 1:
        formatted = "Question:\n- " + sentences[0]
    else:
        formatted = "Problem details:\n" + "\n".join("- " + s for s in sentences[:-1]) + "\n\nQuestion:\n- " + sentences[-1]
    return formatted, {"sentences": sentences}


def add_irrelevant_information(question):
    return question.rstrip() + " " + IRRELEVANT_SENTENCE, {"added_sentence": IRRELEVANT_SENTENCE}


def review_index(path):
    if not path.exists():
        return {}
    decisions = read_jsonl(path)
    result = {}
    for item in decisions:
        key = item["variant_id"]
        if key in result:
            raise ValueError(f"Duplicate review decision: {key}")
        result[key] = item
    return result


def build_variants(originals, perturbation_types, reviews):
    ids = {row["original_id"] for row in originals}
    if set(PARAPHRASED_TAILS) != ids or set(ENTITY_REPLACEMENTS) != ids:
        raise ValueError("Per-question specifications do not exactly cover source IDs")
    rows = []
    for original in originals:
        oid, question = original["original_id"], original["question"]
        generated = {
            "paraphrase": paraphrase(oid, question),
            "entity_rename": rename_entities(oid, question),
            "format_change": change_format(question),
            "irrelevant_information": add_irrelevant_information(question),
        }
        for kind in perturbation_types:
            variant, transform = generated[kind]
            vid = f"{oid}__{kind}"
            review = reviews.get(vid)
            status = "passed_automatic_checks"
            if review and review.get("decision") == "approve":
                status = "passed_automatic_and_codex_review"
            elif review and review.get("decision") == "reject":
                status = "rejected_by_codex_review"
            rows.append({
                "variant_id": vid,
                "original_id": oid,
                "group_id": original["group_id"],
                "split": original["split"],
                "perturbation_type": kind,
                "original_question": question,
                "variant_question": variant,
                "gold_answer": original["gold_answer"],
                "verification_status": status,
                "independent_human_review_status": "pending",
                "reviewer": review.get("reviewer") if review else None,
                "review_note": review.get("note") if review else None,
                "transform_record": transform,
                "source_row_index": original["source_row_index"],
            })
    return rows


def automatic_checks(rows, originals, cfg, reviews):
    expected_types = set(cfg["perturbation_types"])
    original_by_id = {row["original_id"]: row for row in originals}
    per_group = Counter(row["original_id"] for row in rows)
    per_type = Counter(row["perturbation_type"] for row in rows)
    variant_ids = {row["variant_id"] for row in rows}
    checks = {
        "row_count": len(rows) == cfg["expected_originals"] * cfg["variants_per_original"],
        "unique_variant_ids": len(variant_ids) == len(rows),
        "four_variants_per_original": set(per_group.values()) == {cfg["variants_per_original"]},
        "all_types_per_original": all({r["perturbation_type"] for r in rows if r["original_id"] == oid} == expected_types for oid in original_by_id),
        "balanced_types": set(per_type.values()) == {cfg["expected_originals"]},
        "original_text_exact": all(r["original_question"] == original_by_id[r["original_id"]]["question"] for r in rows),
        "group_and_split_inherited": all((r["group_id"], r["split"]) == (original_by_id[r["original_id"]]["group_id"], original_by_id[r["original_id"]]["split"]) for r in rows),
        "gold_inherited": all(r["gold_answer"] == original_by_id[r["original_id"]]["gold_answer"] for r in rows),
        "variants_differ": all(r["variant_question"] != r["original_question"] for r in rows),
        "numbers_exactly_preserved": all(NUMBER_RE.findall(r["variant_question"]) == NUMBER_RE.findall(r["original_question"]) for r in rows),
        "paraphrase_changes_only_tail": all(
            r["original_question"].endswith(r["transform_record"]["original_tail"])
            and r["variant_question"] == r["original_question"][:-len(r["transform_record"]["original_tail"])] + r["transform_record"]["replacement_tail"]
            for r in rows if r["perturbation_type"] == "paraphrase"
        ),
        "entity_sources_removed_and_targets_present": all(
            all(x["source"] not in r["variant_question"] and r["variant_question"].count(x["target"]) >= x["count"] for x in r["transform_record"]["replacements"])
            for r in rows if r["perturbation_type"] == "entity_rename"
        ),
        "format_preserves_sentences": all(
            r["variant_question"] == (
                "Question:\n- " + r["transform_record"]["sentences"][0]
                if len(r["transform_record"]["sentences"]) == 1
                else "Problem details:\n" + "\n".join("- " + s for s in r["transform_record"]["sentences"][:-1]) + "\n\nQuestion:\n- " + r["transform_record"]["sentences"][-1]
            )
            for r in rows if r["perturbation_type"] == "format_change"
        ),
        "irrelevant_append_exact": all(
            r["variant_question"] == r["original_question"].rstrip() + " " + IRRELEVANT_SENTENCE
            for r in rows if r["perturbation_type"] == "irrelevant_information"
        ),
        "review_ids_known": set(reviews).issubset(variant_ids),
        "review_schema_valid": all(item.get("decision") in {"approve", "reject"} and item.get("reviewer") and item.get("variant_sha256") for item in reviews.values()),
        "review_matches_variant_text": all(
            review.get("variant_sha256") == sha256(next(row["variant_question"] for row in rows if row["variant_id"] == variant_id).encode("utf-8"))
            for variant_id, review in reviews.items() if variant_id in variant_ids
        ),
    }
    if not all(checks.values()):
        raise ValueError("Automatic validation failed: " + json.dumps(checks, ensure_ascii=False))
    return checks, per_type


def export_csv(path, rows):
    fields = ["variant_id", "original_id", "split", "perturbation_type", "original_question", "variant_question", "gold_answer", "verification_status", "independent_human_review_status", "reviewer", "review_note"]
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields)
    writer.writeheader()
    for row in rows:
        writer.writerow({key: row.get(key) for key in fields})
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(stream.getvalue(), encoding="utf-8")


def prepare(config_path, output_dir=None):
    cfg = json.loads(config_path.read_text(encoding="utf-8"))
    source = (config_path.parent / cfg["source_file"]).resolve()
    if sha256(source.read_bytes()) != cfg["source_sha256"]:
        raise ValueError("Pinned original dataset SHA-256 mismatch")
    originals = read_jsonl(source)
    if len(originals) != cfg["expected_originals"]:
        raise ValueError("Unexpected original count")
    review_path = config_path.parent / cfg["review_file"]
    reviews = review_index(review_path)
    rows = build_variants(originals, cfg["perturbation_types"], reviews)
    checks, per_type = automatic_checks(rows, originals, cfg, reviews)
    out = output_dir or config_path.parent / "data"
    write_jsonl(out / "offline_eval/paired_variants.jsonl", rows)
    export_csv(out / "offline_eval/paired_variants.csv", rows)
    runtime = [{key: row[key] for key in RUNTIME_FIELDS} for row in rows if row["verification_status"] != "rejected_by_codex_review"]
    write_jsonl(out / "runtime/variants.jsonl", runtime)
    for split in ("dev", "test"):
        write_jsonl(out / f"runtime/{split}.jsonl", [row for row in runtime if row["split"] == split])
    preview = ["# PerturbCoT 变体逐条核对", "", "此文件含离线标准答案。每个原题下依次展示四类变体。", ""]
    for original in originals:
        group = [row for row in rows if row["original_id"] == original["original_id"]]
        preview += [f"## {original['original_id']} · {original['split']}", "", "**原题：** " + original["question"], "", "**标准答案：** " + original["gold_answer"], ""]
        for row in group:
            preview += [f"### {row['perturbation_type']} · {row['verification_status']}", "", row["variant_question"], ""]
    (out / "offline_eval/review_preview.md").write_text("\n".join(preview), encoding="utf-8")
    report = {
        "status": "passed" if all(checks.values()) else "failed",
        "automatic_checks": checks,
        "originals": len(originals),
        "variants": len(rows),
        "variants_by_type": dict(sorted(per_type.items())),
        "split_counts": dict(sorted(Counter(row["split"] for row in rows).items())),
        "codex_review_counts": dict(sorted(Counter(row["verification_status"] for row in rows).items())),
        "independent_human_review_counts": dict(sorted(Counter(row["independent_human_review_status"] for row in rows).items())),
        "accepted_runtime_variants": len(runtime),
        "limitations": [
            "Gold answers are inherited from GSM8K; variants are designed to preserve them rather than independently re-solved.",
            "Codex review is not an independent human annotation; an independent reviewer remains pending.",
            "Entity substitutions use common nouns for six source questions that contain no named entity.",
        ],
    }
    write_json(out / "validation_report.json", report)
    output_files = [
        "offline_eval/paired_variants.jsonl", "offline_eval/paired_variants.csv", "offline_eval/review_preview.md",
        "runtime/variants.jsonl", "runtime/dev.jsonl", "runtime/test.jsonl", "validation_report.json"
    ]
    write_json(out / "manifest.json", {
        "config": cfg,
        "source_path": str(source),
        "source_sha256": sha256(source.read_bytes()),
        "config_sha256": sha256(config_path.read_bytes()),
        "script_sha256": sha256(Path(__file__).read_bytes()),
        "specification_sha256": sha256((config_path.parent / "variant_specs.py").read_bytes()),
        "review_file_sha256": sha256(review_path.read_bytes()) if review_path.exists() else None,
        "output_sha256": {name: sha256((out / name).read_bytes()) for name in output_files},
    })
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=BASE / "config.json")
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    print(json.dumps(prepare(args.config.resolve(), args.output_dir), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
