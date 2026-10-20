import unittest

from src.eda import attribute_eligible, identity_eligible, present


class EdaEligibilityTests(unittest.TestCase):
    def test_identity_requires_matching_program_and_university_evidence(self):
        row = {
            "verification_status": "verified_identity",
            "content_status": "content_available",
            "identity_status": "program_and_university_matched",
            "identity_evidence": "program_excerpt;university_excerpt",
        }
        self.assertTrue(identity_eligible(row))
        row["identity_evidence"] = "program_excerpt"
        self.assertFalse(identity_eligible(row))

    def test_http_success_alone_does_not_pass_identity_filter(self):
        row = {
            "http_status": "200",
            "verification_status": "needs_manual_review",
            "content_status": "content_available",
            "identity_status": "manual_review_required",
            "identity_evidence": "",
        }
        self.assertFalse(identity_eligible(row))

    def test_missing_values_are_not_valid_attributes_or_false_zero(self):
        row = {"verification_status": "verified_identity", "duration_years": ""}
        self.assertFalse(present(row["duration_years"]))
        self.assertFalse(attribute_eligible(row, "duration_years"))
        self.assertTrue(present("0"))
        self.assertTrue(present("False"))

    def test_present_attribute_without_field_provenance_is_not_eligible(self):
        row = {
            "verification_status": "verified_identity",
            "content_status": "content_available",
            "identity_status": "program_and_university_matched",
            "identity_evidence": "program_excerpt;university_excerpt",
            "duration_years": "4",
        }
        self.assertFalse(attribute_eligible(row, "duration_years"))

    def test_attribute_requires_matching_official_excerpt_and_url(self):
        row = {"program_id": "VN001_AI", "duration_years": "4"}
        evidence = [{
            "program_id": "VN001_AI", "field": "duration_years", "value": "4",
            "evidence_status": "verified_official_source", "source_url": "https://official.example/program",
            "evidence_excerpt": "Thời gian đào tạo: 4,0 năm.",
        }]
        self.assertTrue(attribute_eligible(row, "duration_years", evidence))
        evidence[0]["evidence_excerpt"] = ""
        self.assertFalse(attribute_eligible(row, "duration_years", evidence))
        evidence[0]["evidence_excerpt"] = "Thời gian đào tạo: 4,0 năm."
        evidence[0]["program_id"] = "VN002_OTHER"
        self.assertFalse(attribute_eligible(row, "duration_years", evidence))


if __name__ == "__main__":
    unittest.main()
