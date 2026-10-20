import csv
import json
import tempfile
import unittest
from pathlib import Path

from src.merge_official_evidence import NEW_COLUMNS, merge_official_evidence


class OfficialEvidenceMergeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.evidence_path = self.root / "evidence.csv"
        self.programs_path = self.root / "programs.csv"

    def tearDown(self):
        self.temp.cleanup()

    def write_csv(self, path, columns, rows):
        with path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=columns)
            writer.writeheader()
            writer.writerows(rows)

    def read_csv(self, path):
        with path.open(encoding="utf-8-sig", newline="") as f:
            return list(csv.DictReader(f))

    def test_aggregates_only_verified_values_and_preserves_na_and_ranges(self):
        self.write_csv(self.programs_path, ["program_id", "program_name", "duration_years", "instruction_language", "instruction_language_share"], [
            {"program_id": "P1", "program_name": "Original", "duration_years": "", "instruction_language": "", "instruction_language_share": "50"},
            {"program_id": "P2", "program_name": "No evidence", "duration_years": "", "instruction_language": "", "instruction_language_share": ""},
        ])
        self.write_csv(self.evidence_path,
                       ["program_id", "field", "value", "unit", "evidence_status"], [
            {"program_id": "P1", "field": "duration_years", "value": "4", "unit": "years", "evidence_status": "verified_official_source"},
            {"program_id": "P2", "field": "duration_years", "value": "3", "unit": "years", "evidence_status": "unverified"},
            {"program_id": "P1", "field": "duration_range_years", "value": "3.5-4", "unit": "years", "evidence_status": "verified_official_source"},
            {"program_id": "P1", "field": "total_credits", "value": "138", "unit": "Vietnamese credits", "evidence_status": "verified_official_source"},
            {"program_id": "P1", "field": "instruction_language_share", "value": "50", "unit": "percent of courses in English", "evidence_status": "verified_official_source"},
            {"program_id": "P1", "field": "instruction_language", "value": " English ", "unit": "", "evidence_status": "verified_official_source"},
            {"program_id": "P2", "field": "instruction_language", "value": "Vietnamese", "unit": "", "evidence_status": "unverified"},
            {"program_id": "P1", "field": "award_title", "value": "Engineer", "unit": "", "evidence_status": "unverified"},
            {"program_id": "P1", "field": "curriculum_course_list", "value": "Course A; Course B", "unit": "", "evidence_status": "verified_official_source"},
        ])
        programs, columns, stats = merge_official_evidence(self.evidence_path, self.programs_path)
        self.assertEqual(len(programs), 2)
        self.assertEqual(len({row["program_id"] for row in programs}), 2)
        self.assertTrue(set(NEW_COLUMNS).issubset(columns))
        p1, p2 = programs
        self.assertEqual(p1["program_name"], "Original")
        self.assertEqual(p1["duration_years"], "4")
        self.assertEqual(p1["duration_range_years"], "3.5-4")
        self.assertEqual(p1["instruction_language_share"], "50")
        self.assertEqual(p1["instruction_language"], "English")
        self.assertEqual(p2["instruction_language"], "")
        self.assertEqual(p1["credit_system"], "Vietnamese credits")
        self.assertEqual(json.loads(p1["curriculum_course_list"]), ["Course A", "Course B"])
        self.assertEqual(p1["award_title"], "")
        self.assertEqual(p2["program_name"], "No evidence")
        self.assertEqual(p2["duration_years"], "")
        self.assertTrue(all(p2[c] == "" for c in NEW_COLUMNS))
        self.assertEqual(stats["added"], 1)
        self.assertEqual(stats["instruction_language_added"], 1)
        self.assertEqual(stats["instruction_language_evidence_ignored"], 1)
        self.assertEqual(len({row["program_id"] for row in programs}), 2)

    def test_numerically_equivalent_duration_is_preserved(self):
        self.write_csv(self.programs_path, ["program_id", "program_name", "duration_years", "instruction_language", "instruction_language_share"], [
            {"program_id": "P1", "program_name": "Keep this", "duration_years": "4.0", "instruction_language": " English  ", "instruction_language_share": "50"},
        ])
        self.write_csv(self.evidence_path,
                       ["program_id", "field", "value", "unit", "evidence_status"], [
            {"program_id": "P1", "field": "duration_years", "value": "4", "unit": "years", "evidence_status": "verified_official_source"},
            {"program_id": "P1", "field": "duration_years", "value": "4.0", "unit": "years", "evidence_status": "verified_official_source"},
            {"program_id": "P1", "field": "instruction_language", "value": "ENGLISH", "unit": "", "evidence_status": "verified_official_source"},
        ])
        programs, _, stats = merge_official_evidence(self.evidence_path, self.programs_path)
        self.assertEqual(programs[0]["duration_years"], "4.0")
        self.assertEqual(programs[0]["program_name"], "Keep this")
        self.assertEqual(stats["retained_equal"], 1)
        self.assertEqual(stats["added"], 0)
        self.assertEqual(programs[0]["instruction_language"], " English  ")
        self.assertEqual(programs[0]["instruction_language_share"], "50")
        self.assertEqual(stats["instruction_language_retained_equal"], 1)

    def test_duration_conflict_is_reported_without_overwriting_file(self):
        self.write_csv(self.programs_path, ["program_id", "program_name", "duration_years", "instruction_language"], [
            {"program_id": "P1", "program_name": "Original", "duration_years": "3.5", "instruction_language": ""},
        ])
        self.write_csv(self.evidence_path,
                       ["program_id", "field", "value", "unit", "evidence_status"], [
            {"program_id": "P1", "field": "duration_years", "value": "4", "unit": "years", "evidence_status": "verified_official_source"},
        ])
        before = self.programs_path.read_bytes()
        with self.assertRaisesRegex(ValueError, r"Duration conflict for P1/duration_years"):
            merge_official_evidence(self.evidence_path, self.programs_path)
        self.assertEqual(self.programs_path.read_bytes(), before)

    def test_invalid_scalar_and_range_evidence_are_not_coerced(self):
        self.write_csv(self.programs_path, ["program_id", "program_name", "duration_years", "instruction_language"], [
            {"program_id": "P1", "program_name": "Original", "duration_years": "", "instruction_language": ""},
        ])
        self.write_csv(self.evidence_path,
                       ["program_id", "field", "value", "unit", "evidence_status"], [
            {"program_id": "P1", "field": "duration_years", "value": "3.5-4", "unit": "years", "evidence_status": "verified_official_source"},
            {"program_id": "P1", "field": "duration_range_years", "value": "3.5-4", "unit": "years", "evidence_status": "verified_official_source"},
        ])
        programs, _, stats = merge_official_evidence(self.evidence_path, self.programs_path)
        self.assertEqual(programs[0]["duration_years"], "")
        self.assertEqual(programs[0]["duration_range_years"], "3.5-4")
        self.assertEqual(stats["evidence_ignored"], 1)

    def test_duplicate_program_ids_are_rejected(self):
        self.write_csv(self.programs_path, ["program_id", "duration_years", "instruction_language"], [
            {"program_id": "P1", "duration_years": "", "instruction_language": ""}, {"program_id": "P1", "duration_years": "", "instruction_language": ""},
        ])
        self.write_csv(self.evidence_path,
                       ["program_id", "field", "value", "unit", "evidence_status"], [])
        with self.assertRaisesRegex(ValueError, "duplicate program_id"):
            merge_official_evidence(self.evidence_path, self.programs_path)

    def test_conflicting_verified_values_are_rejected(self):
        self.write_csv(self.programs_path, ["program_id", "duration_years", "instruction_language"], [{"program_id": "P1", "duration_years": "", "instruction_language": ""}])
        self.write_csv(self.evidence_path,
                       ["program_id", "field", "value", "unit", "evidence_status"], [
            {"program_id": "P1", "field": "duration_range_years", "value": "3-4", "unit": "years", "evidence_status": "verified_official_source"},
            {"program_id": "P1", "field": "duration_range_years", "value": "4-5", "unit": "years", "evidence_status": "verified_official_source"},
        ])
        with self.assertRaisesRegex(ValueError, "Conflicting verified values"):
            merge_official_evidence(self.evidence_path, self.programs_path)

    def test_instruction_language_conflicts_abort_without_writing(self):
        self.write_csv(self.programs_path,
                       ["program_id", "duration_years", "instruction_language", "program_name"], [
            {"program_id": "P1", "duration_years": "", "instruction_language": "Vietnamese", "program_name": "Keep"},
        ])
        self.write_csv(self.evidence_path,
                       ["program_id", "field", "value", "unit", "evidence_status"], [
            {"program_id": "P1", "field": "instruction_language", "value": "English", "unit": "", "evidence_status": "verified_official_source"},
        ])
        before = self.programs_path.read_bytes()
        with self.assertRaisesRegex(ValueError, r"Conflict for P1/instruction_language"):
            merge_official_evidence(self.evidence_path, self.programs_path)
        self.assertEqual(self.programs_path.read_bytes(), before)

    def test_multiple_verified_instruction_languages_conflict(self):
        self.write_csv(self.programs_path,
                       ["program_id", "duration_years", "instruction_language", "program_name"], [
            {"program_id": "P1", "duration_years": "", "instruction_language": "", "program_name": "Keep"},
        ])
        self.write_csv(self.evidence_path,
                       ["program_id", "field", "value", "unit", "evidence_status"], [
            {"program_id": "P1", "field": "instruction_language", "value": "English", "unit": "", "evidence_status": "verified_official_source"},
            {"program_id": "P1", "field": "instruction_language", "value": "Vietnamese", "unit": "", "evidence_status": "verified_official_source"},
        ])
        before = self.programs_path.read_bytes()
        with self.assertRaisesRegex(ValueError, r"Conflicting verified values for P1/instruction_language"):
            merge_official_evidence(self.evidence_path, self.programs_path)
        self.assertEqual(self.programs_path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
