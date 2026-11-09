from datetime import date
import unittest

from sqlalchemy import text

from db.connection import get_engine
from db import queries as q
from tests.query_support import query_overlay


class QueryIntegrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = get_engine()
        if len(q.get_filter_options()['regions']) != 25:
            raise ValueError('서울 25구 DB가 필요합니다.')

    def test_literal_faq_search(self):
        original = q.search_faq()
        for keyword in ("%", "_", "!", "\\", "' OR 1=1 --"):
            expected = original.question.str.contains(keyword, regex=False) | original.answer_text.str.contains(keyword, regex=False)
            self.assertEqual(len(q.search_faq(keyword)), int(expected.sum()))

    def test_empty_and_multiple_region_filter(self):
        ids = q.get_filter_options()['regions'].region_id.iloc[:2].tolist()
        self.assertEqual(sum(q.get_registration_breakdown(region,date(2026,9,1)).fuel_scope_code.eq('all').sum() for region in ids),8)
        self.assertEqual(len(q.get_parking_summary(ids)),2)
        self.assertTrue(q.get_parking_summary([]).empty)
        self.assertTrue(q.get_charger_summary([]).empty)

    def test_speed_filter_restriction_uses_same_rows(self):
        with query_overlay(source='seoul_charger'):
            for speed in ('all','fast','slow','unknown'):
                detail = q.get_charger_detail(None,speed=speed,limit=None)
                summary = q.get_charger_summary(speed=speed)
                self.assertEqual(len(detail),int(summary.listed_count.sum()))
                self.assertEqual(int(detail.restriction_note.notna().sum()),int(summary.restriction_noted_count.sum()))

    def test_incomplete_snapshot_is_hidden(self):
        with query_overlay(excluded_sources=('seoul_charger',),source='seoul_charger'):
            self.assertTrue(q.get_charger_summary().listed_count.isna().all())

    def test_missing_vehicle_type_hides_ratio(self):
        region = int(q.get_filter_options()['regions'].iloc[0].region_id)
        changes = {'registration': {'where': "NOT (region_id=:fixture_region AND fuel_scope_code='electric' AND vehicle_type_code='passenger')"}}
        with query_overlay(changes,params={'fixture_region':region}):
            result = q.get_summary_metrics(region,date(2026,9,1))
            self.assertTrue(result.electric_count.isna().all())
            self.assertTrue(result.electric_share_pct.isna().all())

    def test_check_and_fk_reject_invalid_insert(self):
        # DB 데이터를 바꾸지 않도록 INSERT 없이 제약 메타데이터를 조회한다.
        with self.engine.connect() as conn:
            foreign_keys = conn.execute(text("""SELECT column_name, referenced_table_name FROM information_schema.key_column_usage
                WHERE table_schema=DATABASE() AND table_name='registration' AND referenced_table_name IS NOT NULL""")).all()
            checks = conn.execute(text("""SELECT cc.check_clause, tc.enforced FROM information_schema.check_constraints cc
                JOIN information_schema.table_constraints tc ON tc.constraint_schema=cc.constraint_schema AND tc.constraint_name=cc.constraint_name
                WHERE tc.table_schema=DATABASE() AND tc.table_name='registration' AND tc.constraint_type='CHECK'""")).all()
            count_type = conn.execute(text("""SELECT column_type FROM information_schema.columns WHERE table_schema=DATABASE()
                AND table_name='registration' AND column_name='vehicle_count'""")).scalar_one()
            missing_region = conn.execute(text('SELECT COUNT(*) FROM region WHERE region_id=65000')).scalar_one()
        self.assertIn(('region_id','region'),foreign_keys)
        self.assertEqual(missing_region,0)
        self.assertTrue(any('dayofmonth' in clause.lower() and '1' in clause and enforced=='YES' for clause,enforced in checks))
        self.assertIn('unsigned',count_type)
        rows = q.get_registration_breakdown(None,date(2026,9,1))
        self.assertEqual(int(rows.loc[rows.fuel_scope_code.eq('all')].vehicle_count.sum()),3150351)

    def test_partial_parking_sum_cannot_become_score(self):
        for status in ('unique','conflict'):
            with self.engine.connect() as conn:
                row = conn.execute(text('SELECT MIN(parking_row_id) FROM parking_site WHERE identifier_status=:status'),{'status':status}).scalar_one()
            with self.subTest(status=status), query_overlay({'parking_site': {'columns': {'space_count': 'CASE WHEN parking_row_id=:fixture_row THEN NULL ELSE space_count END'}}},params={'fixture_row':row}):
                result = q.get_district_ranking(date(2026,9,1))
                if status=='unique':
                    self.assertTrue(result.score.isna().all())
                    self.assertTrue(result.judgment.eq('자료 부족').all())
                else:
                    self.assertTrue(result.score.notna().all())

    def test_electric_greater_than_total_invalidates_score(self):
        region = int(q.get_filter_options()['regions'].iloc[0].region_id)
        changes = {'registration': {'columns': {'vehicle_count': "CASE WHEN region_id=:fixture_region AND fuel_scope_code='electric' AND vehicle_type_code='passenger' THEN 100000000 ELSE vehicle_count END"}}}
        with query_overlay(changes,params={'fixture_region':region}):
            self.assertTrue(q.get_district_ranking(date(2026,9,1)).score.isna().all())
