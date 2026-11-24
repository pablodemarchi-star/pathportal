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
        for key in ['package', 'shipment', 'logistics']:
            self.assertEqual(cells[key]['state'], 'na')
        self.assertFalse(rows[0]['recipient'])
        self.assertEqual(rows[1]['days'], 44)

    def test_format_views_have_distinct_columns_and_keep_navigation(self):
        from app.quality_control import processes_for_format
        for format_name in ('Online', 'Online at exam centre'):
            db.session.add(m.ExamSession(exam_session_name=format_name + ' QC row', category='Path School', status='Pending',
                session_date=date(2026, 12, 20), format=format_name, shifts='Morning', modules='Speaking'))
        db.session.commit()
        client = self.login_client_for_user(self.admin())
        default = client.get('/quality-control?session_year=2026').get_data(as_text=True)
        self.assertIn('value="Onsite"', default)
        self.assertNotIn('data-qc-sort="block_exam_records"', default)
        for format_name in ('Online', 'Online at exam centre', 'Onsite'):
            for tab in ('readiness', 'timing'):
                response = client.get('/quality-control', query_string=dict(session_year=2026, format=format_name, tab=tab))
                self.assertEqual(response.status_code, 200)
                html = response.get_data(as_text=True)
                self.assertLess(html.index('aria-label="Exam session format"'), html.index('aria-label="Quality control views"'))
                for key, _ in processes_for_format(format_name):
                    self.assertIn(f'data-qc-sort="block_{key}"', html)
                if format_name != 'Onsite':
                    for key in (('package', 'shipment', 'logistics') if format_name == 'Online' else ('package', 'shipment')):
                        self.assertNotIn(f'data-qc-sort="block_{key}"', html)
                    self.assertNotIn('June exam session', html)
                    self.assertIn('data-qc-sort-cell="exam_records"', html)
                self.assertIn('name="format" value="' + format_name + '"', html)
        self.assertEqual(client.get('/quality-control?format=Unknown').status_code, 400)

    def test_online_tower_completion_and_reopening_update_quality_and_clock(self):
        from app.exam_records import state, revision
        from app.routes import SINAPSIS_CHECKLIST_ITEMS
        self.session_record.format = 'Online'
        self.session_record.session_date = date(2026, 11, 12)
        self.session_record.monthly_registrations_closed = True
        self.session_record.date_confirmation_status = 'Confirmed'
        person = m.AcademicStaff(full_name='QC Examiner', status='Active', roles='Examiner')
        db.session.add(person); db.session.flush()
        db.session.add_all([
            m.ExamSessionExaminerAssignment(exam_session_id=self.session_record.id, team_member_id=person.id, participation_status='Confirmed'),
            m.ExamSessionScheduleWorkflow(exam_session_id=self.session_record.id, status='Approved'),
            m.ExamSessionStaffingControl(exam_session_id=self.session_record.id, schedule_notification_confirmed=True),
            m.ExamSessionFinanceControl(exam_session_id=self.session_record.id, status='Effective clearance', institutions_confirmed_with_admin=True),
        ])
        control = m.ExamSessionSinapsisControl(exam_session_id=self.session_record.id)
        db.session.add(control); db.session.flush()
        for item in SINAPSIS_CHECKLIST_ITEMS:
            db.session.add(m.ExamSessionSinapsisChecklistItem(sinapsis_control_id=control.id, item_key=item['key'], label=item['label'], is_checked=True))
        db.session.commit()
        setup = m.SpeakingRecordsSetup(exam_session_id=self.session_record.id, completed_steps=3, revision=revision(self.session_record))
        db.session.add_all([setup, m.ExamRecordsControl(exam_session_id=self.session_record.id, started=True),
            m.ExaminerSpeakingRecord(exam_session_id=self.session_record.id, person_ref=f'staff:{person.id}', file_id='qcFile', folder_id='qcFolder', filename='Speaking.xlsx', mime_type='application/octet-stream')])
        db.session.commit()
        tower = state(self.session_record)
        self.assertEqual(tower['status'], 'completed')
        row = load_rows([self.session_record], today=date(2026, 11, 6))[0]
        cells = {item['key']: item for item in row['cells']}
        self.assertTrue(cells['exam_records']['complete'])
        self.assertTrue(cells['finance']['applicable'])
        self.assertTrue(cells['attendance']['applicable'])
        self.assertNotIn('Return ', cells['final_checks']['detail'])
        self.assertEqual(cells['exam_records']['deadline'], date(2026, 11, 5))
        self.assertTrue(row['ready'])
        clock = m.ProcessClock.query.join(m.ProcessClockSession).filter(m.ProcessClockSession.exam_session_id == self.session_record.id, m.ProcessClockSession.block == 'exam_records', m.ProcessClockSession.is_current.is_(True)).one()
        self.assertEqual(clock.category, 'Completed')
        setup.completed_steps = 2; db.session.commit()
        self.assertNotEqual(clock.category, 'Completed')
        self.assertFalse(load_rows([self.session_record], today=date(2026, 11, 6))[0]['ready'])

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

    def test_finance_gate_uses_own_schedule_like_the_tower_for_concat_sessions(self):
        from app.routes import session_preparation_unlocked
        self.session_record.monthly_registrations_closed=True
        self.session_record.date_confirmation_status='Pending'
        peer=m.ExamSession(exam_session_name='Concatenated finance',category='Path School',status='Pending',
            session_date=self.session_record.session_date+timedelta(days=1),format='Onsite',shifts='Morning',modules='Speaking',
            monthly_registrations_closed=True,date_confirmation_status='Pending')
        db.session.add(peer);db.session.flush()
        peer.concat_session_ids=json.dumps([self.session_record.id])
        self.session_record.concat_session_ids=json.dumps([peer.id])
        workflow=m.ExamSessionScheduleWorkflow(exam_session_id=peer.id,status='In progress')
        db.session.add(workflow);db.session.commit()
        row=load_rows([peer],today=date(2026,11,7))[0]
        finance=next(c for c in row['cells'] if c['key']=='finance')
        self.assertTrue(session_preparation_unlocked(peer,workflow))
        self.assertTrue(finance['enabled'])
        self.assertNotEqual(finance['state'],'blocked')
        first_row=load_rows([self.session_record],today=date(2026,11,7))[0]
        first_finance=next(c for c in first_row['cells'] if c['key']=='finance')
        self.assertFalse(first_finance['enabled'])

    def test_operational_status_is_independent_from_timing_enablement(self):
        self.session_record.session_date=date(2026,12,20)
        self.session_record.monthly_registrations_closed=True
        self.session_record.date_confirmation_status='Confirmed'
        person=m.AcademicStaff(full_name='Available Supervisor',status='Active',roles='Supervisor')
        db.session.add(person);db.session.flush()
        db.session.add_all([
            m.ExamSessionSupervisorAssignment(exam_session_id=self.session_record.id,team_member_id=person.id,participation_status='Confirmed',is_shipment_recipient=True),
            m.ExamSessionStaffingControl(exam_session_id=self.session_record.id,schedule_notification_confirmed=True),
            m.ExamSessionScheduleWorkflow(exam_session_id=self.session_record.id,status='Approved',approved_at=datetime.now(timezone.utc))])
        db.session.commit()
        row=load_rows([self.session_record],today=date(2026,11,21))[0]
        cells={c['key']:c for c in row['cells']}
        self.assertEqual(cells['package']['availability'],'UNBLOCKED')
        self.assertEqual(cells['package']['operational_status'],'Not started yet')
        self.assertEqual(cells['final_checks']['availability'],'SEMI-UNBLOCKED')
        self.assertEqual(cells['final_checks']['operational_status'],'Not Started')
        self.assertTrue(row['timing_sources']['package']['begun'])
        self.assertTrue(row['timing_sources']['final_checks']['begun'])

    def test_package_partial_gate_matches_tower(self):
        from app.routes import package_gate_contract
        self.session_record.monthly_registrations_closed=True
        self.session_record.date_confirmation_status='Confirmed'
        db.session.add(m.ExamSessionScheduleWorkflow(exam_session_id=self.session_record.id,status='Approved',approved_at=datetime.now(timezone.utc)))
        db.session.commit()
        row=load_rows([self.session_record],today=date(2026,11,7))[0]
        package=next(c for c in row['cells'] if c['key']=='package')
        self.assertTrue(package['enabled'])
        self.assertEqual(package['availability'],package_gate_contract(True,False)['status'])
        self.assertEqual(package['availability'],'SEMI-UNBLOCKED')

    def test_shipment_uses_all_bundle_recipients_and_packages_even_across_years(self):
        person=m.AcademicStaff(full_name='Bundle recipient',status='Active',roles='Supervisor')
        db.session.add(person);db.session.flush()
        peer=m.ExamSession(exam_session_name='Next-year peer',category='Path School',status='Pending',session_date=date(2027,1,20),format='Onsite',shifts='Morning',modules='Speaking')
        db.session.add(peer);db.session.flush()
        assignments=[m.ExamSessionSupervisorAssignment(exam_session_id=record.id,team_member_id=person.id,participation_status=status,is_shipment_recipient=True)
            for record,status in [(self.session_record,'Confirmed'),(peer,'Pending')]]
        bundle=m.ExamSessionShipmentBundle(supervisor_staff_id=person.id,delivery_address='Test',status='Preparing bundle')
        db.session.add_all(assignments+[bundle]);db.session.flush()
        db.session.add_all([m.ExamSessionShipmentBundleSession(exam_session_id=record.id,bundle_id=bundle.id) for record in [self.session_record,peer]])
        db.session.commit()
        def shipment():
            rows=load_rows([self.session_record],today=date(2026,11,7))
            self.assertEqual(len(rows),1)
            return next(c for c in rows[0]['cells'] if c['key']=='shipment')
        self.assertEqual(shipment()['availability'],'BLOCKED')
        assignments[1].participation_status='Confirmed';db.session.commit()
        self.assertEqual(shipment()['availability'],'SEMI-UNBLOCKED')
        self.assertTrue(shipment()['enabled'])
        for record in [self.session_record,peer]:
            for field in ['package_label_verification_status','package_label_printing_status','room_package_sealing_status','return_packages_status','staff_member_ids_status','inclusion_final_items_status','session_box_sealing_status']:
                setattr(record,field,'completed')
        db.session.commit()
        self.assertEqual(shipment()['availability'],'UNBLOCKED')
        bundle.status='Delivered successfully'
        db.session.commit()
        delivered=shipment()
        self.assertTrue(delivered['complete'])
        self.assertEqual(delivered['state'],'complete')
        row=load_rows([self.session_record],today=date(2026,11,7))[0]
        self.assertFalse(row['timing_sources']['shipment']['waiting'])
        bundle.status='Recipient review successful'
        db.session.commit()
        self.assertTrue(shipment()['complete'])

    def test_confirmed_staff_with_pending_institution_notification_is_explicit(self):
        person=m.AcademicStaff(full_name='Confirmed member',status='Active',roles='Supervisor')
        db.session.add(person);db.session.flush()
        self.session_record.monthly_registrations_closed=True;self.session_record.date_confirmation_status='Confirmed'
        db.session.add(m.ExamSessionSupervisorAssignment(exam_session_id=self.session_record.id,team_member_id=person.id,participation_status='Confirmed'))
        db.session.commit()
        row=load_rows([self.session_record],today=date(2026,11,7))[0]
        staff=next(c for c in row['cells'] if c['key']=='staffing')
        self.assertEqual(staff['label'],'1/1 confirmed')
        self.assertEqual(staff['operational_status'],'Awaiting institution notification')
        self.assertEqual(staff['operational_note'],'Institution notification pending')
        self.assertFalse(staff['complete'])

    def test_all_columns_offer_header_and_dropdown_sorting_in_both_tabs(self):
        from app.quality_control import processes_for_format
        client=self.login_client_for_user(self.admin())
        for tab in ['readiness','timing']:
            response=client.get('/quality-control?tab='+tab+'&sort=block_final_checks_desc')
            self.assertEqual(response.status_code,200)
            html=response.get_data(as_text=True)
            self.assertIn('data-qc-sort="name"',html)
            for key,label in processes_for_format('Onsite'):
                self.assertIn(f'data-qc-sort="block_{key}"',html)
                self.assertIn(f'value="block_{key}_desc"',html)
                self.assertIn(f'data-qc-sort-cell="{key}"',html)
            if tab=='timing':
                self.assertLess(html.index('js/process_timing.js'),html.index('js/quality_control.js'))
