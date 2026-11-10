"""Git에 포함하지 않는 서울 경계 원본을 고정 출처·해시로 복원한다."""
import argparse
import hashlib
import json
from pathlib import Path
import tempfile

import requests

ROOT = Path(__file__).resolve().parents[1]
DESTINATION = ROOT / 'data/raw/boundary/seoul-districts.geojson'
SOURCE = ('https://raw.githubusercontent.com/southkorea/seoul-maps/'
          'dbb1dcde2e3c9937684c5a44ab9301888ad63ee6/'
          'kostat/2013/json/seoul_municipalities_geo_simple.json')
SOURCE_CHECKSUM = {'sha256': '2bb208614451c9f2a096cd62204063d6b27e57dcb7650a35ac19c06f1a84eb03'}
EXPECTED_SHA256 = SOURCE_CHECKSUM['sha256']
MAX_BYTES = 1024 * 1024


def validate(body: bytes) -> None:
    if hashlib.sha256(body).hexdigest() != EXPECTED_SHA256:
        raise ValueError('경계 원본의 SHA-256이 수집 기록과 다릅니다.')
    document = json.loads(body)
    if document.get('type') != 'FeatureCollection' or len(document.get('features', [])) != 25:
        raise ValueError('서울 25구 경계 형식이 아닙니다.')


def fetch_boundary(destination: Path = DESTINATION) -> bool:
    if destination.is_file():
        try:
            if destination.stat().st_size <= MAX_BYTES:
                validate(destination.read_bytes())
                return False
        except (ValueError, UnicodeError):
            pass
    with requests.get(SOURCE, stream=True, timeout=(3, 20), allow_redirects=False) as response:
        if response.status_code != 200:
            raise ValueError('경계 원본을 다운로드하지 못했습니다.')
        body = bytearray()
        for chunk in response.iter_content(chunk_size=65536):
            body.extend(chunk)
            if len(body) > MAX_BYTES:
                raise ValueError('경계 원본의 허용 크기를 초과했습니다.')
    validate(bytes(body))
    destination.parent.mkdir(parents=True, exist_ok=True)
    # 쓰기 핸들을 닫은 뒤 교체해야 Windows에서도 원자적 게시가 가능하다.
    with tempfile.TemporaryDirectory(prefix='.boundary-', dir=destination.parent) as directory:
        staged = Path(directory) / destination.name
        staged.write_bytes(body)
        staged.replace(destination)
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    try:
        changed = fetch_boundary()
    except (OSError, ValueError, requests.RequestException):
        print('경계 복원 실패: 네트워크·출처 해시·저장 권한을 확인하세요.')
        return 1
    print('서울 25구 경계 원본 복원 완료 (SHA-256 검증)' if changed else '검증된 경계 원본이 이미 있습니다.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
