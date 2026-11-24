import re
import unittest
from datetime import datetime, timedelta
from app import db, models as m
from app.routes import LOCAL_TZ
from tests import test_staff_return_materials as fixtures


class StaffSessionActionsTest(unittest.TestCase):
    setUp = fixtures.StaffReturnMaterialsTest.setUp
    tearDown = fixtures.StaffReturnMaterialsTest.tearDown
    assign = fixtures.StaffReturnMaterialsTest.assign
    page = fixtures.StaffReturnMaterialsTest.page

    def report_links(self, page):
        return re.findall(r'<a\b[^>]*\bdata-staff-report-quick\b[^>]*>', page)

    def test_native_report_actions_follow_exam_date_and_submission(self):
        assignment, share = self.assign('supervisor')
        today = datetime.now(LOCAL_TZ).date()
        self.record.session_date = today; db.session.commit()
        page = self.page()
        self.assertIn('>Actions</th>', page)
        self.assertNotIn('>Details</th>', page)
        self.assertIn('Access session details', page)
        self.assertIn('>📦 Return of exam materials</a>', page)
        self.assertIn('>📋 End-of-session report</a>', page)
        self.assertNotIn(' hidden', self.report_links(page)[0])
        name_cell = re.search(r'<td data-label="Exam session">(.*?)</td>', page, re.S).group(1)
        self.assertNotIn('data-staff-return-open', name_cell)
        for date in [today - timedelta(days=1), today + timedelta(days=1)]:
            self.record.session_date = date; db.session.commit()
            page = self.page()
            self.assertNotIn(' hidden', self.report_links(page)[0])
            opener = re.search(r'<button\b[^>]*data-exam-day-report-link[^>]*>', page).group(0)
            self.assertIn('aria-disabled="true"', opener)
        self.record.session_date = today
        db.session.add(m.StaffExamSessionReport(exam_session_id=self.record.id,
            submission_id=share.submissions[0].id, schedule_outcome='There were no delays'))
        db.session.commit()
        self.assertNotIn(' hidden', self.report_links(self.page())[0])
        self.assertIn('Report submitted', self.page())

    def test_report_shortcut_is_absent_for_examiner_intern_and_remote_supervisor(self):
        examiner, share = self.assign('examiner')
        self.assertEqual(self.report_links(self.page()), [])
        examiner.is_shipment_recipient = False
        self.assign('intern')
        self.assertEqual(self.report_links(self.page()), [])
        supervisor, _ = self.assign('supervisor')
        supervisor.is_remote = True; db.session.commit()
        self.assertEqual(self.report_links(self.page()), [])

    def test_external_report_keeps_existing_url_and_from_exam_date_availability(self):
        self.record.format = 'Online at exam centre'
        self.record.session_date = datetime.now(LOCAL_TZ).date()
        self.app.config['STAFF_END_OF_SESSION_REPORT_URL'] = 'https://example.com/existing-report'
        assignment, share = self.assign('supervisor')
        page = self.page()
        link = self.report_links(page)[0]
        self.assertIn('data-staff-report-kind="external"', link)
        self.assertNotIn(' hidden', link)
        self.assertIn('data-staff-external-report-section hidden', page)
        self.assertIn('href="https://example.com/existing-report"', page)
        self.app.config['STAFF_END_OF_SESSION_REPORT_URL'] = ''
        self.assertEqual(self.report_links(self.page()), [])
