import json
import unittest
from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch
from app import db
from app import models as m
from app.quality_control import cell, load_rows
from app.process_timing import (transition, totals, choose_category, reconcile_rows, clock_data,
                               cohort_medians, initialize_process_timing, reconcile_due)
from tests import test_schedule_workflow as fixtures


class ProcessTimingTest(unittest.TestCase):
    setUp=fixtures.ScheduleWorkflowTest.setUp
    tearDown=fixtures.ScheduleWorkflowTest.tearDown
    login_client_for_user=fixtures.ScheduleWorkflowTest.login_client_for_user

    def new_clock(self):
        self.app.config['QUALITY_CONTROL_TRACKING_READY']=False
        start=datetime(2026,11,7,12,tzinfo=timezone.utc)
        clock=m.ProcessClock(owner_key='test:intervals',block='staffing',category='Blocked',tracked_from=start,
            coverage_complete=True,path_seconds=0,external_seconds=0,incident_seconds=0,revision=0,reopenings=0)
        db.session.add(clock);db.session.flush()
        return clock,start

    def move(self,clock,category,at,**kwargs):
        opened=m.ProcessInterval.query.filter_by(clock_id=clock.id,ended_at=None).first()
        transition(clock,category,at,interval=opened,**kwargs);db.session.flush()

    def date_clock(self):
        return m.ProcessClock.query.join(m.ProcessClockSession).filter(m.ProcessClockSession.exam_session_id==self.session_record.id,m.ProcessClock.block=='date').one()

    def admin(self):
        user=m.User(full_name='Timing Admin',email='timing@example.com',department='Management',is_active=True,is_superadmin=True)
        user.set_password('test');db.session.add(user);db.session.commit()
        return self.login_client_for_user(user)

    def test_blocked_time_is_excluded(self):
        clock,start=self.new_clock()
        self.move(clock,'Blocked',start)
        self.move(clock,'Path time',start+timedelta(days=5))
        self.move(clock,'Completed',start+timedelta(days=8))
        result=totals(clock,now=start+timedelta(days=20))
        self.assertEqual(result['total'],3*86400)
        self.assertEqual(result['path'],result['total'])

    def test_external_wait_and_reopening_exclude_completed_gap(self):
        clock,start=self.new_clock()
        for days,category in [(0,'Path time'),(2,'Waiting external'),(9,'Path time'),(10,'Completed'),(15,'Path time'),(17,'Completed')]:
            self.move(clock,category,start+timedelta(days=days))
        result=totals(clock)
        self.assertEqual(result['total'],12*86400)
        self.assertEqual(result['path'],5*86400)
        self.assertEqual(result['external'],7*86400)
        self.assertEqual(clock.reopenings,1)
        self.assertEqual(m.ProcessInterval.query.filter_by(clock_id=clock.id,ended_at=None).count(),1)

    def test_overlapping_incidents_do_not_double_count(self):
        clock,start=self.new_clock()
        self.move(clock,'Path time',start)
        self.move(clock,'Incident time',start+timedelta(days=4),incident_ids=[10])
        self.move(clock,'Incident time',start+timedelta(days=5),incident_ids=[10,11])
        self.move(clock,'Path time',start+timedelta(days=6))
        self.move(clock,'Completed',start+timedelta(days=7))
        result=totals(clock)
        self.assertEqual(result['incident'],2*86400)
        self.assertEqual(result['path'],5*86400)
        self.assertEqual(result['total'],sum(result[key] for key in ['path','external','incident']))

    def test_priority_and_terminal_states(self):
        c=cell('x','x',today=date(2026,11,7));source={'begun':True,'waiting':True,'reason':'Staff member'}
        self.assertEqual(choose_category(c,source,'Provider',[1])[0],'Incident time')
        self.assertEqual(choose_category(c,source,'Provider',[])[0],'Waiting external')
        c['enabled']=False
        self.assertEqual(choose_category(c,source,'Provider',[1])[0],'Blocked')
        c['complete']=True
        self.assertEqual(choose_category(c,source,'Provider',[1])[0],'Completed')
        c['applicable']=False
        self.assertEqual(choose_category(c,source,'Provider',[1])[0],'N/A')

    def test_na_never_creates_intervals(self):
        clock,start=self.new_clock()
        self.move(clock,'N/A',start)
        self.assertEqual(m.ProcessInterval.query.filter_by(clock_id=clock.id).count(),0)
        self.assertEqual(totals(clock)['total'],0)

    def test_live_and_timing_tabs_render_without_legacy_time(self):
        client=self.admin()
        response=client.get('/quality-control')
        self.assertEqual(response.status_code,200)
        html=response.get_data(as_text=True)
        self.assertIn('Live readiness',html);self.assertIn('Process timing',html)
        self.assertNotIn('data-timing=',html);self.assertNotIn('id="qc-times"',html)
        timed=client.get('/quality-control?tab=timing')
        self.assertEqual(timed.status_code,200)
        self.assertIn('By process',timed.get_data(as_text=True))
        self.assertIn('data-qc-timing',timed.get_data(as_text=True))

    def test_manual_wait_requires_superadmin_csrf_reason_and_revision(self):
        client=self.admin();clock=self.date_clock()
        url=f'/quality-control/process-timing/{clock.id}/waiting'
        self.assertEqual(client.post(url,data={'action':'wait','reason':'Institution'}).status_code,400)
        revision=clock.revision
        self.assertEqual(client.post(url,data={'csrf_token':'token','action':'wait','reason':'Other','revision':revision}).status_code,400)
        result=client.post(url,data={'csrf_token':'token','action':'wait','reason':'Institution','revision':revision})
        self.assertEqual(result.status_code,200,result.get_data(as_text=True))
        self.assertEqual(result.json['category'],'Waiting external')
        self.assertEqual(self.session_record.date_confirmation_status,'Pending')
        self.assertEqual(client.post(url,data={'csrf_token':'token','action':'resume','revision':revision}).status_code,409)
        result=client.post(url,data={'csrf_token':'token','action':'resume','revision':result.json['revision']})
        self.assertEqual(result.status_code,200)
        self.assertEqual(result.json['category'],'Path time')
        self.assertEqual(self.session_record.date_confirmation_status,'Pending')
        user=m.User.query.filter_by(email='timing@example.com').one();user.is_superadmin=False;db.session.commit()
        self.assertEqual(client.get(f'/quality-control/process-timing/{clock.id}').status_code,403)

    def test_missing_historical_intervals_are_not_invented(self):
        self.app.config['QUALITY_CONTROL_TRACKING_READY']=False
        m.ProcessInterval.query.delete();m.ProcessClockSession.query.delete();m.ProcessClock.query.delete();db.session.commit()
        initialize_process_timing()
        clock=self.date_clock()
        self.assertFalse(clock.coverage_complete)
        self.assertLess(totals(clock,m.ProcessInterval.query.filter_by(clock_id=clock.id,ended_at=None).first())['total'],10)

    def test_automatic_wait_has_no_override_by_resume(self):
        clock,start=self.new_clock();c=cell('staffing','Sent',today=start.date())
        source={'begun':True,'waiting':True,'reason':'Staff member'}
        self.assertEqual(choose_category(c,source,None)[0],'Waiting external')
        source['waiting']=False
        self.assertEqual(choose_category(c,source,None)[0],'Path time')

    def test_medians_deduplicate_shared_processes(self):
        a={'id':1,'category':'Completed','coverage_complete':True,'totals':{'total':10,'path':4,'external':4,'incident':2}}
        b={'id':2,'category':'Completed','coverage_complete':True,'totals':{'total':20,'path':10,'external':8,'incident':2}}
        result,count=cohort_medians([a,a,a,b,dict(b,id=3,coverage_complete=False)])
        self.assertEqual(count,2);self.assertEqual(result['total'],15)

    def test_rollback_restores_interval_and_counter(self):
        clock,start=self.new_clock();self.move(clock,'Path time',start);db.session.commit()
        self.move(clock,'Completed',start+timedelta(days=2));db.session.rollback()
        self.assertEqual(clock.category,'Path time');self.assertEqual(clock.path_seconds,0)
        self.assertIsNone(m.ProcessInterval.query.filter_by(clock_id=clock.id).one().ended_at)

    def setup_staffing(self, status='Official confirmation sent', record=None):
        record=record or self.session_record
        record.monthly_registrations_closed=True;record.date_confirmation_status='Confirmed'
        person=m.AcademicStaff(full_name='Timing Supervisor',status='Active',roles='Supervisor')
        db.session.add(person);db.session.flush()
        control=m.ExamSessionStaffingControl(exam_session_id=record.id,schedule_notification_confirmed=True)
        assignment=m.ExamSessionSupervisorAssignment(exam_session_id=record.id,team_member_id=person.id,
            participation_status=status,is_shipment_recipient=True)
        db.session.add_all([control,assignment,m.ExamSessionScheduleWorkflow(exam_session_id=record.id,status='Approved',approved_at=datetime.now(timezone.utc))])
        db.session.commit()
        return person,assignment

    def block_clock(self,block,record=None):
        record=record or self.session_record
        return m.ProcessClock.query.join(m.ProcessClockSession).filter(m.ProcessClockSession.exam_session_id==record.id,
            m.ProcessClockSession.block==block,m.ProcessClockSession.is_current.is_(True)).one()

    def test_staffing_waits_only_when_no_internal_action_is_pending(self):
        person,supervisor=self.setup_staffing()
        self.assertEqual(self.block_clock('staffing').category,'Waiting external')
        missing=m.ExamSessionExaminerAssignment(exam_session_id=self.session_record.id,participation_status='Pending')
        db.session.add(missing);db.session.commit()
        self.assertEqual(self.block_clock('staffing').category,'Path time')
        examiner=m.AcademicStaff(full_name='Timing Examiner',status='Active',roles='Examiner')
        db.session.add(examiner);db.session.flush()
        missing.team_member_id=examiner.id;missing.participation_status='Confirmed';db.session.commit()
        self.assertEqual(self.block_clock('staffing').category,'Waiting external')
        supervisor.participation_status='Declined';db.session.commit()
        self.assertEqual(self.block_clock('staffing').category,'Path time')
        supervisor.participation_status='Confirmed';db.session.commit()
        self.assertEqual(self.block_clock('staffing').category,'Completed')

    def test_bundle_shared_clock_incident_priority_and_automatic_resume(self):
        person,assignment=self.setup_staffing('Confirmed')
        peer=m.ExamSession(exam_session_name='Shared bundle session',category='Path School',status='Pending',
            session_date=self.session_record.session_date+timedelta(days=1),format='Onsite',shifts='Morning',modules='Speaking',monthly_registrations_closed=True,date_confirmation_status='Confirmed')
        db.session.add(peer);db.session.flush()
        db.session.add_all([m.ExamSessionSupervisorAssignment(exam_session_id=peer.id,team_member_id=person.id,participation_status='Confirmed',is_shipment_recipient=True),m.ExamSessionStaffingControl(exam_session_id=peer.id,schedule_notification_confirmed=True)])
        bundle=m.ExamSessionShipmentBundle(supervisor_staff_id=person.id,delivery_address='Test address',status='Preparing bundle')
        db.session.add(bundle);db.session.flush()
        db.session.add_all([m.ExamSessionShipmentBundleSession(bundle_id=bundle.id,exam_session_id=record.id) for record in [self.session_record,peer]])
        db.session.commit()
        clock=self.block_clock('shipment')
        self.assertEqual(clock.id,self.block_clock('shipment',peer).id)
        self.assertTrue(clock.coverage_complete)
        bundle.status='Dispatched';db.session.commit()
        self.assertEqual(clock.category,'Waiting external')
        incident=m.ExamSessionIncident(exam_session_id=peer.id,incident_type='Other',title='Courier issue',severity='Low',status='Open',responsible_department='LOGISTICS')
        db.session.add(incident);db.session.commit()
        self.assertEqual(clock.category,'Waiting external')
        incident.affected_block='shipment';db.session.commit()
        self.assertEqual(clock.category,'Incident time')
        another=m.ExamSessionIncident(exam_session_id=self.session_record.id,incident_type='Other',title='Second issue',severity='Low',status='Waiting external',responsible_department='LOGISTICS',affected_block='shipment')
        db.session.add(another);db.session.commit()
        self.assertEqual(clock.category,'Incident time')
        incident.status='Resolved';db.session.commit()
        self.assertEqual(clock.category,'Incident time')
        another.status='Cancelled';db.session.commit()
        self.assertEqual(clock.category,'Waiting external')
        bundle.status='Delivered successfully';db.session.commit()
        self.assertEqual(clock.category,'Completed')
        opened=m.ProcessInterval.query.filter_by(clock_id=clock.id,ended_at=None).one()
        self.assertNotEqual(opened.reason,'Recipient')
        bundle.status='Recipient review successful';db.session.commit()
        self.assertEqual(clock.category,'Completed')

    def test_calendar_job_opens_at_midnight_even_without_any_page_view(self):
        self.session_record.session_date=date(2026,12,20)
        self.setup_staffing('Confirmed')
        clock=self.block_clock('final_checks')
        self.assertEqual(clock.category,'Blocked')
        now=datetime(2026,11,21,9,30,tzinfo=timezone.utc)
        self.assertGreater(reconcile_due(now=now),0)
        self.assertEqual(clock.category,'Path time')
        self.assertEqual(clock.started_at.replace(tzinfo=timezone.utc),datetime(2026,11,21,3,tzinfo=timezone.utc))
        opened=m.ProcessInterval.query.filter_by(clock_id=clock.id,ended_at=None).one()
        self.assertEqual(totals(clock,opened,now)['path'],6.5*3600)

    def test_incident_after_calendar_opening_is_not_backdated(self):
        self.session_record.session_date=date(2026,12,20)
        self.setup_staffing('Confirmed')
        clock=self.block_clock('final_checks')
        self.app.config['QUALITY_CONTROL_TRACKING_READY']=False
        incident=m.ExamSessionIncident(exam_session_id=self.session_record.id,incident_type='Other',title='New morning issue',severity='Low',status='Open',responsible_department='ADMIN',affected_block='final_checks',created_at=datetime(2026,11,21,7,tzinfo=timezone.utc))
        db.session.add(incident);db.session.commit()
        now=datetime(2026,11,21,7,tzinfo=timezone.utc)
        reconcile_rows(load_rows([self.session_record],today=now.date()),now=now);db.session.commit()
        self.assertEqual(clock.category,'Incident time')
        opened=m.ProcessInterval.query.filter_by(clock_id=clock.id,ended_at=None).one()
        result=totals(clock,opened,now+timedelta(hours=2))
        self.assertEqual(result['path'],4*3600)
        self.assertEqual(result['incident'],2*3600)

    def test_detail_is_private_and_history_is_loaded_on_demand(self):
        client=self.admin();clock=self.date_clock()
        response=client.get(f'/quality-control/process-timing/{clock.id}')
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.headers['Cache-Control'],'no-store')
        self.assertIn('history',response.json)
        self.assertIn('created_by',response.json['history'][0])
        page=client.get('/quality-control?tab=timing').get_data(as_text=True)
        self.assertNotIn('"history":',page)

    def test_incident_migration_is_additive_and_idempotent(self):
        from app.schema_migrations import migrate_process_timing
        from sqlalchemy import inspect
        migrate_process_timing();migrate_process_timing()
        columns={column['name'] for column in inspect(db.engine).get_columns('exam_session_incident')}
        self.assertIn('affected_block',columns)

    def test_job_rejects_unauthenticated_call(self):
        client=self.app.test_client()
        with patch.dict('os.environ',{'QUALITY_TIMING_JOB_TOKEN':'a'*40}):
            self.assertEqual(client.post('/internal/jobs/process-timing').status_code,403)
            self.assertEqual(client.post('/internal/jobs/process-timing',headers={'Authorization':'Bearer '+'a'*40}).status_code,200)

    def test_bulk_updates_are_captured_without_opening_quality_control(self):
        clock=self.date_clock()
        m.ExamSession.query.filter_by(id=self.session_record.id).update({'date_confirmation_status':'Confirmed'},synchronize_session=False)
        db.session.commit()
        self.assertEqual(clock.category,'Completed')
        self.assertIsNotNone(clock.completed_at)

    def test_deleted_session_stops_its_clock_but_keeps_intervals(self):
        clock=self.date_clock();cid=clock.id
        db.session.delete(self.session_record);db.session.commit()
        clock=db.session.get(m.ProcessClock,cid)
        self.assertEqual(clock.category,'N/A')
        self.assertEqual(m.ProcessInterval.query.filter_by(clock_id=cid,ended_at=None).count(),0)
        self.assertGreater(m.ProcessInterval.query.filter_by(clock_id=cid).count(),0)

    def test_incident_form_saves_and_validates_affected_block(self):
        client=self.admin();sid=self.session_record.id
        url=f'/pre-session-control-tower/sessions/{sid}/incidents'
        result=client.post(url,data={'csrf_token':'token','incident_type':'Other','title':'Scope test','severity':'Low',
            'responsible_department':'ADMIN','affected_block':'date','view':'sessions'})
        self.assertEqual(result.status_code,302)
        incident=m.ExamSessionIncident.query.filter_by(title='Scope test').one()
        self.assertEqual(incident.affected_block,'date')
        self.assertEqual(self.date_clock().category,'Incident time')
        result=client.post(url+f'/{incident.id}',data={'csrf_token':'token','incident_status':'In progress','severity':'Low',
            'responsible_department':'ADMIN','affected_block':'general','note':'Update scope','view':'sessions'})
        self.assertEqual(result.status_code,302)
        self.assertEqual(incident.affected_block,'general')
        self.assertEqual(self.date_clock().category,'Path time')
        client.post(url+f'/{incident.id}',data={'csrf_token':'token','incident_status':'In progress','severity':'Low',
            'responsible_department':'ADMIN','affected_block':'malformed','note':'Update scope','view':'sessions'})
        self.assertEqual(incident.affected_block,'general')

    def test_live_readiness_never_loads_timing_intervals_or_writes_clocks(self):
        from sqlalchemy import event
        client=self.admin()
        before={clock.id:clock.revision for clock in m.ProcessClock.query.all()}
        statements=[]
        def record(connection,cursor,statement,*args): statements.append(statement.lower())
        event.listen(db.engine,'before_cursor_execute',record)
        try: response=client.get('/quality-control?tab=readiness')
        finally: event.remove(db.engine,'before_cursor_execute',record)
        self.assertEqual(response.status_code,200)
        self.assertFalse(any('process_interval' in statement or 'process_clock' in statement for statement in statements))
        self.assertEqual(before,{clock.id:clock.revision for clock in m.ProcessClock.query.all()})

    def test_first_position_records_start_while_blocked_without_counting_it(self):
        clock=self.block_clock('staffing')
        self.assertIsNone(clock.started_at)
        db.session.add(m.ExamSessionSupervisorAssignment(exam_session_id=self.session_record.id,participation_status='Pending'))
        db.session.commit()
        self.assertIsNotNone(clock.started_at)
        self.assertEqual(clock.category,'Blocked')
        self.assertEqual(totals(clock)['total'],0)

    def test_bulk_deleted_session_does_not_leave_a_running_clock(self):
        clock=self.date_clock();cid=clock.id
        m.ExamSession.query.filter_by(id=self.session_record.id).delete(synchronize_session=False)
        db.session.commit()
        clock=db.session.get(m.ProcessClock,cid)
        self.assertEqual(clock.category,'N/A')
        self.assertEqual(m.ProcessInterval.query.filter_by(clock_id=cid,ended_at=None).count(),0)

    def test_unblocked_finance_without_first_review_is_not_blocked_or_timed(self):
        self.session_record.monthly_registrations_closed=True
        self.session_record.date_confirmation_status='Confirmed'
        db.session.commit()
        clock=self.block_clock('finance')
        self.assertEqual(clock.category,'Not started')
        self.assertIsNone(clock.started_at)
        self.assertEqual(totals(clock)['total'],0)
        self.assertEqual(m.ProcessInterval.query.filter_by(clock_id=clock.id,ended_at=None).count(),0)
        control=m.ExamSessionFinanceControl(exam_session_id=self.session_record.id,status='Effective clearance',institutions_confirmed_with_admin=False)
        db.session.add(control);db.session.commit()
        self.assertEqual(clock.category,'Path time')
        self.assertIsNotNone(clock.started_at)
        db.session.delete(control);db.session.commit()
        self.assertEqual(clock.category,'Path time','Removing a review does not undo the fact that the process started')

    def test_unstarted_finance_category_is_non_counting_and_stable(self):
        c=cell('finance','Not reviewed',enabled=True,today=date(2026,11,7))
        self.assertEqual(choose_category(c,{'begun':False})[0],'Not started')
        c['enabled']=False
        self.assertEqual(choose_category(c,{'begun':False})[0],'Blocked')

    def test_detail_returns_fresh_operational_status_after_source_changes(self):
        client=self.admin();clock=self.date_clock()
        page=client.get('/quality-control?tab=timing').get_data(as_text=True)
        self.assertIn('data-operational-status="Pending"',page)
        self.session_record.date_confirmation_status='Confirmed';db.session.commit()
        result=client.get(f'/quality-control/process-timing/{clock.id}')
        self.assertEqual(result.status_code,200)
        operational=result.json['operational'][str(self.session_record.id)]
        self.assertEqual(operational['status'],'Confirmed')
        self.assertEqual(operational['availability'],'UNBLOCKED')
        self.assertEqual(result.json['category'],'Completed')

    def test_timing_has_its_own_colour_legend(self):
        response=self.admin().get('/quality-control?tab=timing')
        html=response.get_data(as_text=True)
        self.assertIn('Timing category colours',html)
        self.assertIn('Path time · under Path control',html)
        self.assertIn('Waiting external',html)
        self.assertIn('Blocked · paused',html)

    def test_inline_breakdown_and_partial_badge_are_only_in_timing_view(self):
        client=self.admin()
        clock=self.date_clock();clock.coverage_complete=False;db.session.commit()
        timing=client.get('/quality-control?tab=timing').get_data(as_text=True)
        self.assertIn('data-time-breakdown',timing)
        self.assertIn('data-time-path',timing)
        self.assertIn('data-time-external',timing)
        self.assertIn('data-time-incident',timing)
        self.assertIn('>Partial data</span>',timing)
        self.assertIn('Recorded time',timing)
        live=client.get('/quality-control?tab=readiness').get_data(as_text=True)
        self.assertNotIn('data-time-breakdown',live)
        self.assertNotIn('data-time-total',live)
