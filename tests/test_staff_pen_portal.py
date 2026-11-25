import json
import re
import unittest
import uuid
from unittest.mock import patch
from flask import Response
from app import db, models as m
from app.pen_arrangements import completion_state
from tests import test_staff_return_materials as fixtures


class StaffPenPortalTest(unittest.TestCase):
    setUpBase=fixtures.StaffReturnMaterialsTest.setUp
    tearDown=fixtures.StaffReturnMaterialsTest.tearDown
    assign=fixtures.StaffReturnMaterialsTest.assign

    def setUp(self):
        self.setUpBase()
        self.record.pen_enabled=True
        self.assignment,self.share=self.assign('examiner',token='pen-examiner')
        self.other=m.AcademicStaff(full_name='Other Examiner',status='Active',roles='Examiner')
        db.session.add(self.other);db.session.flush()
        self.other_assignment,self.other_share=self.assign('examiner',person=self.other,token='other-pen-examiner')
        self.candidate=m.ExamSessionPenCandidate(id=str(uuid.uuid4()),exam_session_id=self.record.id,candidate_no='00041',candidate_name='Assigned Candidate',
            examiner_refs=json.dumps([str(self.person.id)]),recommendations_html='<p><strong>Extra time</strong></p><ul><li>Quiet room</li></ul><script>private_script()</script>',
            file_id='private-pen-file-123',filename='Assessment.pdf',mime_type='application/pdf')
        self.other_candidate=m.ExamSessionPenCandidate(id=str(uuid.uuid4()),exam_session_id=self.record.id,candidate_no='99999',candidate_name='PRIVATE_OTHER_CANDIDATE',
            examiner_refs=json.dumps([str(self.other.id)]),recommendations_html='<p>PRIVATE_OTHER_RECOMMENDATION</p>',file_id='other-private-file-123',filename='OTHER_PRIVATE_REPORT.pdf',mime_type='application/pdf')
        db.session.add_all([self.candidate,self.other_candidate]);db.session.commit()
        self.client=self.app.test_client()

    def page(self,share=None):
        response=self.client.get('/my-exam-sessions/'+(share or self.share).token)
        self.assertEqual(response.status_code,200)
        return response.get_data(as_text=True)

    def payload(self,page):
        details=[json.loads(value) for value in re.findall(r"data-staff-session-payload='(.*?)'",page,re.S)]
        return next(detail['pen_arrangements'] for detail in details if detail['assignment_type']=='examiner')

    def document_url(self):
        return f'/my-exam-sessions/{self.share.token}/sessions/{self.record.id}/pen-candidates/{self.candidate.id}/document'

    def verify(self):
        control=db.session.get(m.ExamSessionPenControl,self.record.id)
        if control is None:
            control=m.ExamSessionPenControl(exam_session_id=self.record.id);db.session.add(control)
        from datetime import datetime,timezone
        control.confirmed_snapshot=completion_state(self.record)['snapshot'];control.confirmed_at=datetime.now(timezone.utc)
        db.session.commit()

    def test_selected_confirmed_examiner_gets_only_own_candidates_and_pending_documents(self):
        html=self.page();payload=self.payload(html)
        self.assertEqual(payload['status'],'Pending')
        self.assertEqual([candidate['number'] for candidate in payload['candidates']],['00041'])
        self.assertIn('⚠️ Candidates with Personal Educational Needs (PENs)',html)
        self.assertIn('have <strong>Personal Educational Needs (PENs)</strong>',html)
        self.assertIn('<strong>Please read the information provided carefully and ensure that all relevant instructions are followed.</strong>',html)
        self.assertIn('00041 · Assigned Candidate',html)
        self.assertIn('<strong>Extra time</strong>',html)
        self.assertNotIn('private_script()',html)
        for private in ['PRIVATE_OTHER_CANDIDATE','PRIVATE_OTHER_RECOMMENDATION','OTHER_PRIVATE_REPORT.pdf','private-pen-file-123','other-private-file-123']:
            self.assertNotIn(private,html)
        self.assertIn(self.document_url(),html)
        with patch('app.pen_arrangements.stream_document',return_value=Response(b'private assessment')):
            response=self.client.get(self.document_url())
        self.assertEqual(response.status_code,200)
        self.assertIn('no-store',response.headers['Cache-Control'])
        self.assertEqual(response.headers['Referrer-Policy'],'no-referrer')

    def test_global_completion_status_is_shared_and_reopens_after_any_candidate_changes(self):
        self.verify()
        self.assertEqual(self.payload(self.page())['status'],'Completed')
        self.other_candidate.recommendations_html='<p>New instructions for another examiner</p>';db.session.commit()
        self.assertEqual(self.payload(self.page())['status'],'Pending')
        self.assertIn('Assigned Candidate',self.page())

    def test_participation_pen_flag_and_candidate_selection_control_visibility(self):
        for status in ['Pending','Pre-confirmed','Official confirmation sent','Declined','Cancelled']:
            self.assignment.participation_status=status;db.session.commit()
            html=self.page();self.assertNotIn('data-staff-pen-section',html);self.assertNotIn('Assigned Candidate',html)
            self.assertEqual(self.client.get(self.document_url()).status_code,404)
        self.assignment.participation_status='Confirmed';db.session.commit()
        self.record.pen_enabled=False;db.session.commit()
        self.assertNotIn('data-staff-pen-section',self.page())
        self.assertEqual(self.client.get(self.document_url()).status_code,404)
        self.record.pen_enabled=True;self.candidate.examiner_refs=json.dumps([str(self.other.id)]);db.session.commit()
        self.assertNotIn('data-staff-pen-section',self.page())
        self.assertEqual(self.client.get(self.document_url()).status_code,404)

    def test_unconfirmed_supervisor_and_confirmed_intern_do_not_grant_candidate_access(self):
        self.assignment.participation_status='Pending'
        self.assign('supervisor',person=self.person,status='Pending');self.assign('intern',person=self.person)
        self.assertNotIn('data-staff-pen-section',self.page())
        self.assertNotIn('Assigned Candidate',self.page())
        self.assertEqual(self.client.get(self.document_url()).status_code,404)

    def test_document_is_rechecked_for_candidate_session_assignment_and_current_file(self):
        url=self.document_url()
        with patch('app.pen_arrangements.stream_document',return_value=Response(b'allowed')) as stream:
            self.assertEqual(self.client.get(url.replace(self.candidate.id,self.other_candidate.id)).status_code,404)
            self.assertEqual(self.client.get(url.replace('/pen-examiner/','/invalid-token/')).status_code,404)
            self.assertEqual(self.client.get(url.replace(f'sessions/{self.record.id}', 'sessions/999999')).status_code,404)
            stream.assert_not_called()
            self.candidate.file_id='replacement-private-file';db.session.commit()
            self.assertEqual(self.client.get(url).status_code,200)
            self.assertEqual(stream.call_args.args[0].file_id,'replacement-private-file')
            self.candidate.file_id=None;self.candidate.filename=None;db.session.commit()
            self.assertEqual(self.client.get(url).status_code,404)
        self.assertNotIn('Specialist assessment report</h4>',self.page())
        self.assertIn('Recommendations for the examiner',self.page())

    def test_action_is_first_additional_link_and_candidate_dialog_ids_are_unique(self):
        # The same person also supervises and receives shipment, making all three actions applicable.
        self.assignment.is_shipment_recipient=False
        self.assign('supervisor',person=self.person)
        html=self.page()
        cell=re.search(r'<td data-label="Actions">(.*?)</td>',html,re.S).group(1)
        self.assertLess(cell.index('Access session details'),cell.index('⚠️ Personal Educational Needs'))
        self.assertLess(cell.index('⚠️ Personal Educational Needs'),cell.index('📋 End-of-session report'))
        self.assertLess(cell.index('⚠️ Personal Educational Needs'),cell.index('📦 Return of exam materials'))
        self.assertIn('class="staff-session-action-link"',cell)
        self.assertEqual(html.count('data-staff-pen-section>'),2)
        ids=re.findall(r'<dialog id="(staff-pen-[^"]+)"',html)
        self.assertEqual(len(ids),3)
        self.assertEqual(len(set(ids)),3)
        for dialog_id in ids:self.assertEqual(html.count(f'id="{dialog_id}"'),1)
        self.assertIn(f'aria-controls="{ids[0]}"',html)

    def test_multiple_candidates_and_examiners_can_share_an_arrangement(self):
        self.candidate.examiner_refs=json.dumps([str(self.person.id),str(self.other.id)])
        self.other_candidate.examiner_refs=json.dumps([str(self.person.id)])
        db.session.commit()
        self.assertEqual(len(self.payload(self.page())['candidates']),2)
        self.assertEqual(len(self.payload(self.page(self.other_share))['candidates']),1)
        self.assertNotIn('PRIVATE_OTHER_CANDIDATE',self.page(self.other_share))

    def test_confirmed_supervisor_and_remote_supervisor_see_all_cases_with_examiners(self):
        self.assignment.participation_status='Pending'
        supervisor,share=self.assign('supervisor',person=self.person)
        for remote in [False,True]:
            supervisor.is_remote=remote;db.session.commit()
            html=self.page()
            details=[json.loads(value) for value in re.findall(r"data-staff-session-payload='(.*?)'",html,re.S)]
            payload=next(detail['pen_arrangements'] for detail in details if detail['assignment_type']=='supervisor')
            self.assertTrue(payload['supervisor'])
            self.assertEqual(len(payload['candidates']),2)
            self.assertEqual(payload['status'],'Pending')
            self.assertEqual({name for candidate in payload['candidates'] for name in candidate['examiner_names']},{self.person.full_name,self.other.full_name})
            self.assertIn('Candidates in this exam session have <strong>Personal Educational Needs (PENs)</strong>',html)
            self.assertIn('<strong>examiners concerned are aware of and understand the arrangements required</strong>',html)
            self.assertIn('<strong>Session portals</strong>',html)
            self.assertIn('Examiner(s): Other Examiner',html)
            with patch('app.pen_arrangements.stream_document',return_value=Response(b'case for supervisor')):
                self.assertEqual(self.client.get(self.document_url().replace(self.candidate.id,self.other_candidate.id)).status_code,200)
        self.verify()
        details=[json.loads(value) for value in re.findall(r"data-staff-session-payload='(.*?)'",self.page(),re.S)]
        self.assertEqual(next(detail['pen_arrangements']['status'] for detail in details if detail['assignment_type']=='supervisor'),'Completed')

    def test_supervisor_shortcut_uses_all_cases_when_the_same_person_is_also_examiner(self):
        supervisor,_=self.assign('supervisor',person=self.person)
        html=self.page()
        cell=re.search(r'<td data-label="Actions">(.*?)</td>',html,re.S).group(1)
        pen_link=re.search(r'<a[^>]*data-staff-pen-open[^>]*>',cell).group(0)
        self.assertIn('data-staff-pen-role="supervisor"',pen_link)
        self.assertLess(cell.index('⚠️ Personal Educational Needs'),cell.index('📋 End-of-session report'))
        details=[json.loads(value) for value in re.findall(r"data-staff-session-payload='(.*?)'",html,re.S)]
        self.assertEqual(len(next(detail['pen_arrangements']['candidates'] for detail in details if detail['assignment_type']=='examiner')),1)
        self.assertEqual(len(next(detail['pen_arrangements']['candidates'] for detail in details if detail['assignment_type']=='supervisor')),2)
        supervisor.is_remote=True;db.session.commit()
        html=self.page()
        links=re.findall(r'<a[^>]*data-staff-pen-open[^>]*>',html)
        self.assertEqual(len(links),2)
        self.assertTrue(any('data-staff-pen-role="examiner"' in link for link in links))
        self.assertTrue(any('data-staff-pen-role="supervisor"' in link for link in links))

    def test_supervisor_access_is_revoked_without_confirmed_session_role_or_pen(self):
        supervisor,_=self.assign('supervisor',person=self.person)
        url=self.document_url().replace(self.candidate.id,self.other_candidate.id)
        for status in ['Pending','Pre-confirmed','Official confirmation sent','Declined','Cancelled']:
            supervisor.participation_status=status;db.session.commit()
            with patch('app.pen_arrangements.stream_document') as stream:
                self.assertEqual(self.client.get(url).status_code,404);stream.assert_not_called()
            self.assertNotIn('PRIVATE_OTHER_CANDIDATE',self.page())
        supervisor.participation_status='Confirmed';self.record.pen_enabled=False;db.session.commit()
        self.assertNotIn('data-staff-pen-section',self.page())
        self.assertEqual(self.client.get(url).status_code,404)
        self.record.pen_enabled=True;db.session.delete(supervisor);db.session.commit()
        self.assertEqual(self.client.get(url).status_code,404)

    def test_exam_centre_supervisor_cases_explain_examiner_assignment_does_not_apply(self):
        self.record.format='Online at exam centre';db.session.commit()
        self.assign('supervisor',person=self.person)
        html=self.page()
        self.assertIn('data-staff-pen-section',html)
        self.assertIn('⚠️ Personal Educational Needs</a>',html)
        self.assertIn('Examiner assignment does not apply to this session format',html)
        self.assertIn('Assigned Candidate',html);self.assertIn('PRIVATE_OTHER_CANDIDATE',html)
        with patch('app.pen_arrangements.stream_document',return_value=Response(b'assessment')):
            self.assertEqual(self.client.get(self.document_url()).status_code,200)

    def test_supervisor_block_is_hidden_without_cards_and_shared_cases_list_every_examiner(self):
        self.assign('supervisor',person=self.person)
        self.candidate.examiner_refs=json.dumps([str(self.person.id),str(self.other.id)]);db.session.commit()
        self.assertIn('Examiner(s): Test Staff, Other Examiner',self.page())
        self.other_candidate.examiner_refs=json.dumps(['removed-examiner']);db.session.commit()
        self.assertIn('Examiner no longer assigned to this session',self.page())
        db.session.delete(self.candidate);db.session.delete(self.other_candidate);db.session.commit()
        self.assertNotIn('data-staff-pen-section',self.page())
        self.assertNotIn('⚠️ Personal Educational Needs</a>',self.page())

    def test_online_confirmed_examiner_has_the_same_pen_access(self):
        self.record.format='Online';db.session.commit()
        self.assertIn('data-staff-pen-section',self.page())
        self.assertIn('⚠️ Personal Educational Needs</a>',self.page())
        with patch('app.pen_arrangements.stream_document',return_value=Response(b'online assessment')):
            self.assertEqual(self.client.get(self.document_url()).status_code,200)

    def test_potential_examiner_reference_is_scoped_to_its_own_share(self):
        person=m.PotentialEntry(full_name='Potential Examiner',status='Potential')
        db.session.add(person);db.session.flush()
        assignment=m.ExamSessionExaminerAssignment(exam_session_id=self.record.id,potential_entry_id=person.id,participation_status='Confirmed')
        share=m.StaffExamSessionsShare(person_ref='potential:'+str(person.id),token='potential-pen')
        db.session.add_all([assignment,share]);db.session.flush()
        db.session.add(m.StaffExamSessionSubmission(exam_session_id=self.record.id,assignment_type='examiner',assignment_id=assignment.id,share_id=share.id))
        self.candidate.examiner_refs=json.dumps([share.person_ref]);db.session.commit()
        self.assertIn('Assigned Candidate',self.page(share))
        self.assertNotIn('Assigned Candidate',self.page())
        url=self.document_url().replace('/pen-examiner/','/potential-pen/')
        with patch('app.pen_arrangements.stream_document',return_value=Response(b'allowed')):
            self.assertEqual(self.client.get(url).status_code,200)
            self.assertEqual(self.client.get(self.document_url()).status_code,404)

    def test_no_optional_data_still_shows_the_assigned_candidate(self):
        self.candidate.file_id=None;self.candidate.filename=None;self.candidate.recommendations_html='';db.session.commit()
        html=self.page()
        self.assertIn('00041 · Assigned Candidate',html)
        self.assertIn('No additional documents or recommendations have been added yet.',html)
