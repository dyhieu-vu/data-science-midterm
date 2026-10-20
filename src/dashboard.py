"""Build a self-contained, provenance-aware dashboard from current CSV outputs."""
from __future__ import annotations

import csv
import json
import math
from collections import Counter
from pathlib import Path


NEW_FIELDS = [
    "duration_range_years", "total_credits", "credit_system", "award_title",
    "instruction_language_share", "curriculum_course_list",
]
FIELD_MEANINGS = {
    "duration_years": "Officially evidenced scalar duration (years); ranges are stored separately.",
    "duration_range_years": "Officially evidenced duration interval, retained as text.",
    "total_credits": "Total credits as stated by the source; not comparable across systems by default.",
    "credit_system": "Credit unit/system exactly as stated in official evidence.",
    "award_title": "Literal award title; not normalized from a major or program name.",
    "instruction_language_share": "Share of courses taught in English, 0–100; not a language label.",
    "curriculum_course_list": "JSON array of evidenced course names; list may be partial.",
    "instruction_language": "Officially evidenced language label where available.",
    "degree_level": "Broad level label; distinct from literal award title.",
    "verification_status": "Collection and identity review status; not attribute completeness.",
    "content_status": "Whether page content was readable at collection time.",
    "identity_status": "Program/university identity assessment status.",
    "http_status": "HTTP response status when a response was received.",
}

FIELD_METADATA = {
    # field: (meaning, type, unit, provenance, missing interpretation)
    "program_id": ("Định danh bản ghi chương trình trong tập dữ liệu.", "chuỗi", "", "source_registry.csv; preserved across outputs", "Thiếu là lỗi cấu trúc; không thể nối bảng."),
    "university_id": ("Định danh cơ sở trong registry.", "chuỗi", "", "source_registry.csv", "Thiếu nghĩa là chưa có mã cơ sở."),
    "university_name": ("Tên cơ sở ghi trong registry.", "chuỗi", "", "source_registry.csv; collector preserves source value", "Thiếu nghĩa là chưa có tên."),
    "program_name": ("Tên chương trình ghi trong registry.", "chuỗi", "", "source_registry.csv; collector preserves source value", "Thiếu nghĩa là chưa có tên."),
    "country": ("Quốc gia được gán cho bản ghi theo phạm vi thu thập.", "chuỗi", "", "collector; current records use Vietnam", "Thiếu nghĩa là chưa rõ quốc gia."),
    "degree_level": ("Nhãn cấp/bậc đào tạo được trích xuất; không thay cho tên văn bằng.", "chuỗi", "", "collector extraction; verify separately in official_attribute_evidence.csv", "Thiếu là chưa có bằng chứng/giá trị được trích."),
    "source_id": ("Mã nguồn theo registry.", "chuỗi", "", "source_registry.csv", "Thiếu là chưa xác định được nguồn."),
    "source_url": ("URL nguồn được đăng ký/thu thập.", "URL string", "", "source_registry.csv", "Thiếu là không có URL để truy nguyên."),
    "file_name": ("Tên file snapshot cục bộ nếu được ghi.", "chuỗi", "", "source_registry.csv", "Thiếu là không có tên snapshot được ghi; không hàm ý nguồn không tồn tại."),
    "verification_status": ("Trạng thái tổng hợp về thu thập/nhận diện; verified_identity chỉ xác nhận danh tính chương trình và trường.", "category string", "", "collector and identity checks", "Thiếu là chưa có trạng thái; không suy ra đã xác minh."),
    "duration_years": ("Thời lượng dạng số đơn; các khoảng được giữ riêng.", "numeric nullable", "years when supported by evidence", "collector field and/or verified official attribute evidence", "NA nghĩa là chưa có giá trị số đơn có bằng chứng; không thay bằng khoảng."),
    "instruction_language": ("Nhãn ngôn ngữ giảng dạy trích xuất.", "chuỗi", "", "collector extraction; official evidence ledger when verified", "NA nghĩa là chưa có bằng chứng, không phải không có ngôn ngữ."),
    "tuition_amount": ("Mức học phí nếu được ghi nhận.", "numeric nullable", "Chưa xác định từ nguồn hiện có", "collector field; no amount currently evidenced", "NA nghĩa là chưa biết; không có nghĩa miễn phí."),
    "tuition_currency": ("Mã/nhãn tiền tệ nếu được ghi nhận.", "chuỗi", "currency as stated; exact unit not normalized", "collector field", "NA nghĩa là chưa biết tiền tệ."),
    "curriculum_text": ("Nội dung curriculum đã được xác nhận; không bao gồm candidate text.", "chuỗi", "", "collector confirmed field; currently empty", "NA nghĩa là chưa có curriculum xác nhận."),
    "curriculum_candidate_text": ("Đoạn văn có thể liên quan curriculum, chưa được xác nhận đúng phạm vi.", "chuỗi", "", "collector page extraction; requires manual review", "NA nghĩa là không thu được candidate; không tương đương curriculum trống."),
    "collected_at": ("Thời điểm collector ghi nhận bản ghi.", "timestamp string", "ISO 8601", "collector clock", "Thiếu là không có timestamp; không tạo xu hướng thời gian."),
    "http_status": ("Mã HTTP nếu nhận được response.", "integer-like string", "HTTP status code", "HTTP client response", "NA nghĩa là chưa nhận được mã HTTP; không tự suy ra nguyên nhân."),
    "http_status_meaning": ("Diễn giải trạng thái request/response đã ghi.", "chuỗi/category", "", "collector", "NA nghĩa là không có diễn giải được ghi."),
    "content_status": ("Trạng thái nội dung trang sau request.", "category string", "", "collector page parsing", "NA nghĩa là nội dung chưa được đánh giá."),
    "page_title": ("Tiêu đề HTML đọc được từ trang.", "chuỗi", "", "HTML parser", "NA nghĩa là không đọc được tiêu đề."),
    "page_content_chars": ("Độ dài văn bản trang sau chuẩn hóa.", "integer-like string", "characters", "HTML text extraction", "NA nghĩa là không có văn bản để đếm."),
    "identity_status": ("Kết quả kiểm tra riêng danh tính chương trình và cơ sở.", "category string", "", "collector identity matching", "NA/not_checked nghĩa là chưa đánh giá; HTTP 2xx không tự xác minh danh tính."),
    "identity_evidence": ("Các cụm/đoạn dùng trong đánh giá danh tính.", "chuỗi", "", "collector extracted page excerpts", "NA nghĩa là không có trích đoạn lưu lại."),
    "curriculum_status": ("Trạng thái thu thập hoặc rà soát curriculum/candidate.", "category string", "", "collector", "NA nghĩa là chưa có trạng thái; candidate không phải nội dung đã xác minh."),
    "collection_error": ("Chi tiết exception nếu request/xử lý lỗi; trường error-only.", "chuỗi", "", "collector exception handler", "Ô trống nghĩa là không ghi nhận exception, không phải thuộc tính được xác minh."),
    "program_code": ("Mã ngành/chương trình trích xuất nếu có.", "chuỗi mã", "", "collector extraction; verify against source", "NA nghĩa là chưa trích được mã."),
    "duration_range_years": ("Khoảng thời lượng được giữ nguyên dạng văn bản.", "range string", "years as stated", "verified official evidence", "NA nghĩa là không có khoảng thời lượng đã xác minh."),
    "total_credits": ("Tổng số tín chỉ/credit points ghi nguyên giá trị nguồn.", "numeric nullable", "Defined by credit_system; systems are not converted", "verified official evidence", "NA nghĩa là chưa có tổng số đã xác minh."),
    "credit_system": ("Hệ/đơn vị tín chỉ ghi nguyên văn.", "chuỗi", "as stated", "verified official evidence", "NA nghĩa là chưa xác định hệ tín chỉ."),
    "award_title": ("Tên văn bằng/award ghi nguyên văn; không suy ra từ major.", "chuỗi", "as stated", "verified official evidence", "NA nghĩa là chưa có tên văn bằng đã xác minh."),
    "instruction_language_share": ("Tỷ lệ khóa học giảng dạy bằng tiếng Anh.", "numeric nullable", "% (0–100)", "verified official evidence", "NA nghĩa là chưa có tỷ lệ đã xác minh; không suy ra nhãn ngôn ngữ."),
    "curriculum_course_list": ("Danh sách khóa học có bằng chứng, lưu dưới dạng JSON array; có thể chỉ là trích đoạn.", "JSON array string", "", "verified official evidence; partial lists remain partial", "NA nghĩa là chưa có danh sách course đã xác minh; không dùng candidate text."),
    "duration_valid": ("Cờ kiểm tra duration_years trong khoảng cho phép 1–8.", "nullable boolean", "", "derived by clean_data.py from duration_years", "NA nếu thời lượng đầu vào thiếu; False là ngoài khoảng, không bị xóa."),
    "tuition_valid": ("Cờ kiểm tra tuition_amount không âm.", "nullable boolean", "", "derived by clean_data.py from tuition_amount", "NA nếu chưa biết học phí; không diễn giải là miễn phí."),
    "duration_months": ("duration_years nhân 12 khi có giá trị số đơn.", "numeric nullable", "months", "derived by clean_data.py", "NA nếu duration_years thiếu; khoảng không chuyển thành số."),
    "duration_group": ("Nhóm duration_years theo các ngưỡng trong cleaner.", "nullable category string", "years", "derived by clean_data.py", "NA nếu duration_years thiếu/ngoài bin."),
    "has_tuition": ("Cờ tri-state: True khi có amount; chưa biết giữ NA.", "nullable boolean", "", "derived by clean_data.py from tuition_amount", "NA nghĩa là chưa biết; không có False mặc định cho học phí thiếu."),
    "tuition_status": ("unknown, amount_recorded hoặc currency_only theo trường amount/currency.", "category string", "", "derived by clean_data.py", "unknown nghĩa là thiếu amount; không khẳng định chương trình miễn phí."),
    "language_known": ("Cờ tri-state cho sự hiện diện của instruction_language.", "nullable boolean", "", "derived by clean_data.py", "NA khi nhãn ngôn ngữ chưa có; không coi là False."),
    "degree_level_known": ("Cờ tri-state cho sự hiện diện của degree_level.", "nullable boolean", "", "derived by clean_data.py", "NA khi cấp bằng chưa có; không suy ra loại văn bằng."),
    "has_curriculum_text": ("Cờ tri-state về curriculum_text xác nhận; False chỉ khi trang đọc được và ghi nhận không tìm thấy curriculum riêng.", "nullable boolean", "", "derived by clean_data.py from curriculum_text and statuses", "NA khi chưa đánh giá được; candidate text không được tính."),
    "curriculum_word_count": ("Số từ trong curriculum_text đã xác nhận.", "nullable integer", "words", "derived by clean_data.py", "NA nếu curriculum chưa xác định; 0 chỉ cho trường hợp đã kiểm tra và xác nhận không có."),
    "program_name_length": ("Số ký tự trong program_name.", "integer", "characters", "derived by clean_data.py", "0 nếu tên thiếu theo cách tính hiện tại; xem program_name gốc."),
}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def _verified(evidence: list[dict[str, str]], field: str) -> list[dict[str, str]]:
    return [r for r in evidence if r.get("field") == field
            and r.get("evidence_status") == "verified_official_source"
            and r.get("value", "").strip() and r.get("source_url", "").strip()
            and r.get("evidence_excerpt", "").strip()]


def prepare_dashboard_data(expanded, clean, evidence):
    by_id = {r["program_id"]: r for r in expanded}
    clean_by_id = {r["program_id"]: r for r in clean}
    statuses = Counter(r.get("verification_status", "(missing)") or "(missing)" for r in expanded)
    scalar_evidence = _verified(evidence, "duration_years")
    range_evidence = _verified(evidence, "duration_range_years")
    course_evidence = _verified(evidence, "curriculum_course_list")
    credit_evidence = _verified(evidence, "total_credits")
    share_evidence = _verified(evidence, "instruction_language_share")

    def evidence_item(row):
        return {
            "program_id": row["program_id"], "value": row["value"], "unit": row.get("unit", ""),
            "source_url": row["source_url"], "excerpt": row["evidence_excerpt"],
            "scope_notes": row.get("scope_notes", ""),
        }

    duration = []
    for r in scalar_evidence:
        try:
            item = evidence_item(r)
            item["value_num"] = float(r["value"])
            item["program_name"] = by_id.get(r["program_id"], {}).get("program_name", r["program_id"])
            duration.append(item)
        except (ValueError, TypeError):
            continue
    ranges = [evidence_item(r) for r in range_evidence]
    credits = []
    for r in credit_evidence:
        try:
            item = evidence_item(r)
            item["value_num"] = float(r["value"])
            item["credit_system"] = r.get("unit", "")
            credits.append(item)
        except (ValueError, TypeError):
            continue

    courses = []
    for r in course_evidence:
        cleaned = clean_by_id.get(r["program_id"], {})
        try:
            names = json.loads(cleaned.get("curriculum_course_list", ""))
        except (json.JSONDecodeError, TypeError):
            continue
        if not isinstance(names, list) or not all(isinstance(x, str) for x in names):
            continue
        courses.append({
            "program_id": r["program_id"],
            "program_name": by_id.get(r["program_id"], {}).get("program_name", r["program_id"]),
            "university_name": by_id.get(r["program_id"], {}).get("university_name", ""),
            "courses": names, "source_url": r["source_url"],
            "excerpt": r["evidence_excerpt"], "scope_notes": r.get("scope_notes", ""),
        })

    verified_fields = ["duration_years", "duration_range_years", "total_credits", "award_title",
                       "instruction_language_share", "curriculum_course_list", "instruction_language", "degree_level"]
    evidence_counts = {field: len({r["program_id"] for r in _verified(evidence, field)}) for field in verified_fields}
    missingness_fields = ["degree_level", "duration_years", "instruction_language", "tuition_amount",
                          "tuition_currency", "curriculum_text"] + NEW_FIELDS
    metrics = {
        "records": len(expanded), "unique_ids": len(by_id), "all_vietnam": bool(expanded) and all(r.get("country") == "Vietnam" for r in expanded),
        "statuses": dict(statuses), "identity_verified": statuses.get("verified_identity", 0),
        "source_error": statuses.get("source_error", 0), "manual_review": statuses.get("needs_manual_review", 0),
        "course_list_programs": len(courses), "evidence_counts": evidence_counts,
    }
    evidence_program_ids = {field: sorted({r["program_id"] for r in _verified(evidence, field)}) for field in verified_fields}
    programs = [{
        "program_id": r.get("program_id", ""), "program_name": r.get("program_name", ""),
        "university_name": r.get("university_name", ""), "country": r.get("country", ""),
        "verification_status": r.get("verification_status", ""),
        "identity_status": r.get("identity_status", ""), "content_status": r.get("content_status", ""),
        "source_url": r.get("source_url", ""),
        "duration_years": next((x["value_num"] for x in duration if x["program_id"] == r.get("program_id")), None),
        "has_range": any(x["program_id"] == r.get("program_id") for x in ranges),
        "missing_fields": [f for f in missingness_fields if not clean_by_id.get(r.get("program_id"), {}).get(f, "").strip()],
    } for r in expanded]

    # A numeric correlation or regression must use at least five paired records and one
    # common credit system. Current credits/durations do not meet that threshold.
    duration_by_id = {r["program_id"]: r for r in duration}
    paired = []
    for credit in credits:
        d = duration_by_id.get(credit["program_id"])
        if d:
            paired.append({"program_id": credit["program_id"], "duration": d["value_num"],
                           "credits": credit["value_num"], "credit_system": credit["credit_system"]})
    homogeneous_pairs = max(Counter(x["credit_system"] for x in paired).values(), default=0)
    line_dates = {r.get("checked_at_utc", "")[:10] for r in evidence if r.get("evidence_status") == "verified_official_source"}
    eligibility = [
        ("Histogram: scalar duration", "duration_years + official evidence", len(duration), max(0, len(expanded)-len(duration)), 0, len(duration), "16 verified scalar values; interval durations excluded. Descriptive subset only.", "available" if len(duration) >= 5 else "insufficient"),
        ("Boxplot: scalar duration", "duration_years + official evidence", len(duration), max(0, len(expanded)-len(duration)), 0, len(duration), "Same small scalar-duration subset; interval durations remain separate.", "available" if len(duration) >= 5 else "insufficient"),
        ("Violin: scalar duration", "duration_years + official evidence", len(duration), max(0, len(expanded)-len(duration)), 0, len(duration), "Kernel density is unstable for this small, discrete sample; label exploratory.", "exploratory" if len(duration) >= 5 else "insufficient"),
        ("Scatter + regression: duration vs credits", "duration_years, total_credits, credit_system", 0, len(expanded), 0, len(paired), f"Only {len(paired)} paired IDs; largest single credit-system subset has {homogeneous_pairs}. Fewer than 5 comparable pairs.", "insufficient"),
        ("Correlation heatmap", "verified numeric attributes", 0, len(expanded), 0, 0, "No adequate matrix of comparable numeric attributes with sufficient pairwise coverage; mixed credit systems excluded.", "insufficient"),
        ("Sunburst: identity status to program", "verification_status, program_id", len(expanded), 0, 0, len(expanded), "Record-level snapshot counts; each listed program contributes one record.", "available"),
        ("Network: program to evidenced course names", "program_id, curriculum_course_list", len(courses), len(expanded)-len(courses), sum(len(r["courses"]) for r in courses), sum(len(r["courses"]) for r in courses), "Only captured course-list excerpts; edge_count counts program-course links, not programs. Lists are partial, not full curricula.", "available" if courses else "insufficient"),
        ("Missing attribute values", ", ".join(missingness_fields), len(expanded), 0, 0, len(expanded), "Missingness describes this snapshot only; missing does not mean false or absent from the program.", "available"),
        ("Line/area: change over time", "checked_at_utc", 0, len(expanded), 0, 0, f"Verified evidence is recorded on {len(line_dates)} distinct date(s); insufficient comparable repeated observations for a trend.", "insufficient"),
    ]
    return {"metrics": metrics, "missingness_fields": missingness_fields, "programs": programs, "duration": duration, "duration_ranges": ranges,
            "credits": credits, "shares": [evidence_item(r) for r in share_evidence], "courses": courses,
            "paired": paired, "evidence_program_ids": evidence_program_ids,
            "eligible": [{"chart": a, "columns": b, "program_count": c, "programs_excluded": d,
                          "edge_count": edge, "observation_count": obs, "limitation": limitation, "status": status}
                         for a,b,c,d,edge,obs,limitation,status in eligibility],
            "data_scope": {"country_values": sorted({r.get("country", "") for r in expanded}),
                           "evidence_date_values": sorted(line_dates)}}


def _dictionary_rows(expanded, clean, evidence):
    result = []
    for filename, rows in (("programs_expanded.csv", expanded), ("programs_clean.csv", clean),
                           ("official_attribute_evidence.csv", evidence)):
        if not rows:
            continue
        for field in rows[0]:
            vals = [r.get(field, "") for r in rows]
            present = [v for v in vals if str(v or "").strip()]
            sample = next((str(v)[:100] for v in present), "")
            metadata = FIELD_METADATA.get(field)
            meaning, dtype, unit, provenance, missing = metadata or (
                "Ch?a x?c ??nh t? ngu?n hi?n c?", "Ch?a x?c ??nh t? ngu?n hi?n c?", "Ch?a x?c ??nh t? ngu?n hi?n c?",
                filename, "Ch?a x?c ??nh t? ngu?n hi?n c?")
            result.append({"file": filename, "field": field, "meaning": meaning, "data_type": dtype, "unit": unit,
                           "rows": len(rows), "missing_count": len(rows)-len(present),
                           "observed_values": len(set(map(str, present))), "example": sample,
                           "provenance": provenance, "missing_interpretation": missing})
    return result


def build_dashboard_outputs(root: Path) -> dict[str, object]:
    root = Path(root)
    data_dir = root / "data" / "processed"
    out_dir = root / "reports" / "eda"
    expanded = read_csv(data_dir / "programs_expanded.csv")
    clean = read_csv(data_dir / "programs_clean.csv")
    evidence = read_csv(data_dir / "official_attribute_evidence.csv")
    data = prepare_dashboard_data(expanded, clean, evidence)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "dashboard_data.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    with (out_dir / "chart_eligibility.csv").open("w", encoding="utf-8-sig", newline="") as f:
        fields = ["chart", "columns", "program_count", "programs_excluded", "edge_count", "observation_count", "limitation", "status"]
        writer = csv.DictWriter(f, fieldnames=fields); writer.writeheader(); writer.writerows(data["eligible"])
    with (out_dir / "data_dictionary.csv").open("w", encoding="utf-8-sig", newline="") as f:
        dict_rows = _dictionary_rows(expanded, clean, evidence)
        writer = csv.DictWriter(f, fieldnames=list(dict_rows[0])); writer.writeheader(); writer.writerows(dict_rows)
    (out_dir / "quality_report.md").write_text(_quality_report(data, expanded, clean, evidence), encoding="utf-8")
    dates = " / ".join(data["data_scope"]["evidence_date_values"]) or "not recorded"
    html = _dashboard_html(json.dumps(data, ensure_ascii=False).replace("</", "<\\/"), dates)
    (root / "index.html").write_text(html, encoding="utf-8")
    return data["metrics"]


def _quality_report(data, expanded, clean, evidence):
    metrics = data["metrics"]
    new_counts = {field: sum(bool(r.get(field, "").strip()) for r in clean) for field in NEW_FIELDS}
    lines = ["# Data quality and chart eligibility", "",
             "This report describes the current 20-record snapshot only; it is not representative of all AI/Data Science programs.", "",
             f"- Expanded: {len(expanded)} rows, {metrics['unique_ids']} unique IDs, {len(expanded[0]) if expanded else 0} columns.",
             f"- Clean: {len(clean)} rows; ID sets match expanded: {set(r['program_id'] for r in expanded)==set(r['program_id'] for r in clean)}.",
             f"- Official evidence ledger: {len(evidence)} rows; verified official rows: {sum(r.get('evidence_status')=='verified_official_source' for r in evidence)}.",
             f"- Status counts: {', '.join(f'{k}={v}' for k,v in sorted(metrics['statuses'].items()))}.",
             f"- Country values: {', '.join(data['data_scope']['country_values']) or '(none)'}.", "",
             "## Six added attributes", "", "| Field | Present | Missing |", "|---|---:|---:|"]
    lines += [f"| `{f}` | {new_counts[f]} | {len(clean)-new_counts[f]} |" for f in NEW_FIELDS]
    lines += ["", "## Chart eligibility", "", "Counts distinguish programs, links (edges), and observations. `program_count` is not an edge count.", "", "| Chart | Programs eligible | Programs excluded | Edges | Observations | Status | Limitation |", "|---|---:|---:|---:|---:|---|---|"]
    lines += [f"| {r['chart']} | {r['program_count']} | {r['programs_excluded']} | {r['edge_count']} | {r['observation_count']} | {r['status']} | {r['limitation']} |" for r in data['eligible']]
    lines += ["", "## Collection and analysis limitations", "",
              "All current program rows are located in Vietnam. A foreign awarding partner does not change the listed delivery-country field. No geographic coordinates are present.",
              "Tuition, confirmed curriculum_text, and most language/award/credit values remain missing. Course lists are partial evidence excerpts, not complete curricula.",
              "Scalar durations exclude range-valued durations. Credit totals remain in their original credit systems and are not combined.",
              "Collection and evidence timestamps do not form a repeated, comparable time series; a line/area trend is withheld.",
              "Values used for attribute charts require matching verified evidence with source URL and excerpt. Missing values remain missing.",
              "Cleaning normalizes whitespace and blank strings to NA, removes only exact duplicate rows, then fails on remaining duplicate program_id rather than silently choosing a record. It does not impute missing values. Error-only collection_error blanks mean no exception was recorded; source_error and DNS failures do not establish that a page or program is absent.",
              "duration_valid and tuition_valid are nullable checks: missing inputs remain NA; out-of-range values are flagged rather than dropped. tuition amount 0 is distinct from missing. has_tuition is tri-state and unknown amounts remain NA.",
              "The current quality checks use the saved snapshot and collector/parser rules. They cannot establish source completeness, detect every semantic anomaly, or make the 20 records representative. Identity verification is separate from per-attribute evidence verification.", ""]
    return "\n".join(lines)


def _dashboard_html(data_json, dates):
    # Self-contained, dependency-free page: relative paths and CDN assets are not required.
    return r'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>AI & Data Science Program Explorer</title>
<style>
:root{--ink:#13243a;--muted:#607187;--line:#dce5ef;--paper:#f4f7fb;--card:#fff;--blue:#2563eb;--teal:#0f766e;--amber:#d97706;--red:#b42318}*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font:15px/1.5 Inter,Segoe UI,Arial,sans-serif}a{color:#155eef}.layout{display:grid;grid-template-columns:230px 1fr;min-height:100vh}.side{background:#10253e;color:white;padding:28px 18px;position:sticky;top:0;height:100vh}.brand{font-weight:800;font-size:17px;margin-bottom:28px}.side small{color:#b5c6d9}.side nav{display:grid;gap:7px;margin-top:22px}.side nav a{color:#e1eaf5;text-decoration:none;padding:9px 10px;border-radius:8px}.side nav a:hover{background:#24415f}.main{max-width:1500px;width:100%;padding:32px clamp(18px,4vw,56px);margin:auto}.eyebrow{text-transform:uppercase;letter-spacing:.12em;color:var(--blue);font-size:11px;font-weight:800}h1{font-size:clamp(28px,4vw,42px);line-height:1.08;margin:8px 0 12px}h2{font-size:22px;margin:0 0 5px}h3{font-size:16px;margin:0 0 10px}.sub,.muted{color:var(--muted)}.notice{border-left:4px solid var(--amber);background:#fff8e8;padding:13px 16px;border-radius:5px;margin:20px 0}.controls,.kpis,.grid{display:grid;gap:14px}.controls{grid-template-columns:repeat(auto-fit,minmax(180px,1fr));padding:15px;background:#eaf0f7;border-radius:12px;margin:18px 0}.controls label{font-size:12px;color:var(--muted);display:grid;gap:5px}select,input{font:inherit;padding:9px;border:1px solid #cbd5e1;border-radius:7px;background:white}.kpis{grid-template-columns:repeat(auto-fit,minmax(150px,1fr));margin:16px 0 26px}.kpi,.card,.section-card{background:var(--card);border:1px solid var(--line);border-radius:13px;box-shadow:0 2px 8px #203b5b0a}.kpi{padding:16px}.kpi strong{font-size:28px;display:block}.kpi span{font-size:12px;color:var(--muted)}section{scroll-margin-top:18px;margin:38px 0}.section-head{margin-bottom:14px}.grid{grid-template-columns:repeat(2,minmax(0,1fr))}.card{padding:18px;min-width:0}.wide{grid-column:1/-1}.chart{width:100%;min-height:210px;overflow:hidden}.chart svg{width:100%;height:auto;display:block}.chart .mark{cursor:help}.tip{font-size:12px;color:var(--muted);margin:8px 0 0}.unavailable{border:1px dashed #b7c4d4;background:#f8fafc;padding:20px;border-radius:10px;color:#53657a}.unavailable strong{color:var(--ink)}.tag{font-size:11px;font-weight:700;border-radius:999px;padding:4px 8px;background:#e9f2ff;color:#194ca4}.tag.warn{background:#fff1d6;color:#8a4b00}.table-wrap{overflow:auto;max-height:470px;border:1px solid var(--line);border-radius:9px}table{width:100%;border-collapse:collapse;font-size:13px}th,td{text-align:left;padding:10px;border-bottom:1px solid var(--line);vertical-align:top}th{position:sticky;top:0;background:#edf3f8}td a{white-space:nowrap}.method{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px}.method>div{padding:15px;background:white;border:1px solid var(--line);border-radius:10px}.foot{font-size:12px;color:var(--muted);border-top:1px solid var(--line);padding-top:18px;margin-top:40px}.svg-label{font-size:12px;fill:#334155}.svg-value{font-size:11px;fill:#13243a}.axis{stroke:#9aabbd;stroke-width:1}.bar{fill:#3478a8}.duration-dot{fill:#2563eb;stroke:white;stroke-width:2}.box{fill:#bfdbfe;stroke:#1d4ed8}.network-edge{stroke:#aab9cb;stroke-width:1.4;opacity:.65}.node-program{fill:#2563eb}.node-course{fill:#0f766e}.node-label{font-size:10px;fill:#22374d}.arc{stroke:white;stroke-width:2}.tooltip{position:fixed;pointer-events:none;background:#10253e;color:white;padding:8px 11px;border-radius:7px;font-size:12px;max-width:320px;z-index:5;display:none;box-shadow:0 6px 20px #0003}.legend{display:flex;flex-wrap:wrap;gap:12px;font-size:12px;color:var(--muted)}.dot{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:5px}@media(max-width:850px){.layout{display:block}.side{position:relative;height:auto;padding:18px}.side nav{display:flex;overflow:auto}.main{padding:22px 16px}.grid{grid-template-columns:1fr}.wide{grid-column:auto}}
</style></head><body><script id="dashboard-data" type="application/json">__DATA__</script><div class="layout"><aside class="side"><div class="brand">Program Explorer<br><small>AI & Data Science</small></div><small>DATA SNAPSHOT</small><nav><a href="#overview">Overview</a><a href="#collection">Collection</a><a href="#duration">Duration</a><a href="#relationships">Relationships</a><a href="#limits">Methods & limits</a><a href="#records">Records</a></nav></aside><main class="main"><div class="eyebrow">Evidence-aware EDA · Midterm project</div><h1>AI & Data Science programs</h1><p class="sub">A transparent view of the current collected snapshot and its evidence coverage.</p><div class="notice"><strong>Scope:</strong> the current records list Vietnam as the delivery country. This dashboard does not provide international coverage or represent all programs. A program identity match does not verify every attribute.</div>
<div class="controls"><label>Verification status<select id="statusFilter"><option value="all">All statuses</option></select></label><label>Program<select id="programFilter"><option value="all">All programs</option></select></label><label>Search institution/program<input id="searchFilter" placeholder="Search names or IDs"></label></div><div id="kpis" class="kpis"></div>
<section id="overview"><div class="section-head"><h2>Data quality & verification</h2><div class="muted">Counts describe records, not the national program population.</div></div><div class="grid"><article class="card"><h3>Verification status <span class="tag">Interactive</span></h3><div id="statusChart" class="chart"></div><p class="tip">Hover for count and share. Filter controls update the chart.</p></article><article class="card"><h3>Attribute evidence coverage <span class="tag">Interactive</span></h3><div id="coverageChart" class="chart"></div><p class="tip">Coverage means a verified evidence row has a URL and excerpt; it does not imply completeness of the attribute.</p></article><article class="card wide"><h3>Missingness by attribute <span class="tag">Interactive</span></h3><div id="missingnessChart" class="chart"></div><p class="tip">Blank values describe this snapshot; missing does not mean false or absent from the program.</p></article><article class="card wide" id="collection"><h3>Collection and identity stages</h3><div id="stagesChart" class="chart"></div><p class="tip">The stages overlap and are not mutually exclusive.</p></article></div></section>
<section id="duration"><div class="section-head"><h2>Duration distribution</h2><div class="muted">Only official, scalar duration evidence enters these plots; range values remain separate.</div></div><div class="grid"><article class="card"><h3>Histogram <span class="tag">Interactive</span></h3><div id="histogram" class="chart"></div><p class="tip">Hover bars to inspect values and records.</p></article><article class="card"><h3>Boxplot <span class="tag">Interactive</span></h3><div id="boxplot" class="chart"></div><p class="tip">Five-number summary of the evidenced scalar subset.</p></article><article class="card"><h3>Violin plot <span class="tag warn">Exploratory · n is small</span></h3><div id="violin" class="chart"></div><p class="tip">Kernel density is shown for shape only; discrete values and small n limit interpretation.</p></article><article class="card"><h3>Verified duration ranges</h3><div id="ranges" class="chart"></div><p class="tip">Intervals are not converted to single values.</p></article><article class="card"><h3>Scatter + regression</h3><div id="scatter" class="unavailable"></div></article><article class="card"><h3>Correlation heatmap</h3><div id="correlation" class="unavailable"></div></article></div></section>
<section id="relationships"><div class="section-head"><h2>Program and evidence relationships</h2><div class="muted">Relationship views show only captured evidence.</div></div><div class="grid"><article class="card"><h3>Sunburst: status → program <span class="tag">Interactive</span></h3><div id="sunburst" class="chart"></div><p class="tip">Hover slices for status, institution and record count.</p></article><article class="card"><h3>Network: program ↔ course evidence <span class="tag">Interactive</span></h3><div id="network" class="chart"></div><p class="tip">Lists are partial snippets; links do not indicate a complete curriculum.</p></article><article class="card wide"><h3>Credit totals by source system</h3><div id="credits" class="chart"></div><p class="tip">Values are separated by their source unit. No conversion or cross-system ranking is applied.</p></article><article class="card wide"><h3>Language share and time series</h3><div class="grid"><div id="share"></div><div class="unavailable"><strong>Line/area trend withheld.</strong><br>Evidence timestamps do not form a repeated, comparable time series. Current evidence is from __DATES__; collection timestamps are not program outcome measurements.</div></div></article></div></section>
<section id="limits"><div class="section-head"><h2>Sources, methods & limits</h2></div><div class="method"><div><h3>Data sources</h3><p>Clean program snapshot: <code>data/processed/programs_clean.csv</code>. Attribute-level official evidence: <code>data/processed/official_attribute_evidence.csv</code>, requiring verified status, source URL and excerpt for attribute charts.</p></div><div><h3>Collection method</h3><p>Records were assembled from official university/admissions pages. The dashboard reports existing collection statuses; it does not retry sources or re-verify them.</p></div><div><h3>Geographic scope</h3><p>All current program records carry country=Vietnam. A foreign awarding partner is not treated as an international delivery location. No coordinates or international-country comparison are available.</p></div><div><h3>Data treatment</h3><p>Missing values remain missing. Duration intervals are not reduced to a scalar. Credit systems stay separate. Course lists remain JSON arrays and are treated as potentially partial. Program names and IDs are not used as numeric measures.</p></div><div><h3>Uncertainty</h3><p>Tuition is missing for all records. Confirmed curriculum text is missing; five records have course-list evidence only. Most attributes have small evidenced subsets. This snapshot is descriptive and not representative.</p></div></div><div class="card" style="margin-top:14px"><h3>Evidence references</h3><div id="sourceList"></div></div><p class="foot">Generated from the current project CSV snapshot. No fabricated values, imputation, credit conversion or source re-verification.</p></section>
<section id="records"><div class="section-head"><h2>Program records</h2><div class="muted">Filtered table includes links to the stored source URL; source claims still require attribute-level evidence.</div></div><div class="table-wrap"><table><thead><tr><th>ID</th><th>Program</th><th>University</th><th>Country</th><th>Verification</th><th>Content</th><th>Source</th></tr></thead><tbody id="recordRows"></tbody></table></div></section><div class="tooltip" id="tooltip"></div></main></div>
<script>
const D=JSON.parse(document.getElementById('dashboard-data').textContent);let state={status:'all',program:'all',search:''};const colors=['#b42318','#d97706','#0f766e','#2563eb','#7c3aed','#64748b'];
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function filtered(){return D.programs.filter(p=>(state.status==='all'||p.verification_status===state.status)&&(state.program==='all'||p.program_id===state.program)&&(!state.search||(p.program_id+' '+p.program_name+' '+p.university_name).toLowerCase().includes(state.search.toLowerCase())))}
function filteredEvidence(rows){const ids=new Set(filtered().map(x=>x.program_id));return rows.filter(r=>ids.has(r.program_id))}
function setup(){let sf=document.getElementById('statusFilter'),pf=document.getElementById('programFilter');[...new Set(D.programs.map(p=>p.verification_status))].sort().forEach(v=>sf.insertAdjacentHTML('beforeend',`<option>${esc(v)}</option>`));D.programs.forEach(p=>pf.insertAdjacentHTML('beforeend',`<option value="${esc(p.program_id)}">${esc(p.program_id)} · ${esc(p.program_name)}</option>`));sf.onchange=()=>{state.status=sf.value;render()};pf.onchange=()=>{state.program=pf.value;render()};document.getElementById('searchFilter').oninput=e=>{state.search=e.target.value;render()};document.querySelectorAll('.side nav a').forEach(a=>a.onclick=()=>document.querySelector(a.getAttribute('href')).scrollIntoView({behavior:'smooth'}));render()}
function svg(id,w,h,body){document.getElementById(id).innerHTML=`<svg viewBox="0 0 ${w} ${h}" role="img">${body}</svg>`}
function titleMark(x,y,tip){return `<title>${esc(tip)}</title>`}
function render(){const rows=filtered();renderKpis(rows);renderStatus(rows);renderCoverage(rows);renderMissingness(rows);renderStages(rows);renderDurations(rows);renderRanges(rows);renderUnavailable(rows);renderSunburst(rows);renderNetwork(rows);renderCredits(rows);renderShare(rows);renderSources(rows);renderTable(rows)}
function renderKpis(rows){let st={};rows.forEach(r=>st[r.verification_status]=(st[r.verification_status]||0)+1);let items=[['Records',rows.length,'after current filters'],['Identity verified',st.verified_identity||0,'identity evidence only'],['Source errors',st.source_error||0,'not evidence of non-existence'],['Manual review',st.needs_manual_review||0,'identity requires review'],['Course lists',filteredEvidence(D.courses).length,'partial evidence snippets']];document.getElementById('kpis').innerHTML=items.map(x=>`<div class="kpi"><strong>${x[1]}</strong><span>${x[0]} · ${x[2]}</span></div>`).join('')}
function renderStatus(rows){let counts={};rows.forEach(r=>counts[r.verification_status]=(counts[r.verification_status]||0)+1);let keys=Object.keys(counts),h=Math.max(150,keys.length*48+40),body='';keys.forEach((k,i)=>{let y=25+i*48,w=counts[k]/Math.max(1,rows.length)*480;body+=`<text x="5" y="${y+17}" class="svg-label">${esc(k)}</text><rect class="mark" x="150" y="${y}" width="${w}" height="25" rx="5" fill="${colors[i%colors.length]}">${titleMark(0,0,`${k}: ${counts[k]} of ${rows.length}`)}</rect><text x="${160+w}" y="${y+17}" class="svg-value">${counts[k]}</text>`});svg('statusChart',680,h,body)}
function renderCoverage(rows){let fields=Object.keys(D.metrics.evidence_counts),h=fields.length*32+15,body='',ids=new Set(rows.map(p=>p.program_id));fields.forEach((f,i)=>{let n=D.evidence_program_ids[f].filter(id=>ids.has(id)).length;let denom=rows.length||1;let w=n/denom*370,y=8+i*32;body+=`<text x="0" y="${y+14}" class="svg-label">${esc(f)}</text><rect class="mark" x="210" y="${y}" width="${w}" height="20" rx="4" fill="#3478a8"><title>${esc(f)}: ${n}/${rows.length} filtered records with verified evidence</title></rect><text x="${218+w}" y="${y+14}" class="svg-value">${n}</text>`});svg('coverageChart',650,h,body)}
function renderMissingness(rows){let fields=D.missingness_fields,h=fields.length*29+12,body='';fields.forEach((f,i)=>{let n=rows.filter(p=>p.missing_fields.includes(f)).length,w=n/Math.max(1,rows.length)*370,y=5+i*29;body+=`<text x="0" y="${y+14}" class="svg-label">${esc(f)}</text><rect class="mark" x="210" y="${y}" width="${w}" height="18" rx="4" fill="#d97706"><title>${esc(f)}: ${n}/${rows.length} missing</title></rect><text x="${218+w}" y="${y+14}" class="svg-value">${n}</text>`});svg('missingnessChart',650,h,body)}
function renderStages(rows){let vals=[['HTTP 2xx',rows.filter(r=>r.http_status&&Number(r.http_status)>=200&&Number(r.http_status)<300).length],['Readable page',rows.filter(r=>r.content_status==='content_available').length],['Identity verified',rows.filter(r=>r.verification_status==='verified_identity'&&r.identity_status==='program_and_university_matched').length]],body='';vals.forEach((x,i)=>{let y=22+i*43,w=x[1]/Math.max(1,rows.length)*460;body+=`<text x="5" y="${y+15}" class="svg-label">${x[0]}</text><rect x="155" y="${y}" width="${w}" height="23" rx="4" fill="${colors[i+1]}"><title>${x[0]}: ${x[1]} / ${rows.length}</title></rect><text x="${163+w}" y="${y+16}" class="svg-value">${x[1]} / ${rows.length}</text>`});svg('stagesChart',700,160,body)}
function renderDurations(rows){let vals=filteredEvidence(D.duration).sort((a,b)=>a.value_num-b.value_num);if(!vals.length){['histogram','boxplot','violin'].forEach(id=>document.getElementById(id).innerHTML='<div class="unavailable">No verified scalar values in current filter.</div>');return}let data=vals.map(x=>x.value_num),min=Math.min(...data),max=Math.max(...data),bins=[];let nbin=Math.max(1,Math.ceil((max-min)/.5));for(let i=0;i<nbin;i++){let lo=min+i*.5,hi=lo+.5,subset=vals.filter(x=>x.value_num>=lo&&(i===nbin-1?x.value_num<=hi:x.value_num<hi));bins.push({lo,hi,subset})}let maxc=Math.max(...bins.map(b=>b.subset.length),1),body='';bins.forEach((b,i)=>{let w=b.subset.length/maxc*300,y=20+i*32;body+=`<text x="0" y="${y+14}" class="svg-label">${b.lo.toFixed(1)}–${b.hi.toFixed(1)}</text><rect class="mark" x="115" y="${y}" width="${w}" height="22" rx="4" fill="#2563eb"><title>${esc(b.subset.map(x=>`${x.program_id}: ${x.value} ${x.unit}`).join('\n')||'No records')}</title></rect><text x="${122+w}" y="${y+15}" class="svg-value">${b.subset.length}</text>`});svg('histogram',500,bins.length*32+35,body);
let sorted=[...data].sort((a,b)=>a-b),q=p=>sorted[Math.floor((sorted.length-1)*p)],lo=sorted[0],hi=sorted.at(-1),q1=q(.25),med=q(.5),q3=q(.75),scale=x=>70+(x-min)/(max-min||1)*460,box=`<line x1="${scale(lo)}" y1="92" x2="${scale(hi)}" y2="92" stroke="#1d4ed8" stroke-width="3"/><line x1="${scale(lo)}" y1="80" x2="${scale(lo)}" y2="104" stroke="#1d4ed8"/><line x1="${scale(hi)}" y1="80" x2="${scale(hi)}" y2="104" stroke="#1d4ed8"/><rect x="${scale(q1)}" y="65" width="${scale(q3)-scale(q1)}" height="54" class="box"><title>Q1 ${q1}; median ${med}; Q3 ${q3}; n=${data.length}</title></rect><line x1="${scale(med)}" y1="65" x2="${scale(med)}" y2="119" stroke="#b42318" stroke-width="3"/><text x="${scale(lo)}" y="145" class="svg-label">${lo}</text><text x="${scale(hi)-15}" y="145" class="svg-label">${hi}</text><text x="5" y="30" class="svg-label">n=${data.length} scalar values</text>`;svg('boxplot',580,170,box);
let points='';for(let x=min;x<=max+.001;x+=.025){let density=0;data.forEach(v=>{let z=(x-v)/.22;density+=Math.exp(-.5*z*z)});density/=data.length;let ww=density*110,y=96;points+=`${260-ww},${y-(x-min)/(max-min||1)*130} `}let mirror=points.trim().split(' ').reverse().map(pair=>{let [x,y]=pair.split(',');return `${520-(260-Number(x))},${y}`}).join(' ');svg('violin',540,180,`<polygon points="${points}${mirror}" fill="#99d6cc" stroke="#0f766e"/><line x1="260" y1="18" x2="260" y2="150" stroke="#0f766e"/><text x="5" y="168" class="svg-label">${min} years</text><text x="460" y="168" class="svg-label">${max} years</text><text x="5" y="18" class="svg-label">n=${data.length}; display is exploratory</text>`)}
function renderRanges(rows){let arr=filteredEvidence(D.duration_ranges);document.getElementById('ranges').innerHTML=arr.length?'<ul>'+arr.map(x=>`<li><strong>${esc(x.program_id)}</strong>: ${esc(x.value)} ${esc(x.unit)} · <a href="${esc(x.source_url)}" target="_blank" rel="noopener">source</a><details><summary>Evidence excerpt</summary>${esc(x.excerpt)} ${esc(x.scope_notes)}</details></li>`).join('')+'</ul>':'<div class="unavailable">No verified ranges in current filter.</div>'}
function renderUnavailable(rows){let ids=new Set(rows.map(x=>x.program_id)),pairs=D.paired.filter(x=>ids.has(x.program_id)),systems=[...new Set(pairs.map(x=>x.credit_system))];document.getElementById('scatter').innerHTML=`<strong>Not plotted: insufficient comparable pairs.</strong><p>${pairs.length} scalar-duration/credit pairs in the filter, across ${systems.length} credit systems; no system-specific group reaches five paired records. Regression would be unstable and would mix units.</p>`;document.getElementById('correlation').innerHTML='<strong>Not plotted: insufficient numeric overlap.</strong><p>Only three total-credit observations, one language-share value, and mixed credit systems. No meaningful comparable correlation matrix can be formed. Program IDs/codes and text lengths are not used as numeric variables.</p>'}
function renderSunburst(rows){let groups={};rows.forEach(r=>(groups[r.verification_status]??=[]).push(r));let keys=Object.keys(groups),total=Math.max(1,rows.length),cx=220,cy=150,r1=52,r2=130,start=-Math.PI/2,body='';function arc(a0,a1,ri,ro){let p=(r,x)=>[cx+r*Math.cos(x),cy+r*Math.sin(x)],A=p(ro,a0),B=p(ro,a1),C=p(ri,a1),E=p(ri,a0),large=a1-a0>Math.PI?1:0;return `M${A} A${ro} ${ro} 0 ${large} 1 ${B} L${C} A${ri} ${ri} 0 ${large} 0 ${E} Z`}keys.forEach((k,i)=>{let span=(groups[k].length/total)*Math.PI*2,end=start+span;body+=`<path class="mark arc" d="${arc(start,end,r1,r2)}" fill="${colors[i%colors.length]}"><title>${esc(k)}: ${groups[k].length} program records</title></path>`;let cur=start;groups[k].forEach((p,j)=>{let ss=span/groups[k].length,ee=cur+ss;body+=`<path class="mark arc" d="${arc(cur,ee,r2-24,r2)}" fill="${colors[i%colors.length]}" opacity="${.55+(j%4)*.1}"><title>${esc(p.program_id)} · ${esc(p.university_name)} · ${esc(k)}</title></path>`;cur=ee});start=end});svg('sunburst',440,300,`<g transform="translate(0,0)">${body}<text x="${cx-34}" y="${cy-3}" class="svg-label">${rows.length}</text><text x="${cx-43}" y="${cy+14}" class="svg-label">records</text></g>`)}
function renderNetwork(rows){let ids=new Set(rows.map(x=>x.program_id)),groups=D.courses.filter(x=>ids.has(x.program_id));let unique=[...new Set(groups.flatMap(g=>g.courses))],edges=groups.flatMap(g=>g.courses.map(c=>({id:g.program_id,course:c}))),height=Math.max(270,Math.max(groups.length,unique.length)*29+35),body='',py=new Map(),cy=new Map();groups.forEach((g,i)=>py.set(g.program_id,35+i*(height-50)/Math.max(groups.length-1,1)));unique.forEach((c,i)=>cy.set(c,24+i*(height-45)/Math.max(unique.length-1,1)));edges.forEach(e=>body+=`<line class="network-edge" x1="178" y1="${py.get(e.id)}" x2="420" y2="${cy.get(e.course)}"/>`);groups.forEach(g=>body+=`<circle class="mark node-program" cx="178" cy="${py.get(g.program_id)}" r="7"><title>${esc(g.program_id)} · ${esc(g.university_name)}; ${g.courses.length} listed courses</title></circle><text x="5" y="${py.get(g.program_id)+4}" class="node-label">${esc(g.program_id)}</text>`);unique.forEach(c=>body+=`<circle class="mark node-course" cx="420" cy="${cy.get(c)}" r="5"><title>${esc(c)} · connected to ${edges.filter(e=>e.course===c).length} listed program(s)</title></circle><text x="432" y="${cy.get(c)+3}" class="node-label">${esc(c.slice(0,48))}</text>`);svg('network',760,height,body)}
function renderCredits(rows){let arr=filteredEvidence(D.credits);document.getElementById('credits').innerHTML=arr.length?'<div class="table-wrap"><table><thead><tr><th>Program ID</th><th>Credits</th><th>Source system</th><th>Source</th></tr></thead><tbody>'+arr.map(x=>`<tr><td>${esc(x.program_id)}</td><td>${esc(x.value)}</td><td>${esc(x.unit)}</td><td><a href="${esc(x.source_url)}" target="_blank" rel="noopener">official page</a></td></tr>`).join('')+'</tbody></table></div>':'<p>No evidenced credit totals in filter.</p>'}
function renderShare(rows){let arr=filteredEvidence(D.shares);document.getElementById('share').innerHTML=arr.length?'<h3>Evidence-backed language share</h3>'+arr.map(x=>`<p><strong>${esc(x.program_id)}: ${esc(x.value)}%</strong> of courses in English · <a href="${esc(x.source_url)}" target="_blank" rel="noopener">source</a><details><summary>Excerpt</summary>${esc(x.excerpt)}</details></p>`).join(''):'<div class="unavailable"><strong>No evidenced course-language share in current filter.</strong></div>'}
function renderSources(rows){let ids=new Set(rows.map(r=>r.program_id));let evid=[...D.duration,...D.duration_ranges,...D.credits,...D.shares,...D.courses.flatMap(c=>[{program_id:c.program_id,source_url:c.source_url,excerpt:c.excerpt}])].filter(x=>ids.has(x.program_id));let unique=[...new Map(evid.map(x=>[x.source_url,x])).values()].slice(0,12);document.getElementById('sourceList').innerHTML=unique.length?'<ul>'+unique.map(x=>`<li><a href="${esc(x.source_url)}" target="_blank" rel="noopener">${esc(x.source_url)}</a> — ${esc(x.program_id)}<details><summary>Evidence excerpt</summary>${esc(x.excerpt)}</details></li>`).join('')+'</ul>':'<p>No attribute evidence in current filter.</p>'}
function renderTable(rows){document.getElementById('recordRows').innerHTML=rows.map(r=>`<tr><td>${esc(r.program_id)}</td><td>${esc(r.program_name)}</td><td>${esc(r.university_name)}</td><td>${esc(r.country)}</td><td>${esc(r.verification_status)}</td><td>${esc(r.content_status)}</td><td>${r.source_url?`<a href="${esc(r.source_url)}" target="_blank" rel="noopener">source</a>`:''}</td></tr>`).join('')}
setup();
</script></body></html>'''.replace("__DATA__", data_json).replace("__DATES__", dates)


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    print(build_dashboard_outputs(root))
