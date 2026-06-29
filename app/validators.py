import re
from urllib.parse import urlparse

STATUSES_CREATE = {"Inactive", "Active"}
STATUSES_EDIT = {"Archived", "Inactive", "Active"}
POTENTIAL_STATUSES = {"To be interviewed", "Interview arranged", "Interview scheduled"}
ARRANGED_STATUSES = {"Interview arranged", "Interview scheduled"}
PLATFORMS = {"Zoom", "Meet", ""}
INTERVIEWERS = {
    "Prof. Mgter. Pablo Demarchi | Managing Director",
    "Prof. Lic. Agustina Savini | Team Leader",
    "Prof. Brenda Sartori | Customer Experience Officer",
    "Prof. Marcela Romero | Admissions Officer",
    "Prof. Mgter. Pablo Demarchi | Managing Director | pablo.demarchi@pathexaminations.com",
    "Prof. Lic. Agustina Savini | Team Leader | agustina.savini@pathexaminations.com",
    "Prof. Brenda Sartori | Customer Experience Officer | admin@pathexaminations.com",
    "Prof. Marcela Romero | Admissions Officer | admissions@pathexaminations.com",
    "",
}
ROLES = {"Examiner", "Supervisor", "Intern", "RSG"}
HAS_CAR = {"Yes", "No", ""}

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
YEAR_RE = re.compile(r"^\d{4}$")
TIME_RE = re.compile(r"^\d{2}:\d{2}:\d{2}$")


def is_valid_url(value):
    if not value:
        return True
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def is_valid_google_maps_url(value):
    if not value:
        return True
    parsed = urlparse(value)
    host = parsed.netloc.lower()
    if parsed.scheme not in {"http", "https"} or not host:
        return False
    return (
        host == "maps.app.goo.gl"
        or host == "goo.gl"
        or host == "maps.google.com"
        or host.endswith(".google.com") and parsed.path.startswith("/maps")
        or host.startswith("maps.google.")
        or host.startswith("www.google.") and parsed.path.startswith("/maps")
    )


def validate_member_form(form, allow_archived=False):
    errors = []
    status_options = STATUSES_EDIT if allow_archived else STATUSES_CREATE

    status = form.get("status", "").strip()
    full_name = form.get("full_name", "").strip()
    email = form.get("email", "").strip()
    cv = form.get("cv", "").strip()
    profile_picture = form.get("profile_picture", "").strip()
    location_point = form.get("location_point", "").strip()
    started_in = form.get("started_in", "").strip()
    roles = form.getlist("roles")
    has_car = form.get("has_car", "").strip()

    if not status or status not in status_options:
        errors.append("Status is required.")
    if not full_name:
        errors.append("Full name is required.")
    if email and not EMAIL_RE.match(email):
        errors.append("Email must be a valid email address.")
    if cv and not is_valid_url(cv):
        errors.append("CV must be a valid http or https URL.")
    if profile_picture and not is_valid_url(profile_picture):
        errors.append("Profile picture must be a valid http or https URL.")
    if location_point and not is_valid_google_maps_url(location_point):
        errors.append("Location point must be a valid Google Maps URL.")
    if started_in and not YEAR_RE.match(started_in):
        errors.append("Started in must be a four-digit year.")
    if any(role not in ROLES for role in roles):
        errors.append("Roles contains an invalid value.")
    if has_car not in HAS_CAR:
        errors.append("Has a car contains an invalid value.")

    return errors


def validate_potential_form(form):
    errors = []
    status = form.get("status", "").strip()
    full_name = form.get("full_name", "").strip()
    email = form.get("email", "").strip()
    cv = form.get("cv", "").strip()
    interview_date = form.get("interview_date", "").strip()
    interview_time = form.get("interview_time", "").strip()
    platform = form.get("platform", "").strip()
    interviewer = form.get("interviewer", "").strip()

    if not status or status not in POTENTIAL_STATUSES:
        errors.append("Status is required.")
    if not full_name:
        errors.append("Full name is required.")
    if email and not EMAIL_RE.match(email):
        errors.append("Email must be a valid email address.")
    if cv and not is_valid_url(cv):
        errors.append("CV must be a valid http or https URL.")
    if status in ARRANGED_STATUSES:
        if not interview_date:
            errors.append("Interview date is required.")
        if not interview_time or not TIME_RE.match(interview_time):
            errors.append("Interview time must use HH:MM:SS 24-hour format.")
        if platform not in {"Zoom", "Meet"}:
            errors.append("Platform is required.")
        if interviewer not in INTERVIEWERS or not interviewer:
            errors.append("Interviewer is required.")
    if platform not in PLATFORMS:
        errors.append("Platform contains an invalid value.")
    if interviewer not in INTERVIEWERS:
        errors.append("Interviewer contains an invalid value.")

    return errors
