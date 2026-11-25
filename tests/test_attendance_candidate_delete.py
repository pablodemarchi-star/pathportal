"""Deleting review cases leaves source absence lists/reports intact."""
import json
import unittest
from unittest.mock import patch, call
from app import db, models as m
from app import post_attendance as attendance
from tests import test_post_attendance as fixtures


class AttendanceCandidateDeleteTest(unittest.TestCase):
    setUp=fixtures.PostAttendanceTest.setUp
    tearDown=fixtures.PostAttendanceTest.tearDown
    new_session=fixtures.PostAttendanceTest.new_session
    fake_upload=fixtures.PostAttendanceTest.fake_upload
    prepare_review=fixtures.PostAttendanceTest.prepare_review

    def candidate(self,status='Pending',document=True,number='00027'):
        institution=attendance.main_institution(self.record,True)
        doc=None
        if document:
            doc=m.AttendanceDocument(file_id='review-doc-'+number,folder_id='absence-folder-123456',filename='Certificate.pdf',mime_type='application/pdf')
            db.session.add(doc)
        candidate=m.AbsenceCandidate(exam_session_id=self.record.id,institution_id=institution.id,number=number,number_key=number,name='Review Candidate',document=doc,
            review_status=status,approved=status=='Confirmed',exam='B2 Competency',institution_name=self.record.exam_session_name,absent_modules='["Speaking"]')
        db.session.add(candidate);db.session.flush()
        if doc:db.session.add(m.AbsenceSubmissionEvent(candidate_id=candidate.id,file_id=doc.file_id,action='submitted'))
        db.session.commit();return candidate

    def row(self,candidate):
        response=self.client.get(self.url)
        self.assertEqual(response.status_code,200)
        return next(row for row in response.json['state']['candidates'] if row['id']==candidate.id)

    def delete(self,candidate,**fields):
        data=dict(csrf_token='test',action='delete_candidate',candidate_id=candidate.id,confirmed='1',delete_version=self.row(candidate)['delete_version'])
        data.update(fields)
        return self.client.post(self.url,data=data)

    def test_pending_delete_requires_confirmation_and_keeps_absence_records(self):
        self.prepare_review();candidate=self.candidate();ident=candidate.id;file_id=candidate.document_id
        originals={row.id:row.document_id for row in m.AttendanceModule.query.all()}
        notifications=m.AttendanceInstitution.query.first().notifications
        attendance.control(self.record).review_results_notified=True;db.session.commit()
        self.assertTrue(self.row(candidate)['delete_allowed'])
        self.assertEqual(self.delete(candidate,confirmed='0').status_code,400)
        response=self.delete(candidate)
        self.assertEqual(response.status_code,200,response.json)
        self.assertEqual(response.json['state']['candidates'],[])
        self.assertIsNone(db.session.get(m.AbsenceCandidate,ident))
        self.assertIsNone(db.session.get(m.AttendanceDocument,file_id))
        self.assertEqual(m.AbsenceSubmissionEvent.query.count(),0)
        self.trash.assert_called_once_with(file_id)
        self.assertEqual({row.id:row.document_id for row in m.AttendanceModule.query.all()},originals)
        self.assertEqual(m.AttendanceInstitution.query.first().notifications,notifications)
        self.assertTrue(attendance.control(self.record).verified)
        self.assertFalse(attendance.control(self.record).review_results_notified)
        event=m.AttendanceEvent.query.filter_by(action='candidate_deleted').one()
        self.assertEqual(json.loads(event.payload)['number'],'00027');self.assertNotIn('EditOK',event.payload)

    def test_confirmed_and_declined_require_server_checked_password(self):
        for index,status in enumerate(['Confirmed','Declined']):
            candidate=self.candidate(status,number=str(index))
            for password in ['', 'wrong', 'editok']:
                response=self.delete(candidate,password=password)
                self.assertEqual(response.status_code,400,response.json)
                self.assertIn('password',response.json['error'])
            self.trash.assert_not_called()
            file_id=candidate.document_id
            response=self.delete(candidate,password='EditOK')
            self.assertEqual(response.status_code,200,response.json)
            self.trash.assert_called_once_with(file_id);self.trash.reset_mock()

    def test_stale_candidate_snapshot_cannot_delete_a_changed_or_newly_confirmed_case(self):
        candidate=self.candidate();old=self.row(candidate)['delete_version']
        candidate.review_status='Confirmed';candidate.notes='Reviewed by another user';db.session.commit()
        response=self.delete(candidate,delete_version=old)
        self.assertEqual(response.status_code,400);self.assertIn('changed',response.json['error'])
        self.assertEqual(self.delete(candidate).status_code,400)
        self.trash.assert_not_called()
        self.assertEqual(self.delete(candidate,password='EditOK').status_code,200)

    def test_permissions_csrf_and_session_scoping(self):
        candidate=self.candidate()
        self.assertEqual(self.delete(candidate,csrf_token='wrong').status_code,400)
        with patch('app.routes.user_can_edit',return_value=False):self.assertEqual(self.delete(candidate).status_code,403)
        other=self.new_session('Other',self.record.session_date)
        other_candidate=m.AbsenceCandidate(exam_session_id=other.id,institution_id=attendance.main_institution(other,True).id,number='9',number_key='9',name='Other')
        db.session.add(other_candidate);db.session.commit()
        self.assertEqual(self.delete(candidate,candidate_id=other_candidate.id).status_code,404)
        self.trash.assert_not_called()
        self.assertEqual(self.app.test_client().post(self.url,data={'action':'delete_candidate'}).status_code,302)

    def test_same_day_online_report_case_can_be_deleted_without_touching_the_report(self):
        self.record.format='Online';self.record.session_date=self.today;db.session.commit()
        candidate=self.candidate(document=False)
        candidate.it_reason='Connection lost';candidate.institution_name=''
        person=m.AcademicStaff(full_name='Supervisor',status='Active',roles='Supervisor');db.session.add(person);db.session.flush()
        assignment=m.ExamSessionSupervisorAssignment(exam_session_id=self.record.id,team_member_id=person.id,participation_status='Confirmed')
        share=m.StaffExamSessionsShare(person_ref=str(person.id),token='delete-source-report')
        db.session.add_all([assignment,share]);db.session.flush()
        submission=m.StaffExamSessionSubmission(exam_session_id=self.record.id,assignment_type='supervisor',assignment_id=assignment.id,share_id=share.id)
        db.session.add(submission);db.session.flush()
        source=json.dumps([dict(number=candidate.number,name=candidate.name,reason='Connection lost',modules=['Speaking'])])
        report=m.StaffExamSessionReport(exam_session_id=self.record.id,submission_id=submission.id,schedule_outcome='There were no delays',it_absences=source,it_issues=True)
        db.session.add(report);db.session.commit()
        attendance.control(self.record).submission_status='pending';db.session.commit()
        response=self.delete(candidate)
        self.assertEqual(response.status_code,200,response.json)
        self.assertEqual(m.StaffExamSessionReport.query.one().it_absences,source)
        self.trash.assert_not_called()
        institutional=self.candidate(document=True,number='second')
        self.assertFalse(self.row(institutional)['delete_allowed'])
        self.assertEqual(self.delete(institutional).status_code,403)

    def test_failed_trash_or_commit_preserves_candidate_and_restores_file(self):
        candidate=self.candidate();ident=candidate.id;file_id=candidate.document_id
        with patch('app.attendance_drive.trash',side_effect=attendance.drive.DriveStorageError('Drive unavailable')):
            self.assertEqual(self.delete(candidate).status_code,400)
        self.assertIsNotNone(db.session.get(m.AbsenceCandidate,ident))
        snapshot=self.row(candidate)['delete_version']
        data=dict(csrf_token='test',action='delete_candidate',candidate_id=ident,confirmed='1',delete_version=snapshot)
        with patch.object(db.session,'commit',side_effect=RuntimeError('Database unavailable')):
            response=self.client.post(self.url,data=data)
        self.assertEqual(response.status_code,500)
        self.assertEqual(self.trash.call_args_list,[call(file_id),call(file_id,False)])
        self.assertIsNotNone(db.session.get(m.AbsenceCandidate,ident))
        self.assertIsNotNone(db.session.get(m.AttendanceDocument,file_id))
        self.assertEqual(m.AbsenceSubmissionEvent.query.count(),1)
        self.assertEqual(m.AttendanceEvent.query.filter_by(action='candidate_deleted').count(),0)

    def test_document_shared_with_original_absence_list_is_protected(self):
        candidate=self.candidate()
        db.session.add(m.AttendanceModule(institution_id=candidate.institution_id,module='Speaking',document_id=candidate.document_id));db.session.commit()
        response=self.delete(candidate)
        self.assertEqual(response.status_code,400);self.assertIn('another attendance record',response.json['error'])
        self.trash.assert_not_called()

    def test_reconfirmation_message_and_masked_password_are_rendered(self):
        page=self.client.get('/pre-session-control-tower?view=post&session_year=2026').get_data(as_text=True)
        for value in ['Delete this candidate?','Absence documentation review','Drive trash','Absence records','End-of-session report','Sinapsis attendance status','These records will not be updated automatically.','type="password"','Delete candidate']:
            self.assertIn(value,page)
        self.assertNotIn('EditOK',page)
        self.assertLess(page.index('js/attendance_candidate_delete.js'),page.index('js/post_attendance.js'))
