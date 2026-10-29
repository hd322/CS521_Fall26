import json
import tempfile
import unittest
from pathlib import Path

import prepare_dataset as prep


class DataPreparationTests(unittest.TestCase):
    def test_gold_uses_final_marker_not_working_numbers(self):
        self.assertEqual(prep.extract_gold("Work: 2 * 3 = 6\n#### 1,200.50"), "1200.5")
        self.assertEqual(prep.extract_gold("#### -0.00"), "0")

    def test_malformed_gold_is_rejected(self):
        for text in ["answer: 42", "#### 3 apples", "#### 1,2", "#### NaN", "#### 4\n#### 5"]:
            with self.subTest(text=text), self.assertRaises(ValueError):
                prep.extract_gold(text)

    def test_duplicate_grouping_and_split(self):
        rows = [{"original_id": str(i), "group_id": prep.question_group(q)} for i, q in enumerate(["A  question", "a question", "Another", "Third"])]
        result = prep.select_rows(rows, 11, 3, 1)
        self.assertEqual(len({r["group_id"] for r in result}), 3)
        self.assertEqual(sum(r["split"] == "dev" for r in result), 1)
        self.assertNotIn("1", {r["original_id"] for r in result})

    def test_invalid_sizes_are_rejected(self):
        for n, dev in [(0, 0), (1, 1), (3, 1)]:
            with self.subTest(n=n, dev=dev), self.assertRaises(ValueError):
                prep.select_rows([], 11, n, dev)

    def test_source_tampering_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            cfg = json.loads((prep.BASE / "config.json").read_text())
            cfg["source_file"] = "tampered.jsonl"
            (root / "tampered.jsonl").write_text("{}\n")
            prep.write_json(root / "config.json", cfg)
            with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
                prep.prepare(root / "config.json")

    def test_pipeline_reproducible_and_runtime_has_no_labels(self):
        with tempfile.TemporaryDirectory() as temp:
            first, second = Path(temp) / "first", Path(temp) / "second"
            report = prep.prepare(prep.BASE / "config.json", first)
            prep.prepare(prep.BASE / "config.json", second)
            self.assertEqual(report["status"], "passed")
            self.assertEqual(report["split_counts"], {"dev": 10, "test": 40})
            for path in first.rglob("*"):
                if path.is_file():
                    self.assertEqual(path.read_bytes(), (second / path.relative_to(first)).read_bytes())
            rows = prep.read_jsonl(first / "runtime/questions.jsonl")
            self.assertEqual(len(rows), 50)
            self.assertTrue(all(set(r) == prep.RUNTIME_FIELDS for r in rows))


if __name__ == "__main__":
    unittest.main(verbosity=2)
