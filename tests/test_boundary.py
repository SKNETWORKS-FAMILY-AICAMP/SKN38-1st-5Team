import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from sqlalchemy import text

from db.connection import get_engine, is_local_config
from db.queries import get_region_boundaries, get_filter_options
from tests.query_support import query_overlay
from etl.prepare_boundary import geometry_metrics, prepare_boundary, read_boundary_package, RAW


class BoundaryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = get_engine()
        if not is_local_config(cls.engine.url) or cls.engine.url.database != 'chachacha':
            cls.engine.dispose()
            raise unittest.SkipTest('로컬 chachacha에서만 실행합니다.')
        cls.regions = get_filter_options()['regions']

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()

    def test_boundary_query_has_25_parseable_seoul_polygons(self):
        rows = get_region_boundaries()
        self.assertEqual(len(rows), 25)
        self.assertEqual(set(rows.region_id), set(self.regions.region_id))
        self.assertEqual(set(rows.district_name), set(self.regions.district_name))
        original = {f['properties']['name']: f['geometry'] for f in json.loads(RAW.read_text())['features']}
        for row in rows.to_dict("records"):
            geometry = json.loads(row["geometry_json"])
            self.assertEqual(geometry, original[row["district_name"]])
            self.assertEqual(row["boundary_year"], 2013)
            for name, value in geometry_metrics(geometry).items():
                self.assertAlmostEqual(float(row[name]), value, places=7)
            for ring in geometry['coordinates']:
                for longitude, latitude in ring:
                    self.assertLessEqual(row["min_latitude"], latitude)
                    self.assertLessEqual(latitude, row["max_latitude"])
                    self.assertLessEqual(row["min_longitude"], longitude)
                    self.assertLessEqual(longitude, row["max_longitude"])
        with query_overlay(excluded_sources=('kostat_seoul_boundary',)):
            self.assertTrue(get_region_boundaries().empty)

    def test_geometry_rejects_open_nonfinite_and_outside_rings(self):
        geometry = json.loads(RAW.read_text())['features'][0]['geometry']
        broken = copy.deepcopy(geometry)
        broken['coordinates'][0][-1] = [127, 37.5]
        cases = [broken]
        for point in ([37.5, 127], [float('nan'), 37.5], [True, 37.5], [127, 38]):
            broken = copy.deepcopy(geometry)
            broken['coordinates'][0][1] = point
            cases.append(broken)
        for candidate in cases:
            with self.subTest(), self.assertRaises(ValueError):
                geometry_metrics(candidate)

    def test_centroid_uses_area_and_holes_independent_of_winding(self):
        outer = [[127.0,37.5],[127.1,37.5],[127.1,37.6],[127.0,37.6],[127.0,37.5]]
        hole = [[127.06,37.51],[127.08,37.51],[127.08,37.53],[127.06,37.53],[127.06,37.51]]
        geometry = {'type': 'Polygon', 'coordinates': [outer, hole]}
        result = geometry_metrics(geometry)
        self.assertAlmostEqual(result['centroid_longitude'], (127.05 * .01 - 127.07 * .0004) / .0096, places=7)
        self.assertAlmostEqual(result['centroid_latitude'], (37.55 * .01 - 37.52 * .0004) / .0096, places=7)
        self.assertEqual(result['ring_count'], 2)
        self.assertEqual(result, geometry_metrics({'type': 'Polygon', 'coordinates': [outer[::-1], hole[::-1]]}))
        self.assertEqual(result, geometry_metrics({'type': 'MultiPolygon', 'coordinates': [[outer, hole]]}))

    def test_prepare_hashes_and_failure_do_not_publish_stale_success(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            record = prepare_boundary(self.regions, folder)
            self.assertTrue(record['passed'] and record['published'])
            source, frame = read_boundary_package(folder)
            self.assertEqual(len(frame), 25)
            csv = (folder / 'region_boundary.csv').read_bytes()
            prepare_boundary(self.regions, folder)
            self.assertEqual(csv, (folder / 'region_boundary.csv').read_bytes())
            with patch('etl.prepare_boundary.build_frame', side_effect=ValueError), self.assertRaises(ValueError):
                prepare_boundary(self.regions, folder)
            self.assertEqual(csv, (folder / 'region_boundary.csv').read_bytes())
            with self.assertRaises(ValueError):
                read_boundary_package(folder)
            prepare_boundary(self.regions, folder)
            with (folder / 'region_boundary.csv').open('ab') as output:
                output.write(b'\n')
            with self.assertRaises(ValueError):
                read_boundary_package(folder)
