import os
import unittest
from unittest.mock import patch
from datetime import date, datetime, timezone

os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from app import create_app, db
from app.models import (AcademicStaff, ExamSession, ExamSessionScheduleWorkflow, ExamSessionMonthlyRegistration,
                        ExamSessionExaminerAssignment, ExamSessionSupervisorAssignment,
                        ExamSessionInternAssignment, StaffExamSessionSubmission, StaffExamSessionsShare,
                        ExamSessionLogistics, ExamSessionLogisticsConcept, ProviderType)
from app.routes import complex_logistics_staff_members_for_session, save_exam_session_logistics


class StaffPortalLogisticsTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config["TESTING"] = True
        self.context = self.app.app_context()
        self.context.push()
        db.drop_all()
        db.create_all()
        self.record = ExamSession(exam_session_name="Logistics validation", category="Path School",
                                  status="Pending", session_date=date(2026, 11, 10),
                                  shifts="Morning", modules="Speaking", format="Onsite")
        self.person = AcademicStaff(full_name="Test Staff", status="Active", roles="Supervisor, Examiner, Intern")
        db.session.add_all([self.record, self.person])
        db.session.flush()
        db.session.add(ExamSessionScheduleWorkflow(exam_session_id=self.record.id, status="Approved"))
        db.session.commit()
        self.client = self.app.test_client()
        with self.client.session_transaction() as state:
            state.update(user="admin", csrf_token="test")

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def add(self, role, assignment_id):
        return self.client.post(
            f"/pre-session-control-tower/sessions/{self.record.id}/staffing-assignments/{role}/{assignment_id}/submit",
            data={"csrf_token": "test"}, headers={"Accept": "application/json"})

    def test_each_onsite_role_requires_a_logistics_selection(self):
        for role, model in [("supervisor", ExamSessionSupervisorAssignment),
                            ("examiner", ExamSessionExaminerAssignment)]:
            assignment = model(exam_session_id=self.record.id, team_member_id=self.person.id,
                               staffing_role_check_verified=True, participation_status="Pre-confirmed",
                               logistics_type="", logistics_enabled=True)
            db.session.add(assignment)
            db.session.commit()
            before = StaffExamSessionSubmission.query.count()
            response = self.add(role, assignment.id)
            self.assertEqual(response.status_code, 400)
            self.assertIn("Select Logistics", response.json["error"])
            self.assertEqual(StaffExamSessionSubmission.query.count(), before)
            for value in ["Does not apply", "Uber ride", "Complex Uber ride", "Complex logistics", "Carpooling"]:
                assignment.logistics_type = value
                db.session.commit()
                self.assertEqual(self.add(role, assignment.id).status_code, 200)

    def test_online_supervisor_and_examiner_can_be_added_with_zoom_instructions(self):
        for session_format in ("Online", "Online at exam centre"):
            for role, model, phrase in (
                ("supervisor", ExamSessionSupervisorAssignment, "Start the Zoom session <em><u>at least</u></em> 15 minutes before the start."),
                ("examiner", ExamSessionExaminerAssignment, "Join the Zoom session <em><u>at least</u></em> 10 minutes before the start."),
            ):
                if session_format == 'Online at exam centre' and role == 'examiner':
                    continue
                with self.subTest(session_format=session_format, role=role):
                    self.record.format = session_format
                    assignment = model(exam_session_id=self.record.id, team_member_id=self.person.id,
                        staffing_role_check_verified=True, participation_status="Pre-confirmed",
                        logistics_type="Does not apply")
                    db.session.add(assignment)
                    db.session.commit()
                    response = self.add(role, assignment.id)
                    self.assertEqual(response.status_code, 200, response.json)
                    portal = self.app.test_client().get(response.json["url"])
                    self.assertEqual(portal.status_code, 200)
                    expected_phrase = 'Arrive <em><u>at least</u></em> 50 minutes before the start.' if session_format == 'Online at exam centre' and role == 'supervisor' else phrase
                    self.assertIn(expected_phrase, portal.get_data(as_text=True))
                    import re
                    articles = re.findall(r'<article class="staff-detail-assignment".*?</article>', portal.get_data(as_text=True), re.S)
                    for article in articles:
                        import json
                        from html import unescape
                        payload = json.loads(unescape(re.search(r"data-staff-session-payload='([^']*)'", article).group(1)))
                        is_supervisor = payload['role'] == 'Supervisor'
                        has_zoom = session_format == 'Online' and payload['role'] in ('Supervisor', 'Examiner')
                        self.assertEqual('data-staff-zoom-access' in article, has_zoom)
                        self.assertEqual('data-staff-travel-section' in article, session_format == 'Online at exam centre')
                        self.assertEqual('Travel and logistics' in article, session_format == 'Online at exam centre')
                        if has_zoom and is_supervisor:
                            self.assertIn('💻 Zoom access details', article)
                            self.assertIn('<strong>two-step verification</strong>', article)
                            self.assertIn('<strong>Password:</strong> Path&amp;23646', article)
                        else:
                            self.assertNotIn('Path&amp;23646', article)
                            if has_zoom:
                                self.assertIn('join the Zoom meeting at least 10 minutes before your scheduled start time', article)
                                self.assertIn('href="https://zoom.us/j/7284728472"', article)
                                self.assertIn('<strong>ID: 728 472 8472</strong>', article)
                                self.assertIn('<strong>Passcode: path</strong>', article)
                    if session_format == 'Online':
                        self.assertNotIn('Arrive <em><u>at least</u></em>', portal.get_data(as_text=True))

    def test_onsite_portal_keeps_arrival_instructions(self):
        for role, model, minutes in (("supervisor", ExamSessionSupervisorAssignment, "50"),
                                      ("examiner", ExamSessionExaminerAssignment, "30")):
            with self.subTest(role=role):
                assignment=model(exam_session_id=self.record.id, team_member_id=self.person.id,
                    staffing_role_check_verified=True, participation_status="Pre-confirmed",logistics_type="Does not apply")
                db.session.add(assignment); db.session.commit()
                response=self.add(role,assignment.id)
                self.assertEqual(response.status_code,200)
                html=self.app.test_client().get(response.json["url"]).get_data(as_text=True)
                self.assertIn(f'Arrive <em><u>at least</u></em> {minutes} minutes before the start.', html)
                self.assertNotIn('the Zoom session',html)
                self.assertNotIn('data-staff-zoom-access',html)
                self.assertIn('data-staff-travel-section',html)
                self.assertNotIn('Path&amp;23646',html)

    def test_online_supervisor_end_checks_have_five_items_and_exam_day_digitalised_link(self):
        db.session.add(ExamSessionMonthlyRegistration(exam_session_id=self.record.id, month=11, module='Speaking', registration_number=1))
        self.record.format = 'Online'
        self.record.digitalised_exams_url = 'https://example.com/digitalised'
        self.record.session_pictures_folder_url = 'https://example.com/audiovisual'
        self.app.config['STAFF_END_OF_SESSION_REPORT_URL'] = 'https://example.com/report'
        assignment = ExamSessionSupervisorAssignment(exam_session_id=self.record.id, team_member_id=self.person.id,
            staffing_role_check_verified=True, participation_status='Confirmed', logistics_type='Does not apply')
        db.session.add(assignment); db.session.commit()
        added = self.add('supervisor', assignment.id)
        self.assertEqual(added.status_code,200)
        import re
        for instant, enabled in (
            (datetime(2026,11,10,2,59,tzinfo=timezone.utc),False),
            (datetime(2026,11,10,3,0,tzinfo=timezone.utc),True),
            (datetime(2026,11,11,2,59,tzinfo=timezone.utc),True),
            (datetime(2026,11,11,3,0,tzinfo=timezone.utc),False),
        ):
            with self.subTest(instant=instant), patch('app.routes.datetime',wraps=datetime) as clock:
                clock.now.side_effect=lambda tz=None: instant.astimezone(tz) if tz else instant.replace(tzinfo=None)
                html=self.app.test_client().get(added.json['url']).get_data(as_text=True)
                self.assertIn('End-of-session checks (0/5)',html)
                self.assertIn('registered candidate attendance in Sinapsis',html)
                self.assertIn('all submitted exam modules have been successfully uploaded',html)
                self.assertIn('upload their Speaking recordings within one business day',html)
                self.assertIn('Audiovisual material ↗',html)
                self.assertIn('End-of-session report ↗',html)
                self.assertNotIn('data-end-check="centre_feedback"',html)
                self.assertNotIn('printed candidate lists attached',html)
                link=re.search(r'<a[^>]*data-folder-exam-day-only[^>]*>',html).group(0)
                self.assertEqual('href="https://example.com/digitalised"' in link,enabled)
                self.assertEqual('aria-disabled="true"' in link,not enabled)
        share=StaffExamSessionsShare.query.one()
        submission=StaffExamSessionSubmission.query.one()
        with patch('app.routes.datetime',wraps=datetime) as clock:
            clock.now.side_effect=lambda tz=None: datetime(2026,11,10,12,tzinfo=timezone.utc).astimezone(tz) if tz else datetime(2026,11,10,12)
            self.assertEqual(self.client.post(f'/my-exam-sessions/{share.token}/submissions/{submission.id}/end-checks',data={
                'csrf_token':'test','check':'centre_feedback','checked':'1'}).status_code,400)
            self.assertEqual(self.client.post(f'/my-exam-sessions/{share.token}/submissions/{submission.id}/end-checks',data={
                'csrf_token':'test','check':'return_papers','checked':'1'}).status_code,200)
        from app.routes import staff_assignment_end_check_fields
        self.record.format='Online at exam centre'
        self.assertIn('centre_feedback',staff_assignment_end_check_fields(self.record,'supervisor',assignment))
        db.session.commit()
        centre_html=self.app.test_client().get(added.json['url']).get_data(as_text=True)
        self.assertIn('I confirm that all submitted exam modules have been successfully uploaded to the Digitalised exams folder.',centre_html)
        self.assertNotIn('Digitalised Exams folder',centre_html)
        self.assertIn('Digitalised exams ↗',centre_html)

    def test_recording_check_depends_on_candidates_in_latest_registration_month(self):
        assignment = ExamSessionSupervisorAssignment(exam_session_id=self.record.id, team_member_id=self.person.id,
            staffing_role_check_verified=True, participation_status='Confirmed', logistics_type='Does not apply')
        db.session.add(assignment);db.session.commit()
        added=self.add('supervisor',assignment.id)
        from app.routes import staff_assignment_end_check_fields
        for session_format in ('Online','Onsite'):
            self.record.format=session_format
            for module,count in (('Reading and writing',5),('Listening and speaking',0),('Speaking',0),('Listening and speaking',1),('Speaking',1)):
                with self.subTest(session_format=session_format,module=module,count=count):
                    ExamSessionMonthlyRegistration.query.filter_by(exam_session_id=self.record.id).delete()
                    db.session.add(ExamSessionMonthlyRegistration(exam_session_id=self.record.id,month=10,module='Speaking',registration_number=10))
                    db.session.add(ExamSessionMonthlyRegistration(exam_session_id=self.record.id,month=11,module=module,registration_number=count))
                    db.session.commit()
                    expected=module in ('Listening and speaking','Speaking') and count>0
                    fields=staff_assignment_end_check_fields(self.record,'supervisor',assignment)
                    self.assertEqual('recordings' in fields,expected)
                    html=self.app.test_client().get(added.json['url']).get_data(as_text=True)
                    self.assertEqual('data-end-check="recordings"' in html,expected)
                    self.assertIn(f'End-of-session checks (0/{len(fields)})',html)
        ExamSessionMonthlyRegistration.query.filter_by(exam_session_id=self.record.id).delete()
        db.session.commit()
        self.assertNotIn('recordings',staff_assignment_end_check_fields(self.record,'supervisor',assignment))
        share=StaffExamSessionsShare.query.one()
        submission=StaffExamSessionSubmission.query.one()
        with patch('app.routes.staff_end_checks_available',return_value=True):
            self.assertEqual(self.client.post(f'/my-exam-sessions/{share.token}/submissions/{submission.id}/end-checks',data={
                'csrf_token':'test','check':'recordings','checked':'1'}).status_code,400)

    def test_online_formats_cannot_persist_remote_supervisors(self):
        assignment=ExamSessionSupervisorAssignment(exam_session_id=self.record.id, team_member_id=self.person.id,
            participation_status='Confirmed', staffing_role_check_verified=True, is_remote=True, logistics_type='Does not apply')
        db.session.add(assignment);db.session.commit()
        self.assertTrue(assignment.is_remote)
        for session_format in ('Online','Online at exam centre'):
            with self.subTest(session_format=session_format):
                self.record.format=session_format
                db.session.commit()
                db.session.refresh(assignment)
                self.assertFalse(assignment.is_remote)
                assignment.is_remote=True
                db.session.commit()
                db.session.refresh(assignment)
                self.assertFalse(assignment.is_remote)
                self.assertEqual(assignment.participation_status,'Confirmed')
                self.assertEqual(assignment.team_member_id,self.person.id)
        self.record.format='Onsite'
        assignment.is_remote=True
        db.session.commit()
        self.assertTrue(assignment.is_remote)

    def test_existing_invalid_online_remote_flag_is_normalized(self):
        from sqlalchemy import text
        from app.staffing_rules import normalize_existing_online_supervisors
        self.record.format='Online'
        assignment=ExamSessionSupervisorAssignment(exam_session_id=self.record.id,team_member_id=self.person.id,
            participation_status='Confirmed',is_remote=False)
        db.session.add(assignment);db.session.commit()
        db.session.execute(text('UPDATE exam_session_supervisor_assignment SET is_remote=1 WHERE id=:id'),{'id':assignment.id})
        db.session.commit()
        normalize_existing_online_supervisors()
        db.session.refresh(assignment)
        self.assertFalse(assignment.is_remote)
        self.assertEqual(assignment.participation_status,'Confirmed')

    def test_online_cards_exclude_travel_fields_and_online_centre_retains_them(self):
        import re
        assignments=[]
        for role,model in (('supervisor',ExamSessionSupervisorAssignment),('examiner',ExamSessionExaminerAssignment),('intern',ExamSessionInternAssignment)):
            assignment=model(exam_session_id=self.record.id,team_member_id=self.person.id,
                participation_status='Confirmed',logistics_type='Does not apply',km=90,
                commuting='ARS 100',fuel='ARS 200',vehicle_dep='ARS 300',fuel_enabled=True)
            db.session.add(assignment);assignments.append((role,assignment))
        db.session.commit()
        self.record.format='Online'
        db.session.commit()
        for role,assignment in assignments:
            db.session.refresh(assignment)
            self.assertIsNone(assignment.km)
            self.assertFalse(assignment.fuel_enabled)
            self.assertEqual(assignment.logistics_enabled, role == 'intern')
            self.assertEqual(assignment.logistics_type, 'Complex logistics' if role == 'intern' else 'Does not apply')
            for field in ('commuting','fuel','vehicle_dep'):
                self.assertEqual(getattr(assignment,field), None if role == 'intern' else '')
            self.assertEqual(assignment.participation_status,'Confirmed')
        for session_format in ('Online','Online at exam centre'):
            self.record.format=session_format
            db.session.commit()
            response=self.client.get('/exam-session-planner?session_year=2026')
            self.assertEqual(response.status_code,200)
            cards=re.findall(r'<article class="staff-assignment-card".*?</article>',response.get_data(as_text=True),re.S)
            for role,assignment in assignments:
                matches=[card for card in cards if f'data-assignment-id="{assignment.id}"' in card and f'data-section-key="{role}"' in card]
                if session_format == 'Online at exam centre' and role == 'examiner':
                    self.assertFalse(matches)
                    continue
                self.assertTrue(matches,role)
                for card in matches:
                    for selector in ('data-km-field','data-commuting-cell','data-fuel-cell','data-vehicle-cell','data-logistics-control'):
                        self.assertEqual(selector in card, (role == 'intern' or session_format != 'Online') if selector == 'data-logistics-control' else role != 'intern' and session_format != 'Online')
            for role,assignment in assignments:
                if session_format == 'Online at exam centre' and role == 'examiner':
                    continue
                assignment.km=90
                assignment.commuting='ARS 100'
                assignment.fuel='ARS 200'
                assignment.vehicle_dep='ARS 300'
                assignment.fuel_enabled=True
            db.session.commit()
            for role,assignment in assignments:
                if session_format == 'Online at exam centre' and role == 'examiner':
                    continue
                db.session.refresh(assignment)
                self.assertEqual(assignment.km,90 if role != 'intern' and session_format != 'Online' else None)
                self.assertEqual(assignment.commuting, None if role == 'intern' else 'ARS 100' if session_format != 'Online' else '')

    def test_online_supervisor_role_fee_is_65_percent_only_for_that_format_and_role(self):
        import json
        from app.models import Role, Fee
        from app.routes import apply_role_fee_calculation
        role=Role(name='Supervisor')
        db.session.add(role);db.session.flush()
        fee=Fee(fee_description='Supervisor rate',currency='ARS',fee_value='25.000',unit_of_measure='per hour',role_id=role.id)
        db.session.add(fee);db.session.commit()
        for session_format in ('Online','Online at exam centre','Onsite'):
            self.record.format=session_format
            db.session.commit()
            for model in (ExamSessionSupervisorAssignment,ExamSessionExaminerAssignment,ExamSessionInternAssignment):
                if session_format == 'Online at exam centre' and model is ExamSessionExaminerAssignment:
                    continue
                with self.subTest(session_format=session_format,model=model.__name__):
                    assignment=model(exam_session_id=self.record.id,team_member_id=self.person.id,
                        participation_status='Confirmed',logistics_type='Does not apply',
                        time_ranges=json.dumps([{'start':'09:00','end':'10:00'}]))
                    db.session.add(assignment)
                    apply_role_fee_calculation(assignment,fee,datetime.now(timezone.utc))
                    db.session.commit()
                    expected='ARS 16.250' if session_format=='Online' and model is ExamSessionSupervisorAssignment else 'ARS 25.000'
                    self.assertEqual(assignment.role_fee, None if model is ExamSessionInternAssignment else expected)
                    self.assertEqual(fee.fee_value,'25.000')
        self.record.format='Online'
        db.session.commit()
        assignment=ExamSessionSupervisorAssignment(exam_session_id=self.record.id,team_member_id=self.person.id,
            participation_status='Confirmed',time_ranges=json.dumps([{'start':'09:00','end':'11:00'}]))
        db.session.add(assignment);db.session.commit()
        self.assertEqual(assignment.role_fee,'ARS 32.500')
        assignment.role_fee='ARS 99.000'
        assignment.manual_fee_override=True
        db.session.commit()
        self.assertEqual(assignment.role_fee,'ARS 99.000')

    def test_examiner_guidelines_by_format_and_missing_online_link(self):
        from app.models import CertificationYearConfiguration
        from app.routes import staffing_email_examiner_certification_material_links
        data = {'csrf_token': 'test', 'certification_year': '2026',
                'examiner_guideline_url': 'https://example.com/onsite',
                'examiner_online_guideline_url': 'https://example.com/online'}
        endpoint = '/annual-certification-programme/material-settings'
        self.assertEqual(self.client.post(endpoint, data=data).status_code, 302)
        config = CertificationYearConfiguration.query.filter_by(module_key='examiner_certification', year=2026).one()
        for format_name, expected in [('Onsite', 'onsite'), ('Online', 'online')]:
            self.record.format = format_name
            self.assertEqual(staffing_email_examiner_certification_material_links(self.record)['examiner_guideline_url'], 'https://example.com/' + expected)
        self.client.post(endpoint, data={**data, 'examiner_online_guideline_url': 'bad-url'})
        db.session.refresh(config)
        self.assertEqual(config.examiner_online_guideline_url, data['examiner_online_guideline_url'])
        self.client.post(endpoint, data={**data, 'examiner_online_guideline_url': ''})
        self.assertEqual(staffing_email_examiner_certification_material_links(self.record)['examiner_guideline_url'], '')

    def test_online_centre_removes_examiner_and_portal_submission(self):
        from app.models import StaffExamSessionEndChecks
        examiner = ExamSessionExaminerAssignment(exam_session_id=self.record.id, team_member_id=self.person.id,
            staffing_role_check_verified=True, participation_status='Confirmed', logistics_type='Does not apply')
        supervisor = ExamSessionSupervisorAssignment(exam_session_id=self.record.id, team_member_id=self.person.id)
        intern = ExamSessionInternAssignment(exam_session_id=self.record.id, team_member_id=self.person.id)
        db.session.add_all([examiner, supervisor, intern]); db.session.commit()
        examiner_id = examiner.id
        self.assertEqual(self.add('examiner', examiner_id).status_code, 200)
        submission = StaffExamSessionSubmission.query.one()
        db.session.add(StaffExamSessionEndChecks(submission_id=submission.id)); db.session.commit()
        self.record.format = 'Online at exam centre'
        db.session.commit()
        self.assertEqual(ExamSessionExaminerAssignment.query.count(), 0)
        self.assertEqual(StaffExamSessionSubmission.query.count(), 0)
        self.assertEqual(StaffExamSessionEndChecks.query.count(), 0)
        self.assertEqual(ExamSessionSupervisorAssignment.query.count(), 1)
        self.assertEqual(ExamSessionInternAssignment.query.count(), 1)
        self.assertEqual(self.add('examiner', examiner_id).status_code, 404)

    def test_online_centre_cleanup_handles_existing_legacy_assignments(self):
        from sqlalchemy import text
        from app.staffing_rules import remove_existing_online_centre_examiners
        db.session.add(ExamSessionExaminerAssignment(exam_session_id=self.record.id, team_member_id=self.person.id))
        db.session.commit()
        db.session.execute(text("UPDATE exam_session SET format='Online at exam centre' WHERE id=:id"), {'id': self.record.id})
        db.session.commit(); db.session.expire_all()
        remove_existing_online_centre_examiners()
        self.assertEqual(ExamSessionExaminerAssignment.query.count(), 0)
        forbidden = ExamSessionExaminerAssignment(exam_session_id=self.record.id, team_member_id=self.person.id)
        db.session.add(forbidden); db.session.commit()
        self.assertEqual(ExamSessionExaminerAssignment.query.count(), 0)

    def test_supervisor_guidelines_are_saved_and_selected_by_format_and_year(self):
        from app.models import CertificationYearConfiguration
        from app.routes import staffing_email_supervisor_certification_material_links
        config=CertificationYearConfiguration(module_key='supervisor_certification',year=2026,
            supervisor_guideline_url='https://example.com/onsite',backup_material_for_examiners_url='https://example.com/backup')
        db.session.add(config);db.session.commit()
        response=self.client.post('/supervisor-certification/material-settings',data={
            'csrf_token':'test','certification_year':'2026',
            'supervisor_guideline_url':'https://example.com/onsite',
            'supervisor_online_guideline_url':'https://example.com/online',
            'supervisor_online_centre_guideline_url':'https://example.com/centre',
            'backup_material_for_examiners_url':'https://example.com/backup'})
        self.assertEqual(response.status_code,302)
        assignment=ExamSessionSupervisorAssignment(exam_session_id=self.record.id,team_member_id=self.person.id,
            participation_status='Pre-confirmed',staffing_role_check_verified=True,logistics_type='Does not apply')
        db.session.add(assignment);db.session.commit()
        import re,json
        from html import unescape
        for session_format,suffix in (('Onsite','onsite'),('Online','online'),('Online at exam centre','centre')):
            self.record.format=session_format;db.session.commit()
            self.assertEqual(staffing_email_supervisor_certification_material_links(self.record)['supervisor_guideline_url'],'https://example.com/'+suffix)
            added=self.add('supervisor',assignment.id)
            self.assertEqual(added.status_code,200)
            html=self.app.test_client().get(added.json['url']).get_data(as_text=True)
            payload=json.loads(unescape(re.search(r"data-staff-session-payload='([^']*)'",html).group(1)))
            self.assertEqual(payload['supervisor_guideline_url'],'https://example.com/'+suffix)
        config.supervisor_online_guideline_url=''
        self.record.format='Online';db.session.commit()
        self.assertEqual(staffing_email_supervisor_certification_material_links(self.record)['supervisor_guideline_url'],'')
        config.supervisor_online_guideline_url='https://example.com/new-online';db.session.commit()
        self.assertEqual(staffing_email_supervisor_certification_material_links(self.record)['supervisor_guideline_url'],'https://example.com/new-online')
        response=self.client.post('/supervisor-certification/material-settings',data={
            'csrf_token':'test','certification_year':'2026','supervisor_online_guideline_url':'not-a-url'})
        db.session.refresh(config)
        self.assertEqual(config.supervisor_online_guideline_url,'https://example.com/new-online')
        self.record.session_date=date(2027,11,10)
        self.assertEqual(staffing_email_supervisor_certification_material_links(self.record)['supervisor_guideline_url'],'')

    def test_support_guideline_block_saves_independently_and_validates_urls_and_csrf(self):
        from app.models import CertificationYearConfiguration
        config=CertificationYearConfiguration(module_key='supervisor_certification',year=2026,
            supervisor_guideline_url='https://example.com/onsite',backup_material_for_examiners_url='https://example.com/backup')
        db.session.add(config);db.session.commit()
        endpoint='/supervisor-certification/support-material-settings'
        data={'csrf_token':'test','certification_year':'2026',
            'emergency_contact_guideline_url':'https://example.com/emergency',
            'remote_supervisor_guideline_url':'https://example.com/remote'}
        response=self.client.post(endpoint,data=data,follow_redirects=True)
        self.assertEqual(response.status_code,200)
        html=response.get_data(as_text=True)
        self.assertIn('Emergency contact guidelines',html)
        self.assertIn('Remote supervisor guidelines',html)
        self.assertIn('value="https://example.com/emergency"',html)
        self.assertIn('value="https://example.com/remote"',html)
        db.session.refresh(config)
        self.assertEqual(config.supervisor_guideline_url,'https://example.com/onsite')
        self.assertEqual(config.backup_material_for_examiners_url,'https://example.com/backup')
        self.client.post(endpoint,data={**data,'remote_supervisor_guideline_url':'not a URL','emergency_contact_guideline_url':'https://example.com/changed'})
        db.session.refresh(config)
        self.assertEqual(config.emergency_contact_guideline_url,'https://example.com/emergency')
        self.assertEqual(config.remote_supervisor_guideline_url,'https://example.com/remote')
        self.client.post(endpoint,data={**data,'csrf_token':'wrong','remote_supervisor_guideline_url':'https://example.com/changed'})
        db.session.refresh(config)
        self.assertEqual(config.remote_supervisor_guideline_url,'https://example.com/remote')

    def test_invoice_information_is_shared_by_all_roles_and_formats(self):
        import re
        for role,model in (('supervisor',ExamSessionSupervisorAssignment),('examiner',ExamSessionExaminerAssignment),('intern',ExamSessionInternAssignment)):
            assignment=model(exam_session_id=self.record.id,team_member_id=self.person.id,
                participation_status='Pre-confirmed',staffing_role_check_verified=True,logistics_type='Does not apply')
            db.session.add(assignment);db.session.commit()
            self.assertEqual(self.add(role,assignment.id).status_code,200)
        self.record.emergency_contact_required=True
        self.record.emergency_contact_member_id=self.person.id
        self.record.emergency_contact_role_check_verified=True
        self.record.emergency_contact_participation_status='Pre-confirmed'
        db.session.commit()
        emergency=self.add('emergency_contact',self.record.id)
        self.assertEqual(emergency.status_code,200)
        for session_format in ('Online','Online at exam centre','Onsite'):
            self.record.format=session_format;db.session.commit()
            html=self.app.test_client().get(emergency.json['url']).get_data(as_text=True)
            articles=re.findall(r'<article class="staff-detail-assignment".*?</article>',html,re.S)
            self.assertEqual(len(articles),3 if session_format in ("Online at exam centre", "Onsite") else 4)
            for article in articles:
                if '"assignment_type": "intern"' in article:
                    self.assertNotIn('staff-detail-invoice', article)
                    continue
                section=re.search(r'<details class="staff-detail-invoice">.*?</details>',article,re.S).group(0)
                self.assertIn('upload <strong>one consolidated invoice</strong>',section)
                self.assertIn('<strong><em class="staff-invoicing-instructions-reference">Invoicing instructions</em></strong>',section)
                self.assertIn('<strong>72 business hours</strong>',section)
                self.assertIn('<strong>at least 2 business days before the scheduled payment date and time</strong>',section)
                self.assertNotIn('send one consolidated invoice',section)
                self.assertNotIn('mailto:',section)

    def test_remote_supervisor_only_accepts_does_not_apply(self):
        assignment = ExamSessionSupervisorAssignment(exam_session_id=self.record.id, team_member_id=self.person.id,
            staffing_role_check_verified=True, participation_status="Pre-confirmed", is_remote=True)
        db.session.add(assignment)
        for value in ["", "Uber ride", "Complex Uber ride", "Complex logistics", "Carpooling"]:
            assignment.logistics_type = value
            db.session.commit()
            response = self.add("supervisor", assignment.id)
            self.assertEqual(response.status_code, 400)
            self.assertIn("Does not apply", response.json["error"])
            self.assertEqual(StaffExamSessionSubmission.query.count(), 0)
            self.assertEqual(StaffExamSessionsShare.query.count(), 0)
        assignment.logistics_type = "Does not apply"
        db.session.commit()
        self.assertEqual(self.add("supervisor", assignment.id).status_code, 200)

    def test_emergency_contact_does_not_require_logistics(self):
        self.record.emergency_contact_member_id = self.person.id
        self.record.emergency_contact_required = True
        self.record.emergency_contact_role_check_verified = True
        self.record.emergency_contact_participation_status = "Pre-confirmed"
        db.session.commit()
        self.assertEqual(self.add("emergency_contact", self.record.id).status_code, 200)

    def portal_assignment(self, role="examiner"):
        model = ExamSessionSupervisorAssignment if role == "supervisor" else ExamSessionExaminerAssignment
        assignment = model(exam_session_id=self.record.id, team_member_id=self.person.id,
                           staffing_role_check_verified=True, participation_status="Confirmed",
                           logistics_type="Does not apply")
        share = StaffExamSessionsShare(person_ref=str(self.person.id), token="travel-test")
        db.session.add_all([assignment, share])
        db.session.flush()
        db.session.add(StaffExamSessionSubmission(share_id=share.id, exam_session_id=self.record.id,
                                                assignment_type=role, assignment_id=assignment.id))
        db.session.add(ExamSessionLogistics(exam_session_id=self.record.id,
                                           logistics_files_url="https://example.com/travel"))
        db.session.commit()
        return assignment

    def portal_page(self):
        response = self.client.get("/my-exam-sessions/travel-test")
        self.assertEqual(response.status_code, 200)
        return response.get_data(as_text=True)

    def test_exam_centre_contacts_role_scope_and_gmt3_day_boundaries(self):
        import json
        from datetime import date, datetime, timezone
        from types import SimpleNamespace
        from app.routes import staff_exam_centre_contacts
        self.record.contact_points = json.dumps([{"full_name": "Centre Person", "phone": "12345", "email": "centre@example.com"}])
        ordinary = SimpleNamespace(is_shipment_recipient=False, is_remote=False)
        remote = SimpleNamespace(is_shipment_recipient=False, is_remote=True)
        recipient = SimpleNamespace(is_shipment_recipient=True)
        on_day = datetime(2026, 11, 10, 12, tzinfo=timezone.utc)
        for role, assignment in [("supervisor", ordinary), ("supervisor", remote), ("examiner", recipient), ("emergency_contact", self.record)]:
            with self.subTest(role=role):
                self.assertEqual(len(staff_exam_centre_contacts(self.record, role, assignment, "Confirmed", now=on_day)["contacts"]), 1)
                self.assertIsNone(staff_exam_centre_contacts(self.record, role, assignment, "Pre-confirmed", now=on_day))
        for role in ["examiner", "intern"]:
            self.assertIsNone(staff_exam_centre_contacts(self.record, role, ordinary, "Confirmed", now=on_day))
        for moment, available in [
            (datetime(2026, 11, 10, 2, 59, 59, tzinfo=timezone.utc), False),
            (datetime(2026, 11, 10, 3, tzinfo=timezone.utc), True),
            (datetime(2026, 11, 11, 2, 59, 59, tzinfo=timezone.utc), True),
            (datetime(2026, 11, 11, 3, tzinfo=timezone.utc), False),
        ]:
            result = staff_exam_centre_contacts(self.record, "supervisor", ordinary, "Confirmed", now=moment)
            self.assertEqual(result["available"], available)
            self.assertEqual(len(result["contacts"]), 1 if available else 0)
        self.record.contact_points = "[]"
        self.assertIsNone(staff_exam_centre_contacts(self.record, "supervisor", ordinary, "Confirmed", now=on_day))

    def test_exam_centre_contacts_portal_live_updates_and_hidden_data(self):
        import json
        from datetime import date, datetime, timezone
        from unittest.mock import patch
        from app.routes import staff_exam_centre_contacts
        assignment = self.portal_assignment()
        assignment.is_shipment_recipient = True
        contacts = [{"full_name": "Centre First", "phone": "+54 11 1234 5678", "email": "centre-first@example.com"},
                    {"full_name": "Centre Second", "phone": "999999", "email": "centre-second@example.com"}]
        self.record.contact_points = json.dumps(contacts)
        db.session.commit()
        def page_at(moment):
            with patch("app.routes.staff_exam_centre_contacts", side_effect=lambda record, role, assignment, status:
                       staff_exam_centre_contacts(record, role, assignment, status, now=moment)):
                return self.portal_page()
        before = page_at(datetime(2026, 11, 10, 2, 59, tzinfo=timezone.utc))
        self.assertIn("Exam centre contact information", before)
        self.assertIn("Available on exam day only", before)
        for contact in contacts:
            for value in contact.values():
                self.assertNotIn(value, before)
        moment = datetime(2026, 11, 10, 3, tzinfo=timezone.utc)
        page = page_at(moment)
        self.assertLess(page.index("Your session team"), page.index('aria-label="Exam centre contact information"'))
        self.assertNotIn("Available on exam day only", page)
        self.assertNotIn("Calls only – No messages", page)
        for contact in contacts:
            for value in contact.values():
                self.assertIn(value, page)
        contacts[0]["phone"] = "UPDATED-PHONE"
        self.record.contact_points = json.dumps(contacts)
        db.session.commit()
        updated = page_at(moment)
        self.assertIn("UPDATED-PHONE", updated)
        self.assertNotIn("+54 11 1234 5678", updated)
        after = page_at(datetime(2026, 11, 11, 3, tzinfo=timezone.utc))
        self.assertNotIn("UPDATED-PHONE", after)
        self.assertIn("Available on exam day only", after)
        assignment.participation_status = "Pre-confirmed"
        db.session.commit()
        self.assertNotIn("Exam centre contact information", page_at(moment))
        assignment.participation_status = "Confirmed"
        self.record.contact_points = "[]"
        db.session.commit()
        self.assertNotIn("Exam centre contact information", page_at(moment))

    def test_travel_texts_labels_and_bold_for_each_option(self):
        assignment = self.portal_assignment()
        db.session.add(ExamSessionLogisticsConcept(exam_session_id=self.record.id,
            instructions_html="<p>Travel instructions</p>", staff_members=[self.person]))
        db.session.commit()
        for value in ["Does not apply", "Uber ride", "Complex Uber ride", "Complex logistics"]:
            assignment.logistics_type = value
            db.session.commit()
            page = self.portal_page()
            self.assertIn(f'<span class="staff-detail-role">{value}</span>', page)
            self.assertIn(f'>{value}</div>', page)
            self.assertEqual('data-staff-logistics-instructions-open' in page, value.startswith("Complex"))
            if value == "Does not apply":
                self.assertIn('arrive 30 minutes before the start of the exam session.', page)
                self.assertNotIn('Open logistics folder ↗', page)
            else:
                self.assertIn('href="https://example.com/travel"', page)
                self.assertIn('<strong>Reimbursements</strong>', page)
                self.assertIn('<strong>Do not include these expenses in your final invoice.</strong>', page)
            if value in {"Uber ride", "Complex Uber ride"}:
                self.assertIn('arrive 30 minutes before the start of your first assigned module.', page)
                self.assertIn('<strong>official Uber or Cabify receipts</strong>', page)
                self.assertIn('<strong>pick-up and drop-off locations, date and time of the journey, and total fare</strong>', page)
            if value == "Complex logistics":
                self.assertIn('<strong>travel or commute</strong>', page)
                self.assertIn('<strong>additional expenses previously approved by Path Examinations</strong>', page)

    def test_supervisor_arrival_is_fifty_minutes_and_legacy_uber_is_normalized(self):
        assignment = self.portal_assignment("supervisor")
        self.assertIn('arrive 50 minutes before the start of the exam session.', self.portal_page())
        assignment.logistics_type = "Uber"
        db.session.commit()
        page = self.portal_page()
        self.assertIn('<span class="staff-detail-role">Uber ride</span>', page)
        self.assertIn('arrive 50 minutes before the start of your first assigned module.', page)

    def test_carpooling_examiner_portal(self):
        self.assert_carpooling_portal("examiner", 30)

    def test_carpooling_supervisor_portal(self):
        self.assert_carpooling_portal("supervisor", 50)

    def assert_carpooling_portal(self, role, minutes):
        assignment = self.portal_assignment(role)
        assignment.logistics_type = "Carpooling"
        concept = ExamSessionLogisticsConcept(exam_session_id=self.record.id,
            instructions_html="<p>Meet at the shared vehicle.</p>", staff_members=[self.person])
        other = AcademicStaff(full_name="Other traveller", status="Active", roles="Examiner")
        db.session.add_all([concept, other])
        db.session.flush()
        db.session.add(ExamSessionLogisticsConcept(exam_session_id=self.record.id,
            instructions_html="PRIVATE CARPOOL INSTRUCTIONS", staff_members=[other]))
        db.session.commit()
        page = self.portal_page()
        self.assertIn('>Carpooling</div>', page)
        self.assertIn('<span class="staff-detail-role">Carpooling</span>', page)
        self.assertIn('Your journey to the exam centre will involve sharing a vehicle with other staff members. Please read and follow the important instructions below, as specific procedures and requirements must be observed.', page)
        self.assertIn('data-staff-logistics-instructions-open>View instructions</button>', page)
        self.assertIn('<p>Meet at the shared vehicle.</p>', page)
        self.assertNotIn('PRIVATE CARPOOL INSTRUCTIONS', page)
        self.assertIn(f'Make sure you plan your journey accordingly, allow sufficient travel time and arrive {minutes} minutes before the start of your first assigned module.', page)
        self.assertIn(self.person, complex_logistics_staff_members_for_session(self.record.id))

    def test_instructions_are_scoped_to_member_and_session_and_progress_updates(self):
        assignment = self.portal_assignment()
        assignment.logistics_type = "Complex Uber ride"
        own = ExamSessionLogisticsConcept(exam_session_id=self.record.id, status="Pending",
            instructions_html='<ul><li><b>Your instructions</b></li></ul>', staff_members=[self.person])
        other_person = AcademicStaff(full_name="Other member", status="Active", roles="Examiner")
        other_record = ExamSession(exam_session_name="Other session", category="Path School", status="Pending",
            session_date=date(2026, 12, 10), shifts="Morning", modules="Speaking", format="Onsite")
        db.session.add_all([own, other_person, other_record])
        db.session.flush()
        db.session.add_all([
            ExamSessionLogisticsConcept(exam_session_id=self.record.id, instructions_html="PRIVATE OTHER MEMBER", staff_members=[other_person]),
            ExamSessionLogisticsConcept(exam_session_id=other_record.id, instructions_html="PRIVATE OTHER SESSION", staff_members=[self.person])])
        db.session.commit()
        self.assertIn(self.person, complex_logistics_staff_members_for_session(self.record.id))
        page = self.portal_page()
        self.assertIn('<ul><li><b>Your instructions</b></li></ul>', page)
        self.assertNotIn('PRIVATE OTHER', page)
        assignment.logistics_type = "Complex logistics"
        db.session.commit()
        self.assertIn('staff-detail-logistics-progress">In progress</span>', self.portal_page())
        own.status = "Confirmed"
        db.session.commit()
        self.assertIn('staff-detail-logistics-progress is-confirmed">Confirmed</span>', self.portal_page())

    def test_multiple_concepts_have_separate_titled_buttons_and_dialogs(self):
        assignment = self.portal_assignment()
        assignment.logistics_type = "Carpooling"
        for title, content in [("Traslado de ida", "Outbound instructions"), ("Traslado de vuelta", "Return instructions")]:
            db.session.add(ExamSessionLogisticsConcept(exam_session_id=self.record.id,
                instructions_title=title, instructions_html=content, staff_members=[self.person]))
        db.session.commit()
        page = self.portal_page()
        for title in ["Traslado de ida", "Traslado de vuelta"]:
            self.assertIn(f'View instructions | {title}</button>', page)
        import re
        items = re.findall(r'<div data-staff-logistics-instructions-item>(.*?)</dialog>', page, re.S)
        self.assertEqual(len(items), 2)
        self.assertIn("Outbound instructions", items[0])
        self.assertNotIn("Return instructions", items[0])
        self.assertIn("Return instructions", items[1])
        self.assertNotIn("Outbound instructions", items[1])

    def test_planner_logistics_requires_folder_and_lists_all_active_staff(self):
        members = []
        for index, value in enumerate(["Uber ride", "Complex Uber ride", "Complex logistics", "Does not apply", ""]):
            person = AcademicStaff(full_name=f"Logistics person {index}", status="Active", roles="Examiner")
            db.session.add(person)
            db.session.flush()
            db.session.add(ExamSessionExaminerAssignment(exam_session_id=self.record.id,
                team_member_id=person.id, participation_status="Pending", logistics_type=value))
            members.append(person)
        provider_type = ProviderType(name="Transport")
        concept = ExamSessionLogisticsConcept(exam_session_id=self.record.id, status="Pending")
        db.session.add_all([provider_type, concept])
        db.session.commit()
        self.assertEqual({item.id for item in complex_logistics_staff_members_for_session(self.record.id)},
                         {item.id for item in members[:3]})
        for value in ["", "not-a-url"]:
            with self.app.test_request_context(method="POST", data={"logistics_files_url": value}):
                self.assertFalse(save_exam_session_logistics(self.record))
        key = f"existing-{concept.id}"
        with self.app.test_request_context(method="POST", data={
            "logistics_files_url": "https://example.com/logistics",
            "logistics_concept_row_keys": key, f"logistics_concept_id_{key}": str(concept.id),
            f"logistics_provider_type_id_{key}": str(provider_type.id),
            f"logistics_staff_member_ids_{key}": [str(item.id) for item in members[:3]],
        }):
            self.assertTrue(save_exam_session_logistics(self.record))
            db.session.commit()
        self.assertEqual({item.id for item in concept.staff_members}, {item.id for item in members[:3]})
        page = self.client.get('/exam-session-planner?session_year=2026').get_data(as_text=True)
        for person in members[:3]:
            self.assertIn(f'<span>{person.full_name}</span>', page)

    def test_planner_without_active_logistics_does_not_require_folder(self):
        assignment = ExamSessionExaminerAssignment(exam_session_id=self.record.id, team_member_id=self.person.id,
                                                  logistics_type="Does not apply")
        db.session.add(assignment)
        db.session.commit()
        with self.app.test_request_context(method="POST", data={"logistics_files_url": ""}):
            self.assertTrue(save_exam_session_logistics(self.record))

    def test_planner_save_rejects_missing_link_without_persisting_changes(self):
        assignment = ExamSessionExaminerAssignment(exam_session_id=self.record.id, team_member_id=self.person.id,
                                                  logistics_type="Does not apply", participation_status="Pending")
        db.session.add(assignment)
        db.session.commit()
        key = f"existing-{assignment.id}"
        response = self.client.post(f'/exam-session-planner/sessions/{self.record.id}/members',
            headers={"Accept": "application/json"}, data={
                "csrf_token": "test", "session_year": "2026", "examiner_row_keys": key,
                f"examiner_assignment_id_{key}": str(assignment.id),
                f"examiner_team_member_id_{key}": str(self.person.id),
                f"examiner_participation_status_{key}": "Pending",
                f"examiner_logistics_type_{key}": "Uber ride", "logistics_files_url": "",
            })
        self.assertEqual(response.status_code, 400)
        self.assertIn("Configure the Logistics folder link", response.json["error"])
        self.assertEqual(db.session.get(ExamSessionExaminerAssignment, assignment.id).logistics_type, "Does not apply")

    def test_uber_options_disable_fuel_even_if_submitted(self):
        self.person.has_car = "Yes"
        assignment = ExamSessionExaminerAssignment(exam_session_id=self.record.id, team_member_id=self.person.id,
                                                  logistics_type="Does not apply", participation_status="Pending", km=100)
        provider_type = ProviderType(name="Transport")
        concept = ExamSessionLogisticsConcept(exam_session_id=self.record.id, status="Pending")
        db.session.add_all([assignment, provider_type, concept])
        db.session.commit()
        key = f"existing-{assignment.id}"
        concept_key = f"existing-{concept.id}"
        for value in ["Does not apply", "Uber ride", "Complex Uber ride", "Complex logistics", "Carpooling"]:
            response = self.client.post(f'/exam-session-planner/sessions/{self.record.id}/members',
                headers={"Accept": "application/json"}, data={
                    "csrf_token": "test", "session_year": "2026", "examiner_row_keys": key,
                    f"examiner_assignment_id_{key}": str(assignment.id),
                    f"examiner_team_member_id_{key}": str(self.person.id),
                    f"examiner_participation_status_{key}": "Pending",
                    f"examiner_logistics_type_{key}": value, f"examiner_km_{key}": "100",
                    f"examiner_fuel_enabled_{key}": "1", f"examiner_fuel_{key}": "100",
                    f"examiner_fuel_currency_{key}": "ARS", f"examiner_vehicle_dep_{key}": "50",
                    "logistics_files_url": "https://example.com/logistics",
                    "logistics_concept_row_keys": concept_key,
                    f"logistics_concept_id_{concept_key}": str(concept.id),
                    f"logistics_provider_type_id_{concept_key}": str(provider_type.id),
                    f"logistics_staff_member_ids_{concept_key}": str(self.person.id),
                })
            self.assertEqual(response.status_code, 200, response.json)
            item = db.session.get(ExamSessionExaminerAssignment, assignment.id)
            blocked = value in {"Uber ride", "Complex Uber ride"}
            self.assertEqual(item.fuel_enabled, not blocked)
            if blocked:
                self.assertFalse(item.fuel)
                self.assertFalse(item.vehicle_dep)


if __name__ == "__main__":
    unittest.main()
