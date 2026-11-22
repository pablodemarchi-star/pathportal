import io
import re
import unittest
from datetime import date
from unittest.mock import patch
from app import db
from app import models as m
from app import post_attendance as attendance
from tests import test_post_attendance as fixtures


class OnlinePostControlsTest(unittest.TestCase):
    setUp = fixtures.PostAttendanceTest.setUp
    tearDown = fixtures.PostAttendanceTest.tearDown
    new_session = fixtures.PostAttendanceTest.new_session
    fake_upload = fixtures.PostAttendanceTest.fake_upload

    def test_online_and_onsite_views_list_their_own_formats(self):
        self.new_session('Online post exam', date(2026, 11, 17), 'Online')
        self.new_session('Online centre post exam', date(2026, 11, 17), 'Online at exam centre')
        self.new_session('Future online exam', date(2026, 12, 1), 'Online')
        self.new_session('Previous year online', date(2025, 11, 1), 'Online')
        db.session.commit()
        online = self.client.get('/pre-online-session-control-tower?session_year=2026&view=post')
        self.assertEqual(online.status_code, 200)
        html = online.get_data(as_text=True)
        self.assertIn('Online session control tower · Post controls', html)
        rows = re.findall(r'data-post-row data-name="([^"]+)"', html)
        self.assertEqual(set(rows), {'Online post exam', 'Online centre post exam'})
        self.assertIn('>Pre checks</a>', html)
        self.assertIn('aria-current="page"', html)
        self.assertNotIn('>Bundles</a>', html)
        onsite = self.client.get('/pre-session-control-tower?session_year=2026&view=post').get_data(as_text=True)
        self.assertEqual(re.findall(r'data-post-row data-name="([^"]+)"', onsite), ['Main session'])
        self.assertIn('>Bundles</a>', onsite)
        pre = self.client.get('/pre-online-session-control-tower?session_year=2026').get_data(as_text=True)
        self.assertRegex(pre, r'/pre-online-session-control-tower\?[^"<>]*view=post')

    def test_online_formats_share_attendance_uploads_and_persistence(self):
        for format_name in ('Online', 'Online at exam centre'):
            self.record.format = format_name
            db.session.commit()
            response = self.client.get(self.url)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json['state']['format'], format_name)
            response = self.client.post(self.url, data=dict(csrf_token='test', action='module_upload',
                institution_id='main', module='Speaking', previous_file_id='',
                document=(io.BytesIO(b'list'), 'absence.pdf')))
            self.assertEqual(response.status_code, 200, response.json)
            self.assertTrue(response.json['state']['has_absences'])
            document = m.AttendanceModule.query.filter_by(module='Speaking').one()
            self.assertIsNotNone(document.document_id)
            response = self.client.post(self.url, data=dict(csrf_token='test', action='module_clear',
                institution_id='main', module='Speaking', previous_file_id=document.document_id, confirmed='1'))
            self.assertEqual(response.status_code, 200, response.json)

    def test_online_exam_day_is_read_only_and_requires_permissions(self):
        self.record.format = 'Online'
        self.record.session_date = self.today
        db.session.commit()
        self.assertEqual(self.client.get(self.url).status_code, 200)
        self.assertEqual(self.client.post(self.url, data=dict(csrf_token='test', action='submission_status', value='completed')).status_code, 403)
        self.record.session_date = date(2026, 11, 17); db.session.commit()
        self.assertEqual(self.client.post(self.url, data=dict(csrf_token='bad', action='submission_status', value='completed')).status_code, 400)
        with patch('app.routes.user_can_edit', return_value=False):
            self.assertEqual(self.client.post(self.url, data=dict(csrf_token='test', action='submission_status', value='completed')).status_code, 403)
        self.assertEqual(self.app.test_client().get('/pre-online-session-control-tower?view=post').status_code, 302)
