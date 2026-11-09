# 예시 답변 생성에는 API 사용료가 발생한다.

from datetime import datetime
import json
from pathlib import Path
import sys
import tomllib
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ask_service import (  # noqa: E402
    Conversation, EXAMPLE_QUESTIONS, EXAMPLES_PATH, MODEL, create_client, resolve_api_key,
)


def main() -> int:
    try:
        secrets_path = ROOT / ".streamlit" / "secrets.toml"
        secrets = tomllib.loads(secrets_path.read_text(encoding="utf-8")) if secrets_path.is_file() else {}
        key = resolve_api_key(secrets)
        if not key:
            print("물어보기 연결 키가 없어 예시 답변을 만들지 않았어요.")
            return 1
        examples = []
        with create_client(key) as client:
            for question in EXAMPLE_QUESTIONS:
                conversation = Conversation(client, question)
                for _ in conversation.stream():
                    pass
                answer = conversation.answer
                if answer.failed or not answer.evidence:
                    print("근거가 있는 예시 답변을 모두 만들지 못해 기존 파일을 보존했어요.")
                    return 1
                examples.append({"question": question, "answer": answer.text, "evidence": answer.evidence})
        document = {"schema_version": 1, "model": MODEL,
                    "generated_at": datetime.now(ZoneInfo("Asia/Seoul")).isoformat(), "examples": examples}
        EXAMPLES_PATH.parent.mkdir(parents=True, exist_ok=True)
        temporary = EXAMPLES_PATH.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(document, ensure_ascii=False, allow_nan=False, indent=2) + "\n",
                             encoding="utf-8")
        temporary.replace(EXAMPLES_PATH)
        print("data/ask_examples.json에 근거 자료와 예시 답변 3개를 저장했어요.")
        return 0
    except Exception:
        # 접속 정보가 포함될 수 있어 오류 원문을 출력하지 않는다.
        print("예시 답변을 만들지 못했어요. 연결과 자료 상태를 확인해 주세요.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
