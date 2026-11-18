"""Attendance uploads use the portal's existing Drive connection and rollback cleanup."""
from dataclasses import dataclass
from types import SimpleNamespace
from pathlib import PurePosixPath
import json
from urllib.request import Request, urlopen
from app.google_drive import upload_document, folder_metadata, access_token, API, DriveStorageError

LISTS_FOLDER = '1OSADWoQ9pZDmqh-TAirlqHk89X8dwxlv'


@dataclass
class AttendanceUploadTarget:
    request_number: str = ''
    document: object = None


def upload(file, folder_id, basename):
    suffix=PurePosixPath((file.filename or '').replace('\\','/')).suffix
    suffix=suffix if len(suffix)<=15 else ''
    file.filename=basename+suffix
    folder_metadata(folder_id)
    target=AttendanceUploadTarget()
    upload_document(file,target,SimpleNamespace(folder_id=folder_id))
    return target.document


def trash(file_id, trashed=True):
    with urlopen(Request(API+'/files/'+file_id+'?supportsAllDrives=true&fields=id%2Ctrashed',
        data=json.dumps({'trashed':trashed}).encode(),method='PATCH',
        headers={'Authorization':'Bearer '+access_token(),'Content-Type':'application/json'}),timeout=20) as response:
        result=json.load(response)
    if result.get('id')!=file_id or result.get('trashed') is not trashed:
        raise DriveStorageError('Drive did not confirm the file change. Please try again.')
