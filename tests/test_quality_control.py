import json
import unittest
from datetime import date, datetime, timedelta, timezone
from sqlalchemy import event
from tests import test_schedule_workflow as fixtures
from app import db
from app import models as m
from app.quality_control import cell, observe, timing_view, load_rows


class QualityControlTest(unittest.TestCase):
    setUp = fixtures.ScheduleWorkflowTest.setUp
    tearDown = fixtures.ScheduleWorkflowTest.tearDown
    login_client_for_user = fixtures.ScheduleWorkflowTest.login_client_for_user

    def admin(self, superadmin=True):
        user = m.User(full_name='Quality Admin', email='quality@example.com', department='Management',
                      is_active=True, is_superadmin=superadmin)
        user.set_password('test-password')
        db.session.add(user); db.session.commit()
        return user

    def test_superadmin_only_and_menu_visibility(self):
        user = self.admin(False)
        client = self.login_client_for_user(user)
        self.assertEqual(client.get('/quality-control').status_code, 403)
        user.is_superadmin = True; db.session.commit()
        response = client.get('/quality-control')
        self.assertEqual(response.status_code, 200)
        self.assertIn('Quality control', response.get_data(as_text=True))
        self.assertIn('June exam session', response.get_data(as_text=True))
        self.assertEqual(response.headers['Cache-Control'], 'no-store')

    def test_rows_formats_and_no_external_data(self):
        online = m.ExamSession(exam_session_name='Online session', category='Path School', status='Pending',
            session_date=date(2026,12,20), format='Online', shifts='Morning', modules='Speaking')
        db.session.add(online); db.session.commit()
        rows = load_rows([self.session_record, online], today=date(2026,11,6))
        self.assertEqual(len(rows), 2)
        cells = {c['key']: c for c in rows[1]['cells']}
        for key in ['package', 'shipment', 'logistics', 'finance', 'final_checks']:
            self.assertEqual(cells[key]['state'], 'na')
        self.assertFalse(rows[0]['recipient'])
        self.assertEqual(rows[1]['days'], 44)

    def test_palette_precedence_and_near_complete_rule(self):
        today = date(2026,11,6)
        self.assertEqual(cell('x','x',today=today)['state'], 'pending')
        self.assertEqual(cell('x','x',today=today, near=True, active=True)['state'], 'near')
        self.assertEqual(cell('x','x',today=today, near=True, deadline=today-timedelta(days=1))['state'], 'issue')
        self.assertEqual(cell('x','x',today=today, enabled=False, issue=True)['state'], 'blocked')
        self.assertEqual(cell('x','x',today=today, applicable=False, issue=True)['state'], 'na')

    def test_real_transitions_durations_reopenings_and_rollback(self):
        # Use one isolated process to test exact transitions without production hooks.
        self.app.config['QUALITY_CONTROL_TRACKING_READY'] = False
        m.QualityProcessTiming.query.delete(); db.session.commit()
        start = datetime(2026,11,6,tzinfo=timezone.utc)
        def snapshot(**kwargs):
            return [{'session':self.session_record,'cells':[cell('date','Test',today=start.date(),**kwargs)]}]
        observe(snapshot(enabled=False), now=start); db.session.commit()
        observe(snapshot(), now=start+timedelta(days=1)); db.session.commit()
        observe(snapshot(active=True), now=start+timedelta(days=3)); db.session.commit()
        saved = observe(snapshot(active=True,complete=True), now=start+timedelta(days=6)); db.session.commit()
        metric = saved[self.session_record.id,'date']; data = timing_view(metric)
        self.assertEqual(data['elapsed'], 5)
        self.assertEqual(data['wait'], 2)
        self.assertEqual(data['duration'], 3)
        observe(snapshot(active=True), now=start+timedelta(days=7)); db.session.commit()
        self.assertEqual(metric.reopenings, 1)
        self.assertIsNone(metric.completed_at)
        observe(snapshot(active=True,complete=True), now=start+timedelta(days=8)); db.session.rollback()
        self.assertIsNone(metric.completed_at)

    def test_existing_completed_baseline_does_not_invent_duration(self):
        self.app.config['QUALITY_CONTROL_TRACKING_READY'] = False
        m.QualityProcessTiming.query.delete(); db.session.commit()
        saved = observe([{'session':self.session_record,'cells':[cell('date','Confirmed',today=date(2026,11,6),complete=True)]}])
        result = timing_view(saved[self.session_record.id,'date'])
        self.assertIsNone(result['elapsed'])
        self.assertIsNone(result['enabled_at'])

    def test_committed_source_changes_record_completion_without_dashboard_visit(self):
        self.session_record.date_confirmation_status = 'Confirmed'; db.session.commit()
        metric = m.ProcessClock.query.join(m.ProcessClockSession).filter(m.ProcessClockSession.exam_session_id==self.session_record.id,m.ProcessClock.block=='date').one()
        self.assertEqual(metric.category, 'Completed')
        self.assertIsNotNone(metric.completed_at)
        self.session_record.date_confirmation_status = 'Pending'; db.session.commit()
        self.assertEqual(metric.reopenings,1)

    def test_query_count_does_not_grow_per_session(self):
        self.app.config['QUALITY_CONTROL_TRACKING_READY'] = False
        for n in range(12):
            db.session.add(m.ExamSession(exam_session_name=f'Session {n}', category='Path School',status='Pending',
                session_date=date(2026,12,20),format='Online',shifts='Morning',modules='Speaking'))
        db.session.commit()
        records = m.ExamSession.query.filter_by(format='Online').all()
        def count_for(records):
            counter=[]
            def counted(*args): counter.append(1)
            event.listen(db.engine,'before_cursor_execute',counted)
            try: load_rows(records, today=date(2026,11,6))
            finally: event.remove(db.engine,'before_cursor_execute',counted)
            return len(counter)
        one = count_for(records[:1]); many = count_for(records)
        self.assertLessEqual(many, one+3)

    def test_onsite_reuses_batch_cache_without_per_session_queries(self):
        self.app.config['QUALITY_CONTROL_TRACKING_READY'] = False
        for n in range(12):
            db.session.add(m.ExamSession(exam_session_name=f'Onsite {n}',category='Path School',status='Pending',
                session_date=date(2026,12,20),format='Onsite',shifts='Morning',modules='Speaking'))
        db.session.commit()
        records = m.ExamSession.query.filter(m.ExamSession.exam_session_name.like('Onsite %')).all()
        def count_for(records):
            counter=[]
            def counted(*args): counter.append(1)
            event.listen(db.engine,'before_cursor_execute',counted)
            try: load_rows(records,today=date(2026,11,6))
            finally: event.remove(db.engine,'before_cursor_execute',counted)
            return len(counter)
        self.assertLessEqual(count_for(records), count_for(records[:1])+3)

    def test_shared_schedule_matches_primary_and_sessions_stay_separate(self):
        peer=m.ExamSession(exam_session_name='Online peer',category='Path School',status='Pending',
            session_date=self.session_record.session_date+timedelta(days=1),format='Online',shifts='Morning',modules='Speaking')
        db.session.add(peer);db.session.flush()
        self.session_record.concat_session_ids=json.dumps([peer.id])
        peer.concat_session_ids=json.dumps([self.session_record.id])
        db.session.add(m.ExamSessionScheduleWorkflow(exam_session_id=self.session_record.id,status='Approved',approved_at=datetime.now(timezone.utc)))
        db.session.commit()
        rows=load_rows([self.session_record,peer],today=date(2026,11,6))
        self.assertEqual(len(rows),2)
        schedule=next(c for c in rows[1]['cells'] if c['key']=='schedule')
        self.assertTrue(schedule['complete'])
        self.assertIn('Shared schedule',schedule['detail'])

    def test_source_write_rollback_does_not_record_false_completion(self):
        self.session_record.date_confirmation_status='Confirmed';db.session.flush();db.session.rollback()
        metric=m.ProcessClock.query.join(m.ProcessClockSession).filter(m.ProcessClockSession.exam_session_id==self.session_record.id,m.ProcessClock.block=='date').one()
        self.assertEqual(metric.category,'Path time')
        self.assertIsNone(metric.completed_at)

    def test_registrations_use_latest_month_not_sum_of_months(self):
        db.session.add_all([m.ExamSessionMonthlyCandidateTotal(exam_session_id=self.session_record.id,month=1,total_candidates=10),
                            m.ExamSessionMonthlyCandidateTotal(exam_session_id=self.session_record.id,month=2,total_candidates=20)])
        db.session.commit()
        result=load_rows([self.session_record],today=date(2026,11,6))[0]
        detail=next(c['detail'] for c in result['cells'] if c['key']=='registrations')
        self.assertIn('20/30 candidates',detail)
        self.assertNotIn('30/30',detail)
