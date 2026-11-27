import json
import unittest
from unittest.mock import patch
from app import db, models as m
from app.shared_staff_report import discard_legacy_checks
from tests import test_staff_session_report as fixtures


class SharedStaffReportTest(unittest.TestCase):
    setUpBase = fixtures.StaffSessionReportTest.setUp
    tearDown = fixtures.StaffSessionReportTest.tearDown
    post = fixtures.StaffSessionReportTest.post

    def setUp(self):
        self.setUpBase()
        self.assignment.is_remote = True
        self.assignment.is_shipment_recipient = False
        self.examiner = m.AcademicStaff(full_name='Recipient Examiner', status='Active', roles='Examiner')
        db.session.add(self.examiner); db.session.flush()
        self.recipient = m.ExamSessionExaminerAssignment(exam_session_id=self.record.id, team_member_id=self.examiner.id,
            participation_status='Confirmed', is_shipment_recipient=True, logistics_type='Does not apply')
        self.examiner_share = m.StaffExamSessionsShare(person_ref=str(self.examiner.id), token='recipient-report')
        db.session.add_all([self.recipient, self.examiner_share]); db.session.flush()
        self.examiner_submission = m.StaffExamSessionSubmission(exam_session_id=self.record.id, assignment_type='examiner',
            assignment_id=self.recipient.id, share_id=self.examiner_share.id)
        db.session.add(self.examiner_submission); db.session.commit()
        control = m.ExamSessionSinapsisControl.query.filter_by(exam_session_id=self.record.id).one()
        control.return_review_required = False
        db.session.commit()
        self.remote_url = self.url
        self.examiner_url = f'/my-exam-sessions/{self.examiner_share.token}/submissions/{self.examiner_submission.id}/report'
        self.feedback = patch('app.routes.staff_report_feedback_submitted', return_value=True); self.feedback.start(); self.addCleanup(self.feedback.stop)
        self.available = patch('app.routes.staff_report_available', return_value=True); self.available.start(); self.addCleanup(self.available.stop)

    def draft(self, url=None, changes=None, base=None, **extra):
        url = (url or self.remote_url) + '/draft'
        if changes is None:
            return self.client.get(url)
        return self.client.post(url, data=(dict(csrf_token='test', changes=json.dumps(changes), base=json.dumps(base or {})) | extra))

    def complete_answers(self):
        from app.shared_report_roles import return_view, owner
        with self.app.test_request_context():
            info = return_view(self.record, self.examiner_share)
        values = dict(schedule_outcome='There were no delays', facilities_outcome='Satisfactory',
            emergency_pack_outcome='No, it was not needed', return_verification=['submitted_papers', 'submitted_packages', 'absent_packages', 'sealing', 'labelling', 'institutional_verification'],
            absent_candidates_checked=['1'], submitted_candidates_checked=['1'], marketing_confirmed=['1'],
            centre_feedback_confirmed=['1'], recordings_reminder_confirmed=['1'], return_materials_verified=['1'], return_package_reviewed=['1'], return_instructions_confirmed=['1'],
            _return_instructions_version=info['version'], optional_comments='Examiner notes')
        from app.staff_report_review import assessment_criteria
        from app.shared_report_roles import roster
        for member in roster(self.record):
            for criterion in assessment_criteria(self.record):
                values[f"review.{member['key']}.{criterion['key']}"] = criterion['best']
        for role, url in [('examiner', self.examiner_url), ('supervisor', self.remote_url)]:
            changes = {key:value for key,value in values.items() if owner(self.record, key) == role}
            response = self.draft(url, changes=changes, base=self.draft(url).json['values'])
            self.assertEqual(response.status_code, 200, response.json)
        return self.draft().json

    def test_shared_drafts_merge_independent_answers_and_reject_conflicting_answers(self):
        self.assertEqual(self.draft().json['values'], {})
        first = self.draft(self.examiner_url, changes={'schedule_outcome':'There were no delays'})
        self.assertEqual(first.status_code, 200, first.json)
        second = self.draft(changes={'absent_candidates_checked':['1']})
        self.assertEqual(second.status_code, 200, second.json)
        values = self.draft().json['values']
        self.assertEqual(values, {'schedule_outcome':'There were no delays', 'absent_candidates_checked':['1']})
        self.assertEqual(self.draft(self.examiner_url).json['values'], values)
        self.assertEqual(self.draft(self.examiner_url, changes={'schedule_outcome':'There were minor delays'}).status_code, 409)
        self.assertEqual(self.draft(self.examiner_url, changes={'schedule_outcome':'There were minor delays'}, base=values).status_code, 200)
        self.assertEqual(self.draft().json['values']['absent_candidates_checked'], ['1'])

    def test_examiner_cannot_write_any_remote_supervisor_confirmation(self):
        from app.shared_report_roles import SUPERVISOR_FIELDS
        for field in SUPERVISOR_FIELDS:
            with self.subTest(field=field):
                response = self.draft(self.examiner_url, changes={field: ['1'], 'optional_comments': 'Must not save'})
                self.assertEqual(response.status_code, 403, response.json)
                self.assertEqual(self.draft().json['values'], {})
        saved = self.draft(changes={'absent_candidates_checked': ['1']})
        self.assertEqual(saved.status_code, 200)
        response = self.draft(self.examiner_url, changes={'absent_candidates_checked': []}, base=saved.json['values'])
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.draft().json['values'], {'absent_candidates_checked': ['1']})

    def test_portal_reuses_native_onsite_report_and_actions_for_both_roles(self):
        for share in [self.share, self.examiner_share]:
            html = self.client.get('/my-exam-sessions/' + share.token).get_data(as_text=True)
            self.assertIn('data-onsite-report-flow', html)
            self.assertIn('data-staff-exam-day-report', html)
            self.assertIn('data-staff-report-quick', html)
            self.assertIn('data-staff-report-kind="native"', html)
            self.assertIn('data-shared-report-url=', html)
            self.assertNotIn('data-staff-end-checks ', html)
            self.assertIn('Exam return package verification', html)
            self.assertIn('name="return_instructions_confirmed"', html)
            self.assertIn('Recipient Examiner', html)

    def test_only_remote_supervisor_submits_authoritative_shared_answers_and_locks_both(self):
        saved = self.complete_answers()
        self.url = self.examiner_url
        response = self.post(shared_report_revision=str(saved['revision']))
        self.assertEqual(response.status_code, 403, response.json)
        self.url = self.remote_url
        response = self.post(shared_report_revision=str(saved['revision']), schedule_outcome='Forged examiner answer', optional_comments='Forged note')
        self.assertEqual(response.status_code, 200, response.json)
        report = m.StaffExamSessionReport.query.one()
        self.assertEqual(report.author_name, self.person.full_name)
        self.assertEqual(report.schedule_outcome, 'There were no delays')
        self.assertEqual(report.optional_comments, 'Examiner notes')
        self.assertEqual(json.loads(report.staff_assessments), [])
        self.assertTrue(json.loads(report.return_instructions_context)['acknowledged_by_recipient'])
        self.assertEqual(m.StaffSharedSessionReportDraft.query.count(), 0)
        self.assertEqual(self.post(shared_report_revision='0').status_code, 409)
        self.assertTrue(self.draft(self.examiner_url).json['submitted'])

    def test_authorization_current_shipment_remote_status_format_date_and_csrf(self):
        self.assertEqual(self.draft(changes={'absent_candidates_checked':['1']}, csrf_token='bad').status_code, 400)
        self.recipient.is_shipment_recipient = False; db.session.commit()
        self.assertEqual(self.draft(self.examiner_url).status_code, 403)
        self.recipient.is_shipment_recipient = True; self.assignment.is_remote = False; db.session.commit()
        self.assertEqual(self.draft(self.examiner_url).status_code, 403)
        self.assignment.is_remote = True; self.recipient.participation_status = 'Pending'; db.session.commit()
        self.assertEqual(self.draft(self.examiner_url).status_code, 403)
        self.recipient.participation_status = 'Confirmed'; db.session.commit()
        with patch('app.routes.staff_report_available', return_value=False):
            self.assertEqual(self.draft().status_code, 403)
        wrong = self.remote_url.replace(self.share.token, self.examiner_share.token)
        self.assertEqual(self.draft(wrong).status_code, 404)
        self.record.format = 'Online'; db.session.commit()
        self.assertEqual(self.draft().status_code, 403)

    def test_legacy_checks_are_discarded_only_for_replaced_profiles_and_cannot_be_written(self):
        db.session.add_all([m.StaffExamSessionEndChecks(submission_id=self.submission.id, attendance=True),
            m.StaffExamSessionEndChecks(submission_id=self.examiner_submission.id, printed_attendance=True)])
        db.session.commit()
        discard_legacy_checks(); discard_legacy_checks()
        self.assertEqual(m.StaffExamSessionEndChecks.query.count(), 0)
        for url in [self.remote_url, self.examiner_url]:
            response = self.client.post(url.replace('/report', '/end-checks'), data=dict(csrf_token='test', check='attendance', checked='1'))
            self.assertEqual(response.status_code, 404)
        self.assertEqual(self.draft().json['values'], {})

    def test_shared_media_feedback_access_and_stale_final_submit(self):
        for url in [self.remote_url, self.examiner_url]:
            response = self.client.get(url + '/feedback-status')
            self.assertEqual(response.status_code, 200, response.json)
            self.assertEqual(len(response.json['files']), 1)
        self.draft(self.examiner_url, changes={'optional_comments':'latest'})
        response = self.post(shared_report_revision='0')
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json['code'], 'shared_draft_changed')

    def test_examiner_can_upload_media_shared_with_supervisor(self):
        from io import BytesIO
        def upload(file, target, destination):
            db.session.add(m.StaffSessionReportMedia(submission_id=target.submission_id, file_id='sharedExaminerMedia123',
                folder_id=destination.folder_id, filename=file.filename, mime_type='image/jpeg'))
        with patch('app.staff_report_media.folder_metadata'), patch('app.staff_report_media.upload_document', side_effect=upload):
            response = self.client.post(self.examiner_url + '/media', data=dict(csrf_token='test', file=(BytesIO(b'photo'), 'examiner-photo.jpg')))
        self.assertEqual(response.status_code, 200, response.json)
        response = self.client.get(self.remote_url + '/feedback-status')
        self.assertEqual({row['filename'] for row in response.json['files']}, {'photo.jpg', 'examiner-photo.jpg'})

    def test_role_permissions_completion_and_unfinished_report_cannot_submit(self):
        for key, value in [('schedule_outcome', 'There were no delays'), ('return_instructions_confirmed', ['1']), ('optional_comments', 'Wrong role')]:
            self.assertEqual(self.draft(changes={key:value}).status_code, 403)
        for key in ['absent_candidates_checked', 'centre_feedback_confirmed', 'recordings_reminder_confirmed', 'return_materials_verified', 'return_package_reviewed']:
            self.assertEqual(self.draft(self.examiner_url, changes={key:['1']}).status_code, 403)
        self.assertFalse(self.draft().json['completion']['ready'])
        self.assertEqual(self.post(shared_report_revision='0').status_code, 400)
        saved = self.complete_answers()
        self.assertTrue(saved['completion']['examiner'])
        self.assertTrue(saved['completion']['supervisor'])
        self.assertTrue(saved['completion']['ready'])
        with patch('app.routes.staff_report_feedback_submitted', return_value=False):
            self.assertFalse(self.draft().json['completion']['ready'])
            self.assertEqual(self.post(shared_report_revision=str(saved['revision']), _feedback_submitted=False).status_code, 400)

    def test_legacy_answers_are_preserved_and_examiner_cannot_review_self(self):
        draft = m.StaffSharedSessionReportDraft(exam_session_id=self.record.id, values_json=json.dumps({'schedule_outcome':'There were no delays', 'optional_comments':'Existing notes'}))
        db.session.add(draft); db.session.commit()
        self.assertEqual(self.draft().json['values']['optional_comments'], 'Existing notes')
        for share in [self.share, self.examiner_share]:
            html = self.client.get('/my-exam-sessions/' + share.token).get_data(as_text=True)
            self.assertNotIn('Staff member performance review', html)
        self.assertEqual(self.draft(self.examiner_url, changes={f'review.examiner:{self.examiner.id}.arrival':'Early enough'}).status_code, 403)
        other = m.AcademicStaff(full_name='Another Examiner', status='Active', roles='Examiner')
        db.session.add(other); db.session.flush()
        db.session.add(m.ExamSessionExaminerAssignment(exam_session_id=self.record.id, team_member_id=other.id, participation_status='Confirmed'))
        db.session.commit()
        html = self.client.get('/my-exam-sessions/' + self.examiner_share.token).get_data(as_text=True)
        self.assertIn('Staff member performance review', html)
        self.assertIn(f'name="review.examiner:{other.id}.arrival"', html)
        self.assertNotIn(f'name="review.examiner:{self.examiner.id}.arrival"', html)

    def test_remote_session_remains_pending_in_management_session_reports(self):
        from app.session_reports import load_report_rows
        # The report is now required even when all Supervisors are remote.
        rows = load_report_rows(2026)
        self.assertTrue(rows[0]['report_applicable'])
        self.assertIn(self.person.full_name, rows[0]['supervisors'])


    def test_confirmed_emergency_contact_does_not_enter_report_eligibility(self):
        person = m.AcademicStaff(full_name='Emergency contact', status='Active', roles='Emergency contact')
        db.session.add(person); db.session.flush()
        share = m.StaffExamSessionsShare(person_ref=str(person.id), token='emergency-contact-no-report')
        db.session.add(share); db.session.flush()
        self.record.emergency_contact_member_id = person.id
        self.record.emergency_contact_participation_status = 'Confirmed'
        submission = m.StaffExamSessionSubmission(exam_session_id=self.record.id, assignment_type='emergency_contact',
            assignment_id=self.record.id, share_id=share.id)
        db.session.add(submission); db.session.commit()
        from app.routes import staff_report_assignment_eligible
        self.assertFalse(staff_report_assignment_eligible(self.record, self.record, 'emergency_contact'))
        for session_format in ['Onsite', 'Online', 'Online at exam centre']:
            with self.subTest(session_format=session_format):
                self.record.format = session_format; db.session.commit()
                response = self.client.get('/my-exam-sessions/' + share.token)
                self.assertEqual(response.status_code, 200)
                self.assertNotIn('data-staff-exam-day-report', response.get_data(as_text=True))
                self.assertNotIn('data-staff-end-checks ', response.get_data(as_text=True))

    def test_role_labels_intro_and_readonly_blocks_match_each_actor(self):
        import re
        owners = {'schedule':'examiner', 'attendance':'supervisor', 'facilities':'examiner', 'materials':'examiner',
                  'emergency':'examiner', 'media':'examiner', 'feedback':'supervisor', 'return_materials':'examiner', 'comments':'examiner', 'return_materials_verification':'supervisor', 'package_review':'supervisor'}
        for actor, share, contact in [('supervisor', self.share, 'Examiner'), ('examiner', self.examiner_share, 'Remote supervisor')]:
            html = self.client.get('/my-exam-sessions/' + share.token).get_data(as_text=True)
            self.assertIn(f'<strong>This is a shared report.</strong> Please contact the {contact}', html)
            self.assertIn('<strong>You are only responsible for completing the sections labelled with your role.</strong>', html)
            for block, owner in owners.items():
                match = re.search(r'<li[^>]*data-report-block="' + block + r'"[^>]*>(.*?)\n\s*</li>', html, re.S)
                self.assertIsNotNone(match, block)
                self.assertEqual('disabled data-report-role-locked' in match.group(1), actor != owner, (actor, block))
            self.assertIn('The Remote supervisor is responsible for submitting this shared report', html)
            self.assertRegex(html, r'<button type="submit" class="primary-button" disabled>Submit report</button>')

    def test_instruction_changes_reopen_examiner_completion_and_cannot_be_overridden_at_submit(self):
        saved = self.complete_answers()
        self.assertTrue(saved['completion']['ready'])
        control = m.ExamSessionSinapsisControl.query.filter_by(exam_session_id=self.record.id).one()
        control.return_instructions_html = '<p>Updated return instructions.</p>'
        db.session.commit()
        self.assertFalse(self.draft().json['completion']['blocks']['return_materials'])
        response = self.post(shared_report_revision=str(saved['revision']), return_instructions_version='forged')
        self.assertEqual(response.status_code, 400)
        self.assertIn('return instructions', response.json['error'].lower())

    def test_marketing_upload_is_rejected_for_remote_supervisor(self):
        from io import BytesIO
        with patch('app.staff_report_media.upload_document') as upload:
            response = self.client.post(self.remote_url + '/media', data=dict(csrf_token='test', file=(BytesIO(b'photo'), 'photo.jpg')))
        self.assertEqual(response.status_code, 403)
        upload.assert_not_called()


    def test_supervisor_return_verification_is_required_saved_and_examiner_readonly(self):
        saved = self.complete_answers()
        self.assertTrue(saved['completion']['blocks']['return_materials_verification'])
        self.assertTrue(saved['completion']['ready'])
        values = saved['values']
        response = self.draft(changes={'return_materials_verified':[]}, base=values)
        self.assertEqual(response.status_code, 200, response.json)
        self.assertFalse(response.json['completion']['blocks']['return_materials_verification'])
        self.assertFalse(response.json['completion']['supervisor'])
        self.assertTrue(response.json['completion']['examiner'])
        self.assertFalse(response.json['completion']['ready'])
        self.assertEqual(self.draft(self.examiner_url, changes={'return_materials_verified':['1']}, base=response.json['values']).status_code, 403)
        # The final submit must read the shared draft, so a forged checked value cannot bypass this requirement.
        submitted = self.post(shared_report_revision=str(response.json['revision']), return_materials_verified='1')
        self.assertEqual(submitted.status_code, 400)
        self.assertIn('Return of materials verification', submitted.json['error'])
        response = self.draft(changes={'return_materials_verified':['1']}, base=response.json['values'])
        self.assertEqual(response.status_code, 200, response.json)
        submitted = self.post(shared_report_revision=str(response.json['revision']))
        self.assertEqual(submitted.status_code, 200, submitted.json)
        report = m.StaffExamSessionReport.query.one()
        self.assertTrue(json.loads(report.return_instructions_context)['supervisor_return_verified'])

    def test_return_verification_placement_and_exact_text(self):
        for share in [self.share, self.examiner_share]:
            html = self.client.get('/my-exam-sessions/' + share.token).get_data(as_text=True)
            self.assertLess(html.index('<b class="staff-report-check-title">Return of exam session materials</b>'), html.index('<b class="staff-report-check-title">Return of materials verification</b>'))
            self.assertLess(html.index('<b class="staff-report-check-title">Return of materials verification</b>'), html.index('<li data-report-stage="finish"'))
            self.assertIn('I confirm that I have reviewed the return instructions with the Examiner and verified that they understand the required procedures and deadlines.', html)
            self.assertIn('name="return_materials_verified" value="1" required', html)
        self.assignment.is_remote = False
        db.session.commit()
        html = self.client.get('/my-exam-sessions/' + self.share.token).get_data(as_text=True)
        self.assertNotIn('Return of materials verification', html)
        self.assertNotIn('name="return_materials_verified"', html)

    def test_package_review_is_supervisor_only_required_and_saved(self):
        saved = self.complete_answers()
        response = self.draft(changes={'return_package_reviewed':[]}, base=saved['values'])
        self.assertEqual(response.status_code, 200, response.json)
        self.assertFalse(response.json['completion']['blocks']['package_review'])
        self.assertFalse(response.json['completion']['supervisor'])
        self.assertFalse(response.json['completion']['ready'])
        self.assertTrue(response.json['completion']['examiner'])
        self.assertEqual(self.draft(self.examiner_url, changes={'return_package_reviewed':['1']}, base=response.json['values']).status_code, 403)
        submitted = self.post(shared_report_revision=str(response.json['revision']), return_package_reviewed='1')
        self.assertEqual(submitted.status_code, 400)
        self.assertIn('Exam return package review', submitted.json['error'])
        response = self.draft(changes={'return_package_reviewed':['1']}, base=response.json['values'])
        self.assertEqual(self.post(shared_report_revision=str(response.json['revision'])).status_code, 200)
        self.assertTrue(json.loads(m.StaffExamSessionReport.query.one().return_instructions_context)['supervisor_return_package_reviewed'])

    def test_package_review_placement_text_and_shared_only_scope(self):
        for share in [self.share, self.examiner_share]:
            html = self.client.get('/my-exam-sessions/' + share.token).get_data(as_text=True)
            self.assertLess(html.index('<b>Exam return package verification</b>'), html.index('>Exam return package review</b>'))
            self.assertLess(html.index('>Exam return package review</b>'), html.index("<label><b>Exam centre's facilities"))
            self.assertIn('<strong>This is a critical procedure to ensure the efficient handling and accurate sorting of completed examination papers.</strong>', html)
            self.assertIn('I confirm that I have carefully reviewed each step outlined in the section above with the Examiner and verified that all procedures have been correctly followed.', html)
            self.assertIn('name="return_package_reviewed" value="1" required', html)
        self.assignment.is_remote = False; db.session.commit()
        html = self.client.get('/my-exam-sessions/' + self.share.token).get_data(as_text=True)
        self.assertNotIn('>Exam return package review</b>', html)

    def test_feedback_heading_matches_recordings_visibility_and_title_style(self):
        url = '/my-exam-sessions/' + self.share.token
        html = self.client.get(url).get_data(as_text=True)
        self.assertIn('<b class="staff-report-check-title">Exam centre feedback</b>', html)
        db.session.add(m.ExamSessionMonthlyRegistration(exam_session_id=self.record.id, month=11, module='Speaking', registration_number=1))
        db.session.commit()
        html = self.client.get(url).get_data(as_text=True)
        self.assertIn('<b class="staff-report-check-title">Exam centre feedback and recordings verification</b>', html)
        self.assertIn('name="recordings_reminder_confirmed"', html)
