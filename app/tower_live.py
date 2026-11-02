"""Fresh, private control-tower modal snapshots and optimistic edit protection."""
import hashlib
import hmac
import json

from flask import Blueprint, abort, current_app, g, has_request_context, jsonify, request, session
from sqlalchemy import event, func, literal, select, union_all
from sqlalchemy.orm import Session

from app import db, login_required
from app.models import ExamSession

live_bp = Blueprint('tower_live', __name__)
STALE_MESSAGE = 'This session was updated by another user.'


def session_revision(session_id):
    """One SQL snapshot, including related controls, deletions and bundle members.

    Read actual values rather than just the maximum timestamp: an older checklist
    edit or removal must also invalidate the snapshot. No snapshot data leaves here.
    """
    from app.routes import exam_session_concat_component_map
    tables = db.metadata.tables
    records = tables['exam_session']
    links = tables['exam_session_shipment_bundle_session']
    bundle_ids = select(links.c.bundle_id).where(links.c.exam_session_id == session_id)
    ids = set(exam_session_concat_component_map().get(session_id, {session_id}))
    ids.update(db.session.execute(select(links.c.exam_session_id).where(links.c.bundle_id.in_(bundle_ids))).scalars())
    conditions = {'exam_session': records.c.id.in_(ids)}
    bundles = tables['exam_session_shipment_bundle']
    conditions[bundles.name] = bundles.c.id.in_(bundle_ids)
    # Follow child FKs so notes, checklist rows, events, and deleted rows all count.
    pending = {name: table for name, table in tables.items()
               if name.startswith('exam_session_') and name not in conditions}
    while pending:
        added = []
        for name, table in pending.items():
            for foreign_key in sorted(table.foreign_keys, key=lambda key: (key.column.table.name != "exam_session", key.target_fullname, key.parent.name)):
                parent = foreign_key.column.table
                if parent.name in conditions:
                    conditions[name] = foreign_key.parent.in_(
                        select(foreign_key.column).where(conditions[parent.name]))
                    added.append(name)
                    break
        if not added:
            break
        for name in added:
            pending.pop(name)
    staff = tables['academic_staff']
    staff_sources = []
    for name in ('exam_session_supervisor_assignment', 'exam_session_examiner_assignment', 'exam_session_intern_assignment'):
        table = tables[name]
        staff_sources.append(select(table.c.team_member_id).where(table.c.exam_session_id.in_(ids)))
    staff_sources.append(select(records.c.emergency_contact_member_id).where(records.c.id.in_(ids)))
    staff_sources.append(select(bundles.c.supervisor_staff_id).where(conditions[bundles.name]))
    conditions[staff.name] = staff.c.id.in_(union_all(*staff_sources))
    postgres = db.engine.dialect.name == 'postgresql'
    json_array = func.json_build_array if postgres else func.json_array
    queries = [select(literal(name).label('source'), json_array(*tables[name].c).label('payload')).where(condition)
               for name, condition in sorted(conditions.items())]
    rows = db.session.execute(union_all(*queries)).all()
    payload = json.dumps(sorted((name, json.dumps(value, sort_keys=True, default=str) if postgres else value)
                                for name, value in rows), ensure_ascii=False).encode()
    key = current_app.config['SECRET_KEY']
    return hmac.new(key.encode() if isinstance(key, str) else key, payload, hashlib.sha256).hexdigest()


@live_bp.get('/pre-session-control-tower/sessions/<int:session_id>/revision')
@login_required
def revision(session_id):
    from app.routes import require_menu_view
    require_menu_view('pre_session_control_tower')
    if db.session.get(ExamSession, session_id) is None:
        abort(404)
    response = jsonify(revision=session_revision(session_id))
    response.headers['Cache-Control'] = 'no-store'
    return response


def guard_tower_edit():
    """Only modal-originated writes carry a snapshot; normal routes keep their guards."""
    if request.method != 'POST' or not session.get('user'):
        return None
    supplied = request.headers.get('X-Tower-Revision') or request.form.get('tower_revision')
    raw_id = request.headers.get('X-Tower-Session') or request.form.get('tower_revision_session_id')
    if not supplied and not raw_id:
        return None
    try:
        session_id = int(raw_id)
    except (ValueError, TypeError):
        abort(400)
    from app.routes import require_menu_view, menu_key_for_path
    menu = menu_key_for_path(request.path)
    if menu:
        require_menu_view(menu)
    if db.engine.dialect.name == 'postgresql':
        db.session.execute(select(ExamSession.id).where(ExamSession.id == session_id).with_for_update())
    if db.engine.dialect.name == 'sqlite':
        connection = db.session.connection()
        if not connection.connection.driver_connection.in_transaction:
            connection.exec_driver_sql('BEGIN IMMEDIATE')
    if not supplied or not hmac.compare_digest(supplied.encode(), session_revision(session_id).encode()):
        response = jsonify(ok=False, saved=False, error=STALE_MESSAGE, code='stale_session')
        response.status_code = 409
        response.headers['Cache-Control'] = 'no-store'
        return response
    g.tower_saved_session_id = session_id
    g.pop("tower_written_revision", None)
    return None


@event.listens_for(Session, 'before_commit')
def capture_written_tower_revision(unit_of_work):
    # Capture our revision while the write transaction still holds its locks.
    # Reading it after commit could accidentally acknowledge another writer's edit.
    if has_request_context() and unit_of_work is db.session() and getattr(g, 'tower_saved_session_id', None):
        unit_of_work.flush()
        g.tower_written_revision = session_revision(g.tower_saved_session_id)


def finish_tower_edit(response):
    session_id = getattr(g, 'tower_saved_session_id', None)
    if request.method == "POST" and session_id and 200 <= response.status_code < 400:
        response.headers['X-Tower-Revision'] = getattr(g, "tower_written_revision", None) or session_revision(session_id)
        response.headers['Cache-Control'] = 'no-store'
    return response
