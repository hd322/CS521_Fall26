import json
import tempfile
import unittest
from pathlib import Path

import prepare_variants as prep


class VariantPreparationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = prep.BASE / "config.json"

    def test_sentence_split_does_not_break_decimals(self):
        text = "It costs $4.00. What is $.25 plus $1.50?"
        self.assertEqual(prep.sentence_spans(text), ["It costs $4.00.", "What is $.25 plus $1.50?"])

    def test_pipeline_counts_and_runtime_label_separation(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp)
            report = prep.prepare(self.config, out)
            self.assertEqual(report["status"], "passed")
            self.assertEqual(report["variants"], 200)
            self.assertEqual(report["variants_by_type"], {
                "entity_rename": 50,
                "format_change": 50,
                "irrelevant_information": 50,
                "paraphrase": 50,
            })
            runtime = prep.read_jsonl(out / "runtime/variants.jsonl")
            self.assertEqual(len(runtime), 200)
            self.assertTrue(all(set(row) == prep.RUNTIME_FIELDS for row in runtime))
            self.assertTrue(all("gold_answer" not in row for row in runtime))

    def test_pipeline_is_reproducible(self):
        with tempfile.TemporaryDirectory() as temp:
            first, second = Path(temp) / "a", Path(temp) / "b"
            prep.prepare(self.config, first)
            prep.prepare(self.config, second)
            for path in first.rglob("*"):
                if path.is_file():
                    self.assertEqual(path.read_bytes(), (second / path.relative_to(first)).read_bytes())

    def test_tampered_source_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source.jsonl"
            source.write_text("{}\n", encoding="utf-8")
            config = json.loads(self.config.read_text(encoding="utf-8"))
            config["source_file"] = "source.jsonl"
            prep.write_json(root / "config.json", config)
            with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
                prep.prepare(root / "config.json", root / "out")

    def test_review_with_unknown_id_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = (prep.BASE / "../perturbcot_data_prep/data/offline_eval/originals.jsonl").resolve()
            config = json.loads(self.config.read_text(encoding="utf-8"))
            config["source_file"] = str(source)
            config["review_file"] = "bad_review.jsonl"
            prep.write_json(root / "config.json", config)
            (root / "bad_review.jsonl").write_text(json.dumps({"variant_id": "unknown", "decision": "approve", "reviewer": "tester"}) + "\n")
            with self.assertRaisesRegex(ValueError, "Automatic validation failed"):
                prep.prepare(root / "config.json", root / "out")


if __name__ == "__main__":
    unittest.main(verbosity=2)
