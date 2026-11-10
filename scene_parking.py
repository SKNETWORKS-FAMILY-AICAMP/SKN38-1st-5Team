from pathlib import Path
from xml.etree import ElementTree as ET

import streamlit as st

from car_expression import add_expression, FACE_JS


def _car_symbols() -> str:
    svg = ET.fromstring(
        (Path(__file__).parent / "assets" / "three_cars.svg").read_text(encoding="utf-8")
    )
    for node in svg.iter():
        node.tag = node.tag.rsplit("}", 1)[-1]
    symbols = []
    for index, car in enumerate(svg[0]):
        car.attrib.pop("transform", None)
        add_expression(car, index)
        symbols.append(
            f'<symbol id="h4-car-{index}" viewBox="0 0 112 122">'
            '<g stroke="#1B2340" stroke-width="3.5" stroke-linecap="round" '
            f'stroke-linejoin="round">{ET.tostring(car, encoding="unicode")}</g></symbol>'
        )
    return "".join(symbols)


HTML = """
<section class="parking-hero" aria-labelledby="h4-title" data-opening="settled">
  <div class="hero-copy">
    <div class="eyebrow"><span class="brand">차차차</span><span>서울 25구의 자동차 생활</span></div>
    <h1 id="h4-title">우리 동네,<br>내 차 자리 있나요<span class="coral">?</span></h1>
    <p class="intro">차량 보유 · 주차 여건 · 대중교통 지표를 함께 살펴요.</p>
    <div class="district-line" aria-live="polite" aria-atomic="true">
      <span class="district-chip"><svg viewBox="0 0 20 20" aria-hidden="true"><path d="M10 18s6-6 6-11A6 6 0 0 0 4 7c0 5 6 11 6 11Z"/><circle cx="10" cy="7" r="2"/></svg><span data-text="district">자료 없음</span></span>
      <span class="verdict">주차 여건 <strong data-text="parking-level">자료 없음</strong></span>
    </div>
    <p class="measure" data-text="parking-value">자료 없음</p>
    <div class="little-road" aria-hidden="true"><i></i><i></i><i></i><span>지도에서 주차장과 충전소의 위치·요금을 확인해요</span></div>
  </div>
  <figure class="parking-scene">
    <svg class="lot" viewBox="0 0 660 340" role="group" aria-labelledby="h4-lot-title h4-lot-description">
      <title id="h4-lot-title">차차차 동네 주차장</title>
      <desc id="h4-lot-description">주차 판정을 빈자리로 표현한 그림이에요. 실제 빈자리 수는 아니에요. 차를 누르면 인사해요.</desc>
      <defs>__CAR_SYMBOLS__
        <pattern id="h4-curb" width="26" height="12" patternUnits="userSpaceOnUse"><rect width="26" height="12" fill="#8E98CF"/><path d="M0 0h13v12H0z" fill="#EEF0FA"/></pattern>
        <pattern id="h4-dots" width="12" height="12" patternUnits="userSpaceOnUse"><circle cx="2" cy="2" r=".8" fill="#EEF0FA" opacity=".1"/></pattern>
      </defs>
      <g aria-hidden="true">
        <rect x="17" y="18" width="626" height="302" rx="32" fill="#C8CDE3"/>
        <rect x="17" y="10" width="626" height="302" rx="32" fill="#27336B"/>
        <rect x="17" y="10" width="626" height="302" rx="32" fill="url(#h4-dots)"/>
        <rect x="52" y="23" width="550" height="7" rx="3" fill="url(#h4-curb)"/>
        <rect x="52" y="292" width="550" height="7" rx="3" fill="url(#h4-curb)"/>
        <rect x="17" y="143" width="626" height="55" fill="#34417C"/>
        <path d="M30 171h78m68 0h75m64 0h75m64 0h75m67 0h24" stroke="#EEF0FA" stroke-width="2" stroke-dasharray="13 12" opacity=".38"/>
        <path d="m111 163 10 8-10 8m279-16 10 8-10 8" fill="none" stroke="#EEF0FA" stroke-width="3" opacity=".55"/>
        <g class="bays"></g>
        <g class="support-cars"></g>
        <g transform="translate(32 74)"><rect width="34" height="38" rx="9" fill="#EEF0FA"/><text x="17" y="27" text-anchor="middle" font-size="27" font-weight="800" fill="#27336B">P</text></g>
        <g transform="translate(585 215)"><rect width="36" height="57" rx="10" fill="#8E98CF"/><path d="m20 7-11 22h12l-7 19 16-27H17Z" fill="#EEF0FA"/></g>
        <g class="parking-labels" fill="#EEF0FA" font-size="13" font-weight="700" text-anchor="middle"><text x="126" y="46">차량 보유</text><text x="292" y="46">주차</text><text x="458" y="46">차 필요</text></g>
        <rect x="25" y="202" width="18" height="66" rx="9" fill="#8E98CF"/>
        <path d="M34 214v42m-6-29 6 5 6-5m-12 12 6 5 6-5" fill="none" stroke="#EEF0FA" stroke-width="2"/>
        <rect x="618" y="60" width="15" height="55" rx="7" fill="#FF7A66"/>
        <path d="M625 70v34" stroke="#27336B" stroke-width="2"/>
        <g class="beacon"><circle cx="614" cy="171" r="8" fill="#FF7A66" opacity=".18"/><circle cx="614" cy="171" r="3" fill="#FF7A66"/></g>
      </g>
      <g class="hero-cars"></g>
      <g class="missing-cover" aria-hidden="true"><rect x="166" y="142" width="330" height="58" rx="18" fill="#EEF0FA"/><text x="331" y="178" text-anchor="middle" fill="#27336B" font-size="18" font-weight="700">주차 자료가 아직 없어요</text></g>
      <g class="scene-sign" aria-hidden="true"><rect x="207" y="301" width="245" height="32" rx="16" fill="#FFFFFF" stroke="#C8CDE3"/><circle cx="225" cy="317" r="4" fill="#FF7A66"/><text x="337" y="322" text-anchor="middle" fill="#27336B" font-size="13" font-weight="700" data-text="scene-label">동네 주차 여건을 살펴봐요</text></g>
    </svg>
    <figcaption><span class="tap-hint">차를 누르면 경적이 울려요</span><span>빈자리는 판정을 표현한 그림이에요.</span></figcaption>
  </figure>
  <span class="sr-only" data-text="announcement" role="status" aria-live="polite"></span>
</section>
""".replace("__CAR_SYMBOLS__", _car_symbols())


CSS = """
.parking-hero.map-layout {display:block;padding:20px;min-height:330px;height:100%;border:1px solid #DDE1F0;border-radius:18px;background:#F7F8FC;}
.parking-hero.map-layout h1 {font-size:clamp(34px,2.7vw,40px);line-height:1.25;}
.parking-hero.map-layout .intro {font-size:18px;}
.parking-hero.map-layout .district-line {margin-top:12px;}
.parking-hero.map-layout .little-road {margin-top:14px;}
.parking-hero.map-layout .parking-scene {display:none;}
.parking-hero.map-layout .measure,.parking-hero.map-layout .little-road {font-size:16px;line-height:1.6;}
@media(max-width:600px){.parking-hero.map-layout {padding:20px;min-height:0;}.parking-hero.map-layout h1 {font-size:34px;}}

:host { display: block; width: 100%; height:100%; }
* { box-sizing: border-box; }
.parking-hero {
  --navy: #27336B; --ink: #1B2340; --mid: #8E98CF; --pale: #EEF0FA; --coral: #FF7A66;
  display: grid; grid-template-columns: minmax(0, .9fr) minmax(0, 1.2fr);
  gap: 22px; align-items: center; height: auto; min-height: 350px; width: 100%; min-width: 0;
  color: var(--ink); font-family: 'Noto Sans KR', var(--st-font), sans-serif;
}
.hero-copy { min-width: 0; padding: 0 0 0 3px; }
.eyebrow { display: flex; align-items: center; gap: 12px; color: var(--navy); font-size: 13px; font-weight: 600; }
.brand { font-family: Jua, var(--st-heading-font), sans-serif; font-size: 23px; font-weight: 400; }
h1 { padding: 0; margin: 15px 0 11px; color: var(--ink); font-family: Jua, var(--st-heading-font), sans-serif; font-size: clamp(34px, 3.8vw, 52px); line-height: 1.16; font-weight: 400; letter-spacing: -.025em; word-break: keep-all; }
.coral { color: #DC5946; }
.intro { margin: 0; font-size: 18px; font-weight: 500; line-height: 1.65; word-break: keep-all; }
.district-line { display: flex; align-items: center; gap: 11px; margin-top: 20px; flex-wrap: wrap; }
.district-chip { display: inline-flex; align-items: center; gap: 5px; background: #FFF2D6; color: #8A4B08; padding: 8px 13px; border-radius: 999px; font-size: 24px; font-weight: 700; line-height: 1.3; }
.district-chip svg { width: 16px; height: 16px; fill: none; stroke: currentColor; stroke-width: 1.5; }
.verdict { font-size: 18px; color: #4A5270; }
.verdict strong { margin-left: 5px; font-size: clamp(24px, 2.4vw, 30px); line-height: 1.4; font-weight: 800; color: var(--navy); }
.verdict strong[data-state="caution"] { color: #DC2626; }
.verdict strong[data-state="sufficient"] { color: #15803D; }
.verdict strong[data-state="normal"] { color: #CA8A04; }
.measure { margin: 8px 0 0; color: #4A5270; font-size: 13px; font-variant-numeric: tabular-nums; }
.little-road { display: flex; align-items: center; gap: 5px; margin-top: 22px; font-size: 13px; color: #4A5270; }
.little-road i { width: 11px; height: 3px; background: var(--mid); border-radius: 5px; }
.little-road span { margin-left: 7px; }
.parking-scene { min-width: 0; width: 100%; margin: 0; }
.lot { width: 100%; height: auto; display: block; overflow: hidden; }
.lot text { font-family: 'Noto Sans KR', var(--st-font), sans-serif; }
figcaption { display: flex; flex-wrap: wrap; justify-content: space-between; gap: 8px; margin: 5px 20px 0; font-size: 13px; line-height: 1.5; color: #4A5270; }
.tap-hint { font-weight: 700; color: var(--navy); }
.hero-car { cursor: pointer; outline: none; transform-origin: 0 0; }
.car-body { transform-box: fill-box; transform-origin: center; }
.car-hit { fill: transparent; }
.car-focus { fill: none; stroke: #FF7A66; stroke-width: 3; opacity: 0; }
.hero-car:hover .car-focus, .hero-car:focus-visible .car-focus { opacity: 1; }
.hero-car:focus-visible .car-focus { stroke: #FFFFFF; stroke-width: 4; stroke-dasharray: 4 4; }
.topic-marker { opacity: 0; }
.hero-car[data-active="true"] .topic-marker { opacity: 1; }
.horn { opacity: 0; pointer-events: none; }
.support-car { pointer-events: none; transform-origin: 0 0; }
.bay { transition: opacity 250ms ease; }
.bay-p { fill: #EEF0FA; opacity: .18; font-size: 24px; font-weight: 700; }
.bay[data-occupied="true"] .bay-p { opacity: 0; }
.bay[data-occupied="false"] .bay-floor { fill: #EEF0FA; opacity: .11; }
.missing-cover { display: none; }
[data-missing="true"] .missing-cover { display: block; }
[data-missing="true"] .bay { opacity: .25; }
[data-opening="settled"] .beacon { animation: h4-beacon 3.6s ease-in-out infinite; }
.sr-only { position: absolute; width: 1px; height: 1px; overflow: hidden; clip-path: inset(50%); white-space: nowrap; }
@keyframes h4-beacon { 0%, 100% { opacity: .45; } 50% { opacity: .9; } }
@media (max-width: 1100px) and (min-width: 741px) {
  .parking-hero { gap: 8px; grid-template-columns: minmax(0, .95fr) minmax(0, 1.1fr); }
  h1 { font-size: 38px; }
  .intro { font-size: 18px; }
  figcaption { margin-inline: 9px; font-size: 13px; }
}
@media (max-width: 740px) {
  .parking-hero { grid-template-columns: minmax(0, 1fr); grid-template-rows: auto auto; height: auto; min-height: 0; gap: 9px; align-items: start; }
  .hero-copy { padding: 0; }
  .eyebrow { font-size: 13px; gap: 9px; line-height: 1.3; }
  .brand { font-size: 19px; }
  h1 { font-size: 30px; line-height: 1.1; margin: 9px 0 7px; }
  .intro { font-size: 18px; line-height: 1.5; }
  .district-line { margin-top: 10px; gap: 9px; }
  .district-chip { font-size: 20px; padding: 6px 10px; }
  .verdict { font-size: 18px; }
  .measure { font-size: 13px; margin-top: 5px; }
  .little-road { display: none; }
  .parking-scene { align-self: center; max-width: 350px; justify-self: center; }
  figcaption { margin: 3px 7px 0; font-size: 13px; gap: 4px; }
}
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { animation: none !important; transition: none !important; }
}
"""


JS = """
const instances = new WeakMap();
// 메뉴 이동으로 오프닝이 반복되지 않도록 document에 재생 기록을 둔다.

const visitLedger = Symbol.for('chachacha.h4.parking.visits');
const NS = 'http://www.w3.org/2000/svg';
const topics = ['ownership', 'parking', 'need'];
const labels = ['차량 보유', '주차', '차 필요'];
const heroSlots = [0, 2, 4];
const otherSlots = [7, 10, 1, 9, 5, 6, 3, 11, 8];
__FACE_JS__
const occupiedByLevel = { '좋음': 2, '보통': 5, '빠듯함': 8 };

function svgElement(tag, attributes, parent) {
  const node = parent.ownerDocument.createElementNS(NS, tag);
  Object.entries(attributes).forEach(([key, value]) => node.setAttribute(key, String(value)));
  parent.append(node);
  return node;
}
function position(slot) {
  return { x: 126 + (slot % 6) * 83, y: slot < 6 ? 99 : 245, angle: slot < 6 ? 0 : 180 };
}
function transform(p) { return `translate(${p.x}px, ${p.y}px) rotate(${p.angle}deg)`; }
function basePosition(node, p) { node.setAttribute('transform', `translate(${p.x} ${p.y}) rotate(${p.angle})`); }
function text(root, name, value) {
  const node = root.querySelector(`[data-text="${name}"]`);
  if (node && node.textContent !== value) node.textContent = value;
}
function animate(state, node, frames, options) {
  if (state.motion.matches) return null;
  const animation = node.animate(frames, { easing: 'cubic-bezier(.22,.7,.3,1)', ...options });
  state.animations.add(animation);
  const release = () => state.animations.delete(animation);
  animation.onfinish = release;
  animation.oncancel = release;
  return animation;
}
function settle(state) {
  state.animations.forEach(animation => animation.cancel());
  state.animations.clear();
  state.moves.clear();
  state.honks.clear();
  clearTimeout(state.openingTimer);
  state.root.dataset.opening = 'settled';
}
function makeScene(state) {
  const root = state.root;
  const bays = root.querySelector('.bays');
  for (let slot = 0; slot < 12; slot++) {
    const p = position(slot);
    const bay = svgElement('g', {class: 'bay', 'data-slot': slot}, bays);
    svgElement('rect', {class: 'bay-floor', x: p.x - 36, y: p.y - 43, width: 72, height: 86, rx: 6, fill: 'transparent'}, bay);
    const y = slot < 6 ? p.y - 43 : p.y + 43;
    const dy = slot < 6 ? 86 : -86;
    svgElement('path', {d: `M${p.x - 36} ${y + dy}v${-dy}h72v${dy}`, fill: 'none', stroke: '#EEF0FA', 'stroke-width': 2, opacity: .42}, bay);
    const letter = svgElement('text', {class: 'bay-p', x: p.x, y: p.y + 8, 'text-anchor': 'middle'}, bay);
    letter.textContent = 'P';
    state.bays.push(bay);
  }
  otherSlots.forEach((slot, index) => {
    const p = position(slot);
    const car = svgElement('g', {class: 'support-car', opacity: 0}, root.querySelector('.support-cars'));
    basePosition(car, p);
    svgElement('ellipse', {cx: 0, cy: 5, rx: 29, ry: 34, fill: '#1B2340', opacity: .25}, car);
    svgElement('use', {href: `#h4-car-${index % 3}`, x: -30, y: -35, width: 60, height: 70, opacity: .82}, car);
    state.support.set(slot, {node: car, visible: false});
  });
  heroSlots.forEach((slot, index) => {
    const car = svgElement('g', {class: 'hero-car', role: 'button', tabindex: 0, 'data-topic': topics[index]}, root.querySelector('.hero-cars'));
    basePosition(car, position(slot));
    svgElement('rect', {class: 'car-hit', x: -48, y: -48, width: 96, height: 96, rx: 15}, car);
    svgElement('rect', {class: 'car-focus', x: -37, y: -43, width: 74, height: 86, rx: 13}, car);
    const body = svgElement('g', {class: 'car-body'}, car);
    svgElement('ellipse', {cx: 0, cy: 12, rx: 32, ry: 32, fill: '#1B2340', opacity: .3}, body);
    svgElement('use', {href: `#h4-car-${index}`, x: -35, y: -40, width: 70, height: 81}, body);
    svgElement('circle', {class: 'topic-marker', cx: 0, cy: 47, r: 3, fill: '#FF7A66'}, car);
    const horn = svgElement('g', {class: 'horn'}, car);
    svgElement('path', {d: 'M18-52h35q9 0 9 9v11q0 9-9 9H34l-11 8 2-8h-7q-9 0-9-9v-11q0-9 9-9', fill: '#FF7A66', stroke: '#1B2340', 'stroke-width': 2}, horn);
    const message = svgElement('text', {x: 36, y: -31, fill: '#1B2340', 'font-size': 17, 'font-weight': 800, 'text-anchor': 'middle'}, horn);
    message.textContent = '빵!';
    state.heroes.push(car);
    const honk = () => {
      text(root, 'announcement', `${labels[index]} 자동차가 인사해요. 빵!`);
      if (state.motion.matches) return;
      (state.honks.get(car) || []).forEach(animation => animation?.cancel());
      state.honks.set(car, [
        animate(state, body, [{transform: 'translateY(0) scale(1)'}, {transform: 'translateY(-9px) scale(1.08)', offset: .3}, {transform: 'translateY(3px) scale(.96)', offset: .65}, {transform: 'translateY(0) scale(1)'}], {duration: 460}),
        animate(state, horn, [{opacity: 0, transform: 'translateY(5px)'}, {opacity: 1, transform: 'translateY(0)', offset: .2}, {opacity: 1, offset: .65}, {opacity: 0, transform: 'translateY(-7px)'}], {duration: 650}),
      ]);
    };
    car.onclick = honk;
    car.onkeydown = event => {
      if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); honk(); }
    };
  });
}
function parkingTargets(data) {
  const count = occupiedByLevel[data.parkingLevel] ?? 0;
  const offset = Math.abs(Number(data.districtId) || 0) % otherSlots.length;
  return new Set(Array.from({length: count}, (_, i) => otherSlots[(i + offset) % otherSlots.length]));
}
function updateOccupancy(state, data, respond) {
  const occupied = parkingTargets(data);
  const missing = !(data.parkingLevel in occupiedByLevel);
  state.root.dataset.missing = String(missing);
  state.bays.forEach((bay, slot) => {
    bay.dataset.occupied = String(heroSlots.includes(slot) || occupied.has(slot));
  });
  state.support.forEach((car, slot) => {
    const visible = occupied.has(slot);
    if (visible === car.visible) return;
    state.moves.get(car.node)?.cancel();
    state.moves.delete(car.node);
    car.visible = visible;
    car.node.setAttribute('opacity', visible ? '1' : '0');
    car.node.dataset.occupied = String(visible);
    if (!respond || state.motion.matches) return;
    const p = position(slot);
    const lane = {x: p.x + 24, y: 171, angle: -55};
    const edge = {x: visible ? 680 : -70, y: 171, angle: -90};
    const frames = visible
      ? [{transform: transform(edge), opacity: 0}, {transform: transform(lane), opacity: .75, offset: .5}, {transform: transform(p), opacity: 1}]
      : [{transform: transform(p), opacity: 1}, {transform: transform(lane), opacity: .75, offset: .5}, {transform: transform(edge), opacity: 0}];
    state.moves.set(car.node, animate(state, car.node, frames, {duration: 600, delay: (slot % 3) * 35, fill: 'backwards'}));
  });
}
function opening(state) {
  state.root.dataset.opening = 'running';
  state.heroes.forEach((car, index) => {
    const p = position(heroSlots[index]);
    animate(state, car, [
      {transform: transform({x: -85, y: 171, angle: -90}), opacity: 0},
      {transform: transform({x: 50, y: 171, angle: -90}), opacity: 1, offset: .13},
      {transform: transform({x: p.x + 69, y: 171, angle: -90}), opacity: 1, offset: .48},
      {transform: transform({x: p.x + 21, y: 145, angle: -32}), opacity: 1, offset: .7},
      {transform: transform({x: p.x, y: p.y - 3, angle: 0}), opacity: 1, offset: .91},
      {transform: transform(p), opacity: 1},
    ], {duration: 1340, delay: index * 350, fill: 'backwards'});
  });
  animate(state, state.root.querySelector('.hero-copy'), [{opacity: .5, transform: 'translateY(12px)'}, {opacity: 1, transform: 'translateY(0)'}], {duration: 650});
  state.openingTimer = setTimeout(() => { state.root.dataset.opening = 'settled'; }, 2150);
}
function reactToDistrict(state) {
  if (state.motion.matches) return;
  state.heroes.forEach((car, index) => {
    const p = position(heroSlots[index]);
    animate(state, car, [
      {transform: transform(p)},
      {transform: transform({x: p.x + 7, y: p.y + 23, angle: -8}), offset: .4},
      {transform: transform(p)},
    ], {duration: 520, delay: index * 55});
  });
  animate(state, state.root.querySelector('.scene-sign'), [{opacity: .35}, {opacity: 1}], {duration: 400});
}

export default function(component) {
  const {parentElement, data} = component;
  const root = parentElement.querySelector('.parking-hero');
  if (!root || !data) return;
  root.classList.toggle("map-layout", Boolean(data.hideScene));
  let state = instances.get(parentElement);
  const firstMount = !state;
  if (firstMount) {
    state = {root, heroes: [], bays: [], support: new Map(), animations: new Set(), moves: new Map(), honks: new Map(), motion: matchMedia('(prefers-reduced-motion: reduce)'), district: null, level: null, openingTimer: null};
    instances.set(parentElement, state);
    makeScene(state);
    state.motionListener = () => { if (state.motion.matches) settle(state); };
    state.motion.addEventListener('change', state.motionListener);
  }
  const district = String(data.districtId ?? 'missing');
  const changed = !firstMount && (district !== state.district || data.parkingLevel !== state.level);
  if (changed) settle(state);
  text(root, 'district', data.districtName);
  const statuses = {'좋음': ['여유로움', 'sufficient'], '보통': ['보통', 'normal'], '빠듯함': ['빠듯함', 'caution']};
  const [statusLabel, statusState] = statuses[data.parkingLevel] || [data.parkingLevel, 'unknown'];
  text(root, 'parking-level', statusLabel);
  root.querySelector('[data-text="parking-level"]').dataset.state = statusState;
  text(root, 'parking-value', data.parkingValue);
  const scenes = {'좋음': '넉넉한 자리, 가벼운 마음', '보통': '우리 동네 주차 여건은 보통', '빠듯함': '주차 자리, 미리 확인하세요'};
  text(root, 'scene-label', scenes[data.parkingLevel] || '주차 자료를 기다리고 있어요');
  root.dataset.districtId = district;
  root.dataset.parkingLevel = data.parkingLevel;
  const signColors = {sufficient:['#DCFCE7','#15803D'],normal:['#FEF9C3','#A16207'],caution:['#FEE2E2','#DC2626']};
  const [signFill, signInk] = signColors[statusState] || ['#EEF0FA','#4A5270'];
  const sign = root.querySelector('.scene-sign');
  sign.querySelector('rect').setAttribute('fill',signFill);
  sign.querySelector('rect').setAttribute('stroke',signInk);
  sign.querySelector('circle').setAttribute('fill',signInk);
  sign.querySelector('text').setAttribute('fill',signInk);
  state.heroes.forEach((car, index) => {
    const level = data.levels[topics[index]] || '자료 없음';
    car.setAttribute('aria-label', `${labels[index]}: ${level}. 누르면 자동차가 인사해요.`);
    car.dataset.active = String(topics[index] === data.activeTopic);
    const mood = level === '자료 없음' ? 'smile' : ({'좋음':'happy', '빠듯함':'crying', '보통':'smile', '많은 편':'crying', '적은 편':'happy', '차가 필요한 편':'crying', '있으면 편함':'smile', '대중교통으로 충분':'happy'}[level] || 'smile');
    setCarFace(root.querySelector(`#h4-car-${index}`), mood);
  });
  updateOccupancy(state, data, changed);
  if (firstMount) {
    const doc = root.ownerDocument;
    const visits = doc[visitLedger] || (doc[visitLedger] = new Set());
    const visited = visits.has(data.instanceKey);
    visits.add(data.instanceKey);
    if (!visited && !state.motion.matches) opening(state);
  } else if (changed) {
    reactToDistrict(state);
  }
  state.district = district;
  state.level = data.parkingLevel;
  return () => {
    settle(state);
    state.motion.removeEventListener('change', state.motionListener);
    state.heroes.forEach(car => { car.onclick = null; car.onkeydown = null; });
    instances.delete(parentElement);
  };
}
"""


JS = JS.replace("__FACE_JS__", FACE_JS)

_PARKING_HERO = st.components.v2.component(
    "chachacha_h4_parking_hero", html=HTML, css=CSS, js=JS, isolate_styles=True
)


def parking_hero(
    *,
    district_id: int | None,
    district_name: str,
    parking_level: str,
    parking_value: str,
    levels: dict[str, str],
    active_topic: str,
    hide_scene: bool = False,
    stretch: bool = False,
) -> None:
    _PARKING_HERO(
        key="hero_h4_parking",
        data={
            "instanceKey": "hero_h4_parking",
            "districtId": int(district_id) if district_id is not None else None,
            "districtName": district_name,
            "parkingLevel": parking_level,
            "parkingValue": parking_value,
            "levels": levels,
            "activeTopic": active_topic,
            "hideScene": hide_scene,
        },
        width="stretch",
        height="stretch" if stretch else "content",
    )
