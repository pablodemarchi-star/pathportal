import json
import os
import unittest
from datetime import date

os.environ['DATABASE_URL'] = 'sqlite:///:memory:'
from app import create_app, db
from app.models import (AcademicStaff, ExamSession, ExamSessionYear, ExamSessionSupervisorAssignment,
    ExamSessionExaminerAssignment, ExamSessionInternAssignment, StaffExamSessionsShare, StaffExamSessionSubmission)


class StaffConfirmationPersistenceTest(unittest.TestCase):
    def setUp(self):
        self.app=create_app(); self.app.config['TESTING']=True
        self.context=self.app.app_context(); self.context.push()
        db.drop_all(); db.create_all()
        db.session.add(ExamSessionYear(year=2026))
        self.record=ExamSession(exam_session_name='Confirmation persistence session',category='Path School',
            status='Pending',session_date=date(2026,11,20),shifts='Morning',modules='Speaking',format='Online')
        db.session.add(self.record); db.session.commit()
        self.client=self.app.test_client()
        with self.client.session_transaction() as state: state.update(user='admin',csrf_token='test')

    def tearDown(self):
        db.session.remove(); db.drop_all(); self.context.pop()

    def member(self, name, role):
        member=AcademicStaff(full_name=name,status='Active',roles=role,email=name.replace(' ','').lower()+'@example.com')
        db.session.add(member); db.session.flush()
        return member

    def save(self, data):
        return self.client.post(f'/exam-session-planner/sessions/{self.record.id}/members',
            data={'csrf_token':'test','session_year':'2026','modal_action':'save',**data},headers={'Accept':'application/json'})

    def test_portal_acceptance_survives_other_card_edits_for_all_staff_roles(self):
        for role,model in [('supervisor',ExamSessionSupervisorAssignment),('examiner',ExamSessionExaminerAssignment),('intern',ExamSessionInternAssignment)]:
            with self.subTest(role=role):
                person=self.member(role.title()+' Person',role.title())
                assignment=model(exam_session_id=self.record.id,team_member_id=person.id,participation_status='Official confirmation sent')
                share=StaffExamSessionsShare(person_ref=str(person.id),token=role+'-confirm-token')
                db.session.add_all([assignment,share]); db.session.flush()
                db.session.add(StaffExamSessionSubmission(share_id=share.id,exam_session_id=self.record.id,assignment_type=role,assignment_id=assignment.id))
                db.session.commit()
                confirm=f'/my-exam-sessions/{share.token}/sessions/{self.record.id}/assignments/{role}/{assignment.id}/confirm'
                self.assertEqual(self.client.post(confirm,data={'csrf_token':'test'}).status_code,303)
                self.assertEqual(assignment.participation_status,'Confirmed')
                key=f'existing-{assignment.id}'
                # Real browsers omit the disabled selected Confirmed option.
                response=self.save({f'{role}_row_keys':key,f'{role}_assignment_id_{key}':str(assignment.id),
                    f'{role}_team_member_id_{key}':str(person.id),f'{role}_logistics_type_{key}':'Does not apply',
                    f'{role}_start_time_{key}':'09:00',f'{role}_end_time_{key}':'12:00'})
                self.assertEqual(response.status_code,200,response.json)
                self.assertEqual(assignment.participation_status,'Confirmed')
                self.assertEqual(response.json['saved_values'][f'{role}_participation_status_{key}'],'Confirmed')
                page=self.client.get(f'/my-exam-sessions/{share.token}').get_data(as_text=True)
                awaiting=page.split('aria-labelledby="awaiting-sessions-title"',1)[1].split('</section>',1)[0]
                self.assertNotIn(self.record.exam_session_name,awaiting)
                self.assertIn(f'data-confirmed-session="{self.record.id}"',page)
                self.assertEqual(self.record.status,'Pending')  # Other session requirements are separate.

    def test_missing_status_does_not_transfer_confirmation_to_a_replacement(self):
        first=self.member('Original examiner','Examiner');second=self.member('Replacement examiner','Examiner')
        assignment=ExamSessionExaminerAssignment(exam_session_id=self.record.id,team_member_id=first.id,participation_status='Confirmed')
        db.session.add(assignment);db.session.commit();key=f'existing-{assignment.id}'
        response=self.save({'examiner_row_keys':key,f'examiner_assignment_id_{key}':str(assignment.id),f'examiner_team_member_id_{key}':str(second.id)})
        self.assertEqual(response.status_code,200,response.json)
        self.assertEqual(assignment.team_member_id,second.id)
        self.assertEqual(assignment.participation_status,'Pending')

    def test_explicit_pending_reset_remains_possible(self):
        person=self.member('Explicit reset examiner','Examiner')
        assignment=ExamSessionExaminerAssignment(exam_session_id=self.record.id,team_member_id=person.id,participation_status='Confirmed')
        db.session.add(assignment);db.session.commit();key=f'existing-{assignment.id}'
        response=self.save({'examiner_row_keys':key,f'examiner_assignment_id_{key}':str(assignment.id),
            f'examiner_team_member_id_{key}':str(person.id),f'examiner_participation_status_{key}':'Pending'})
        self.assertEqual(response.status_code,200,response.json)
        self.assertEqual(assignment.participation_status,'Pending')

    def test_missing_emergency_statuses_do_not_shift_onto_other_contacts(self):
        first=self.member('Emergency one','Supervisor');second=self.member('Emergency two','Supervisor')
        self.record.emergency_contact_required=True
        self.record.emergency_contact_member_id=first.id
        self.record.emergency_contact_participation_status='Confirmed'
        self.record.emergency_contact_additional_contacts=json.dumps([{'member_id':second.id,'status':'Pre-confirmed','start_time':'','end_time':''}])
        db.session.commit()
        data={'emergency_contact_required':'1','emergency_contact_member_id':[str(first.id),str(second.id)],
              'emergency_contact_participation_status':['Pre-confirmed']}
        response=self.save(data)
        self.assertEqual(response.status_code,200,response.json)
        self.assertEqual(self.record.emergency_contact_participation_status,'Confirmed')
        self.assertEqual(self.record.additional_emergency_contacts_list()[0]['status'],'Pre-confirmed')
        data['emergency_contact_participation_status']=['Confirmed','Pending']
        response=self.save(data)
        self.assertEqual(response.status_code,200,response.json)
        self.assertEqual(self.record.emergency_contact_participation_status,'Confirmed')
        self.assertEqual(self.record.additional_emergency_contacts_list()[0]['status'],'Pending')

    def test_editing_one_card_preserves_omitted_confirmations_on_other_cards(self):
        first=self.member('First confirmed examiner','Examiner');second=self.member('Second confirmed examiner','Examiner')
        rows=[ExamSessionExaminerAssignment(exam_session_id=self.record.id,team_member_id=person.id,participation_status='Confirmed') for person in (first,second)]
        db.session.add_all(rows);db.session.commit()
        keys=[f'existing-{item.id}' for item in rows]
        data={'examiner_row_keys':keys}
        for key,item in zip(keys,rows):
            data[f'examiner_assignment_id_{key}']=str(item.id)
            data[f'examiner_team_member_id_{key}']=str(item.team_member_id)
        data[f'examiner_start_time_{keys[0]}']='09:00'
        data[f'examiner_end_time_{keys[0]}']='12:00'
        response=self.save(data)
        self.assertEqual(response.status_code,200,response.json)
        self.assertEqual([item.participation_status for item in rows],['Confirmed','Confirmed'])
        self.assertEqual(rows[1].team_member_id,second.id)

    def test_changing_person_cannot_reuse_the_previous_person_confirmation_explicitly(self):
        first=self.member('Previously confirmed examiner','Examiner');second=self.member('Another examiner','Examiner')
        assignment=ExamSessionExaminerAssignment(exam_session_id=self.record.id,team_member_id=first.id,participation_status='Confirmed')
        db.session.add(assignment);db.session.commit();key=f'existing-{assignment.id}'
        response=self.save({'examiner_row_keys':key,f'examiner_assignment_id_{key}':str(assignment.id),
            f'examiner_team_member_id_{key}':str(second.id),f'examiner_participation_status_{key}':'Confirmed'})
        self.assertEqual(response.status_code,400)
        self.assertEqual(assignment.team_member_id,first.id)
        self.assertEqual(assignment.participation_status,'Confirmed')
