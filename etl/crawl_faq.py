"""저장된 현대 EV HTML에서 FAQ를 추출한다. 네트워크 요청은 하지 않는다."""

import argparse
from datetime import date
import hashlib
from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup

SOURCE_URL = "https://www.hyundai.com/kr/ko/service-membership/ev/ev-everycare/ev"
FETCHED_ON = "2026-11-05"
PROJECT = Path(__file__).resolve().parents[1]
FAQ_SELECTOR = 'section.faq[aria-labelledby="ev-care-faq-title"] li'


def extract_faq_html(html: str, fetched_on: str = FETCHED_ON) -> pd.DataFrame:
    fetched_on = date.fromisoformat(fetched_on).isoformat()
    soup = BeautifulSoup(html, "html.parser")
    rows = []
    for number, item in enumerate(
        soup.select(FAQ_SELECTOR), 1
    ):
        heading = item.find("h3")
        paragraph = item.find_all("p")
        if heading is None or not paragraph:
            raise ValueError("FAQ 질문 또는 답변이 없는 항목이 있습니다.")
        question = " ".join(heading.get_text(" ", strip=True).split())
        answer = "\n".join(p.get_text(" ", strip=True) for p in paragraph).strip()
        if not question or not answer:
            raise ValueError("FAQ의 질문 또는 답변이 비었습니다.")
        key = hashlib.sha256(f"{SOURCE_URL}\n{question}".encode()).hexdigest()
        rows.append({
            "company_name": "현대자동차", "faq_key": key, "category": "EV 에브리케어",
            "question": question, "answer_text": answer, "source_url": SOURCE_URL,
            "fetched_on": fetched_on, "source_row_no": number,
        })
    result = pd.DataFrame(rows)
    if result.empty or result["faq_key"].duplicated().any():
        raise ValueError("FAQ 영역이 없거나 같은 질문이 중복되었습니다.")
    return result


def extract_faq(path: Path, fetched_on: str = FETCHED_ON) -> pd.DataFrame:
    return extract_faq_html(path.read_text(encoding="utf-8"), fetched_on)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=PROJECT / "data/raw/ab_verified/hyundai_ev_current.html")
    parser.add_argument("--output", type=Path, default=PROJECT / "data/preview/faq.csv")
    parser.add_argument("--fetched-on", default=FETCHED_ON,
                        help="HTML을 실제 수집한 날짜 YYYY-MM-DD. 기본값은 기존 보관본 날짜")
    args = parser.parse_args(argv)
    frame = extract_faq(args.input, args.fetched_on)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(args.output, index=False, encoding="utf-8-sig", lineterminator="\n")
    print(f"FAQ {len(frame)}쌍 저장")


if __name__ == "__main__":
    main()
