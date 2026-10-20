import unittest

from src.collect_data import assess_identity, course_candidates, set_collection_failure, set_page_evidence
from src.audit_data import audit_rows, classify_source_error


class CollectionContractTests(unittest.TestCase):
    def test_page_with_curriculum_records_snippet_and_status(self):
        row = {}
        set_page_evidence(row, "Data Science", "x" * 120, "Machine learning course")
        self.assertEqual(row["content_status"], "content_available")
        self.assertEqual(row["curriculum_text"], "")
        self.assertEqual(row["curriculum_candidate_text"], "Machine learning course")
        self.assertEqual(row["curriculum_status"], "candidate_requires_manual_scope_review")

    def test_empty_curriculum_is_explained_not_filled(self):
        row = {}
        set_page_evidence(row, "", "Readable page text" * 8, "")
        self.assertEqual(row["curriculum_text"], "")
        self.assertEqual(row["curriculum_status"], "not_extracted_no_explicit_course_entries")
        self.assertEqual(row["content_status"], "content_available")

    def test_source_exception_is_recorded_and_not_confused_with_http(self):
        row = {"http_status": "", "content_status": "not_checked", "curriculum_status": "not_checked"}
        set_collection_failure(row, TimeoutError("timed out"))
        self.assertEqual(row["verification_status"], "source_error")
        self.assertIn("TimeoutError", row["collection_error"])
        self.assertEqual(row["http_status_meaning"], "request failed before HTTP response")
        self.assertEqual(row["curriculum_status"], "not_collected_due_to_source_error")

    def test_identity_requires_both_program_and_university_terms(self):
        matched, evidence = assess_identity("Data Science", "Example University", "Data Science", "Example University offers the Data Science bachelor's program.")
        self.assertTrue(matched)
        self.assertIn("program_excerpt=", evidence)
        rejected, _ = assess_identity("Data Science", "Example University", "Data Science", "Other school offers Data Science.")
        self.assertFalse(rejected)

    def test_curriculum_extractor_rejects_navigation_and_overview(self):
        candidates = course_candidates([
            "Artificial Intelligence – Major",
            "The program prepares students for modern careers in AI.",
            "CSC14003 - Fundamentals of Artificial Intelligence",
        ])
        self.assertEqual(candidates, "CSC14003 - Fundamentals of Artificial Intelligence")

    def test_audit_does_not_keep_legacy_keyword_only_verification(self):
        program = {"program_id": "P1", "source_id": "S1", "source_url": "https://example.edu/p", "university_name": "Example University", "program_name": "AI Program", "http_status": "200", "verification_status": "verified_identity", "file_name": "", "collection_error": ""}
        registry = [{"program_id": "P1", "source_id": "S1", "source_url": "https://example.edu/p"}]
        sources = [{"source_id": "S1", "source_url": "https://example.edu/p", "http_status": "200"}]
        result = audit_rows([program], registry, sources)[0]
        self.assertEqual(result["recommended_status"], "needs_manual_review")
        self.assertIn("program and institution identity evidence is missing or incomplete", result["review_reason"])

    def test_audit_classifies_dns_error_without_calling_it_http_or_timeout(self):
        error = "ConnectionError: Failed to resolve 'example.edu' while requesting /robots.txt"
        classification = classify_source_error(error, "")
        self.assertIn("name-resolution", classification)
        self.assertNotIn("HTTP response", classification)
        self.assertNotIn("Timeout", classification)


if __name__ == "__main__": unittest.main()
