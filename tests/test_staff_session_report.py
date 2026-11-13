import os
import unittest
from datetime import date, datetime, timezone
from unittest.mock import patch
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'
from app import create_app, db
from app import models as m
from app.routes import staff_report_available


class StaffSessionReportTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config['TESTING'] = True
        self.context = self.app.app_context()
        self.context.push()
        db.drop_all()
        db.create_all()
        self.record = m.ExamSession(exam_session_name='Report session', category='Path School', status='Pending',
            session_date=date(2026, 11, 13), shifts='Morning', modules='Speaking', format='Onsite',
            session_pictures_folder_url='https://drive.google.com/drive/folders/testPicturesFolder123')
        self.person = m.AcademicStaff(full_name='Report Supervisor', status='Active', roles='Supervisor')
        db.session.add_all([self.record, self.person]); db.session.flush()
        self.assignment = m.ExamSessionSupervisorAssignment(exam_session_id=self.record.id, team_member_id=self.person.id,
            participation_status='Confirmed', is_remote=False)
        self.share = m.StaffExamSessionsShare(person_ref=str(self.person.id), token='report-test')
        db.session.add_all([self.assignment, self.share]); db.session.flush()
        self.submission = m.StaffExamSessionSubmission(exam_session_id=self.record.id, assignment_type='supervisor',
            assignment_id=self.assignment.id, share_id=self.share.id)
        db.session.add(self.submission); db.session.flush()
        db.session.add(m.StaffSessionReportMedia(submission_id=self.submission.id, file_id='initialMedia123', folder_id='testPicturesFolder123', filename='photo.jpg', mime_type='image/jpeg'))
        db.session.commit()
        self.client = self.app.test_client()
        with self.client.session_transaction() as state:
            state['csrf_token'] = 'test'
        self.url = f'/my-exam-sessions/{self.share.token}/submissions/{self.submission.id}/report'

    def tearDown(self):
        db.session.remove(); db.drop_all(); self.context.pop()

    def post(self, **values):
        data = dict(csrf_token='test', schedule_outcome='There were no delays', absent_candidates_checked='1', submitted_candidates_checked='1', facilities_outcome='Satisfactory', emergency_pack_outcome='No, it was not needed', marketing_confirmed='1', centre_feedback_confirmed='1')
        data['return_verification'] = ['submitted_papers', 'submitted_packages', 'absent_packages', 'sealing', 'labelling', 'institutional_verification']
        feedback_submitted = values.pop('_feedback_submitted', True)
        data.update(values)
        with patch('app.routes.staff_report_available', return_value=True), patch('app.routes.staff_report_feedback_submitted', return_value=feedback_submitted):
            return self.client.post(self.url, data=data)

    def test_midnight_boundaries_in_gmt_minus_three(self):
        for instant, expected in [('2026-11-13T02:59:59+00:00', False), ('2026-11-13T03:00:00+00:00', True),
                                  ('2026-11-14T02:59:59+00:00', True), ('2026-11-14T03:00:00+00:00', False)]:
            self.assertEqual(staff_report_available(self.record, datetime.fromisoformat(instant)), expected)

    def test_required_fields_and_single_immutable_submission(self):
        self.assertEqual(self.post(schedule_outcome='').status_code, 400)
        self.assertEqual(self.post(schedule_outcome='Other').status_code, 400)
        for outcome in ('The session finished ahead of schedule', 'There were minor delays', 'There were significant delays'):
            self.assertEqual(self.post(schedule_outcome=outcome, reasons='  ').status_code, 400)
        self.assertEqual(self.post(schedule_outcome='There were minor delays', reasons='Transport delay').status_code, 200)
        self.assertEqual(self.post(schedule_outcome='There were significant delays', reasons='Changed answer').status_code, 409)
        saved = m.StaffExamSessionReport.query.one()
        self.assertEqual(saved.schedule_outcome, 'There were minor delays')
        self.assertEqual(saved.reasons, 'Transport delay')

    def test_candidate_attendance_required_and_optional_checkboxes(self):
        for field in ('absent_candidates_checked', 'submitted_candidates_checked'):
            self.assertEqual(self.post(**{field: ''}).status_code, 400)
        self.assertEqual(m.StaffExamSessionReport.query.count(), 0)
        self.assertEqual(self.post().status_code, 200)
        saved = m.StaffExamSessionReport.query.one()
        self.assertTrue(saved.absent_candidates_checked)
        self.assertTrue(saved.submitted_candidates_checked)
        self.assertFalse(saved.session_completed_checked)

    def test_optional_session_completed_checkbox_is_saved(self):
        self.assertEqual(self.post(session_completed_checked='1').status_code, 200)
        self.assertTrue(m.StaffExamSessionReport.query.one().session_completed_checked)

    def test_facilities_outcome_and_comments_validation(self):
        self.assertEqual(self.post(facilities_outcome='').status_code, 400)
        self.assertEqual(self.post(facilities_outcome='Other').status_code, 400)
        for outcome in ('Satisfactory, with comments', 'Unsatisfactory'):
            self.assertEqual(self.post(facilities_outcome=outcome, facilities_comments='  ').status_code, 400)
        self.assertEqual(self.post(facilities_outcome='Satisfactory, with comments', facilities_comments='Room was noisy').status_code, 200)
        saved = m.StaffExamSessionReport.query.one()
        self.assertEqual(saved.facilities_outcome, 'Satisfactory, with comments')
        self.assertEqual(saved.facilities_comments, 'Room was noisy')

    def test_satisfactory_discards_hidden_comments(self):
        self.assertEqual(self.post(facilities_comments='Old hidden comment').status_code, 200)
        self.assertEqual(m.StaffExamSessionReport.query.one().facilities_comments, '')

    def test_emergency_pack_selection_and_required_reasons(self):
        for outcome in ('', 'Other'):
            self.assertEqual(self.post(emergency_pack_outcome=outcome).status_code, 400)
        for outcome in ('Yes, it was opened and used', 'It was opened but not used'):
            self.assertEqual(self.post(emergency_pack_outcome=outcome, emergency_pack_reasons='  ').status_code, 400)
        self.assertEqual(self.post(emergency_pack_outcome='It was opened but not used', emergency_pack_reasons='Opened to check contents').status_code, 200)
        saved = m.StaffExamSessionReport.query.one()
        self.assertEqual(saved.emergency_pack_outcome, 'It was opened but not used')
        self.assertEqual(saved.emergency_pack_reasons, 'Opened to check contents')

    def test_unused_emergency_pack_discards_hidden_reasons(self):
        self.assertEqual(self.post(emergency_pack_reasons='Old hidden reason').status_code, 200)
        self.assertEqual(m.StaffExamSessionReport.query.one().emergency_pack_reasons, '')

    def test_return_package_steps_are_all_required_in_order(self):
        steps = ['submitted_papers', 'submitted_packages', 'absent_packages', 'sealing', 'labelling', 'institutional_verification']
        for length in range(6):
            self.assertEqual(self.post(return_verification=steps[:length]).status_code, 400)
        self.assertEqual(self.post(return_verification=list(reversed(steps))).status_code, 400)
        self.assertEqual(self.post().status_code, 200)
        import json
        self.assertEqual(json.loads(m.StaffExamSessionReport.query.one().return_verification), steps)

    def review_people(self):
        examiner = m.AcademicStaff(full_name='Examiner Review', status='Active', roles='Examiner, Intern, Supervisor')
        intern = m.AcademicStaff(full_name='Intern Review', status='Active', roles='Intern, Examiner')
        db.session.add_all([examiner, intern]); db.session.flush()
        db.session.add_all([
            m.ExamSessionExaminerAssignment(exam_session_id=self.record.id, team_member_id=examiner.id),
            m.ExamSessionInternAssignment(exam_session_id=self.record.id, team_member_id=intern.id),
            m.ExamSessionInternAssignment(exam_session_id=self.record.id, team_member_id=examiner.id),
        ])
        db.session.commit()
        return examiner, intern

    def review_answers(self):
        from app.staff_report_review import assessment_roster, CRITERIA
        return {f"review.{row['key']}.{criterion['key']}": criterion['options'][0]
                for row in assessment_roster(self.record) for criterion in CRITERIA}

    def test_staff_review_roster_filters_roles_and_deduplicates(self):
        from app.staff_report_review import assessment_roster
        examiner, intern = self.review_people()
        db.session.add(m.ExamSessionExaminerAssignment(exam_session_id=self.record.id, team_member_id=examiner.id))
        db.session.add(m.ExamSessionInternAssignment(exam_session_id=self.record.id))
        other = m.ExamSession(exam_session_name='Other review session', category='Path School', status='Pending',
            session_date=date(2026, 11, 14), shifts='Morning', modules='Speaking', format='Onsite')
        db.session.add(other); db.session.flush()
        db.session.add(m.ExamSessionExaminerAssignment(exam_session_id=other.id, team_member_id=self.person.id))
        db.session.commit()
        roster = assessment_roster(self.record)
        self.assertEqual(len(roster), 3)
        self.assertEqual({(row['person_ref'], row['role']) for row in roster},
                         {(str(examiner.id), 'Examiner'), (str(examiner.id), 'Intern'), (str(intern.id), 'Intern')})
        self.assertNotIn(str(self.person.id), [row['person_ref'] for row in roster])
        self.assertEqual(len(assessment_roster(other)), 1)

    def test_staff_review_requires_seven_values_and_saves_individual_notes(self):
        import json
        examiner, intern = self.review_people()
        self.assertEqual(self.post().status_code, 400)
        answers = self.review_answers()
        field = f'review.examiner:{examiner.id}.arrival'
        self.assertEqual(self.post(**{**answers, field: 'Invalid'}).status_code, 400)
        for key in answers:
            self.assertEqual(self.post(**{**answers, key: ''}).status_code, 400)
        answers[f'review.examiner:{examiner.id}.notes'] = 'Helped candidates patiently'
        answers[f'review.intern:{intern.id}.notes'] = 'Helpful preparation'
        self.assertEqual(self.post(**answers).status_code, 200)
        rows = json.loads(m.StaffExamSessionReport.query.one().staff_assessments)
        self.assertEqual(len(rows), 3)
        self.assertTrue(all(row['exam_session_id'] == self.record.id for row in rows))
        self.assertTrue(all(len(row['criteria']) == 7 for row in rows))
        notes = {row['key']: row['notes'] for row in rows}
        self.assertEqual(notes[f'examiner:{examiner.id}'], 'Helped candidates patiently')
        self.assertEqual(notes[f'intern:{intern.id}'], 'Helpful preparation')
        self.assertEqual(notes[f'intern:{examiner.id}'], '')
        self.assertEqual(self.post(**{**answers, field: 'Too risky'}).status_code, 409)
        self.assertEqual(m.StaffExamSessionReport.query.count(), 1)

    def test_staff_review_current_roster_and_optional_notes(self):
        examiner, intern = self.review_people()
        answers = self.review_answers()
        db.session.add(m.ExamSessionExaminerAssignment(exam_session_id=self.record.id, team_member_id=self.person.id))
        db.session.commit()
        self.assertEqual(self.post(**answers).status_code, 400)
        self.assertEqual(self.post(**self.review_answers()).status_code, 200)

    def test_staff_review_matrix_renders_current_names_and_unselected_fields(self):
        examiner, intern = self.review_people()
        response = self.client.get(f'/my-exam-sessions/{self.share.token}?session_year=2026')
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        table = html.split('<table class="staff-report-review-table">', 1)[1].split('</table>', 1)[0]
        self.assertIn(examiner.full_name, table)
        self.assertIn(intern.full_name, table)
        self.assertEqual(table.count('data-review-row>'), 3)
        self.assertEqual(table.count('required data-review-select'), 21)
        self.assertIn('value="">Select</option>', table)
        self.assertNotIn(' selected', table)
        self.assertIn('0/3 completed', html)
        self.assertNotIn('No staff members to assess', html)

    def test_staff_review_empty_roster_is_complete(self):
        import json
        self.assertEqual(self.post().status_code, 200)
        self.assertEqual(json.loads(m.StaffExamSessionReport.query.one().staff_assessments), [])

    def test_marketing_requires_folder_upload_and_confirmation(self):
        self.assertEqual(self.post(marketing_confirmed='').status_code, 400)
        self.record.session_pictures_folder_url = ''
        db.session.commit()
        self.assertEqual(self.post().status_code, 400)
        self.record.session_pictures_folder_url = 'https://drive.google.com/drive/folders/anotherPictures123'
        db.session.commit()
        self.assertEqual(self.post().status_code, 400)
        self.record.session_pictures_folder_url = 'https://drive.google.com/drive/folders/testPicturesFolder123'
        m.StaffSessionReportMedia.query.delete()
        db.session.commit()
        self.assertEqual(self.post().status_code, 400)
        self.assertEqual(m.StaffExamSessionReport.query.count(), 0)

    def test_marketing_confirmation_and_uploaded_file_snapshot_saved(self):
        import json
        self.assertEqual(self.post().status_code, 200)
        saved = m.StaffExamSessionReport.query.one()
        self.assertTrue(saved.marketing_confirmed)
        self.assertEqual(json.loads(saved.marketing_media), ['initialMedia123'])

    def test_media_upload_uses_current_session_folder_and_locks_after_report(self):
        from io import BytesIO
        from app.google_drive import DriveStorageError
        media_url = self.url + '/media'
        def fake_upload(file, target, destination):
            self.assertEqual(destination.folder_id, 'testPicturesFolder123')
            self.assertEqual(target.submission_id, self.submission.id)
            document = m.StaffSessionReportMedia(submission_id=target.submission_id,
                file_id='uploadedFile123', folder_id=destination.folder_id, filename=file.filename, mime_type=file.mimetype)
            db.session.add(document)
            target.document = document
        def upload():
            return self.client.post(media_url, data={'csrf_token':'test', 'file':(BytesIO(b'photo'), 'new.jpg')})
        with patch('app.routes.staff_report_available', return_value=True), patch('app.staff_report_media.folder_metadata') as metadata, patch('app.staff_report_media.upload_document', side_effect=fake_upload):
            response = upload()
            self.assertEqual(response.status_code, 200)
            metadata.assert_called_once_with('testPicturesFolder123')
            self.assertEqual(len(response.json['files']), 2)
        with patch('app.routes.staff_report_available', return_value=True), patch('app.staff_report_media.folder_metadata', side_effect=DriveStorageError('No folder access')):
            self.assertEqual(upload().status_code, 502)
        self.assertEqual(m.StaffSessionReportMedia.query.count(), 2)
        self.assertEqual(self.post().status_code, 200)
        with patch('app.routes.staff_report_available', return_value=True), patch('app.staff_report_media.upload_document') as sender:
            self.assertEqual(upload().status_code, 409)
            sender.assert_not_called()

    def test_media_upload_authorization_and_missing_folder(self):
        from io import BytesIO
        def upload(token='test'):
            return self.client.post(self.url + '/media', data={'csrf_token':token, 'file':(BytesIO(b'x'), 'photo.jpg')})
        self.assertEqual(upload('bad').status_code, 400)
        with patch('app.routes.staff_report_available', return_value=False):
            self.assertEqual(upload().status_code, 403)
        with patch('app.routes.staff_report_available', return_value=True), patch('app.staff_report_media.upload_document') as sender:
            self.record.session_pictures_folder_url = ''
            db.session.commit()
            self.assertEqual(upload().status_code, 400)
            sender.assert_not_called()

    def test_feedback_must_actually_be_submitted_and_confirmed(self):
        from app.routes import staff_report_feedback_submitted
        self.assertFalse(staff_report_feedback_submitted(self.record))
        self.assertEqual(self.post(_feedback_submitted=False).status_code, 400)
        self.assertEqual(self.post(centre_feedback_confirmed='').status_code, 400)
        self.assertEqual(m.StaffExamSessionReport.query.count(), 0)
        self.assertEqual(self.post().status_code, 200)
        self.assertTrue(m.StaffExamSessionReport.query.one().centre_feedback_confirmed)

    def test_recordings_reminder_required_only_with_applicable_candidates(self):
        for module in ('Speaking', 'Listening and speaking'):
            m.ExamSessionMonthlyRegistration.query.delete()
            db.session.add(m.ExamSessionMonthlyRegistration(exam_session_id=self.record.id, month=11, module=module, registration_number=1))
            db.session.commit()
            self.assertEqual(self.post().status_code, 400)
        self.assertEqual(self.post(recordings_reminder_confirmed='1').status_code, 200)
        self.assertTrue(m.StaffExamSessionReport.query.one().recordings_reminder_confirmed)

    def test_recordings_reminder_not_required_for_zero_or_other_modules(self):
        db.session.add_all([
            m.ExamSessionMonthlyRegistration(exam_session_id=self.record.id, month=11, module='Speaking', registration_number=0),
            m.ExamSessionMonthlyRegistration(exam_session_id=self.record.id, month=11, module='Reading and writing', registration_number=10)])
        db.session.commit()
        self.assertEqual(self.post().status_code, 200)
        self.assertFalse(m.StaffExamSessionReport.query.one().recordings_reminder_confirmed)

    def test_final_checks_feedback_badge_and_conditional_recording_display(self):
        url = f'/my-exam-sessions/{self.share.token}?session_year=2026'
        response = self.client.get(url)
        html = response.get_data(as_text=True)
        self.assertIn('Feedback form not submitted', html)
        self.assertIn('data-submitted="false" disabled', html)
        self.assertNotIn('name="recordings_reminder_confirmed"', html)
        db.session.add(m.ExamSessionMonthlyRegistration(exam_session_id=self.record.id, month=11, module='Speaking', registration_number=1))
        db.session.commit()
        with patch('app.routes.staff_report_feedback_submitted', return_value=True):
            html = self.client.get(url).get_data(as_text=True)
        self.assertIn('Feedback form submitted', html)
        self.assertIn('name="recordings_reminder_confirmed"', html)
        self.assertIn('within two business days after the exam session', html)

    def test_old_end_checks_removed_only_for_nonremote_onsite_supervisors(self):
        url = f'/my-exam-sessions/{self.share.token}?session_year=2026'
        html = self.client.get(url).get_data(as_text=True)
        self.assertNotIn('data-staff-end-checks ', html)
        self.assertIn('data-staff-exam-day-report', html)
        self.assertIn('data-report-availability', html)
        self.assignment.is_remote = True
        db.session.commit()
        html = self.client.get(url).get_data(as_text=True)
        self.assertIn('data-staff-end-checks ', html)
        self.assertNotIn('data-staff-exam-day-report', html)
        self.assignment.is_remote = False
        self.record.format = 'Online'
        db.session.commit()
        html = self.client.get(url).get_data(as_text=True)
        self.assertIn('data-staff-end-checks ', html)
        self.assertNotIn('data-staff-exam-day-report', html)

    def test_optional_comments_saved_and_locked(self):
        self.assertEqual(self.post(optional_comments='  More preparation time would help.  ').status_code, 200)
        self.assertEqual(m.StaffExamSessionReport.query.one().optional_comments, 'More preparation time would help.')
        self.assertEqual(self.post(optional_comments='Changed').status_code, 409)
        self.assertEqual(m.StaffExamSessionReport.query.one().optional_comments, 'More preparation time would help.')

    def test_optional_comments_can_be_empty_but_not_excessively_long(self):
        self.assertEqual(self.post(optional_comments='x' * 10001).status_code, 400)
        self.assertEqual(self.post(optional_comments='').status_code, 200)
        self.assertEqual(m.StaffExamSessionReport.query.one().optional_comments, '')

    def test_no_delays_does_not_save_hidden_reasons(self):
        self.assertEqual(self.post(reasons='Old hidden answer').status_code, 200)
        self.assertEqual(m.StaffExamSessionReport.query.one().reasons, '')

    def test_ahead_of_schedule_saves_required_reasons(self):
        self.assertEqual(self.post(schedule_outcome='The session finished ahead of schedule', reasons='All candidates finished early').status_code, 200)
        self.assertEqual(m.StaffExamSessionReport.query.one().reasons, 'All candidates finished early')

    def test_authorization_date_and_csrf(self):
        self.assertEqual(self.post(csrf_token='bad').status_code, 400)
        with patch('app.routes.staff_report_available', return_value=False):
            self.assertEqual(self.client.post(self.url, data=dict(csrf_token='test', schedule_outcome='There were no delays')).status_code, 403)
        self.assignment.is_remote = True; db.session.commit()
        self.assertEqual(self.post().status_code, 403)
        self.assignment.is_remote = False
        self.assignment.participation_status = 'Pending'; db.session.commit()
        self.assertEqual(self.post().status_code, 403)
        self.assignment.participation_status = 'Confirmed'
        self.record.format = 'Online'; db.session.commit()
        self.assertEqual(self.post().status_code, 403)
        self.record.format = 'Onsite'
        self.share.person_ref = '99999'; db.session.commit()
        self.assertEqual(self.post().status_code, 404)
        self.assertEqual(m.StaffExamSessionReport.query.count(), 0)

    def test_portal_shows_form_and_locks_after_submission(self):
        with patch('app.routes.staff_report_available', return_value=True):
            response = self.client.get(f'/my-exam-sessions/{self.share.token}?session_year=2026')
        self.assertEqual(response.status_code, 200)
        self.assertIn('data-session-report-dialog', response.get_data(as_text=True))
        self.assertIn('Did the exam session run according to the approved schedule?', response.get_data(as_text=True))
        self.post()
        response = self.client.get(f'/my-exam-sessions/{self.share.token}?session_year=2026')
        self.assertIn('Report submitted', response.get_data(as_text=True))
