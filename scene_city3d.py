import json
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from db import queries as q
from kakao_map import SDK_LOADER_JS, javascript_key
from ui import date_text, load_frame, remember_region, word


KEY = "ownership_city_hero"
_CARS = (Path(__file__).parent / "assets" / "three_cars.svg").read_text(encoding="utf-8")

HTML = """
<section class="h2-hero" aria-labelledby="h2-title">
  <div class="h2-copy">
    <div class="h2-brandline"><span class="h2-wordmark">차차차</span>
      <span class="h2-eyebrow">서울 25구 · 차량 보유 현황</span>
      <span class="h2-cars" aria-hidden="true">__CARS__</span>
    </div>
    <h1 id="h2-title">우리 동네에는<br><em>차가 얼마나 있을까요?</em></h1>
    <p class="h2-intro">서울 25구의 등록 차량을 입체 지도로 보여 드려요.<br>구를 누르면 차량 보유, 주차, 차 필요성을 확인할 수 있어요.</p>
    <div class="h2-local" aria-live="polite" aria-atomic="true">
      <p class="h2-now"><span class="h2-status-dot"></span>지금 살펴보는 동네 <strong class="h2-selected-name"></strong></p>
      <dl class="h2-criteria">
        <div><dt>차량 보유</dt><dd data-level="ownership">자료 없음</dd></div>
        <div><dt>주차 여건</dt><dd data-level="parking">자료 없음</dd></div>
        <div><dt>차 필요</dt><dd data-level="need">자료 없음</dd></div>
      </dl>
    </div>
  </div>
  <div class="h2-scene">
    <div class="h2-map-heading"><span>서울 25구 등록 차량</span><span class="h2-count"></span></div>
    <svg class="h2-city" viewBox="0 0 720 400" role="group" aria-label="서울 구별 자동차 등록 대수 입체 지도. 각 구를 눌러 선택하세요.">
      <defs>
        <radialGradient id="h2-ground-glow"><stop stop-color="#8E98CF" stop-opacity=".20"/><stop offset="1" stop-color="#8E98CF" stop-opacity="0"/></radialGradient>
        <linearGradient id="h2-top" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#C2CAED"/><stop offset="1" stop-color="#8E98CF"/></linearGradient>
        <linearGradient id="h2-coral" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#FFA18F"/><stop offset="1" stop-color="#FF7A66"/></linearGradient>
        <pattern id="h2-missing" width="6" height="6" patternUnits="userSpaceOnUse"><path d="M0 6L6 0" stroke="#8E98CF" stroke-width="1"/></pattern>
      </defs>
      <ellipse cx="365" cy="265" rx="325" ry="145" fill="url(#h2-ground-glow)"/>
      <g class="h2-grid" aria-hidden="true"></g>
      <g class="h2-footprints" aria-hidden="true"></g>
      <g class="h2-districts"></g>
      <g class="h2-pin" aria-hidden="true" pointer-events="none">
        <circle class="h2-pin-halo" r="11" fill="#FF7A66" opacity=".17"/>
        <circle r="3.5" fill="#FFF" stroke="#FF7A66" stroke-width="2"/>
        <path d="M0 -9V-30" stroke="#FFD7CF" stroke-width="1.5"/>
        <rect x="-37" y="-54" width="74" height="25" rx="12.5" fill="#EEF0FA"/>
        <text class="h2-pin-name" text-anchor="middle" y="-37" fill="#1B2340" font-size="13" font-weight="700"></text>
      </g>
    </svg>
    <div class="h2-kakao" role="group" aria-label="서울 구별 자동차 등록 대수 지도. 구 이름을 눌러 동네를 선택하세요."></div>
    <div class="h2-readout" aria-hidden="true"><span class="h2-readout-name"></span><strong class="h2-readout-count"></strong><span class="h2-readout-hint">등록 자동차</span></div>
    <p class="h2-empty" hidden>지도 경계 자료가 없어요.<br>위에서 동네를 선택해 주세요.</p>
    <div class="h2-map-bottom"><span class="h2-legend"><i></i>높이 = 등록 대수 <span class="h2-month"></span></span><span class="h2-map-instruction">궁금한 구를 눌러 주세요 <b>↗</b></span></div>
    <p class="h2-source">통계청 2013년 구 경계 · 높이는 현재 교통량과 달라요</p>
  </div>
</section>
""".replace("__CARS__", _CARS)

# 내용 높이에 맞춰 영역이 늘어나야 모바일에서도 아래 지표와 겹치지 않는다.
CSS = """
.st-key-ownership_hero {
  padding: 0; background: #27336B;
  box-shadow: 0 0 0 100vmax #27336B; clip-path: inset(0 -100vmax);
}
.h2-hero, .h2-hero * { box-sizing: border-box; }
.h2-hero {
  --h2-light: #EEF0FA; --h2-muted: #B9C1E4;
  display: grid; grid-template-columns: minmax(360px, .92fr) minmax(0, 1.2fr);
  align-items: center; gap: 22px; min-height: 436px; padding: 28px 0 36px;
  color: var(--h2-light); font-family: 'Noto Sans KR', var(--st-font, sans-serif);
  position: relative; isolation: isolate; width: 100%; min-width: 0;
}
.h2-hero .h2-copy { min-width: 0; }
.h2-hero p, .h2-hero h1, .h2-hero dl, .h2-hero dd { margin: 0; padding: 0; }
.h2-hero .h2-brandline { display: flex; align-items: center; gap: 13px; margin-bottom: 17px; }
.h2-hero .h2-wordmark { font-family: 'Jua', var(--st-heading-font, sans-serif); font-size: 25px; color: #EEF0FA; white-space: nowrap; }
.h2-hero .h2-eyebrow { font-size: 14px; color: var(--h2-muted); white-space: nowrap; letter-spacing: .04em; }
.h2-hero .h2-cars { display: block; width: 100px; margin-left: auto; transform: rotate(-4deg); }
.h2-hero .h2-cars svg { width: 100%; height: auto; display: block; }
.h2-hero h1 { color: #EEF0FA; font: 400 clamp(36px, 3.7vw, 54px)/1.19 'Jua', var(--st-heading-font, sans-serif); letter-spacing: -.035em; word-break: keep-all; }
.h2-hero h1 em { font-style: normal; color: #FF9A87; }
.h2-hero .h2-intro { margin-top: 18px; font-size: 17px; line-height: 1.8; color: #D2D8EF; letter-spacing: -.025em; }
.h2-hero .h2-local { margin-top: 22px; }
.h2-hero .h2-now { display: flex; align-items: center; gap: 7px; font-size: 13px; color: var(--h2-muted); }
.h2-hero .h2-now strong { color: #FF9A87; font-size: 30px; margin-left: 3px; }
.h2-hero .h2-status-dot { width: 5px; height: 5px; background: #FF7A66; border-radius: 50%; }
.h2-hero .h2-criteria { display: grid; grid-template-columns: .8fr .8fr 1.4fr; gap: 16px; margin-top: 11px; }
.h2-hero .h2-criteria > div { border-top: 1px solid #4B5578; padding-top: 10px; min-width: 0; }
.h2-hero .h2-criteria dt { font-size: 13px; color: var(--h2-muted); margin-bottom: 5px; }
.h2-hero .h2-criteria dd { font-size: 16px; font-weight: 600; color: #EEF0FA; word-break: keep-all; }
.h2-hero .h2-scene { position: relative; min-width: 0; width: 100%; height: 370px; }
.h2-hero .h2-map-heading { position: absolute; left: 14px; right: 0; top: 3px; display: flex; justify-content: space-between; color: var(--h2-muted); font-size: 13px; letter-spacing: .03em; }
.h2-hero .h2-count { color: #EEF0FA; }
.h2-hero .h2-city { display: block; width: 100%; height: calc(100% - 29px); overflow: hidden; }
.h2-hero[data-map="kakao"] .h2-city, .h2-hero:not([data-map="kakao"]) .h2-kakao { display: none; }
.h2-hero[data-map="kakao"] .h2-scene { height: 560px; }
.h2-hero[data-map="kakao"] .h2-readout { top: 36px; left: 10px; right: auto; z-index: 1; padding: 8px 12px; border-radius: 12px; background: #27336BE6; text-align: left; }
.h2-hero[data-map="kakao"] .h2-map-bottom { margin-top: 8px; }
.h2-hero .h2-kakao { position: relative; isolation: isolate; width: 100%; height: calc(100% - 55px); margin-top: 26px; border-radius: 16px; overflow: hidden; background: #EEF0FA; }
/* 고정 지도가 터치를 잡고 있으면 지도 위에서 페이지를 내릴 수 없다. */
.h2-hero .h2-kakao * { touch-action: auto !important; }
.h2-hero .h2-bar { position: absolute; display: flex; flex-direction: column; align-items: center; gap: 3px; padding: 0; border: 0; background: none; color: #1B2340; font: 700 13px/1.2 'Noto Sans KR', var(--st-font, sans-serif); cursor: pointer; white-space: nowrap; transform: translate(-50%, -100%); }
.h2-hero .h2-bar-stem { display: block; width: 12px; height: 0; border-radius: 4px 4px 0 0; background: #27336B; box-shadow: inset -4px 0 0 #00000026; transition: height .7s cubic-bezier(.2,.7,.2,1); }
.h2-hero .h2-bar-name { padding: 1px 4px; border-radius: 6px; background: #FFFFFFE6; }
.h2-hero .h2-kakao[data-compact="true"] .h2-bar { gap: 2px; font-size: 12px; line-height: 15px; }
.h2-hero .h2-kakao[data-compact="true"] .h2-bar-stem { width: 6px; box-shadow: none; }
.h2-hero .h2-kakao[data-compact="true"] .h2-bar-name { padding: 0 2px; }
.h2-hero .h2-bar[aria-pressed="true"] .h2-bar-stem { background: #FF7A66; }
.h2-hero .h2-bar[aria-pressed="true"] .h2-bar-name { background: #27336B; color: #FFF; }
.h2-hero .h2-bar[data-missing="true"] .h2-bar-stem { background: none; border: 1px dashed #4A5270; }
.h2-hero .h2-bar:focus-visible { outline: none; }
.h2-hero .h2-bar:focus-visible .h2-bar-name { outline: 3px solid #27336B; outline-offset: 1px; }
.h2-hero .h2-grid { fill: none; stroke: #8E98CF; stroke-width: .65; opacity: .13; }
.h2-hero .h2-footprints { fill: #36416A; stroke: #7884B3; stroke-width: .7; opacity: .55; }
.h2-hero .h2-district { cursor: pointer; outline: none; }
.h2-hero .h2-top { fill: url(#h2-top); stroke: #C8D0EE; stroke-width: .75; stroke-linejoin: round; }
.h2-hero .h2-side-light { fill: #5B69A1; stroke: #6573AA; stroke-width: .35; }
.h2-hero .h2-side-dark { fill: #3E4C82; stroke: #49578B; stroke-width: .35; }
.h2-hero .h2-district[data-selected="true"] .h2-top { fill: url(#h2-coral); stroke: #FFD4C9; stroke-width: 1.5; }
.h2-hero .h2-district[data-selected="true"] .h2-side-light { fill: #D66A60; stroke: #E58070; }
.h2-hero .h2-district[data-selected="true"] .h2-side-dark { fill: #A64E50; stroke: #BD5C59; }
.h2-hero .h2-district[data-missing="true"] .h2-top { fill: url(#h2-missing); }
.h2-hero .h2-district:hover .h2-top, .h2-hero .h2-district:focus-visible .h2-top { stroke: #FFF; stroke-width: 2.5; }
.h2-hero .h2-district:focus-visible { filter: drop-shadow(0 0 4px #EEF0FA); }
.h2-hero .h2-readout { position: absolute; right: 0; top: 33px; text-align: right; pointer-events: none; }
.h2-hero .h2-readout-name { color: #FFAE9F; font-size: 15px; font-weight: 600; }
.h2-hero .h2-readout-count { display: block; color: #EEF0FA; font-size: 28px; line-height: 1.4; font-weight: 700; letter-spacing: -.04em; font-variant-numeric: tabular-nums; }
.h2-hero .h2-readout-hint { font-size: 13px; color: var(--h2-muted); }
.h2-hero .h2-map-bottom { display: flex; justify-content: space-between; align-items: center; gap: 8px; margin-top: -8px; font-size: 13px; color: #CBD2ED; }
.h2-hero .h2-legend { display: flex; gap: 7px; align-items: center; white-space: nowrap; }
.h2-hero .h2-legend i { display: inline-block; width: 8px; height: 8px; background: #8E98CF; border-radius: 2px; }
.h2-hero .h2-month { color: #B9C1E4; font-size: 13px; }
.h2-hero .h2-map-instruction b { color: #FF9A87; font-size: 16px; margin-left: 4px; }
.h2-hero .h2-source { color: #ABB5DA; font-size: 13px; margin-top: 7px; text-align: right; }
.h2-hero .h2-empty { position: absolute; top: 42%; width: 100%; text-align: center; color: #EEF0FA; font-size: 14px; line-height: 1.8; }
.h2-hero .h2-pin-halo { transform-origin: center; animation: h2-breathe 6s ease-in-out infinite; }
.h2-hero .h2-local.h2-changed { animation: h2-response .42s ease-out; }
@keyframes h2-breathe { 0%, 100% { opacity: .12; } 50% { opacity: .3; } }
@keyframes h2-response { 0% { opacity: .55; transform: translateY(3px); } 100% { opacity: 1; transform: translateY(0); } }
@media (max-width: 1050px) and (min-width: 701px) {
  .h2-hero { grid-template-columns: minmax(300px, .95fr) minmax(0, 1.05fr); gap: 8px; min-height: 420px; }
  .h2-hero .h2-cars { width: 77px; }
  .h2-hero .h2-eyebrow { font-size: 13px; }
  .h2-hero .h2-map-instruction { display: none; }
  .h2-hero .h2-readout-count { font-size: 24px; }
  .h2-hero .h2-criteria { gap: 9px; }
  .h2-hero .h2-criteria dd { font-size: 14px; }
}
@media (max-width: 700px) {
  .h2-hero { display: flex; flex-direction: column; align-items: stretch; gap: 12px; min-height: 0; padding: 20px 0 28px; }
  .h2-hero .h2-brandline { gap: 9px; margin-bottom: 7px; height: 25px; }
  .h2-hero .h2-wordmark { font-size: 21px; }
  .h2-hero .h2-eyebrow { font-size: 12px; }
  .h2-hero .h2-cars { width: 74px; }
  .h2-hero h1 { font-size: 31px; line-height: 1.1; letter-spacing: -.03em; }
  .h2-hero h1 br { display: none; }
  .h2-hero h1 em { display: block; }
  .h2-hero .h2-intro { font-size: 13px; line-height: 1.7; margin-top: 8px; }
  .h2-hero .h2-local { margin-top: 9px; }
  .h2-hero .h2-now { font-size: 12px; }
  .h2-hero .h2-now strong { font-size: 24px; }
  .h2-hero .h2-criteria { margin-top: 6px; gap: 10px; }
  .h2-hero .h2-criteria > div { padding-top: 5px; }
  .h2-hero .h2-criteria dt { font-size: 12px; margin-bottom: 2px; }
  .h2-hero .h2-criteria dd { font-size: 13px; }
  .h2-hero .h2-scene { flex: none; height: 245px; margin-top: 3px; }
  .h2-hero[data-map="kakao"] .h2-scene { height: 380px; }
  .h2-hero[data-map="kakao"] .h2-readout { top: 0; left: 0; right: 0; display: flex; align-items: baseline; gap: 6px; padding: 0; background: none; }
  .h2-hero[data-map="kakao"] .h2-readout-count { line-height: 1.25; }
  .h2-hero .h2-city { height: calc(100% - 17px); }
  .h2-hero .h2-map-heading { display: none; }
  .h2-hero .h2-readout { top: 9px; }
  .h2-hero .h2-readout-name { font-size: 12px; }
  .h2-hero .h2-readout-count { font-size: 20px; }
  .h2-hero .h2-readout-hint { font-size: 12px; }
  .h2-hero .h2-map-bottom { margin-top: -3px; font-size: 12px; gap: 2px; }
  .h2-hero .h2-legend { gap: 4px; }
  .h2-hero .h2-month { font-size: 12px; }
  .h2-hero .h2-map-instruction b { font-size: 12px; margin-left: 0; }
  .h2-hero .h2-source { font-size: 12px; margin-top: 3px; }
}
@media (prefers-reduced-motion: reduce) {
  .h2-hero *, .h2-hero *::before, .h2-hero *::after { animation: none !important; transition: none !important; }
}
"""

JS = """
// 새로고침 전에는 메뉴를 오가도 오프닝이 반복되지 않도록 한다.

const instances = new WeakMap();
const opened = new Set();
const NS = 'http://www.w3.org/2000/svg';
const number = new Intl.NumberFormat('ko-KR');
const NAME_SHIFT = {양천구: [-20, 0], 도봉구: [4, 0], 서대문구: [4, 4], 중랑구: [8, 0], 마포구: [0, 4], 노원구: [4, 0]};
const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
const ease = t => 1 - Math.pow(1 - clamp(t, 0, 1), 3);
const path = points => points.length ? 'M' + points.map(p => p.map(v => v.toFixed(2)).join(',')).join('L') + 'Z' : '';
function svg(tag, attrs = {}) {
  const node = document.createElementNS(NS, tag);
  Object.entries(attrs).forEach(([key, value]) => node.setAttribute(key, value));
  return node;
}
function project([lon, lat]) {
  
  const east = (lon - 126.98) * Math.cos(37.56 * Math.PI / 180);
  const south = 37.56 - lat;
  return [(east - south) * Math.sqrt(3) / 2, (east + south) / 2];
}
function buildCity(state) {
  const { root, data } = state;
  const layer = root.querySelector('.h2-districts');
  const ground = root.querySelector('.h2-footprints');
  const grid = root.querySelector('.h2-grid');
  layer.replaceChildren(); ground.replaceChildren(); grid.replaceChildren();
  const points = data.districts.flatMap(d => d.polygons.flat(2).map(project));
  if (!points.length) { state.nodes = []; return; }
  const xs = points.map(p => p[0]), ys = points.map(p => p[1]);
  const x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ys), y1 = Math.max(...ys);
  const scale = Math.min(585 / (x1 - x0 || 1), 220 / (y1 - y0 || 1));
  const screen = coord => {
    const p = project(coord);
    return [350 + (p[0] - (x0 + x1) / 2) * scale, 255 + (p[1] - (y0 + y1) / 2) * scale];
  };
  for (let offset = -4; offset <= 4; offset++) {
    grid.append(svg('path', {d: `M${92+offset*39} ${255-offset*22}l310 179M${295+offset*39} ${126+offset*22}l-250 144`}));
  }
  const max = Math.max(1, ...data.districts.map(d => d.count ?? 0));
  state.nodes = data.districts.filter(d => d.polygons.length).map(d => {
    const center = screen(d.center);
    const polygons = d.polygons.map(poly => poly.map(ring => ring.map(coord => {
      const p = screen(coord);
      return [center[0] + (p[0]-center[0])*.965, center[1] + (p[1]-center[1])*.965];
    })));
    const group = svg('g', {'class':'h2-district', 'role':'button', 'tabindex':'0',
      'data-region-id':d.id, 'data-missing':d.count === null,
      'aria-label':`${d.name}, 등록 자동차 ${d.count === null ? '자료 없음' : number.format(d.count)+'대'}, 차량 보유 ${d.levels.ownership}. 동네 선택`});
    const dark = svg('path', {'class':'h2-side-dark'});
    const light = svg('path', {'class':'h2-side-light'});
    const top = svg('path', {'class':'h2-top', 'fill-rule':'evenodd'});
    group.append(dark, light, top);
    ground.append(svg('path', {d: polygons.flatMap(poly => poly.map(path)).join(''), 'fill-rule':'evenodd'}));
    group.onpointerenter = () => hover(state, d.id);
    group.onpointerleave = () => hover(state, null);
    group.onfocus = () => hover(state, d.id);
    group.onblur = () => hover(state, null);
    group.onclick = () => choose(state, d.id);
    group.onkeydown = event => {
      if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); choose(state, d.id); }
      if (['ArrowRight','ArrowLeft','ArrowUp','ArrowDown'].includes(event.key)) {
        event.preventDefault();
        const current = state.nodes.findIndex(n => n.data.id === d.id);
        const step = ['ArrowRight','ArrowDown'].includes(event.key) ? 1 : -1;
        state.nodes[(current + step + state.nodes.length) % state.nodes.length].group.focus();
      }
    };
    return {data:d, group, dark, light, top, polygons, center, height:(d.count ?? 0)/max*116, lift:0};
  }).sort((a,b) => a.center[1]-b.center[1]);
  state.nodes.forEach((node,index) => {node.delay = index*35; layer.append(node.group);});
}
function readout(state, id) {
  const d = state.data.districts.find(d => d.id === id);
  state.root.querySelector('.h2-readout-name').textContent = d?.name ?? state.data.selected_name;
  state.root.querySelector('.h2-readout-count').textContent = d?.count == null ? '자료 없음' : number.format(d.count)+'대';
  state.root.querySelector('.h2-readout-hint').textContent = state.hovered && state.hovered !== state.selected ? '눌러서 이 동네 선택' : '등록 자동차';
}
function reconcile(state, id, react = false) {
  state.selected = id;
  const d = state.data.districts.find(d => d.id === id);
  state.root.querySelector('.h2-selected-name').textContent = d?.name ?? state.data.selected_name;
  state.root.querySelector('.h2-pin-name').textContent = d?.name ?? '';
  for (const topic of ['ownership','parking','need']) {
    const el = state.root.querySelector(`[data-level="${topic}"]`);
    const level = d?.levels[topic] ?? '자료 없음';
    const states = {ownership: {'많은 편':'주의','보통':'보통','적은 편':'충분'}, parking: {'좋음':'충분','보통':'보통','빠듯함':'주의'}, need: {'차가 필요한 편':'주의','있으면 편함':'보통','대중교통으로 충분':'충분'}};
    const status = states[topic][level];
    el.textContent = status && status !== level ? `${status} · ${level}` : level;
    el.style.color = {'주의':'#FF8A80','보통':'#FACC15','충분':'#86EFAC'}[status] || '#EEF0FA';
  }
  state.nodes.forEach(n => {
    const selected = n.data.id === id;
    n.group.dataset.selected = String(selected);
    n.group.setAttribute('aria-pressed', String(selected));
  });
  if (react && !state.reduced) {
    const local = state.root.querySelector('.h2-local');
    local.classList.remove('h2-changed'); void local.offsetWidth; local.classList.add('h2-changed');
  }
  readout(state, state.hovered ?? id);
  paintKakao(state);
  schedule(state);
}
function paintKakao(state) {
  if (!state.kakao) return;
  state.kakao.items.forEach(item => {
    const selected = item.id === state.selected;
    const hovered = item.id === state.hovered;
    item.button.setAttribute('aria-pressed', String(selected));
    item.shapes.forEach(shape => shape.setOptions({
      fillColor: selected ? '#FF7A66' : '#8E98CF',
      fillOpacity: selected ? .6 : hovered ? .55 : .38,
      strokeColor: selected ? '#C24C38' : hovered ? '#27336B' : '#FFFFFF',
      strokeWeight: selected || hovered ? 3 : 1.5,
    }));
  });
}
function clearKakao(state) {
  state.kakao.items.forEach(item => {
    item.overlay.setMap(null);
    item.shapes.forEach(shape => shape.setMap(null));
  });
  state.kakao.items = [];
}
function fitKakao(state) {
  if (!state.kakao.items.length) return;
  state.kakao.map.relayout();
  state.kakao.map.setBounds(state.kakao.bounds, 12, 12, 12, 12);
  placeKakao(state);
}
// 좁은 칸은 축척이 한 단계 작아 짧은 이름과 낮은 막대를 쓴다. 구 경계는 고정 자료라 겹치는 이름표의 이동량도 고정이다.
function placeKakao(state) {
  const {map, items} = state.kakao;
  const compact = map.getLevel() > 9;
  state.root.querySelector('.h2-kakao').dataset.compact = String(compact);
  const max = Math.max(1, ...items.map(item => item.count ?? 0));
  items.forEach(item => {
    const [x, y] = compact ? NAME_SHIFT[item.label] ?? [0, 0] : [0, 0];
    item.name.textContent = compact && item.label.length > 2 ? item.label.slice(0, -1) : item.label;
    item.name.style.transform = `translate(${x}px, ${y}px)`;
    requestAnimationFrame(() => {
      item.stem.style.height = (item.count === null ? 12 : Math.max(4, Math.round(item.count / max * (compact ? 20 : 52)))) + 'px';
    });
  });
}
function drawKakao(state) {
  const {api, map} = state.kakao;
  clearKakao(state);
  const bounds = new api.maps.LatLngBounds();
  const districts = state.data.districts.filter(d => d.polygons.length);
  state.kakao.items = districts.map(d => {
    const shapes = d.polygons.map(rings => {
      const path = rings.map(ring => ring.map(([lon, lat]) => {
        const point = new api.maps.LatLng(lat, lon);
        bounds.extend(point);
        return point;
      }));
      const shape = new api.maps.Polygon({map, path});
      api.maps.event.addListener(shape, 'click', () => choose(state, d.id));
      api.maps.event.addListener(shape, 'mouseover', () => hover(state, d.id));
      api.maps.event.addListener(shape, 'mouseout', () => hover(state, null));
      return shape;
    });
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'h2-bar';
    button.dataset.regionId = d.id;
    button.dataset.missing = String(d.count === null);
    button.setAttribute('aria-label', `${d.name}, 등록 자동차 ${d.count === null ? '자료 없음' : number.format(d.count)+'대'}, 차량 보유 ${d.levels.ownership}. 동네 선택`);
    const stem = document.createElement('span');
    stem.className = 'h2-bar-stem';
    const name = document.createElement('span');
    name.className = 'h2-bar-name';
    name.textContent = d.name;
    button.append(stem, name);
    button.onclick = () => choose(state, d.id);
    button.onpointerenter = button.onfocus = () => hover(state, d.id);
    button.onpointerleave = button.onblur = () => hover(state, null);
    button.onkeydown = event => {
      if (!['ArrowRight','ArrowLeft','ArrowUp','ArrowDown'].includes(event.key)) return;
      event.preventDefault();
      const items = state.kakao.items;
      const current = items.findIndex(item => item.id === d.id);
      const step = ['ArrowRight','ArrowDown'].includes(event.key) ? 1 : -1;
      items[(current + step + items.length) % items.length].button.focus();
    };
    // SDK는 앵커를 처음 크기로 한 번만 계산한다. CSS로 밑변을 구 중심에 맞추고, SDK가 감싼 칸은 크기를 없애 클릭을 가로채지 않게 한다.
    const overlay = new api.maps.CustomOverlay({
      map, content: button, clickable: true, xAnchor: 0, yAnchor: 0, zIndex: 2,
      position: new api.maps.LatLng(d.center[1], d.center[0]),
    });
    return {id: d.id, label: d.name, count: d.count, shapes, button, stem, name, overlay};
  });
  state.kakao.bounds = bounds;
  // 경계 자료가 비면 빈 지도 대신 SVG 쪽 안내를 보여 준다.
  if (districts.length) state.root.dataset.map = 'kakao';
  else delete state.root.dataset.map;
  fitKakao(state);
}
function startKakao(state, appkey) {
  state.kakaoRequested = true;
  window.chachachaKakao(appkey).then(api => {
    if (state.disposed) return;
    const element = state.root.querySelector('.h2-kakao');
    // 크기가 0인 칸에 지도를 만들지 않도록 먼저 영역을 보이게 한다.
    state.root.dataset.map = 'kakao';
    const map = new api.maps.Map(element, {
      center: new api.maps.LatLng(37.56, 126.98), level: 9,
      draggable: false, scrollwheel: false, disableDoubleClickZoom: true,
    });
    // 더 축소되면 25구 이름이 들어갈 자리가 없다.
    map.setMaxLevel(10);
    // SDK가 터치를 취소하면 지도 위에서 페이지를 내릴 수 없다. 탭 판정은 SDK에 그대로 맡긴다.
    ['touchstart', 'touchmove'].forEach(type => element.addEventListener(type, event => {
      event.preventDefault = () => {};
      Object.defineProperty(event, 'returnValue', {set() {}});
    }, {capture: true, passive: true}));
    state.kakao = {api, map, items: [], bounds: null};
    drawKakao(state);
    paintKakao(state);
    state.kakao.observer = new ResizeObserver(() => fitKakao(state));
    state.kakao.observer.observe(element);
  }).catch(() => {
    state.kakao = null;
    delete state.root.dataset.map;
  });
}
function choose(state, id) {
  if (state.selected === id) return;
  reconcile(state, id, true);
  state.emit('district', id);
}
function hover(state, id) {
  state.hovered = id;
  readout(state, id ?? state.selected);
  paintKakao(state);
  schedule(state);
}
function draw(state, now) {
  state.raf = null;
  const elapsed = now - state.started;
  let moving = false;
  let opening = false;
  const pin = state.root.querySelector('.h2-pin');
  pin.style.display = 'none';
  state.nodes.forEach(node => {
    const progress = state.introDone || state.reduced ? 1 : ease((elapsed-node.delay)/1120);
    if (progress < 1) { moving = true; opening = true; }
    const targetLift = state.hovered === node.data.id && !state.reduced ? 9 : 0;
    node.lift = state.reduced ? 0 : node.lift + (targetLift-node.lift)*.24;
    if (Math.abs(targetLift-node.lift) > .08) moving = true;
    else node.lift = targetLift;
    const height = node.height*progress;
    const dark = [], light = [], top = [];
    node.polygons.forEach(poly => poly.forEach(ring => {
      top.push(path(ring.map(([x,y]) => [x,y-height-node.lift])));
      for (let i=0; i<ring.length-1; i++) {
        const a=ring[i], b=ring[i+1];
        const face=path([[a[0],a[1]-node.lift],[b[0],b[1]-node.lift],
          [b[0],b[1]-height-node.lift],[a[0],a[1]-height-node.lift]]);
        (b[0]-a[0] > 0 ? light : dark).push(face);
      }
    }));
    node.dark.setAttribute('d',dark.join(''));
    node.light.setAttribute('d',light.join(''));
    node.top.setAttribute('d',top.join(''));
    if (node.data.id === state.selected) {
      pin.style.display = '';
      pin.setAttribute('transform',`translate(${node.center[0]},${node.center[1]-height-node.lift})`);
    }
  });
  
  if (!opening || state.reduced) state.introDone = true;
  state.root.dataset.intro = state.introDone ? 'complete' : 'playing';
  if (moving) schedule(state);
}
function schedule(state) {
  if (state.raf === null && !state.disposed) state.raf = requestAnimationFrame(now => draw(state,now));
}
export default function(component) {
  const {parentElement, data, setTriggerValue} = component;
  const root = parentElement.querySelector('.h2-hero');
  if (!root || !data) return;
  let state = instances.get(parentElement);
  if (!state) {
    const media = window.matchMedia('(prefers-reduced-motion: reduce)');
    state = {root, data, nodes:[], selected:null, hovered:null, raf:null, disposed:false,
      reduced:media.matches, introDone:opened.has(data.instance_key) || media.matches,
      started:performance.now(), media, signature:null, emit:setTriggerValue};
    opened.add(data.instance_key);
    state.motionChange = event => {
      state.reduced = event.matches;
      if (event.matches) state.introDone = true;
      schedule(state);
    };
    media.addEventListener('change',state.motionChange);
    instances.set(parentElement,state);
  }
  state.data = data; state.emit = setTriggerValue;
  const signature = JSON.stringify(data.districts);
  if (state.signature !== signature) {
    state.signature = signature;
    buildCity(state);
    if (state.kakao) drawKakao(state);
  }
  root.querySelector('.h2-empty').hidden = state.nodes.length > 0;
  root.querySelector('.h2-count').textContent = state.nodes.length ? state.nodes.length+'개의 동네' : '자료 없음';
  root.querySelector('.h2-month').textContent = '· '+data.month;
  const changed = state.selected !== null && state.selected !== data.selected_id;
  reconcile(state,data.selected_id,changed);
  if (data.kakao_key && state.nodes.length && !state.kakaoRequested) startKakao(state, data.kakao_key);

  if (state.reduced) { if (state.raf !== null) cancelAnimationFrame(state.raf); draw(state,performance.now()); }
  return () => {
    state.disposed = true;
    if (state.raf !== null) cancelAnimationFrame(state.raf);
    state.media.removeEventListener('change',state.motionChange);
    if (state.kakao) { state.kakao.observer?.disconnect(); clearKakao(state); state.kakao = null; }
    state.nodes.forEach(n => {
      n.group.onpointerenter = n.group.onpointerleave = n.group.onfocus = n.group.onblur = null;
      n.group.onclick = n.group.onkeydown = null;
    });
    instances.delete(parentElement);
  };
}
"""

_HERO = st.components.v2.component(
    "chachacha_h2_seoul", html=HTML, css=CSS, js=SDK_LOADER_JS + JS, isolate_styles=False,
)


def _payload(ranking: pd.DataFrame, boundaries: pd.DataFrame,
             selected_id: int | None, selected_name: str) -> dict[str, Any]:
    # 결측값과 등록 0대를 구분해야 하므로 차량 수가 없으면 None을 유지한다.
    metrics = {int(row.region_id): row for _, row in ranking.iterrows()}
    shapes = {int(row.region_id): row for _, row in boundaries.iterrows()}
    districts = []
    for region_id in sorted(metrics.keys() | shapes.keys()):
        row = metrics.get(region_id, pd.Series(dtype=object))
        boundary = shapes.get(region_id)
        polygons = []
        center = None
        if boundary is not None:
            geometry = json.loads(boundary.geometry_json)
            polygons = (geometry["coordinates"] if geometry["type"] == "MultiPolygon"
                        else [geometry["coordinates"]])
            center = [float(boundary.centroid_longitude), float(boundary.centroid_latitude)]
        raw = row.get("vehicle_count")
        count = None if raw is None or pd.isna(raw) else int(raw)
        districts.append({
            "id": region_id,
            "name": word(row.get("district_name"), str(boundary.district_name)
                         if boundary is not None else "자료 없음"),
            "count": count, "center": center,
            "polygons": polygons,
            "levels": {topic: word(row.get(f"{topic}_level"))
                       for topic in ("ownership", "parking", "need")},
        })
    months = ranking["stat_month"].dropna() if "stat_month" in ranking else pd.Series(dtype=object)
    return {
        "instance_key": KEY, "selected_id": selected_id, "selected_name": selected_name,
        "month": date_text(months.iloc[0], month=True) if not months.empty else "자료 없음",
        "districts": districts,
    }


def _select_district() -> None:
    # 구 선택 위젯이 만들어지기 전에 콜백에서 district_id를 갱신한다.
    event = st.session_state.get(KEY, {}).get("district")
    if (isinstance(event, int) and not isinstance(event, bool)
            and event in st.session_state.get("_h2_region_ids", ())
            and event != st.session_state.get("district_id")):
        st.session_state.district_id = event
        remember_region()


def render_hero(district_name: str, *, ranking: pd.DataFrame | None = None) -> None:
    if ranking is None:
        ranking = load_frame(q.get_district_ranking)
    boundaries = load_frame(q.get_region_boundaries)
    selected_id = st.session_state.get("district_id")
    data = {**_payload(ranking, boundaries, selected_id, district_name), "kakao_key": javascript_key()}
    st.session_state["_h2_region_ids"] = tuple(
        int(value) for value in ranking.get("region_id", pd.Series(dtype=int))
    )
    with st.container(key="ownership_hero", gap=0):
        _HERO(key=KEY, data=data, on_district_change=_select_district,
              width="stretch", height="content")
