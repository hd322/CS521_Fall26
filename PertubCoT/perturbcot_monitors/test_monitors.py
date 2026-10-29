#!/usr/bin/env python3

import unittest

from monitor_answer import monitor_group, normalize_answer
from monitor_cot import (
    compare_relations,
    extract_equations,
    extract_version,
    safe_eval,
    trailing_numeric_expression,
)


class MonitorTests(unittest.TestCase):
    def test_answer_normalization(self):
        self.assertEqual(normalize_answer("$1,200.00"), "1200")
        self.assertEqual(normalize_answer("2.500"), "2.5")
        self.assertIsNone(normalize_answer(None))

    def test_answer_monitor_alert(self):
        rows = [
            {
                "original_id": "x",
                "split": "test",
                "run_id": "o",
                "run_kind": "original_initial",
                "perturbation_type": None,
                "status": "ok",
                "extracted_answer": "10",
            }
        ]
        for name, answer in [
            ("entity_rename", "10"),
            ("format_change", "11"),
            ("irrelevant_information", "10"),
            ("paraphrase", "10"),
        ]:
            rows.append(
                {
                    "original_id": "x",
                    "split": "test",
                    "run_id": name,
                    "run_kind": "variant_initial",
                    "perturbation_type": name,
                    "status": "ok",
                    "extracted_answer": answer,
                }
            )
        self.assertEqual(monitor_group(rows)["decision"], "alert")

    def test_equation_extraction_and_arithmetic(self):
        equations = extract_equations("Cost: 3 * $16.50 = $49.50")
        self.assertEqual(len(equations), 1)
        self.assertTrue(equations[0]["arithmetic_correct"])
        wrong = extract_equations("Distance: 40 + 15 = 35")
        self.assertFalse(wrong[0]["arithmetic_correct"])
        self.assertEqual(str(safe_eval("60 - 15")), "45")

    def test_fraction_expression_is_not_truncated(self):
        equations = extract_equations("Occupied units = 120 * (3/4) = 90")
        self.assertEqual(equations[0]["expression"], "120 * (3/4)")
        self.assertTrue(equations[0]["arithmetic_correct"])
        self.assertIsNone(
            trailing_numeric_expression(
                "The value is 4/5 of D, so it can be written as G"
            )
        )

    def test_equivalent_operand_order_is_allowed(self):
        base = {
            "run_id": "o",
            "perturbation_type": None,
            "raw_output": "120 * (3/4) = 90",
        }
        variant = {
            "run_id": "v",
            "perturbation_type": "paraphrase",
            "raw_output": "(3/4) * 120 = 90",
        }
        self.assertEqual(
            compare_relations(extract_version(base), extract_version(variant)), []
        )

    def test_equivalent_rounded_result_is_allowed(self):
        base = {
            "run_id": "o",
            "perturbation_type": None,
            "raw_output": "450 / 7 = 64.28571428571429",
        }
        variant = {
            "run_id": "v",
            "perturbation_type": "format_change",
            "raw_output": "450 / 7 = 64.2857",
        }
        self.assertEqual(
            compare_relations(extract_version(base), extract_version(variant)), []
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
