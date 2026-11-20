"""Post attendance and institutional evidence: no external Drive calls."""
import io
import json
import os
import unittest
from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch
from werkzeug.datastructures import MultiDict
os.environ['DATABASE_URL']='sqlite:///:memory:'
from app import create_app, db
from app import models as m
from app import post_attendance as attendance
from app.routes import journey_absence_upload_window


class PostAttendanceTest(unittest.TestCase):
    def setUp(self):
        self.app=create_app();self.app.config['TESTING']=True
        self.context=self.app.app_context();self.context.push();db.drop_all();db.create_all()
        self.today=date(2026,11,18)
        self.clock=patch('app.post_attendance.local_today',return_value=self.today);self.clock.start()
        from app.routes import journey_absence_upload_window
        self.window_clock=patch('app.routes.journey_absence_upload_window',side_effect=lambda record,now=None:journey_absence_upload_window(record,now=now or datetime(2026,11,18,12,tzinfo=timezone.utc)))
        self.window_clock.start()
        self.record=self.new_session('Main session',date(2026,11,17))
        self.record.absence_documentation_folder_url='https://drive.google.com/drive/folders/absence-folder-123456'
        self.record.contact_points=json.dumps([{'full_name':'Contact A','phone':'123','email':'a@example.com'}])
        self.share=m.ExamSessionJourneyShare(exam_session_id=self.record.id,audience='institution',token='absence-test')
        db.session.add(self.share);db.session.commit()
        self.client=self.app.test_client()
        with self.client.session_transaction() as session:session.update(user='admin',user_department='Admin',csrf_token='test')
        self.url=f'/pre-session-control-tower/post/sessions/{self.record.id}/attendance'
        self.public=f'/path-session-journey/{self.share.token}/institution/absences/{self.record.id}'
        attendance.control(self.record,True).submission_status='completed'
        db.session.commit()
        self.sequence=0;self.uploads=[]
        self.upload_patch=patch('app.attendance_drive.upload',side_effect=self.fake_upload);self.upload_patch.start()
        self.trash_patch=patch('app.attendance_drive.trash');self.trash=self.trash_patch.start()

    def tearDown(self):
        self.upload_patch.stop();self.trash_patch.stop();self.window_clock.stop();self.clock.stop()
        db.session.remove();db.drop_all();self.context.pop()

    def new_session(self,name,day,format='Onsite'):
        record=m.ExamSession(exam_session_name=name,category='Path School',status='Pending',session_date=day,
            shifts='Morning',modules='Speaking,Listening and speaking,Reading and writing',format=format)
        db.session.add(record);db.session.flush();return record

    def fake_upload(self,file,folder,name):
        self.sequence+=1;self.uploads.append((folder,name,file.filename))
        doc=m.AttendanceDocument(file_id=f'attendance-file-{self.sequence}',folder_id=folder,filename=name+'.pdf',mime_type='application/pdf')
        db.session.add(doc);return doc

    def open_window(self):
        def opened(record,now=None):
            window=journey_absence_upload_window(record,datetime.combine(record.session_date,datetime.min.time()).replace(tzinfo=__import__('app.routes',fromlist=['LOCAL_TZ']).LOCAL_TZ))
            window['state']='open';return window
        return patch('app.routes.journey_absence_upload_window',side_effect=opened)

    def closed_window(self):
        def closed(record,now=None):
            window=journey_absence_upload_window(record,datetime.fromisoformat('2027-01-01T12:00:00+00:00'))
            window['state']='expired';return window
        return patch('app.routes.journey_absence_upload_window',side_effect=closed)

    def prepare_review(self,names=()):
        # Field-validation tests start after the real verification/Sent prerequisites.
        main=attendance.main_institution(self.record,True)
        institutions=[main]
        for name in names:
            if not name.strip():continue
            item=next((item for item in m.AttendanceInstitution.query.filter_by(exam_session_id=self.record.id).all() if attendance.institution_key(item.name)==attendance.institution_key(name)),None)
            if item is None:
                item=m.AttendanceInstitution(exam_session_id=self.record.id,name=name.strip(),is_main=False)
                db.session.add(item);db.session.flush()
            institutions.append(item)
        for item in institutions:
            for module in attendance.modules(self.record):
                entry=m.AttendanceModule.query.filter_by(institution_id=item.id,module=module).first()
                if entry is None:
                    entry=m.AttendanceModule(institution_id=item.id,module=module);db.session.add(entry)
                if not entry.document_id:
                    doc=m.AttendanceDocument(file_id=f'fixture-{item.id}-{module}',folder_id=attendance.drive.LISTS_FOLDER,filename='Absence list.pdf',mime_type='application/pdf')
                    db.session.add(doc);entry.document=doc
        attendance.control(self.record,True).verified=True
        for item in m.AttendanceInstitution.query.filter_by(exam_session_id=self.record.id).all():
            keys=[contact['key'] for contact in attendance.contacts(self.record)] if item.is_main else ['external']
            item.notifications=json.dumps({key:True for key in keys})
        db.session.commit()

    def post(self,action,**data):
        if action=='candidate':self.prepare_review(names=[data.get('value','')] if data.get('field')=='institution_name' else [])
        if action=='candidate' and data.get('field')=='review':
            with self.closed_window():return self.client.post(self.url,data=dict(csrf_token='test',action=action,**data))
        return self.client.post(self.url,data=dict(csrf_token='test',action=action,**data))

    def upload(self,**data):
        values=dict(institution_id='main',module='Speaking',previous_file_id='',document=(io.BytesIO(b'pdf'),'absents.pdf'))
        values.update(data);return self.post('module_upload',**values)

    def submit(self,**data):
        values=dict(csrf_token='test',candidate_number='123',candidate_name='Candidate Example',language='en',rescheduled_for='next_july_online',document=(io.BytesIO(b'pdf'),'original.pdf'))
        values.update(data)
        with self.open_window():
            return self.client.post(self.public,data=values)

    def test_post_listing_date_format_separate_concatenated_rows_and_csrf(self):
        same=self.new_session('Today session',self.today)
        self.new_session('Future hidden',date(2026,11,19));self.new_session('Online hidden',date(2026,11,17),'Online')
        self.new_session('Centre hidden',date(2026,11,17),'Online at exam centre')
        self.record.concat_session_ids=json.dumps([same.id]);db.session.commit()
        with self.client.session_transaction() as session:session.pop('csrf_token')
        response=self.client.get('/pre-session-control-tower?view=post&session_year=2026')
        self.assertEqual(response.status_code,200);html=response.get_data(as_text=True)
        self.assertEqual(html.count('data-post-row '),2)
        self.assertNotIn('Future hidden',html);self.assertNotIn('Online hidden',html)
        self.assertIn('Concatenated:',html);self.assertIn('logistics-gate-blocked',html)
        self.assertIn('contextual-cell-trigger pa-attendance-trigger',html)
        self.assertIn('badge logistics-control-status-not-started',html)
        with self.client.session_transaction() as session:self.assertTrue(session['csrf_token'])
        self.assertEqual(m.PostAttendance.query.count(),1)

    def test_read_defaults_and_blocked_day_write_guard(self):
        result=self.client.get(self.url).json['state']
        self.assertEqual(result['progress'],'Not started');self.assertEqual(result['institutions'][0]['id'],'main')
        self.assertTrue(all(doc is None for doc in result['institutions'][0]['modules'].values()))
        self.assertEqual(m.AttendanceInstitution.query.count(),0)
        self.record.session_date=self.today;db.session.commit()
        self.assertFalse(self.client.get(self.url).json['state']['enabled'])
        self.assertEqual(self.post('verified',value='1').status_code,403)
        self.record.session_date=date(2026,11,19);db.session.commit()
        self.assertEqual(self.client.get(self.url).status_code,404)

    def test_permission_and_csrf(self):
        self.assertEqual(self.client.post(self.url,data={'action':'verified','value':'1'}).status_code,400)
        with patch('app.routes.user_can_edit',return_value=False):
            self.assertFalse(self.client.get(self.url).json['state']['can_edit'])
            self.assertEqual(self.post('verified',value='1').status_code,403)
        with patch('app.routes.user_can_view',return_value=False):
            self.assertEqual(self.client.get(self.url).status_code,403)
            self.assertEqual(self.client.get('/pre-session-control-tower?view=post').status_code,403)

    def test_module_upload_notification_reset_and_filename(self):
        response=self.upload();self.assertEqual(response.status_code,200,response.json)
        state=response.json['state'];self.assertTrue(state['has_absences']);self.assertEqual(state['progress'],'In progress')
        self.assertEqual(self.uploads[0][:2],(attendance.drive.LISTS_FOLDER,'Main session - 17/11/2026 - Speaking'))
        main=state['institutions'][0];key=state['contacts'][0]['key']
        self.post('verified',value='1')
        self.assertEqual(self.post('sent',institution_id=main['id'],key=key,value='1').status_code,200)
        old=main['modules']['Speaking']['id']
        self.assertEqual(self.upload(institution_id=main['id'],previous_file_id=old).status_code,400)
        self.assertEqual(self.upload(institution_id=main['id'],previous_file_id='stale',confirmed='1').status_code,400)
        response=self.upload(institution_id=main['id'],previous_file_id=old,confirmed='1')
        self.assertEqual(response.status_code,200,response.json);state=response.json['state']
        self.assertFalse(state['verified']);self.assertEqual(state['institutions'][0]['sent'],{})
        self.trash.assert_called_with(old)
        self.assertIsNone(db.session.get(m.AttendanceDocument,old))
        doc=state['institutions'][0]['modules']['Speaking']
        response=self.post('module_clear',institution_id=main['id'],module='Speaking',previous_file_id=doc['id'],confirmed='1')
        self.assertEqual(response.status_code,200,response.json);self.assertFalse(response.json['state']['has_absences'])

    def test_configured_module_and_single_file_only(self):
        self.record.modules='Speaking';db.session.commit()
        self.assertEqual(self.upload(module='Reading and writing').status_code,400)
        self.assertEqual(self.post('module_upload',institution_id='main',module='Speaking').status_code,400)
        response=self.client.post(self.url,data=MultiDict([('csrf_token','test'),('action','module_upload'),('institution_id','main'),('module','Speaking'),('document',(io.BytesIO(b'a'),'a.pdf')),('document',(io.BytesIO(b'b'),'b.pdf'))]))
        self.assertEqual(response.status_code,400);self.assertEqual(len(self.uploads),0)
        self.assertEqual(m.PostAttendance.query.count(),1)

    def test_drive_failure_keeps_previous_file_and_verified(self):
        state=self.upload().json['state'];main=state['institutions'][0];old=main['modules']['Speaking']['id']
        self.post('verified',value='1')
        self.trash.side_effect=attendance.drive.DriveStorageError('Drive unavailable')
        response=self.post('module_clear',institution_id=main['id'],module='Speaking',previous_file_id=old,confirmed='1')
        self.assertEqual(response.status_code,400)
        state=self.client.get(self.url).json['state']
        self.assertTrue(state['verified']);self.assertEqual(state['institutions'][0]['modules']['Speaking']['id'],old)

    def test_external_deletion_cascade_and_main_protection(self):
        response=self.post('add_institution',name='External school');self.assertEqual(response.status_code,200)
        external=response.json['state']['institutions'][1]
        state=self.upload(institution_id=external['id']).json['state']
        self.assertIn('External school - Speaking',self.uploads[-1][1])
        endpoint=self.url.replace('/attendance','/candidates')
        self.prepare_review()
        with self.closed_window():response=self.client.post(endpoint,data={'csrf_token':'test','institution_id':external['id'],'institution_name':'External school','exam':'Ready','modules':['Speaking'],'rescheduled_for':'next_july_online','approval':'Confirmed','currency':'ARS','credit_balance':'100','candidate_number':'ext','candidate_name':'External Candidate','document':(io.BytesIO(b'pdf'),'x.pdf')})
        self.assertEqual(response.status_code,200,response.json)
        candidate=m.AbsenceCandidate.query.one();candidate.notes='test';candidate.rescheduled_for='next_novdec_online';db.session.commit()
        self.assertEqual(self.post('delete_institution',institution_id=external['id']).status_code,400)
        response=self.post('delete_institution',institution_id=external['id'],confirmed='1')
        self.assertEqual(response.status_code,200,response.json)
        self.assertEqual(len(response.json['state']['institutions']),1)
        self.assertEqual(m.AbsenceCandidate.query.count(),0);self.assertEqual(m.AbsenceSubmissionEvent.query.count(),0)
        self.assertEqual(m.AttendanceDocument.query.count(),m.AttendanceModule.query.filter(m.AttendanceModule.document_id.isnot(None)).count());self.assertEqual(self.trash.call_count,2)
        self.assertEqual(self.post('delete_institution',institution_id='main',confirmed='1').status_code,400)

    def test_public_upload_duplicate_replace_event_and_internal_auto_row(self):
        self.assertEqual(self.submit().status_code,200)
        self.assertEqual(self.uploads[-1][:2],('absence-folder-123456','123 - Candidate Example - Absence documentation'))
        candidate=m.AbsenceCandidate.query.one();old=candidate.document_id
        self.assertFalse(candidate.approved);self.assertEqual(candidate.review_status,'Pending');self.assertEqual(candidate.exam,'');self.assertEqual(candidate.absent_modules,'[]')
        self.assertEqual(m.PostAttendance.query.one().revision,1)
        self.assertFalse(self.client.get(self.url).json['state']['candidates'][0]['actionable'])
        response=self.submit();self.assertEqual(response.status_code,409);self.assertTrue(response.json['duplicate'])
        self.assertEqual(len(self.uploads),1)
        response=self.submit(replace='1',confirmed='1',previous_file_id=old,candidate_name='Corrected Name')
        self.assertEqual(response.status_code,200,response.json)
        self.assertEqual(m.AbsenceCandidate.query.count(),1);self.assertEqual(m.AbsenceSubmissionEvent.query.count(),2)
        self.assertEqual([event['current'] for event in response.json['entries']],[False,True])
        self.trash.assert_called_once_with(old)
        self.assertEqual(self.submit(replace='1',confirmed='1',previous_file_id=old).status_code,409)
        self.assertEqual(len(self.uploads),2)

    def test_public_validation_window_scope_and_language(self):
        for changes in [{'candidate_number':''},{'candidate_name':''},{'document':(io.BytesIO(b''),'')}]:
            self.assertEqual(self.submit(**changes).status_code,400)
        self.assertEqual(self.submit(csrf_token='wrong',language='es').status_code,400)
        with self.closed_window():
            response=self.client.post(self.public,data={'csrf_token':'test','language':'es'})
            self.assertEqual(response.status_code,403);self.assertIn('cerrado',response.json['error'])
        other=self.new_session('Not shared',date(2026,11,17));db.session.commit()
        self.assertEqual(self.client.get(self.public.rsplit('/',1)[0]+'/'+str(other.id)).status_code,404)
        self.share.is_enabled=False;db.session.commit();self.assertEqual(self.client.get(self.public).status_code,410)
        self.assertEqual(m.AbsenceCandidate.query.count(),0)

    def test_bilingual_journey_and_shared_concat_scope(self):
        other=self.new_session('Concatenated session',date(2026,11,18));self.record.concat_session_ids=json.dumps([other.id]);db.session.commit()
        self.assertEqual(self.client.get(self.public.rsplit('/',1)[0]+'/'+str(other.id)).status_code,200)
        for lang,label in [('en','Candidate number'),('es','Número de candidato')]:
            response=self.client.get(f'/path-session-journey/{self.share.token}/institution?lang={lang}')
            self.assertEqual(response.status_code,200)
            html=response.get_data(as_text=True);self.assertEqual(html.count('data-absence-request data-url='),2)
            self.assertIn(label,html);self.assertIn('data-absence-file',html)
        self.submit()
        response=self.client.get(f'/path-session-journey/{self.share.token}/institution?lang=en')
        self.assertIn('See absence documentation',response.get_data(as_text=True))

    def test_candidate_review_actions_currency_and_source_year_default(self):
        last=self.new_session('Last 2026',date(2026,12,23),'Online')
        self.new_session('2027 future',date(2027,2,1));db.session.commit()
        self.submit(rescheduled_for=str(last.id));candidate=m.AbsenceCandidate.query.one()
        self.assertEqual(candidate.rescheduled_for,str(last.id))
        def edit(field,value='',**extra):return self.post('candidate',candidate_id=candidate.id,field=field,value=value,**extra)
        self.assertEqual(edit('exam','Level IV').status_code,400)
        self.assertEqual(edit('institution_name','School').status_code,200)
        self.assertEqual(edit('exam','Ready').status_code,200)
        response=edit('modules',modules=['Speaking']);self.assertFalse(response.json['state']['candidates'][0]['actionable'])
        response=edit('review','Confirmed',previous_file_id=candidate.document_id)
        self.assertEqual(response.status_code,200);self.assertTrue(response.json['state']['candidates'][0]['actionable'])
        self.assertEqual(self.reopen_candidate().status_code,200)
        self.assertEqual(edit('modules',modules=['Wrong']).status_code,400)
        self.assertEqual(edit('rescheduled_for',str(self.record.id)).status_code,400)
        self.assertEqual(edit('rescheduled_for','next_novdec_onsite').status_code,200)
        for currency in attendance.CURRENCIES:self.assertEqual(edit('currency',currency).status_code,200)
        self.assertEqual(edit('currency','XXX').status_code,400)
        self.assertEqual(edit('credit_balance','120,25').status_code,200)
        self.assertEqual(str(m.AbsenceCandidate.query.one().credit_balance),'120.25')
        self.assertEqual(edit('credit_balance','-1').status_code,400)
        self.assertEqual(edit('notes','Review detail').status_code,200)
        self.assertEqual(edit('review','Declined',previous_file_id=candidate.document_id,reason='Unacceptable documentation').status_code,200)
        self.assertFalse(self.client.get(self.url).json['state']['candidates'][0]['actionable'])
        with patch('app.post_attendance.local_today',return_value=date(2027,1,1)):
            options,default=attendance.reschedule_options(self.record)
            self.assertEqual(default,'next_july_online')
            self.assertIn('2027 future',options[0]['label'])

    def test_document_routes_scope_and_internal_review_after_expiry(self):
        self.submit();candidate=m.AbsenceCandidate.query.one()
        with patch('app.google_drive.stream_document',return_value='pdf'):
            self.assertEqual(self.client.get(self.public+f'/{candidate.id}/document').status_code,200)
            self.assertEqual(self.client.get(self.url.replace('/attendance',f'/files/{candidate.document_id}')).status_code,200)
            self.assertEqual(self.client.get(self.public+'/999/document').status_code,404)
        with self.closed_window():
            self.assertEqual(self.post('candidate',candidate_id=candidate.id,field='notes',value='Still reviewing').status_code,200)

    def test_partial_external_delete_failure_restores_files_and_keeps_all_rows(self):
        response=self.post('add_institution',name='External');external=response.json['state']['institutions'][1]
        self.upload(institution_id=external['id']);self.upload(institution_id=external['id'],module='Reading and writing')
        self.trash.side_effect=[None,attendance.drive.DriveStorageError('Drive unavailable'),None]
        response=self.post('delete_institution',institution_id=external['id'],confirmed='1')
        self.assertEqual(response.status_code,400)
        self.assertEqual(m.AttendanceInstitution.query.count(),2)
        self.assertEqual(m.AttendanceModule.query.count(),2)
        self.assertEqual(m.AttendanceDocument.query.count(),2)
        self.assertEqual(self.trash.call_args_list[-1].args,('attendance-file-1',False))

    def test_delete_session_removes_owned_attendance_rows(self):
        from app.routes import delete_exam_session_dependencies
        self.upload();self.submit()
        self.assertEqual(m.AttendanceDocument.query.count(),2)
        delete_exam_session_dependencies(self.record.id);db.session.commit()
        for model in [m.PostAttendance,m.AttendanceInstitution,m.AttendanceModule,m.AbsenceCandidate,m.AbsenceSubmissionEvent,m.AttendanceDocument]:
            self.assertEqual(model.query.count(),0,model.__name__)

    def test_institution_requires_rescheduling_choice_and_persists_it(self):
        from app.absence_submissions import institutional_reschedule_options
        older=self.new_session('Earlier future',date(2026,12,1),'Onsite')
        latest=self.new_session('Last online',date(2026,12,20),'Online')
        self.new_session('Next year',date(2027,12,20),'Onsite');db.session.commit()
        options=institutional_reschedule_options(self.record)
        self.assertEqual(len(options),4);self.assertEqual(options[0]['value'],str(latest.id))
        self.assertEqual(options[1]['label'],'July, next year | Online | Digital certificate only')
        self.assertEqual(self.submit(rescheduled_for='').status_code,400)
        self.assertEqual(self.submit(rescheduled_for=str(older.id)).status_code,400)
        self.assertEqual(self.submit(rescheduled_for=str(latest.id)).status_code,200)
        self.assertEqual(m.AbsenceCandidate.query.one().rescheduled_for,str(latest.id))
        for language,title in [('en','Select rescheduled exam date'),('es','Selecciona la fecha del examen reprogramado')]:
            html=self.client.get(f'/path-session-journey/{self.share.token}/institution?lang={language}').get_data(as_text=True)
            self.assertIn(title,html);self.assertIn('name="rescheduled_for" required',html)
            self.assertLess(html.index('name="rescheduled_for"'),html.index('name="document"'))
            self.assertIn('(Last online · 20/12/2026)',html)
            self.assertIn('absence-approval-notice',html)

    def review_candidate(self,field,value='',**extra):
        candidate=m.AbsenceCandidate.query.one()
        return self.post('candidate',candidate_id=candidate.id,field=field,value=value,**extra)

    def reopen_candidate(self):
        candidate=m.AbsenceCandidate.query.one()
        with self.closed_window():
            return self.review_candidate('reopen',confirmed='1',previous_file_id=candidate.document_id,previous_status=candidate.review_status)

    def test_documentation_is_blocked_without_recorded_absences(self):
        self.record.session_date=self.today;db.session.commit();self.submit()
        state=self.client.get(self.url).json['state']
        self.assertFalse(state['enabled']);self.assertFalse(state['documentation_enabled']);self.assertFalse(state['has_absences'])
        self.assertEqual(len(state['candidates']),1)
        candidate=m.AbsenceCandidate.query.one()
        response=self.client.post(self.url,data={'csrf_token':'test','action':'candidate','candidate_id':candidate.id,'field':'institution_name','value':'School'})
        self.assertEqual(response.status_code,403)
        self.assertEqual(self.post('verified',value='1').status_code,403)
        self.assertFalse(self.client.get(self.url).json['state']['documentation_enabled'])

    def test_all_exam_module_rules_and_confirmation_requirements(self):
        self.submit();candidate=m.AbsenceCandidate.query.one()
        def confirm():return self.review_candidate('review','Confirmed',previous_file_id=candidate.document_id)
        self.assertEqual(confirm().status_code,400)
        self.assertEqual(self.review_candidate('modules',modules=['Speaking']).status_code,400)
        self.review_candidate('institution_name','School')
        self.review_candidate('currency','ARS');self.review_candidate('credit_balance','100')
        for exam in attendance.EXAMS:
            self.assertEqual(self.review_candidate('exam',exam).status_code,200)
            allowed=['Speaking'] if exam in attendance.SPEAKING_EXAMS else ['Listening and speaking','Reading and writing']
            forbidden='Reading and writing' if exam in attendance.SPEAKING_EXAMS else 'Speaking'
            self.assertEqual(self.review_candidate('modules',modules=[forbidden]).status_code,400)
            response=self.review_candidate('modules',modules=allowed)
            self.assertEqual(response.status_code,200)
            self.assertEqual(response.json['state']['candidates'][0]['allowed_modules'],allowed)
            self.assertEqual(confirm().status_code,200)
            self.assertEqual(self.reopen_candidate().status_code,200)
        response=self.review_candidate('exam','Ready')
        row=response.json['state']['candidates'][0]
        self.assertEqual(row['review_status'],'Pending');self.assertEqual(row['modules'],[])
        self.assertEqual(confirm().status_code,400)
        self.review_candidate('modules',modules=['Speaking']);self.assertEqual(confirm().status_code,200)
        self.assertEqual(self.reopen_candidate().status_code,200)
        self.review_candidate('institution_name','')
        self.assertEqual(confirm().status_code,400)
        self.assertEqual(self.review_candidate('approved','1').status_code,400)

    def test_decline_reason_public_status_and_replacement_restarts_review(self):
        self.submit();candidate=m.AbsenceCandidate.query.one();old=candidate.document_id
        self.assertEqual(self.review_candidate('review','Declined',previous_file_id=old,reason=' ').status_code,400)
        self.assertEqual(self.review_candidate('review','Declined',previous_file_id='stale',reason='Reason').status_code,400)
        reason='Document is not legible. <script>unsafe</script>'
        self.assertEqual(self.review_candidate('review','Declined',previous_file_id=old,reason=reason).status_code,200)
        data=self.client.get(self.public).json['entries'][0]
        self.assertEqual(data['review_status'],'Declined');self.assertEqual(data['decline_reason'],reason)
        html=self.client.get(f'/path-session-journey/{self.share.token}/institution?lang=es').get_data(as_text=True)
        self.assertIn('Rechazado',html);self.assertIn('data-absence-review-reason=',html)
        self.assertIn('&lt;script&gt;unsafe&lt;/script&gt;',html)
        self.assertNotIn('<script>unsafe</script>',html)
        response=self.submit(replace='1',confirmed='1',previous_file_id=old)
        self.assertEqual(response.status_code,200)
        candidate=m.AbsenceCandidate.query.one()
        self.assertEqual(candidate.review_status,'Pending');self.assertEqual(candidate.decline_reason,'');self.assertFalse(candidate.approved)
        self.assertEqual(self.review_candidate('review','Confirmed',previous_file_id=old).status_code,400)

    def test_legacy_review_migration_is_once_only_and_preserves_new_reviews(self):
        from sqlalchemy import text
        from app.schema_migrations import migrate_absence_reviews
        db.session.execute(text('DROP TABLE absence_candidate'))
        db.session.execute(text("CREATE TABLE absence_candidate (id INTEGER PRIMARY KEY, approved BOOLEAN, exam TEXT, absent_modules TEXT, rescheduled_for TEXT)"))
        db.session.execute(text("INSERT INTO absence_candidate VALUES (1,1,'Level I','[\"Speaking\"]','next_july_online')"));db.session.commit()
        migrate_absence_reviews()
        row=db.session.execute(text('SELECT approved,review_status,exam,absent_modules,requested_rescheduled_for FROM absence_candidate')).one()
        self.assertEqual(tuple(row),(0,'Pending','','[]','next_july_online'))
        db.session.execute(text("UPDATE absence_candidate SET approved=1,review_status='Confirmed'"));db.session.commit()
        migrate_absence_reviews()
        self.assertEqual(db.session.execute(text('SELECT review_status FROM absence_candidate')).scalar(),'Confirmed')

    def internal_document(self,**changes):
        values={'csrf_token':'test','candidate_number':'internal-1','candidate_name':'Internal Candidate','institution_name':'School',
            'exam':'A1 Access','modules':['Listening and speaking','Reading and writing'],'rescheduled_for':'next_novdec_onsite',
            'approval':'Confirmed','currency':'ARS','credit_balance':'100.50','document':(io.BytesIO(b'pdf'),'internal.pdf')}
        values.update(changes)
        self.prepare_review(names=[values['institution_name']])
        with self.closed_window():return self.client.post(self.url.replace('/attendance','/candidates'),data=values)

    def test_internal_form_requires_all_fields_and_respects_module_rules(self):
        for field in ['candidate_number','candidate_name','institution_name','exam','modules','rescheduled_for','approval']:
            response=self.internal_document(**{field:[] if field=='modules' else ''})
            self.assertEqual(response.status_code,400,(field,response.json))
        self.assertEqual(self.internal_document(exam='Ready',modules=['Reading and writing']).status_code,400)
        self.assertEqual(self.internal_document(exam='A1 Access',modules=['Speaking']).status_code,400)
        self.assertEqual(self.internal_document(approval='Invalid').status_code,400)
        self.assertEqual(self.internal_document(document=(io.BytesIO(b''),'')).status_code,400)
        self.assertEqual(m.AbsenceCandidate.query.count(),0);self.assertEqual(len(self.uploads),0)

    def test_internal_upload_after_deadline_saves_complete_confirmed_row(self):
        with self.closed_window():
            response=self.internal_document()
        self.assertEqual(response.status_code,200,response.json)
        row=response.json['state']['candidates'][0]
        self.assertEqual(row['number'],'internal-1');self.assertEqual(row['name'],'Internal Candidate')
        self.assertEqual(row['institution_name'],'School');self.assertEqual(row['exam'],'A1 Access')
        self.assertEqual(row['modules'],['Listening and speaking','Reading and writing'])
        self.assertEqual(row['review_status'],'Confirmed');self.assertTrue(row['actionable'])
        self.assertEqual(row['rescheduled_label'],'Nov/Dec, next year | Onsite')
        self.assertEqual(self.uploads[-1][0],'absence-folder-123456')
        self.assertTrue(row['document']['url'])

    def test_internal_pending_upload_after_deadline_can_be_reviewed_later(self):
        response=self.internal_document(approval='Pending',currency='',credit_balance='')
        self.assertEqual(response.status_code,200,response.json)
        row=response.json['state']['candidates'][0]
        self.assertEqual(row['review_status'],'Pending')
        self.assertFalse(row['approved'])
        self.assertEqual(row['whatsapp_message'],'')
        self.assertEqual(row['whatsapp_message_es'],'')
        self.assertFalse(response.json['state']['results_notification_enabled'])
        self.assertEqual(self.review_candidate('review','Confirmed',previous_file_id=row['document']['id']).status_code,400)
        response=self.review_candidate('review','Declined',previous_file_id=row['document']['id'],reason='Documentation does not meet requirements')
        self.assertEqual(response.status_code,200,response.json)
        self.assertEqual(response.json['state']['candidates'][0]['review_status'],'Declined')

    def test_final_review_is_readonly_and_requires_confirmed_reopening(self):
        response=self.internal_document()
        self.assertEqual(response.status_code,200,response.json)
        candidate=m.AbsenceCandidate.query.one()
        original=(candidate.document_id,candidate.name,candidate.number,candidate.exam,candidate.absent_modules,candidate.currency,candidate.credit_balance)
        with self.closed_window():
            for field,value in [('number','changed'),('name','Changed'),('institution_name','Other'),('institution_id','main'),('exam','Ready'),('modules',''),('rescheduled_for','next_july_online'),('currency','USD'),('credit_balance','2'),('review','Declined')]:
                result=self.raw_action('candidate',candidate_id=candidate.id,field=field,value=value)
                self.assertEqual(result.status_code,400,(field,result.json))
            result=self.raw_action('candidate',candidate_id=candidate.id,field='notes',value='Keep this note')
            self.assertEqual(result.status_code,200,result.json)
            self.assertTrue(result.json['state']['candidates'][0]['document']['url'])
            record_control=attendance.control(self.record,True)
            record_control.review_results_notified=True;db.session.commit()
            fields=dict(candidate_id=candidate.id,field='reopen',previous_file_id=candidate.document_id,previous_status='Confirmed')
            self.assertEqual(self.raw_action('candidate',**fields).status_code,400)
            self.assertEqual(self.raw_action('candidate',**{**fields,'previous_status':'Declined','confirmed':'1'}).status_code,400)
            result=self.raw_action('candidate',**fields,confirmed='1')
            self.assertEqual(result.status_code,200,result.json)
            candidate=m.AbsenceCandidate.query.one()
            self.assertEqual(candidate.review_status,'Pending')
            self.assertEqual((candidate.document_id,candidate.name,candidate.number,candidate.exam,candidate.absent_modules,candidate.currency,candidate.credit_balance),original)
            self.assertEqual(candidate.notes,'Keep this note')
            self.assertFalse(attendance.control(self.record).review_results_notified)
            self.assertEqual(result.json['state']['candidates'][0]['whatsapp_message'],'')
            self.assertEqual(self.raw_action('candidate',candidate_id=candidate.id,field='name',value='Updated name').status_code,200)
            result=self.raw_action('candidate',candidate_id=candidate.id,field='review',value='Declined',previous_file_id=candidate.document_id,reason='Old reason')
            self.assertEqual(result.status_code,200,result.json)
            self.assertEqual(self.raw_action('candidate',candidate_id=candidate.id,field='exam',value='Ready').status_code,400)
            fields.update(previous_status='Declined')
            self.assertEqual(self.raw_action('candidate',**fields,confirmed='1').status_code,200)
            self.assertEqual(m.AbsenceCandidate.query.one().decline_reason,'')
            self.assertEqual(m.AbsenceCandidate.query.one().notes,'Keep this note')

    def test_internal_decline_reason_and_duplicate_replacement(self):
        self.assertEqual(self.internal_document(approval='Declined').status_code,400)
        response=self.internal_document(approval='Declined',reason='Certificate cannot be accepted')
        self.assertEqual(response.status_code,200,response.json)
        candidate=m.AbsenceCandidate.query.one();old=candidate.document_id
        self.assertEqual(candidate.decline_reason,'Certificate cannot be accepted');self.assertFalse(candidate.approved)
        self.assertEqual(self.internal_document().status_code,409);self.assertEqual(len(self.uploads),1)
        response=self.internal_document(replace='1',confirmed='1',previous_file_id=old,exam='Ready',modules=['Speaking'],approval='Confirmed')
        self.assertEqual(response.status_code,200,response.json)
        self.assertEqual(m.AbsenceCandidate.query.count(),1);self.assertEqual(len(self.uploads),2)
        candidate=m.AbsenceCandidate.query.one();self.assertTrue(candidate.approved);self.assertEqual(candidate.decline_reason,'')
        self.trash.assert_called_once_with(old)

    def test_credit_required_to_confirm_but_not_decline(self):
        self.submit();candidate=m.AbsenceCandidate.query.one()
        self.review_candidate('institution_name','School');self.review_candidate('exam','Ready');self.review_candidate('modules',modules=['Speaking'])
        def confirm():return self.review_candidate('review','Confirmed',previous_file_id=candidate.document_id)
        self.assertEqual(confirm().status_code,400)
        self.review_candidate('currency','USD');self.assertEqual(confirm().status_code,400)
        self.review_candidate('currency','');self.review_candidate('credit_balance','125.25');self.assertEqual(confirm().status_code,400)
        self.review_candidate('currency','UYU');self.assertEqual(confirm().status_code,200)
        self.assertEqual(self.reopen_candidate().status_code,200)
        self.assertEqual(self.review_candidate('credit_balance','-1').status_code,400)
        self.assertEqual(self.review_candidate('credit_balance','').status_code,200)
        self.assertEqual(m.AbsenceCandidate.query.one().review_status,'Pending')
        self.assertEqual(self.review_candidate('review','Declined',previous_file_id=candidate.document_id,reason='Invalid document').status_code,200)

    def test_credit_exempt_for_last_session_of_source_year_all_formats(self):
        latest=self.new_session('Last online exam',date(2026,12,23),'Online')
        self.new_session('Later in next year',date(2027,12,23),'Onsite');db.session.commit()
        response=self.internal_document(rescheduled_for=str(latest.id),currency='',credit_balance='')
        self.assertEqual(response.status_code,200,response.json)
        row=response.json['state']['candidates'][0]
        self.assertFalse(row['credit_applicable']);self.assertEqual(row['credit_balance'],'');self.assertEqual(row['currency'],'')
        self.assertIn(str(latest.id),response.json['state']['credit_exempt_options'])
        candidate=m.AbsenceCandidate.query.one()
        self.assertEqual(self.reopen_candidate().status_code,200)
        response=self.review_candidate('credit_balance','999')
        self.assertEqual(response.status_code,200);self.assertIsNone(m.AbsenceCandidate.query.one().credit_balance)
        self.assertEqual(self.review_candidate('review','Confirmed',previous_file_id=candidate.document_id).status_code,200)
        self.assertEqual(self.reopen_candidate().status_code,200)
        changed=self.review_candidate('rescheduled_for','next_july_online')
        self.assertEqual(changed.status_code,200);self.assertTrue(changed.json['state']['candidates'][0]['credit_applicable'])
        self.assertEqual(changed.json['state']['candidates'][0]['review_status'],'Pending')
        self.assertEqual(self.review_candidate('review','Confirmed',previous_file_id=candidate.document_id).status_code,400)
        self.review_candidate('rescheduled_for',str(latest.id))
        # This stays exempt after the selected date has passed.
        with patch('app.post_attendance.local_today',return_value=date(2027,1,1)):
            self.assertFalse(attendance.candidate_credit_applicable(candidate))

    def test_internal_credit_validation_and_zero_amount(self):
        self.assertEqual(self.internal_document(currency='',credit_balance='').status_code,400)
        self.assertEqual(self.internal_document(currency='EUR',credit_balance='').status_code,400)
        self.assertEqual(self.internal_document(currency='',credit_balance='50').status_code,400)
        self.assertEqual(self.internal_document(currency='XYZ',credit_balance='50').status_code,400)
        response=self.internal_document(currency='GBP',credit_balance='0')
        self.assertEqual(response.status_code,200,response.json)
        self.assertEqual(response.json['state']['candidates'][0]['credit_balance'],'0.00')

    def test_internal_decline_allows_empty_credit_balance(self):
        response=self.internal_document(approval='Declined',reason='Not valid',currency='',credit_balance='')
        self.assertEqual(response.status_code,200,response.json)
        self.assertFalse(response.json['state']['candidates'][0]['approved'])

    def test_confirmed_whatsapp_message_has_formatted_credit_and_exact_text(self):
        response=self.internal_document(currency='USD',credit_balance='1234.50')
        self.assertEqual(response.status_code,200,response.json)
        message=response.json['state']['candidates'][0]['whatsapp_message']
        expected="\n".join(['- *Status:* Confirmed','- *Candidate number:* internal-1','- *Candidate name:* Internal Candidate',
            '- *Rescheduled exam date:* Nov/Dec, next year | Onsite','- *Credit balance:* USD 1,234.50','',
            "We confirm that the supporting documentation submitted for this candidate's absence has been *reviewed and approved by Path Examinations*.",'',
            'The absence is now considered justified, and *the candidate has been rescheduled for the selected exam session*.','',
            '*Path International Examinations*'])
        self.assertEqual(message,expected)
        spanish=response.json['state']['candidates'][0]['whatsapp_message_es']
        self.assertIn('ha sido *revisada y aprobada por Path Examinations*',spanish)
        self.assertIn('- *Saldo a favor:* USD 1.234,50',spanish)
        self.assertIn('Nov/Dic, próximo año | Presencial',spanish)
        self.assertIn('*revisada y aprobada por Path Examinations*',spanish)

    def test_whatsapp_message_pending_declined_and_no_credit_when_exempt(self):
        self.submit();candidate=m.AbsenceCandidate.query.one()
        self.assertEqual(self.client.get(self.url).json['state']['candidates'][0]['whatsapp_message'],'')
        self.assertEqual(self.client.get(self.url).json['state']['candidates'][0]['whatsapp_message_es'],'')
        response=self.review_candidate('review','Declined',previous_file_id=candidate.document_id,reason='Private review reason')
        message=response.json['state']['candidates'][0]['whatsapp_message']
        self.assertIn('- *Status:* Declined',message)
        self.assertIn('*the request has not been approved*',message)
        self.assertIn("The candidate's absence will therefore remain recorded as Absent.",message)
        self.assertNotIn('Credit balance',message);self.assertNotIn('Rescheduled exam date',message);self.assertNotIn('Private review reason',message)
        spanish=response.json['state']['candidates'][0]['whatsapp_message_es']
        self.assertIn('- *Estado:* Rechazado',spanish)
        self.assertIn('*la solicitud no ha sido aprobada*',spanish)
        self.assertNotIn('Saldo a favor',spanish)
        self.assertNotIn('Private review reason',spanish)
        latest=self.new_session('Last session',date(2026,12,23),'Online');db.session.commit()
        response=self.internal_document(rescheduled_for=str(latest.id),currency='',credit_balance='')
        row=next(item for item in response.json['state']['candidates'] if item['number']=='internal-1')
        self.assertIn('Last session · 23/12/2026',row['whatsapp_message'])
        self.assertNotIn('Credit balance',row['whatsapp_message'])
        self.assertNotIn('Saldo a favor',row['whatsapp_message_es'])
        candidate=m.AbsenceCandidate.query.filter_by(number='internal-1').one()
        response=self.submit(candidate_number='internal-1',replace='1',confirmed='1',previous_file_id=candidate.document_id,rescheduled_for=str(latest.id))
        self.assertEqual(response.status_code,200)
        row=next(item for item in self.client.get(self.url).json['state']['candidates'] if item['number']=='internal-1')
        self.assertEqual(row['whatsapp_message'],'')

    def grouped_copy(self,ids,csrf='test',language='en'):
        with self.closed_window():return self.client.post(self.url.replace('/attendance','/absence-message'),data={'csrf_token':csrf,'language':language,'candidate_ids':[str(value) for value in ids]})

    def test_grouped_confirmed_message_preserves_individual_dates_and_credits(self):
        first=self.internal_document(candidate_number='G1',institution_name='  Same   School  ',currency='USD',credit_balance='125.50').json['state']['candidates'][0]
        last=self.new_session('Last onsite',date(2026,12,23),'Onsite');db.session.commit()
        response=self.internal_document(candidate_number='G2',institution_name='same school',rescheduled_for=str(last.id),currency='',credit_balance='')
        second=next(row for row in response.json['state']['candidates'] if row['number']=='G2')
        self.assertEqual(first['institution_key'],second['institution_key'])
        result=self.grouped_copy([first['id'],second['id']])
        self.assertEqual(result.status_code,200,result.json)
        message=result.json['message']
        self.assertIn('from the *Main session* examination session, held on *17 November 2026*',message)
        self.assertIn('*1. Candidate number:* G1',message);self.assertIn('*2. Candidate number:* G2',message)
        self.assertIn('Nov/Dec, next year | Onsite',message);self.assertIn('*Rescheduled exam session:* Last onsite',message);self.assertIn('*Rescheduled exam date:* 23 December 2026',message)
        self.assertEqual(message.count('*Credit balance:*'),1);self.assertIn('USD 125.50',message)
        self.assertIn('*Rescheduled exam date:* Date to be confirmed',message)
        self.assertIn('*Exam time:* To be confirmed next year',message)
        self.assertIn('both candidates have been successfully rescheduled for the examination sessions indicated for each candidate above',message)
        spanish=self.grouped_copy([first['id'],second['id']],language='es').json['message']
        self.assertIn('ha sido *revisada y aprobada por Path Examinations*',spanish)
        self.assertIn('*1. Número de candidato:* G1',spanish)
        self.assertIn('Nov/Dic, próximo año | Presencial',spanish)
        self.assertEqual(spanish.count('*Saldo a favor:*'),1)
        self.assertIn('USD 125,50',spanish)
        self.assertIn('*Fecha del examen reprogramado:* Fecha a confirmar',spanish)
        self.assertIn('*Horario del examen:* A confirmar el próximo año',spanish)
        self.assertEqual(self.grouped_copy([first['id']],language='invalid').status_code,400)
        selected=self.grouped_copy([second['id']]).json['message']
        self.assertNotIn('G1',selected);self.assertNotIn('Credit balance',selected)
        self.assertIn('the candidate has been successfully rescheduled for the examination session indicated above',selected)
        self.assertEqual(m.AbsenceCandidate.query.count(),2)

    def test_approved_group_message_four_business_day_deadline_and_dynamic_count(self):
        target=self.new_session('Rescheduled Exams and Late Entries 2026',date(2026,12,26),'Online')
        db.session.commit()
        ids=[]
        for number in ['112318','112376','112916','112334']:
            response=self.internal_document(candidate_number=number,rescheduled_for=str(target.id),currency='',credit_balance='')
            self.assertEqual(response.status_code,200,response.json)
            ids.append(next(row['id'] for row in response.json['state']['candidates'] if row['number']==number))
        message=self.grouped_copy(ids).json['message']
        self.assertTrue(message.startswith("Hello!\n\nWe hope you're well. 😊"))
        self.assertEqual(message.count('*Rescheduled exam session:* Rescheduled Exams and Late Entries 2026'),4)
        self.assertEqual(message.count('*Rescheduled exam date:* 26 December 2026'),4)
        self.assertEqual(message.count('*Exam time:* To be confirmed by 21 December 2026'),4)
        self.assertIn('all four candidates have been successfully rescheduled for the examination session indicated above',message)
        self.assertNotIn('Credit balance',message)
        self.assertTrue(message.endswith('Thanks,\nBrenda\n*Path International Examinations*'))
        spanish=self.grouped_copy(ids,language='es').json['message']
        self.assertEqual(spanish.count('*Horario del examen:* A confirmar a más tardar el 21 de diciembre de 2026'),4)
        self.assertEqual(spanish.count('*Fecha del examen reprogramado:* 26 de diciembre de 2026'),4)
        self.assertIn('los cuatro candidatos han sido reprogramados correctamente para la sesión de examen indicada anteriormente',spanish)
        subset=self.grouped_copy(ids[:2]).json['message']
        self.assertIn('both candidates',subset)
        self.assertNotIn('112916',subset)

    def test_grouped_declined_message_has_active_journey_link_and_whatsapp_format(self):
        ids=[]
        for number in ['D1','D2']:
            response=self.internal_document(candidate_number=number,institution_name='School',approval='Declined',reason='Private reason',currency='',credit_balance='')
            ids.append(next(row['id'] for row in response.json['state']['candidates'] if row['number']==number))
        response=self.grouped_copy(ids);self.assertEqual(response.status_code,200,response.json)
        message=response.json['message']
        paragraph='The reasons for the rejection can be viewed in the corresponding *_Exam session journey_*: http://localhost/path-session-journey/absence-test/institution'
        self.assertIn(paragraph,message);self.assertLess(message.index(paragraph),message.index('*Path International Examinations*'))
        self.assertTrue(message.startswith("Hello!\n\nWe hope you're well. 😊\n\n"))
        self.assertIn('If you have any questions, please let us know!',message)
        self.assertTrue(message.endswith('Thanks,\nBrenda\n*Path International Examinations*'))
        self.assertNotIn('Private reason',message);self.assertNotIn('Credit balance',message);self.assertNotIn('Rescheduled exam date',message)
        spanish=self.grouped_copy(ids,language='es').json['message']
        self.assertTrue(spanish.startswith('¡Hola!\n\nEsperamos que se encuentren bien. 😊\n\n'))
        self.assertIn('Si tienen alguna consulta, no duden en contactarnos.',spanish)
        self.assertTrue(spanish.endswith('Gracias,\nBrenda\n*Path International Examinations*'))
        self.assertIn('*las solicitudes no han sido aprobadas*',spanish)
        self.assertIn('Los motivos del rechazo',spanish)
        self.assertIn('*_Exam session journey_*: http://localhost/path-session-journey/absence-test/institution',spanish)
        self.assertNotIn('Saldo a favor',spanish)
        self.share.is_enabled=False;db.session.commit()
        self.assertEqual(self.grouped_copy(ids).status_code,400)
        self.assertFalse(m.ExamSessionJourneyShare.query.one().is_enabled)
        peer=self.new_session('Concatenated',self.today);self.record.concat_session_ids=json.dumps([peer.id])
        db.session.add(m.ExamSessionJourneyShare(exam_session_id=peer.id,audience='institution',token='concat-active'));db.session.commit()
        self.assertIn('/path-session-journey/concat-active/institution',self.grouped_copy(ids).json['message'])

    def test_grouped_message_guards_scope_status_institution_and_permissions(self):
        first=self.internal_document(candidate_number='M1',institution_name='School').json['state']['candidates'][0]['id']
        response=self.internal_document(candidate_number='M2',institution_name='Other School')
        second=next(row['id'] for row in response.json['state']['candidates'] if row['number']=='M2')
        self.assertEqual(self.grouped_copy([first,second]).status_code,400)
        other=db.session.get(m.AbsenceCandidate,second);other.institution_name='School';other.review_status='Declined';db.session.commit()
        self.assertEqual(self.grouped_copy([first,second]).status_code,400)
        other.review_status='Pending';db.session.commit()
        self.assertEqual(self.grouped_copy([second]).status_code,400)
        self.assertEqual(self.grouped_copy([]).status_code,400)
        self.assertEqual(self.grouped_copy([99999]).status_code,404)
        self.assertEqual(self.grouped_copy([first],csrf='bad').status_code,400)
        with patch('app.routes.user_can_view',return_value=False):self.assertEqual(self.grouped_copy([first]).status_code,403)
        source=self.new_session('Other source',date(2026,11,16));db.session.get(m.AbsenceCandidate,first).exam_session_id=source.id;db.session.commit()
        self.assertEqual(self.grouped_copy([first]).status_code,404)

    def test_review_notification_checkbox_requires_final_reviews_and_closed_window(self):
        db.session.commit()
        self.assertEqual(self.post('review_results_notified',value='1').status_code,400)
        self.internal_document()
        with self.closed_window():
            response=self.post('review_results_notified',value='1')
            self.assertEqual(response.status_code,200,response.json)
            self.assertTrue(response.json['state']['review_results_notified'])
            self.assertTrue(self.client.get(self.url).json['state']['review_results_notified'])
        self.assertEqual(self.post('review_results_notified',value='invalid').status_code,400)
        with patch('app.routes.user_can_edit',return_value=False):self.assertEqual(self.post('review_results_notified',value='0').status_code,403)
        self.assertEqual(self.client.post(self.url,data={'action':'review_results_notified','value':'0'}).status_code,400)
        response=self.post('review_results_notified',value='0');self.assertFalse(response.json['state']['review_results_notified'])
        other=self.new_session('Independent session',self.today);db.session.commit()
        other_url=self.url.replace(f'/sessions/{self.record.id}/',f'/sessions/{other.id}/')
        self.assertFalse(self.client.get(other_url).json['state']['review_results_notified'])

    def raw_action(self,action,**fields):
        return self.client.post(self.url,data={'csrf_token':'test','action':action,**fields})

    def real_notification_setup(self):
        response=self.upload();self.assertEqual(response.status_code,200,response.json)
        state=response.json['state'];main=next(card for card in state['institutions'] if card['main'])
        key=state['contacts'][0]['key']
        self.assertEqual(self.raw_action('verified',value='1').status_code,200)
        self.assertEqual(self.raw_action('sent',institution_id=main['id'],key=key,value='1').status_code,200)
        return main['id'],key

    def raw_internal(self,**changes):
        data={'csrf_token':'test','candidate_number':'manual','candidate_name':'Manual Candidate','institution_name':self.record.exam_session_name,
            'exam':'Ready','modules':['Speaking'],'rescheduled_for':'next_july_online','approval':'Pending',
            'document':(io.BytesIO(b'pdf'),'certificate.pdf')}
        data.update(changes)
        return self.client.post(self.url.replace('/attendance','/candidates'),data=data)

    def test_full_workflow_from_exam_day_until_closed_window(self):
        self.record.session_date=self.today;db.session.commit()
        self.assertFalse(self.client.get(self.url).json['state']['enabled'])
        self.assertEqual(self.upload().status_code,403)
        self.record.session_date=self.today-timedelta(days=1);db.session.commit()
        # On the next day only absence records are initially editable.
        state=self.client.get(self.url).json['state']
        self.assertTrue(state['enabled']);self.assertFalse(state['notifications_enabled']);self.assertFalse(state['documentation_enabled'])
        self.assertFalse(state['results_notification_enabled'])
        self.assertEqual(self.raw_internal().status_code,400)
        state=self.upload().json['state'];main=state['institutions'][0];key=state['contacts'][0]['key']
        self.assertEqual(self.raw_action('sent',institution_id=main['id'],key=key,value='1').status_code,400)
        state=self.raw_action('verified',value='1').json['state']
        self.assertTrue(state['notifications_enabled']);self.assertFalse(state['documentation_enabled'])
        state=self.raw_action('sent',institution_id=main['id'],key=key,value='1').json['state']
        self.assertTrue(state['documentation_enabled']);self.assertFalse(state['review_allowed'])
        response=self.raw_internal();self.assertEqual(response.status_code,200,response.json)
        candidate=m.AbsenceCandidate.query.one();self.assertEqual(candidate.review_status,'Pending')
        self.assertEqual(self.raw_internal(candidate_number='premature',approval='Confirmed',currency='ARS',credit_balance='10').status_code,400)
        for status in ['Confirmed','Declined']:
            response=self.raw_action('candidate',candidate_id=candidate.id,field='review',value=status,previous_file_id=candidate.document_id,reason='Reason')
            self.assertEqual(response.status_code,400)
        self.assertEqual(self.raw_action('candidate',candidate_id=candidate.id,field='notes',value='Preliminary review').status_code,200)
        self.assertEqual(self.raw_action('review_results_notified',value='1').status_code,400)
        self.submit(candidate_number='waiting-public')
        waiting=m.AbsenceCandidate.query.filter_by(number='waiting-public').one()
        with self.closed_window():
            self.assertTrue(self.client.get(self.url).json['state']['review_allowed'])
            self.assertEqual(self.raw_internal(candidate_number='closed-invalid',approval='Invalid').status_code,400)
            self.assertEqual(self.raw_action('candidate',candidate_id=candidate.id,field='currency',value='ARS').status_code,200)
            self.assertEqual(self.raw_action('candidate',candidate_id=candidate.id,field='credit_balance',value='100').status_code,200)
            response=self.raw_action('candidate',candidate_id=candidate.id,field='review',value='Confirmed',previous_file_id=candidate.document_id)
            self.assertEqual(response.status_code,200,response.json);self.assertFalse(response.json['state']['results_notification_enabled'])
            self.assertEqual(self.raw_action('review_results_notified',value='1').status_code,400)
            response=self.raw_action('candidate',candidate_id=waiting.id,field='review',value='Declined',previous_file_id=waiting.document_id,reason='Not accepted')
            self.assertEqual(response.status_code,200,response.json);self.assertTrue(response.json['state']['results_notification_enabled'])
            self.assertEqual(self.raw_action('review_results_notified',value='1').status_code,200)
            self.assertTrue(m.PostAttendance.query.one().review_results_notified)
            # A new internally reviewed certificate invalidates the final notification confirmation only.
            response=self.raw_internal(candidate_number='second',approval='Declined',reason='Reason')
            self.assertEqual(response.status_code,200,response.json)
            state=response.json['state'];self.assertTrue(state['verified']);self.assertTrue(state['documentation_enabled'])
            self.assertFalse(state['review_results_notified']);self.assertTrue(state['results_notification_enabled'])

    def test_gates_require_every_contact_and_external_sent_and_preserve_data(self):
        main,key=self.real_notification_setup()
        self.submit();candidate=m.AbsenceCandidate.query.one()
        self.assertTrue(self.client.get(self.url).json['state']['documentation_enabled'])
        state=self.raw_action('sent',institution_id=main,key=key,value='0').json['state']
        self.assertFalse(state['documentation_enabled'])
        self.assertEqual(self.raw_action('candidate',candidate_id=candidate.id,field='notes',value='Blocked edit').status_code,400)
        self.assertEqual(m.AbsenceCandidate.query.count(),1)
        self.raw_action('sent',institution_id=main,key=key,value='1')
        self.record.contact_points=json.dumps([{'full_name':'Contact A','phone':'123','email':'a@example.com'},{'full_name':'Contact B','phone':'456','email':'b@example.com'}]);db.session.commit()
        state=self.client.get(self.url).json['state'];self.assertFalse(state['documentation_enabled'])
        second=next(contact['key'] for contact in state['contacts'] if contact['key']!=key)
        self.raw_action('sent',institution_id=main,key=second,value='1')
        self.assertTrue(self.client.get(self.url).json['state']['documentation_enabled'])
        added=self.raw_action('add_institution',name='External').json['state'];external=next(card for card in added['institutions'] if not card['main'])
        self.upload(institution_id=external['id']);self.raw_action('verified',value='1')
        self.assertFalse(self.client.get(self.url).json['state']['documentation_enabled'])
        state=self.raw_action('sent',institution_id=external['id'],key='external',value='1').json['state']
        self.assertTrue(state['documentation_enabled'])
        self.raw_action('verified',value='0')
        state=self.client.get(self.url).json['state'];self.assertFalse(state['notifications_enabled']);self.assertFalse(state['documentation_enabled'])
        self.assertEqual(m.AbsenceCandidate.query.count(),1)
        self.assertEqual(self.raw_action('sent',institution_id=main,key=key,value='0').status_code,400)
        self.raw_action('verified',value='1');self.assertTrue(self.client.get(self.url).json['state']['documentation_enabled'])
        self.record.contact_points='[]';db.session.commit()
        self.assertFalse(self.client.get(self.url).json['state']['documentation_enabled'])

    def test_no_absences_or_no_certificates_never_enables_final_notification(self):
        self.raw_action('verified',value='1')
        with self.closed_window():
            state=self.client.get(self.url).json['state']
            self.assertFalse(state['notifications_enabled']);self.assertFalse(state['documentation_enabled']);self.assertFalse(state['results_notification_enabled'])
            self.assertEqual(self.raw_action('review_results_notified',value='1').status_code,400)
        self.real_notification_setup()
        with self.closed_window():
            state=self.client.get(self.url).json['state']
            self.assertTrue(state['documentation_enabled']);self.assertEqual(state['candidates'],[]);self.assertFalse(state['results_notification_enabled'])
            self.assertEqual(self.raw_action('review_results_notified',value='1').status_code,400)

    def test_public_uploads_preserve_first_steps_and_reset_final_notification(self):
        main,key=self.real_notification_setup()
        self.submit();candidate=m.AbsenceCandidate.query.one();original=candidate.document_id
        value=m.PostAttendance.query.one();value.review_results_notified=True;db.session.commit()
        response=self.submit(replace='1',confirmed='1',previous_file_id=original)
        self.assertEqual(response.status_code,200)
        value=m.PostAttendance.query.one();self.assertTrue(value.verified);self.assertFalse(value.review_results_notified)
        state=self.client.get(self.url).json['state'];self.assertTrue(state['documentation_enabled'])
        self.assertTrue(state['institutions'][0]['sent'][key]);self.assertEqual(m.AbsenceCandidate.query.one().review_status,'Pending')

    def test_no_absences_complete_only_after_verification(self):
        state=self.client.get(self.url).json['state']
        self.assertEqual(state['progress'],'Not started');self.assertEqual(state['steps']['records']['status'],'ready')
        self.assertEqual(state['steps']['notifications']['status'],'locked')
        self.assertEqual(state['steps']['documentation']['status'],'locked')
        state=self.raw_action('verified',value='1').json['state']
        self.assertEqual(state['progress'],'Completed');self.assertEqual(state['steps']['records']['status'],'completed')
        self.assertEqual(state['steps']['notifications']['status'],'not_applicable')
        self.assertEqual(state['steps']['documentation']['status'],'not_applicable')
        self.assertFalse(state['notifications_enabled']);self.assertFalse(state['documentation_enabled'])
        html=self.client.get('/pre-session-control-tower?view=post&session_year=2026').get_data(as_text=True)
        self.assertIn('logistics-control-status-completed',html)
        state=self.raw_action('verified',value='0').json['state'];self.assertEqual(state['progress'],'In progress')
        self.assertEqual(state['steps']['records']['status'],'in_progress')
        self.assertEqual(state['steps']['notifications']['status'],'locked')

    def test_absence_notifications_encode_both_languages_and_only_first_name(self):
        from urllib.parse import urlsplit,parse_qs
        self.record.exam_session_name='Colegio 💙 & + María'
        self.record.contact_points=json.dumps([{'full_name':'María José Gómez','phone':'+54 9 (11) 2850-8482','email':'maria@example.com'}])
        db.session.commit()
        self.upload(module='Speaking');self.upload(module='Listening and speaking')
        self.raw_action('verified',value='1')
        state=self.client.get(self.url).json['state'];card=state['institutions'][0]
        self.assertTrue(state['notifications_enabled'])
        self.assertEqual(card['sent'],{})
        actions=card['notification_contacts'][0]['actions']
        self.assertEqual(len(actions),2)
        for action in actions:
            self.assertEqual(action['disabled_reason'],'')
            parsed=urlsplit(action['url']);query=parse_qs(parsed.query)
            self.assertEqual(parsed.netloc,'api.whatsapp.com')
            self.assertEqual(query['phone'],['5491128508482'])
            self.assertEqual(query['text'],[action['message']])
            self.assertIn('%20',parsed.query);self.assertNotIn('+',parsed.query)
            for emoji in ['👋','📋','👉','⏳','💙']:self.assertIn(emoji,query['text'][0])
            self.assertNotIn('\ufffd',action['message'])
            self.assertEqual(action['message'].count('📋'),2)
            self.assertIn('*Speaking*',action['message']);self.assertIn('*Listening and Speaking*',action['message'])
            self.assertNotIn('*Reading and Writing*',action['message'])
            self.assertNotIn('José Gómez',action['message'])
            self.assertIn('María José Gómez',action['label'])
        self.assertTrue(actions[0]['message'].startswith('Hello, María! 👋'))
        self.assertIn('*17 November 2026*',actions[0]['message'])
        self.assertTrue(actions[1]['message'].startswith('¡Hola, María! 👋'))
        self.assertIn('*17 de noviembre de 2026*',actions[1]['message'])
        self.assertIn('lang=es',actions[1]['message'])
        self.assertEqual(attendance.control(self.record).review_results_notified,False)
        self.assertEqual(m.AttendanceInstitution.query.filter_by(is_main=True).one().notifications,'{}')

    def test_external_absence_messages_use_external_journey_and_public_scoped_lists(self):
        import re
        from flask import Response
        self.record.contact_points=json.dumps([{'full_name':'John Smith','phone':'+442071234567','email':'john@example.com'}]);db.session.commit()
        self.upload(module='Speaking')
        state=self.raw_action('add_institution',name='External school').json['state']
        external=next(card for card in state['institutions'] if not card['main'])
        self.upload(institution_id=external['id'],module='Reading and writing')
        self.raw_action('verified',value='1')
        state=self.client.get(self.url).json['state']
        ext=next(card for card in state['institutions'] if not card['main'])
        self.assertTrue(all(action['disabled_reason'] and not action['message'] for action in ext['notification_actions']))
        share=m.ExamSessionJourneyShare(exam_session_id=self.record.id,audience='external',token='external-absence-notice')
        db.session.add(share);db.session.commit()
        state=self.client.get(self.url).json['state']
        main=next(card for card in state['institutions'] if card['main']);ext=next(card for card in state['institutions'] if not card['main'])
        for action in ext['notification_actions']:
            self.assertEqual(action['disabled_reason'],'')
            self.assertEqual(action['url'],'')
            self.assertIn('/external-absence-notice/external?lang=',action['message'])
            self.assertIn('*Reading and Writing*',action['message'])
            self.assertNotIn('*Speaking*',action['message'])
        self.assertTrue(ext['notification_actions'][0]['message'].startswith('Hello! 👋'))
        self.assertTrue(ext['notification_actions'][1]['message'].startswith('¡Hola! 👋'))
        self.assertEqual(ext['notification_actions'][0]['label'],'Copy absence notification (English)')
        self.assertEqual(ext['notification_actions'][1]['label'],'Copy absence notification (Spanish)')
        main_url=re.search(r'https?://\S+/speaking',main['notification_contacts'][0]['actions'][0]['message']).group(0)
        ext_url=re.search(r'https?://\S+/reading-and-writing',ext['notification_actions'][0]['message']).group(0)
        anonymous=self.app.test_client()
        with patch('app.google_drive.stream_document',return_value=Response(b'list',mimetype='application/pdf')) as stream:
            self.assertEqual(anonymous.get(main_url).status_code,200)
            self.assertEqual(anonymous.get(ext_url).status_code,200)
            self.assertEqual(stream.call_count,2)
            self.assertEqual(anonymous.get(ext_url.replace(f'/{external["id"]}/reading-and-writing',f'/{main["id"]}/speaking')).status_code,404)
            self.assertEqual(anonymous.get(main_url.replace(f'/{main["id"]}/speaking',f'/{external["id"]}/reading-and-writing')).status_code,404)
        share.is_enabled=False;db.session.commit()
        self.assertEqual(anonymous.get(ext_url).status_code,410)
        self.record.contact_points=json.dumps([{'full_name':'John Smith','phone':'123','email':'john@example.com'}]);db.session.commit()
        main=next(card for card in self.client.get(self.url).json['state']['institutions'] if card['main'])
        self.assertIn('phone',main['notification_contacts'][0]['actions'][0]['disabled_reason'])
        self.share.is_enabled=False;db.session.commit()
        main=next(card for card in self.client.get(self.url).json['state']['institutions'] if card['main'])
        self.assertIn('journey',main['notification_contacts'][0]['actions'][0]['disabled_reason'])


    def test_exam_and_module_choices_follow_each_institution_absence_lists(self):
        self.record.modules='Listening and speaking, Reading and writing';db.session.commit()
        self.assertEqual(self.upload(module='Listening and speaking').status_code,200)
        self.submit()
        state=self.client.get(self.url).json['state'];main=state['institutions'][0]['id'];key=state['contacts'][0]['key']
        self.raw_action('verified',value='1');self.raw_action('sent',institution_id=main,key=key,value='1')
        candidate=m.AbsenceCandidate.query.one()
        def edit(field,value='',**extra):return self.raw_action('candidate',candidate_id=candidate.id,field=field,value=value,**extra)
        self.assertEqual(edit('exam','A1- Entry').status_code,400)
        state=edit('institution_name',self.record.exam_session_name).json['state']
        row=state['candidates'][0]
        self.assertNotIn('SPA level 1',row['allowed_exams'])
        self.assertEqual(edit('exam','Ready').status_code,400)
        result=edit('exam','A1- Entry')
        self.assertEqual(result.status_code,200,result.json)
        self.assertEqual(result.json['state']['candidates'][0]['allowed_modules'],['Listening and speaking'])
        self.assertEqual(edit('modules',modules=['Reading and writing']).status_code,400)
        self.assertEqual(edit('modules',modules=['Listening and speaking']).status_code,200)
        response=self.raw_action('add_institution',name='External school')
        external=next(item for item in response.json['state']['institutions'] if not item['main'])
        self.assertEqual(self.upload(institution_id=external['id'],module='Reading and writing').status_code,200)
        self.raw_action('verified',value='1');self.raw_action('sent',institution_id=main,key=key,value='1');self.raw_action('sent',institution_id=external['id'],key='external',value='1')
        result=edit('institution_name','  EXTERNAL   school ')
        self.assertEqual(result.status_code,200,result.json)
        row=result.json['state']['candidates'][0]
        self.assertEqual(row['institution_id'],external['id'])
        self.assertEqual(row['modules'],[])
        self.assertEqual(row['allowed_modules'],['Reading and writing'])
        self.assertEqual(edit('modules',modules=['Listening and speaking']).status_code,400)
        self.assertEqual(edit('modules',modules=['Reading and writing']).status_code,200)
        self.assertEqual(self.raw_internal(institution_name='Unknown',exam='A1 Access',modules=['Reading and writing']).status_code,400)
        self.assertEqual(self.raw_internal(institution_name='External school',exam='Ready',modules=['Speaking']).status_code,400)
        self.assertEqual(self.raw_internal(institution_name='External school',exam='A1 Access',modules=['Listening and speaking']).status_code,400)
        result=self.raw_internal(institution_name='External school',exam='A1 Access',modules=['Reading and writing'])
        self.assertEqual(result.status_code,200,result.json)
        self.assertEqual(m.AbsenceCandidate.query.filter_by(number='manual').one().institution_id,int(external['id']))

    def test_removing_absence_list_reopens_incompatible_review_without_losing_document(self):
        self.assertEqual(self.upload(module='Listening and speaking').status_code,200)
        self.assertEqual(self.upload(module='Reading and writing').status_code,200)
        state=self.client.get(self.url).json['state'];main=state['institutions'][0];key=state['contacts'][0]['key']
        self.raw_action('verified',value='1');self.raw_action('sent',institution_id=main['id'],key=key,value='1')
        with self.closed_window():
            result=self.raw_internal(institution_name=self.record.exam_session_name,exam='A1 Access',modules=['Listening and speaking','Reading and writing'],approval='Confirmed',currency='ARS',credit_balance='100')
        self.assertEqual(result.status_code,200,result.json)
        candidate=m.AbsenceCandidate.query.one();document=candidate.document_id
        attendance.control(self.record).review_results_notified=True;db.session.commit()
        result=self.raw_action('module_clear',institution_id=main['id'],module='Reading and writing',previous_file_id=main['modules']['Reading and writing']['id'],confirmed='1')
        self.assertEqual(result.status_code,200,result.json)
        candidate=m.AbsenceCandidate.query.one()
        self.assertEqual(candidate.review_status,'Pending')
        self.assertEqual(candidate.exam,'A1 Access')
        self.assertEqual(json.loads(candidate.absent_modules),['Listening and speaking'])
        self.assertEqual(candidate.document_id,document)
        self.assertFalse(attendance.control(self.record).review_results_notified)
        from app.routes import apply_exam_session_form
        fields=['exam_session_name','category','status','session_date','minimum_candidates_required','exam_session_organised_by',
                'full_address_google_maps','city','province','format','location_url','details_url','schedule_folder_url',
                'exam_entry_slips_url','session_pictures_folder_url','absence_documentation_folder_url','digitalised_exams_url']
        data={field:getattr(self.record,field) for field in fields}
        data.update(contact_points=self.record.contact_points_list(),shifts=['Morning'],modules=list(reversed(self.record.modules_list())))
        attendance.control(self.record).verified=True;db.session.commit()
        revision=attendance.control(self.record).revision
        apply_exam_session_form(self.record,data);db.session.commit()
        self.assertEqual(attendance.control(self.record).revision,revision)
        self.assertTrue(attendance.control(self.record).verified)
        data['modules']=['Speaking']
        apply_exam_session_form(self.record,data);db.session.commit()
        self.assertEqual(candidate.exam,'');self.assertEqual(candidate.absent_modules,'[]')
        self.assertEqual(candidate.document_id,document)
        self.assertFalse(attendance.control(self.record).verified)

    def test_three_steps_completion_counters_and_reopening(self):
        self.record.contact_points=json.dumps([{'full_name':'A','phone':'1','email':'a@example.com'},{'full_name':'B','phone':'2','email':'b@example.com'}]);db.session.commit()
        state=self.upload().json['state'];self.assertEqual(state['steps']['records']['status'],'in_progress')
        state=self.raw_action('verified',value='1').json['state']
        self.assertEqual(state['steps']['records']['status'],'completed');self.assertEqual(state['steps']['notifications']['status'],'ready')
        main=state['institutions'][0]['id'];a,b=[contact['key'] for contact in state['contacts']]
        state=self.raw_action('sent',institution_id=main,key=a,value='1').json['state']
        self.assertEqual(state['steps']['notifications']['status'],'in_progress');self.assertEqual(state['notifications_sent'],1);self.assertEqual(state['notifications_total'],2)
        state=self.raw_action('sent',institution_id=main,key=b,value='1').json['state']
        self.assertEqual(state['steps']['notifications']['status'],'completed');self.assertEqual(state['steps']['documentation']['status'],'ready')
        self.submit();candidate=m.AbsenceCandidate.query.one()
        state=self.client.get(self.url).json['state']
        self.assertEqual(state['steps']['documentation']['status'],'in_progress');self.assertEqual(state['reviews_completed'],0);self.assertEqual(state['reviews_total'],1)
        with self.closed_window():
            state=self.raw_action('candidate',candidate_id=candidate.id,field='review',value='Declined',previous_file_id=candidate.document_id,reason='Not accepted').json['state']
            self.assertEqual(state['reviews_completed'],1);self.assertEqual(state['steps']['documentation']['status'],'in_progress')
            self.assertEqual(state['progress'],'In progress')
            state=self.raw_action('review_results_notified',value='1').json['state']
            self.assertEqual(state['steps']['documentation']['status'],'completed');self.assertEqual(state['progress'],'Completed')
            html=self.client.get('/pre-session-control-tower?view=post&session_year=2026').get_data(as_text=True)
            self.assertIn('logistics-control-status-completed',html)
            state=self.raw_action('sent',institution_id=main,key=b,value='0').json['state']
            self.assertEqual(state['progress'],'In progress');self.assertEqual(state['steps']['documentation']['status'],'locked')
            self.assertEqual(m.AbsenceCandidate.query.one().review_status,'Declined')
            self.raw_action('sent',institution_id=main,key=b,value='1');self.raw_action('review_results_notified',value='1')
            state=self.raw_internal(candidate_number='new-review',approval='Declined',reason='Reason').json['state']
            self.assertEqual(state['progress'],'In progress');self.assertEqual(state['steps']['records']['status'],'completed')
            self.assertEqual(state['steps']['notifications']['status'],'completed');self.assertEqual(state['steps']['documentation']['status'],'in_progress')

    def test_certificate_reopens_completed_attendance_if_institution_has_no_absences(self):
        state=self.raw_action('verified',value='1').json['state'];self.assertEqual(state['progress'],'Completed')
        response=self.submit();self.assertEqual(response.status_code,200,response.json)
        state=self.client.get(self.url).json['state']
        self.assertFalse(state['verified']);self.assertEqual(state['progress'],'In progress')
        self.assertEqual(state['steps']['records']['status'],'in_progress')
        self.assertFalse(state['documentation_enabled']);self.assertEqual(len(state['candidates']),1)
        self.assertEqual(state['candidates'][0]['review_status'],'Pending')
        self.assertFalse(state['has_absences'])

    def test_new_certificate_checks_its_own_institution_and_preserves_other_sent_flags(self):
        added=self.raw_action('add_institution',name='External').json['state']
        external=next(card for card in added['institutions'] if not card['main'])
        self.upload(institution_id=external['id']);self.raw_action('verified',value='1')
        self.raw_action('sent',institution_id=external['id'],key='external',value='1')
        self.assertTrue(self.client.get(self.url).json['state']['documentation_enabled'])
        self.submit()  # The main institution is still marked No, despite external absences.
        state=self.client.get(self.url).json['state'];self.assertFalse(state['verified'])
        self.assertFalse(state['documentation_enabled'])
        external_state=next(card for card in state['institutions'] if not card['main'])
        self.assertTrue(external_state['sent']['external']);self.assertTrue(external_state['modules']['Speaking'])

    def test_replacement_reopens_verification_only_after_successful_upload(self):
        self.submit();candidate=m.AbsenceCandidate.query.one();old=candidate.document_id
        self.raw_action('verified',value='1')
        self.assertEqual(self.submit().status_code,409)
        self.assertTrue(m.PostAttendance.query.one().verified)
        with patch('app.attendance_drive.upload',side_effect=attendance.drive.DriveStorageError('Drive unavailable')):
            response=self.submit(replace='1',confirmed='1',previous_file_id=old)
        self.assertEqual(response.status_code,400);self.assertTrue(m.PostAttendance.query.one().verified)
        self.assertEqual(m.AbsenceCandidate.query.one().document_id,old)
        response=self.submit(replace='1',confirmed='1',previous_file_id=old)
        self.assertEqual(response.status_code,200);self.assertFalse(m.PostAttendance.query.one().verified)
        self.assertEqual(m.AbsenceCandidate.query.count(),1)

    def test_window_boundaries_use_existing_gmt_minus_three_deadline(self):
        self.record.session_date=date(2026,11,17)
        window=journey_absence_upload_window(self.record,datetime.fromisoformat('2026-11-17T03:00:00+00:00'))
        self.assertEqual(window['state'],'open')
        self.assertEqual(journey_absence_upload_window(self.record,datetime.fromisoformat('2026-11-17T02:59:59+00:00'))['state'],'pending')
        self.assertEqual(journey_absence_upload_window(self.record,datetime.fromisoformat(window['expires_at']))['state'],'expired')


if __name__=='__main__':unittest.main()
