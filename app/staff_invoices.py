"""Single-file invoice upload through each staff member's existing private portal."""
from dataclasses import dataclass
from flask import Blueprint, abort, flash, redirect, request, url_for, g
from app import db, validate_csrf, login_required
from sqlalchemy.exc import IntegrityError
from app.models import StaffExamSessionsShare, GoogleDriveStaffInvoiceUpload
from app.google_drive import DriveStorageError, destination_for_category, upload_document, stream_document

staff_invoices_bp = Blueprint('staff_invoices', __name__)


@dataclass
class StaffInvoiceTarget:
    share_id: int
    year: int
    token: str
    request_number: str


def confirmed_share_for_year(share, year):
    from app.routes import staff_submission_assignment
    for submission in share.submissions:
        record = submission.exam_session
        if not record or not record.session_date or record.session_date.year != year:
            continue
        assignment, person_ref = staff_submission_assignment(record, submission.assignment_type, submission.assignment_id)
        if not assignment or person_ref != share.person_ref:
            continue
        status = record.emergency_contact_participation_status if submission.assignment_type == 'emergency_contact' else assignment.participation_status
        if status == 'Confirmed':
            return True
    return False


@staff_invoices_bp.post('/my-exam-sessions/<token>/invoices')
def upload(token):
    share = StaffExamSessionsShare.query.filter_by(token=token).first_or_404()
    year = request.form.get('session_year', type=int)
    if year is None or not confirmed_share_for_year(share, year):
        abort(403)
    target_url = url_for('staff.staff_exam_sessions', token=token, session_year=year) + '#invoice-information-title'
    if not validate_csrf():
        flash('Security token expired. Reload the page before uploading your invoice.', 'staff-invoice-error')
        return redirect(target_url)
    files = [file for file in request.files.getlist('invoice_file') if file.filename]
    if len(files) != 1:
        flash('Please select exactly one invoice file.', 'staff-invoice-error')
        return redirect(target_url)
    if GoogleDriveStaffInvoiceUpload.query.filter_by(share_id=share.id, year=year).first():
        flash('An invoice has already been uploaded for this year. Contact Path Examinations if it needs to be replaced.', 'staff-invoice-error')
        return redirect(target_url)
    destination = destination_for_category('staff_invoices')
    if destination is None:
        flash('Invoice uploads are not available yet. Please contact Path Examinations.', 'staff-invoice-error')
        return redirect(target_url)
    from app.models import AcademicStaff, PotentialEntry
    ref = share.person_ref
    person = db.session.get(PotentialEntry if ref.startswith('potential:') else AcademicStaff, int(ref.split(':')[-1]))
    if person is None:
        abort(404)
    target = StaffInvoiceTarget(share.id, year, token, f'Staff invoice {year} - {person.full_name}')
    try:
        upload_document(files[0], target, destination)
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        flash('An invoice has already been uploaded for this year.', 'staff-invoice-error')
        return redirect(target_url)
    except OSError as exc:
        db.session.rollback()
        flash(str(exc) if isinstance(exc, DriveStorageError) else 'Your invoice could not be uploaded. Please try again.', 'staff-invoice-error')
        return redirect(target_url)
    flash('Your invoice was uploaded successfully.', 'staff-invoice-success')
    return redirect(target_url)


@staff_invoices_bp.get('/my-exam-sessions/<token>/invoices/<file_id>')
def download(token, file_id):
    share = StaffExamSessionsShare.query.filter_by(token=token).first_or_404()
    document = GoogleDriveStaffInvoiceUpload.query.filter_by(file_id=file_id, share_id=share.id).first_or_404()
    if not confirmed_share_for_year(share, document.year):
        abort(404)
    return stream_document(document)


def invoice_for_staff_payment(member_id, year):
    return (GoogleDriveStaffInvoiceUpload.query.join(StaffExamSessionsShare,
        GoogleDriveStaffInvoiceUpload.share_id == StaffExamSessionsShare.id)
        .filter(StaffExamSessionsShare.person_ref == str(member_id), GoogleDriveStaffInvoiceUpload.year == year)
        .first_or_404())


@staff_invoices_bp.get('/staff-payments/<int:member_id>/<int:year>/invoice')
@login_required
def preview(member_id, year):
    from app.routes import require_menu_view
    require_menu_view('staff_payments')
    response = stream_document(invoice_for_staff_payment(member_id, year))
    response.headers['Content-Security-Policy'] = "frame-ancestors 'self'; base-uri 'none'"
    return response


def trash_document(document):
    import json
    from urllib.request import Request, urlopen
    from app.google_drive import API, access_token
    try:
        with urlopen(Request(API + '/files/' + document.file_id + '?supportsAllDrives=true&fields=id%2Ctrashed',
            data=json.dumps({'trashed': True}).encode(), method='PATCH',
            headers={'Authorization': 'Bearer ' + access_token(), 'Content-Type': 'application/json'}), timeout=15) as response:
            result = json.load(response)
        if result.get('id') != document.file_id or result.get('trashed') is not True:
            raise ValueError('Drive did not confirm trashing the invoice')
    except (OSError, ValueError, KeyError) as exc:
        raise DriveStorageError('The invoice could not be moved to the Drive trash. Nothing was removed from the portal; please try again.') from exc


@staff_invoices_bp.post('/staff-payments/<int:member_id>/<int:year>/invoice/remove')
@login_required
def remove(member_id, year):
    from app.routes import require_menu_edit
    require_menu_edit('staff_payments')
    if not validate_csrf():
        abort(400, description='Security token expired. Reload the page and try again.')
    document = invoice_for_staff_payment(member_id, year)
    from app.staff_invoice_notifications import queue_invoice_cancellation, deliver_invoice_cancellation
    try:
        trash_document(document)
        notice_id = queue_invoice_cancellation(document, member_id)
        db.session.delete(document)
        db.session.commit()
    except OSError as exc:
        db.session.rollback()
        flash(str(exc), 'error')
        return redirect(url_for('staff.staff_payments', session_year=year))
    email_sent = deliver_invoice_cancellation(notice_id)
    flash('Invoice moved to the Drive trash. The staff member can upload a new invoice.', 'success')
    if not email_sent:
        flash('The invoice was annulled, but the email could not be confirmed. Check Email connection before retrying the notification.', 'error')
    return redirect(url_for('staff.staff_payments', session_year=year))
