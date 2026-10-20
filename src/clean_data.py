
from pathlib import Path
import csv
import json
import re


# =========================================================
# 1. CẤU HÌNH ĐƯỜNG DẪN
# =========================================================

ROOT = Path(__file__).resolve().parents[1]
INPUT_FILE = ROOT / "data" / "processed" / "programs_expanded.csv"
OUTPUT_FILE = ROOT / "data" / "processed" / "programs_clean.csv"
MISSING_REPORT = (
    ROOT / "data" / "processed" / "missing_values_report.csv"
)


def tri_state_presence(value, is_missing):
    """Return True when evidence is present, missing when availability is unknown."""
    return None if is_missing else True


def curriculum_presence(value, is_missing, curriculum_status, content_status):
    """False means a readable page was checked and no program curriculum was found."""
    if not is_missing:
        return True
    if (
        str(curriculum_status) == "no_program_specific_curriculum_found"
        and str(content_status) == "content_available"
    ):
        return False
    return None


def range_validity(value, is_missing, minimum, maximum=None):
    """Keep validity unknown when the source value itself is missing."""
    if is_missing:
        return None
    return value >= minimum and (maximum is None or value <= maximum)


def normalize_course_list_json(value):
    """Validate the evidence-backed course list without consulting candidate text."""
    text = "" if value is None else str(value).strip()
    if text in {"", "<NA>", "nan"}:
        return None
    try:
        parsed = json.loads(text)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValueError("curriculum_course_list must contain valid JSON") from exc
    if not isinstance(parsed, list) or not all(isinstance(item, str) for item in parsed):
        raise ValueError("curriculum_course_list must be a JSON array of strings")
    return json.dumps(parsed, ensure_ascii=False)


# =========================================================
# 2. ĐỌC DỮ LIỆU
# =========================================================

def load_data():
    import pandas as pd

    if not INPUT_FILE.exists():
        raise FileNotFoundError(
            f"Không tìm thấy dữ liệu đầu vào: {INPUT_FILE}\n"
            "Hãy chạy python src/collect_data.py trước."
        )

    df = pd.read_csv(INPUT_FILE, encoding="utf-8-sig")
    print(f"Đã đọc dữ liệu: {len(df)} dòng, {len(df.columns)} cột")
    return df


# =========================================================
# 3. CHUẨN HÓA DỮ LIỆU
# =========================================================

def clean_data(df):
    import pandas as pd

    df = df.copy()

    # Chuẩn hóa khoảng trắng và chuỗi rỗng.
    string_columns = df.select_dtypes(
        include=["object", "string"]
    ).columns

    for col in string_columns:
        df[col] = (
            df[col]
            .astype("string")
            .str.replace(r"\s+", " ", regex=True)
            .str.strip()
        )
        df[col] = df[col].replace("", pd.NA)

    # Chuẩn hóa kiểu số.
    numeric_columns = [
        "duration_years",
        "duration_months",
        "tuition_amount",
        "curriculum_word_count",
        "total_credits",
        "instruction_language_share",
    ]

    for col in numeric_columns:
        if col in df.columns:
            df[col] = pd.to_numeric(
                df[col], errors="coerce"
            )

    # Nullable numeric types retain unknowns as NA in the cleaned dataset.
    for col in ("total_credits", "instruction_language_share"):
        if col in df.columns:
            df[col] = df[col].astype("Float64")

    if "instruction_language_share" in df.columns:
        share = df["instruction_language_share"]
        invalid_share = share.notna() & ~share.between(0, 100)
        if invalid_share.any():
            raise ValueError(
                "instruction_language_share must be between 0 and 100; "
                f"invalid rows: {df.index[invalid_share].tolist()}"
            )

    if "curriculum_course_list" in df.columns:
        df["curriculum_course_list"] = df["curriculum_course_list"].map(
            normalize_course_list_json
        ).astype("string")

    # Chuẩn hóa thời điểm thu thập.
    if "collected_at" in df.columns:
        df["collected_at"] = pd.to_datetime(
            df["collected_at"],
            errors="coerce",
            utc=True,
        )

    # Không tự điền giá trị thiếu bằng 0 hoặc giá trị trung bình.
    # Loại bỏ các dòng giống hệt nhau hoàn toàn.
    before = len(df)
    df = df.drop_duplicates().copy()
    exact_duplicates_removed = before - len(df)

    # ID chương trình phải duy nhất.
    if "program_id" in df.columns:
        duplicated_ids = df.loc[
            df["program_id"].duplicated(keep=False),
            "program_id",
        ].dropna().unique()

        if len(duplicated_ids) > 0:
            raise ValueError(
                "Phát hiện program_id bị trùng: "
                f"{duplicated_ids.tolist()}. "
                "Hãy kiểm tra nguồn trước khi tiếp tục."
            )

    # Không tự xóa các thời lượng bất thường:
    # tạo cờ để có thể rà soát và truy nguyên.
    
    if "duration_years" in df.columns:
        df["duration_valid"] = df["duration_years"].map(
            lambda value: range_validity(value, pd.isna(value), 1, 8)
        ).astype("boolean")

    # Học phí phải không âm; giá trị âm được đánh dấu
    # không hợp lệ thay vì âm thầm biến đổi.
    
    if "tuition_amount" in df.columns:
        df["tuition_valid"] = df["tuition_amount"].map(
            lambda value: range_validity(value, pd.isna(value), 0)
        ).astype("boolean")

    print(f"Số dòng trùng hoàn toàn đã loại: {exact_duplicates_removed}")

    return df


# =========================================================
# 4. TẠO ĐẶC TRƯNG
# =========================================================

def create_features(df):
    import pandas as pd

    df = df.copy()

    
    # Chuẩn hóa thời lượng đơn lẻ và khoảng thời lượng.
    # Không tự thay duration_years bằng trung bình của một khoảng.
    if "duration_years" in df.columns:
        df["duration_months"] = df["duration_years"] * 12

        # Mặc định khoảng thời lượng từ giá trị đơn lẻ, nếu có.
        df["duration_min_years"] = df["duration_years"]
        df["duration_max_years"] = df["duration_years"]

        # Đọc khoảng có dạng "3.5-4", "4-4.5".
        if "duration_range_years" in df.columns:
            import re

            def parse_duration_range(value):
                if pd.isna(value):
                    return (pd.NA, pd.NA)

                text = str(value).strip().replace(",", ".")
                match = re.fullmatch(
                    r"(\d+(?:\.\d+)?)\s*[-–—]\s*(\d+(?:\.\d+)?)",
                    text,
                )
                if not match:
                    return (pd.NA, pd.NA)

                minimum, maximum = map(float, match.groups())
                if not (1 <= minimum <= maximum <= 8):
                    return (pd.NA, pd.NA)

                return (minimum, maximum)

            parsed_ranges = df["duration_range_years"].map(
                parse_duration_range
            )
            range_min = parsed_ranges.map(lambda pair: pair[0])
            range_max = parsed_ranges.map(lambda pair: pair[1])

            # Ưu tiên khoảng đã được xác minh khi có sẵn.
            has_range = range_min.notna() & range_max.notna()

            # Chuyển sang kiểu nullable Float64 trước khi cập nhật khoảng.
            df["duration_min_years"] = pd.to_numeric(
                df["duration_min_years"], errors="coerce"
            ).astype("Float64")

            df["duration_max_years"] = pd.to_numeric(
                df["duration_max_years"], errors="coerce"
            ).astype("Float64")

            df.loc[has_range, "duration_min_years"] = (
                range_min.loc[has_range].astype("Float64")
            )
            df.loc[has_range, "duration_max_years"] = (
                range_max.loc[has_range].astype("Float64")
            )

        # Nhóm thời lượng chính xác chỉ áp dụng khi biết một giá trị đơn lẻ.
        df["duration_group"] = pd.cut(
            df["duration_years"],
            bins=[0, 3, 4, 8],
            labels=[
                "3 năm trở xuống",
                "Trên 3 đến 4 năm",
                "Trên 4 đến 8 năm",
            ],
            include_lowest=True,
        ).astype("string")


    # Cờ cho biết thuộc tính có dữ liệu hay chưa.
    if "tuition_amount" in df.columns:
        df["has_tuition"] = df["tuition_amount"].map(
            lambda value: tri_state_presence(value, pd.isna(value))
        ).astype("boolean")
        df["tuition_status"] = "unknown"
        df.loc[df["tuition_amount"].notna(), "tuition_status"] = "amount_recorded"
        if "tuition_currency" in df.columns:
            currency_only = df["tuition_amount"].isna() & df["tuition_currency"].notna()
            df.loc[currency_only, "tuition_status"] = "currency_only"

    if "instruction_language" in df.columns:
        df["language_known"] = df["instruction_language"].map(
            lambda value: tri_state_presence(value, pd.isna(value))
        ).astype("boolean")

    if "degree_level" in df.columns:
        df["degree_level_known"] = df["degree_level"].map(
            lambda value: tri_state_presence(value, pd.isna(value))
        ).astype("boolean")

    if "curriculum_text" in df.columns:
        curriculum = (
            df["curriculum_text"]
            .fillna("")
            .astype(str)
            .str.strip()
        )

        status = df.get("curriculum_status", pd.Series("", index=df.index))
        content_status = df.get("content_status", pd.Series("", index=df.index))
        df["has_curriculum_text"] = [
            curriculum_presence(value, not bool(value), cs, ps)
            for value, cs, ps in zip(curriculum, status, content_status)
        ]
        df["has_curriculum_text"] = df["has_curriculum_text"].astype("boolean")
        word_count = curriculum.str.split().str.len().astype("Int64")
        confirmed_empty = (
            df["curriculum_status"].eq("no_program_specific_curriculum_found")
            & df["content_status"].eq("content_available")
            if "curriculum_status" in df.columns and "content_status" in df.columns
            else pd.Series(False, index=df.index)
        )
        word_count.loc[curriculum.eq("") & ~confirmed_empty] = pd.NA
        word_count.loc[curriculum.eq("") & confirmed_empty] = 0
        df["curriculum_word_count"] = word_count

    # Số ký tự tên chương trình.
    if "program_name" in df.columns:
        df["program_name_length"] = (
            df["program_name"].fillna("").str.len()
        )

    return df


# =========================================================
# 5. BÁO CÁO GIÁ TRỊ THIẾU
# =========================================================

def create_missing_report(df):
    import pandas as pd

    records = []
    for col in df.columns:
        error_only = col == "collection_error"
        missing_count = 0 if error_only else int(df[col].isna().sum())
        records.append({
            "column": col,
            "missing_count": missing_count,
            "missing_percent": round(missing_count / len(df) * 100, 2) if len(df) else 0,
            "data_type": str(df[col].dtype),
            "recorded_exception_count": int(df[col].notna().sum()) if error_only else "",
            "notes": "error-only field; blank means no exception recorded" if error_only else "",
        })
    report = pd.DataFrame(records)

    report = report.sort_values(
        "missing_percent", ascending=False
    )

    return report


def _clean_csv_fallback():
    """Use the same missing-value rules with stdlib CSV when pandas is unavailable."""
    with INPUT_FILE.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        columns = list(reader.fieldnames or [])
        raw_rows = list(reader)
    rows = []
    seen_ids = set()
    seen_rows = set()
    for raw in raw_rows:
        row = {k: re.sub(r"\s+", " ", (v or "")).strip() for k, v in raw.items()}
        row = {k: (None if v == "" else v) for k, v in row.items()}
        row_key = tuple(row.get(k) for k in columns)
        if row_key in seen_rows:
            continue
        seen_rows.add(row_key)
        if row.get("program_id") in seen_ids:
            raise ValueError(f"Duplicate program_id: {row.get('program_id')}")
        seen_ids.add(row.get("program_id"))
        for col in ("duration_years", "tuition_amount"):
            value = row.get(col)
            if value is not None:
                try: row[col] = float(value.replace(",", "."))
                except ValueError: row[col] = None
        for col in ("total_credits", "instruction_language_share"):
            value = row.get(col)
            if value is not None:
                try:
                    row[col] = float(value.replace(",", "."))
                except ValueError:
                    row[col] = None
        share = row.get("instruction_language_share")
        if share is not None and not 0 <= share <= 100:
            raise ValueError(f"instruction_language_share outside 0-100 for {row.get('program_id')}")
        if "curriculum_course_list" in row:
            row["curriculum_course_list"] = normalize_course_list_json(row["curriculum_course_list"])
        if row.get("duration_years") is not None:
            d = row["duration_years"]
            row["duration_valid"] = 1 <= d <= 8
            row["duration_months"] = d * 12
            row["duration_group"] = (
                "3 năm trở xuống" if 0 <= d <= 3 else
                "Trên 3 đến 4 năm" if 3 < d <= 4 else
                "Trên 4 đến 8 năm" if 4 < d <= 8 else None
            )
        else:
            row["duration_valid"] = None
            row["duration_months"] = None
            row["duration_group"] = None
        amount = row.get("tuition_amount")
        row["tuition_valid"] = None if amount is None else amount >= 0
        row["has_tuition"] = None if amount is None else True
        row["tuition_status"] = "amount_recorded" if amount is not None else ("currency_only" if row.get("tuition_currency") else "unknown")
        for source_col, target_col in (("instruction_language", "language_known"), ("degree_level", "degree_level_known")):
            row[target_col] = None if not row.get(source_col) else True
        text = row.get("curriculum_text") or ""
        status = row.get("curriculum_status") or ""
        content_status = row.get("content_status") or ""
        row["has_curriculum_text"] = curriculum_presence(text, not bool(text), status, content_status)
        row["curriculum_word_count"] = (
            len(text.split()) if text else
            0 if status == "no_program_specific_curriculum_found" and content_status == "content_available" else None
        )
        name = row.get("program_name")
        row["program_name_length"] = len(name) if name else None
        rows.append(row)
    feature_columns = ["duration_valid", "tuition_valid", "duration_months", "duration_group", "has_tuition", "tuition_status", "language_known", "degree_level_known", "has_curriculum_text", "curriculum_word_count", "program_name_length"]
    output_columns = columns + [c for c in feature_columns if c not in columns]
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_FILE.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=output_columns); writer.writeheader(); writer.writerows(rows)
    missing_rows = []
    for col in output_columns:
        error_only = col == "collection_error"
        count = 0 if error_only else sum(r.get(col) is None or r.get(col) == "" for r in rows)
        data_type = "boolean" if col in {"duration_valid", "tuition_valid", "has_tuition", "language_known", "degree_level_known", "has_curriculum_text"} else ("Float64" if col in {"duration_years", "tuition_amount", "duration_months", "total_credits", "instruction_language_share"} else ("Int64" if col == "curriculum_word_count" else ("string" if col in {"duration_range_years", "credit_system", "award_title", "curriculum_course_list"} else "object")))
        missing_rows.append({"column": col, "missing_count": count, "missing_percent": round(100 * count / len(rows), 2) if rows else 0, "data_type": data_type, "recorded_exception_count": sum(bool(r.get(col)) for r in rows) if error_only else "", "notes": "error-only field; blank means no exception recorded" if error_only else ""})
    with MISSING_REPORT.open("w", encoding="utf-8-sig", newline="") as f:
        fields = ["column", "missing_count", "missing_percent", "data_type", "recorded_exception_count", "notes"]
        writer = csv.DictWriter(f, fieldnames=fields); writer.writeheader(); writer.writerows(sorted(missing_rows, key=lambda r: -r["missing_percent"]))
    print(f"Pandas unavailable; stdlib cleaner processed {len(rows)} rows, {len(columns)} input columns, {len(output_columns)} output columns")
    print(f"Unknown tuition values retained as missing; has_tuition NA count: {sum(r['has_tuition'] is None for r in rows)}")
    print("Saved cleaned data: data/processed/programs_clean.csv")
    print("Saved missing report: data/processed/missing_values_report.csv")


# =========================================================
# 6. CHẠY PIPELINE
# =========================================================

def main():
    try:
        import pandas  # noqa: F401
    except ImportError:
        _clean_csv_fallback()
        return
    df = load_data()
    df = clean_data(df)
    df = create_features(df)

    OUTPUT_FILE.parent.mkdir(
        parents=True, exist_ok=True
    )

    df.to_csv(
        OUTPUT_FILE,
        index=False,
        encoding="utf-8-sig",
    )

    missing_report = create_missing_report(df)
    missing_report.to_csv(
        MISSING_REPORT,
        index=False,
        encoding="utf-8-sig",
    )

    print("\n=== KẾT QUẢ LÀM SẠCH ===")
    print(f"Số dòng: {len(df)}")
    print(f"Số cột sau tạo đặc trưng: {len(df.columns)}")

    display_columns = [
        col for col in [
            "program_id",
            "duration_years",
            "duration_months",
            "duration_group",
            "instruction_language",
            "has_tuition",
        ]
        if col in df.columns
    ]

    print("\n=== DỮ LIỆU SAU XỬ LÝ ===")
    print(df[display_columns].to_string(index=False))

    print("\n=== CÁC CỘT CÒN THIẾU ===")
    print(
        missing_report[
            missing_report["missing_count"] > 0
        ].to_string(index=False)
    )

    print(f"\nĐã lưu dữ liệu sạch: {OUTPUT_FILE}")
    print(f"Đã lưu báo cáo thiếu: {MISSING_REPORT}")


if __name__ == "__main__":
    main()
