import json
import os
import unittest
from datetime import date, datetime, timezone
from unittest.mock import patch
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'
from app import create_app, db
from app import models as m
from app.exam_centre_feedback import feedback_available
from app.exam_centre_feedback_text import QUESTIONS, OPEN_QUESTIONS
from app.routes import LOCAL_TZ, staff_report_feedback_submitted


class ExamCentreFeedbackTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app(); self.app.config['TESTING'] = True
        self.context = self.app.app_context(); self.context.push()
        db.drop_all(); db.create_all()
        self.record = m.ExamSession(exam_session_name='Feedback session',category='Path School',status='Pending',
            session_date=datetime.now(LOCAL_TZ).date(),shifts='Morning',modules='Speaking',format='Onsite')
        db.session.add(self.record);db.session.flush()
        self.share=m.ExamSessionJourneyShare(exam_session_id=self.record.id,audience='institution',token='institution-feedback')
        db.session.add(self.share);db.session.commit()
        self.client=self.app.test_client()
        self.page=f'/path-session-journey/{self.share.token}/institution'
        self.url=self.page+f'/feedback/{self.record.id}'
        with self.client.session_transaction() as state: state['csrf_token']='test'

    def tearDown(self):
        db.session.remove();db.drop_all();self.context.pop()

    def answers(self, **changes):
        values={'csrf_token':'test','language':'en'}
        values.update({q[0]+'_score':'8' for q in QUESTIONS})
        values.update(changes)
        return values

    def post(self, **changes):
        with patch('app.exam_centre_feedback.feedback_available',return_value=True):
            return self.client.post(self.url,data=self.answers(**changes))

    def test_date_boundaries_in_gmt_minus_three(self):
        self.record.session_date=date(2026,11,13)
        for value,expected in [('2026-11-13T02:59:59+00:00',False),('2026-11-13T03:00:00+00:00',True),('2026-11-14T02:59:59+00:00',True),('2026-11-14T03:00:00+00:00',False)]:
            self.assertEqual(feedback_available(self.record,datetime.fromisoformat(value)),expected)

    def test_four_ratings_required_exact_integer_range(self):
        for question in QUESTIONS:
            key=question[0]+'_score'
            for value in ('','0','11','1.5','bad'):
                response=self.post(**{key:value})
                self.assertEqual(response.status_code,400)
                self.assertIn(key,response.json['fields'])
        self.assertEqual(m.ExamCentreFeedback.query.count(),0)

    def test_low_scores_require_independent_comments(self):
        for question in QUESTIONS:
            key=question[0]
            for score in ('1','7'):
                response=self.post(**{key+'_score':score,key+'_comment':' '})
                self.assertEqual(response.status_code,400)
                self.assertIn(key+'_comment',response.json['fields'])
        values={q[0]+'_score':'7' for q in QUESTIONS}
        values.update({q[0]+'_comment':'Improve '+q[0] for q in QUESTIONS})
        self.assertEqual(self.post(**values).status_code,200)
        saved=m.ExamCentreFeedback.query.one()
        for q in QUESTIONS:
            self.assertEqual(getattr(saved,q[0]+'_score'),7)
            self.assertEqual(getattr(saved,q[0]+'_comment'),'Improve '+q[0])

    def test_optional_answers_timestamp_and_lock_across_languages(self):
        self.assertEqual(self.post(worked_well='Friendly team',improvements_noticed='Better timing',improvements_needed='Clearer instructions',organisation_comment='Hidden high-score comment').status_code,200)
        saved=m.ExamCentreFeedback.query.one()
        self.assertEqual(saved.worked_well,'Friendly team')
        self.assertEqual(saved.improvements_noticed,'Better timing')
        self.assertEqual(saved.improvements_needed,'Clearer instructions')
        self.assertEqual(saved.organisation_comment,'')
        self.assertEqual(saved.session_year,self.record.session_date.year)
        self.assertEqual(saved.session_name,self.record.exam_session_name)
        self.assertIsNotNone(saved.submitted_at)
        self.assertEqual(self.post(language='es',overall_score='10').status_code,409)
        self.assertEqual(m.ExamCentreFeedback.query.count(),1)
        self.assertEqual(saved.overall_score,8)

    def test_security_revocation_and_exam_date(self):
        self.assertEqual(self.post(csrf_token='bad').status_code,400)
        with patch('app.exam_centre_feedback.feedback_available',return_value=False):
            self.assertEqual(self.client.post(self.url,data=self.answers()).status_code,403)
        outside=m.ExamSession(exam_session_name='Outside',category='Path School',status='Pending',session_date=self.record.session_date,format='Onsite')
        db.session.add(outside);db.session.flush()
        self.assertEqual(self.client.post(self.page+f'/feedback/{outside.id}',data=self.answers()).status_code,404)
        self.share.audience='public';db.session.commit()
        self.assertEqual(self.post().status_code,404)
        self.share.audience='institution';self.share.is_enabled=False;db.session.commit()
        self.assertEqual(self.post().status_code,410)
        self.assertEqual(m.ExamCentreFeedback.query.count(),0)

    def test_bilingual_modal_and_spanish_validation(self):
        for language,title in [('en','Exam centre feedback'),('es','Evaluación del centro de examen')]:
            response=self.client.get(self.page+'?lang='+language)
            self.assertEqual(response.status_code,200)
            html=response.get_data(as_text=True)
            self.assertIn(title,html)
            self.assertEqual(html.count('type="radio"'),40)
            self.assertNotIn(' checked',html)
            self.assertIn('data-feedback-conditional hidden',html)
            self.assertIn('name="improvements_needed"',html)
            self.assertNotIn('name="improvements_needed" required',html)
        response=self.post(language='es',overall_score='')
        self.assertIn('Seleccione una calificación',response.json['fields']['overall_score'])
        response=self.post(language='es',overall_score='5')
        self.assertIn('Explique',response.json['fields']['overall_comment'])
        self.assertEqual(self.post(language='es').status_code,200)
        self.assertEqual(m.ExamCentreFeedback.query.one().language,'es')
        html=self.client.get(self.page+'?lang=es').get_data(as_text=True)
        self.assertIn('Evaluación enviada',html)
        self.assertNotIn('data-centre-feedback-form',html)

    def test_concatenated_sessions_are_independent_and_date_specific(self):
        second=m.ExamSession(exam_session_name='Second',category='Path School',status='Pending',session_date=date(2026,12,14),format='Onsite',shifts='Morning',modules='Speaking')
        db.session.add(second);db.session.flush()
        self.record.concat_session_ids=json.dumps([second.id]);second.concat_session_ids=json.dumps([self.record.id]);db.session.commit()
        second_url=self.page+f'/feedback/{second.id}'
        self.assertEqual(self.post().status_code,200)
        self.assertFalse(staff_report_feedback_submitted(second))
        with patch('app.exam_centre_feedback.feedback_available',return_value=False):
            self.assertEqual(self.client.post(second_url,data=self.answers()).status_code,403)
        with patch('app.exam_centre_feedback.feedback_available',return_value=True):
            self.assertEqual(self.client.post(second_url,data=self.answers(overall_score='10')).status_code,200)
        self.assertEqual(m.ExamCentreFeedback.query.count(),2)
        self.assertTrue(staff_report_feedback_submitted(second))

    def test_feedback_enables_only_corresponding_supervisor_status(self):
        person=m.AcademicStaff(full_name='Supervisor',status='Active',roles='Supervisor')
        db.session.add(person);db.session.flush()
        assignment=m.ExamSessionSupervisorAssignment(exam_session_id=self.record.id,team_member_id=person.id,participation_status='Confirmed')
        share=m.StaffExamSessionsShare(person_ref=str(person.id),token='staff-feedback')
        db.session.add_all([assignment,share]);db.session.flush()
        submission=m.StaffExamSessionSubmission(exam_session_id=self.record.id,assignment_type='supervisor',assignment_id=assignment.id,share_id=share.id)
        db.session.add(submission);db.session.commit()
        status_url=f'/my-exam-sessions/{share.token}/submissions/{submission.id}/report/feedback-status'
        self.assertFalse(self.client.get(status_url).json['submitted'])
        self.assertEqual(self.post().status_code,200)
        self.assertTrue(staff_report_feedback_submitted(self.record))
        response=self.client.get(status_url)
        self.assertTrue(response.json['submitted'])
        self.assertEqual(response.headers['Cache-Control'],'private, no-store')
        self.assertEqual(self.client.get(status_url.replace(share.token,'wrong')).status_code,404)
