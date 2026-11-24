import json
import unittest
from unittest.mock import patch
from app import db
from app import models as m
from app.staff_report_components import it_module_options, validate_it
from tests import test_staff_report_components as fixtures


class StaffReportITIssuesTest(unittest.TestCase):
    setUp = fixtures.StaffReportComponentsTest.setUp
    tearDown = fixtures.StaffReportComponentsTest.tearDown
    post = fixtures.StaffReportComponentsTest.post
    attendance_state = fixtures.StaffReportComponentsTest.attendance_state

    def online(self, modules='Listening and speaking,Reading and writing,Speaking'):
        self.record.format = 'Online'; self.record.modules = modules; db.session.commit()

    def entry(self, number='001230', **values):
        item = dict(number=number, name='Candidate Example', exam='B2 Competency',
                    modules=['Listening and speaking','Reading and writing'], reason='Power outage prevented completion.')
        item.update(values)
        return item

    def submit(self, rows, **values):
        return self.post(it_issues='1', it_absences=json.dumps(rows), **values)

    def test_module_options_follow_exam_and_session(self):
        self.online()
        options = it_module_options(self.record)
        self.assertEqual(options['Ready'], ['Speaking'])
        self.assertEqual(options['B2 Competency'], ['Listening and speaking', 'Reading and writing'])
        self.online('Speaking')
        self.assertNotIn('B2 Competency', it_module_options(self.record))
        self.online('Reading and writing')
        self.assertEqual(it_module_options(self.record)['B2 Competency'], ['Reading and writing'])
        self.assertNotIn('Ready', it_module_options(self.record))

    def test_visible_for_all_online_sessions_and_requires_explicit_choice(self):
        for format_name, modules, visible in [('Online','Speaking',True),('Online','Reading and writing',True),
                                              ('Online','Listening and speaking',True),('Onsite','Speaking',False)]:
            self.record.format = format_name; self.record.modules = modules; db.session.commit()
            html = self.client.get(f'/my-exam-sessions/{self.share.token}?session_year=2026').get_data(as_text=True)
            self.assertEqual('<b>Candidate IT issues</b>' in html, visible)
            if 'Listening and speaking' in modules and visible:
                self.assertLess(html.index('<b>Listening and Speaking module completion</b>'),html.index('<b>Candidate IT issues</b>'))
        self.online('Reading and writing')
        for choice in ('', 'invalid'):
            response = self.post(it_issues=choice)
            self.assertEqual(response.status_code, 400)
        response = self.post(it_issues='0', it_absences=json.dumps([self.entry()]))
        self.assertEqual(response.status_code,200,response.json)
        saved = m.StaffExamSessionReport.query.one()
        self.assertFalse(saved.it_issues)
        self.assertEqual(saved.it_absences,'[]')
        self.assertEqual(m.AbsenceCandidate.query.count(),0)

    def test_all_fields_and_allowed_modules_are_validated_on_server(self):
        self.online()
        self.assertEqual(self.submit([]).status_code,400)
        for key in ('number','name','exam','reason'):
            invalid=self.entry();invalid[key]=''
            self.assertEqual(self.submit([invalid]).status_code,400,key)
        for modules in ([],['Unknown'],['Listening'],['Speaking','Reading and writing'],['Speaking']):
            self.assertEqual(self.submit([self.entry(modules=modules)]).status_code,400,modules)
        self.assertEqual(self.submit([self.entry(),self.entry()]).status_code,400)
        self.online('Reading and writing')
        self.assertEqual(self.submit([self.entry()]).status_code,400)
        self.assertEqual(m.AbsenceCandidate.query.count(),0)
        self.assertEqual(m.StaffExamSessionReport.query.count(),0)

    def test_speaking_only_and_combined_modules_are_accepted(self):
        self.online()
        rows=[self.entry(),self.entry('000002',name='Speaking Candidate',exam='Ready',modules=['Speaking'])]
        response=self.submit(rows)
        self.assertEqual(response.status_code,200,response.json)
        self.assertEqual(m.AbsenceCandidate.query.count(),2)
        self.assertEqual(json.loads(m.AbsenceCandidate.query.filter_by(number_key='000002').one().absent_modules),['Speaking'])
        saved=m.StaffExamSessionReport.query.one()
        self.assertTrue(saved.it_issues)
        self.assertEqual(len(json.loads(saved.it_absences)),2)
        state=self.attendance_state().json['state']
        first=next(candidate for candidate in state['candidates'] if candidate['number']=='001230')
        self.assertEqual(first['it_reason'],self.entry()['reason'])
        self.assertEqual(set(first['allowed_modules']),{'Listening and speaking','Reading and writing'})
        self.assertTrue(state['has_absences'])

    def test_same_candidate_in_both_sections_merges_and_keeps_both_reasons(self):
        self.online()
        component=dict(number='001230',name='Candidate Example',institution='Example School',exam='B2 Competency',component='Listening',reason='Component absence explanation.')
        response=self.submit([self.entry()],component_completion='component_absences',component_absences=json.dumps([component]))
        self.assertEqual(response.status_code,200,response.json)
        candidate=m.AbsenceCandidate.query.one()
        self.assertEqual(candidate.component_reason,component['reason'])
        self.assertEqual(candidate.it_reason,self.entry()['reason'])
        self.assertEqual(set(json.loads(candidate.absent_modules)),{'Listening','Listening and speaking','Reading and writing'})
        state=self.attendance_state().json['state']['candidates'][0]
        self.assertEqual(state['component_reason'],component['reason'])
        self.assertEqual(state['it_reason'],self.entry()['reason'])

    def test_candidate_identity_must_match_across_sections(self):
        self.online()
        component=dict(number='001230',name='Candidate Example',institution='Example School',exam='B2 Competency',component='Listening',reason='Component absence explanation.')
        for key,value in [('name','Different candidate'),('exam','B1 Progress')]:
            response=self.submit([self.entry(**{key:value})],component_completion='component_absences',component_absences=json.dumps([component]))
            self.assertEqual(response.status_code,400,response.json)
            self.assertIn('must match',response.json['error'])
        self.assertEqual(m.AbsenceCandidate.query.count(),0)
        self.assertEqual(m.StaffExamSessionReport.query.count(),0)

    def test_it_reason_update_reopens_review_and_preserves_file_and_component_reason(self):
        from app.staff_report_components import merge
        self.online()
        merge(self.record,[self.entry()],reason_field='it_reason');db.session.commit()
        candidate=m.AbsenceCandidate.query.one()
        document=m.AttendanceDocument(file_id='ITproof',folder_id='folder',filename='proof.pdf',mime_type='application/pdf')
        db.session.add(document);candidate.document=document
        candidate.component_reason='Keep previous component reason.'
        candidate.review_status='Confirmed';candidate.approved=True;db.session.commit()
        merge(self.record,[self.entry(reason='New IT explanation')],reason_field='it_reason');db.session.commit()
        self.assertEqual(candidate.document_id,'ITproof')
        self.assertEqual(candidate.component_reason,'Keep previous component reason.')
        self.assertEqual(candidate.it_reason,'New IT explanation')
        self.assertEqual(candidate.review_status,'Pending')
        self.assertFalse(candidate.approved)

    def test_speaking_exclusivity_is_independent_of_current_exam_configuration(self):
        self.online()
        # Future exam configurations must still obey the explicit exclusivity rule.
        with patch('app.staff_report_components.it_module_options', return_value={'B2 Competency':['Speaking','Reading and writing']}):
            with self.assertRaisesRegex(ValueError,'cannot be combined'):
                validate_it(self.record,{'it_issues':'1','it_absences':json.dumps([self.entry(modules=['Speaking','Reading and writing'])])})

    def test_it_only_evidence_follows_attendance_review_and_notification_flow(self):
        from app import post_attendance as attendance
        self.online()
        response=self.submit([self.entry(modules=['Reading and writing'])])
        self.assertEqual(response.status_code,200,response.json)
        candidate=m.AbsenceCandidate.query.one()
        self.attendance_state()
        self.client.post(f'/pre-session-control-tower/post/sessions/{self.record.id}/attendance',data=dict(csrf_token='test',action='candidate',candidate_id=candidate.id,field='institution_name',value='Example School'))
        institution=db.session.get(m.AttendanceInstitution,candidate.institution_id)
        institution.notifications='{"external":true}'
        control=attendance.control(self.record,True)
        control.submission_status='completed';control.verified=True
        candidate.rescheduled_for=str(self.record.id)
        db.session.commit()
        self.attendance_state()
        response=self.client.post(f'/pre-session-control-tower/post/sessions/{self.record.id}/attendance',data=dict(
            csrf_token='test',action='candidate',candidate_id=candidate.id,field='review',value='Confirmed',previous_file_id=''))
        self.assertEqual(response.status_code,200,response.json)
        self.assertTrue(response.json['state']['results_notification_enabled'])
        self.assertIn('001230',response.json['state']['candidates'][0]['whatsapp_message'])
        self.assertIsNone(candidate.document_id)

    def test_original_institution_name_does_not_create_an_ambiguous_external_card(self):
        self.online()
        response=self.submit([self.entry(institution=self.record.exam_session_name)])
        self.assertEqual(response.status_code,200,response.json)
        self.assertTrue(m.AttendanceInstitution.query.one().is_main)
        row=self.attendance_state().json['state']['candidates'][0]
        self.assertIn('B2 Competency',row['allowed_exams'])

    def test_forged_onsite_it_data_is_ignored(self):
        self.record.format='Onsite';db.session.commit()
        response=self.submit([self.entry()])
        self.assertEqual(response.status_code,200,response.json)
        self.assertIsNone(m.StaffExamSessionReport.query.one().it_issues)
        self.assertEqual(m.AbsenceCandidate.query.count(),0)
