import json
import re
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import requests
from streamlit.components.v2.bidi_component.main import _make_trigger_id
from streamlit.testing.v1 import AppTest

from tests import app_env
from parking_explorer import (charger_records, distance_m, fee, hours, map_html, map_payload,
                              parking_records, place_distance_m, restriction_label,
                              region_boundary, seoul_parking, station_search)


class ParkingExplorerTest(unittest.TestCase):
    def setUp(self):
        key_patch = patch("parking_explorer.javascript_key", return_value="")
        key_patch.start()
        self.addCleanup(key_patch.stop)
        rest_patch = patch("parking_explorer.rest_key", return_value="")
        rest_patch.start()
        self.addCleanup(rest_patch.stop)

    def test_prices_do_not_turn_missing_amounts_or_zero_caps_into_free(self):
        self.assertEqual(fee({"pay_yn": "N"}), "무료")
        self.assertIn("금액 정보 미제공", fee({"pay_yn": "Y", "rates": "", "day_maximum": "0"}))
        label = fee({"pay_yn": "Y", "rates": "0", "time_rate": "30", "add_rates": "1000", "add_time_rate": "10"})
        self.assertIn("유료", label)
        self.assertIn("기본 30분 0원", label)
        self.assertIn("추가 10분 1,000원", label)
        self.assertIn("유·무료 정보 미제공", fee({}))

    def test_hours_missing_closed_and_overnight(self):
        self.assertEqual(hours("0000", "2400"), "24시간")
        self.assertEqual(hours("0000", "0000"), "운영 여부 확인 필요")
        self.assertEqual(hours(None, "1800"), "정보 미제공")
        self.assertIn("다음 날", hours("2200", "0600"))
        self.assertEqual(hours("9999", "1800"), "정보 미제공")

    def test_invalid_coordinates_are_not_mapped(self):
        rows = [{"parking_code": "1", "parking_type": "NS", "parking_name": "실제 주차장",
                 "position_list": [{"lat": "0", "lng": "0"}, {"lat": "37.55", "lng": "126.93"}]}]
        records = parking_records(rows)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["name"], "실제 주차장")
        self.assertEqual(records[0]["operation"], "공영")
        self.assertEqual(parking_records([{"position_list": [{"lat": 0, "lng": 0}]}]), [])

    def test_station_search_excludes_shops_and_exits(self):
        station_search.clear()
        rows = [{"title": title, "latitude": "37.4852", "longitude": "127.0162"}
                for title in ["남부터미널역 3호선", "카페 남부터미널역점", "남부터미널역 3호선 1번출구"]]
        with patch("parking_explorer.requests.post") as post:
            post.return_value.json.return_value = rows
            self.assertEqual([r["name"] for r in station_search("남부터미널역")], ["남부터미널역 3호선"])
        station_search.clear()

    def test_network_failure_is_distinct_from_no_parking_results(self):
        seoul_parking.clear()
        with patch("parking_explorer.requests.post", side_effect=requests.Timeout):
            self.assertIsNone(seoul_parking("마포구"))
        seoul_parking.clear()

    def test_failed_requests_retry_and_successful_results_are_cached(self):
        for fetch, argument, payload in (
            (seoul_parking, "마포구", {"result_state": "0000", "res_value": {"parking_list": []}}),
            (station_search, "홍대입구역", [{"title": "홍대입구역 2호선", "latitude": 37.55, "longitude": 126.93}]),
        ):
            with self.subTest(fetch=fetch.__name__):
                fetch.clear()
                with patch("parking_explorer.requests.post") as post:
                    response = post.return_value
                    response.json.return_value = payload
                    post.side_effect = [requests.Timeout(), response]
                    self.assertFalse(fetch(argument))
                    recovered = fetch(argument)
                    self.assertIsNotNone(recovered)
                    self.assertEqual(fetch(argument), recovered)
                    self.assertEqual(post.call_count, 2)
                fetch.clear()

    def test_known_restriction_is_not_hidden_when_note_is_missing(self):
        restricted = pd.DataFrame([{"restriction_code": "Y", "restriction_note": None}])
        self.assertEqual(restriction_label(restricted), "이용제한 있음 · 상세 정보 미제공")
        mixed = pd.DataFrame([{"restriction_code": "Y", "restriction_note": "입주민 전용"},
                              {"restriction_code": "N", "restriction_note": None}])
        self.assertEqual(restriction_label(mixed), "일부 충전기 이용제한 있음 · 입주민 전용")
        partial = pd.DataFrame([{"restriction_code": "N"}, {"restriction_code": None}])
        self.assertIn("제한 여부 미확인", restriction_label(partial))
        self.assertIn("제한 여부 미확인", restriction_label(pd.DataFrame()))

    def test_parking_segment_uses_nearest_coordinate_without_double_counting(self):
        station = {"name": "검색역", "latitude": 37.52, "longitude": 127.03}
        rows = [{"parking_code": "388", "infra_type": "time", "parking_name": "긴 주차구간",
                 "position_list": [{"lat": 37.54, "lng": 127.03}, {"lat": 37.52, "lng": 127.03}]}]
        records = parking_records(rows + rows)
        self.assertEqual(len(records), 1)
        self.assertEqual(len(records[0]["positions"]), 2)
        self.assertGreater(distance_m(station, records[0]), 2000)
        self.assertEqual(place_distance_m(station, records[0]), 0)
        html = map_html(records, station)
        payload = json.loads(re.search(r"const data=(.*?);\nconst esc", html, re.S).group(1))
        self.assertEqual(payload["places"][0]["latitude"], station["latitude"])
        self.assertEqual(len(payload["places"][0]["positions"]), 2)
        self.assertEqual(records[0]["latitude"], 37.54, "Rendering must not mutate cached records")

    def test_distance_boundary_and_html_escaping(self):
        station = {"name": "홍대입구역", "latitude": 37.55, "longitude": 126.93}
        self.assertEqual(distance_m(station, station), 0)
        self.assertGreater(distance_m(station, {"latitude": 37.56, "longitude": 126.93}), 1000)
        html = map_html([{"name": "</script><img onerror=alert(1)>", "latitude": 37.55, "longitude": 126.93}], station, 500, False)
        self.assertNotIn("</script><img onerror", html)
        self.assertIn("\\u003c/script>", html)
        self.assertIn('"animate": false', html)
        self.assertIn("map.kakao.com/link/to/", html)
        self.assertIn("map.kakao.com/link/roadview/", html)
        self.assertNotIn("map.naver.com", html)
        self.assertIn("distance=p.distance_m,near=p.near", html)

    def test_map_payload_uses_python_distance_and_counts_facilities_not_segments(self):
        station = {"name": "검색역", "latitude": 37.52, "longitude": 127.03}
        record = {"id": "parking-1", "name": "주차장", "latitude": 37.54, "longitude": 127.03,
                  "positions": [{"latitude": 37.54, "longitude": 127.03}, station]}
        payload = map_payload([record, record, {"id": "invalid", "latitude": 0, "longitude": 0}], station, 300, False)
        self.assertEqual(len(payload["places"]), 1)
        place = payload["places"][0]
        self.assertEqual(place["distance_m"], place_distance_m(station, record))
        self.assertTrue(place["near"])
        self.assertEqual(place["latitude"], station["latitude"])
        self.assertEqual(len(place["positions"]), 2)
        self.assertFalse(payload["animate"])
        self.assertEqual(record["latitude"], 37.54)
        far = {"id": "far", "latitude": 37.54, "longitude": 127.03}
        outside = map_payload([far], station, 300)["places"][0]
        self.assertFalse(outside["near"])
        self.assertEqual(outside["distance_m"], distance_m(station, far))
        plain = map_payload([far])["places"][0]
        self.assertIsNone(plain["distance_m"])
        self.assertFalse(plain["near"])

    def test_component_keeps_identity_when_records_change_or_become_empty(self):
        source = '''
import streamlit as st
from parking_explorer import render_map
render_map(st.session_state.get("places", []), st.session_state.get("district", "마포구"))
'''
        with patch("parking_explorer.javascript_key", return_value="test-only"):
            app = AppTest.from_string(source).run()
            self.assertFalse(app.exception)
            component = app.get("bidi_component")[0].proto
            identity = component.id
            self.assertEqual(component.component_name, "chachacha_kakao_places")
            self.assertFalse(app.get("iframe"))
            for district, places in (("마포구", [{"id": "one", "latitude": 37.55, "longitude": 126.93}]),
                                     ("강남구", [{"id": "two", "latitude": 37.5, "longitude": 127.04}]),
                                     ("강남구", [])):
                app.session_state["district"] = district
                app.session_state["places"] = places
                app.run()
                self.assertFalse(app.exception)
                component = app.get("bidi_component")[0].proto
                self.assertEqual(component.id, identity)
                payload = json.loads(component.json)
                self.assertEqual(payload["district"], district)
                self.assertEqual([p["id"] for p in payload["places"]], [p["id"] for p in places])
                self.assertNotIn("rest_api_key", payload)

    def test_boundary_uses_selected_db_geometry_and_rejects_missing_shapes(self):
        ring = [[126.93, 37.55], [126.94, 37.55], [126.93, 37.56], [126.93, 37.55]]
        frame = pd.DataFrame([{"region_id": 1, "geometry_json": json.dumps({"type": "Polygon", "coordinates": [ring]}),
                               "boundary_year": 2013},
                              {"region_id": 2, "geometry_json": json.dumps({"type": "MultiPolygon", "coordinates": [[ring]]}),
                               "boundary_year": 2013}])
        with patch("parking_explorer.q.get_region_boundaries", return_value=frame):
            self.assertEqual(region_boundary(1), {"polygons": [[ring]], "year": 2013})
            self.assertEqual(region_boundary(2), region_boundary(1))
            self.assertEqual(region_boundary(999), {})
        for geometry in ('{}', 'invalid', '{"type":"Point","coordinates":[126.93,37.55]}',
                         '{"type":"Polygon","coordinates":[[[0,0],[0,1],[1,0]]]}'):
            with self.subTest(geometry=geometry), patch("parking_explorer.q.get_region_boundaries", return_value=frame.assign(geometry_json=geometry)):
                self.assertEqual(region_boundary(1), {})

    def test_javascript_map_lifecycle_clusters_and_sdk_failure(self):
        script = r'''
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const source = readFileSync(process.argv[2], 'utf8');
const render = (await import('data:text/javascript;base64,' + Buffer.from(source).toString('base64'))).default;
class Element {
  constructor() { this.children = []; this.style = {setProperty() {}}; this.attributes = {}; this.classList = {toggle() {}}; }
  appendChild(child) { this.children.push(child); return child; }
  replaceChildren(...children) { this.children = children; }
  setAttribute(name, value) { this.attributes[name] = value; }
}
globalThis.document = {createElement: () => new Element()};
globalThis.Option = class extends Element { constructor(text, value) { super(); this.textContent = text; this.value = value; } };
const observers = [];
globalThis.ResizeObserver = class { constructor(callback) { this.callback = callback; observers.push(this); } observe() {} disconnect() { this.stopped = true; } };
const allMaps = [], allLayers = [], clusters = [], events = [], roadviews = [], timers = [];
globalThis.setTimeout = (callback, delay) => { timers.push({callback, delay}); return callback; };
globalThis.clearTimeout = () => {};
class MapView {
  constructor(element, options) { this.center = options.center; allMaps.push(this); }
  setZoomable(value) { this.zoomable = value; }
  addControl(control) { (this.controls ||= []).push(control); } setBounds() {} setLevel() {} relayout() {}
  setCenter(value) { this.center = value; } getCenter() { return this.center; }
}
class Layer {
  constructor(options = {}) { this.options = options; this.map = options.map; allLayers.push(this); }
  setMap(map) { this.map = map; }
  setContent(content) { this.content = content; } setPosition(point) { this.point = point; }
  open(map) { this.map = map; } close() { this.map = null; } getBounds() { return {}; }
}
class Marker extends Layer {}
class Circle extends Layer {}
class Polygon extends Layer {}
let panoCallback;
class RoadviewClient { getNearestPanoId(point, radius, callback) { assert.equal(radius, 50); panoCallback = callback; } }
class Roadview { constructor() { roadviews.push(this); } relayout() {} setPanoId(id) { this.pano = id; } }
class Clusterer {
  constructor(options) { this.map = options.map; this.markers = []; clusters.push(this); }
  clear() { this.markers.forEach(marker => marker.setMap(null)); this.markers = []; }
  addMarkers(markers) { this.markers = markers; markers.forEach(marker => marker.setMap(this.map)); }
}
const maps = {Map: MapView, Marker, Circle, Polygon, RoadviewClient, Roadview,
  MarkerClusterer: Clusterer, InfoWindow: Layer, CustomOverlay: Layer,
  MarkerImage: class {}, Size: class {}, Point: class {}, ZoomControl: class {}, MapTypeControl: class {}, ControlPosition: {RIGHT: 1, TOPRIGHT: 2},
  LatLng: class { constructor(lat, lon) { this.lat = lat; this.lon = lon; } },
  LatLngBounds: class { extend() {} }, event: {
    addListener(target, name, callback) { events.push({target, name, callback}); },
    removeListener(target, name, callback) { const i = events.findIndex(e => e.target === target && e.name === name && e.callback === callback); if (i >= 0) events.splice(i, 1); },
  }};
let loads = 0;
globalThis.window = {chachachaKakao: async (_, libraries) => { loads++; assert.equal(libraries, 'clusterer'); return {maps}; }};
function parent() {
  const nodes = Object.fromEntries(['.kp-map', '.kp-status', '.kp-detail', '.kp-choice', '.kp-motion', '.kp-retry',
    '.kp-roadview-panel', '.kp-roadview', '.kp-roadview-status', '.kp-roadview-close'].map(name => [name, new Element()]));
  const root = new Element(); root.querySelector = name => nodes[name];
  return {querySelector: () => root, nodes};
}
const tick = () => new Promise(resolve => setImmediate(resolve));
const place = (id, near = false) => ({id, name: '<장소>', kind: '주차장', operation: '공영', latitude: 37.55, longitude: 126.93,
  price: '정보 미제공', hours: '24시간', near, distance_m: near ? 10 : 1000,
  positions: [{latitude: 37.55, longitude: 126.93}, {latitude: 37.551, longitude: 126.931}]});
const data = {appkey: 'test-only', places: [place('near', true), place('far')], station: {name: '역', latitude: 37.55, longitude: 126.93}, radius: 500, animate: true, district: '마포구'};
const root = parent();
let cleanup = render({data, parentElement: root});
await tick();
assert.equal(loads, 1); assert.equal(allMaps.length, 1); assert.equal(allMaps[0].zoomable, false);
assert.equal(allMaps[0].controls.length, 2);
assert.equal(clusters[0].markers.length, 1, 'Highlighted facilities must remain outside the cluster');
assert.equal(allLayers.filter(layer => layer instanceof Circle).length, 1, 'Segments stay hidden until a facility opens');
const oldMarker = clusters[0].markers[0];
events.find(event => event.target === oldMarker && event.name === 'click').callback();
assert.equal(allLayers.filter(layer => layer instanceof Circle && layer.map).length, 2);
assert.ok(root.nodes['.kp-detail'].children[0].innerHTML.includes('&lt;장소&gt;'));
assert.ok(root.nodes['.kp-detail'].children[0].innerHTML.includes('map.kakao.com/link/to/'));
assert.ok(root.nodes['.kp-detail'].children[0].innerHTML.includes('map.kakao.com/link/roadview/'));
const openRoadview = root.nodes['.kp-detail'].children[0].children[0];
assert.equal(roadviews.length, 0, 'Roadview is loaded only on request');
openRoadview.onclick(); panoCallback(null);
assert.match(root.nodes['.kp-roadview-status'].textContent, /표시할 수 없어요/);
openRoadview.onclick(); panoCallback(123);
assert.equal(roadviews.length, 1); assert.equal(roadviews[0].pano, 123);
assert.equal(root.nodes['.kp-roadview'].hidden, false);
openRoadview.onclick(); const late = panoCallback;
assert.equal(timers.at(-1).delay, 8000); timers.at(-1).callback(); late(456);
assert.equal(roadviews[0].pano, 123); assert.equal(root.nodes['.kp-roadview'].hidden, true);
openRoadview.onclick(); const obsolete = panoCallback;
cleanup = render({data: {...data, places: [place('new')], district: '강남구'}, parentElement: root});
obsolete(789); assert.equal(roadviews[0].pano, 123); assert.equal(root.nodes['.kp-roadview-panel'].hidden, true);
assert.equal(allMaps.length, 1); assert.equal(loads, 1); assert.equal(oldMarker.map, null);
assert.equal(clusters[0].markers.length, 1); assert.equal(root.nodes['.kp-choice'].children[1].value, 'new');
cleanup = render({data: {...data, places: [], station: null}, parentElement: root});
assert.equal(allMaps.length, 1); assert.equal(clusters[0].markers.length, 0);
assert.ok(allLayers.every(layer => !layer.map));
assert.match(root.nodes['.kp-status'].textContent, /위치 자료가 없어요/);
const boundary = {polygons: [[[[126.93, 37.55], [126.94, 37.55], [126.93, 37.56], [126.93, 37.55]]]]};
cleanup = render({data: {...data, places: [], station: null, boundary}, parentElement: root});
const polygon = allLayers.find(layer => layer instanceof Polygon && layer.map);
assert.equal(polygon.options.path[0][0].lat, 37.55); assert.equal(polygon.options.path[0][0].lon, 126.93);
assert.equal(clusters[0].markers.length, 0); assert.equal(allMaps.length, 1);
cleanup(); assert.equal(events.length, 0); assert.ok(observers[0].stopped);
const failed = parent();
window.chachachaKakao = async () => { throw new Error('private-url'); };
cleanup = render({data, parentElement: failed}); await tick();
assert.match(failed.nodes['.kp-status'].textContent, /아래 목록/);
assert.ok(!failed.nodes['.kp-status'].textContent.includes('private-url'));
assert.equal(failed.nodes['.kp-retry'].hidden, false);
window.chachachaKakao = async () => ({maps});
failed.nodes['.kp-retry'].onclick(); await tick();
assert.equal(allMaps.length, 2); cleanup();
let resolve;
window.chachachaKakao = () => new Promise(done => { resolve = done; });
const pending = parent();
cleanup = render({data, parentElement: pending}); await tick();
cleanup = render({data: {...data, places: [place('latest')]}, parentElement: pending});
resolve({maps}); await tick();
assert.equal(pending.nodes['.kp-choice'].children[1].value, 'latest'); cleanup();
const gone = parent(); cleanup = render({data, parentElement: gone}); await tick();
const before = allMaps.length; cleanup(); resolve({maps}); await tick();
assert.equal(allMaps.length, before, 'Unmounted maps must ignore late SDK completion');
assert.equal(events.length, 0);
window.chachachaKakao = async () => ({maps});
const walkRoot = parent(), selections = [], requests = [];
const walkData = {...data, walk_enabled: true, walking: null};
const renderWalk = next => render({data: next, parentElement: walkRoot,
  setStateValue: (name, value) => { assert.equal(name, 'selected_place'); selections.push(value); },
  setTriggerValue: (name, value) => { assert.equal(name, 'walk_request'); requests.push(value); }});
cleanup = renderWalk(walkData); await tick();
const mapCount = allMaps.length;
const choose = id => { walkRoot.nodes['.kp-choice'].value = id; walkRoot.nodes['.kp-choice'].onchange(); };
const walkSection = () => walkRoot.nodes['.kp-detail'].children[0].children.find(node => node.className === 'kp-walk');
choose('near');
assert.equal(requests.length, 0, 'Opening a facility never requests a route');
assert.equal(selections.at(-1).requested, false); assert.equal(walkSection().hidden, false);
walkSection().children[0].onclick();
assert.deepEqual(requests, ['near'], 'Only the facility ID is sent in the trigger');
assert.equal(walkSection().children[0].disabled, true);
walkSection().children[0].onclick(); assert.equal(requests.length, 1);
const success = {...walkData, walking: {place_id: 'near', revision: selections.at(-1).revision,
  result: {distance_m: 750, duration_s: 125}}};
cleanup = renderWalk(success);
assert.match(walkSection().children[1].textContent, /도보 약 3분 · 750m · 카카오 제공/);
assert.ok(walkRoot.nodes['.kp-detail'].children[0].innerHTML.includes('직선 10m'));
assert.equal(walkSection().children[0].disabled, false);
cleanup = renderWalk({...success, animate: false});
assert.equal(allMaps.length, mapCount); assert.equal(requests.length, 1);
choose('far');
assert.equal(walkSection().children[1].textContent, '');
cleanup = renderWalk(success);
assert.equal(walkSection().children[1].textContent, '', 'Late results for another facility are ignored');
choose('near');
cleanup = renderWalk(success);
assert.equal(walkSection().children[1].textContent, '', 'Returning to a facility does not restore its old result');
walkSection().children[0].onclick();
cleanup = renderWalk({...walkData, walking: {place_id: 'near', revision: selections.at(-1).revision, result: null}});
assert.match(walkSection().children[1].textContent, /도보 경로를 찾지 못했어요/);
assert.ok(walkRoot.nodes['.kp-detail'].children[0].innerHTML.includes('직선 10m'));
choose(''); assert.equal(walkSection().hidden, true); assert.equal(selections.at(-1), null);
const requested = requests.length;
cleanup = renderWalk({...walkData, walk_enabled: false}); choose('near');
assert.equal(walkSection().hidden, true);
walkSection().children[0].onclick(); assert.equal(requests.length, requested);
const oldSection = walkSection();
cleanup = renderWalk({...walkData, station: null, walk_enabled: false});
assert.equal(oldSection.hidden, true);
assert.equal(allMaps.length, mapCount); cleanup(); assert.equal(events.length, 0);
console.log('Lifecycle, clustering, replacement, failure, retry and cleanup passed');
'''
        result = subprocess.run(["node", "--input-type=module", "-",
                                 str(Path(__file__).resolve().parents[1] / "assets/kakao_places.js")],
                                input=script, text=True, capture_output=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_charger_parking_fee_is_not_charging_fee(self):
        points = pd.DataFrame([{"place_id": 1, "place_name": "충전소", "address": "주소",
                                "latitude": 37.55, "longitude": 126.93, "charger_count": 2,
                                "operator_name": "운영사"}])
        devices = pd.DataFrame([{"station_id": 1, "parking_free": "Y", "operating_time_text": "24시간",
                                  "restriction_note": None}])
        record = charger_records(points, devices)[0]
        self.assertIn("주차 무료", record["price"])
        self.assertIn("충전요금: 금액 정보 미제공", record["price"])
        self.assertEqual(record["hours"], "24시간")

    def test_public_map_search_and_station_highlight(self):
        station = {"name": "홍대입구역 2호선", "latitude": 37.55687, "longitude": 126.92378}
        place = {"id": "public-1", "name": "홍대 테스트 주차장", "address": "서울 마포구 양화로",
                 "latitude": 37.58, "longitude": 126.924, "operation": "공영", "kind": "주차장",
                 "positions": [{"latitude": 37.58, "longitude": 126.924},
                               {"latitude": 37.557, "longitude": 126.924}],
                 "price": "유료 · 기본 10분 500원", "hours": "24시간", "note": "현장 확인",
                 "capacity": "10면", "operator": "서울시", "updated": "2026-11-09"}
        with patch("parking_explorer.seoul_parking", return_value=[place]), \
                patch("parking_explorer.station_search", return_value=[station]):
            app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py", default_timeout=40).run()
            app.switch_page("app_pages/parking.py").run()
            app.selectbox(key="parking_station_마포구_").set_value(1).run()
            self.assertFalse(app.exception)
            self.assertFalse(app.error)
            self.assertTrue(any("500m 안 주차장 1곳" in x.value for x in app.caption))
            app.text_input(key="parking_keyword").set_value("홍대 테스트").run()
            html = app.get("iframe")[0].proto.srcdoc
            payload = json.loads(re.search(r"const data=(.*?);\nconst esc", html, re.S).group(1))
            self.assertEqual(payload["places"][0]["name"], "홍대 테스트 주차장")
            self.assertEqual(payload["station"]["name"], station["name"])
            self.assertEqual(payload["places"][0]["latitude"], 37.557)
            app.checkbox(key="parking_pin_animation").uncheck().run()
            self.assertIn('"animate": false', app.get("iframe")[0].proto.srcdoc)
            app.text_input(key="parking_keyword").set_value("일치하지않는장소").run()
            self.assertTrue(any("반경에 표시할 시설이 없어요" in x.value for x in app.info))


class WalkingMapTest(unittest.TestCase):
    def setUp(self):
        self.javascript_key = self.enterContext(patch("parking_explorer.javascript_key", return_value="test-only"))
        self.rest_key = self.enterContext(patch("parking_explorer.rest_key", return_value="test-only"))
        self.get_walking_route = self.enterContext(patch("parking_explorer.get_walking_route",
                                                       return_value={"distance_m": 750, "duration_s": 125}))
        self.source = '''
import streamlit as st
from parking_explorer import render_map
render_map(st.session_state["records"], "마포구", st.session_state["station"])
'''
        self.records = [
            {"id": "parking-a", "latitude": 37.57, "longitude": 126.93,
             "positions": [{"latitude": 37.57, "longitude": 126.93}, {"latitude": 37.551, "longitude": 126.93}]},
            {"id": "charger-b", "kind": "충전소", "latitude": 37.56, "longitude": 126.94},
        ]
        self.station = {"name": "검색역", "latitude": 37.55, "longitude": 126.93}
        self.app = self.new_app()

    def new_app(self):
        app = AppTest.from_string(self.source)
        app.session_state["records"] = self.records
        app.session_state["station"] = self.station
        app.run()
        self.assertFalse(app.exception)
        return app

    def payload(self):
        self.assertFalse(self.app.exception)
        return json.loads(self.app.get("bidi_component")[0].proto.json)

    def event(self, selection, request=None):
        component = self.app.get("bidi_component")[0].proto
        states = self.app._tree.get_widget_states()
        state = states.widgets.add()
        state.id = component.id
        state.json_value = json.dumps({"selected_place": selection})
        if request is not None:
            trigger = states.widgets.add()
            trigger.id = _make_trigger_id(component.id, "events")
            trigger.json_trigger_value = json.dumps([{"event": "walk_request", "value": request}])
        self.app._run(widget_state=states)
        return self.payload()

    def request(self, place_id="parking-a", revision=1):
        return self.event({"id": place_id, "revision": revision, "requested": True}, place_id)

    def assert_cleared(self):
        self.assertIsNone(self.payload()["walking"])
        self.assertNotIn("parking_places_map_walking", self.app.session_state)

    def test_query_only_on_button_uses_python_nearest_position_and_not_cached(self):
        self.assertTrue(self.payload()["walk_enabled"])
        self.event({"id": "parking-a", "revision": 1, "requested": False})
        self.get_walking_route.assert_not_called()
        data = self.request(revision=2)
        self.get_walking_route.assert_called_once_with(37.55, 126.93, 37.551, 126.93)
        self.assertEqual(data["walking"]["result"], {"distance_m": 750, "duration_s": 125})
        self.assertEqual(data["places"][0]["distance_m"], place_distance_m(self.station, self.records[0]))
        self.app.run()
        self.assertEqual(self.get_walking_route.call_count, 1)
        self.assertEqual(self.payload()["walking"], data["walking"])
        self.get_walking_route.return_value = {"distance_m": 0, "duration_s": 0}
        self.assertEqual(self.request(revision=3)["walking"]["result"], {"distance_m": 0, "duration_s": 0})
        self.assertEqual(self.get_walking_route.call_count, 2)
        other = self.new_app()
        self.assertIsNone(json.loads(other.get("bidi_component")[0].proto.json)["walking"])

    def test_selection_station_destination_and_filter_changes_clear_result(self):
        self.request()
        self.event({"id": "charger-b", "revision": 2, "requested": False})
        self.assert_cleared()
        self.request("charger-b", 3)
        self.app.session_state["station"] = {**self.station, "latitude": 37.555}
        self.app.run()
        self.assert_cleared()
        self.assertEqual(self.get_walking_route.call_count, 2)
        self.request("charger-b", 4)
        self.get_walking_route.assert_called_with(37.555, 126.93, 37.56, 126.94)
        self.app.session_state["records"] = [self.records[0], {**self.records[1], "latitude": 37.561}]
        self.app.run()
        self.assert_cleared()
        self.request("charger-b", 5)
        self.app.session_state["records"] = [self.records[0]]
        self.app.run()
        self.assert_cleared()
        self.assertEqual(self.get_walking_route.call_count, 4)

    def test_missing_key_or_station_disables_queries_and_clears_session(self):
        self.request()
        self.rest_key.return_value = ""
        data = self.request(revision=2)
        self.assertFalse(data["walk_enabled"])
        self.assert_cleared()
        self.assertNotIn("rest_api_key", data)
        self.assertEqual(self.get_walking_route.call_count, 1)
        self.rest_key.return_value = "test-only"
        self.request(revision=3)
        self.app.session_state["station"] = None
        self.app.run()
        self.assertFalse(self.payload()["walk_enabled"])
        self.assert_cleared()
        self.request(revision=4)
        self.assertEqual(self.get_walking_route.call_count, 2)
        self.app.session_state["station"] = self.station
        self.app.run()
        self.request(revision=5)
        self.javascript_key.return_value = ""
        self.app.run()
        self.assertFalse(self.app.exception)
        self.assertTrue(self.app.get("iframe"))
        self.assertNotIn("parking_places_map_walking", self.app.session_state)
        self.assertEqual(self.get_walking_route.call_count, 3)

    def test_invalid_ids_and_stale_selection_events_are_ignored(self):
        selection = {"id": "parking-a", "revision": 1, "requested": True}
        for invalid in (None, True, 1, {}, [], "missing", "charger-b"):
            with self.subTest(request=invalid):
                self.event(selection, invalid)
                self.assert_cleared()
        for invalid in (None, "parking-a", {}, {**selection, "id": []}, {**selection, "id": "missing"},
                        {**selection, "revision": "1"}, {**selection, "revision": True},
                        {**selection, "requested": False}):
            with self.subTest(selection=invalid):
                self.event(invalid, "parking-a")
                self.assert_cleared()
        self.get_walking_route.assert_not_called()

    def test_failure_keeps_straight_distance_and_retries_only_on_another_button_press(self):
        self.get_walking_route.return_value = None
        data = self.request()
        self.assertIsNone(data["walking"]["result"])
        self.assertGreater(data["places"][0]["distance_m"], 0)
        self.app.run()
        self.assertEqual(self.get_walking_route.call_count, 1)
        self.request(revision=2)
        self.assertEqual(self.get_walking_route.call_count, 2)
        self.event(None)
        self.assert_cleared()


if __name__ == "__main__":
    unittest.main()
