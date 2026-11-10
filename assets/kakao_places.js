const instances = new WeakMap();
const esc = value => String(value ?? '정보 미제공').replace(/[&<>"']/g,
  char => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[char]));
const color = place => ({free:'#15803D',paid:'#C65D0A'}[place.fee_status] || '#64748B');
const feeLabel = place => ({free:'주차 무료',paid:'주차 유료'}[place.fee_status] || '주차 요금 미확인');
const symbol = place => place.kind === '충전소' ? '⚡' : 'P';
const position = (state, place) => new state.maps.LatLng(place.latitude, place.longitude);

function listen(state, target, event, callback) {
  state.maps.event.addListener(target, event, callback);
  state.listeners.push([target, event, callback]);
}

function clearSegments(state) {
  state.segments.forEach(segment => segment.setMap(null));
  state.segments = [];
}

function closePlace(state) {
  state.popup?.close();
  state.tooltip?.setMap(null);
  clearSegments(state);
}

function closeRoadview(state) {
  state.roadviewVersion++;
  clearTimeout(state.roadviewTimer);
  state.roadviewPanel.hidden = true;
  state.roadviewCanvas.hidden = true;
}

function showRoadview(state, place) {
  closeRoadview(state);
  const version = state.roadviewVersion;
  state.roadviewPanel.hidden = false;
  state.roadviewStatus.textContent = '주변 로드뷰를 불러오는 중이에요.';
  const fail = () => {
    if (state.disposed || version !== state.roadviewVersion) return;
    state.roadviewVersion++;
    clearTimeout(state.roadviewTimer);
    state.roadviewCanvas.hidden = true;
    state.roadviewStatus.textContent = '이 위치의 로드뷰를 표시할 수 없어요. 카카오맵 로드뷰 링크에서 확인해 주세요.';
  };
  state.roadviewTimer = setTimeout(fail, 8000);
  try {
    const point = position(state, place);
    const client = new state.maps.RoadviewClient();
    client.getNearestPanoId(point, 50, panoId => {
      if (state.disposed || version !== state.roadviewVersion) return;
      if (!panoId) { fail(); return; }
      clearTimeout(state.roadviewTimer);
      try {
        state.roadviewCanvas.hidden = false;
        state.roadview = state.roadview || new state.maps.Roadview(state.roadviewCanvas);
        state.roadview.relayout();
        state.roadview.setPanoId(panoId, point);
        state.roadviewStatus.textContent = `${place.name} 주변 로드뷰 · 카카오 제공`;
      } catch { fail(); }
    });
  } catch { fail(); }
}

function selectWalkingPlace(state, place) {
  if (state.selection?.id === place?.id) return;
  state.selection = place ? {id: place.id, revision: ++state.selectionRevision, requested: false} : null;
  state.walkRequested = state.walkPending = false;
  if (state.data.walk_enabled || state.data.external_detail) state.setStateValue('selected_place', state.selection);
}

function updateWalking(state) {
  if (!state.walkSection) return;
  const enabled = state.data.walk_enabled && state.data.station && state.selection;
  state.walkSection.hidden = !enabled;
  if (!enabled) {
    state.walkStatus.textContent = '';
    state.walkRequested = state.walkPending = false;
    return;
  }
  const walking = state.data.walking;
  if (state.walkRequested && walking?.place_id === state.selection.id && walking.revision === state.selection.revision) {
    state.walkPending = false;
    state.walkStatus.textContent = walking.result ?
      `도보 약 ${Math.ceil(walking.result.duration_s / 60).toLocaleString()}분 · ${walking.result.distance_m.toLocaleString()}m · 카카오 제공` :
      '도보 경로를 찾지 못했어요. 직선거리와 카카오맵 길찾기 링크를 참고해 주세요.';
  } else {
    state.walkStatus.textContent = state.walkPending ? '도보 경로를 찾고 있어요.' : '';
  }
  state.walkButton.disabled = state.walkPending;
}

function details(state, place, popup = false) {
  const node = document.createElement('div');
  node.className = popup ? 'kp-popup' : 'kp-description';
  const distance = place.distance_m === null ? '' :
    `<span class="kp-tag">${esc(state.data.station.name)}에서 직선 ${Math.round(place.distance_m).toLocaleString()}m${place.near ? ' · 반경 안' : ''}</span>`;
  const coords = `${place.latitude},${place.longitude}`;
  node.innerHTML = `<span class="kp-tag">${esc(place.kind)} · ${esc(place.operation)}</span>${distance}<br>
    <strong>${esc(place.name)}</strong><br><span class="kp-fee kp-fee-${['free','paid'].includes(place.fee_status) ? place.fee_status : 'unknown'}">${feeLabel(place)}</span><br>${esc(place.address)}<br>
    <b>이용시간</b> ${esc(place.hours)}<br><b>요금</b> ${esc(place.price)}<br>
    <b>이용 안내</b> ${esc(place.note)}<br><b>규모</b> ${esc(place.capacity)} · ${esc(place.operator)}<br>
    자료 갱신: ${esc(place.updated)} · 방문 전 현장 확인
    <div class="kp-links"><a target="_blank" rel="noopener noreferrer" href="https://map.kakao.com/link/to/${encodeURIComponent(place.name)},${coords}">카카오맵 길찾기 ↗</a>
    <a target="_blank" rel="noopener noreferrer" href="https://map.kakao.com/link/roadview/${coords}">로드뷰 ↗</a></div>`;
  const roadview = document.createElement('button');
  roadview.type = 'button';
  roadview.className = 'kp-button';
  roadview.textContent = '주변 로드뷰 보기';
  roadview.onclick = () => showRoadview(state, place);
  node.appendChild(roadview);
  if (!popup) {
    state.walkSection = document.createElement('div');
    state.walkSection.className = 'kp-walk';
    state.walkButton = document.createElement('button');
    state.walkButton.type = 'button';
    state.walkButton.className = 'kp-button';
    state.walkButton.textContent = '도보 시간 보기';
    state.walkStatus = document.createElement('p');
    state.walkStatus.setAttribute('role', 'status');
    state.walkButton.onclick = () => {
      if (!state.data.walk_enabled || !state.data.station || state.walkPending || state.selection?.id !== place.id) return;
      state.selection = {id: place.id, revision: ++state.selectionRevision, requested: true};
      state.walkRequested = state.walkPending = true;
      updateWalking(state);
      state.setStateValue('selected_place', state.selection);
      state.setTriggerValue('walk_request', place.id);
    };
    state.walkSection.appendChild(state.walkButton);
    state.walkSection.appendChild(state.walkStatus);
    node.appendChild(state.walkSection);
  }
  if (popup) {
    const close = document.createElement('button');
    close.type = 'button';
    close.className = 'kp-button';
    close.textContent = '팝업 닫기';
    close.onclick = () => closePlace(state);
    node.appendChild(close);
  }
  return node;
}

function selectPlace(state, place) {
  closePlace(state);
  closeRoadview(state);
  selectWalkingPlace(state, place);
  state.detail.replaceChildren(details(state, place));
  updateWalking(state);
  state.choice.value = place.id;
  const point = position(state, place);
  state.popup.setContent(details(state, place, true));
  state.popup.setPosition(point);
  state.popup.open(state.map);
  for (const part of place.positions || []) {
    if (part.latitude === place.latitude && part.longitude === place.longitude) continue;
    state.segments.push(new state.maps.Circle({map: state.map, center: position(state, part),
      radius: 4, strokeWeight: 1, strokeColor: color(place), fillColor: color(place), fillOpacity: .7}));
  }
}

function showTooltip(state, place) {
  const node = document.createElement('div');
  node.className = 'kp-tooltip';
  node.innerHTML = `<b>${esc(place.name)}</b><br>${esc(place.price)}<br>${esc(place.hours)}` +
    (place.distance_m === null ? '' : `<br>직선 ${Math.round(place.distance_m).toLocaleString()}m${place.near ? ' · 반경 안' : ''}`);
  state.tooltip.setContent(node);
  state.tooltip.setPosition(position(state, place));
  state.tooltip.setMap(state.map);
}

function updateMotion(state) {
  state.motionButton.hidden = !state.data.station;
  state.motionButton.textContent = state.motion ? '깜빡임 끄기' : '깜빡임 켜기';
  state.motionButton.setAttribute('aria-pressed', String(state.motion));
  state.pins.forEach(pin => pin.classList.toggle('kp-pulse', state.motion));
}

function clearLayers(state) {
  closePlace(state);
  closeRoadview(state);
  state.clusterer?.clear();
  state.layers.forEach(layer => layer.setMap(null));
  state.listeners.forEach(([target, event, callback]) => state.maps.event.removeListener(target, event, callback));
  state.layers = [];
  state.listeners = [];
  state.pins = [];
}

function reconcile(state) {
  if (state.disposed || !state.map) return;
  const data = state.data;
  if (state.lastAnimate !== data.animate) {
    state.motion = data.animate;
    state.lastAnimate = data.animate;
  }
  const signature = JSON.stringify([data.places, data.station, data.radius, data.district, data.boundary]);
  if (signature === state.signature) { updateMotion(state); updateWalking(state); return; }
  selectWalkingPlace(state, null);
  updateWalking(state);
  clearLayers(state);
  state.signature = signature;
  state.choice.replaceChildren(new Option('장소를 선택해 주세요', ''));
  state.detail.textContent = '핀이나 장소 목록을 선택하면 이용시간과 요금을 확인할 수 있어요. 좌표가 없는 시설은 아래 표에서 확인해 주세요.';
  const bounds = new state.maps.LatLngBounds();
  for (const polygon of data.boundary?.polygons || []) {
    const path = polygon.map(ring => ring.map(([lon, lat]) => new state.maps.LatLng(lat, lon)));
    path.flat().forEach(point => bounds.extend(point));
    state.layers.push(new state.maps.Polygon({map: state.map, path, strokeWeight: 2,
      strokeColor: '#27336B', strokeOpacity: .8, fillColor: '#8E98CF', fillOpacity: .04}));
  }
  const markers = [];
  for (const place of data.places) {
    const point = position(state, place);
    bounds.extend(point);
    state.choice.appendChild(new Option(`${place.name} · ${place.operation}${place.near ? ' · 반경 안' : ''}`, place.id));
    if (place.near) {
      const pin = document.createElement('button');
      pin.type = 'button';
      pin.className = 'kp-pin';
      pin.style.setProperty('--pin', color(place));
      pin.textContent = symbol(place);
      pin.setAttribute('aria-label', `${place.name} · ${place.operation} · ${feeLabel(place)} · 반경 안`);
      pin.onclick = () => selectPlace(state, place);
      pin.onmouseenter = pin.onfocus = () => showTooltip(state, place);
      pin.onmouseleave = pin.onblur = () => state.tooltip.setMap(null);
      state.pins.push(pin);
      state.layers.push(new state.maps.CustomOverlay({map: state.map, position: point,
        content: pin, xAnchor: .5, yAnchor: .5, zIndex: 5, clickable: true}));
    } else {
      const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="36" height="36"><circle cx="18" cy="18" r="16" fill="${color(place)}" stroke="white" stroke-width="2"/><text x="18" y="24" text-anchor="middle" font-family="sans-serif" font-weight="bold" font-size="20" fill="white">${symbol(place)}</text></svg>`;
      const marker = new state.maps.Marker({position: point, title: `${place.name} · ${place.operation} · ${feeLabel(place)}`,
        image: new state.maps.MarkerImage(`data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`,
          new state.maps.Size(36, 36), {offset: new state.maps.Point(18, 18)})});
      listen(state, marker, 'click', () => selectPlace(state, place));
      listen(state, marker, 'mouseover', () => showTooltip(state, place));
      listen(state, marker, 'mouseout', () => state.tooltip.setMap(null));
      markers.push(marker);
      state.layers.push(marker);
    }
  }
  state.clusterer.addMarkers(markers);
  if (data.station) {
    const center = position(state, data.station);
    const circle = new state.maps.Circle({map: state.map, center, radius: data.radius,
      strokeColor: '#FF7A66', strokeWeight: 2, strokeStyle: 'dash', fillColor: '#FF7A66', fillOpacity: .07});
    const label = document.createElement('span');
    label.className = 'kp-station';
    label.textContent = `역 · ${data.station.name}`;
    state.layers.push(circle, new state.maps.CustomOverlay({map: state.map, position: center,
      content: label, xAnchor: .5, yAnchor: .5, zIndex: 6}));
    state.map.setBounds(circle.getBounds(), 40, 40, 40, 40);
  } else if (data.boundary?.polygons?.length) {
    state.map.setBounds(bounds, 40, 40, 40, 40);
  } else if (data.places.length === 1) {
    state.map.setCenter(position(state, data.places[0]));
    state.map.setLevel(3);
  } else if (data.places.length) {
    state.map.setBounds(bounds, 40, 40, 40, 40);
  } else {
    state.map.setCenter(new state.maps.LatLng(37.55, 126.98));
    state.map.setLevel(7);
  }
  state.status.textContent = data.places.length ? `${data.district} · 지도에 표시한 시설 ${data.places.length.toLocaleString()}곳` :
    '이 조건에서 지도에 표시할 위치 자료가 없어요. 아래 목록에서 주소로 확인해 주세요.';
  state.choice.disabled = !data.places.length;
  updateMotion(state);
}

function load(state) {
  if (state.pending || state.disposed) return;
  state.pending = true;
  state.retry.hidden = true;
  state.status.textContent = '지도를 불러오는 중이에요.';
  Promise.resolve().then(() => window.chachachaKakao(state.data.appkey, 'clusterer')).then(kakao => {
    if (state.disposed) return;
    state.maps = kakao.maps;
    if (!state.map) {
      state.map = new state.maps.Map(state.canvas, {center: new state.maps.LatLng(37.55, 126.98), level: 7});
      state.map.setZoomable(false);
      state.map.addControl(new state.maps.ZoomControl(), state.maps.ControlPosition.RIGHT);
      state.map.addControl(new state.maps.MapTypeControl(), state.maps.ControlPosition.TOPRIGHT);
      state.clusterer = new state.maps.MarkerClusterer({map: state.map, averageCenter: true, minLevel: 5,
        styles: [{width: '42px', height: '42px', background: '#27336B', color: '#FFFFFF', borderRadius: '50%',
          textAlign: 'center', lineHeight: '42px', fontSize: '16px', fontWeight: '700'}]});
      state.popup = new state.maps.InfoWindow({zIndex: 10});
      state.tooltip = new state.maps.CustomOverlay({yAnchor: 1.4, zIndex: 11});
      state.onMapClick = () => closePlace(state);
      state.maps.event.addListener(state.map, 'click', state.onMapClick);
      state.observer = new ResizeObserver(() => {
        if (state.disposed) return;
        const center = state.map.getCenter();
        state.map.relayout();
        state.map.setCenter(center);
      });
      state.observer.observe(state.canvas);
    }
    state.pending = false;
    reconcile(state);
  }).catch(() => {
    if (state.disposed) return;
    clearLayers(state);
    state.observer?.disconnect();
    if (state.map && state.onMapClick) state.maps.event.removeListener(state.map, 'click', state.onMapClick);
    state.map = null;
    state.signature = null;
    state.canvas.replaceChildren();
    state.pending = false;
    state.status.textContent = '지도를 불러오지 못했어요. 아래 목록에서 주소와 이용 안내를 확인해 주세요.';
    state.retry.hidden = false;
  });
}

export default function ({data, parentElement, setStateValue, setTriggerValue}) {
  let state = instances.get(parentElement);
  if (!state) {
    const root = parentElement.querySelector('.kakao-places');
    state = {root, canvas: root.querySelector('.kp-map'), status: root.querySelector('.kp-status'),
      detail: root.querySelector('.kp-detail'), choice: root.querySelector('.kp-choice'),
      motionButton: root.querySelector('.kp-motion'), retry: root.querySelector('.kp-retry'),
      roadviewPanel: root.querySelector('.kp-roadview-panel'), roadviewCanvas: root.querySelector('.kp-roadview'),
      roadviewStatus: root.querySelector('.kp-roadview-status'), roadviewClose: root.querySelector('.kp-roadview-close'),
      roadviewVersion: 0, layers: [], listeners: [], segments: [], pins: [], disposed: false,
      selectionRevision: 0, selection: null, data};
    state.choice.onchange = () => {
      const place = state.data.places.find(item => item.id === state.choice.value);
      if (place && state.map) selectPlace(state, place);
      else {
        closePlace(state);
        closeRoadview(state);
        selectWalkingPlace(state, null);
        updateWalking(state);
      }
    };
    state.motionButton.onclick = () => { state.motion = !state.motion; updateMotion(state); };
    state.retry.onclick = () => load(state);
    state.roadviewClose.onclick = () => closeRoadview(state);
    instances.set(parentElement, state);
  }
  state.data = data;
  state.setStateValue = setStateValue;
  parentElement.querySelector('.kp-detail').hidden = Boolean(data.external_detail);
  state.setTriggerValue = setTriggerValue;
  if (state.map) reconcile(state);
  else load(state);
  return () => {
    state.disposed = true;
    state.observer?.disconnect();
    clearLayers(state);
    if (state.map) state.maps.event.removeListener(state.map, 'click', state.onMapClick);
    instances.delete(parentElement);
  };
}
