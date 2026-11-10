"""명시적으로 실행할 때만 Selenium으로 현대 EV FAQ를 수집한다. DB 적재 없음."""

import argparse
from datetime import datetime
import math
from pathlib import Path
import tempfile
from zoneinfo import ZoneInfo

from etl.crawl_faq import FAQ_SELECTOR, PROJECT, SOURCE_URL, extract_faq_html


def collect_faq(timeout: float = 30):
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("timeout은 유한한 양수여야 합니다.")
    # 오프라인 파서는 Selenium이나 브라우저를 초기화하지 않는다.
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait

    options = webdriver.ChromeOptions()
    options.add_argument("--headless=new")
    driver = webdriver.Chrome(options=options)
    try:
        driver.set_page_load_timeout(timeout)
        driver.get(SOURCE_URL)
        WebDriverWait(driver, timeout).until(
            EC.presence_of_all_elements_located((By.CSS_SELECTOR, FAQ_SELECTOR))
        )
        html = driver.page_source
        collected_at = datetime.now(ZoneInfo("Asia/Seoul"))
        frame = extract_faq_html(html, collected_at.date().isoformat())
        # 기존 CSV 열은 유지하고 정확한 수집시각은 별도 열로 기록한다.
        frame["collected_at"] = collected_at.isoformat(timespec="seconds")
        return frame
    finally:
        driver.quit()


def fetch_faq(output: Path, timeout: float = 30) -> int:
    # 브라우저 종료와 파싱 검증까지 성공한 뒤에만 기존 파일을 교체한다.
    frame = collect_faq(timeout)
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".faq-", dir=output.parent) as directory:
        staged = Path(directory) / "faq.csv"
        frame.to_csv(staged, index=False, encoding="utf-8-sig", lineterminator="\n")
        staged.replace(output)
    return len(frame)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=PROJECT / "data/preview/faq_live.csv")
    parser.add_argument("--timeout", type=float, default=30)
    args = parser.parse_args(argv)
    count = fetch_faq(args.output, args.timeout)
    print(f"FAQ {count}쌍 수집 완료")


if __name__ == "__main__":
    main()
