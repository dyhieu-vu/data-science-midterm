import csv
import json
import tempfile
import unittest
from pathlib import Path

from src.dashboard import build_dashboard_outputs, prepare_dashboard_data


class DashboardEligibilityTests(unittest.TestCase):
    def base_rows(self):
        programs = [
            {"program_id": "P1", "program_name": "AI", "university_name": "Example University",
             "country": "Vietnam", "verification_status": "verified_identity", "identity_status": "program_and_university_matched",
             "content_status": "content_available", "http_status": "200", "source_url": "https://example.edu/p1"},
            {"program_id": "P2", "program_name": "Data Science", "university_name": "Other University",
             "country": "Vietnam", "verification_status": "source_error", "identity_status": "not_checked",
             "content_status": "not_available_due_to_error", "http_status": "", "source_url": "https://example.edu/p2"},
        ]
        clean = [dict(r, duration_range_years="", total_credits="", credit_system="", award_title="",
                      instruction_language_share="", curriculum_course_list="") for r in programs]
        evidence = [
            {"program_id": "P1", "field": "duration_years", "value": "4", "unit": "years",
             "source_url": "https://example.edu/p1", "evidence_excerpt": "Duration 4 years",
             "evidence_status": "verified_official_source", "checked_at_utc": "2026-10-15T00:00:00Z", "scope_notes": ""},
            {"program_id": "P1", "field": "total_credits", "value": "120", "unit": "credits",
             "source_url": "https://example.edu/p1", "evidence_excerpt": "120 credits",
             "evidence_status": "verified_official_source", "checked_at_utc": "2026-10-15T00:00:00Z", "scope_notes": ""},
            {"program_id": "P1", "field": "curriculum_course_list", "value": "Course A", "unit": "",
             "source_url": "https://example.edu/p1", "evidence_excerpt": "Course A",
             "evidence_status": "verified_official_source", "checked_at_utc": "2026-10-15T00:00:00Z", "scope_notes": "partial"},
        ]
        clean[0]["curriculum_course_list"] = '["Course A"]'
        return programs, clean, evidence

    def test_chart_eligibility_withholds_noncomparable_scatter_and_correlation(self):
        programs, clean, evidence = self.base_rows()
        data = prepare_dashboard_data(programs, clean, evidence)
        statuses = {r["chart"]: r["status"] for r in data["eligible"]}
        self.assertEqual(statuses["Histogram: scalar duration"], "insufficient")
        self.assertEqual(statuses["Scatter + regression: duration vs credits"], "insufficient")
        self.assertEqual(statuses["Correlation heatmap"], "insufficient")
        self.assertEqual(statuses["Network: program to evidenced course names"], "available")
        self.assertEqual(data["metrics"]["source_error"], 1)
        network = next(r for r in data["eligible"] if r["chart"] == "Network: program to evidenced course names")
        self.assertEqual(network["program_count"], 1)
        self.assertEqual(network["programs_excluded"], 1)
        self.assertEqual(network["edge_count"], 1)
        self.assertEqual(network["observation_count"], 1)
        self.assertIn("program_count", network)
        self.assertNotIn("records_eligible", network)

    def test_builder_writes_relative_self_contained_dashboard_and_docs(self):
        programs, clean, evidence = self.base_rows()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "data" / "processed").mkdir(parents=True)
            for name, rows in (("programs_expanded.csv", programs), ("programs_clean.csv", clean),
                               ("official_attribute_evidence.csv", evidence)):
                with (root / "data" / "processed" / name).open("w", encoding="utf-8", newline="") as f:
                    writer = csv.DictWriter(f, fieldnames=list(rows[0]))
                    writer.writeheader(); writer.writerows(rows)
            metrics = build_dashboard_outputs(root)
            page = (root / "index.html").read_text(encoding="utf-8")
            self.assertEqual(metrics["records"], 2)
            self.assertIn('id="statusFilter"', page)
            self.assertIn('id="tooltip"', page)
            self.assertIn('id="dashboard-data"', page)
            for chart_id in ("missingnessChart", "histogram", "boxplot", "violin", "scatter", "correlation", "sunburst", "network"):
                self.assertIn(f'id="{chart_id}"', page)
            self.assertIn("sf.onchange=", page)
            self.assertIn("pf.onchange=", page)
            self.assertIn("<title>", page)  # SVG native hover tooltip content
            self.assertIn("Line/area trend withheld", page)
            for target in ("overview", "collection", "duration", "relationships", "limits", "records"):
                self.assertIn(f'id="{target}"', page)
                self.assertIn(f'href="#{target}"', page)
            eligibility = (root / "reports" / "eda" / "chart_eligibility.csv").read_text(encoding="utf-8-sig")
            self.assertIn("No adequate matrix", eligibility)
            self.assertIn("program_count", eligibility.splitlines()[0])
            self.assertIn("edge_count", eligibility.splitlines()[0])
            self.assertTrue((root / "reports" / "eda" / "data_dictionary.csv").exists())
            self.assertTrue((root / "reports" / "eda" / "quality_report.md").exists())


if __name__ == "__main__":
    unittest.main()

