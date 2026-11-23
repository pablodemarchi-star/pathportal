import json
import unittest
from app import db
from app import models as m
from tests import test_staff_session_report as fixtures


class StaffReportConsiderationsTest(unittest.TestCase):
    setUp=fixtures.StaffSessionReportTest.setUp
    tearDown=fixtures.StaffSessionReportTest.tearDown
    post=fixtures.StaffSessionReportTest.post

    def online(self,modules='Listening and speaking,Reading and writing'):
        self.record.format='Online';self.record.modules=modules;db.session.commit()

    def test_widgets_only_appear_in_applicable_verification_sections(self):
        for format_name,modules,expected in [('Online','Reading and writing',{'reading_writing'}),('Online','Listening and speaking',{'listening','speaking'}),('Online','Speaking',{'speaking'}),('Onsite','Reading and writing',set())]:
            self.record.format=format_name;self.record.modules=modules;db.session.commit()
            html=self.client.get(f'/my-exam-sessions/{self.share.token}?session_year=2026').get_data(as_text=True)
            for section in ('reading_writing','listening','speaking'):
                self.assertEqual('name="important_considerations_'+section+'"' in html,section in expected)
            self.assertEqual(html.count('data-add-consideration>'),len(expected))

    def test_speaking_considerations_are_validated_saved_and_read_only(self):
        self.online('Speaking')
        self.assertEqual(self.post(important_considerations_speaking=json.dumps([dict(title='',text='Detail')])).status_code,400)
        entries=[dict(title='Speaking issue',text='Speaking explanation')]
        response=self.post(important_considerations_speaking=json.dumps(entries))
        self.assertEqual(response.status_code,200,response.json)
        self.assertEqual(json.loads(m.StaffExamSessionReport.query.one().important_considerations),{'speaking':entries})
        self.assertEqual(self.post(important_considerations_speaking='[]').status_code,409)

    def test_multiple_titled_considerations_save_and_report_is_immutable(self):
        self.online()
        reading=[dict(title='Candidate file issue',text='Missing page explained.'),dict(title='Second consideration',text='Additional detail')]
        listening=[dict(title='Audio interruption',text='The audio paused during the test.')]
        response=self.post(important_considerations_reading_writing=json.dumps(reading),important_considerations_listening=json.dumps(listening))
        self.assertEqual(response.status_code,200,response.json)
        saved=m.StaffExamSessionReport.query.one()
        self.assertEqual(json.loads(saved.important_considerations),dict(reading_writing=reading,listening=listening,speaking=[]))
        self.assertEqual(self.post(important_considerations_listening='[]').status_code,409)
        self.assertEqual(json.loads(saved.important_considerations)['listening'],listening)

    def test_optional_considerations_and_server_validation(self):
        self.online()
        for value in ('invalid','{}','[null]',json.dumps([dict(title='',text='Text')]),json.dumps([dict(title='Title',text='  ')]),json.dumps([dict(title='x'*201,text='Text')]),json.dumps([dict(title='Title',text='x'*10001)])):
            self.assertEqual(self.post(important_considerations_listening=value).status_code,400,value[:50])
        self.assertEqual(m.StaffExamSessionReport.query.count(),0)
        self.assertEqual(self.post().status_code,200)
        self.assertEqual(json.loads(m.StaffExamSessionReport.query.one().important_considerations),dict(reading_writing=[],listening=[],speaking=[]))

    def test_migration_preserves_historical_report_and_defaults_to_no_considerations(self):
        from sqlalchemy import text
        from app.schema_migrations import migrate_staff_report_components
        self.assertEqual(self.post(optional_comments='Original report').status_code,200)
        report_id=m.StaffExamSessionReport.query.one().id
        db.session.expunge_all()
        db.session.execute(text('ALTER TABLE staff_exam_session_report DROP COLUMN important_considerations'))
        db.session.commit()
        migrate_staff_report_components();migrate_staff_report_components()
        saved=db.session.get(m.StaffExamSessionReport,report_id)
        self.assertEqual(saved.optional_comments,'Original report')
        self.assertEqual(saved.important_considerations,'{}')

    def test_irrelevant_sections_and_onsite_forged_payload_are_ignored(self):
        self.online('Speaking')
        self.assertEqual(self.post(important_considerations_listening='invalid',important_considerations_reading_writing='invalid').status_code,200)
        self.assertEqual(json.loads(m.StaffExamSessionReport.query.one().important_considerations),{'speaking':[]})

    def test_read_only_report_displays_title_and_escaped_text_under_correct_section(self):
        self.online()
        self.assertEqual(self.post(important_considerations_reading_writing=json.dumps([dict(title='RW issue',text='<script>alert(1)</script>')]),important_considerations_listening=json.dumps([dict(title='Listening issue',text='Audio detail')])).status_code,200)
        admin=m.User(full_name='Considerations Admin',email='considerations@example.com',department='Management',is_active=True,is_superadmin=True,password_hash='test')
        db.session.add(admin);db.session.commit()
        with self.client.session_transaction() as state:
            state.update(user=admin.full_name,user_id=admin.id,user_email=admin.email,user_full_name=admin.full_name,user_department=admin.department)
        response=self.client.get(f'/quality-control/session-reports/{self.record.id}')
        self.assertEqual(response.status_code,200)
        html=response.get_data(as_text=True)
        self.assertIn('<h5>RW issue</h5>',html)
        self.assertIn('&lt;script&gt;alert(1)&lt;/script&gt;',html)
        self.assertNotIn('<script>alert(1)</script>',html)
        self.assertLess(html.index('RW issue'),html.index('Listening component verifications'))
        self.assertLess(html.index('Listening issue'),html.index('Speaking component verifications'))
