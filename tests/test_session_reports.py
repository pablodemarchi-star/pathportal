import json
import unittest
from datetime import date
from unittest.mock import patch
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from types import SimpleNamespace
from tests import test_staff_session_report as fixtures
from app import db, models as m
from app.session_reports import load_report_rows
from app.schema_migrations import migrate_session_scoped_staff_reports


class SessionReportsTest(unittest.TestCase):
    setUp=fixtures.StaffSessionReportTest.setUp
    tearDown=fixtures.StaffSessionReportTest.tearDown
    post=fixtures.StaffSessionReportTest.post

    def admin_client(self, superadmin=True):
        user=m.User(full_name='Review Admin',email='review@example.com',department='Management',is_active=True,is_superadmin=superadmin,password_hash='test')
        db.session.add(user);db.session.commit()
        client=self.app.test_client()
        with client.session_transaction() as state:
            state.update(user=user.full_name,user_id=user.id,user_full_name=user.full_name,user_email=user.email,user_department=user.department,csrf_token='test')
        return client,user

    def feedback(self):
        share=m.ExamSessionJourneyShare(exam_session_id=self.record.id,audience='institution',token='quality-feedback')
        db.session.add(share);db.session.flush()
        feedback=m.ExamCentreFeedback(exam_session_id=self.record.id,share_id=share.id,session_year=2026,
            session_name=self.record.exam_session_name,language='es',organisation_score=5,organisation_comment='Improve timing',
            candidate_experience_score=9,communication_score=8,overall_score=7,overall_comment='Clearer information',
            worked_well='Friendly team',improvements_noticed='Better instructions',improvements_needed='More notice')
        db.session.add(feedback);db.session.commit()

    def test_superadmin_only_on_summary_and_full_detail(self):
        client,user=self.admin_client(False)
        self.assertEqual(client.get('/quality-control?tab=reports&session_year=2026').status_code,403)
        self.assertEqual(client.get(f'/quality-control/session-reports/{self.record.id}').status_code,403)
        user.is_superadmin=True;db.session.commit()
        response=client.get('/quality-control?tab=reports&session_year=2026')
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.headers['Cache-Control'],'private, no-store')
        self.assertIn('Session reports',response.get_data(as_text=True))

    def test_all_sessions_formats_and_concatenated_rows_are_separate(self):
        other=m.ExamSession(exam_session_name='Online peer',category='Path School',status='Pending',session_date=date(2026,12,2),format='Online')
        db.session.add(other);db.session.flush()
        self.record.concat_session_ids=json.dumps([other.id]);other.concat_session_ids=json.dumps([self.record.id]);db.session.commit()
        rows=load_report_rows(2026)
        self.assertEqual(len(rows),2)
        online=next(row for row in rows if row['session'].id==other.id)
        self.assertEqual(online['report_status'],'Not applicable')
        self.assertEqual(online['feedback_status'],'Pending')
        client,_=self.admin_client()
        with patch('app.quality_control.dashboard_rows',side_effect=AssertionError('Reports must not load timing/readiness')):
            html=client.get('/quality-control?tab=reports&session_year=2026').get_data(as_text=True)
        self.assertIn('Online peer',html)
        self.assertEqual(html.count('data-report-row '),2)

    def test_scores_alerts_author_and_lazy_full_answers(self):
        self.feedback()
        self.assertEqual(self.post(optional_comments='Private detailed suggestion',schedule_outcome='There were minor delays',reasons='Bus arrived late',facilities_outcome='Unsatisfactory',facilities_comments='Noisy room').status_code,200)
        row=load_report_rows(2026)[0]
        self.assertEqual(row['average'],7.2)
        self.assertTrue(row['complete'])
        self.assertIn('Report Supervisor',row['report_author'])
        self.assertTrue(any('score ≤ 7' in item for item in row['alerts']))
        self.assertTrue(any('Unsatisfactory' in item for item in row['alerts']))
        client,_=self.admin_client()
        page=client.get('/quality-control?tab=reports&session_year=2026').get_data(as_text=True)
        self.assertNotIn('Private detailed suggestion',page)
        detail=client.get(f'/quality-control/session-reports/{self.record.id}')
        self.assertEqual(detail.status_code,200)
        html=detail.get_data(as_text=True)
        for value in ['Private detailed suggestion','Bus arrived late','Noisy room','Improve timing','Friendly team','Better instructions','More notice','photo.jpg']:
            self.assertIn(value,html)
        self.assertNotIn('<form',html)
        self.assertEqual(detail.headers['Cache-Control'],'private, no-store')

    def test_legacy_author_name_is_resolved_without_losing_report(self):
        self.assertEqual(self.post().status_code,200)
        report=m.StaffExamSessionReport.query.one()
        report.author_name=''
        db.session.commit()
        self.assertEqual(load_report_rows(2026)[0]['report_author'],'Report Supervisor')

    def test_missing_reports_after_exam_date_are_highlighted(self):
        self.record.session_date=date(2025,1,1);db.session.commit()
        row=load_report_rows(2025)[0]
        self.assertEqual(row['report_status'],'Not submitted — exam date passed')
        self.assertEqual(len(row['alerts']),2)


class SessionReportMigrationTest(unittest.TestCase):
    def test_existing_duplicate_reports_are_preserved_with_one_session_owner(self):
        engine=create_engine('sqlite:///:memory:')
        unit=Session(engine)
        for sql in ['CREATE TABLE exam_session (id INTEGER PRIMARY KEY)',
                    'CREATE TABLE staff_exam_session_submission (id INTEGER PRIMARY KEY, exam_session_id INTEGER NOT NULL)',
                    'CREATE TABLE staff_exam_session_report (id INTEGER PRIMARY KEY, submission_id INTEGER NOT NULL)',
                    'INSERT INTO exam_session VALUES (1),(2)',
                    'INSERT INTO staff_exam_session_submission VALUES (1,1),(2,1),(3,2)',
                    'INSERT INTO staff_exam_session_report VALUES (1,1),(2,2),(3,3)']:
            unit.execute(text(sql))
        unit.commit()
        with patch('app.schema_migrations.db',SimpleNamespace(engine=engine,session=unit)):
            migrate_session_scoped_staff_reports();migrate_session_scoped_staff_reports()
        rows=unit.execute(text('SELECT id,exam_session_id FROM staff_exam_session_report ORDER BY id')).all()
        self.assertEqual([tuple(row) for row in rows],[(1,1),(2,None),(3,2)])
        unit.close();engine.dispose()
