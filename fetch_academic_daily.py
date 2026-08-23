import urllib.request
import xml.etree.ElementTree as ET
import time
import os
from pathlib import Path

# 設定
BASE_DIR = Path(__file__).resolve().parent
SAVE_DIR = str(BASE_DIR / "data_hdd_storage" / "academic_data")
QUERIES = [
    'all: "Deep Learning" AND all: "Adaptive System"',
    'all: "Justice AI" AND all: "Elijah"',
    'all: "Large Language Model" AND all: "Data Centric"',
]


def fetch_arxiv():
    os.makedirs(SAVE_DIR, exist_ok=True)
    print(
        f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 正在從 arXiv 抓取以利雅準則相關論文..."
    )

    for query in QUERIES:
        encoded_query = urllib.parse.quote(query)
        url = f"http://export.arxiv.org/api/query?search_query={encoded_query}&start=0&max_results=5&sortBy=submittedDate&sortOrder=descending"

        try:
            with urllib.request.urlopen(url) as response:
                content = response.read().decode("utf-8")
                root = ET.fromstring(content)

                for entry in root.findall("{http://www.w3.org/2005/Atom}entry"):
                    title = (
                        entry.find("{http://www.w3.org/2005/Atom}title")
                        .text.strip()
                        .replace("\n", " ")
                    )
                    summary = entry.find(
                        "{http://www.w3.org/2005/Atom}summary"
                    ).text.strip()
                    paper_id = entry.find("{http://www.w3.org/2005/Atom}id").text.split(
                        "/"
                    )[-1]

                    filename = f"{paper_id}.md"
                    filepath = os.path.join(SAVE_DIR, filename)

                    with open(filepath, "w", encoding="utf-8") as f:
                        f.write(f"# {title}\n\n")
                        f.write(f"**ID:** {paper_id}\n")
                        f.write(f"**Query:** {query}\n\n")
                        f.write(f"## Abstract\n{summary}\n")

                    print(f"已儲存: {title[:50]}...")
        except Exception as e:
            print(f"抓取失敗 ({query}): {e}")
        time.sleep(1)  # 尊重 API 限制


if __name__ == "__main__":
    fetch_arxiv()
