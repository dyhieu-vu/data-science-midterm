"""Collect program metadata from the official URLs in source_registry.csv."""
import csv
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "data/raw/source_registry.csv"
OUT = ROOT / "data/processed"
HEADERS = {"User-Agent": "UniversityProgramResearch/1.0 (student research)"}
IDENTITY_STOPWORDS = {"program", "bachelor", "degree", "major", "honors", "honours", "university", "vietnam", "vietnamese", "national", "college", "school", "institute", "technology", "the", "and", "of", "hanoi", "city"}
FIELDS = ["program_id", "university_id", "university_name", "program_name",
          "country", "degree_level", "source_id", "source_url", "file_name",
          "verification_status", "duration_years", "instruction_language",
          "tuition_amount", "tuition_currency", "curriculum_text",
          "curriculum_candidate_text",
          "collected_at", "http_status", "http_status_meaning",
          "content_status", "page_title", "page_content_chars",
          "identity_status", "identity_evidence", "curriculum_status",
          "collection_error"]


def _extract(text, patterns, convert=lambda x: x):
    for pattern in patterns:
        m = re.search(pattern, text, flags=re.I)
        if m:
            return convert(m.group(1).replace(",", "."))
    return None


def assess_identity(program_name, university_name, title, text):
    """Require program terms and at least one distinctive school term in page text."""
    body = f"{title} {text}".lower()
    words = lambda value: [t.lower() for t in re.findall(r"[a-zA-ZÀ-ỹ]{4,}", value) if t.lower() not in IDENTITY_STOPWORDS]
    program_tokens = words(program_name)
    university_tokens = words(university_name)
    matched_program = [t for t in program_tokens if t in body]
    matched_university = [t for t in university_tokens if t in body]
    program_ok = bool(program_tokens) and len(matched_program) == len(program_tokens)
    university_ok = bool(matched_university)

    def excerpt(term):
        idx = body.find(term)
        if idx < 0: return ""
        return body[max(0, idx - 90): min(len(body), idx + len(term) + 110)]

    evidence = (
        f"program_terms={','.join(matched_program)}; "
        f"university_terms={','.join(matched_university)}; "
        f"program_excerpt={excerpt(matched_program[0]) if matched_program else ''}; "
        f"university_excerpt={excerpt(matched_university[0]) if matched_university else ''}"
    )
    return program_ok and university_ok, evidence


def course_candidates(blocks):
    """Keep course-list-like blocks as candidates; they are not confirmed curriculum."""
    code_pattern = re.compile(r"\b[A-Z]{2,5}\s?-?\d{3,6}\b")
    candidates = []
    for block in blocks:
        snippet = re.sub(r"\s+", " ", str(block)).strip()
        if code_pattern.search(snippet) and len(snippet) > 12 and snippet not in candidates:
            candidates.append(snippet[:600])
        if len(candidates) >= 30:
            break
    return "\n".join(candidates)


def parse_program_page(html):
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    for element in soup(["script", "style", "noscript"]):
        element.decompose()
    text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))
    duration = _extract(text, [r"(?:thời gian đào tạo|duration of training|program duration|training time)\s*[:|–-]?\s*(\d+(?:[.,]\d+)?)\s*(?:năm|years?)"] , float)
    language = None
    if re.search(r"(?:ngôn ngữ đào tạo|ngôn ngữ giảng dạy|language of delivery|medium of instruction)\s*[:|–-]?\s*(?:tiếng việt|vietnamese)", text, re.I):
        language = "Vietnamese"
    elif re.search(r"(?:ngôn ngữ đào tạo|ngôn ngữ giảng dạy|language of delivery|medium of instruction)\s*[:|–-]?\s*(?:tiếng anh|english)", text, re.I):
        language = "English"
    degree_label = r"(?:danh hiệu tốt nghiệp|tên văn bằng(?: sau)?(?: tốt nghiệp)?|degree awarded|degree title)\s*[:|–-]?\s*"
    if re.search(degree_label + r"(?:cử nhân|bachelor)", text, re.I):
        degree = "Bachelor"
    elif re.search(degree_label + r"(?:kỹ sư|engineer)", text, re.I):
        degree = "Engineer"
    else:
        degree = None
    code = _extract(text, [r"mã (?:số )?ngành(?: đào tạo)?\s*[:|–-]?\s*(\d{7})"])
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    blocks = [node.get_text(" ", strip=True) for node in soup.find_all(["p", "li", "tr"])]
    curriculum_candidates = course_candidates(blocks)
    return title, duration, language, degree, code, text, curriculum_candidates


def set_page_evidence(row, title, text, curriculum):
    """Store course-like excerpts as candidates, never as confirmed curriculum."""
    row["page_title"] = title
    row["page_content_chars"] = len(text)
    row["content_status"] = "content_available" if len(text) >= 80 else "empty_or_insufficient_content"
    row["curriculum_text"] = ""
    row["curriculum_candidate_text"] = curriculum
    row["curriculum_status"] = "candidate_requires_manual_scope_review" if curriculum else "not_extracted_no_explicit_course_entries"


def set_collection_failure(row, exc):
    row["collection_error"] = f"{type(exc).__name__}: {exc}"
    row["verification_status"] = "source_error"
    row["http_status_meaning"] = (
        "HTTP response received; later processing failed"
        if row.get("http_status")
        else "request failed before HTTP response"
    )
    if row.get("content_status") == "not_checked":
        row["content_status"] = "not_available_due_to_error"
    if row.get("curriculum_status") == "not_checked":
        row["curriculum_status"] = "not_collected_due_to_source_error"


def collect_one(source, session=None):
    import requests

    if session is None:
        session = requests
    now = datetime.now(timezone.utc).isoformat()
    row = {k: "" for k in FIELDS}
    row.update({k: source.get(k, "") for k in ("program_id", "university_id", "university_name", "program_name", "source_id", "source_url", "file_name")})
    row.update(country="Vietnam", collected_at=now, http_status="", http_status_meaning="not_requested", content_status="not_checked", page_title="", page_content_chars="", identity_status="not_checked", identity_evidence="", curriculum_status="not_checked", collection_error="", verification_status="needs_manual_review")
    parsed = urlparse(source["source_url"])
    try:
        robot_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        rr = session.get(robot_url, headers=HEADERS, timeout=12)
        if rr.status_code == 200:
            rp = RobotFileParser(); rp.parse(rr.text.splitlines())
            if not rp.can_fetch(HEADERS["User-Agent"], source["source_url"]):
                row["verification_status"] = "blocked_by_robots"
                return row
        elif rr.status_code != 404:
            row["verification_status"] = "robots_unavailable"
            row["collection_error"] = f"robots.txt returned HTTP {rr.status_code}; skipped source"
            return row
        response = session.get(source["source_url"], headers=HEADERS, timeout=20)
        row["http_status"] = response.status_code
        response.raise_for_status()
        title, duration, language, degree, code, text, curriculum = parse_program_page(response.text)
        row["http_status_meaning"] = "HTTP response received; 2xx means request succeeded"
        set_page_evidence(row, title, text, curriculum)
        row["duration_years"] = duration if duration is not None else ""
        row["instruction_language"] = language or ""
        row["degree_level"] = degree or ""
        row["program_code"] = code or ""
        identity_match, identity_evidence = assess_identity(source["program_name"], source["university_name"], title, text)
        row["identity_status"] = "program_and_university_matched" if identity_match else "manual_review_required"
        row["identity_evidence"] = identity_evidence
        if response.status_code == 200 and row["content_status"] == "content_available" and identity_match:
            row["verification_status"] = "verified_identity"
    except Exception as exc:
        set_collection_failure(row, exc)
    return row


def main():
    with REGISTRY.open(encoding="utf-8-sig", newline="") as f:
        sources = list(csv.DictReader(f))
    if not sources:
        raise ValueError(f"Source registry is empty: {REGISTRY}")
    seen = set(); rows = []; duplicates = 0
    for i, source in enumerate(sources):
        if source["program_id"] in seen:
            duplicates += 1; continue
        seen.add(source["program_id"])
        rows.append(collect_one(source))
        if i < len(sources) - 1: time.sleep(1)
    OUT.mkdir(parents=True, exist_ok=True)
    for filename, fields, data in [
        ("programs_expanded.csv", FIELDS + ["program_code"], rows),
        ("sources.csv", ["source_id", "source_url", "file_name", "collected_at", "http_status", "http_status_meaning", "content_status", "identity_status", "curriculum_status", "verification_status", "collection_error"], rows),
        ("universities.csv", ["university_id", "university_name", "country"], list({(r["university_id"],r["university_name"],r["country"]) for r in rows}))]:
        with (OUT / filename).open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields); w.writeheader()
            if filename == "universities.csv":
                w.writerows(dict(zip(fields, x)) for x in data)
            elif filename == "sources.csv":
                w.writerows({k:r.get(k,"") for k in fields} for r in data)
            else: w.writerows(data)
    print(f"Programs retained: {len(rows)}; duplicate IDs skipped: {duplicates}")
    print(f"HTTP 2xx responses: {sum(str(r['http_status']).startswith('2') for r in rows)} / {len(rows)}")
    print(f"Readable page content: {sum(r['content_status'] == 'content_available' for r in rows)}; identity matches (program + university): {sum(r['identity_status'] == 'program_and_university_matched' for r in rows)}")
    print(f"Course-list candidate snippets: {sum(bool(r.get('curriculum_candidate_text')) for r in rows)}; confirmed curriculum text: {sum(bool(r.get('curriculum_text')) for r in rows)}")
    print("verification_status=verified_identity means identity evidence only; it does not verify every attribute.")
    print("collection_error is intentionally blank when no collection exception occurred.")


if __name__ == "__main__": main()
