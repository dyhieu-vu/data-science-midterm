"""Create a reproducible, row-level audit from saved CSV snapshots (offline)."""
import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/processed/programs_expanded.csv"
REGISTRY = ROOT / "data/raw/source_registry.csv"
SOURCES = ROOT / "data/processed/sources.csv"
CLEAN = ROOT / "data/processed/programs_clean.csv"
ORIGINAL = ROOT / "data/processed/programs.csv"
REPORT = ROOT / "data/processed/program_audit.csv"

EVIDENCE_FIELDS = ("degree_level", "duration_years", "instruction_language", "program_code", "curriculum_text")
MISSING_FIELDS = ("degree_level", "duration_years", "instruction_language", "tuition_amount", "tuition_currency", "program_code", "curriculum_text")

CURRICULUM_REVIEW = {
    "VN001_AI": "Program identity/objectives plus unrelated PhD credit requirements and Materials Engineering text; not a curriculum.",
    "VN003_AI": "Navigation and program overview only in crawl snippet. Separate saved sample contains an actual 138-credit course structure; see manual_evidence.csv and review current source.",
    "VN005_AI_MAJOR": "Menu/AI overview mixed with a Data Science course-structure fragment; scope is ambiguous for AI Major.",
    "VN006_DS": "Overview/objectives and data science subject areas; no course list in stored snippet.",
    "VN007_DSE": "Program objectives/outcomes; no course list in stored snippet.",
    "VN008_DS": "Contains course descriptions and Data Science curriculum framework references; candidate content, verify it is the program curriculum and retain relevant section only.",
    "VN009_AI": "Learning outcomes and general program description; no course list in stored snippet.",
    "VN010_DS": "Learning outcomes and general program description; no course list in stored snippet.",
    "VN011_AI": "Program description and learning outcomes; no course list in stored snippet.",
    "VN012_AI": "Program overview and career roles; no course list in stored snippet.",
}


def classify_source_error(error, http_status=""):
    if not error:
        return "No collection_error recorded"
    if "Failed to resolve" in error or "NameResolutionError" in error:
        return "Connection/name-resolution failure while requesting robots.txt; program URL was not requested"
    if "Timeout" in error:
        return "Timeout recorded"
    if http_status and not str(http_status).startswith("2"):
        return f"Non-2xx HTTP response recorded: {http_status}"
    if "HTTPError" in error:
        return "HTTP error raised after response"
    return "Recorded processing/request exception; see exact collection_error"


def read_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def read_header(path):
    with path.open(encoding="utf-8-sig", newline="") as f:
        return next(csv.reader(f), [])


def audit_rows(programs, registry, sources):
    reg = {r["program_id"]: r for r in registry}
    source_by_key = {(r.get("source_id", ""), r.get("source_url", "")): r for r in sources}
    audit = []
    for p in programs:
        r = reg.get(p.get("program_id", ""), {})
        s = source_by_key.get((p.get("source_id", ""), p.get("source_url", "")), {})
        fields = [name for name in EVIDENCE_FIELDS if p.get(name, "").strip()]
        missing = [name for name in MISSING_FIELDS if not p.get(name, "").strip()]
        reasons = []
        if not r:
            reasons.append("program_id not found in registry")
        elif r.get("source_url") != p.get("source_url") or r.get("source_id") != p.get("source_id"):
            reasons.append("registry source_id/URL mismatch")
        if not s:
            reasons.append("no matching sources.csv row")
        elif s.get("http_status") != "200":
            reasons.append("HTTP status is not 200")
        else:
            reasons.append("HTTP 200 only proves an HTTP response; saved snapshot has no title/body evidence to assess page content")
        source_status_matches = bool(s) and all(
            s.get(field, "") == p.get(field, "")
            for field in ("http_status", "verification_status", "collection_error", "curriculum_status")
        )
        if not source_status_matches:
            reasons.append("sources.csv and programs_expanded.csv status/error fields differ")
        if fields:
            reasons.append("populated attributes have no saved page excerpt/provenance; populated is not the same as independently evidenced")
        if p.get("verification_status") == "source_error":
            recommended = "source_error"
        elif (p.get("verification_status") == "verified_identity"
              and p.get("content_status") == "content_available"
              and p.get("identity_status") == "program_and_university_matched"
              and p.get("identity_evidence", "").find("program_excerpt=") >= 0):
            recommended = "verified_identity (identity only)"
        else:
            recommended = "needs_manual_review"
            reasons.append("program and institution identity evidence is missing or incomplete")
        if not p.get("file_name", "").strip():
            reasons.append("no local page sample; identity/content cannot be independently replayed offline")
        program_id = p.get("program_id", "")
        special = {
            "VN001_AI": "UET record is explicitly an honors/talent variant; confirm this is intended as a distinct program record.",
            "VN002_DS_AI": "Combined Data Science and AI degree; do not classify as a Data Science-only degree without checking the award/program structure.",
            "VN005_AI_MAJOR": "Configured as a major/track; confirm it is a standalone undergraduate program before counting it as an independent degree.",
            "VN009_AI": "UIT source URL is cohort 20 / 2025; treat as that cohort edition, not automatically as a separate program from later editions.",
            "VN010_DS": "UIT source URL is cohort 20 / 2025; treat as that cohort edition, not automatically as a separate program from later editions.",
            "VN013_AI": "Extracted code 7480210 appears inconsistent with an AI label; inspect the source section and confirm the official code.",
            "VN014_AI": "Confirm the linked page describes a standalone AI program rather than a specialization or curriculum track.",
        }
        if program_id in special:
            reasons.append(special[program_id])
        error_class = classify_source_error(p.get("collection_error", ""), p.get("http_status", ""))
        curriculum_quality = CURRICULUM_REVIEW.get(program_id, "No collected curriculum candidate in this snapshot.")
        if p.get("curriculum_status") == "not_collected_due_to_source_error":
            curriculum_quality = "Not assessed because collection failed before the program page was retrieved."
        audit.append({
            "program_id": program_id,
            "university_name": p.get("university_name", ""),
            "program_name": p.get("program_name", ""),
            "source_url": p.get("source_url", ""),
            "http_status": p.get("http_status", ""),
            "content_status": p.get("content_status", ""),
            "identity_status": p.get("identity_status", ""),
            "curriculum_status": p.get("curriculum_status", ""),
            "collection_error_classification": error_class,
            "fields_with_values_in_snapshot": ";".join(fields),
            "value_evidence_limit": "snapshot retains values and URL, but not the page excerpt/selector for each extracted value; recheck attributes against the source",
            "fields_missing": ";".join(missing),
            "collection_error": p.get("collection_error", ""),
            "collection_error_meaning": "blank means no collection exception was recorded; it is not a missing program attribute",
            "curriculum_missing_reason": (
                "candidate snippets preserved separately; not promoted because snippet relevance/scope was unconfirmed"
                if p.get("curriculum_candidate_text", "").strip()
                else "no program-specific course-list text recorded; source error means page was not assessed"
                if p.get("verification_status") == "source_error"
                else "no program-specific course-list text recorded"
            ),
            "curriculum_quality_review": curriculum_quality,
            "curriculum_candidate_present": "yes" if p.get("curriculum_candidate_text", "").strip() else "no",
            "source_program_status_fields_match": str(source_status_matches).lower(),
            "sources_http_status": s.get("http_status", ""),
            "sources_verification_status": s.get("verification_status", ""),
            "sources_collection_error": s.get("collection_error", ""),
            "manual_snapshot_evidence": "see data/processed/manual_evidence.csv" if program_id in {"VN003_AI", "VN005_AI_MAJOR"} else "",
            "legacy_verification_status": p.get("verification_status", ""),
            "recommended_status": recommended,
            "review_reason": " | ".join(reasons),
        })
    return audit


def main():
    programs, registry, sources, clean, original = map(read_csv, (RAW, REGISTRY, SOURCES, CLEAN, ORIGINAL))
    audit = audit_rows(programs, registry, sources)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    with REPORT.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(audit[0]) if audit else [])
        writer.writeheader(); writer.writerows(audit)
    ids = [r.get("program_id", "") for r in programs]
    registry_ids = {r.get("program_id", "") for r in registry}
    clean_ids = [r.get("program_id", "") for r in clean]
    original_ids = {r.get("program_id", "") for r in original}
    urls = [r.get("source_url", "") for r in programs]
    program_columns = read_header(RAW)
    source_columns = read_header(SOURCES)
    clean_columns = read_header(CLEAN)
    print(f"Rows: programs_expanded={len(programs)}; registry={len(registry)}; sources={len(sources)}; clean={len(clean)}; original programs.csv={len(original)}")
    print(f"Columns: programs_expanded={len(program_columns)}; sources={len(source_columns)}; programs_clean={len(clean_columns)}")
    print(f"Registry matches={sum(x in registry_ids for x in ids)}/{len(ids)}; sources matches={sum((p.get('source_id'),p.get('source_url')) in {(s.get('source_id'),s.get('source_url')) for s in sources} for p in programs)}/{len(programs)}")
    print(f"HTTP 2xx={sum(str(r.get('http_status','')).startswith('2') for r in programs)}/{len(programs)}; source_error={sum(r.get('verification_status') == 'source_error' for r in programs)}; verified_identity={sum(r.get('verification_status') == 'verified_identity' for r in programs)}; needs_manual_review={sum(r.get('verification_status') == 'needs_manual_review' for r in programs)}")
    print(f"sources.csv row pair/status/error consistency={sum(bool(a['source_program_status_fields_match']=='true') for a in audit)}/{len(audit)}")
    print(f"Distinct URLs={len(set(urls))}/{len(urls)}; duplicate program IDs={len(ids)-len(set(ids))}; clean ID set matches expanded={set(clean_ids)==set(ids)}; original 5 IDs still present={original_ids.issubset(set(ids))}")
    print("Audit report written to data/processed/program_audit.csv")


if __name__ == "__main__": main()
