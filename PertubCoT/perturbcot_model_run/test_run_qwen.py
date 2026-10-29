import unittest

from run_qwen import build_schedule, extract_answer


class RunnerTests(unittest.TestCase):
    def test_answer_extraction_priority(self):
        self.assertEqual(extract_answer("work 2+2=4\nFinal answer: $1,200.50")[:2], ("$1,200.50", "1200.5"))
        self.assertEqual(extract_answer(r"Therefore \\boxed{3/2}")[:2], ("3/2", "1.5"))
        self.assertEqual(extract_answer("No numeric result."), (None, None, "not_found"))

    def test_schedule_shape(self):
        originals = [{"original_id": "o1", "group_id": "g1", "split": "dev", "question": "Q1"}]
        variants = [{"variant_id": "v1", "original_id": "o1", "group_id": "g1", "split": "dev", "perturbation_type": "paraphrase", "variant_question": "Q1?"}]
        rows = build_schedule(originals, variants, 5, 100)
        self.assertEqual(len(rows), 6)
        self.assertEqual([row["seed"] for row in rows], list(range(100, 106)))
        self.assertEqual(sum(row["run_kind"] == "original_initial" for row in rows), 1)
        self.assertEqual(sum(row["run_kind"] == "original_repeat" for row in rows), 4)
        self.assertEqual(sum(row["run_kind"] == "variant_initial" for row in rows), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
