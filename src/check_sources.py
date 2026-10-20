import csv
import time
from pathlib import Path
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = PROJECT_ROOT / "data" / "raw" / "source_registry.csv"
OUTPUT_PATH = PROJECT_ROOT / "data" / "raw" / "source_check_report.csv"

HEADERS = {
    "User-Agent": "UniversityAIResearch/1.0 (educational research)"
}


def check_source(source):
    url = source["source_url"]
    result = {
        "source_id": source["source_id"],
        "source_name": source["source_name"],
        "source_url": url,
        "http_status": "",
        "content_type": "",
        "robots_txt_url": "",
        "robots_status": "not_checked",
        "allowed_by_robots": "",
        "error": "",
    }

    try:
        response = requests.get(
            url,
            headers=HEADERS,
            timeout=20,
        )

        result["http_status"] = response.status_code
        result["content_type"] = response.headers.get(
            "Content-Type", ""
        )

        # Kiểm tra robots.txt ở cấp tên miền.
        parsed = urlparse(url)
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        result["robots_txt_url"] = robots_url

        try:
            robots_response = requests.get(
                robots_url,
                headers=HEADERS,
                timeout=15,
            )

            if robots_response.status_code == 200:
                parser = RobotFileParser()
                parser.set_url(robots_url)
                parser.parse(robots_response.text.splitlines())

                allowed = parser.can_fetch(HEADERS["User-Agent"], url)
                result["robots_status"] = "retrieved"
                result["allowed_by_robots"] = allowed

            elif robots_response.status_code == 404:
                result["robots_status"] = "not_found"
            else:
                result["robots_status"] = (
                    f"http_{robots_response.status_code}"
                )

        except requests.RequestException as exc:
            result["robots_status"] = "request_error"
            result["error"] = f"robots.txt: {exc}"

        # Chờ giữa các nguồn để hạn chế gửi request liên tục.
        time.sleep(1)

    except requests.RequestException as exc:
        result["error"] = str(exc)

    return result


def main():
    if not REGISTRY_PATH.exists():
        raise FileNotFoundError(
            f"Không tìm thấy file nguồn: {REGISTRY_PATH}"
        )

    with REGISTRY_PATH.open(
        "r", encoding="utf-8-sig", newline=""
    ) as file:
        sources = list(csv.DictReader(file))

    if not sources:
        raise ValueError("Danh sách nguồn đang rỗng.")

    results = [check_source(source) for source in sources]

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    with OUTPUT_PATH.open(
        "w", encoding="utf-8-sig", newline=""
    ) as file:
        writer = csv.DictWriter(
            file, fieldnames=results[0].keys()
        )
        writer.writeheader()
        writer.writerows(results)

    for result in results:
        print(
            f'{result["source_id"]}: '
            f'HTTP={result["http_status"] or "ERROR"} | '
            f'robots={result["robots_status"]} | '
            f'allowed={result["allowed_by_robots"] or "unknown"}'
        )

    print(f"\nBáo cáo đã lưu tại: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()