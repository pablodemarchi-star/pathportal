import json
import re
import unittest
from datetime import datetime, timezone
from unittest.mock import patch
from sqlalchemy import text
from app import db
from app.models import FinanceCompletionNotification, PaymentRequestEvent
from app.schema_migrations import migrate_finance_completion_events
from tests import test_finance_requests as fixtures


class FinanceCompletionMigrationTest(unittest.TestCase):
    setUp=fixtures.FinanceRequestsTest.setUp
    tearDown=fixtures.FinanceRequestsTest.tearDown
    create_user=fixtures.FinanceRequestsTest.create_user
    client_for=fixtures.FinanceRequestsTest.client_for
    payment=fixtures.FinanceRequestsTest.payment

    def legacy_schema(self):
        user=self.create_user('migration@example.com',is_superadmin=True)
        payment=self.payment(user,status='Payment completed')
        event=PaymentRequestEvent(payment_request_id=payment.id,event_type='Payment completed',new_status='Payment completed',created_on=datetime(2026,11,1,11,59,tzinfo=timezone.utc))
        db.session.add(event);db.session.commit()
        schema=db.session.execute(text("SELECT sql FROM sqlite_master WHERE name='finance_completion_notification'")).scalar()
        legacy=re.sub(r'\s*event_id INTEGER NOT NULL,','',schema).replace('UNIQUE (request_kind, event_id)','UNIQUE (request_kind, request_id)')
        db.session.execute(text('DROP TABLE finance_completion_notification'))
        db.session.execute(text(legacy))
        payload=json.dumps({'requester':'Migration','amount':'ARS 100','name':'Payee','concept':'Accounting',
            'en':{'message':'Original English','error':''},'sp':{'message':'Original Spanish','error':''}})
        statement=text('''INSERT INTO finance_completion_notification
            (id,request_kind,request_id,request_number,requester_user_id,recipient,payload,status,gmail_message_id,created_at)
            VALUES (:id,'payment',:request_id,:number,:user_id,'migration@example.com',:payload,:status,:gmail,'2026-11-01 12:00:00')''')
        db.session.execute(statement,[{'id':1,'request_id':payment.id,'number':payment.request_number,'user_id':user.id,'payload':payload,'status':'sent','gmail':'original-gmail-id'},
            {'id':2,'request_id':9999,'number':'PAY-2026-9999','user_id':user.id,'payload':payload,'status':'failed','gmail':None}])
        db.session.commit()
        return user,payment,event.id

    def test_legacy_notifications_and_delivery_statuses_survive_upgrade(self):
        user,payment,event_id=self.legacy_schema()
        with patch('app.google_mail.send_notification_email') as send:
            migrate_finance_completion_events()
        send.assert_not_called()
        notices=FinanceCompletionNotification.query.order_by(FinanceCompletionNotification.id).all()
        self.assertEqual(len(notices),2)
        self.assertEqual(notices[0].event_id,event_id)
        self.assertEqual(notices[0].status,'sent')
        self.assertEqual(notices[0].gmail_message_id,'original-gmail-id')
        self.assertEqual(notices[1].event_id,-2)
        self.assertEqual(notices[1].status,'failed')
        self.assertEqual(json.loads(notices[0].payload)['en']['message'],'Original English')
        self.assertEqual(json.loads(notices[0].payload)['status'],'Completed')
        db.session.add(FinanceCompletionNotification(request_kind='payment',request_id=payment.id,event_id=event_id+100,
            request_number=payment.request_number,requester_user_id=user.id,recipient=user.email,payload=notices[0].payload))
        db.session.commit()
        migrate_finance_completion_events()
        self.assertEqual(FinanceCompletionNotification.query.count(),3)
        response=self.client_for(user).get('/integrations/google')
        self.assertEqual(response.status_code,200)
        self.assertIn('Google Drive file storage',response.get_data(as_text=True))

    def test_failed_migration_rolls_back_without_losing_legacy_records(self):
        self.legacy_schema()
        execute=db.session.execute
        def failure(statement,*args,**kwargs):
            if str(statement)=='DROP TABLE finance_completion_notification':
                raise RuntimeError('Simulated failure before swapping tables')
            return execute(statement,*args,**kwargs)
        with patch.object(db.session,'execute',side_effect=failure),self.assertRaises(RuntimeError):
            migrate_finance_completion_events()
        columns={row[1] for row in db.session.execute(text('PRAGMA table_info(finance_completion_notification)'))}
        self.assertNotIn('event_id',columns)
        self.assertEqual(db.session.execute(text('SELECT count(*) FROM finance_completion_notification')).scalar(),2)
        self.assertFalse(db.session.execute(text("SELECT 1 FROM sqlite_master WHERE name='finance_completion_notification_migration'")).scalar())
