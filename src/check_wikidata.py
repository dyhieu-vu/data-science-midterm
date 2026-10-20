import requests

URL = "https://query.wikidata.org/sparql"

PARAMS = {
    "query": """
    SELECT ?university ?universityLabel WHERE {
      ?university wdt:P31/wdt:P279* wd:Q3918.
      ?university wdt:P17 wd:Q881.
      SERVICE wikibase:label {
        bd:serviceParam wikibase:language "vi,en".
      }
    }
    LIMIT 5
    """,
    "format": "json",
}

HEADERS = {
    "User-Agent": "UniversityAIResearch/1.0 (educational research)",
    "Accept": "application/sparql-results+json",
}

try:
    response = requests.get(
        URL,
        params=PARAMS,
        headers=HEADERS,
        timeout=45,
    )

    print("HTTP status:", response.status_code)
    response.raise_for_status()

    data = response.json()
    rows = data["results"]["bindings"]

    print("Số kết quả:", len(rows))

    for row in rows:
        print(
            row["universityLabel"]["value"],
            row["university"]["value"],
        )

except requests.RequestException as exc:
    print("Lỗi kết nối HTTP:", repr(exc))

except (ValueError, KeyError) as exc:
    print("Lỗi đọc dữ liệu trả về:", repr(exc))

