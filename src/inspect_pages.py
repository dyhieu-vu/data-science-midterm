
from pathlib import Path

import requests
from bs4 import BeautifulSoup

URLS = {
    "VN001_UET": (
        "https://uet.vnu.edu.vn/"
        "chuong-trinh-dao-tao-nganh-tri-tue-nhan-tao-16/"
    ),
    "VN002_BUV": (
        "https://www.buv.edu.vn/undergraduate/"
        "bsc-hons-data-science-artificial-intelligence/"
    ),
    "VN003_HCMUS": (
        "https://www.fit.hcmus.edu.vn/beta/"
        "undergraduate/artificial-intelligence"
    ),
    "VN004_HOASEN": (
        "https://www.hoasen.edu.vn/cntt/en/education/ai/"
    ),
    "VN005_SWINBURNE": (
        "https://swinburne-vn.edu.vn/en/course/artificial-intelligence/"
    ),
}

HEADERS = {
    "User-Agent": "UniversityAIResearch/1.0 (educational research)"
}

OUTPUT_DIR = Path("data/raw/page_samples")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def inspect_page(source_id, url):
    print("\n" + "=" * 60)
    print(f"{source_id}: {url}")

    try:
        response = requests.get(
            url,
            headers=HEADERS,
            timeout=30,
        )

        print("HTTP:", response.status_code)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "lxml")

        # Loại bỏ các phần không cần thiết.
        for tag in soup(
            ["script", "style", "noscript", "svg", "nav", "footer"]
        ):
            tag.decompose()

        title = (
            soup.title.get_text(" ", strip=True)
            if soup.title
            else "(Không tìm thấy tiêu đề)"
        )

        text = soup.get_text(" ", strip=True)

        print("Tiêu đề:", title)
        print("Độ dài văn bản:", len(text), "ký tự")
        print("Nội dung mẫu:", text[:1200])

        output_path = OUTPUT_DIR / f"{source_id}.txt"
        output_path.write_text(text, encoding="utf-8")

        print("Đã lưu văn bản:", output_path)

    except requests.RequestException as exc:
        print("Lỗi tải trang:", repr(exc))

    except Exception as exc:
        print("Lỗi xử lý trang:", repr(exc))


def main():
    for source_id, url in URLS.items():
        inspect_page(source_id, url)


if __name__ == "__main__":
    main()
