from copy import deepcopy
from math import isfinite
from pathlib import Path
from typing import Any
import xml.etree.ElementTree as ET

import pandas as pd
import streamlit as st

from ui import district_row, word


KEY = "transit_drive_hero"
_ASSET = ET.parse(Path(__file__).parent / "assets" / "three_cars.svg").getroot()
_MOODS = {
    "많은 편": "happy", "보통": "calm", "적은 편": "curious",
    "좋음": "happy", "빠듯함": "worried",
    "차가 필요한 편": "eager", "있으면 편함": "curious",
    "대중교통으로 충분": "relaxed", "자료 없음": "unknown",
}


def _car_svg(index: int) -> str:
    car = deepcopy(_ASSET[0][index])
    for node in car.iter():
        node.tag = node.tag.rsplit("}", 1)[-1]
    car.set("transform", "translate(0 12)" if index == 2 else "translate(0 0)")
    for node in list(car):
        if node.tag == "circle" or (
            node.tag == "path" and node.get("d", "").startswith(("M45", "m36"))
        ):
            car.remove(node)
    paths = car.findall("path")
    if index == 0:
        paths[0].set("d", "M12 21Q12 7 26 7h58q14 0 14 14v64q0 12-12 12H24Q12 97 12 85Z")
        paths[1].set("d", "M23 27h64v22H23Z")
        ET.SubElement(car, "rect", {"x": "29", "y": "13", "width": "52", "height": "7",
                                  "rx": "3", "fill": "#FF7A66", "stroke": "none"})
        ET.SubElement(car, "path", {"d": "M36 85h38", "stroke": "#8E98CF", "stroke-width": "2"})
    elif index == 1:
        paths[0].set("d", "M15 27Q15 12 31 12h48q16 0 16 15v59q0 17-17 17H32Q15 103 15 86Z")
        paths[0].set("fill", "#8E98CF")
        paths[1].set("d", "M26 29h58v23H26Z")
        ET.SubElement(car, "path", {"d": "M43 12l12-9 12 9M40 3h30", "fill": "none"})
        ET.SubElement(car, "path", {"d": "M30 114l-8 9m58-9 8 9M24 120h62", "stroke-width": "2.5"})
    eye_y, mouth_y = (31, 69) if index == 2 else (39, 76)
    eyes = ET.SubElement(car, "g", {"class": "eyes", "fill": "none"})
    for side, x in (("left", 40), ("right", 70)):
        ET.SubElement(eyes, "path", {
            "class": f"eye-{side}", "d": f"M{x} {eye_y}v1",
            "stroke-width": "4.4",
        })
    ET.SubElement(car, "path", {
        "class": "mouth", "d": f"M45 {mouth_y}q10 9 20 0",
        "fill": "none", "stroke": "#FFFFFF" if index == 0 else "#1B2340",
        "stroke-width": "3",
    })
    svg = ET.Element("svg", {
        "viewBox": "0 0 112 126", "aria-hidden": "true", "focusable": "false",
        "data-eye-y": str(eye_y), "data-mouth-y": str(mouth_y),
        "fill": "none", "stroke": "#1B2340", "stroke-width": "3.5",
        "stroke-linecap": "round", "stroke-linejoin": "round",
    })
    ET.SubElement(svg, "ellipse", {
        "cx": "55", "cy": "120", "rx": "42", "ry": "4",
        "fill": "#27336B", "opacity": ".12", "stroke": "none",
    })
    svg.append(car)
    return ET.tostring(svg, encoding="unicode")


_VEHICLES = (
    ("bus", "버스", "주차 걱정 없이", "창밖을 보며 동네를 지나가요."),
    ("subway", "지하철", "이동 시간도 내 시간", "책을 읽거나 음악을 들으며 가요."),
    ("car", "자동차", "필요한 날 함께", "이동 경로와 짐에 맞춰 골라요."),
)
_CARS = "".join(
    f"""
    <button class="car" type="button" data-mode="{mode}" aria-label="{name}. {speech}. {description}">
      <span class="arrival">
        <span class="speech">{speech}</span>
        <span class="car-sprite">
          <span class="brake" aria-hidden="true">도착!</span>
          <span class="dust" aria-hidden="true"></span>
          <span class="car-bob">{_car_svg(index)}</span>
        </span>
        <span class="car-title">{name}</span>
        <span class="vehicle-note">{description}</span>
      </span>
    </button>
    """
    for index, (mode, name, speech, description) in enumerate(_VEHICLES)
)

HTML = """
<section class="hero" aria-labelledby="transit-title" data-phase="ready" data-motion="off">
  <div class="copy">
    <p class="brand"><span class="brand-mark" aria-hidden="true">차차차</span><span>서울 자동차 생활 안내서</span></p>
    <h1 id="transit-title"><span>차 없이도</span><span><em>잘 달려요.</em></span></h1>
    <p class="intro">차량 보유, 주차, 차 필요성을 살피는 차차차.<br>우리 동네 버스와 지하철의 하루를 살펴볼 수 있어요.</p>
    <p class="verdict">우리 동네 차 필요성 <strong class="need-level">자료 없음</strong></p>
  </div>
  <div class="scene">
    <div class="destination"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 21s7-7 7-13a7 7 0 0 0-14 0c0 6 7 13 7 13Z"/><circle cx="12" cy="8" r="2.5"/></svg><span><b class="district">자료 없음</b><span class="arrived">에 도착했어요</span></span></div>
    <button class="motion" type="button" aria-label="장면 움직임 멈추기"><span class="motion-icon" aria-hidden="true">Ⅱ</span><span class="motion-text">움직임 멈춤</span></button>
    <svg class="city" viewBox="0 0 620 150" preserveAspectRatio="xMidYMax meet" aria-hidden="true">
      <circle cx="516" cy="39" r="25" fill="#FF7A66" opacity=".24"/>
      <path d="M0 140h620" stroke="#8E98CF" stroke-width="2"/>
      <path d="M28 139v-43h48v43m12 0V66h48v73m14 0v-30l27-19 27 19v30m26 0V41h37v98m13 0V78h50v61m19 0V54h32v85m13 0v-36l24-20 24 20v36m20 0V65h46v74m15 0V99h60v40" fill="#DEE2F3" stroke="#BBC2E1" stroke-width="2" stroke-linejoin="round"/>
      <path d="M235 41V32h27v9M248 32V17m-9 0h18M101 83h6m12 0h6m-24 14h6m12 0h6m-24 14h6m12 0h6M292 94h8m12 0h8m-28 15h8m12 0h8m151-29h8m12 0h8m-28 15h8m12 0h8" fill="none" stroke="#A8B1D8" stroke-width="3"/>
      <path d="M10 64h30m-18-8h28M542 80h38m-21-8h29" fill="none" stroke="#BBC2E1" stroke-width="3" stroke-linecap="round"/>
    </svg>
    <svg class="road" viewBox="0 0 640 100" preserveAspectRatio="none" aria-hidden="true">
      <path d="M-20 11Q310-12 660 11V85Q310 104-20 85Z" fill="#D4D9EF"/>
      <path d="M-20 16Q310-7 660 16M-20 80Q310 99 660 80" fill="none" stroke="#8E98CF" stroke-width="2"/>
      <path d="M-20 50Q310 30 660 50" fill="none" stroke="#FFFFFF" stroke-width="4" stroke-dasharray="25 23"/>
    </svg>
    <div class="garage" role="group" aria-label="함께 도착하는 버스, 지하철, 자동차">
""" + _CARS + """
    </div>
  </div>
  <span class="sr-only" role="status" aria-live="polite" aria-atomic="true"></span>
</section>
"""

CSS = """
:host { display:block; min-width:0; }
* { box-sizing:border-box; }
.hero { --navy:#27336B; --ink:#1B2340; --muted:#4A5270; --lavender:#8E98CF;
  --pale:#EEF0FA; --coral:#FF7A66; width:100%; min-height:390px; position:relative;
  padding:24px 28px; border-radius:24px;
  display:grid; grid-template-columns:minmax(0, .92fr) minmax(0, 1.08fr); gap:24px;
  color:var(--ink); background:var(--pale); font-family:'Noto Sans KR',var(--st-font),sans-serif;
  isolation:isolate; }
.copy { align-self:center; min-width:0; padding:0 0 4px; }
p, h1 { margin:0; }
.brand { display:flex; align-items:center; gap:10px; color:var(--navy); font-size:13px;
  font-weight:600; letter-spacing:.01em; margin-bottom:17px; }
.brand-mark { font-family:'Jua',var(--st-heading-font),sans-serif; font-size:22px;
  font-weight:400; padding-right:10px; border-right:1px solid #ADB5DA; line-height:1; }
h1 { font-family:'Jua',var(--st-heading-font),sans-serif; font-size:clamp(34px,3.6vw,52px);
  line-height:1.22; letter-spacing:-.035em; font-weight:400; }
h1 > span { display:block; white-space:nowrap; transform-origin:0 100%; }
h1 em { font-style:normal; position:relative; z-index:0; }
h1 em::after { content:''; position:absolute; left:0; right:0; bottom:2px; height:12px;
  border-radius:4px; background:var(--coral); opacity:.75; z-index:-1; transform:rotate(-2deg); }
.intro { margin-top:15px; font-size:18px; line-height:1.8; word-break:keep-all; }
.verdict { margin-top:20px; color:var(--muted); font-size:13px; line-height:1.8; }
.verdict strong { color:var(--navy); display:block; font-size:26px; font-weight:800; }
.need-level[data-state="caution"] { color:#DC2626; }
.need-level[data-state="normal"] { color:#CA8A04; }
.need-level[data-state="sufficient"] { color:#15803D; }
.vehicle-note { font-size:13px; color:var(--muted); line-height:1.6; margin-top:6px;
  word-break:keep-all; max-width:160px; text-align:center; }
.scene { min-width:0; min-height:342px; position:relative; overflow:hidden; }
.destination { display:flex; align-items:center; gap:6px; position:absolute; left:13px; top:5px;
  font-size:13px; line-height:26px; z-index:2; transform-origin:left center; }
.destination svg { width:18px; height:22px; fill:var(--coral); stroke:var(--navy); stroke-width:1.7; }
.destination svg circle { fill:var(--pale); }
.destination b { color:#B45309; font-size:clamp(28px,3.5vw,40px); line-height:1.3; font-weight:800; }
.destination > span { display:flex; flex-wrap:wrap; align-items:baseline; gap:3px; }
.arrived { color:var(--muted); margin-left:3px; }
.motion { position:absolute; top:6px; right:5px; display:flex; align-items:center; gap:5px;
  background:transparent; color:var(--muted); border:0; border-radius:6px; cursor:pointer;
  padding:5px; font:inherit; font-size:13px; z-index:3; min-height:28px; }
.motion-icon { font-weight:800; font-size:13px; }
.motion:disabled { cursor:default; }
.city { position:absolute; top:31px; left:0; width:100%; height:150px; opacity:.65; }
.road { position:absolute; left:0; width:100%; height:79px; top:204px; border-radius:18px; overflow:hidden; }
.garage { position:absolute; left:0; right:0; top:55px; display:grid;
  grid-template-columns:repeat(3,minmax(0,1fr)); gap:4px; align-items:start; }
.car { display:block; width:100%; padding:0 4px 5px; min-width:0; border:0;
  color:var(--ink); cursor:pointer; background:none; border-radius:16px; font:inherit;
  -webkit-tap-highlight-color:transparent; }
.arrival { display:flex; flex-direction:column; align-items:center; width:100%; }
.speech { display:flex; align-items:center; justify-content:center; min-height:31px;
  padding:5px 9px; font-size:13px; font-weight:700; line-height:18px; background:#fff;
  color:var(--navy); border:1.5px solid #B6BDDE; border-radius:12px; white-space:normal;
  max-width:100%; text-align:center; word-break:keep-all;
  position:relative; margin-bottom:3px; transition:background 160ms,color 160ms; }
.speech::after { content:''; width:7px; height:7px; border-bottom:1.5px solid #B6BDDE;
  border-right:1.5px solid #B6BDDE; position:absolute; bottom:-5px; left:calc(50% - 4px);
  transform:rotate(45deg); background:inherit; }
.car-sprite { display:block; position:relative; width:100%; max-width:148px; height:166px;
  transform-origin:50% 85%; transition:transform 220ms cubic-bezier(.2,.8,.3,1); }
.car-bob { display:block; width:100%; height:100%; }
.car svg { display:block; width:100%; height:100%; overflow:visible; }
.car-title { display:flex; align-items:center; gap:5px; margin-top:3px; padding:2px 5px;
  font-family:'Jua',var(--st-heading-font),sans-serif; font-size:20px; line-height:1.25; font-weight:400; }
.brake { position:absolute; top:15px; right:-4px; font-family:'Jua',sans-serif; font-size:20px;
  color:var(--navy); transform:rotate(14deg); opacity:0; }
.dust { position:absolute; left:-12px; bottom:13px; width:28px; height:13px; background:#fff;
  border:1.5px solid #BCC3E1; border-radius:50%; opacity:0; }
.dust::before { content:''; position:absolute; width:14px; height:14px; left:8px; top:-8px;
  border-radius:50%; background:white; border-top:1.5px solid #BCC3E1; }
button:focus-visible { outline:3px solid var(--navy); outline-offset:-3px; }
.motion:focus-visible { outline-offset:1px; }
.hero[data-motion="on"] .car:active .car-sprite { transform:translateY(-3px) scale(.97); }
.sr-only { position:absolute; width:1px; height:1px; padding:0; margin:-1px;
  overflow:hidden; clip:rect(0,0,0,0); white-space:nowrap; border:0; }
@media (hover:hover) {
  .hero[data-motion="on"] .car:hover .car-sprite { transform:translateY(-8px) rotate(-4deg); }
  .car:hover .car-title { color:var(--navy); }
}
.hero[data-phase="settled"][data-motion="on"] .car-bob { animation:breathe 7s ease-in-out infinite; }
.hero[data-phase="settled"][data-motion="on"] .car:nth-child(2) .car-bob { animation-delay:1.1s; }
.hero[data-phase="settled"][data-motion="on"] .car:nth-child(3) .car-bob { animation-delay:2.2s; }
.hero[data-phase="settled"][data-motion="on"] .eyes { transform-box:fill-box; transform-origin:center;
  animation:blink 6.5s ease-in-out infinite; }
.hero[data-phase="settled"][data-motion="on"] .car:nth-child(2) .eyes { animation-delay:1.8s; }
.hero[data-phase="settled"][data-motion="on"] .car:nth-child(3) .eyes { animation-delay:3s; }
@keyframes breathe { 0%,42%,62%,100% { transform:translateY(0); } 51% { transform:translateY(-2px); } }
@keyframes blink { 0%,46%,49%,100% { transform:scaleY(1); } 47.5% { transform:scaleY(.1); } }
.hero[data-motion="off"] *, .hero[data-motion="off"] *::after { animation:none!important; transition:none!important; }
@media (max-width:1100px) and (min-width:701px) {
  .hero { gap:14px; grid-template-columns:minmax(0,.9fr) minmax(0,1.1fr); }
  .scene { min-height:380px; }
  h1 { font-size:clamp(27px,3.5vw,39px); }
  .brand { font-size:13px; gap:6px; }
  .intro { font-size:18px; }
  .car-sprite { height:154px; }
  .garage { top:71px; }
  .speech { font-size:13px; padding:5px 7px; }
  .car-title { font-size:17px; }
  .motion-text { display:none; }
}
@media (max-width:700px) {
  .hero { display:grid; grid-template-columns:minmax(0,1fr); grid-template-rows:auto auto;
    min-height:0; gap:14px; padding:18px 14px; border-radius:18px; }
  .scene { min-height:310px; }
  .copy { align-self:start; padding:0; }
  .brand { margin-bottom:9px; font-size:12px; gap:8px; }
  .brand-mark { font-size:18px; padding-right:8px; }
  h1 { font-size:32px; line-height:1.18; letter-spacing:-.03em; }
  h1 em::after { height:8px; bottom:1px; }
  .intro { margin-top:10px; font-size:18px; line-height:1.7; }
  .verdict { margin-top:10px; font-size:12px; }
  .verdict strong { display:inline; margin-left:5px; font-size:24px; }
  .destination { top:0; left:1px; max-width:calc(100% - 32px); font-size:12px; line-height:24px; gap:4px; }
  .destination svg { width:14px; height:17px; }
  .motion { top:0; right:0; min-height:26px; font-size:12px; gap:4px; padding:2px; }
  .motion-icon { font-size:12px; }
  .motion-text { display:none; }
  .city { top:54px; height:85px; opacity:.55; }
  .road { top:152px; height:53px; }
  .garage { top:62px; gap:2px; }
  .car { padding:0 0 3px; border-radius:10px; }
  .speech { min-height:26px; padding:3px 6px; font-size:12px; line-height:18px; margin-bottom:1px; border-radius:9px; white-space:normal; text-align:center; }
  .car-sprite { max-width:94px; height:105px; }
  .car-title { font-size:16px; margin-top:0; gap:2px; padding:1px 0; }
  .vehicle-note { font-size:12px; line-height:1.5; margin-top:3px; }
  .brake { top:10px; right:-3px; font-size:16px; }
  .dust { width:20px; height:10px; left:-4px; }
}
@media (max-width:360px) {
  h1 { font-size:29px; }
  .speech { font-size:12px; padding:3px 4px; }
  .car-title { font-size:14px; }
  .motion-text { display:none; }
}
@media (prefers-reduced-motion:reduce) {
  *, *::before, *::after { animation:none!important; transition:none!important; }
  .car:hover .car-sprite, .car:active .car-sprite { transform:none!important; }
}
"""

JS = """
const instances = new WeakMap();
const openedKeys = new Set();

function hasOpened(key) {
  // 새로고침과 메뉴 이동을 구분하려고 timeOrigin을 재생 기록에 저장한다.
  let opened = openedKeys.has(key);
  try {
    const token = String(performance.timeOrigin);
    const storageKey = 'chachacha:transit:opening:' + key;
    opened ||= sessionStorage.getItem(storageKey) === token;
    sessionStorage.setItem(storageKey, token);
  } catch (_) { /* Per-instance memory also works when storage is disabled. */ }
  openedKeys.add(key);
  return opened;
}

function animate(state, node, frames, options) {
  if (state.reduced.matches || state.paused || !node?.animate) return;
  const animation = node.animate(frames, {duration:450, easing:'ease-out', ...options});
  state.animations.add(animation);
  animation.onfinish = () => state.animations.delete(animation);
}

function drawFace(button, mood) {
  const svg = button.querySelector('svg');
  const eyeY = Number(svg.dataset.eyeY), mouthY = Number(svg.dataset.mouthY);
  const eyes = [button.querySelector('.eye-left'), button.querySelector('.eye-right')];
  eyes.forEach((eye, i) => {
    const x = i ? 70 : 40;
    let d = 'M' + x + ' ' + eyeY + 'v1';
    if (['happy','eager'].includes(mood)) d = 'M' + (x-4) + ' ' + (eyeY+1) + 'q4-7 8 0';
    if (mood === 'relaxed') d = 'M' + (x-4) + ' ' + (eyeY-1) + 'q4 6 8 0';
    if (mood === 'worried') d = 'M' + (x-4) + ' ' + (eyeY-2) + 'l8 ' + (i ? -3 : 3);
    if (mood === 'curious' && i) d = 'M' + (x-4) + ' ' + (eyeY-2) + 'h8';
    if (mood === 'unknown') d = 'M' + (x-3) + ' ' + eyeY + 'h6';
    eye.setAttribute('d', d);
    eye.setAttribute('stroke-width', ['calm','curious'].includes(mood) ? '3.5' : '2.8');
  });
  const mouths = {
    happy:'M44 ' + (mouthY-1) + 'q11 13 22 0',
    eager:'M46 ' + (mouthY-1) + 'q9 17 18 0Z',
    calm:'M47 ' + (mouthY+2) + 'q8 4 16 0',
    curious:'M49 ' + (mouthY+2) + 'q6-4 12 0',
    worried:'M46 ' + (mouthY+5) + 'q9-9 18 0',
    relaxed:'M46 ' + mouthY + 'q9 8 18 0',
    unknown:'M49 ' + (mouthY+2) + 'h12',
  };
  button.querySelector('.mouth').setAttribute('d', mouths[mood] || mouths.unknown);
  button.dataset.mood = mood;
}

function settle(state) {
  clearTimeout(state.finishTimer);
  for (const animation of state.animations) animation.cancel();
  state.animations.clear();
  state.root.dataset.phase = 'settled';
}

function motionControl(state) {
  const reduced = state.reduced.matches;
  state.root.dataset.motion = reduced || state.paused ? 'off' : 'on';
  const button = state.root.querySelector('.motion');
  button.disabled = reduced;
  button.querySelector('.motion-icon').textContent = reduced || state.paused ? '▷' : 'Ⅱ';
  button.querySelector('.motion-text').textContent = reduced ? '움직임 줄임' : state.paused ? '움직임 켜기' : '움직임 멈춤';
  button.setAttribute('aria-label', reduced ? '기기 설정에 따라 움직임을 줄였어요' : state.paused ? '장면 움직임 켜기' : '장면 움직임 멈추기');
  if (reduced || state.paused) settle(state);
}

function opening(state) {
  const root = state.root;
  root.dataset.phase = 'opening';
  root.dataset.openingCount = '1';
  root.querySelectorAll('h1 > span').forEach((line, i) => animate(state, line, [
    {transform:'translateY(25px) rotate(2deg)', opacity:0},
    {transform:'translateY(-6px) rotate(-1deg)', opacity:1, offset:.67},
    {transform:'translateY(0) rotate(0)', opacity:1},
  ], {duration:650, delay:200 + i*110, fill:'backwards'}));
  root.querySelectorAll('.car').forEach((car, i) => {
    const delay = i*150;
    animate(state, car.querySelector('.arrival'), [
      {transform:'translateX(-620px) rotate(-7deg)', opacity:0},
      {transform:'translateX(-390px) rotate(-7deg)', opacity:1, offset:.18},
      {transform:'translateX(14px) rotate(5deg)', opacity:1, offset:.56},
      {transform:'translate(-4px,-15px) rotate(-4deg)', offset:.7},
      {transform:'translate(2px,0) rotate(2deg) scale(1.04,.94)', offset:.82},
      {transform:'translate(0,-5px) rotate(-1deg)', offset:.92},
      {transform:'translate(0,0) rotate(0)', opacity:1},
    ], {duration:1300, delay, fill:'backwards'});
    animate(state, car.querySelector('.brake'), [
      {opacity:0, transform:'rotate(14deg) scale(.7)'},
      {opacity:1, transform:'rotate(14deg) scale(1.12)', offset:.2},
      {opacity:1, transform:'rotate(14deg) scale(1)', offset:.65},
      {opacity:0, transform:'translateY(-8px) rotate(14deg)'},
    ], {duration:620, delay:delay+680});
    animate(state, car.querySelector('.dust'), [
      {opacity:0, transform:'translateX(8px) scale(.5)'},
      {opacity:.85, transform:'translateX(-3px) scale(1)', offset:.3},
      {opacity:0, transform:'translateX(-24px) scale(1.5)'},
    ], {duration:550, delay:delay+650});
  });
  state.finishTimer = setTimeout(() => settle(state), 2150);
}

export default function(component) {
  const {parentElement, data, key} = component;
  const root = parentElement.querySelector('.hero');
  if (!root || !data) return;
  let state = instances.get(parentElement);
  const firstMount = !state;
  if (!state) {
    state = {root, regionId:null, signature:null, paused:false,
      finishTimer:0, animations:new Set(), reduced:matchMedia('(prefers-reduced-motion: reduce)')};
    instances.set(parentElement, state);
    state.onMotionChange = () => motionControl(state);
    state.reduced.addEventListener('change', state.onMotionChange);
    state.dispose = () => {
      settle(state);
      state.reduced.removeEventListener('change', state.onMotionChange);
      root.querySelectorAll('button').forEach(button => {button.onclick = null;});
      instances.delete(parentElement);
    };
  }
  const changedDistrict = !firstMount && state.regionId !== data.district_id;
  const signature = JSON.stringify(data);
  const changedData = state.signature !== signature;
  state.regionId = data.district_id;
  root.dataset.districtId = String(data.district_id ?? '');
  root.querySelector('.district').textContent = data.district_name;
  root.querySelector('.arrived').textContent = data.district_id === null ? '' : '에 도착했어요';
  if (changedDistrict) settle(state);
  root.querySelector('.need-level').textContent = data.need_level;
  root.querySelector('.need-level').dataset.state = {'차가 필요한 편':'caution','있으면 편함':'normal','대중교통으로 충분':'sufficient'}[data.need_level] || 'unknown';
  root.querySelectorAll('.car').forEach(car => {
    drawFace(car, car.dataset.mode === 'car' ? data.need_mood : 'happy');
    car.onclick = () => {
      animate(state, car.querySelector('.car-sprite'), [
        {transform:'translateY(0)'}, {transform:'translateY(-10px) rotate(-3deg)', offset:.4},
        {transform:'translateY(0)'},
      ], {duration:380});
    };
    if (changedDistrict) animate(state, car.querySelector('.car-sprite'), [
      {transform:'translateX(-10px)'},
      {transform:'translate(2px,-3px)', offset:.65},
      {transform:'translate(0,0)'},
    ], {duration:420});
  });
  if (changedData) {
    root.querySelector('[role="status"]').textContent = data.district_name + '. 차 필요성, ' + data.need_level + '.';
  }
  if (changedDistrict) animate(state, root.querySelector('.destination'), [
    {transform:'translateY(3px)', opacity:.6}, {transform:'translateY(0)', opacity:1},
  ], {duration:350});
  state.signature = signature;
  root.querySelector('.motion').onclick = () => {state.paused = !state.paused; motionControl(state);};
  motionControl(state);
  if (firstMount) {
    const opened = hasOpened(key);
    if (!opened && !state.reduced.matches) opening(state);
    else {root.dataset.openingCount = '0'; settle(state);}
  }
  return state.dispose;
}
"""

_COMPONENT = st.components.v2.component("chachacha_transit_drive", html=HTML, css=CSS, js=JS,
                                      isolate_styles=True)


def hero_props(ranking: pd.DataFrame, district_id: int | None,
               district_name: str) -> dict[str, Any]:
    row = district_row(ranking, district_id) if district_id is not None else pd.Series(dtype=object)
    raw = row.get("need_value")
    valid = raw is not None and pd.notna(raw) and isfinite(float(raw))
    level = word(row.get("need_level")) if valid else "자료 없음"
    return {"district_id": district_id, "district_name": district_name,
            "need_level": level, "need_mood": _MOODS.get(level, "unknown")}


def render_hero(ranking: pd.DataFrame, district_id: int, district_name: str) -> None:
    _COMPONENT(
        key=KEY,
        data=hero_props(ranking, district_id, district_name),
        width="stretch", height="content",
    )
