"""Offline CSV validation and completeness report for the collected dataset."""
import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "data/processed/programs_expanded.csv"
REQUIRED = ("program_id", "university_id", "university_name", "program_name", "source_url", "collected_at", "verification_status")


def validate_rows(rows, columns):
    errors = []
    missing_columns = sorted(set(REQUIRED) - set(columns))
    if missing_columns: errors.append(f"Missing columns: {missing_columns}")
    ids = [r.get("program_id", "").strip() for r in rows]
    if not all(ids): errors.append("program_id contains blank values")
    if len(set(ids)) != len(ids): errors.append("program_id contains duplicates")
    for i, row in enumerate(rows, 2):
        for col in REQUIRED:
            if not row.get(col, "").strip(): errors.append(f"row {i}: required {col} is blank")
        duration = row.get("duration_years", "").strip()
        if duration:
            try:
                if not 1 <= float(duration) <= 8: errors.append(f"row {i}: duration_years outside 1–8")
            except ValueError: errors.append(f"row {i}: duration_years is not numeric")
        status = row.get("verification_status", "")
        if status == "source_error" and not row.get("collection_error", "").strip():
            errors.append(f"row {i}: source_error has no collection_error detail")
        if status == "verified_identity":
            identity_requirements = {
                "http_status": "200",
                "content_status": "content_available",
                "identity_status": "program_and_university_matched",
            }
            for field, expected in identity_requirements.items():
                if row.get(field, "") != expected:
                    errors.append(f"row {i}: verified_identity requires {field}={expected}")
            evidence = row.get("identity_evidence", "")
            if "program_excerpt=" not in evidence or "university_excerpt=" not in evidence:
                errors.append(f"row {i}: verified_identity requires saved program and university excerpts")
    return errors


def main():
    if not DATA_PATH.exists():
        raise FileNotFoundError(f"Run python src/collect_data.py first: {DATA_PATH}")
    with DATA_PATH.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f); columns = reader.fieldnames or []; rows = list(reader)
    errors = validate_rows(rows, columns)
    print(f"Rows: {len(rows)} | columns: {len(columns)}")
    print("Validation: " + ("PASS" if not errors else "FAIL"))
    for err in errors: print(" - " + err)
    print("Source status counts:")
    for status in sorted({r.get("verification_status", "") for r in rows}):
        print(f" {status or '(missing)'}: {sum(r.get('verification_status') == status for r in rows)}")
    # This column is an error-only field: blank means no exception was recorded.
    expected_blank = {"collection_error"}
    print("Missingness by column (error-only fields reported separately):")
    for col in columns:
        n = sum(not r.get(col, "").strip() for r in rows)
        if n and col not in expected_blank: print(f" {col}: {n}/{len(rows)} ({100*n/len(rows):.1f}%)")
    if "collection_error" in columns:
        errors_seen = sum(bool(r.get("collection_error", "").strip()) for r in rows)
        print(f"Recorded collection exceptions: {errors_seen}/{len(rows)} (blank means no exception was recorded)")
    review = [r["program_id"] for r in rows if r.get("verification_status") != "verified_identity"]
    print("Manual review required: " + (", ".join(review) if review else "none"))
    if errors: raise SystemExit(1)


if __name__ == "__main__": main()
