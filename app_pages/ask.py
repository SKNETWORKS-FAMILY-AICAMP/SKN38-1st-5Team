from dataclasses import asdict

import pandas as pd
import streamlit as st

from ask_service import (
    Answer, Conversation, DailyQuota, EXAMPLE_QUESTIONS, InputError, MAX_QUESTION_CHARS,
    MAX_SESSION_QUESTIONS, NOT_CONNECTED, create_client, load_saved_example, resolve_api_key,
)


@st.cache_resource(max_entries=1, show_spinner=False)
def get_client():
    key = resolve_api_key(st.secrets)
    return create_client(key) if key else None


@st.cache_resource(max_entries=1, show_spinner=False)
def get_quota() -> DailyQuota:
    return DailyQuota()


COLUMN_NAMES = {
    "district_name": "동네", "stat_month": "등록·주민 기준월",
    "ownership_value": "세대당 차량(대)", "ownership_rank": "차량 보유 순위", "ownership_level": "차량 보유 판정",
    "parking_value": "차량당 수록 주차면(면)", "parking_rank": "주차면 비율 순위", "parking_level": "주차 여건 판정",
    "need_value": "주민당 하루 승객", "need_rank": "대중교통 이용 순위", "need_level": "차 필요성 판정",
    "vehicle_count": "등록 차량(대)", "household_count": "세대수", "population": "주민(명)",
    "electric_count": "전기차(대)", "electric_share_pct": "전기차 비중(%)",
    "unique_space_count": "알려진 수록 주차면(면)", "unique_missing_space_count": "면수 미확인 주차 자료(행)",
    "need_stat_date": "승객 기준일", "transit_passenger_count": "수록 하루 승객",
    "transit_observed_hour_count": "수록 시간 수", "transit_complete_hour_count": "전체 동이 수록된 시간 수",
    "transit_min_valid_dong_count": "최소 수록 동 수", "transit_expected_dong_count": "전체 동 수",
    "vehicle_type_name": "차종", "fuel_scope_name": "연료 범위",
    "company_name": "기업", "category": "분류", "question": "질문", "answer_text": "기업 답변",
    "source_url": "원문 출처", "fetched_on": "수집일",
}


def show_evidence(evidence: list[dict], turn_index: int) -> None:
    with st.expander("답변의 근거 자료 보기", key=f"ask_evidence_{turn_index}"):
        if not evidence:
            st.caption("이 답변에서 조회한 근거 자료는 없어요.")
        for item in evidence:
            st.markdown(f"**{item['title']}**")
            if item["rows"]:
                # 큰 정수의 정밀도를 잃지 않도록 문자열로 표시한다.
                rows = [{COLUMN_NAMES.get(key, key): "자료 없음" if value is None else str(value)
                         for key, value in row.items()} for row in item["rows"]]
                st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch",
                             alt=item["title"])
            else:
                st.caption("자료 없음")
            for note in item["notes"]:
                st.caption(note)


st.session_state.setdefault("ask_history", [])
st.session_state.setdefault("ask_count", 0)
history = st.session_state.ask_history
quota = get_quota()
try:
    client = get_client()
except Exception:
    # 연결 오류에 포함될 수 있는 설정값을 화면에 노출하지 않는다.
    client = None

with st.container(border=True, gap="small", key="ask_intro"):
    st.subheader("궁금한 동네, 톡 물어봐요", anchor=False)
    st.markdown("차량 보유, 주차 여건, 차가 꼭 필요한지 차차차 자료에서 찾아 알려드려요. "
                "기업이 안내한 자동차 이용 방법도 물어볼 수 있어요.")
    st.caption("답변 아래에서 근거 자료를 펼쳐볼 수 있어요. 질문은 200자 이내, 이번 대화에서 10번까지예요.")

if client is None:
    st.info(NOT_CONNECTED, icon=":material/chat_bubble:")

limit_reached = st.session_state.ask_count >= MAX_SESSION_QUESTIONS or quota.remaining() == 0
if st.session_state.ask_count >= MAX_SESSION_QUESTIONS:
    st.info("이번 대화의 질문 10회를 모두 사용했어요. 다른 메뉴의 자료도 살펴봐 주세요.")
elif quota.remaining() == 0:
    st.info("오늘 준비한 질문 200회를 모두 사용했어요. 내일 다시 물어봐 주세요.")

example_prompt = None
if not history:
    with st.container(horizontal=True, gap="small", key="ask_examples"):
        for index, example in enumerate(EXAMPLE_QUESTIONS):
            saved_available = client is None and load_saved_example(example) is not None
            if st.button(example, key=f"ask_example_{index}", icon=":material/chat_bubble:",
                         disabled=limit_reached or (client is None and not saved_available)):
                example_prompt = example

for index, turn in enumerate(history):
    with st.chat_message("user"):
        st.markdown(turn["question"])
    with st.chat_message("assistant"):
        if turn.get("saved"):
            st.caption("미리 저장한 답변 · 저장 당시 자료를 바탕으로 한 답변이에요.")
        st.markdown(turn["answer"])
        show_evidence(turn["evidence"], index)

st.caption(f"이번 대화에서 {MAX_SESSION_QUESTIONS - st.session_state.ask_count}번 더 물어볼 수 있어요.")
prompt = st.chat_input("어느 동네의 자동차 생활이 궁금한가요?", key="ask_prompt",
                       max_chars=MAX_QUESTION_CHARS, submit_mode="disable",
                       disabled=client is None or limit_reached)
# 머리말의 통합검색에서 넘어온 질문은 한 번만 쓴다.
prompt = prompt or example_prompt or st.session_state.pop("ask_prefill", None)
if prompt:
    try:
        # 화면의 입력 제한은 우회할 수 있어 서버에서도 검사한다.
        saved = load_saved_example(prompt)
        if client is None and saved is None:
            raise InputError(NOT_CONNECTED)
        question = quota.reserve(prompt, st.session_state.ask_count)
        st.session_state.ask_count += 1
    except InputError as exc:
        st.info(str(exc))
    else:
        with st.chat_message("user"):
            st.markdown(question)
        with st.chat_message("assistant"):
            output = st.empty()
            if client is None:
                answer = saved or Answer(text=NOT_CONNECTED, failed=True)
            else:
                conversation = Conversation(client, question, history)
                with output.container():
                    st.write_stream(conversation.stream())
                answer = conversation.answer
                if answer.failed and saved is not None:
                    answer = saved
            output.markdown(answer.text)
        turn = asdict(answer)
        turn["question"] = question
        turn["answer"] = turn.pop("text")
        history.append(turn)
        st.rerun()
