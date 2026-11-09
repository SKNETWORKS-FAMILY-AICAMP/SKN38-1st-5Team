from datetime import date
from decimal import Decimal
import unittest
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
from sqlalchemy import text

from db import queries as q
from db.connection import get_engine
from scoring import compute_score
from tests.query_support import clear_query_cache, query_overlay


class NumericFrameTest(unittest.TestCase):
    def test_large_integral_decimals_and_nullable_integers_are_exact(self):
        values = [Decimal(2**53+1), None, Decimal(2**63-1)]
        result = q._optimize_frame(pd.DataFrame({'vehicle_count':values},dtype=object))
        self.assertEqual(result.vehicle_count.dtype, pd.Int64Dtype())
        self.assertEqual(int(result.vehicle_count.iloc[0]),2**53+1)
        self.assertEqual(int(result.vehicle_count.iloc[2]),2**63-1)
        unsigned = q._optimize_frame(pd.DataFrame({'vehicle_count':[Decimal(2**64-1),None]},dtype=object))
        self.assertEqual(unsigned.vehicle_count.dtype,pd.UInt64Dtype())
        self.assertEqual(int(unsigned.vehicle_count.iloc[0]),2**64-1)
        larger = q._optimize_frame(pd.DataFrame({'vehicle_count':[Decimal(2**64+1),None]},dtype=object))
        self.assertEqual(larger.vehicle_count.iloc[0],2**64+1)

    def test_coordinates_ratios_and_long_text_preserve_values(self):
        frame = pd.DataFrame({
            'latitude':[Decimal('37.512345678912345')], 'longitude':[Decimal('127.123456789123456')],
            'vehicle_per_household':[Decimal('0.000049997500125')], 'district_name':['강남구'],
            'geometry_json':['{"type":"Polygon"}'], 'address':['긴 주소'*100],
            'answer_text':['긴 본문'*1000], 'source_charger_id':['01'], 'listed_count':[Decimal(10)]},dtype=object)
        result=q._optimize_frame(frame.copy())
        for column in ('latitude','longitude','vehicle_per_household'):
            self.assertEqual(result[column].dtype,np.dtype('float64'))
            self.assertEqual(result[column].iloc[0],float(frame[column].iloc[0]))
        self.assertIsInstance(result.district_name.dtype,pd.CategoricalDtype)
        for column in ('geometry_json','address','answer_text','source_charger_id'):
            self.assertFalse(isinstance(result[column].dtype,pd.CategoricalDtype))
            self.assertEqual(result[column].iloc[0],frame[column].iloc[0])
        self.assertEqual(result.listed_count.dtype,np.dtype('int8'))

    def test_connections_return_to_pool_on_failure(self):
        engine=MagicMock()
        engine.connect.return_value.__enter__.return_value.execute.side_effect=RuntimeError('query failed')
        with patch.object(q,'get_engine',return_value=engine),self.assertRaises(RuntimeError):
            q._read_query('SELECT region_id FROM region')
        engine.connect.return_value.__exit__.assert_called_once()


class QueryContractTest(unittest.TestCase):
    def test_engine_and_cached_results_are_reused_without_shared_frame_mutation(self):
        self.assertIs(get_engine(),get_engine())
        q.get_parking_summary.clear()
        with patch.object(q,'_read_query',wraps=q._read_query) as read:
            first=q.get_parking_summary([1])
            first.loc[:,'listed_row_count']=0
            second=q.get_parking_summary([1])
            self.assertEqual(read.call_count,1)
            self.assertGreater(int(second.iloc[0].listed_row_count),0)

    def test_three_levels_and_sql_rank_groups_cover_all_25_districts(self):
        rows=q.get_district_ranking()
        self.assertEqual(len(rows),25)
        for prefix,metric,labels in (
            ('ownership','vehicle_per_household',('많은 편','보통','적은 편')),
            ('parking','parking_space_per_vehicle',('좋음','보통','빠듯함')),
            ('need','transit_passenger_per_resident',('대중교통으로 충분','있으면 편함','차가 필요한 편'))):
            with self.subTest(prefix=prefix):
                self.assertTrue(rows[prefix+'_value'].notna().all())
                self.assertEqual(rows[prefix+'_level'].value_counts().to_dict(),dict(zip(labels,(8,9,8))))
                pd.testing.assert_series_equal(rows[prefix+'_rank'].astype(float),rows[metric].rank(method='min',ascending=False),check_names=False)
                np.testing.assert_array_equal(rows[prefix+'_value'],rows[metric])
        computed=compute_score(rows)
        np.testing.assert_allclose(rows.score_raw,computed.score_raw,rtol=0,atol=1e-12)
        np.testing.assert_array_equal(rows.score,computed.score)
        np.testing.assert_array_equal(rows.judgment,computed.judgment)

    def test_selected_card_and_comparison_keep_city_averages_and_ranks(self):
        ranking=q.get_district_ranking().set_index('region_id')
        for region in (1,25):
            row=q.get_summary_metrics(region).iloc[0]
            for prefix in ('ownership','parking','need'):
                self.assertEqual(row[prefix+'_rank'],ranking.loc[region,prefix+'_rank'])
                self.assertEqual(row[prefix+'_level'],ranking.loc[region,prefix+'_level'])
            self.assertAlmostEqual(row.vehicle_count_seoul_avg,ranking.vehicle_count.mean(),places=8)
            self.assertAlmostEqual(row.vehicle_count_vs_seoul,row.vehicle_count-ranking.vehicle_count.mean(),places=8)
        comparison=q.get_compare_metrics(25,1)
        self.assertEqual(comparison.region_id.tolist(),[25,1])
        self.assertEqual(len(q.get_compare_metrics(1,1)),1)

    def test_need_uses_only_weekday_total_and_exposes_partial_observation(self):
        rows=q.get_district_ranking().set_index('region_id')
        with get_engine().connect() as conn:
            totals=conn.execute(text("""SELECT region_id,SUM(known_passenger_sum) FROM transit_ridership_snapshot
                WHERE stat_date=:day AND mode_code='total' AND analysis_type='4' GROUP BY region_id"""),{'day':date(2026,10,30)}).all()
        for region,count in totals:
            self.assertEqual(rows.loc[region,'transit_passenger_count'],int(count))
            self.assertAlmostEqual(rows.loc[region,'need_value'],float(count)/int(rows.loc[region,'population']),places=12)
        self.assertTrue(rows.transit_observed_hour_count.eq(24).all())
        self.assertEqual(rows.loc[4,'transit_complete_hour_count'],0)
        self.assertEqual(rows.loc[4,'district_name'],'강서구')
        self.assertEqual(set(rows.need_stat_date),{date(2026,10,30)})

    def test_rank_ties_share_level_and_missing_values_have_no_rank(self):
        with query_overlay({'registration':{'columns':{'vehicle_count':"CASE WHEN fuel_scope_code='all' THEN 25 ELSE vehicle_count END"}},
                            'region_context':{'columns':{'household_count':'100'}}}):
            rows=q.get_district_ranking()
            self.assertTrue(rows.ownership_rank.eq(1).all())
            self.assertTrue(rows.ownership_level.eq('많은 편').all())
        with query_overlay({'region_context':{'where':'region_id<>1'}}):
            row=q.get_summary_metrics(1).iloc[0]
            self.assertEqual(row.ownership_level,'자료 없음')
            self.assertEqual(row.need_level,'자료 없음')
            self.assertTrue(pd.isna(row.ownership_rank) and pd.isna(row.need_rank))
        with query_overlay(excluded_sources=('parking_standard',)):
            rows=q.get_district_ranking()
            self.assertTrue(rows.parking_rank.isna().all())
            self.assertTrue(rows.parking_level.eq('자료 없음').all())

    def test_parking_capacity_missing_and_absent_categories_remain_distinct(self):
        rows=q.get_parking_summary()
        self.assertEqual(int(rows.unique_space_count.sum()),73068)
        self.assertTrue((rows.public_space_count+rows.private_space_count+rows.other_space_count).eq(rows.unique_space_count).all())
        with query_overlay({'parking_site':{'columns':{'parking_operation':"'공영'"}}}):
            public=q.get_parking_summary()
            self.assertTrue(public.private_space_count.eq(0).all())
            self.assertTrue(public.other_space_count.eq(0).all())
            self.assertEqual(int(public.public_space_count.sum()),73068)
        with query_overlay({'parking_site':{'columns':{'space_count':"CASE WHEN identifier_status='unique' AND parking_operation='공영' THEN NULL ELSE space_count END"}}}):
            missing=q.get_parking_summary()
            self.assertTrue(missing.loc[missing.public_missing_space_count.gt(0),'public_space_count'].isna().all())
        with query_overlay(excluded_sources=('parking_standard',)):
            missing=q.get_parking_summary()
            self.assertTrue(missing.public_space_count.isna().all())

    def test_latest_complete_snapshot_is_selected_without_combining_sources(self):
        columns={'source_code':"CASE WHEN source_code='seoul_charger' THEN 'keco_ev_charger' ELSE source_code END",
                 'collected_on':"CASE WHEN source_code='seoul_charger' THEN '2026-11-07' ELSE collected_on END"}
        with query_overlay({'source_snapshot':{'columns':columns}}):
            self.assertEqual(int(q.get_charger_summary().listed_count.sum()),429)
        columns={**columns,'is_complete':"CASE WHEN source_code='seoul_charger' THEN 0 ELSE is_complete END"}
        with query_overlay({'source_snapshot':{'columns':columns}}):
            self.assertEqual(int(q.get_charger_summary().listed_count.sum()),75607)

    def test_trend_dates_do_not_pretend_sources_observed_the_same_day(self):
        rows=q.get_trend_data(1)
        self.assertEqual(set(rows.loc[rows.series_type.eq('passenger')].stat_date),{date(2026,10,31)})
        self.assertEqual(set(rows.loc[rows.series_type.eq('traffic')].stat_date),{date(2026,9,30)})
        self.assertEqual(set(rows.hour_of_day),set(range(24)))
        october=q.get_trend_data(1,date(2026,10,30),'4')
        self.assertFalse(october.series_type.eq('traffic').any())
        self.assertEqual(len(october),72)
        self.assertTrue(q.get_trend_data(1,date(2027,1,1)).empty)
        self.assertTrue(q.get_registration_breakdown(1,date(2027,1,1)).empty)
