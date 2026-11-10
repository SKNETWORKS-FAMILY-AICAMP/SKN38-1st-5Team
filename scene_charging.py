"""주차·충전 화면에서 공유하는 충전 여건 게이지."""
import pandas as pd
import streamlit as st
from ui import number

_GAUGE = st.components.v2.component(
    "chachacha_charging_gauge",
    isolate_styles=True,
    html="""
    <section class="scene">
      <div class="copy"><p class="eyebrow">우리 동네 충전 여건</p>
        <h3 class="title"><span class="district-name"></span><span class="title-copy"></span></h3><p class="detail"></p></div>
      <div class="battery" role="img"><div class="fill"></div>
        <div class="divider first"></div><div class="divider second"></div>
        <svg class="bolt" viewBox="0 0 24 32" aria-hidden="true">
          <path d="M14 1 2 18h9l-1 13 12-19h-9Z" fill="#FF7A66"/>
        </svg>
      </div>
    </section>
    """,
    css="""
    .scene { box-sizing: border-box; display: flex; align-items: center;
      justify-content: space-between; gap: 24px; padding: 24px 30px;
      border: 1px solid #C8CDE3; border-radius: var(--st-base-radius, 16px);
      background: #EEF0FA; color: #1B2340; font-family: var(--st-font, sans-serif); }
    .scene.compact {padding:26px 28px;gap:20px;min-height:220px;}
    .scene.compact .district-name {font-size:36px;}
    .scene.compact .title {font-size:26px;}
    .scene.compact .battery {transform:none;}
    @media(max-width:480px){.scene.compact {padding:20px;min-height:0;}.scene.compact .district-name {font-size:32px;}}
    .copy { min-width: 0; }
    .eyebrow { color: #4A5270; font-size: 16px; margin: 0 0 8px; }
    .title { font-family: var(--st-heading-font, inherit); font-size: 27px;
      font-weight: 400; line-height: 1.3; margin: 0 0 8px; overflow-wrap: anywhere; }
    .district-name { display:block; font-size:clamp(36px,5vw,52px); font-weight:800;
      color:#B45309; margin-bottom:6px; }
    .detail { color: #4A5270; margin: 0; font-size: 16px; line-height: 1.6; }
    .battery { width: 152px; height: 66px; flex: 0 0 auto; position: relative;
      border: 4px solid var(--status-color, #64748B); border-radius: 13px; background: #E5E7EB; }
    .battery::after { content: ''; position: absolute; right: -13px; top: 20px;
      height: 25px; width: 8px; border-radius: 0 4px 4px 0; background: var(--status-color, #64748B); }
    .fill { position: absolute; inset: 5px; border-radius: 5px; background: var(--status-color, #64748B);
      transform: scaleX(0); transform-origin: left center; }
    .divider { position: absolute; top: 4px; bottom: 4px; width: 4px; background: white; }
    .first { left: 33.33%; } .second { left: 66.66%; }
    .bolt { position: absolute; width: 24px; height: 32px; left: 64px; top: 17px; }
    @media (max-width: 480px) {
      .scene { padding: 20px; gap: 22px; flex-direction: column; align-items: flex-start; }
      .title { font-size: 24px; } .battery { margin-bottom: 4px; }
    }
    """,
    js="""
    export default function ({ data, parentElement }) {
      const scene = parentElement.querySelector('.scene');
      scene.classList.toggle('compact', Boolean(data.compact));
      const fill = parentElement.querySelector('.fill');
      const battery = parentElement.querySelector('.battery');
      parentElement.querySelector('.district-name').textContent = data.district_name;
      parentElement.querySelector('.title-copy').textContent = data.title_copy;
      parentElement.querySelector('.detail').textContent = data.detail;
      battery.setAttribute('aria-label', data.accessibleLabel);
      const level = Math.max(0, Math.min(3, Number(data.level) || 0));
      const target = level / 3;
      battery.style.setProperty('--status-color', data.color);
      battery.dataset.level = String(level);
      fill.getAnimations().forEach(animation => animation.cancel());
      fill.style.transform = `scaleX(${target})`;
      if (data.animate && !scene.dataset.opened &&
          !window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
        fill.animate([{ transform: 'scaleX(0)' }, { transform: `scaleX(${target})` }],
          { duration: 1100, easing: 'cubic-bezier(.2,.7,.2,1)' });
      }
      scene.dataset.opened = 'true';
      return () => fill.getAnimations().forEach(animation => animation.cancel());
    }
    """,
)


def _level(row: pd.Series) -> tuple[str, int]:
    ratio, rank = row.get("charger_per_electric_vehicle"), row.get("charger_per_electric_vehicle_rank")
    if any(value is None or pd.isna(value) for value in (ratio, rank)):
        return "자료 없음", 0
    if float(ratio) < 0 or not 1 <= int(rank) <= 25:
        return "자료 없음", 0
    if rank <= 8:
        return "많은 편", 3
    if rank <= 17:
        return "보통", 2
    return "적은 편", 1


def charging_summary(row: pd.Series, district: str) -> None:
    level, cells = _level(row)
    ratio = row.get("charger_per_electric_vehicle")
    rank = row.get("charger_per_electric_vehicle_rank")
    rank_label = f"서울 25구 중 {int(rank)}위" if cells else "순위 자료 없음"
    _GAUGE(data={"district_name": district, "title_copy": f"충전기는 {level}",
                 "detail": f"전기차 한 대당 {number(ratio, 2, '기')} · {rank_label}",
                 "level": cells, "color": ("#64748B", "#DC2626", "#EAB308", "#15803D")[cells],
                 "animate": False, "compact": True,
                 "accessibleLabel": f"{district} 충전 여건 {level}, {cells}칸. {rank_label}. 실시간 빈자리가 아닌 수록 충전기 비율이에요."},
           key="parking_charging_summary", width="stretch", height="content")
    st.caption("전기차 대비 수록 충전기 비율이에요. 실시간 빈자리·배터리 잔량과는 달라요.")
    st.page_link("app_pages/charging.py", label="전기차 충전 상세보기", icon=":material/ev_station:")
