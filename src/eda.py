"""Reproducible, provenance-aware EDA for the current program snapshot.

Uses only the Python standard library. Run from the project root:
    python src/eda.py
"""
from __future__ import annotations

import csv
import html
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "processed"
OUT = ROOT / "reports" / "eda"
OFFICIAL_EVIDENCE = DATA / "official_attribute_evidence.csv"
CORE_ATTRIBUTES = {
    "degree_level": "Cấp bằng",
    "duration_years": "Thời lượng (năm)",
    "instruction_language": "Ngôn ngữ giảng dạy",
    "tuition_amount": "Học phí",
    "tuition_currency": "Đơn vị học phí",
    "curriculum_text": "Curriculum đã xác nhận",
}
ATTR_PROVENANCE = {
    "degree_level": "Không có provenance theo từng trường (trích đoạn/selector).",
    "duration_years": "Không có provenance theo từng trường; bằng chứng thủ công còn chờ xác minh.",
    "instruction_language": "Không có provenance theo từng trường (trích đoạn/selector).",
    "tuition_amount": "Không có giá trị; không suy diễn từ missing.",
    "tuition_currency": "Không có giá trị; không suy diễn từ missing.",
    "curriculum_text": "Chỉ có curriculum_candidate_text; chưa được xác nhận là curriculum.",
}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def present(value: str | None) -> bool:
    return value is not None and value.strip() != ""


def identity_eligible(row: dict[str, str]) -> bool:
    """Strict evidence rule: matched identity plus captured program and school evidence."""
    evidence = row.get("identity_evidence", "").casefold()
    return (
        row.get("verification_status") == "verified_identity"
        and row.get("content_status") == "content_available"
        and row.get("identity_status") == "program_and_university_matched"
        and "program_excerpt" in evidence
        and "university_excerpt" in evidence
    )


def attribute_eligible(row: dict[str, str], field: str, evidence_rows: list[dict[str, str]] = ()) -> bool:
    """Require a matching, explicitly verified official evidence-ledger row."""
    return any(
        evidence.get("program_id") == row.get("program_id")
        and evidence.get("field") == field
        and evidence.get("evidence_status") == "verified_official_source"
        and present(evidence.get("value"))
        and present(evidence.get("source_url"))
        and present(evidence.get("evidence_excerpt"))
        for evidence in evidence_rows
    )


def _svg_bar_chart(title: str, labels: list[str], values: list[int], path: Path) -> None:
    width, height, left, top, plot_width, plot_height = 900, max(180, 86 + 38 * len(labels)), 250, 52, 560, 0
    plot_height = height - top - 24
    maximum = max(values, default=0) or 1
    row_height = plot_height / max(len(labels), 1)
    elements = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
                '<rect width="100%" height="100%" fill="#ffffff"/>',
                f'<text x="24" y="30" font-size="20" font-family="sans-serif" font-weight="bold">{html.escape(title)}</text>']
    for i, (label, value) in enumerate(zip(labels, values)):
        y = top + i * row_height
        bar_width = plot_width * value / maximum
        elements += [f'<text x="{left-12}" y="{y+row_height*0.68:.1f}" text-anchor="end" font-size="14" font-family="sans-serif">{html.escape(label)}</text>',
                     f'<rect x="{left}" y="{y+5:.1f}" width="{bar_width:.1f}" height="{max(12,row_height-10):.1f}" fill="#3478a8"/>',
                     f'<text x="{left+bar_width+8:.1f}" y="{y+row_height*0.68:.1f}" font-size="14" font-family="sans-serif">{value}</text>']
    elements.append("</svg>")
    path.write_text("\n".join(elements), encoding="utf-8")


def run() -> dict[str, object]:
    expanded = read_csv(DATA / "programs_expanded.csv")
    clean = read_csv(DATA / "programs_clean.csv")
    sources = read_csv(DATA / "sources.csv")
    audit = read_csv(DATA / "program_audit.csv")
    manual = read_csv(DATA / "manual_evidence.csv")
    evidence = read_csv(OFFICIAL_EVIDENCE)
    verified_evidence = [r for r in evidence if r.get("evidence_status") == "verified_official_source"]
    OUT.mkdir(parents=True, exist_ok=True)
    figures = OUT / "figures"
    figures.mkdir(exist_ok=True)

    ids = [row.get("program_id", "") for row in expanded]
    duplicate_ids = len(ids) - len(set(ids))
    statuses = Counter(row.get("verification_status", "(missing)") or "(missing)" for row in expanded)
    content = Counter(row.get("content_status", "(missing)") or "(missing)" for row in expanded)
    identity = Counter(row.get("identity_status", "(missing)") or "(missing)" for row in expanded)
    http_2xx = sum((row.get("http_status", "").strip().isdigit() and 200 <= int(row["http_status"]) < 300) for row in expanded)
    identity_rows = [row for row in expanded if identity_eligible(row)]

    _svg_bar_chart("Verification status (all records)", list(sorted(statuses)), [statuses[k] for k in sorted(statuses)], figures / "verification_status.svg")
    pipeline_labels = ["HTTP 2xx response", "Page content available", "Program + university evidence"]
    pipeline_values = [http_2xx, content.get("content_available", 0), len(identity_rows)]
    _svg_bar_chart("Collection and identity stages (counts are nested stages)", pipeline_labels, pipeline_values, figures / "source_identity_stages.svg")

    missing_rows = []
    for field, label in CORE_ATTRIBUTES.items():
        count = sum(not present(row.get(field)) for row in expanded)
        missing_rows.append((field, label, count, len(expanded)))
    _svg_bar_chart("Missing core attributes (records)", [label for _, label, _, _ in missing_rows], [count for _, _, count, _ in missing_rows], figures / "core_attribute_missingness.svg")
    duration_values = [float(r["value"]) for r in verified_evidence if r.get("field") == "duration_years" and present(r.get("value"))]
    duration_counts = Counter(duration_values)
    duration_labels = [f"{value:g} years" for value in sorted(duration_counts)]
    _svg_bar_chart("Officially evidenced scalar durations", duration_labels, [duration_counts[v] for v in sorted(duration_counts)], figures / "verified_duration.svg")
    language_counts = Counter(r["value"] for r in verified_evidence if r.get("field") == "instruction_language" and present(r.get("value")))
    _svg_bar_chart("Officially evidenced instruction language", list(sorted(language_counts)), [language_counts[k] for k in sorted(language_counts)], figures / "verified_instruction_language.svg")
    course_list_ids = {r["program_id"] for r in verified_evidence if r.get("field") == "curriculum_course_list" and present(r.get("evidence_excerpt"))}
    _svg_bar_chart("Programs with course-list evidence captured", ["Evidence captured", "No verified course-list evidence"], [len(course_list_ids), max(0, len(expanded)-len(course_list_ids))], figures / "course_list_evidence_coverage.svg")

    chart_rows: list[dict[str, str]] = []
    def add_chart(name: str, chart_type: str, columns: str, eligible: int, excluded: int, reason: str, outcome: str) -> None:
        chart_rows.append({"chart": name, "type": chart_type, "columns": columns, "records_eligible": str(eligible),
                           "records_excluded": str(excluded), "exclusion_reason": reason, "outcome": outcome})
    add_chart("Verification status", "bar", "program_id,verification_status", len(expanded), 0, "", "rendered")
    add_chart("Collection and identity stages", "bar", "http_status,content_status,identity_status,identity_evidence", len(expanded), 0,
              "All records contribute to stage denominators; stage counts overlap and are not mutually exclusive.", "rendered")
    add_chart("Core attribute missingness", "bar", ",".join(CORE_ATTRIBUTES), len(expanded), 0, "Missingness describes the snapshot only.", "rendered")
    duration_evidence_count = sum(r.get("field") == "duration_years" and present(r.get("value")) for r in verified_evidence)
    duration_range_count = sum(r.get("field") == "duration_range_years" for r in verified_evidence)
    add_chart("Verified scalar duration", "histogram", "official_attribute_evidence.csv: program_id,field,value,source_url,evidence_excerpt", duration_evidence_count, len(expanded)-duration_evidence_count,
              f"{duration_range_count} records have verified ranges that are excluded from a scalar histogram; other exclusions have no exact duration evidence. Not population-representative.", "rendered" if duration_evidence_count >= 5 else "chưa đủ dữ liệu")
    language_evidence_count = sum(r.get("field") == "instruction_language" and present(r.get("value")) for r in verified_evidence)
    bilingual_share_count = sum(r.get("field") == "instruction_language_share" for r in verified_evidence)
    add_chart("Verified instruction language", "category bar", "official_attribute_evidence.csv: program_id,field,value,source_url,evidence_excerpt", language_evidence_count, len(expanded)-language_evidence_count,
              f"{bilingual_share_count} bilingual course-share record is excluded because it is not a single language category; remaining exclusions lack explicit medium evidence. Descriptive subset only.", "rendered" if language_evidence_count >= 5 else "chưa đủ dữ liệu")
    degree_evidence_count = sum(r.get("field") == "degree_level" and present(r.get("value")) for r in verified_evidence)
    award_title_count = sum(r.get("field") == "award_title" for r in verified_evidence)
    add_chart("Degree-level categories", "category bar", "official_attribute_evidence.csv: program_id,field,value,source_url,evidence_excerpt", degree_evidence_count, len(expanded)-degree_evidence_count,
              f"{award_title_count} literal Engineer awards are retained separately; degree taxonomy is not normalized across award titles, so category comparison is withheld.", "chưa đủ dữ liệu / chưa chuẩn hóa taxonomy")
    add_chart("Course-list evidence coverage", "coverage bar", "official_attribute_evidence.csv: program_id,field,value,source_url,evidence_excerpt", len(course_list_ids), len(expanded)-len(course_list_ids),
              "Excluded means no course-list excerpt was captured in the verification ledger; it does not prove that a program has no curriculum.", "rendered")

    with (OUT / "chart_eligibility.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(chart_rows[0]))
        writer.writeheader()
        writer.writerows(chart_rows)

    summary = [
        "# Báo cáo chất lượng và điều kiện EDA", "",
        "Snapshot hiện có, không đại diện thống kê cho toàn bộ chương trình AI/Khoa học dữ liệu tại Việt Nam. Script chỉ dùng Python standard library.", "",
        "## Toàn bộ bản ghi: chất lượng dữ liệu", "",
        f"- programs_expanded.csv: **{len(expanded)}** dòng; ID trùng: **{duplicate_ids}**.",
        f"- programs_clean.csv: **{len(clean)}** dòng; ID trùng: **{len(clean)-len({r.get('program_id','') for r in clean})}**; ID khớp expanded: **{set(ids)=={r.get('program_id','') for r in clean}}**.",
        f"- sources.csv: **{len(sources)}** dòng; program_audit.csv: **{len(audit)}** dòng; manual_evidence.csv: **{len(manual)}** dòng (giữ riêng); official_attribute_evidence.csv: **{len(verified_evidence)}** dòng bằng chứng; các trường được ánh xạ được tổng hợp vào programs_expanded rồi cleaner chuyển tiếp sang programs_clean.",
        f"- Verification status: {', '.join(f'{k}={v}' for k,v in sorted(statuses.items()))}.",
        f"- Content status: {', '.join(f'{k}={v}' for k,v in sorted(content.items()))}.",
        f"- Identity status: {', '.join(f'{k}={v}' for k,v in sorted(identity.items()))}.",
        f"- HTTP response 2xx: **{http_2xx}/{len(expanded)}**; trang có nội dung: **{content.get('content_available',0)}/{len(expanded)}**; danh tính có bằng chứng theo rule nghiêm ngặt: **{len(identity_rows)}/{len(expanded)}**.",
        "- Các giai đoạn trên khác nhau về ý nghĩa; số đếm stage không hàm ý thuộc tính chương trình đã xác minh.", "",
        "## Thiếu dữ liệu và số lượng dùng được", "",
        "| Thuộc tính | Missing trong expanded | Missing % | Giá trị hiện có trong snapshot | Có bằng chứng chính thức mới trong ledger |",
        "|---|---:|---:|---:|---:|",
    ]
    for field, label, missing, total in missing_rows:
        observed = total - missing
        evidenced = sum(attribute_eligible(row, field, verified_evidence) for row in expanded)
        summary.append(f"| {label} (`{field}`) | {missing}/{total} | {missing/total:.0%} | {observed} | {evidenced} |")
    summary += ["", f"Ledger có bằng chứng khóa học cụ thể cho **{len(course_list_ids)}** bản ghi. `curriculum_candidate_text` không được tính là curriculum xác nhận. Bằng chứng cũ trong manual_evidence.csv (8 dòng) vẫn tách biệt và chưa xác minh lại; không quy đổi tín chỉ/credit points.", "",
                "## Giá trị được xác minh từ nguồn chính thức", "",
                "Ledger chỉ ghi thuộc tính có URL và trích đoạn. Các thuộc tính được ánh xạ từ dòng verified_official_source được tổng hợp vào programs_expanded; cleaner chuyển tiếp các giá trị này sang programs_clean. Những trường không được ánh xạ và giá trị chưa có bằng chứng vẫn để NA.", "",
                "| ID | Thuộc tính | Giá trị |", "|---|---|---|"]
    for row in verified_evidence:
        if row.get("field") in {"duration_years", "duration_range_years", "instruction_language", "instruction_language_share", "degree_level", "award_title"}:
            summary.append(f"| {row['program_id']} | {row['field']} | {row['value']} {row.get('unit','')} |")
    summary += ["",
                "## Danh tính và điều kiện phân tích", "",
                f"Có **{len(identity_rows)}** bản ghi đủ điều kiện nhóm danh tính: verification_status=verified_identity, content_status=content_available, identity_status=program_and_university_matched và identity_evidence có program_excerpt cùng university_excerpt. Đây chỉ xác nhận nhận diện chương trình/trường, không xác nhận mọi thuộc tính.", "",
                "## Biểu đồ", "",
                "- `figures/verification_status.svg`: dùng verification_status, toàn bộ bản ghi; loại 0.",
                "- `figures/source_identity_stages.svg`: dùng http_status/content_status/identity_status/identity_evidence; toàn bộ 20 bản ghi ở mẫu số, không loại. Đây là các số đếm stage lồng nhau.",
                "- `figures/core_attribute_missingness.svg`: dùng sáu thuộc tính cốt lõi; toàn bộ 20 bản ghi, không loại.",
                "- `figures/verified_duration.svg`: 16 giá trị thời lượng chính xác có bằng chứng; loại 4/20, gồm các trường hợp không có giá trị scalar (khoảng thời lượng được giữ riêng). Mô tả tập nguồn đã kiểm tra, không đại diện toàn bộ.",
                "- `figures/verified_instruction_language.svg`: 6 giá trị medium có bằng chứng; loại 14/20, gồm một chương trình song ngữ 50% môn học tiếng Anh không ép vào một nhãn ngôn ngữ.",
                "- `figures/course_list_evidence_coverage.svg`: 5 bản ghi có trích đoạn danh sách học phần; 15 chưa có trích đoạn trong ledger. Đây không phải phép đo chương trình nào có/không có curriculum.",
                "- Cấp bằng: 14 giá trị Bachelor có bằng chứng; các danh hiệu Kỹ sư được giữ nguyên riêng. Chưa vẽ so sánh cấp bằng vì taxonomy chưa được chuẩn hóa.",
                "- Chi tiết eligible/excluded của mọi biểu đồ ở `chart_eligibility.csv`.", "",
                "## Giới hạn", "",
                "Các thống kê mô tả snapshot 20 dòng. Giá trị NA được giữ là thiếu, không diễn giải thành False/0. Tuition chưa biết không phải miễn phí; curriculum candidate không phải curriculum đã xác nhận.", ""]
    (OUT / "quality_report.md").write_text("\n".join(summary), encoding="utf-8")
    try:
        from .dashboard import build_dashboard_outputs
    except ImportError:
        from dashboard import build_dashboard_outputs
    dashboard_metrics = build_dashboard_outputs(ROOT)
    return {"records": len(expanded), "duplicate_ids": duplicate_ids, "identity_eligible": len(identity_rows),
            "http_2xx": http_2xx, "content_available": content.get("content_available", 0), "manual_evidence_rows": len(manual),
            "official_evidence_rows": len(verified_evidence), "verified_duration": duration_evidence_count,
            "verified_language": language_evidence_count, "course_list_evidence_programs": len(course_list_ids),
            "dashboard": dashboard_metrics}


if __name__ == "__main__":
    result = run()
    print("EDA outputs written to reports/eda")
    print(result)
