import unittest

from src.validate_data import REQUIRED, validate_rows
from src.clean_data import range_validity, tri_state_presence, curriculum_presence


class ValidationTests(unittest.TestCase):
    def row(self, **changes):
        row = {name: "x" for name in REQUIRED}
        row.update(duration_years="4")
        row.update(changes)
        return row

    def test_schema_and_valid_row(self):
        self.assertEqual(validate_rows([self.row()], list(REQUIRED) + ["duration_years"]), [])

    def test_duplicate_id_and_required_fields(self):
        rows = [self.row(), self.row()]
        errors = validate_rows(rows, list(REQUIRED))
        self.assertTrue(any("duplicates" in e for e in errors))
        self.assertTrue(validate_rows([self.row(program_id="")], list(REQUIRED)))

    def test_bad_duration_is_rejected(self):
        self.assertTrue(validate_rows([self.row(duration_years="9")], list(REQUIRED) + ["duration_years"]))

    def test_source_error_requires_error_detail(self):
        self.assertTrue(validate_rows([self.row(verification_status="source_error")], list(REQUIRED) + ["collection_error"]))

    def test_identity_status_requires_page_and_school_evidence(self):
        row = self.row(verification_status="verified_identity", http_status="200", content_status="content_available", identity_status="program_and_university_matched", identity_evidence="program_excerpt=AI; university_excerpt=school")
        columns = list(REQUIRED) + ["http_status", "content_status", "identity_status", "identity_evidence"]
        self.assertEqual(validate_rows([row], columns), [])
        row["identity_evidence"] = ""
        self.assertTrue(validate_rows([row], columns))

    def test_missing_values_keep_validity_and_presence_unknown(self):
        self.assertIsNone(range_validity(None, True, 0))
        self.assertIsNone(range_validity(None, True, 1, 8))
        self.assertIsNone(tri_state_presence(None, True))
        self.assertIs(tri_state_presence(0, False), True)

    def test_curriculum_flag_only_false_when_readable_page_was_checked(self):
        self.assertIsNone(curriculum_presence("", True, "not_collected_due_to_source_error", "not_available_due_to_error"))
        self.assertIsNone(curriculum_presence("", True, "candidate_scope_ambiguous", "content_available"))
        self.assertIs(curriculum_presence("", True, "no_program_specific_curriculum_found", "content_available"), False)


if __name__ == "__main__": unittest.main()
