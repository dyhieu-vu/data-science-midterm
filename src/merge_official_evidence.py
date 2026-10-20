"""Merge verified, structured attributes from the official evidence ledger."""

import csv
import json
from decimal import Decimal, InvalidOperation
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_FILE = ROOT / "data" / "processed" / "official_attribute_evidence.csv"
PROGRAMS_FILE = ROOT / "data" / "processed" / "programs_expanded.csv"

NEW_COLUMNS = [
    "duration_range_years",
    "total_credits",
    "credit_system",
    "award_title",
    "instruction_language_share",
    "curriculum_course_list",
]


def _one_value(rows, program_id, field):
    values = {row["value"].strip() for row in rows if row["value"].strip()}
    if len(values) > 1:
        raise ValueError(f"Conflicting verified values for {program_id}/{field}: {sorted(values)}")
    return next(iter(values), "")


def _duration_number(value):
    """Parse a single plausible duration in years; ranges and invalid values are excluded."""
    try:
        number = Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        return None
    if not number.is_finite() or not Decimal("1") <= number <= Decimal("8"):
        return None
    return number


def _normalize_language(value):
    """Normalize whitespace and case for equality checks; retain the display label."""
    label = " ".join(str(value or "").split())
    return (label.casefold(), label) if label else None


def merge_official_evidence(evidence_path=EVIDENCE_FILE, programs_path=PROGRAMS_FILE):
    """Add evidence-backed attributes; preserve all existing program columns and rows."""
    with Path(evidence_path).open(encoding="utf-8-sig", newline="") as f:
        evidence_reader = csv.DictReader(f)
        evidence = list(evidence_reader)
        evidence_fields = set(evidence_reader.fieldnames or [])
    required_evidence = {"program_id", "field", "value", "unit", "evidence_status"}
    if not required_evidence.issubset(evidence_fields):
        raise ValueError(f"Evidence schema missing: {sorted(required_evidence - evidence_fields)}")

    with Path(programs_path).open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        programs = list(reader)
        fields = list(reader.fieldnames or [])
    required_program_fields = {"program_id", "duration_years", "instruction_language"}
    if not required_program_fields.issubset(fields):
        raise ValueError(
            f"Programs schema missing required fields: {sorted(required_program_fields - set(fields))}"
        )
    ids = [row["program_id"] for row in programs]
    if len(ids) != len(set(ids)):
        raise ValueError("programs_expanded.csv contains duplicate program_id")
    known_ids = set(ids)

    verified = [r for r in evidence if r["evidence_status"].strip() == "verified_official_source"]
    unknown = sorted({r["program_id"] for r in verified} - known_ids)
    if unknown:
        raise ValueError(f"Evidence references unknown program_id: {unknown}")
    by_key = {}
    for row in verified:
        by_key.setdefault((row["program_id"], row["field"]), []).append(row)

    merge_stats = {
        "added": 0,
        "retained_equal": 0,
        "conflicts": 0,
        "evidence_ignored": sum(
            r.get("field", "").strip() == "duration_years"
            and r.get("evidence_status", "").strip() != "verified_official_source"
            for r in evidence
        ),
        "instruction_language_added": 0,
        "instruction_language_retained_equal": 0,
        "instruction_language_conflicts": 0,
        "instruction_language_evidence_ignored": sum(
            r.get("field", "").strip() == "instruction_language"
            and (
                r.get("evidence_status", "").strip() != "verified_official_source"
                or _normalize_language(r.get("value", "")) is None
            )
            for r in evidence
        ),
    }

    mappings = {
        "duration_range_years": "duration_range_years",
        "total_credits": "total_credits",
        "award_title": "award_title",
        "instruction_language_share": "instruction_language_share",
        "curriculum_course_list": "curriculum_course_list",
    }
    out_fields = fields + [c for c in NEW_COLUMNS if c not in fields]
    for program in programs:
        pid = program["program_id"]
        for col in NEW_COLUMNS:
            program.setdefault(col, "")
        for source_field, target_col in mappings.items():
            rows = by_key.get((pid, source_field), [])
            value = _one_value(rows, pid, source_field)
            if source_field == "instruction_language_share" and not value:
                # Preserve the existing percentage when this run has no verified
                # share evidence; it is distinct from the language label below.
                value = program.get(target_col, "")
            if source_field == "curriculum_course_list" and value:
                # Ledger values are semicolon-delimited course names, not prose snippets.
                courses = [part.strip() for part in value.split(";") if part.strip()]
                value = json.dumps(courses, ensure_ascii=False)
            program[target_col] = value

        # Scalar duration is an existing field, so merge it conservatively rather
        # than treating it as one of the newly introduced columns above.
        raw_duration_rows = [
            r for r in evidence
            if r.get("program_id", "").strip() == pid
            and r.get("field", "").strip() == "duration_years"
        ]
        merge_stats["evidence_ignored"] += sum(
            r.get("evidence_status", "").strip() == "verified_official_source"
            and _duration_number(r.get("value", "")) is None
            for r in raw_duration_rows
        )
        duration_rows = by_key.get((pid, "duration_years"), [])
        numeric_values = {}
        for row in duration_rows:
            number = _duration_number(row.get("value", ""))
            if number is not None:
                numeric_values.setdefault(number, row["value"].strip())
        if len(numeric_values) > 1:
            merge_stats["conflicts"] += 1
            raise ValueError(
                f"Duration conflict for {pid}/duration_years: "
                f"verified values {sorted(str(v) for v in numeric_values)}"
            )
        evidence_duration = next(iter(numeric_values.items()), None)
        if evidence_duration is not None:
            evidence_number, evidence_text = evidence_duration
            current_text = program.get("duration_years", "").strip()
            if not current_text:
                program["duration_years"] = evidence_text
                merge_stats["added"] += 1
            else:
                current_number = _duration_number(current_text)
                if current_number is None or current_number != evidence_number:
                    merge_stats["conflicts"] += 1
                    raise ValueError(
                        f"Duration conflict for {pid}/duration_years: "
                        f"existing={current_text!r}, verified={evidence_text!r}"
                    )
                merge_stats["retained_equal"] += 1

        # Teaching-language labels are separate from the English-course share.
        # Resolve only verified, nonblank language evidence and never silently
        # replace a populated source value.
        language_rows = by_key.get((pid, "instruction_language"), [])
        normalized_languages = {}
        for row in language_rows:
            normalized = _normalize_language(row.get("value", ""))
            if normalized is not None:
                normalized_languages.setdefault(normalized[0], normalized[1])
        if len(normalized_languages) > 1:
            merge_stats["instruction_language_conflicts"] += 1
            raise ValueError(
                f"Conflicting verified values for {pid}/instruction_language: "
                f"{sorted(normalized_languages.values())}"
            )
        evidence_language = next(iter(normalized_languages.items()), None)
        if evidence_language is not None:
            evidence_key, evidence_label = evidence_language
            current_language = _normalize_language(program.get("instruction_language", ""))
            if current_language is None:
                program["instruction_language"] = evidence_label
                merge_stats["instruction_language_added"] += 1
            elif current_language[0] != evidence_key:
                merge_stats["instruction_language_conflicts"] += 1
                raise ValueError(
                    f"Conflict for {pid}/instruction_language: "
                    f"existing={current_language[1]!r}, verified={evidence_label!r}"
                )
            else:
                merge_stats["instruction_language_retained_equal"] += 1
        credit_rows = by_key.get((pid, "total_credits"), [])
        units = {r["unit"].strip() for r in credit_rows if r["unit"].strip()}
        if len(units) > 1:
            raise ValueError(f"Conflicting credit systems for {pid}: {sorted(units)}")
        program["credit_system"] = next(iter(units), "")

    # Refuse a pre-existing ID/data mismatch instead of silently overwriting it.
    # All columns written here are newly introduced in the current schema.
    with Path(programs_path).open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=out_fields)
        writer.writeheader()
        writer.writerows(programs)
    return programs, out_fields, merge_stats


if __name__ == "__main__":
    rows, columns, merge_stats = merge_official_evidence()
    print(f"Updated programs_expanded.csv: {len(rows)} rows, {len(columns)} columns")
    print(
        "duration_years: "
        f"added={merge_stats['added']}; retained_equal={merge_stats['retained_equal']}; "
        f"conflicts={merge_stats['conflicts']}; "
        f"unverified_or_invalid_evidence_ignored={merge_stats['evidence_ignored']}"
    )
    print(
        "instruction_language: "
        f"added={merge_stats['instruction_language_added']}; "
        f"retained_equal={merge_stats['instruction_language_retained_equal']}; "
        f"conflicts={merge_stats['instruction_language_conflicts']}; "
        f"unverified_or_empty_evidence_ignored={merge_stats['instruction_language_evidence_ignored']}"
    )
    for column in NEW_COLUMNS:
        present = sum(bool(row[column]) for row in rows)
        print(f"{column}: {present} populated, {len(rows) - present} NA")
