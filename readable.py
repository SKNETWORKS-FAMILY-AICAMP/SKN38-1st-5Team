"""숫자를 '서울 평균과 비교한 말'과 '25구 중 위치 막대'로 바꿔 보여 주는 공용 카드."""
from dataclasses import dataclass
from html import escape

import pandas as pd
import streamlit as st


@dataclass(frozen=True)
class Metric:
    label: str
    column: str
    scale: float
    digits: int
    unit: str
    prefix: str
    more: str
    less: str
    higher_is_good: bool | None


METRICS = {
    "own": Metric("차 보유", "vehicle_per_household", 1, 2, "대", "세대당", "차가 많은 동네", "차가 적은 동네", None),
    "park": Metric("주차", "parking_value", 100, 1, "면", "차 100대당", "주차가 넉넉한 편", "주차가 빠듯한 편", True),
    "need": Metric("대중교통", "need_value", 1, 2, "명", "주민 1명당 하루", "대중교통을 많이 타요", "대중교통 이용이 적어요", True),
    "charger": Metric("전기차 충전", "charger_per_electric_vehicle", 1, 2, "기", "전기차 1대당", "충전기가 넉넉한 편", "충전기가 부족한 편", True),
    "ev": Metric("전기차 비율", "electric_share_pct", 1, 1, "%", "등록 차량 중", "전기차가 많은 편", "전기차가 적은 편", None),
}
COMMUTER = {"중구", "종로구"}

CSS = """
<style>
.rd-grid { display: grid; grid-template-columns: repeat(var(--rd-cols, 4), minmax(0, 1fr)); gap: 14px; }
.rd-card { border: 1px solid #E2E5F0; border-radius: 18px; padding: 18px 20px; background: #fff;
  display: flex; flex-direction: column; gap: 8px; }
.rd-k { font-size: 14px; color: #4A5270; }
.rd-say { font-size: 21px; font-weight: 800; line-height: 1.35; }
.rd-good { color: #16803C; } .rd-mid { color: #A16207; } .rd-bad { color: #DC2626; } .rd-plain { color: #27336B; }
.rd-fact { font-size: 14px; color: #4A5270; }
.rd-pos { position: relative; height: 8px; border-radius: 4px; margin-top: 6px;
  background: linear-gradient(90deg, #EEF0FA, #8E98CF); }
.rd-pos i { position: absolute; top: -4px; width: 16px; height: 16px; border-radius: 50%; background: #FF7A66;
  border: 3px solid #fff; box-shadow: 0 1px 3px rgba(27,35,64,.3); transform: translateX(-50%); }
.rd-pos b { position: absolute; top: -6px; width: 2px; height: 20px; background: #1B2340; opacity: .35; transform: translateX(-50%); }
.rd-ends { display: flex; justify-content: space-between; font-size: 12px; color: #4A5270; }
.rd-note { font-size: 13px; color: #4A5270; margin: 4px 0 0; }
.rd-duel { display: grid; grid-template-columns: 1fr auto 1fr; align-items: center; gap: 10px; }
.rd-duel .side { display: flex; flex-direction: column; gap: 2px; }
.rd-duel .side.win .v { color: #27336B; }
.rd-duel .n { font-size: 14px; color: #4A5270; }
.rd-duel .v { font-size: 24px; font-weight: 800; color: #4A5270; font-variant-numeric: tabular-nums; }
.rd-duel .side:last-child { text-align: right; }
.rd-duel .vs { font-size: 13px; color: #4A5270; }
.rd-bar { display: flex; height: 10px; border-radius: 5px; overflow: hidden; background: #EEF0F4; }
.rd-bar span:first-child { background: #27336B; } .rd-bar span:last-child { background: #FF7A66; }
@media (max-width: 1100px) { .rd-grid { --rd-cols: 2 !important; } }
@media (max-width: 700px) { .rd-grid { --rd-cols: 1 !important; } }
</style>
"""


def _num(value) -> float | None:
    number = pd.to_numeric(value, errors="coerce")
    return None if pd.isna(number) else float(number)


def compare_phrase(value: float, average: float, metric: Metric) -> tuple[str, str]:
    """서울 평균과 견준 말과 색 이름을 돌려준다."""
    if not average:
        return "비교 자료 없음", "rd-plain"
    ratio = value / average
    if ratio >= 1.5:
        text, way = f"{metric.more} · 서울 평균의 {ratio:.1f}배", 1
    elif ratio >= 1.15:
        text, way = f"{metric.more} · 평균보다 조금 많아요", 1
    elif ratio > 0.87:
        text, way = "서울 평균과 비슷해요", 0
    elif ratio > 0.6:
        text, way = f"{metric.less} · 평균보다 조금 적어요", -1
    else:
        text, way = f"{metric.less} · 평균의 {ratio * 100:.0f}% 수준", -1
    if metric.higher_is_good is None or way == 0:
        tone = "rd-mid" if way == 0 else "rd-plain"
    else:
        tone = "rd-good" if (way > 0) == metric.higher_is_good else "rd-bad"
    return text, tone


def _card(row: pd.Series, ranking: pd.DataFrame, key: str) -> str:
    metric = METRICS[key]
    if metric.column not in ranking:
        return ""
    values = pd.to_numeric(ranking[metric.column], errors="coerce").dropna() * metric.scale
    value = _num(row.get(metric.column))
    if value is None or values.empty:
        return (f'<div class="rd-card"><span class="rd-k">{metric.label}</span>'
                f'<span class="rd-say rd-plain">자료 없음</span></div>')
    value *= metric.scale
    average = float(values.mean())
    text, tone = compare_phrase(value, average, metric)
    low, high = float(values.min()), float(values.max())
    spread = high - low or 1.0
    position = 100 * (value - low) / spread
    middle = 100 * (average - low) / spread
    rank = int((values > value).sum()) + 1
    return (f'<div class="rd-card"><span class="rd-k">{metric.label}</span>'
            f'<span class="rd-say {tone}">{escape(text)}</span>'
            f'<span class="rd-fact">{metric.prefix} {value:.{metric.digits}f}{metric.unit} · '
            f'서울 평균 {average:.{metric.digits}f}{metric.unit} · 25구 중 {rank}위</span>'
            f'<span class="rd-pos"><b style="left:{middle:.1f}%"></b><i style="left:{position:.1f}%"></i></span>'
            f'<span class="rd-ends"><span>적음</span><span>| 서울 평균</span><span>많음</span></span></div>')


def cards(row: pd.Series, ranking: pd.DataFrame, keys: tuple[str, ...], *, title: str | None = None) -> None:
    """한 구의 지표를 비교 문장 카드로 보여 준다."""
    if row is None or ranking is None or ranking.empty:
        return
    body = "".join(_card(row, ranking, key) for key in keys)
    if not body:
        return
    st.html(CSS)
    if title:
        st.markdown(f"**{title}**")
    st.html(f'<div class="rd-grid" style="--rd-cols:{min(len(keys), 4)}">{body}</div>')
    if str(row.get("district_name")) in COMMUTER and ({"need", "park"} & set(keys)):
        st.html('<p class="rd-note">* 출퇴근 인구가 몰리는 구라 주민 기준 대중교통·주차 값이 체감보다 크게 나와요.</p>')


def duel(left: pd.Series, right: pd.Series, left_name: str, right_name: str,
         keys: tuple[str, ...] = ("own", "park", "need", "charger")) -> None:
    """두 구를 항목별 막대와 한 줄 결론으로 나란히 보여 준다."""
    blocks = []
    for key in keys:
        metric = METRICS[key]
        a, b = _num(left.get(metric.column)), _num(right.get(metric.column))
        if a is None or b is None:
            continue
        a, b = a * metric.scale, b * metric.scale
        total = (a + b) or 1.0
        if max(a, b) == 0 or abs(a - b) / max(a, b) < 0.1:
            verdict = "두 구가 비슷해요"
        else:
            bigger, smaller = (left_name, b) if a > b else (right_name, a)
            ratio = max(a, b) / smaller if smaller else None
            how = f"{ratio:.1f}배" if ratio and ratio < 10 else "훨씬"
            verdict = f"{bigger} 쪽이 {how} 많아요"
        win_left = metric.higher_is_good is not None and a > b * 1.1
        win_right = metric.higher_is_good is not None and b > a * 1.1
        blocks.append(
            f'<div class="rd-card"><span class="rd-k">{metric.label} · {metric.prefix}</span>'
            f'<div class="rd-duel"><div class="side{" win" if win_left else ""}"><span class="n">{escape(left_name)}</span>'
            f'<span class="v">{a:.{metric.digits}f}{metric.unit}</span></div><span class="vs">vs</span>'
            f'<div class="side{" win" if win_right else ""}"><span class="n">{escape(right_name)}</span>'
            f'<span class="v">{b:.{metric.digits}f}{metric.unit}</span></div></div>'
            f'<div class="rd-bar"><span style="width:{100 * a / total:.1f}%"></span><span style="width:{100 * b / total:.1f}%"></span></div>'
            f'<span class="rd-say rd-plain" style="font-size:17px">{escape(verdict)}</span></div>')
    if not blocks:
        return
    st.html(CSS)
    st.html(f'<div class="rd-grid" style="--rd-cols:{min(len(blocks), 4)}">{"".join(blocks)}</div>')
