import json
import math
from pathlib import Path
import xml.etree.ElementTree as ET

import pandas as pd
import streamlit as st

from car_expression import add_expression, FACE_JS
from db import queries as q
from ui import (COLORS, TOPICS, date_text, district_row, load_frame, neighborhood_sentence,
                mobility_mood, number, rank_text, remember_region, set_topic, topic_value, word)


KEY = "hero_h3_seoul_drawing"
TOPIC_LABELS = {topic: spec.title for topic, spec in TOPICS.items()}
TOPIC_LABELS["need"] = "대중교통 이용 지표"
TRANSIT_LEVELS = {"차가 필요한 편": "이용 적은 편", "있으면 편함": "이용 보통", "대중교통으로 충분": "이용 많은 편"}


def _car_svg(index: int) -> str:
    ET.register_namespace("", "http://www.w3.org/2000/svg")
    source = ET.parse(Path(__file__).parent / "assets" / "three_cars.svg")
    car = source.getroot()[0][index]
    car.attrib.pop("transform", None)
    add_expression(car, index)
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 112 120" '
            'aria-hidden="true"><g stroke="#1B2340" stroke-width="3.5" '
            'stroke-linecap="round" stroke-linejoin="round">'
            + ET.tostring(car, encoding="unicode") + "</g></svg>")


_CARS = [_car_svg(i) for i in range(3)]
HTML = """
<section class="hero" aria-label="차차차, 서울에서 차와 살기">
  <div class="intro">
    <p class="eyebrow"><span class="brand">차차차</span><span>서울의 자동차 생활 안내서</span></p>
    <h1>우리 동네,<br>차와 살기 좋을까요<span class="coral">?</span></h1>
    <p class="description">차량 보유, 주차 여건, 대중교통 이용 지표를 한눈에 확인할 수 있어요.</p>
  </div>
  <figure class="map-scene">
    <svg class="seoul" viewBox="0 0 740 620" aria-label="서울 구 지도. 구를 누르면 동네를 바꿀 수 있어요.">
      <defs>
        <pattern id="h3-dots" width="20" height="20" patternUnits="userSpaceOnUse">
          <circle cx="1" cy="1" r="1" fill="#8E98CF" opacity=".24"/>
        </pattern>
      </defs>
      <rect width="740" height="620" fill="url(#h3-dots)"/>
      <g class="districts"></g>
      <g class="travel" aria-hidden="true" pointer-events="none">
        <path class="road-edge" fill="none" stroke="#FFFFFF" stroke-width="8"/>
        <path class="road" fill="none" stroke="#8E98CF" stroke-width="5"/>
        <path class="road-center" fill="none" stroke="#FFFFFF" stroke-width="1.4" stroke-dasharray="3 6"/>
        <g class="destination"><circle class="halo" r="20" fill="#FF7A66" opacity=".2"/>
          <circle r="7" fill="#FF7A66" stroke="#FFFFFF" stroke-width="3"/>
        </g>
        <g class="car"><ellipse cx="0" cy="5" rx="6" ry="2" fill="#1B2340" opacity=".13"/>
          <g transform="translate(-8 -19) scale(.14)">__CAR__</g>
        </g>
      </g>
      <g class="label-lines" aria-hidden="true" pointer-events="none"></g>
      <g class="district-labels" aria-hidden="true"></g>
      <text class="map-empty" x="370" y="310" text-anchor="middle" fill="#4A5270" hidden>지도 경계 자료 없음</text>
    </svg>
    <div class="legend" aria-label="지도 판정 범례"></div>
    <figcaption><span class="map-guide">궁금한 구를 눌러 주세요</span><span class="source"></span></figcaption>
    <span class="hover-label" role="tooltip" hidden></span>
  </figure>
  <div class="arrival">
    <p class="summary-caption">한눈에 읽는 우리 동네</p>
    <p class="arrival-title" aria-hidden="true"><span class="typed"></span><span class="cursor">|</span></p>
    <p class="sentence"></p>
    <div class="verdicts" aria-label="선택한 동네의 세 가지 판정">__VERDICTS__</div>
    <p class="guide">세 기준을 누르면 지도가 바뀌어요.<br>서울 25구 안에서 비교한 참고 판정이에요. 대중교통은 주민 대비 수록 승객 수로, 개인의 차량 구매 필요를 뜻하지 않아요.</p>
    <span class="sr-only announcement" role="status" aria-live="polite" aria-atomic="true"></span>
  </div>
</section>
""".replace("__CAR__", _CARS[0]).replace("__VERDICTS__", "".join(
    f'<button type="button" class="verdict" data-topic="{topic}" aria-pressed="false">'
    f'{_CARS[index]}<span class="verdict-copy"><span class="topic-label">{label}</span>'
    '<strong class="level">자료 없음</strong></span>'
    '<span class="signals" aria-hidden="true"><span class="signal-dot signal-red"></span>'
    '<span class="signal-dot signal-yellow"></span><span class="signal-dot signal-green"></span></span></button>'
    for index, (topic, label) in enumerate(TOPIC_LABELS.items())
))

CSS = """
:host { display: block; width: 100%; }
* { box-sizing: border-box; }
.hero { min-height: 700px; display: grid; grid-template-columns: minmax(340px, .72fr) minmax(0, 1.28fr);
  grid-template-rows: auto 1fr; column-gap: 28px; color: #1B2340;
  font-family: 'Noto Sans KR', var(--st-font), sans-serif; font-size: 18px; }
p, figure, h1 { margin: 0; }
.intro { grid-column: 1; grid-row: 1; align-self: start; padding-top: 22px; }
.eyebrow { display: flex; gap: 13px; align-items: center; font-size: 13px; font-weight: 500; color: #4A5270; }
.brand { color: #27336B; font: 24px/1.1 'Jua', var(--st-heading-font), sans-serif; }
h1 { margin: 18px 0 14px; font: 48px/1.18 'Jua', var(--st-heading-font), sans-serif;
  letter-spacing: -.025em; color: #27336B; word-break: keep-all; }
.coral { color: #FF7A66; }
.description { max-width: 420px; font-size: 16px; line-height: 1.7; word-break: keep-all; }
.map-scene { grid-column: 2; grid-row: 1 / 3; position: relative; min-width: 0; display: flex; flex-direction: column; justify-content: center; }
.seoul { display: block; width: 100%; height: 600px; flex: 0 0 600px; overflow: visible; }
.district { cursor: pointer; stroke: #FFFFFF; stroke-width: 1.5; stroke-linejoin: round;
  vector-effect: non-scaling-stroke; outline: none; }
.district:hover, .district:focus-visible { stroke: #1B2340; stroke-width: 3; filter: brightness(1.06); }
.district[aria-pressed="true"] { stroke: #FF7A66; stroke-width: 3.5; }
.district:focus-visible { stroke-dasharray: 4 2 !important; }
.district-name { text-anchor: middle; dominant-baseline: central; paint-order: stroke fill;
  stroke-width: 3.5; stroke-linejoin: round; font-weight: 700; cursor: pointer; }
.label-line { stroke: #4A5270; stroke-width: 1; vector-effect: non-scaling-stroke; }
.car > g > svg { width: 112px; height: 120px; }
.legend { display: flex; justify-content: center; flex-wrap: wrap; gap: 6px 18px;
  min-height: 24px; color: #1B2340; font-size: 13px; line-height: 20px; }
.legend-item { display: inline-flex; align-items: center; gap: 6px; white-space: nowrap; }
.swatch { width: 14px; height: 14px; border-radius: 4px; border: 1px solid #8E98CF; }
figcaption { display: flex; justify-content: space-between; flex-wrap: wrap; gap: 3px 8px; padding: 6px 8px 0;
  color: #4A5270; font-size: 13px; }
.map-guide::before { content: ''; display: inline-block; height: 6px; width: 6px;
  margin-right: 6px; border-radius: 50%; background: #FF7A66; vertical-align: 2px; }
.hover-label { position: absolute; left: 12px; right: 12px; top: 6px; width: fit-content; max-width: calc(100% - 24px);
  background: #fff; color: #27336B; border: 1px solid #8E98CF; border-radius: 14px;
  padding: 9px 14px; font-size: 13px; line-height: 1.6; pointer-events: none; }
.arrival { grid-column: 1; grid-row: 2; align-self: center; padding: 18px 0 6px; min-width: 0; }
.summary-caption { font-size: 13px; color: #4A5270; margin-bottom: 5px; }
.arrival-title { font: 29px/1.3 'Jua', var(--st-heading-font), sans-serif; min-height: 38px; color: #27336B; }
.typed .district-name { color: #C24C38; }
.cursor { color: #FF7A66; margin-left: 2px; }
.hero[data-phase="ready"] .cursor { visibility: hidden; }
.sentence { color: #1B2340; font-size: 18px; line-height: 1.65; margin-top: 5px; word-break: keep-all; }
.verdicts { display: grid; gap: 7px; margin-top: 16px; }
.verdict { appearance: none; border: 1px solid #C8CDE3; border-radius: 13px; background: #FFFFFFB8;
  display: flex; text-align: left; align-items: center; gap: 9px; padding: 8px 12px; min-width: 0; min-height: 68px;
  cursor: pointer; color: #1B2340; font-family: inherit; }
.verdict > svg { flex: 0 0 30px; width: 30px; height: 36px; }
.verdict-copy { min-width: 0; flex: 1; }
.topic-label { display: block; color: #4A5270; font-size: 13px; line-height: 1.4; }
.level { display: block; font-size: 18px; line-height: 1.6; overflow-wrap: anywhere; }
.signals { flex: 0 0 auto; display: inline-flex; gap: 7px; align-items: center; }
.signal-dot { width: 14px; height: 14px; border-radius: 50%; background: #DDE1F0; }
.signals[data-state="sufficient"] .signal-green { background: #16803C; box-shadow: 0 0 0 3px #DCFCE7; }
.signals[data-state="normal"] .signal-yellow { background: #EAB308; box-shadow: 0 0 0 3px #FEF9C3; }
.signals[data-state="caution"] .signal-red { background: #DC2626; box-shadow: 0 0 0 3px #FEE2E2; }
.verdict[aria-pressed="true"] { border-color: #27336B; background: #fff; }
.verdict:hover { background: #fff; border-color: #8E98CF; }
.verdict:focus-visible { outline: 3px solid #27336B; outline-offset: 2px; }
.guide { color: #4A5270; font-size: 13px; line-height: 1.6; margin-top: 10px; }
.hero[data-phase="ready"] .halo { animation: breathe 4.5s ease-in-out infinite; transform-box: fill-box; transform-origin: center; }
.sr-only { position: absolute; width: 1px; height: 1px; overflow: hidden; clip-path: inset(50%); white-space: nowrap; }
[hidden] { display: none !important; }
@keyframes breathe { 0%, 100% { opacity: .1; transform: scale(.85); } 50% { opacity: .25; transform: scale(1.13); } }
@media (max-width: 1100px) and (min-width: 901px) {
  .hero { column-gap: 16px; grid-template-columns: minmax(310px, .8fr) minmax(0, 1.2fr); }
  h1 { font-size: 40px; }
  .verdict { gap: 6px; padding: 8px; }
  .verdict > svg { width: 24px; flex-basis: 24px; }
  .signals { font-size: 18px; }
}
@media (max-width: 900px) {
  .hero { min-height: 0; height: auto; grid-template-columns: minmax(0, 1fr); grid-template-rows: auto auto auto; gap: 20px; }
  .intro { grid-area: 1 / 1; padding: 0; }
  h1 { font-size: 40px; margin: 12px 0 10px; }
  .arrival { grid-area: 2 / 1; padding: 0; }
  .map-scene { grid-area: 3 / 1; }
  .seoul { height: auto; aspect-ratio: 740 / 620; flex: none; }
  .legend { gap: 5px 12px; margin-top: 10px; }
}
@media (max-width: 480px) {
  .eyebrow { gap: 9px; font-size: 12px; }
  .brand { font-size: 22px; }
  h1 { font-size: 36px; }
  .arrival-title { font-size: 27px; }
  .verdict { gap: 7px; padding: 8px; }
  .verdict > svg { width: 25px; flex-basis: 25px; }
  .signals { font-size: 19px; }
  figcaption { font-size: 12px; padding: 6px 0 0; }
  .hover-label { left: 0; right: 0; top: 0; font-size: 12px; }
}
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { animation: none !important; transition: none !important; }
  .cursor { visibility: hidden; }
}
"""

JS = """
const instances = new WeakMap();
// 메뉴 이동으로 오프닝이 반복되지 않도록 재생 기록을 document별로 보관한다.
const playedInDocument = new WeakMap();
const NS = 'http://www.w3.org/2000/svg';
const clamp = x => Math.max(0, Math.min(1, x));
const ease = x => 1 - Math.pow(1 - clamp(x), 3);

export default function(component) {
  const { parentElement, data, key, setTriggerValue } = component;
  const root = parentElement.querySelector('.hero');
  if (!root || !data) return;
  const select = selector => root.querySelector(selector);
  let s = instances.get(parentElement);
  const fresh = !s;
  if (fresh) {
    s = { root, paths: [], raf: 0, lastId: null, point: null, shapeKey: '',
      media: matchMedia('(prefers-reduced-motion: reduce)'), disposed: false };
    instances.set(parentElement, s);
    s.onMotion = () => { if (s.media.matches) settle(); };
    s.media.addEventListener('change', s.onMotion);
  }
  // 기존 애니메이션을 이어 가면서 최신 이벤트 콜백을 사용한다.
  s.emit = setTriggerValue;
  s.data = data;
  s.rows = new Map((data.district_data || []).map(d => [d.id, d]));
  const shapes = data.boundaries || [];
  const shapeKey = JSON.stringify(shapes);
  const shapesChanged = shapeKey !== s.shapeKey;
  if (shapesChanged) {
    select('.districts').replaceChildren();
    select('.district-labels').replaceChildren();
    select('.label-lines').replaceChildren();
    s.paths = shapes.map(d => {
      const path = document.createElementNS(NS, 'path');
      path.setAttribute('d', d.path);
      path.setAttribute('pathLength', '1');
      path.setAttribute('class', 'district');
      path.setAttribute('role', 'button');
      path.setAttribute('tabindex', '0');
      path.setAttribute('fill-rule', 'evenodd');
      path.dataset.regionId = String(d.id);
      const title = document.createElementNS(NS, 'title');
      path.appendChild(title);
      const label = document.createElementNS(NS, 'text');
      label.setAttribute('class', 'district-name');
      label.textContent = d.name;
      label.dataset.regionId = String(d.id);
      const line = document.createElementNS(NS, 'line');
      line.setAttribute('class', 'label-line');
      select('.label-lines').appendChild(line);
      select('.district-labels').appendChild(label);
      path.onclick = label.onclick = () => {
        if (d.id !== s.data.selected.id) s.emit('district', d.id);
      };
      path.onkeydown = e => {
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); path.onclick(); }
      };
      path.onmouseenter = path.onfocus = label.onmouseenter = () => showTooltip(d.id);
      path.onmouseleave = path.onblur = label.onmouseleave = () => {
        s.hoverId = null;
        select('.hover-label').hidden = true;
      };
      select('.districts').appendChild(path);
      return { node: path, label, line, title, ...d };
    });
    s.shapeKey = shapeKey;
  }
  const selected = data.selected;
  const changed = !fresh && s.lastId !== selected.id;
  const destination = shapes.find(d => d.id === selected.id);
  const oldPoint = s.point ? { ...s.point } : null;
  s.target = destination || null;
  s.lastId = selected.id;
  root.dataset.districtId = String(selected.id ?? '');
  root.dataset.topic = data.topic;
  s.paths.forEach(d => {
    const active = d.id === selected.id;
    const item = verdictFor(d.id);
    d.node.setAttribute('fill', item.color);
    d.node.setAttribute('aria-pressed', String(active));
    d.node.setAttribute('aria-label', `${d.name}: ${item.display_level}. ${item.value}. ${item.rank}. 선택`);
    d.title.textContent = `${d.name} · ${item.display_level} · ${item.value} · ${item.rank}`;
    if (active) select('.districts').appendChild(d.node);
  });
  select('.source').textContent = data.boundary_source;
  select('.sentence').textContent = selected.sentence;
  select('.map-empty').toggleAttribute('hidden', shapes.length > 0);
  select('.travel').style.visibility = destination ? 'visible' : 'hidden';
  select('.map-guide').textContent = shapes.length ? '궁금한 구를 눌러 주세요' : '위에서 동네를 선택해 주세요';
  select('.seoul').setAttribute('aria-label', `서울 구 지도. 지금 선택한 동네는 ${selected.name}. 구를 누르면 선택해요.`);
  root.querySelectorAll('.verdict').forEach(button => {
    const topic = button.dataset.topic;
    const item = selected.verdicts.find(v => v.topic === topic);
    button.querySelector('.level').textContent = item.display_level;
    setCarFace(button, {sufficient:'happy',normal:'smile',caution:'crying'}[item.signal_state] || 'smile');
    button.querySelector('.signals').dataset.state = item.signal_state;
    button.querySelector('.level').style.color = {sufficient:'#16803C', normal:'#A16207', caution:'#DC2626'}[item.signal_state] || '#1B2340';
    button.setAttribute('aria-pressed', String(data.topic === topic));
    button.setAttribute('aria-label', `${item.label}: ${item.display_level}. ${item.value}. ${item.rank}. 이 기준으로 지도 보기`);
    button.title = `${item.value} · ${item.rank}`;
    button.onclick = () => { if (s.data.topic !== topic) s.emit('topic', topic); };
  });
  setCarFace(select('.travel .car'), selected.mobility_mood || 'smile');
  s.title = selected.name === '자료 없음' ? '동네 자료 없음' : `${selected.name}는요`;
  const legendKey = JSON.stringify(data.legend);
  if (legendKey !== s.legendKey) {
    select('.legend').replaceChildren();
    (data.legend || []).forEach(item => {
      const entry = document.createElement('span');
      entry.className = 'legend-item';
      const swatch = document.createElement('span');
      swatch.className = 'swatch';
      swatch.style.background = item.color;
      swatch.setAttribute('aria-hidden', 'true');
      const label = document.createElement('span');
      label.textContent = item.level;
      entry.append(swatch, label);
      select('.legend').appendChild(entry);
    });
    s.legendKey = legendKey;
  }
  if (s.hoverId != null) showTooltip(s.hoverId);

  function verdictFor(id) {
    return s.rows.get(id)?.verdicts.find(v => v.topic === s.data.topic)
      || { level: '자료 없음', value: '자료 없음', rank: '순위 자료 없음', color: '#E4E7E6' };
  }
  function showTooltip(id) {
    const item = verdictFor(id);
    s.hoverId = id;
    const name = s.paths.find(d => d.id === id)?.name || '';
    select('.hover-label').textContent = `${name} · ${item.level} · ${item.value} · ${item.rank}`;
    select('.hover-label').hidden = false;
  }
  function arrangeLabels() {
    // 좁은 화면에서 구 이름이 겹치지 않도록 위치를 조정한다.
    
    const rect = select('.seoul').getBoundingClientRect();
    const scale = Math.min(rect.width / 740, rect.height / 620) || 1;
    const font = Math.max(16, (matchMedia('(max-width:700px)').matches ? 12 : 13) / scale);
    select('.map-empty').setAttribute('font-size', font);
    const occupied = [];
    [...s.paths].sort((a, b) => a.y - b.y || a.x - b.x).forEach(d => {
      d.label.setAttribute('font-size', font);
      const width = d.label.getComputedTextLength() || d.name.length * font;
      const height = font * 1.2;
      let placed = null;
      for (let radius = 0; radius <= font * 6 && !placed; radius += font * .65) {
        for (let angle = 0; angle < 8 && !placed; angle++) {
          const x = Math.max(width / 2 + 5, Math.min(735 - width / 2, d.x + Math.cos(angle * Math.PI / 4) * radius));
          const y = Math.max(height / 2 + 5, Math.min(615 - height / 2, d.y + Math.sin(angle * Math.PI / 4) * radius));
          const box = { x, y, w: width + 5 / scale, h: height + 2 / scale };
          if (!occupied.some(b => Math.abs(x - b.x) < (box.w + b.w) / 2 && Math.abs(y - b.y) < (box.h + b.h) / 2)) placed = box;
        }
      }
      placed ||= { x: d.x, y: d.y, w: width, h: height };
      occupied.push(placed);
      d.label.setAttribute('x', placed.x);
      d.label.setAttribute('y', placed.y);
      const moved = Math.hypot(placed.x - d.x, placed.y - d.y) > font * .6;
      d.line.setAttribute('x1', d.x); d.line.setAttribute('y1', d.y);
      d.line.setAttribute('x2', placed.x); d.line.setAttribute('y2', placed.y);
      d.line.style.display = moved ? '' : 'none';
      const dark = !moved && verdictFor(d.id).color === '#27336B';
      d.label.setAttribute('fill', dark ? '#FFFFFF' : '#1B2340');
      d.label.setAttribute('stroke', dark ? '#27336B' : '#FFFFFF');
    });
  }
  s.arrangeLabels = arrangeLabels;
  arrangeLabels();

  function carAt(point) {
    if (!point) return;
    s.point = { x: point.x, y: point.y };
    select('.car').setAttribute('transform', `translate(${point.x} ${point.y})`);
  }
  function route(from, to) {
    if (!to) return;
    const start = from || { x: 40, y: 550 };
    const d = `M${start.x},${start.y} C${start.x + 80},${start.y + 16} ${to.x - 75},${to.y + 60} ${to.x},${to.y}`;
    ['.road-edge', '.road', '.road-center'].forEach(sel => select(sel).setAttribute('d', d));
    select('.destination').setAttribute('transform', `translate(${to.x} ${to.y})`);
    s.roadLength = select('.road').getTotalLength();
  }
  function move(progress) {
    if (s.target && s.roadLength) carAt(select('.road').getPointAtLength(s.roadLength * ease(progress)));
  }
  function announce() {
    select('.announcement').textContent = `${s.title}. ${s.data.selected.sentence}`;
  }
  function settle() {
    cancelAnimationFrame(s.raf);
    s.raf = 0;
    root.dataset.phase = 'ready';
    s.paths.forEach(d => {
      d.node.style.strokeDasharray = 'none';
      d.node.style.strokeDashoffset = '0';
      d.node.style.fillOpacity = '1';
    });
    root.querySelectorAll('.verdict').forEach(el => { el.style.opacity = '1'; el.style.transform = 'none'; });
    ['.road-edge', '.road', '.road-center', '.destination', '.car', '.sentence', '.district-labels', '.label-lines'].forEach(sel => {
      select(sel).style.opacity = '1';
    });
    renderTitle(s.title);
    carAt(s.target);
    announce();
  }
  function renderTitle(text) {
    const name = selected.name === '자료 없음' ? '' : selected.name;
    const strong = document.createElement('span');
    strong.className = 'district-name';
    strong.textContent = text.slice(0, name.length);
    select('.typed').replaceChildren(strong, document.createTextNode(text.slice(name.length)));
  }
  function opening() {
    root.dataset.phase = 'opening';
    root.dataset.openingCount = '1';
    const began = performance.now();
    function frame(now) {
      if (s.disposed) return;
      const ms = now - began;
      s.paths.forEach(d => {
        const wave = d.x / 740;
        d.node.style.strokeDasharray = '1';
        d.node.style.strokeDashoffset = String(1 - ease((ms - wave * 160) / 650));
        d.node.style.fillOpacity = String(clamp((ms - 540 - wave * 300) / 320));
      });
      const travel = clamp((ms - 900) / 170);
      ['.road-edge', '.road', '.road-center', '.destination', '.car'].forEach(sel => { select(sel).style.opacity = String(travel); });
      move((ms - 970) / 650);
      select('.district-labels').style.opacity = select('.label-lines').style.opacity = String(clamp((ms - 960) / 220));
      const letters = Math.floor(clamp((ms - 1660) / 400) * s.title.length);
      renderTitle(s.title.slice(0, letters));
      select('.sentence').style.opacity = String(clamp((ms - 1950) / 160));
      root.querySelectorAll('.verdict').forEach((el, i) => {
        const p = clamp((ms - 1920 - i * 120) / 220);
        el.style.opacity = String(p);
        el.style.transform = `translateY(${(1 - ease(p)) * 12}px) scale(${.96 + .04 * ease(p)})`;
      });
      if (ms < 2400) s.raf = requestAnimationFrame(frame);
      else settle();
    }
    frame(began);
  }
  function respond(from) {
    settle();
    route(from, s.target);
    if (s.media.matches || !s.target) return;
    root.dataset.phase = 'responding';
    const began = performance.now();
    function frame(now) {
      if (s.disposed) return;
      const p = clamp((now - began) / 420);
      move(p);
      if (p < 1) s.raf = requestAnimationFrame(frame);
      else settle();
    }
    frame(began);
  }

  if (fresh) {
    s.observer = new ResizeObserver(() => s.arrangeLabels());
    s.observer.observe(select('.seoul'));
    parentElement.ownerDocument.fonts?.ready.then(() => { if (!s.disposed) s.arrangeLabels(); });
    const doc = parentElement.ownerDocument;
    let played = playedInDocument.get(doc);
    if (!played) { played = new Set(); playedInDocument.set(doc, played); }
    const alreadyPlayed = played.has(key);
    played.add(key);
    route(null, destination);
    if (alreadyPlayed || s.media.matches || !destination) settle();
    else opening();
  } else if (changed || shapesChanged) {
    respond(oldPoint);
  } else {
    announce();
  }
  
  return () => {
    s.disposed = true;
    cancelAnimationFrame(s.raf);
    s.media.removeEventListener('change', s.onMotion);
    s.observer?.disconnect();
    root.querySelectorAll('.district, .district-name, .verdict').forEach(el => {
      el.onclick = el.onkeydown = el.onmouseenter = el.onmouseleave = el.onfocus = el.onblur = null;
    });
    instances.delete(parentElement);
  };
}
"""

JS = FACE_JS + JS

_HERO = st.components.v2.component("h3_seoul_drawing", html=HTML, css=CSS, js=JS)


@st.cache_data(ttl=600, max_entries=4, show_spinner=False)
def _project_boundaries(frame: pd.DataFrame) -> list[dict]:
    if frame.empty:
        return []
    districts = []
    all_points = []
    for _, row in frame.iterrows():
        geometry = json.loads(row.geometry_json)
        polygons = ([geometry["coordinates"]] if geometry["type"] == "Polygon"
                    else geometry["coordinates"] if geometry["type"] == "MultiPolygon" else [])
        rings = [ring for polygon in polygons for ring in polygon]
        if rings:
            districts.append((row, rings))
            all_points.extend(point for ring in rings for point in ring)
    if not all_points:
        return []
    longitude_factor = math.cos(math.radians(37.56))
    xs = [float(p[0]) * longitude_factor for p in all_points]
    ys = [float(p[1]) for p in all_points]
    left, right, bottom, top = min(xs), max(xs), min(ys), max(ys)
    scale = min(708 / (right - left), 584 / (top - bottom))
    offset_x = (740 - (right - left) * scale) / 2
    offset_y = (620 - (top - bottom) * scale) / 2

    def project(lon: float, lat: float) -> tuple[float, float]:
        return (round(offset_x + (float(lon) * longitude_factor - left) * scale, 2),
                round(offset_y + (top - float(lat)) * scale, 2))

    result = []
    for row, rings in districts:
        path = " ".join("M" + " L".join(f"{x},{y}" for x, y in
                        (project(p[0], p[1]) for p in ring)) + " Z" for ring in rings)
        x, y = project(row.centroid_longitude, row.centroid_latitude)
        result.append({"id": int(row.region_id), "name": str(row.district_name),
                       "path": path, "x": x, "y": y})
    return result


def _select_district() -> None:
    # 구 선택 위젯이 만들어지기 전에 콜백에서 district_id를 갱신한다.
    candidate = st.session_state.get(KEY, {}).get("district")
    regions = load_frame(q.get_district_ranking)
    if (isinstance(candidate, int) and not isinstance(candidate, bool)
            and not regions.empty and candidate in regions.region_id.values
            and candidate != st.session_state.get("district_id")):
        st.session_state.district_id = candidate
        remember_region()


def _select_topic() -> None:
    topic = st.session_state.get(KEY, {}).get("topic")
    if isinstance(topic, str) and topic in TOPICS:
        set_topic(topic)


def _verdicts(row: pd.Series) -> list[dict]:
    result = []
    for topic, spec in TOPICS.items():
        level = word(row.get(f"{topic}_level"))
        index = spec.levels.index(level) if level in spec.levels else None
        result.append({"topic": topic, "label": TOPIC_LABELS[topic], "level": level,
                       "display_level": TRANSIT_LEVELS.get(level, level) if topic == "need" else level,
                       "value": topic_value(row, topic), "rank": rank_text(row, topic),
                       "signal_index": index,
                       "signal_state": {
                           "ownership": {"많은 편": "caution", "보통": "normal", "적은 편": "sufficient"},
                           "parking": {"좋음": "sufficient", "보통": "normal", "빠듯함": "caution"},
                           "need": {"차가 필요한 편": "caution", "있으면 편함": "normal", "대중교통으로 충분": "sufficient"},
                       }[topic].get(level, "unknown"),
                       "color": COLORS[index if index is not None else 3]})
    return result


def render_hero(district_name: str) -> None:
    ranking = load_frame(q.get_district_ranking)
    boundaries = load_frame(q.get_region_boundaries)
    region_id = st.session_state.get("district_id")
    row = district_row(ranking, int(region_id)) if region_id is not None else pd.Series(dtype=object)
    count = number(row.get("vehicle_count"), suffix="대")
    years = sorted({int(y) for y in boundaries.get("boundary_year", pd.Series(dtype=float)).dropna()})
    source = "통계청 " + ", ".join(map(str, years)) + "년 경계" if years else "경계 자료 없음"
    topic = st.session_state.get("topic", "ownership")
    districts: list[dict] = [{"id": int(item.region_id), "name": str(item.district_name),
                             "verdicts": _verdicts(item)}
                             for _, item in ranking.iterrows() if {"region_id", "district_name"} <= set(item.index)]
    legend = [{"level": TRANSIT_LEVELS.get(level, level) if topic == "need" else level, "color": color}
              for level, color in zip(TOPICS[topic].levels, COLORS)]
    if ranking.empty or any(item["verdicts"][list(TOPICS).index(topic)]["signal_index"] is None
                            for item in districts):
        legend.append({"level": "자료 없음", "color": COLORS[3]})
    _HERO(
        key=KEY,
        data={
            "boundaries": _project_boundaries(boundaries),
            "district_data": districts,
            "boundary_source": source,
            "topic": topic,
            "legend": legend,
            "selected": {
                "id": int(region_id) if region_id is not None else None,
                "name": word(row.get("district_name"), district_name),
                "count": f"등록 {count} · {date_text(row.get('stat_month'), month=True)}",
                "sentence": neighborhood_sentence(row),
                "mobility_mood": mobility_mood(row),
                "verdicts": _verdicts(row),
            },
        },
        on_district_change=_select_district,
        on_topic_change=_select_topic,
        width="stretch", height="content",
    )
