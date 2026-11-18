"""Resolve saved session folders without changing any planner configuration."""
from flask import request, jsonify
from app.models import ExamSession
from app.staff_report_media import session_pictures_folder


def bulk_session_pictures(action, purpose='Session pictures'):
    from app.google_drive import folder_metadata, DriveStorageError
    raw=request.form.getlist('session_ids')
    if not raw or len(raw)>500 or any(not value.isdigit() for value in raw):
        return jsonify(ok=False,error='Select between 1 and 500 exam sessions.'),400
    ids=list(dict.fromkeys(int(value) for value in raw))
    records=ExamSession.query.filter(ExamSession.id.in_(ids)).order_by(ExamSession.session_date,ExamSession.id).all()
    if len(records)!=len(ids):
        return jsonify(ok=False,error='Some selected sessions no longer exist. Refresh the planner and try again.'),400
    folders,issues={},[]
    from types import SimpleNamespace
    field = 'absence_documentation_folder_url' if purpose == 'Absence documentation' else 'session_pictures_folder_url'
    for record in records:
        link = getattr(record, field)
        folder_id=session_pictures_folder(SimpleNamespace(session_pictures_folder_url=link))
        if not folder_id:
            issues.append({'session_id':record.id,'session_name':record.exam_session_name,
                'error':f'{purpose} folder is not configured.' if not link else f'{purpose} must contain a valid Google Drive folder link.'})
            continue
        item=folders.setdefault(folder_id,dict(folder_id=folder_id,session_ids=[],session_names=[]))
        item['session_ids'].append(record.id);item['session_names'].append(record.exam_session_name)
    if action=='prepare':
        return jsonify(ok=True,folders=list(folders.values()),issues=issues)
    selected=list(dict.fromkeys(request.form.getlist('folder_ids')))
    if not selected or len(selected)>20:
        return jsonify(ok=False,error='Select between 1 and 20 folders per verification request.'),400
    results=[]
    for folder_id in selected:
        if folder_id not in folders:
            results.append(dict(folder_id=folder_id,status='not_configured',error='This folder is not currently configured in the selected sessions. Refresh and retry.'))
            continue
        result=dict(folders[folder_id])
        try:
            metadata=folder_metadata(folder_id)
            result.update(status='authorized',name=metadata['name'])
        except DriveStorageError as error:
            result.update(status='failed',error=str(error))
        results.append(result)
    return jsonify(ok=True,results=results,issues=issues)
