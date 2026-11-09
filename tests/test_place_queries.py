from datetime import date
import unittest

import pandas as pd
from sqlalchemy import text

from db.connection import LOCAL_HOSTS, get_engine
from db import queries as q
from tests.query_support import points_and_coverage, query_overlay


class PlaceQueryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = get_engine()
        if cls.engine.url.host not in LOCAL_HOSTS or cls.engine.url.database != 'chachacha':
            raise unittest.SkipTest('로컬 chachacha에서만 실행합니다.')
        cls.points, cls.coverage = points_and_coverage()

    def test_place_points_count_coordinate_and_exclusion_totals(self):
        points, coverage = self.points, self.coverage
        self.assertGreater(len(points), 0)
        self.assertTrue(points.latitude.between(37.4, 37.75).all())
        self.assertTrue(points.longitude.between(126.75, 127.2).all())
        self.assertFalse(points.duplicated(['kind', 'place_id']).any())
        self.assertTrue(points.coordinate_valid.eq(1).all())
        self.assertTrue(coverage.total_count.eq(coverage.point_count + coverage.excluded_count).all())
        self.assertTrue(coverage.excluded_count.eq(coverage.invalid_coordinate_count + coverage.identifier_conflict_count).all())
        self.assertEqual(int(coverage.point_count.sum()), len(points))
        self.assertEqual(coverage.set_index('kind').total_count.to_dict(), {'charging_station': 13098, 'parking_site': 857})
        charging = points.loc[points.kind.eq('charging_station')]
        self.assertTrue(charging.charger_count.eq(charging.fast_count + charging.slow_count + charging.unknown_count).all())

    def test_region_and_kind_filters_have_consistent_counts(self):
        ids = q.get_filter_options()['regions'].region_id.iloc[:2].tolist()
        for region in ids:
            points, coverage = points_and_coverage(region, kinds=('parking',))
            expected = self.points.loc[self.points.region_id.eq(region) & self.points.kind.eq('parking_site')]
            self.assertEqual(set(points.place_id), set(expected.place_id))
            self.assertEqual(int(coverage.point_count.sum()), len(points))
            self.assertEqual(coverage.kind.tolist(), ['parking_site'])
        points, coverage = points_and_coverage(65000)
        self.assertTrue(points.empty)
        self.assertEqual(int(coverage.total_count.sum()), 0)
        points, coverage = points_and_coverage(kinds=())
        self.assertTrue(points.empty and coverage.empty)
        limited = q.get_place_points(None, limit=3)
        self.assertEqual(len(limited), 3)
        self.assertEqual(limited.attrs['coverage'], self.points.attrs['coverage'])

    def test_speed_and_snapshot_filters_share_map_and_exclusion_population(self):
        station = self.points.loc[self.points.kind.eq('charging_station') & self.points.charger_count.ge(2)].iloc[0]
        region, station_id = int(station.region_id), int(station.place_id)
        with self.engine.connect() as conn:
            first = conn.execute(text('SELECT MIN(source_charger_id) FROM charger WHERE station_id=:id'), {'id': station_id}).scalar_one()
            raw = pd.read_sql_query(text('''SELECT t.station_id, t.source_snapshot_id, c.source_charger_id, c.speed_code, c.latitude, c.longitude
                FROM charging_station t JOIN charger c ON c.station_id=t.station_id WHERE t.region_id=:region'''), conn, params={'region': region})
        selected = raw.station_id.eq(station_id)
        raw.loc[selected, ['latitude','longitude']] = float('nan')
        raw.loc[selected, 'speed_code'] = 'fast'
        raw.loc[selected & raw.source_charger_id.eq(first), ['speed_code','latitude','longitude']] = ['slow',37.6,127.0]
        changed = {'charger': {'columns': {
            'speed_code': "CASE WHEN station_id=:fixture_station THEN CASE WHEN source_charger_id=:fixture_first THEN 'slow' ELSE 'fast' END ELSE speed_code END",
            'latitude': 'CASE WHEN station_id=:fixture_station THEN CASE WHEN source_charger_id=:fixture_first THEN 37.6 ELSE NULL END ELSE latitude END',
            'longitude': 'CASE WHEN station_id=:fixture_station THEN CASE WHEN source_charger_id=:fixture_first THEN 127.0 ELSE NULL END ELSE longitude END'}}}
        snapshots = q.get_filter_options()['snapshots'].set_index('source_code').snapshot_id.to_dict()
        for source in ('keco_ev_charger','seoul_charger'):
            with query_overlay(changed, source=source, params={'fixture_station': station_id, 'fixture_first': first}):
                for speed in ('all','fast','slow','unknown'):
                    with self.subTest(source=source, speed=speed):
                        expected = raw.loc[raw.source_snapshot_id.eq(snapshots[source])]
                        if speed != 'all':
                            expected = expected.loc[expected.speed_code.eq(speed)]
                        valid = expected.latitude.between(37.4,37.75) & expected.longitude.between(126.75,127.2)
                        mapped_ids = set(expected.loc[valid,'station_id'])
                        counts = expected.groupby('station_id').size().loc[lambda rows: rows.index.isin(mapped_ids)]
                        points, coverage = points_and_coverage(region, speed=speed)
                        charging = points.loc[points.kind.eq('charging_station')].set_index('place_id')
                        self.assertEqual(charging.charger_count.to_dict(), counts.to_dict())
                        self.assertTrue(charging.source_snapshot_id.eq(snapshots[source]).all())
                        if speed != 'all':
                            self.assertTrue(charging.charger_count.eq(charging[speed+'_count']).all())
                        row = coverage.set_index('kind').loc['charging_station']
                        self.assertEqual(int(row.total_count), expected.station_id.nunique())
                        self.assertEqual(int(row.point_count), len(mapped_ids))
                        self.assertEqual(int(row.excluded_count), expected.station_id.nunique()-len(mapped_ids))
                        self.assertEqual(int(row.invalid_coordinate_count), int(row.excluded_count))
                        expected_parking = self.points.loc[self.points.kind.eq('parking_site') & self.points.region_id.eq(region)]
                        pd.testing.assert_frame_equal(
                            points.loc[points.kind.eq('parking_site')].astype(expected_parking.dtypes.to_dict()).reset_index(drop=True),
                            expected_parking.reset_index(drop=True),
                        )
        with query_overlay(source='parking_standard'):
            points, coverage = points_and_coverage(kinds=('charger',))
            self.assertTrue(points.empty)
            self.assertEqual(int(coverage.total_count.sum()), 0)

    def test_representative_coordinate_comes_from_one_valid_charger(self):
        station = int(self.points.loc[self.points.charger_count.ge(3)].iloc[0].place_id)
        with self.engine.connect() as conn:
            ids = conn.execute(text('SELECT source_charger_id FROM charger WHERE station_id=:id ORDER BY source_charger_id LIMIT 3'), {'id': station}).scalars().all()
        changed = {'charger': {'columns': {
            'latitude': 'CASE WHEN station_id=:fixture_station THEN CASE source_charger_id WHEN :fixture_first THEN 0 WHEN :fixture_second THEN 37.6 WHEN :fixture_third THEN 37.5 END ELSE latitude END',
            'longitude': 'CASE WHEN station_id=:fixture_station THEN CASE source_charger_id WHEN :fixture_first THEN 0 WHEN :fixture_second THEN 127.0 WHEN :fixture_third THEN 127.1 END ELSE longitude END'}}}
        with query_overlay(changed, params=dict(zip(('fixture_station','fixture_first','fixture_second','fixture_third'), [station,*ids]))):
            points, _ = points_and_coverage(kinds=('charger',))
            row = points.loc[points.place_id.eq(station)].iloc[0]
            self.assertAlmostEqual(row.latitude,37.6)
            self.assertAlmostEqual(row.longitude,127.0)
            expected = self.points.loc[self.points.kind.eq('charging_station') & self.points.place_id.eq(station)].iloc[0]
            self.assertEqual(row.charger_count,expected.charger_count)

    def test_invalid_points_are_searchable_but_excluded_from_map(self):
        station = self.points.loc[self.points.kind.eq('charging_station')].iloc[0]
        changes = {'charger': {'columns': {name: 'CASE WHEN station_id=:fixture_station THEN 0 ELSE '+name+' END' for name in ('latitude','longitude')}}}
        with query_overlay(changes, params={'fixture_station': int(station.place_id)}):
            points, coverage = points_and_coverage()
            self.assertFalse((points.kind.eq('charging_station') & points.place_id.eq(station.place_id)).any())
            self.assertEqual(int(coverage.excluded_count.sum()), int(self.coverage.excluded_count.sum())+1)
            found = q.search_places(station.place_name, int(station.region_id), limit=100)
            row = found.loc[found.kind.eq('charging_station') & found.place_id.eq(station.place_id)].iloc[0]
            self.assertEqual(row.map_eligible,0)
            self.assertTrue(pd.isna(row.latitude) and pd.isna(row.longitude))

    def test_search_places_name_address_limit_and_parking_name_absence(self):
        station = self.points.loc[self.points.kind.eq('charging_station')].iloc[0]
        result = q.search_places(station.place_name,int(station.region_id))
        self.assertGreater(len(result),0)
        self.assertIn(int(station.place_id), result.loc[result.kind.eq('charging_station')].place_id.tolist())
        parking = self.points.loc[self.points.kind.eq('parking_site')].iloc[0]
        result = q.search_places(parking.source_parking_no,int(parking.region_id),limit=100)
        selected = result.loc[result.kind.eq('parking_site') & result.place_id.eq(parking.place_id)]
        self.assertEqual(len(selected),1)
        self.assertTrue(selected.place_name.isna().all())
        result = q.search_places(parking.address,int(parking.region_id),limit=100)
        self.assertIn(int(parking.place_id),result.loc[result.kind.eq('parking_site')].place_id.tolist())
        self.assertEqual(len(q.search_places('',limit=3)),3)
        self.assertTrue(q.search_places('',region_id=65000).empty)

    def test_search_special_characters_are_literal(self):
        station = int(self.points.loc[self.points.kind.eq('charging_station')].iloc[0].place_id)
        marker = "phase5!_%'\\"
        with query_overlay({'charging_station': {'columns': {'station_name': 'CASE WHEN station_id=:fixture_station THEN :fixture_name ELSE station_name END'}}}, params={'fixture_station':station,'fixture_name':marker}):
            result = q.search_places(marker)
            self.assertEqual(len(result),1)
            self.assertEqual(int(result.iloc[0].place_id),station)
            self.assertTrue(q.search_places("' OR 1=1 --").empty)

    def test_incomplete_default_source_is_hidden_without_fallback(self):
        with query_overlay(excluded_sources=('keco_ev_charger',)):
            points,coverage = points_and_coverage()
            self.assertFalse(points.kind.eq('charging_station').any())
            self.assertEqual(int(coverage.set_index('kind').loc['charging_station','total_count']),0)
            self.assertFalse(q.search_places('',limit=100).kind.eq('charging_station').any())

    def test_invalid_filters_fail_before_query(self):
        for kwargs in ({'kinds':'parking'}, {'kinds':('unknown',)}, {'region_id':True}, {'region_id':-1}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                q.get_place_points(**{'region_id':None, **kwargs})
        for kwargs in ({'keyword':None}, {'keyword':'a'*501}, {'keyword':'','limit':True}, {'keyword':'','limit':101}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                q.search_places(**kwargs)

    def test_two_region_comparison_preserves_full_city_percentiles(self):
        score = q.get_district_ranking(date(2026,9,1))
        self.assertEqual(len(score),25)
        comparison = q.get_compare_metrics(1,2,date(2026,9,1))
        self.assertEqual(len(comparison),2)
        self.assertTrue(comparison.score.between(0,100).all())
        pd.testing.assert_series_equal(comparison.set_index('region_id').score_raw,
            score.set_index('region_id').loc[[1,2]].score_raw,check_names=False)
