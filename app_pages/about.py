from pathlib import Path

import pandas as pd
import streamlit as st

from content_faq import RANKING_NOTE, RELATIVE_REASON, VERDICT_RULES
from ui import date_text, load_options, word


SOURCE_NAMES = {
    "molit_registration": "국토교통부 · 자동차 등록",
    "seoul_fuel": "서울시 · 연료별 자동차 등록",
    "resident_population": "행정안전부 · 주민등록 인구·세대",
    "parking_standard": "전국주차장정보표준데이터",
    "keco_ev_charger": "한국환경공단 · 전기차 충전기",
    "seoul_charger": "서울시 · 공공 전기차 충전기",
    "seoul_traffic": "서울 TOPIS · 지점별 교통량",
    "seoul_passenger": "서울시 · 행정동별 대중교통 승객",
    "kma_asos_hourly": "기상청 · 서울 108 시간별 관측",
    "kostat_seoul_boundary": "통계청 · 서울 구 경계 (seoul-maps)",
    "hyundai_ev_faq": "현대자동차 · EV 에브리케어 FAQ",
}

SOURCE_DESCRIPTIONS = {
    "molit_registration": (
        "서울 구별·전국 시도별 자동차 등록 자료예요. "
        "현재는 한 달 자료라 전월 대비를 보여주지 않아요."
    ),
    "seoul_fuel": (
        "서울의 연료별 자동차 등록 자료예요. "
        "전기차는 전체 차량에 포함되므로 둘을 더하지 않아요."
    ),
    "resident_population": (
        "서울 25구의 주민 수와 세대수예요. "
        "세대당 차량 수와 주민당 승객 수를 계산할 때 써요."
    ),
    "parking_standard": (
        "수집한 서울 주차장 목록이에요. 아파트는 빠져 있고, "
        "관리번호가 충돌한 행은 면수 합계에서 제외해요."
    ),
    "keco_ev_charger": (
        "기본 조회에 쓰는 서울 충전기 목록이에요. "
        "수집 당시 상태이며 서울시 공공 목록과 합산하지 않아요."
    ),
    "seoul_charger": (
        "서울시 공공 충전기 목록을 별도로 보관했어요. "
        "환경공단 자료를 쓰는 기본 충전 지표에는 더하지 않아요."
    ),
    "seoul_traffic": (
        "서울 24구의 관측 지점별 교통량을 합쳤어요. "
        "강북구 자료는 없고, 구마다 관측 지점 수가 달라요."
    ),
    "seoul_passenger": (
        "서울 25구의 이틀간 대중교통 승객 자료예요. "
        "강서구는 일부 행정동이 빠져 이용 규모가 작게 집계될 수 있어요."
    ),
    "kma_asos_hourly": (
        "서울 108번 관측소의 48시간 자료예요. "
        "구별 날씨가 아니며 빠진 강수·적설 값은 0으로 바꾸지 않아요."
    ),
    "kostat_seoul_boundary": (
        "2013년 서울 구 경계를 지도에 표시해요. "
        "현재 법적 경계나 판정 계산에 쓰지 않아요."
    ),
    "hyundai_ev_faq": (
        "현대자동차 EV 에브리케어의 질문과 답변 10개예요. "
        "수집 당시 안내라 최신 조건은 기업 원문에서 확인해요."
    ),
}

DB_TABLES = (
    ("출처·지역", "source_snapshot", "자료의 기준 기간, 수집일과 검수 기록"),
    ("출처·지역", "region", "서울 25개 구의 이름과 지역 코드"),
    ("출처·지역", "region_boundary", "지도 표시용 2013년 구 경계"),
    ("등록·인구", "vehicle_type", "승용·승합·화물·특수 차종"),
    ("등록·인구", "fuel_scope", "전체 차량 또는 전기차 범위"),
    ("등록·인구", "registration", "서울 구·월·차종·연료 범위별 등록"),
    ("등록·인구", "province_registration", "전국 시도·월·차종·용도별 등록"),
    ("등록·인구", "region_context", "구·월별 인구와 세대수"),
    ("주차·충전", "parking_site", "원본에 수록된 주차장 관측행"),
    ("주차·충전", "charging_station", "출처별 충전소와 운영기관의 묶음"),
    ("주차·충전", "charger", "충전소 안의 충전기와 수집 당시 상태"),
    ("교통·날씨", "traffic_coverage", "구별로 기대한 교통 관측 지점·방향 수"),
    ("교통·날씨", "traffic_snapshot", "구·시간별 관측 교통량 부분합"),
    ("교통·날씨", "transit_coverage", "구·날짜별로 기대한 행정동 수"),
    ("교통·날씨", "transit_ridership_snapshot", "구·날짜·시간·수단별 승객 부분합"),
    ("교통·날씨", "weather_snapshot", "서울 108 관측소의 시간별 날씨"),
    ("기업 FAQ", "company", "FAQ를 제공한 기업"),
    ("기업 FAQ", "faq", "기업의 질문·답변·원문 출처·수집일"),
)

LIMITATIONS = (
    ("서로 다른 시점의 자료예요",
     r"등록·인구·세대와 교통량은 2026.09, 승객·날씨는 2026.10.30\~31 자료예요. "
     "등록은 한 달뿐이라 전월 대비나 월별 추이를 만들 수 없어요. "
     "시설 기준일을 모를 때 수집일로 대신하지 않아요."),
    ("주차 목록과 지도는 전체 주차장을 담지 않아요",
     "아파트 주차장은 빠져 있어요. 관리번호가 충돌한 행은 면수 합계에서 제외해요. "
     "좌표가 없거나 검수를 통과하지 못한 곳은 지도에서 제외하며, 원본에 없는 실제 이름은 만들지 않아요. "
     "수록 면수는 실시간 빈자리가 아니에요."),
    ("충전기 상태는 수집 당시 정보예요",
     "현재 빈자리나 요금을 알려주지 않아요. 이용 제한 안내가 없다고 자유 이용을 보장하지 않아요. "
     "기본 조회는 환경공단 자료만 쓰고 서울시 공공 목록과 합산하지 않아요."),
    ("승객 수로 개인의 차 필요성을 확정할 수 없어요",
     "차 필요성은 2026.10.30 하루 승객과 9월 주민 수를 비교한 참고값이에요. "
     "고유 주민 수나 주민만의 이용 횟수가 아니며, 중구·종로구는 출퇴근 유입의 영향을 받을 수 있어요. "
     "강서구는 일부 행정동이 빠진 부분합이라 실제 이용 규모보다 작게 집계될 수 있어요."),
    ("교통량은 관측 지점의 합이에요",
     "2026.09에 관측한 24개 구의 지점별 차량 수를 합쳤어요. "
     "구마다 관측 지점·방향 수가 달라 절대 교통량으로 구끼리 비교하기 어려워요. "
     "강북구는 관측 지점 자료가 없어 교통량을 보여주지 못해요."),
    ("날씨는 서울 공통 표본이에요",
     r"2026.10.30\~31의 48시간 자료이고 서울 108 관측소 값이에요. "
     "구별 실측이나 오늘의 예보가 아니에요. 빠진 강수·적설 값은 0으로 바꾸지 않아요."),
    ("지도 경계와 전국 등록의 범위를 확인해요",
     "2013년 구 경계는 지도 표시용이며 현재의 법적 경계나 판정 계산에 쓰지 않아요. "
     "전국 등록은 원본에 수록된 16개 시도 표기를 유지해요. '전남광주'를 임의로 나누지 않아요."),
)


def reference_period(start: object, end: object) -> str:
    first, last = date_text(start), date_text(end)
    if first == last:
        return first
    return f"{first} ~ {last}"


section = st.segmented_control(
    "자료 안내 항목", ["출처·기준일", "판정 기준", "DB 구성", "자료의 한계"],
    default="출처·기준일", required=True, key="about_section", label_visibility="collapsed",
)

if section == "출처·기준일":
    st.subheader("어디서 온 자료인가요?", anchor=False)
    st.caption("기준 기간은 자료가 설명하는 시점, 수집일은 자료를 모은 날이에요.")
    snapshots = load_options().get("snapshots", pd.DataFrame())
    if snapshots is None or snapshots.empty:
        st.info("출처 수집본은 자료 없음으로 표시해요. 판정 기준과 DB 구성은 위에서 볼 수 있어요.",
                icon=":material/info:")
    else:
        records = []
        for _, row in snapshots.iterrows():
            source_code = word(row.get("source_code"))
            records.append({
                "자료": SOURCE_NAMES.get(source_code, source_code),
                "기준 기간": reference_period(row.get("reference_start"), row.get("reference_end")),
                "수집일": date_text(row.get("collected_on")),
                # is_complete=1이어도 관측 대상·필드가 모두 수록됐다는 뜻은 아니다.
                "완전성": "검수 완료",
                "수록 범위·누락": SOURCE_DESCRIPTIONS.get(source_code, "자료 없음"),
            })
        st.caption(f"검수한 수집본 {len(records):,}건 · 출처별 기준일을 함께 확인해요.")
        st.dataframe(pd.DataFrame(records), hide_index=True, width="stretch",
                     height="content", key="about_sources",
                     alt="출처 수집본별 이름, 기준 기간, 수집일, 검수 상태와 수록 범위")
        st.info("'검수 완료'는 수집본이 DB 검사를 통과했다는 뜻이에요. "
                "모든 지역·시설·관측값이 빠짐없이 있다는 뜻은 아니에요.", icon=":material/info:")
        with st.expander("출처별 수록 범위와 누락 자세히", key="about_coverage"):
            for record, (_, snapshot) in zip(records, snapshots.iterrows()):
                st.markdown(f"**{record['자료']} · 수집 {record['수집일']}**")
                st.markdown(record["수록 범위·누락"])
                coverage_note = word(snapshot.get("coverage_note")).replace("~", r"\~")
                st.caption(f"수집 기록 원문: {coverage_note}")
                if pd.notna(snapshot.get("page_updated_on")):
                    st.caption(f"제공 페이지 갱신일 {date_text(snapshot.get('page_updated_on'))} · 자료 기준일과 달라요.")

elif section == "판정 기준":
    st.subheader("세 질문, 세 가지 비교 지표", anchor=False)
    st.markdown(RANKING_NOTE)
    st.table(pd.DataFrame(VERDICT_RULES), hide_index=True, border="horizontal",
             alt="세 판정의 지표와 서울 25구 순위 구간별 판정표")
    with st.container(border=True, gap="small", key="about_relative"):
        st.markdown("**왜 상대 비교인가요?**")
        st.markdown(RELATIVE_REASON)
    st.caption("주차 비율은 화면에서 차 100대당 면수로 바꿔 보여줘요. 차량 보유가 많다는 판정은 좋고 나쁨을 뜻하지 않아요.")
    st.caption("차 필요성의 1위는 대중교통 이용 지표가 가장 큰 구예요. 승객 수는 고유 주민 수나 주민만의 이용 횟수가 아니에요.")
    st.caption("등록·인구·세대는 2026.09, 차 필요성의 승객은 2026.10.30 기준이에요. 강서구 승객에는 일부 행정동이 빠져 있어요.")

elif section == "DB 구성":
    st.subheader(f"자료를 {len(DB_TABLES)}개 표로 연결했어요", anchor=False)
    st.markdown("지역을 기준으로 등록·주차·충전·시간별 자료를 연결해요. "
                "충전소와 충전기, 기업과 FAQ를 나누고 각 자료의 출처를 함께 보관해요.")
    st.dataframe(pd.DataFrame(DB_TABLES, columns=pd.Index(["묶음", "표 이름", "담은 내용"])),
                 hide_index=True, width="stretch", height="content", key="about_db_tables",
                 alt="현재 DB를 이루는 18개 표의 이름과 역할")
    with st.expander("표 사이의 연결 그림 보기 (ERD)", key="about_erd"):
        erd_path = Path(__file__).resolve().parents[1] / "docs" / "erd_core.png"
        if erd_path.is_file():
            st.image(erd_path, width="stretch",
                     alt="출처와 지역을 중심으로 등록, 주차, 충전, 승객, 교통, 날씨, FAQ를 연결한 18표 관계도")
        else:
            st.info("DB 관계도는 자료 없음으로 표시해요.")
        st.caption("지역에는 여러 등록·시설 자료가, 충전소에는 여러 충전기가 연결돼요. 판정은 조회할 때 계산해요.")

else:
    st.subheader("숫자를 읽기 전에 함께 봐요", anchor=False)
    st.caption("빠진 자료는 0으로 채우지 않고 자료 없음으로 표시해요.")
    for title, description in LIMITATIONS:
        with st.container(border=True, gap="xsmall"):
            st.markdown(f"**{title}**")
            st.markdown(description)
