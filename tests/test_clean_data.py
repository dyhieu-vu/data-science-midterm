import json
import csv
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src import clean_data as cleaner


class CleanDataNewAttributesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.input_path = self.root / "expanded.csv"
        self.output_path = self.root / "clean.csv"
        self.missing_path = self.root / "missing.csv"
        self.columns = ["program_id", "duration_years", "duration_range_years", "total_credits", "credit_system",
                        "award_title", "instruction_language", "instruction_language_share", "curriculum_course_list",
                        "curriculum_candidate_text"]

    def tearDown(self):
        self.temp.cleanup()

    def write_rows(self, rows):
        with self.input_path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=self.columns)
            writer.writeheader()
            writer.writerows(rows)

    def run_fallback(self):
        with patch.object(cleaner, "INPUT_FILE", self.input_path), \
             patch.object(cleaner, "OUTPUT_FILE", self.output_path), \
             patch.object(cleaner, "MISSING_REPORT", self.missing_path):
            cleaner._clean_csv_fallback()
        with self.output_path.open(encoding="utf-8-sig", newline="") as stream:
            return list(csv.DictReader(stream))

    def good_rows(self):
        return [
            {"program_id": "P1", "duration_years": "4", "duration_range_years": "3.5-4", "total_credits": "138",
             "credit_system": "Vietnamese credits", "award_title": "Engineer in AI",
             "instruction_language": "English", "instruction_language_share": "50", "curriculum_course_list": '["Course A", "Course B"]',
             "curriculum_candidate_text": "must not be used"},
            {"program_id": "P2", "duration_years": "", "duration_range_years": "", "total_credits": "",
             "credit_system": "", "award_title": "", "instruction_language": "", "instruction_language_share": "",
             "curriculum_course_list": "", "curriculum_candidate_text": "candidate only"},
        ]

    def test_nullable_numeric_values_ranges_strings_and_json(self):
        rows = self.good_rows()
        self.write_rows(rows)
        cleaned = self.run_fallback()
        self.assertEqual(len(cleaned), 2)
        self.assertEqual(float(cleaned[0]["duration_years"]), 4)
        self.assertEqual(cleaned[0]["duration_valid"], "True")
        self.assertEqual(cleaned[0]["duration_months"], "48.0")
        self.assertEqual(cleaned[0]["duration_range_years"], "3.5-4")
        self.assertEqual(float(cleaned[0]["total_credits"]), 138)
        self.assertEqual(float(cleaned[0]["instruction_language_share"]), 50)
        self.assertEqual(cleaned[0]["instruction_language"], "English")
        self.assertEqual(cleaned[1]["instruction_language"], "")
        self.assertEqual(cleaned[0]["credit_system"], "Vietnamese credits")
        self.assertEqual(cleaned[0]["award_title"], "Engineer in AI")
        self.assertEqual(json.loads(cleaned[0]["curriculum_course_list"]), ["Course A", "Course B"])
        for field in ("total_credits", "instruction_language_share", "curriculum_course_list"):
            self.assertEqual(cleaned[1][field], "")
        self.assertEqual(cleaned[1]["curriculum_course_list"], "")  # candidate text was not used
        self.assertEqual(cleaned[1]["duration_years"], "")
        self.assertEqual(cleaned[1]["duration_valid"], "")

    def test_scalar_duration_validity_does_not_convert_range(self):
        rows = self.good_rows()
        rows[0]["duration_years"] = "9"
        self.write_rows(rows)
        cleaned = self.run_fallback()
        self.assertEqual(cleaned[0]["duration_years"], "9.0")
        self.assertEqual(cleaned[0]["duration_valid"], "False")
        self.assertEqual(cleaned[0]["duration_range_years"], "3.5-4")

    def test_language_share_bounds_and_unique_program_ids(self):
        rows = self.good_rows()
        rows[0]["instruction_language_share"] = "101"
        self.write_rows(rows)
        with self.assertRaisesRegex(ValueError, "outside 0-100"):
            self.run_fallback()

        rows = self.good_rows()
        rows[1]["program_id"] = "P1"
        self.write_rows(rows)
        with self.assertRaisesRegex(ValueError, "Duplicate program_id"):
            self.run_fallback()

    def test_invalid_course_json_is_rejected(self):
        rows = self.good_rows()
        rows[0]["curriculum_course_list"] = "not-json"
        self.write_rows(rows)
        with self.assertRaisesRegex(ValueError, "valid JSON"):
            self.run_fallback()


if __name__ == "__main__":
    unittest.main()
