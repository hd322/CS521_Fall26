#!/usr/bin/env python3
"""Run the pinned PerturbCoT schedule with a local Hugging Face causal LM."""
import argparse
import hashlib
import json
import os
import platform
import re
import time
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from fractions import Fraction
from pathlib import Path

BASE = Path(__file__).resolve().parent
NUMBER = r"[-+]?\$?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?:/\d+)?%?"


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def read_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalize_number(text):
    value = text.strip().replace("$", "").replace(",", "")
    percent = value.endswith("%")
    if percent:
        value = value[:-1]
    try:
        if "/" in value:
            number = Decimal(Fraction(value).numerator) / Decimal(Fraction(value).denominator)
        else:
            number = Decimal(value)
    except (InvalidOperation, ValueError, ZeroDivisionError):
        return None
    if number == 0:
        normalized = "0"
    else:
        normalized = format(number, "f")
        if "." in normalized:
            normalized = normalized.rstrip("0").rstrip(".")
    return normalized + ("%" if percent else "")


def extract_answer(text):
    methods = [
        ("final_answer", re.findall(r"(?im)^\s*Final\s+answer\s*:\s*(.+?)\s*$", text)),
        ("boxed", re.findall(r"\\boxed\s*\{([^{}]+)\}", text)),
        ("hash_answer", re.findall(r"####\s*([^\n]+)", text)),
    ]
    for method, candidates in methods:
        for candidate in reversed(candidates):
            matches = re.findall(NUMBER, candidate)
            if matches:
                raw = matches[-1]
                return raw, normalize_number(raw), method
    matches = re.findall(NUMBER, text)
    if matches:
        raw = matches[-1]
        return raw, normalize_number(raw), "last_number_fallback"
    return None, None, "not_found"


def build_schedule(originals, variants, repetitions, base_seed):
    original_ids = {row["original_id"] for row in originals}
    if len(original_ids) != len(originals):
        raise ValueError("Duplicate original IDs")
    if any(row["original_id"] not in original_ids for row in variants):
        raise ValueError("Variant references unknown original")
    schedule = []
    for row in originals:
        for repeat_index in range(repetitions):
            schedule.append({
                "run_id": f"{row['original_id']}__original__r{repeat_index}",
                "original_id": row["original_id"],
                "item_id": row["original_id"],
                "group_id": row["group_id"],
                "split": row["split"],
                "version_type": "original",
                "perturbation_type": None,
                "repeat_index": repeat_index,
                "run_kind": "original_initial" if repeat_index == 0 else "original_repeat",
                "question": row["question"],
            })
    for row in variants:
        schedule.append({
            "run_id": f"{row['variant_id']}__r0",
            "original_id": row["original_id"],
            "item_id": row["variant_id"],
            "group_id": row["group_id"],
            "split": row["split"],
            "version_type": "variant",
            "perturbation_type": row["perturbation_type"],
            "repeat_index": 0,
            "run_kind": "variant_initial",
            "question": row["variant_question"],
        })
    schedule.sort(key=lambda row: (row["original_id"], 0 if row["version_type"] == "original" else 1, row["repeat_index"], row["item_id"]))
    for index, row in enumerate(schedule):
        row["schedule_index"] = index
        row["seed"] = base_seed + index
    if len({row["run_id"] for row in schedule}) != len(schedule):
        raise ValueError("Duplicate run IDs")
    return schedule


def append_record(path, record):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record, ensure_ascii=False) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=BASE / "config.json")
    parser.add_argument("--originals", type=Path, default=BASE / "input/originals.jsonl")
    parser.add_argument("--variants", type=Path, default=BASE / "input/variants.jsonl")
    parser.add_argument("--output-dir", type=Path, default=BASE / "results")
    parser.add_argument("--start", type=int, default=0, help="Skip the first N scheduled records")
    parser.add_argument("--limit", type=int, help="Run only the first N scheduled records")
    args = parser.parse_args()

    cfg = json.loads(args.config.read_text(encoding="utf-8"))
    originals, variants = read_jsonl(args.originals), read_jsonl(args.variants)
    if len(originals) != cfg["expected_originals"] or len(variants) != cfg["expected_variants"]:
        raise ValueError(f"Input counts differ from config: originals={len(originals)}, variants={len(variants)}")
    forbidden = {"gold_answer", "source_solution", "answer"}
    if any(forbidden & set(row) for row in originals + variants):
        raise ValueError("Runtime input contains a forbidden answer field")
    schedule = build_schedule(originals, variants, cfg["original_repetitions"], cfg["base_seed"])
    if len(schedule) != cfg["expected_generations"]:
        raise ValueError(f"Expected {cfg['expected_generations']} schedule rows, got {len(schedule)}")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    schedule_path = args.output_dir / "schedule.jsonl"
    schedule_path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in schedule), encoding="utf-8")
    selected = schedule[args.start:]
    selected = selected[:args.limit] if args.limit is not None else selected
    results_path = args.output_dir / "generations.jsonl"
    completed = {row["run_id"] for row in read_jsonl(results_path)} if results_path.exists() else set()

    import torch
    import transformers
    from transformers import AutoModelForCausalLM, AutoTokenizer

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is required for this configured run")
    started_at = utc_now()
    manifest = {
        "status": "running",
        "started_at": started_at,
        "experiment": cfg,
        "inputs": {"originals_sha256": sha256(args.originals), "variants_sha256": sha256(args.variants)},
        "software": {"python": platform.python_version(), "torch": torch.__version__, "transformers": transformers.__version__},
        "hardware": {"cuda": torch.version.cuda, "gpu": torch.cuda.get_device_name(0)},
        "schedule_rows": len(schedule),
        "selected_rows": len(selected),
        "resume_completed_at_start": len(completed),
    }
    write_json(args.output_dir / "run_manifest.json", manifest)

    tokenizer = AutoTokenizer.from_pretrained(cfg["model_path"], local_files_only=True, trust_remote_code=True)
    model = AutoModelForCausalLM.from_pretrained(
        cfg["model_path"], local_files_only=True, trust_remote_code=True,
        torch_dtype=torch.bfloat16, low_cpu_mem_usage=True,
    ).to("cuda").eval()
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token_id = tokenizer.eos_token_id

    session_started = time.perf_counter()
    attempted = 0
    for item in selected:
        if item["run_id"] in completed:
            continue
        attempted += 1
        prompt = cfg["prompt_template"].format(question=item["question"])
        record = {**item, "model_id": cfg["model_id"], "model_path": cfg["model_path"], "prompt": prompt, "started_at": utc_now()}
        try:
            torch.manual_seed(item["seed"])
            torch.cuda.manual_seed_all(item["seed"])
            encoded = tokenizer(prompt, return_tensors="pt", add_special_tokens=True)
            input_ids = encoded["input_ids"].to("cuda")
            attention_mask = encoded["attention_mask"].to("cuda")
            torch.cuda.synchronize()
            begin = time.perf_counter()
            with torch.inference_mode():
                generated = model.generate(
                    input_ids=input_ids,
                    attention_mask=attention_mask,
                    max_new_tokens=cfg["max_new_tokens"],
                    do_sample=cfg["do_sample"],
                    temperature=cfg["temperature"],
                    top_p=cfg["top_p"],
                    top_k=cfg["top_k"],
                    repetition_penalty=cfg["repetition_penalty"],
                    pad_token_id=tokenizer.pad_token_id,
                    eos_token_id=tokenizer.eos_token_id,
                    use_cache=True,
                )
            torch.cuda.synchronize()
            latency = time.perf_counter() - begin
            output_ids = generated[0, input_ids.shape[1]:]
            output = tokenizer.decode(output_ids, skip_special_tokens=True)
            raw_answer, normalized_answer, extraction_method = extract_answer(output)
            record.update({
                "status": "ok",
                "raw_output": output,
                "extracted_answer_raw": raw_answer,
                "extracted_answer": normalized_answer,
                "answer_extraction_method": extraction_method,
                "answer_extraction_success": normalized_answer is not None,
                "input_tokens": int(input_ids.shape[1]),
                "output_tokens": int(output_ids.shape[0]),
                "latency_seconds": latency,
                "tokens_per_second": float(output_ids.shape[0] / latency) if latency else None,
                "truncated": int(output_ids.shape[0]) >= cfg["max_new_tokens"] and (output_ids[-1].item() != tokenizer.eos_token_id if output_ids.numel() else False),
                "error_type": None,
                "error_message": None,
            })
        except Exception as exc:
            record.update({
                "status": "error", "raw_output": None, "extracted_answer_raw": None,
                "extracted_answer": None, "answer_extraction_method": "error",
                "answer_extraction_success": False, "input_tokens": None,
                "output_tokens": None, "latency_seconds": None, "tokens_per_second": None,
                "truncated": None, "error_type": type(exc).__name__, "error_message": str(exc),
            })
        record["finished_at"] = utc_now()
        append_record(results_path, record)
        completed.add(item["run_id"])
        if attempted % 10 == 0 or attempted == 1 or attempted == len(selected):
            print(f"progress {len(completed)}/{len(selected)} latest={item['run_id']} status={record['status']}", flush=True)

    records = read_jsonl(results_path)
    selected_ids = {row["run_id"] for row in selected}
    relevant = [row for row in records if row["run_id"] in selected_ids]
    summary = {
        "status": "complete" if len({row["run_id"] for row in relevant}) == len(selected) else "incomplete",
        "started_at": started_at,
        "finished_at": utc_now(),
        "wall_seconds_this_session": time.perf_counter() - session_started,
        "selected_rows": len(selected),
        "result_rows": len(relevant),
        "status_counts": dict(Counter(row["status"] for row in relevant)),
        "extraction_success": sum(bool(row.get("answer_extraction_success")) for row in relevant),
        "truncated": sum(bool(row.get("truncated")) for row in relevant),
        "input_tokens": sum(row.get("input_tokens") or 0 for row in relevant),
        "output_tokens": sum(row.get("output_tokens") or 0 for row in relevant),
    }
    write_json(args.output_dir / "summary.json", summary)
    manifest["status"] = summary["status"]
    manifest["finished_at"] = summary["finished_at"]
    manifest["summary"] = summary
    write_json(args.output_dir / "run_manifest.json", manifest)
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
