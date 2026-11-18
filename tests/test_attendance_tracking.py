import io
import json
import unittest
from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch
from app import db
from app import models as m
from app import post_attendance as attendance
from app.attendance_tracking import presentation
from app.routes import LOCAL_TZ,journey_absence_upload_window
from app.quality_control import load_rows
from app.process_timing import reconcile_due,totals
from tests import test_post_attendance as fixtures


class AttendanceTrackingTest(unittest.TestCase):
    new_session=fixtures.PostAttendanceTest.new_session
    fake_upload=fixtures.PostAttendanceTest.fake_upload
    raw_action=fixtures.PostAttendanceTest.raw_action

    def setUp(self):
        fixtures.PostAttendanceTest.setUp(self)
        self.now=datetime(2026,11,19,12,tzinfo=timezone.utc)
        self.clock.stop();self.clock=patch('app.post_attendance.local_today',side_effect=lambda:self.now.astimezone(LOCAL_TZ).date());self.clock.start()
        parent=self
        class Clock(datetime):
            @classmethod
            def now(cls,tz=None):return parent.now.astimezone(tz) if tz else parent.now.replace(tzinfo=None)
        self.patches=[patch('app.absence_submissions.local_today',side_effect=lambda:self.now.astimezone(LOCAL_TZ).date()),patch('app.attendance_tracking.now_utc',side_effect=lambda:self.now),
            patch('app.quality_control.datetime',Clock),patch('app.process_timing.datetime',Clock),patch('app.routes.datetime',Clock),
            patch('app.routes.journey_absence_upload_window',side_effect=lambda record,now=None:journey_absence_upload_window(record,now or self.now))]
        for value in self.patches:value.start()
        self.record.session_date=date(2026,11,18);db.session.commit()

    def tearDown(self):
        for value in reversed(self.patches):value.stop()
        fixtures.PostAttendanceTest.tearDown(self)

    def get(self):return self.client.get(self.url).json['state']

    def upload(self):
        return self.raw_action('module_upload',institution_id='main',module='Speaking',previous_file_id='',document=(io.BytesIO(b'list'),'list.pdf'))

    def submit(self,number='001'):
        return self.client.post(self.public,data={'csrf_token':'test','candidate_number':number,'candidate_name':'Candidate',
            'rescheduled_for':'next_july_online','document':(io.BytesIO(b'certificate'),'cert.pdf')})

    def finish_first(self):
        self.assertEqual(self.upload().status_code,200)
        self.now+=timedelta(hours=1);self.raw_action('verified',value='1')
        state=self.get();main=state['institutions'][0]['id'];key=state['contacts'][0]['key']
        self.now+=timedelta(hours=1)
        self.assertEqual(self.raw_action('sent',institution_id=main,key=key,value='1').status_code,200)
        return main,key

    def clock_record(self):
        return m.ProcessClock.query.join(m.ProcessClockSession).filter(m.ProcessClockSession.exam_session_id==self.record.id,m.ProcessClock.block=='attendance',m.ProcessClockSession.is_current.is_(True)).one()

    def test_exam_day_is_readonly_and_public_uploads_are_not_internal_activity(self):
        self.record.session_date=self.now.astimezone(LOCAL_TZ).date();db.session.commit()
        self.assertEqual(self.submit().status_code,200)
        state=self.get();self.assertEqual(state['progress'],'Not started');self.assertFalse(state['enabled'])
        self.assertEqual(state['tracking']['department'],'-');self.assertEqual(state['tracking']['action'],'Exam session in progress')
        self.assertEqual(self.raw_action('verified',value='1').status_code,403)
        self.assertFalse(m.PostAttendance.query.one().internal_activity)
        self.assertEqual(self.clock_record().category,'Blocked')
        opens=datetime.fromisoformat(state['tracking']['opens_at'])
        self.now=opens.astimezone(timezone.utc)-timedelta(microseconds=1)
        self.assertFalse(self.get()['enabled']);self.now+=timedelta(microseconds=1)
        reconcile_due(self.now)
        state=self.get();self.assertTrue(state['enabled']);self.assertEqual(state['progress'],'Not started')
        self.assertEqual(state['tracking']['department'],'ADMIN')
        self.assertEqual(state['tracking']['action'],'Perform attendance review and notify institutions')
        self.assertEqual(self.clock_record().category,'Not started')
        self.assertEqual(self.raw_action('verified',value='1').status_code,200)
        self.assertTrue(m.PostAttendance.query.one().internal_activity)
        self.assertEqual(m.PostAttendance.query.one().internal_started_at.replace(tzinfo=timezone.utc),self.now)

    def test_argentine_holiday_and_end_of_day_deadline_colours(self):
        self.record.session_date=date(2026,11,20);db.session.commit()
        self.now=datetime(2026,11,21,12,tzinfo=timezone.utc)
        state=self.get();self.assertEqual(state['tracking']['deadlines'][0]['date'],'24/11/2026')
        self.now=datetime(2026,11,25,2,59,59,tzinfo=timezone.utc)
        self.assertEqual(self.get()['tracking']['deadlines'][0]['status'],'on-track')
        self.raw_action('verified',value='1')
        state=self.get();self.assertEqual(state['tracking']['deadlines'][0]['status'],'met');self.assertEqual(state['progress'],'Completed')
        self.now+=timedelta(seconds=1);self.raw_action('verified',value='0')
        self.assertEqual(self.get()['tracking']['deadlines'][0]['status'],'overdue')
        self.raw_action('verified',value='1')
        self.assertEqual(self.get()['tracking']['deadlines'][0]['status'],'missed')
        self.assertEqual(self.get()['tracking']['department'],'');self.assertEqual(self.get()['tracking']['action'],'')
        self.assertEqual(self.get()['tracking']['controls_completed'],1);self.assertEqual(self.get()['tracking']['controls_total'],1)

    def test_waiting_time_no_documentation_closure_and_reopening(self):
        start=self.now;self.finish_first();waiting_started=self.now
        state=self.get();self.assertEqual(state['tracking']['action'],'Awaiting absence documentation from institution')
        self.assertEqual(state['tracking']['department'],'-');self.assertEqual(self.clock_record().category,'Waiting external')
        self.assertEqual(self.raw_action('no_documentation_received',value='1').status_code,400)
        close=datetime.fromisoformat(state['window']['expires_at']).astimezone(timezone.utc)
        self.now=close+timedelta(hours=1);reconcile_due(self.now)
        self.assertEqual(self.clock_record().category,'Path time')
        self.assertEqual(self.get()['tracking']['action'],'Confirm no absence documentation was received')
        original_due=self.get()['tracking']['deadlines'][1]['due_at']
        self.assertEqual(self.raw_action('no_documentation_received',value='1').status_code,200)
        state=self.get();self.assertEqual(state['progress'],'Completed');self.assertFalse(state['review_results_notified'])
        clock=self.clock_record();self.assertEqual(clock.category,'Completed')
        measured=totals(clock,now=self.now)
        self.assertEqual(measured['path'],3*3600)
        self.assertEqual(measured['external'],(close-waiting_started).total_seconds())
        self.assertTrue(clock.coverage_complete)
        for item in state['tracking']['deadlines']:self.assertEqual(item['status'],'met')
        self.now+=timedelta(days=1)
        response=self.client.post(self.url.replace('/attendance','/candidates'),data={'csrf_token':'test','candidate_number':'new',
            'candidate_name':'New Candidate','institution_name':'School','exam':'Ready','modules':['Speaking'],
            'rescheduled_for':'next_july_online','approval':'Confirmed','currency':'USD','credit_balance':'10','document':(io.BytesIO(b'new'),'new.pdf')})
        self.assertEqual(response.status_code,200,response.json)
        state=response.json['state'];self.assertFalse(state['no_documentation_received']);self.assertEqual(state['progress'],'In progress')
        self.assertEqual(state['tracking']['action'],'Notify institutions of absence documentation review results')
        self.assertEqual(state['tracking']['deadlines'][1]['due_at'],original_due)
        self.assertEqual(self.clock_record().reopenings,1)
        self.raw_action('review_results_notified',value='1');self.assertEqual(self.get()['progress'],'Completed')
        self.assertEqual(self.clock_record().category,'Completed')

    def test_reviews_action_and_quality_control_use_same_contract(self):
        self.finish_first();self.submit()
        self.now=datetime.fromisoformat(self.get()['window']['expires_at']).astimezone(timezone.utc)+timedelta(hours=1)
        reconcile_due(self.now)
        state=self.get();self.assertEqual(state['tracking']['action'],'Review absence documentation')
        row=load_rows([self.record],today=self.now.astimezone(LOCAL_TZ).date())[0]
        cell=next(item for item in row['cells'] if item['key']=='attendance')
        self.assertEqual(cell['label'],state['progress'])
        self.assertEqual(cell['attendance']['controls_completed'],state['tracking']['controls_completed'])
        self.assertEqual(cell['attendance']['deadlines'],state['tracking']['deadlines'])
        online=self.new_session('Online',self.record.session_date,'Online');db.session.commit()
        self.assertFalse(next(item for item in load_rows([online])[0]['cells'] if item['key']=='attendance')['applicable'])
        candidate=m.AbsenceCandidate.query.one()
        self.raw_action('candidate',candidate_id=candidate.id,field='review',value='Declined',previous_file_id=candidate.document_id,reason='Reason')
        self.assertEqual(self.get()['tracking']['action'],'Notify institutions of absence documentation review results')
        self.raw_action('review_results_notified',value='1')
        state=self.get();self.assertEqual(state['tracking']['action'],'');self.assertEqual(state['tracking']['department'],'')
        self.assertEqual(next(item for item in load_rows([self.record])[0]['cells'] if item['key']=='attendance')['state'],'complete')

    def test_overdue_first_steps_keep_priority_and_deadline_is_not_reset(self):
        self.now=datetime(2026,11,26,12,tzinfo=timezone.utc)
        self.assertEqual(self.get()['tracking']['action'],'Perform attendance review and notify institutions')
        self.assertTrue(self.get()['tracking']['overdue'])
        main,key=self.finish_first();state=self.get()
        self.assertEqual(state['tracking']['deadlines'][0]['status'],'missed')
        due=state['tracking']['deadlines'][0]['due_at']
        self.raw_action('sent',institution_id=main,key=key,value='0')
        state=self.get();self.assertEqual(state['tracking']['action'],'Perform attendance review and notify institutions')
        self.assertEqual(state['tracking']['deadlines'][0]['due_at'],due)
        self.assertEqual(state['tracking']['deadlines'][0]['status'],'overdue')

    def test_historical_completion_without_timestamp_is_neutral(self):
        value=attendance.control(self.record,True);value.verified=True;value.internal_activity=True;db.session.commit()
        state=self.get();self.assertEqual(state['progress'],'Completed')
        self.assertEqual(state['tracking']['deadlines'][0]['status'],'unknown')
        self.assertIsNone(state['tracking']['timing_stages'][0]['completed_at'])

    def test_quality_pages_and_my_actions_offer_attendance_navigation(self):
        user=m.User(full_name='QA Admin',email='qa@example.com',department='Admin',is_superadmin=True,is_active=True,password_hash='test')
        db.session.add(user);db.session.commit()
        with self.client.session_transaction() as session:session.update(user='QA Admin',user_id=user.id,user_email=user.email,user_department='Admin')
        for tab in ['readiness','timing']:
            response=self.client.get('/quality-control?session_year=2026&tab='+tab)
            self.assertEqual(response.status_code,200)
            self.assertIn('data-key="attendance"',response.get_data(as_text=True))
        response=self.client.get('/my-actions?session_year=2026&actions_section=attendance')
        self.assertEqual(response.status_code,200)
        self.assertIn('Perform attendance review and notify institutions',response.get_data(as_text=True))
        self.assertIn('open_attendance=',response.get_data(as_text=True))

    def test_legacy_activity_migration_does_not_invent_internal_work_or_dates(self):
        from sqlalchemy import text
        from app.schema_migrations import migrate_attendance_tracking
        self.submit();source_id=self.record.id
        other=self.new_session('Verified legacy',self.record.session_date);other_id=other.id;db.session.commit()
        self.app.config['QUALITY_CONTROL_TRACKING_READY']=False
        db.session.expunge_all()
        db.session.execute(text('DROP TABLE post_attendance'))
        db.session.execute(text('CREATE TABLE post_attendance (exam_session_id INTEGER PRIMARY KEY, verified BOOLEAN NOT NULL, review_results_notified BOOLEAN NOT NULL, revision INTEGER NOT NULL, updated_at TIMESTAMP)'))
        db.session.execute(text('INSERT INTO post_attendance VALUES (:id,0,0,5,NULL)'),{'id':source_id})
        db.session.execute(text('INSERT INTO post_attendance VALUES (:id,1,0,8,NULL)'),{'id':other_id});db.session.commit()
        migrate_attendance_tracking()
        public_only=db.session.get(m.PostAttendance,source_id);verified=db.session.get(m.PostAttendance,other_id)
        self.assertFalse(public_only.internal_activity);self.assertIsNone(public_only.internal_started_at)
        self.assertTrue(verified.internal_activity);self.assertIsNone(verified.internal_started_at);self.assertIsNone(verified.notifications_completed_at)
        public_only.internal_activity=True;public_only.internal_started_at=self.now;db.session.commit()
        migrate_attendance_tracking();self.assertTrue(db.session.get(m.PostAttendance,source_id).internal_activity)
        self.assertIsNotNone(db.session.get(m.PostAttendance,source_id).internal_started_at)
