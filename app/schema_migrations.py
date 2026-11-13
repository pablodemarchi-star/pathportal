"""Data-preserving upgrades for older SQLite application databases."""
import json
import re
from sqlalchemy import text
from sqlalchemy.schema import CreateTable, CreateIndex
from app import db


def migrate_final_checks_workflow():
    from sqlalchemy import inspect
    columns = {column['name'] for column in inspect(db.engine).get_columns('exam_session_sinapsis_control')}
    definitions = {'return_started_on': 'DATE', 'return_recipient_ref': 'VARCHAR(80)',
                   'return_recipient_confirmed_on': 'DATE',
                   'return_review_required': 'BOOLEAN NOT NULL DEFAULT FALSE',
                   'return_reviewed_at': 'TIMESTAMP', 'return_completed_at': 'TIMESTAMP',
                   'return_shipping_label_id': 'VARCHAR(160) REFERENCES return_shipping_label(file_id)',
                   'combined_return_shipping_label_id': 'VARCHAR(160) REFERENCES return_shipping_label(file_id)',
                   'return_instructions_title': "VARCHAR(200) NOT NULL DEFAULT ''",
                   'return_instructions_html': "TEXT NOT NULL DEFAULT ''"}
    for field, definition in definitions.items():
        if field not in columns:
            db.session.execute(text(f'ALTER TABLE exam_session_sinapsis_control ADD COLUMN {field} {definition}'))
    if 'return_shipping_label_id' not in columns:
        db.session.execute(text("UPDATE exam_session_sinapsis_control SET return_materials_label_url = NULL, combined_return_materials_label_url = NULL, return_completed_at = CASE WHEN return_materials_method IN ('immediate_dispatch', 'combined_dispatch') THEN NULL ELSE return_completed_at END WHERE return_materials_label_url IS NOT NULL OR combined_return_materials_label_url IS NOT NULL"))
    if 'return_recipient_confirmed_on' not in columns:
        from datetime import date, timedelta
        db.session.execute(text('UPDATE exam_session_sinapsis_control SET return_recipient_confirmed_on = return_started_on'))
        records = db.session.execute(text('SELECT c.id, c.return_started_on, s.session_date FROM exam_session_sinapsis_control c JOIN exam_session s ON s.id = c.exam_session_id WHERE c.return_started_on IS NOT NULL')).all()
        for record in records:
            started = date.fromisoformat(str(record.return_started_on)[:10])
            exam_date = date.fromisoformat(str(record.session_date)[:10])
            if started < exam_date - timedelta(days=29):
                db.session.execute(text('UPDATE exam_session_sinapsis_control SET return_started_on = NULL WHERE id = :id'), {'id': record.id})
    db.session.commit()


def migrate_finance_completion_events():
    from app.models import FinanceCompletionNotification
    if db.engine.dialect.name != 'sqlite':
        return
    name = FinanceCompletionNotification.__tablename__
    columns = {row[1] for row in db.session.execute(text(f'PRAGMA table_info({name})'))}
    legacy_unique = False
    for index in db.session.execute(text(f'PRAGMA index_list({name})')).all():
        if index[2]:
            quoted = index[1].replace('"', '""')
            fields = [row[2] for row in db.session.execute(text(f'PRAGMA index_info("{quoted}")'))]
            if fields == ['request_kind', 'request_id']:
                legacy_unique = True
    if not columns or ('event_id' in columns and not legacy_unique):
        return
    connection = db.session.connection()
    if not connection.connection.driver_connection.in_transaction:
        connection.exec_driver_sql('BEGIN IMMEDIATE')
    try:
        rows = [dict(row) for row in db.session.execute(text(f'SELECT * FROM {name}')).mappings()]
        triggers = db.session.execute(text(
            "SELECT sql FROM sqlite_master WHERE type='trigger' AND tbl_name=:name AND sql IS NOT NULL"
        ), {'name': name}).scalars().all()
        used = set()
        for row in rows:
            event_id = row.get('event_id')
            if event_id is None:
                payment = row['request_kind'] == 'payment'
                table = 'payment_request' if payment else 'billing_request'
                event_table = table + '_event'
                complete = 'Payment completed' if payment else 'Invoice issued'
                event_id = db.session.execute(text(f'''
                    SELECT event.id FROM {event_table} AS event
                    JOIN {table} AS request ON request.id=event.{table}_id
                    WHERE request.id=:request_id AND request.request_number=:number
                    AND event.new_status=:complete AND event.created_on <= :notice_created
                    ORDER BY event.id LIMIT 1
                '''), {'request_id': row['request_id'], 'number': row['request_number'], 'complete': complete, 'notice_created': row['created_at']}).scalar()
            if event_id is None or (row['request_kind'], event_id) in used:
                # Deleted requests may have no surviving status event. Negative IDs
                # preserve those historical notices without colliding with new events.
                event_id = -row['id']
                while (row['request_kind'], event_id) in used:
                    event_id -= len(rows) + 1
            row['event_id'] = event_id
            used.add((row['request_kind'], event_id))
            try:
                payload = json.loads(row['payload'])
                if isinstance(payload, dict):
                    payload.setdefault('status', 'Completed')
                    payload.setdefault('reason', '')
                    row['payload'] = json.dumps(payload)
            except (ValueError, TypeError):
                pass
        temporary = name + '_migration'
        ddl = str(CreateTable(FinanceCompletionNotification.__table__).compile(dialect=db.engine.dialect))
        ddl = re.sub(r'CREATE TABLE\s+' + re.escape(name) + r'\b', 'CREATE TABLE ' + temporary, ddl, count=1)
        db.session.execute(text(ddl))
        if rows:
            fields = [column.name for column in FinanceCompletionNotification.__table__.columns]
            quoted = ', '.join('"' + field + '"' for field in fields)
            parameters = ', '.join(':' + field for field in fields)
            db.session.execute(text(f'INSERT INTO {temporary} ({quoted}) VALUES ({parameters})'), rows)
        db.session.execute(text(f'DROP TABLE {name}'))
        db.session.execute(text(f'ALTER TABLE {temporary} RENAME TO {name}'))
        for index in FinanceCompletionNotification.__table__.indexes:
            db.session.execute(CreateIndex(index))
        for trigger in triggers:
            db.session.execute(text(trigger))
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise


def migrate_staff_id_expiry():
    """Existing cards without an expiry date remain valid."""
    if db.engine.dialect.name != 'sqlite':
        return
    columns = {row[1] for row in db.session.execute(text("PRAGMA table_info(staff_id_document)"))}
    if columns and "expiry_date" not in columns:
        db.session.execute(text("ALTER TABLE staff_id_document ADD COLUMN expiry_date DATE"))
        db.session.commit()


def migrate_payee_notification_preferences():
    if db.engine.dialect.name != 'sqlite':
        return
    for table in ('payment_request', 'finance_contact', 'billing_request', 'finance_client_contact'):
        columns = {row[1] for row in db.session.execute(text(f'PRAGMA table_info({table})'))}
        if columns and 'automatic_payment_notification' not in columns:
            db.session.execute(text(f'ALTER TABLE {table} ADD COLUMN automatic_payment_notification BOOLEAN NOT NULL DEFAULT 0'))
        if columns and 'payment_notification_email' not in columns:
            db.session.execute(text(f'ALTER TABLE {table} ADD COLUMN payment_notification_email VARCHAR(254)'))
        if columns and 'payment_notification_language' not in columns:
            db.session.execute(text(f"ALTER TABLE {table} ADD COLUMN payment_notification_language VARCHAR(2) NOT NULL DEFAULT 'en'"))
    db.session.commit()


def migrate_process_timing():
    """Additive only. Existing clocks/timing history remain available for rollback."""
    from sqlalchemy import inspect
    columns = {column['name'] for column in inspect(db.engine).get_columns('exam_session_incident')}
    if 'affected_block' not in columns:
        db.session.execute(text("ALTER TABLE exam_session_incident ADD COLUMN affected_block VARCHAR(30) NOT NULL DEFAULT 'general'"))
    db.session.execute(text("CREATE INDEX IF NOT EXISTS ix_exam_session_incident_affected_block ON exam_session_incident (affected_block)"))
    clock_columns = {column['name'] for column in inspect(db.engine).get_columns('process_clock')}
    if 'has_begun' not in clock_columns:
        db.session.execute(text('ALTER TABLE process_clock ADD COLUMN has_begun BOOLEAN NOT NULL DEFAULT FALSE'))
        db.session.execute(text("UPDATE process_clock SET has_begun = TRUE, coverage_complete = FALSE WHERE category NOT IN ('Blocked','N/A') OR started_at IS NOT NULL"))
    db.session.commit()


def migrate_staff_session_report_attendance():
    from sqlalchemy import inspect
    columns = {column['name'] for column in inspect(db.engine).get_columns('staff_exam_session_report')}
    for field in ('absent_candidates_checked', 'submitted_candidates_checked', 'session_completed_checked', 'centre_feedback_confirmed', 'recordings_reminder_confirmed'):
        if field not in columns:
            db.session.execute(text(f'ALTER TABLE staff_exam_session_report ADD COLUMN {field} BOOLEAN NOT NULL DEFAULT FALSE'))
    for field, definition in {'facilities_outcome': "VARCHAR(40) NOT NULL DEFAULT ''", 'facilities_comments': "TEXT NOT NULL DEFAULT ''", 'emergency_pack_outcome': "VARCHAR(40) NOT NULL DEFAULT ''", 'emergency_pack_reasons': "TEXT NOT NULL DEFAULT ''", 'return_verification': "TEXT NOT NULL DEFAULT '[]'", 'staff_assessments': "TEXT NOT NULL DEFAULT '[]'", 'marketing_confirmed': 'BOOLEAN NOT NULL DEFAULT FALSE', 'marketing_media': "TEXT NOT NULL DEFAULT '[]'", 'optional_comments': "TEXT NOT NULL DEFAULT ''"}.items():
        if field not in columns:
            db.session.execute(text(f'ALTER TABLE staff_exam_session_report ADD COLUMN {field} {definition}'))
    db.session.commit()


def migrate_session_scoped_staff_reports():
    """Keep historical duplicates; only the earliest report owns the unique session key."""
    from sqlalchemy import inspect
    columns = {column['name'] for column in inspect(db.engine).get_columns('staff_exam_session_report')}
    for field, definition in {'author_name': "VARCHAR(300) NOT NULL DEFAULT ''", 'author_person_ref': "VARCHAR(80) NOT NULL DEFAULT ''"}.items():
        if field not in columns:
            db.session.execute(text(f'ALTER TABLE staff_exam_session_report ADD COLUMN {field} {definition}'))
    if 'exam_session_id' not in columns:
        db.session.execute(text('ALTER TABLE staff_exam_session_report ADD COLUMN exam_session_id INTEGER REFERENCES exam_session(id)'))
        db.session.execute(text('''UPDATE staff_exam_session_report SET exam_session_id = (
            SELECT exam_session_id FROM staff_exam_session_submission WHERE id = staff_exam_session_report.submission_id
        ) WHERE id IN (SELECT MIN(r.id) FROM staff_exam_session_report r
            JOIN staff_exam_session_submission s ON s.id = r.submission_id GROUP BY s.exam_session_id)'''))
    db.session.execute(text('CREATE UNIQUE INDEX IF NOT EXISTS uq_staff_report_session ON staff_exam_session_report (exam_session_id) WHERE exam_session_id IS NOT NULL'))
    db.session.commit()
