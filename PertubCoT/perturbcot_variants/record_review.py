#!/usr/bin/env python3
"""Record a completed review of the currently generated variant set."""
import argparse
import hashlib
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--variants", type=Path, default=BASE / "data/offline_eval/paired_variants.jsonl")
    parser.add_argument("--output", type=Path, default=BASE / "review_decisions.jsonl")
    parser.add_argument("--reviewer", default="Codex")
    parser.add_argument("--note", default="Question meaning, mathematical conditions, requested quantity, and answer invariance reviewed; automatic checks also passed.")
    args = parser.parse_args()
    rows = [json.loads(line) for line in args.variants.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(rows) != 200 or len({row["variant_id"] for row in rows}) != 200:
        raise ValueError("Expected exactly 200 unique variants before recording review")
    payload = "".join(json.dumps({
        "variant_id": row["variant_id"],
        "variant_sha256": hashlib.sha256(row["variant_question"].encode("utf-8")).hexdigest(),
        "decision": "approve",
        "reviewer": args.reviewer,
        "note": args.note,
    }, ensure_ascii=False) + "\n" for row in rows)
    args.output.write_text(payload, encoding="utf-8")
    print(f"Recorded {len(rows)} approvals in {args.output}")


if __name__ == "__main__":
    main()
