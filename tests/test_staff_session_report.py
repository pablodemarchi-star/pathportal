import os
import re
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
            digitalised_exams_url='https://drive.google.com/drive/folders/testDigitalised123',
            session_pictures_folder_url='https://drive.google.com/drive/folders/testPicturesFolder123')
        self.person = m.AcademicStaff(full_name='Report Supervisor', status='Active', roles='Supervisor')
        db.session.add_all([self.record, self.person]); db.session.flush()
        self.assignment = m.ExamSessionSupervisorAssignment(exam_session_id=self.record.id, team_member_id=self.person.id,
            participation_status='Confirmed', is_remote=False, is_shipment_recipient=True)
        self.share = m.StaffExamSessionsShare(person_ref=str(self.person.id), token='report-test')
        db.session.add_all([self.assignment, self.share]); db.session.flush()
        self.submission = m.StaffExamSessionSubmission(exam_session_id=self.record.id, assignment_type='supervisor',
            assignment_id=self.assignment.id, share_id=self.share.id)
        db.session.add(self.submission); db.session.flush()
        db.session.add(m.StaffSessionReportMedia(submission_id=self.submission.id, file_id='initialMedia123', folder_id='testPicturesFolder123', filename='photo.jpg', mime_type='image/jpeg'))
        control = m.ExamSessionSinapsisControl.query.filter_by(exam_session_id=self.record.id).first()
        if control is None:
            control = m.ExamSessionSinapsisControl(exam_session_id=self.record.id)
            db.session.add(control)
        control.return_materials_method = 'location_drop_off'
        control.return_drop_off_address_url = 'https://maps.example.com/materials-return'
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
        from app.routes import staff_report_online_attendance_fields, staff_report_module_sections
        for field in staff_report_online_attendance_fields(self.record):
            data[field] = '1'
        for section in staff_report_module_sections(self.record):
            for field in section['fields']:
                data[field] = '1'
        if self.record.format == 'Online':
            data['recordings_reminder_confirmed'] = '1'
            data['it_issues'] = '0'
        from app.staff_report_components import applicable
        if applicable(self.record):
            data['component_completion'] = 'complete'
        if self.record.format == 'Onsite':
            from app.staff_return_materials import report_return_view
            from app.routes import staff_submission_assignment
            target = db.session.get(m.StaffExamSessionSubmission, int(self.url.split('/')[-2]))
            target_assignment, _ = staff_submission_assignment(self.record, target.assignment_type, target.assignment_id)
            with self.app.test_request_context():
                info = report_return_view(self.record, target_assignment, target.share)
            data.update(return_instructions_confirmed='1', return_instructions_version=info['version'])
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
        from app.staff_report_review import assessment_roster, assessment_criteria
        return {f"review.{row['key']}.{criterion['key']}": ('Satisfactory' if criterion['key'] == 'overall' else 'Proficient' if criterion['key'] == 'it_skills' else criterion['options'][0])
                for row in assessment_roster(self.record) for criterion in assessment_criteria(self.record)}

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

    def test_online_final_checks_follow_session_modules(self):
        self.record.format = 'Online'
        for modules, visible in [('Reading and writing', False), ('Speaking', True), ('Listening and speaking', True)]:
            self.record.modules = modules; db.session.commit()
            html = self.client.get(f'/my-exam-sessions/{self.share.token}?session_year=2026').get_data(as_text=True)
            self.assertNotIn('name="centre_feedback_confirmed"', html)
            self.assertNotIn('Feedback form not submitted', html)
            self.assertNotIn('I confirm that the exam centre has submitted its feedback form.', html)
            self.assertEqual('<b>Final checks</b>' in html, visible)
            self.assertEqual('name="recordings_reminder_confirmed"' in html, visible)
        self.assertEqual(self.post(recordings_reminder_confirmed='0').status_code, 400)
        self.record.modules = 'Reading and writing'; db.session.commit()
        response = self.post(recordings_reminder_confirmed='0', centre_feedback_confirmed='', _feedback_submitted=False)
        self.assertEqual(response.status_code, 200, response.json)
        saved = m.StaffExamSessionReport.query.one()
        self.assertFalse(saved.recordings_reminder_confirmed)
        self.assertFalse(saved.centre_feedback_confirmed)

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

    def test_old_end_checks_replaced_for_all_onsite_supervisors(self):
        url = f'/my-exam-sessions/{self.share.token}?session_year=2026'
        html = self.client.get(url).get_data(as_text=True)
        self.assertNotIn('data-staff-end-checks ', html)
        self.assertIn('data-staff-exam-day-report', html)
        self.assertIn('data-report-availability', html)
        self.assignment.is_remote = True
        db.session.commit()
        html = self.client.get(url).get_data(as_text=True)
        self.assertNotIn('data-staff-end-checks ', html)
        self.assertIn('data-staff-exam-day-report', html)
        self.assignment.is_remote = False
        self.record.format = 'Online'
        db.session.commit()
        html = self.client.get(url).get_data(as_text=True)
        self.assertNotIn('data-staff-end-checks ', html)
        self.assertIn('data-staff-exam-day-report', html)

    def test_guided_layout_supports_each_format_and_keeps_all_report_controls(self):
        url=f'/my-exam-sessions/{self.share.token}?session_year=2026'
        onsite=self.client.get(url).get_data(as_text=True)
        self.assertNotIn(' data-online-report-flow',onsite)
        self.assertIn(' data-onsite-report-flow',onsite)
        for key in ('session', 'centre', 'materials', 'team', 'media', 'checks', 'finish'):
            self.assertIn('data-report-stage="'+key+'"', onsite)
        for key in ('schedule_outcome', 'absent_candidates_checked', 'submitted_candidates_checked',
                    'facilities_outcome', 'facilities_comments', 'emergency_pack_outcome',
                    'emergency_pack_reasons', 'return_verification', 'marketing_confirmed',
                    'centre_feedback_confirmed', 'optional_comments'):
            self.assertIn('name="'+key+'"', onsite)
        self.assertNotIn('data-add-consideration', onsite)
        self.assertNotIn('data-report-stage="candidates"', onsite)
        self.assertNotIn('data-report-stage="modules"', onsite)
        self.record.format='Online';self.record.modules='Speaking,Listening and speaking,Reading and writing';db.session.commit()
        online=self.client.get(url).get_data(as_text=True)
        self.assertIn(' data-online-report-flow',online)
        for key in ('session','modules','candidates','team','finish'):
            self.assertIn('data-report-stage="'+key+'"',online)
        for key in ('schedule_outcome','absent_candidates_checked','submitted_candidates_checked','rw_files_uploaded_checked','listening_files_uploaded_checked','examiner_marks_checked','component_completion','it_issues','optional_comments','comments_speaking','comments_listening','comments_reading_writing'):
            self.assertIn('name="'+key+'"',online)
        self.assertIn('all modules of the exam session have concluded',online)
        self.assertIn('js/staff_report_flow.js',online)
        self.assertLess(online.index('js/staff_session_report.js'),online.index('js/staff_report_flow.js'))

    def test_online_comment_columns_follow_session_modules(self):
        for modules, expected in [('Speaking', {'speaking'}), ('Listening and speaking', {'speaking','listening'}),
                                  ('Reading and writing', {'reading_writing'}), ('Speaking,Listening and speaking,Reading and writing', {'speaking','listening','reading_writing'}), ('', set())]:
            self.record.format='Online';self.record.modules=modules;db.session.commit()
            html=self.client.get(f'/my-exam-sessions/{self.share.token}?session_year=2026').get_data(as_text=True)
            self.assertIn('aria-label="Overall comments"',html)
            self.assertNotIn('name="optional_comments" rows="5" maxlength="10000" required',html)
            for key in ('speaking','listening','reading_writing'):
                self.assertEqual('name="comments_'+key+'"' in html,key in expected)
        self.record.format='Onsite';self.record.modules='Speaking';db.session.commit()
        html=self.client.get(f'/my-exam-sessions/{self.share.token}?session_year=2026').get_data(as_text=True)
        self.assertNotIn('staff-report-comments-grid',html)
        self.assertIn('name="optional_comments"',html)

    def test_online_module_comments_are_saved_separately_and_locked(self):
        import json
        self.record.format='Online';self.record.modules='Listening and speaking,Reading and writing';db.session.commit()
        response=self.post(comments_speaking=' Speaking notes ',comments_listening='Listening notes',comments_reading_writing='RW notes',optional_comments='Overall notes')
        self.assertEqual(response.status_code,200,response.json)
        report=m.StaffExamSessionReport.query.one()
        self.assertEqual(json.loads(report.module_comments),dict(speaking='Speaking notes',listening='Listening notes',reading_writing='RW notes',overall='Overall notes'))
        self.assertEqual(report.optional_comments,'Overall notes')
        self.assertEqual(self.post(comments_speaking='Changed').status_code,409)
        self.assertEqual(json.loads(report.module_comments)['speaking'],'Speaking notes')

    def test_online_module_comments_are_optional_and_validate_only_visible_fields(self):
        import json
        self.record.format='Online';self.record.modules='Speaking';db.session.commit()
        self.assertEqual(self.post(comments_speaking='x'*10001).status_code,400)
        self.assertEqual(self.post(comments_listening='x'*10001,comments_reading_writing='forged hidden comment').status_code,200)
        self.assertEqual(json.loads(m.StaffExamSessionReport.query.one().module_comments),dict(speaking='',overall=''))

    def test_optional_comments_saved_and_locked(self):
        self.assertEqual(self.post(optional_comments='  More preparation time would help.  ').status_code, 200)
        self.assertEqual(m.StaffExamSessionReport.query.one().optional_comments, 'More preparation time would help.')
        self.assertEqual(self.post(optional_comments='Changed').status_code, 409)
        self.assertEqual(m.StaffExamSessionReport.query.one().optional_comments, 'More preparation time would help.')

    def test_optional_comments_can_be_empty_but_not_excessively_long(self):
        self.assertEqual(self.post(optional_comments='x' * 10001).status_code, 400)
        self.assertEqual(self.post(optional_comments='').status_code, 200)
        self.assertEqual(m.StaffExamSessionReport.query.one().optional_comments, '')

    def second_supervisor(self):
        person=m.AcademicStaff(full_name='Second Supervisor',status='Active',roles='Supervisor')
        db.session.add(person);db.session.flush()
        assignment=m.ExamSessionSupervisorAssignment(exam_session_id=self.record.id,team_member_id=person.id,participation_status='Confirmed')
        share=m.StaffExamSessionsShare(person_ref=str(person.id),token='second-supervisor')
        db.session.add_all([assignment,share]);db.session.flush()
        submission=m.StaffExamSessionSubmission(exam_session_id=self.record.id,share_id=share.id,assignment_type='supervisor',assignment_id=assignment.id)
        db.session.add(submission);db.session.commit()
        return person,share,submission

    def test_report_and_uploaded_material_are_shared_by_session(self):
        from app.staff_report_media import media_for_submission
        person,share,submission=self.second_supervisor()
        self.assertEqual(len(media_for_submission(self.record,submission)),1)
        first_url=self.url
        self.url=f'/my-exam-sessions/{share.token}/submissions/{submission.id}/report'
        self.assertEqual(self.post().status_code,200)
        saved=m.StaffExamSessionReport.query.one()
        self.assertEqual(saved.exam_session_id,self.record.id)
        self.assertEqual(saved.author_name,person.full_name)
        self.assertEqual(saved.author_person_ref,str(person.id))
        self.url=first_url
        self.assertEqual(self.post().status_code,409)
        for staff_share in (self.share,share):
            html=self.client.get(f'/my-exam-sessions/{staff_share.token}?session_year=2026').get_data(as_text=True)
            self.assertIn('Report submitted',html)
        response=self.client.get(first_url+'/feedback-status')
        self.assertTrue(response.json['report_submitted'])
        self.assertEqual(response.json['author_name'],person.full_name)
        from io import BytesIO
        with patch('app.routes.staff_report_available',return_value=True), patch('app.staff_report_media.upload_document') as upload:
            response=self.client.post(first_url+'/media',data={'csrf_token':'test','file':(BytesIO(b'x'),'blocked.jpg')})
            self.assertEqual(response.status_code,409)
            upload.assert_not_called()

    def test_database_prevents_second_report_for_same_session(self):
        from sqlalchemy.exc import IntegrityError
        person,share,submission=self.second_supervisor()
        self.assertEqual(self.post().status_code,200)
        db.session.add(m.StaffExamSessionReport(exam_session_id=self.record.id,submission_id=submission.id,schedule_outcome='There were no delays'))
        with self.assertRaises(IntegrityError): db.session.commit()
        db.session.rollback()
        self.assertEqual(m.StaffExamSessionReport.query.count(),1)

    def test_online_review_criteria_and_required_comments(self):
        import json
        from app.staff_report_review import assessment_criteria
        self.record.format = 'Online'
        examiner, intern = self.review_people()
        criteria = {item['key']: item for item in assessment_criteria(self.record)}
        self.assertEqual(criteria['exam_environment']['options'], ['Appropriate', 'Inappropriate'])
        self.assertEqual(criteria['it_skills']['options'], ['Limited', 'Adequate', 'Proficient'])
        self.assertNotIn('staff_id', criteria)
        self.assertNotIn('language', criteria)
        html = self.client.get(f'/my-exam-sessions/{self.share.token}?session_year=2026').get_data(as_text=True)
        self.assertIn('Comment on Exam environment', html)
        self.assertIn('Comment on IT skills', html)
        answers = self.review_answers()
        prefix = f'review.examiner:{examiner.id}.'
        for key, value in [('exam_environment', 'Inappropriate'), ('it_skills', 'Limited')]:
            for comment in ('', '  '):
                response = self.post(**{**answers, prefix + key: value, prefix + 'comments.' + key: comment})
                self.assertEqual(response.status_code, 400)
                self.assertIn(criteria[key]['comment_title'], response.json['error'])
        self.assertEqual(self.post(**{**answers, prefix + 'exam_environment': 'Worn'}).status_code, 400)
        self.assertEqual(self.post(**{**answers, prefix + 'it_skills': 'English'}).status_code, 400)
        answers.update({prefix + 'exam_environment': 'Inappropriate', prefix + 'comments.exam_environment': 'Unsuitable room',
                        prefix + 'it_skills': 'Limited', prefix + 'comments.it_skills': 'Needed technical help'})
        self.assertEqual(self.post(**answers).status_code, 200)
        reviews = json.loads(m.StaffExamSessionReport.query.one().staff_assessments)
        reviewed = next(row for row in reviews if row['key'] == f'examiner:{examiner.id}')
        self.assertEqual(reviewed['comments']['it_skills'], 'Needed technical help')
        self.assertEqual(reviewed['criteria']['exam_environment'], 'Inappropriate')

    def test_criterion_specific_comments_required_for_each_negative_selection(self):
        from app.staff_report_review import COMMENT_RULES
        examiner, intern=self.review_people()
        answers=self.review_answers()
        prefix=f'review.examiner:{examiner.id}.'
        for key,(title,options) in COMMENT_RULES.items():
            for option in options:
                case_answers = {**answers, prefix + key: option}
                if key == 'overall':
                    case_answers[prefix + 'attitude'] = 'Satisfactory'
                response=self.post(**case_answers)
                self.assertEqual(response.status_code,400)
                self.assertIn(title,response.json['error'])
                self.assertEqual(self.post(**{**case_answers,prefix+'comments.'+key:'  '}).status_code,400)
        self.assertEqual(m.StaffExamSessionReport.query.count(),0)
        for key,(title,options) in COMMENT_RULES.items():
            answers[prefix+key]=options[0]
            answers[prefix+'comments.'+key]='Explanation for '+key
        response=self.post(**answers)
        self.assertEqual(response.status_code,200)
        import json
        assessments=json.loads(m.StaffExamSessionReport.query.one().staff_assessments)
        reviewed=next(row for row in assessments if row['key']==f'examiner:{examiner.id}')
        self.assertEqual(reviewed['comments'],{key:'Explanation for '+key for key in COMMENT_RULES})
        self.assertEqual(reviewed['notes'],'')
        for row in assessments:
            if row['key']!=reviewed['key']:self.assertEqual(row['comments'],{})

    def test_untriggered_comments_remain_optional_and_are_not_submitted(self):
        examiner,intern=self.review_people()
        answers=self.review_answers()
        answers[f'review.examiner:{examiner.id}.comments.arrival']='Earlier note no longer applicable'
        self.assertEqual(self.post(**answers).status_code,200)
        import json
        self.assertTrue(all(not row['comments'] for row in json.loads(m.StaffExamSessionReport.query.one().staff_assessments)))

    def test_zip_upload_saves_each_photo_and_video_as_a_separate_document(self):
        from io import BytesIO
        from zipfile import ZipFile
        content=BytesIO()
        with ZipFile(content,'w') as archive:
            archive.writestr('photos/Foto 1.jpg',b'photo bytes')
            archive.writestr('videos/Video 1.mp4',b'video bytes')
            archive.writestr('__MACOSX/._Foto 1.jpg',b'metadata')
        content.seek(0)
        saved=[]
        def fake_upload(file,target,destination):
            saved.append((file.filename,file.read()))
            db.session.add(m.StaffSessionReportMedia(submission_id=target.submission_id,file_id=f'zip-file-{len(saved)}',folder_id=destination.folder_id,filename=file.filename,mime_type=file.mimetype))
        with patch('app.routes.staff_report_available',return_value=True),patch('app.staff_report_media.folder_metadata'),patch('app.staff_report_media.upload_document',side_effect=fake_upload):
            response=self.client.post(self.url+'/media',data={'csrf_token':'test','file':(content,'session.zip')})
        self.assertEqual(response.status_code,200)
        self.assertEqual(saved,[('Foto 1.jpg',b'photo bytes'),('Video 1.mp4',b'video bytes')])
        self.assertEqual(len(response.json['files']),3)
        self.assertTrue(all(not item['filename'].endswith('.zip') for item in response.json['files']))

    def test_zip_failure_rolls_back_all_new_media_records(self):
        from io import BytesIO
        from zipfile import ZipFile
        content=BytesIO()
        with ZipFile(content,'w') as archive:
            archive.writestr('one.jpg',b'photo')
            archive.writestr('broken.zip',b'not a zip')
        content.seek(0)
        def fake_upload(file,target,destination):
            db.session.add(m.StaffSessionReportMedia(submission_id=target.submission_id,file_id='must-rollback',folder_id=destination.folder_id,filename=file.filename,mime_type=file.mimetype))
        with patch('app.routes.staff_report_available',return_value=True),patch('app.staff_report_media.folder_metadata'),patch('app.staff_report_media.upload_document',side_effect=fake_upload):
            response=self.client.post(self.url+'/media',data={'csrf_token':'test','file':(content,'broken-export.zip')})
        self.assertEqual(response.status_code,400)
        self.assertEqual(m.StaffSessionReportMedia.query.count(),1)
        self.assertIsNone(m.StaffSessionReportMedia.query.filter_by(file_id='must-rollback').first())

    def test_invalid_zip_does_not_register_any_media(self):
        from io import BytesIO
        with patch('app.routes.staff_report_available',return_value=True),patch('app.staff_report_media.folder_metadata'),patch('app.staff_report_media.upload_document') as upload:
            response=self.client.post(self.url+'/media',data={'csrf_token':'test','file':(BytesIO(b'invalid archive'),'bad.zip')})
        self.assertEqual(response.status_code,400)
        upload.assert_not_called()
        self.assertEqual(m.StaffSessionReportMedia.query.count(),1)

    def test_pdf_is_not_accepted_as_marketing_photos_or_videos(self):
        from io import BytesIO
        for filename in ('document.pdf', 'photo.jpg'):
            with self.subTest(filename=filename), patch('app.routes.staff_report_available',return_value=True), patch('app.staff_report_media.folder_metadata'), patch('app.staff_report_media.upload_document') as upload:
                response=self.client.post(self.url+'/media',data={'csrf_token':'test','file':(BytesIO(b'%PDF-1.4 linked folder'),filename)})
                self.assertEqual(response.status_code,400)
                self.assertIn('original photos and videos',response.json['error'])
                upload.assert_not_called()
                self.assertEqual(m.StaffSessionReportMedia.query.count(),1)

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
        self.assertEqual(self.post().status_code, 409)  # Shared reports require the currently displayed draft revision.
        self.assignment.is_remote = False
        self.assignment.participation_status = 'Pending'; db.session.commit()
        self.assertEqual(self.post().status_code, 403)
        self.assignment.participation_status = 'Confirmed'
        self.record.format = 'Online at exam centre'; db.session.commit()
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


    def test_online_supervisor_report_only_available_on_exam_day(self):
        self.record.format = 'Online'; db.session.commit()
        for instant, expected in [('2026-11-13T02:59:59+00:00', False), ('2026-11-13T03:00:00+00:00', True),
                                  ('2026-11-14T02:59:59+00:00', True), ('2026-11-14T03:00:00+00:00', False)]:
            moment = datetime.fromisoformat(instant)
            self.assertEqual(staff_report_available(self.record, moment), expected)
            with patch('app.routes.datetime', wraps=datetime) as clock:
                clock.now.side_effect = lambda tz=None: moment.astimezone(tz) if tz else moment.replace(tzinfo=None)
                html = self.client.get(f'/my-exam-sessions/{self.share.token}?session_year=2026').get_data(as_text=True)
                self.assertNotIn('data-report-date-unrestricted="true"', html)
                self.assertIn('on the exam day only', html)
                self.assertEqual(bool(re.search(r'data-exam-day-report-link[^>]*aria-disabled="true"', html)), not expected)
                if not expected:
                    self.assertEqual(self.client.post(self.url, data={'csrf_token': 'test'}).status_code, 403)
        feedback = self.client.get(self.url + '/feedback-status')
        self.assertEqual(feedback.status_code, 200)
        self.assertFalse(feedback.json['report_submitted'])
        self.assertTrue(feedback.json['files'])

    def test_online_report_keeps_validation_and_single_submission(self):
        self.record.format = 'Online'; db.session.commit()
        self.assertEqual(self.post(recordings_reminder_confirmed='0').status_code, 400)
        self.assertEqual(self.post(_feedback_submitted=False, centre_feedback_confirmed='').status_code, 200)
        self.assertEqual(m.StaffExamSessionReport.query.count(), 1)
        self.assertEqual(self.post().status_code, 409)
        html = self.client.get(f'/my-exam-sessions/{self.share.token}?session_year=2026').get_data(as_text=True)
        self.assertIn('Report submitted', html)
        self.assertRegex(html, r'data-exam-day-report-link[^>]*aria-disabled="true"')

    def test_online_report_no_longer_accepts_marketing_uploads(self):
        from io import BytesIO
        self.record.format = 'Online'; db.session.commit()
        with patch('app.staff_report_media.folder_metadata'), patch('app.staff_report_media.upload_document') as sender:
            response = self.client.post(self.url + '/media', data=dict(csrf_token='test', file=(BytesIO(b'picture'), 'photo.jpg')))
        self.assertEqual(response.status_code, 403)
        sender.assert_not_called()

    def test_online_report_keeps_validation_feedback_and_submission_lock(self):
        self.record.format = 'Online'
        self.record.session_date = date(2099, 1, 1)
        db.session.commit()
        response = self.client.post(self.url, data={'csrf_token': 'test'})
        self.assertEqual(response.status_code, 403)
        feedback = self.client.get(self.url + '/feedback-status')
        self.assertEqual(feedback.status_code, 200)
        self.assertEqual(self.post(recordings_reminder_confirmed='0').status_code, 400)
        self.assertEqual(self.post(_feedback_submitted=False, centre_feedback_confirmed='').status_code, 200)
        self.assertEqual(self.post().status_code, 409)

    def test_online_module_sections_follow_modules(self):
        cases = [('Reading and writing', [True, False, False]),
                 ('Listening and speaking', [False, True, True]), ('Speaking', [False, False, True])]
        titles = ['Reading and Writing module verification', 'Listening component verifications', 'Speaking component verifications']
        for modules, expected in cases:
            self.record.format = 'Online'; self.record.modules = modules; db.session.commit()
            html = self.client.get(f'/my-exam-sessions/{self.share.token}?session_year=2026').get_data(as_text=True)
            for title, visible in zip(titles, expected):
                self.assertEqual(title in html, visible)
                if visible:
                    self.assertGreater(html.index('<b>' + title + '</b>'), html.index('<b>Candidate attendance</b>'))
            if expected[0] or expected[1]:
                self.assertIn(self.record.digitalised_exams_url, html)
        self.record.format = 'Onsite'; db.session.commit()
        html = self.client.get(f'/my-exam-sessions/{self.share.token}?session_year=2026').get_data(as_text=True)
        for title in titles:
            self.assertNotIn(title, html)

    def test_online_module_checks_required_and_saved(self):
        from app.routes import MODULE_VERIFICATION_FIELDS
        self.record.format = 'Online'; self.record.modules = 'Reading and writing,Listening and speaking'; db.session.commit()
        for field in MODULE_VERIFICATION_FIELDS:
            self.assertEqual(self.post(**{field: '0'}).status_code, 400, field)
        self.assertEqual(self.post().status_code, 200)
        saved = m.StaffExamSessionReport.query.one()
        for field in MODULE_VERIFICATION_FIELDS:
            self.assertTrue(getattr(saved, field), field)

    def test_online_speaking_records_use_uploaded_examiner_files(self):
        self.record.format = 'Online'
        examiner, _ = self.review_people()
        db.session.add(m.ExaminerSpeakingRecord(exam_session_id=self.record.id,
            person_ref=f'staff:{examiner.id}', file_id='examinerFile123', folder_id='folder123',
            filename='Speaking.xlsx', mime_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'))
        db.session.commit()
        html = self.client.get(f'/my-exam-sessions/{self.share.token}?session_year=2026').get_data(as_text=True)
        speaking_section = html.split('<b>Speaking component verifications</b>', 1)[1].split('</li>\n              ', 1)[0]
        self.assertIn(examiner.full_name, speaking_section)
        self.assertIn('https://drive.google.com/file/d/examinerFile123/view', speaking_section)
        self.assertIn('target="_blank"', speaking_section)

    def test_online_module_folder_required(self):
        self.record.format = 'Online'; self.record.modules = 'Reading and writing'
        self.record.digitalised_exams_url = None; db.session.commit()
        html = self.client.get(f'/my-exam-sessions/{self.share.token}?session_year=2026').get_data(as_text=True)
        self.assertIn('data-report-records-folder-missing', html)
        response = self.post()
        self.assertEqual(response.status_code, 400)
        self.assertIn('Digitalised exams', response.json['error'])
        self.assertEqual(m.StaffExamSessionReport.query.count(), 0)

    def test_online_attendance_fields_follow_modules_and_preserve_onsite_text(self):
        cases = [('Online', 'Speaking', True, False), ('Online', 'Listening and speaking', True, True),
                 ('Online', 'Reading and writing', False, False), ('Onsite', 'Listening and speaking', False, False)]
        for format_name, modules, speaking, components in cases:
            with self.subTest(format=format_name, modules=modules):
                self.record.format = format_name; self.record.modules = modules; db.session.commit()
                html = self.client.get(f'/my-exam-sessions/{self.share.token}?session_year=2026').get_data(as_text=True)
                self.assertNotIn('name="speaking_records_checked"', html)
                self.assertNotIn('name="listening_speaking_components_checked"', html)
                self.assertEqual('name="component_completion"' in html, components)
                self.assertEqual('in Sinapsis and on the printed candidate list.' in html, format_name == 'Onsite')
                if speaking:
                    self.assertIn('name="examiner_marks_checked" value="1" required', html)
                    self.assertIn('with all statuses matching those recorded in Sinapsis.', html)
                if components:
                    self.assertIn('name="component_completion" value="complete" required', html)
                    self.assertGreater(html.index('name="component_completion"'), html.index('name="examiner_marks_checked"'))

    def test_online_attendance_requires_and_persists_applicable_checks(self):
        self.record.format = 'Online'; self.record.modules = 'Listening and speaking'; db.session.commit()
        self.assertEqual(self.post(examiner_marks_checked='0').status_code, 400)
        self.assertEqual(self.post(component_completion='').status_code, 400)
        self.assertEqual(m.StaffExamSessionReport.query.count(), 0)
        self.assertEqual(self.post().status_code, 200)
        report = m.StaffExamSessionReport.query.one()
        self.assertFalse(report.speaking_records_checked)
        self.assertFalse(report.listening_speaking_components_checked)
        self.assertEqual(report.component_completion, 'complete')
        self.assertFalse(report.session_completed_checked)

    def test_inapplicable_online_attendance_checks_are_not_required_or_saved(self):
        self.record.format = 'Online'; self.record.modules = 'Reading and writing'; db.session.commit()
        self.assertEqual(self.post(speaking_records_checked='1', listening_speaking_components_checked='1').status_code, 200)
        report = m.StaffExamSessionReport.query.one()
        self.assertFalse(report.speaking_records_checked)
        self.assertFalse(report.listening_speaking_components_checked)

    def test_online_attendance_migration_preserves_existing_reports(self):
        from sqlalchemy import text
        from app.schema_migrations import migrate_staff_session_report_attendance
        self.assertEqual(self.post(optional_comments='Existing report').status_code, 200)
        report_id = m.StaffExamSessionReport.query.one().id
        db.session.expunge_all()
        for field in ('speaking_records_checked', 'listening_speaking_components_checked', 'rw_files_uploaded_checked', 'rw_files_matched_checked', 'listening_files_uploaded_checked', 'listening_files_matched_checked', 'examiner_marks_checked'):
            db.session.execute(text(f'ALTER TABLE staff_exam_session_report DROP COLUMN {field}'))
        db.session.commit()
        migrate_staff_session_report_attendance()
        migrate_staff_session_report_attendance()
        report = db.session.get(m.StaffExamSessionReport, report_id)
        self.assertEqual(report.optional_comments, 'Existing report')
        self.assertFalse(report.speaking_records_checked)
        self.assertFalse(report.listening_speaking_components_checked)

    def test_online_report_omits_onsite_sections_and_needs_no_marketing_folder(self):
        import json
        self.record.format = 'Online'
        self.record.session_pictures_folder_url = ''
        m.StaffSessionReportMedia.query.delete()
        db.session.commit()
        html = self.client.get(f'/my-exam-sessions/{self.share.token}?session_year=2026').get_data(as_text=True)
        for marker in ('name="return_verification"', 'name="facilities_outcome"', 'name="emergency_pack_outcome"', 'data-report-media ', 'name="marketing_confirmed"'):
            self.assertNotIn(marker, html)
        for marker in ('name="schedule_outcome"', 'name="absent_candidates_checked"', 'Staff member performance review', 'name="optional_comments"'):
            self.assertIn(marker, html)
        response = self.post(return_verification=[], facilities_outcome='', emergency_pack_outcome='', marketing_confirmed='0')
        self.assertEqual(response.status_code, 200, response.json)
        report = m.StaffExamSessionReport.query.one()
        self.assertEqual(json.loads(report.return_verification), [])
        self.assertEqual(report.facilities_outcome, '')
        self.assertEqual(report.emergency_pack_outcome, '')
        self.assertFalse(report.marketing_confirmed)
        self.assertEqual(json.loads(report.marketing_media), [])

    def test_onsite_report_still_requires_return_facilities_emergency_and_marketing(self):
        self.assertEqual(self.post(return_verification=[]).status_code, 400)
        self.assertEqual(self.post(facilities_outcome='').status_code, 400)
        self.assertEqual(self.post(emergency_pack_outcome='').status_code, 400)
        self.assertEqual(self.post(marketing_confirmed='0').status_code, 400)
        html = self.client.get(f'/my-exam-sessions/{self.share.token}?session_year=2026').get_data(as_text=True)
        for marker in ('name="return_verification"', 'name="facilities_outcome"', 'name="emergency_pack_outcome"', 'name="marketing_confirmed"'):
            self.assertIn(marker, html)
