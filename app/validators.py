import re
from urllib.parse import urlparse

STATUSES_CREATE = {"Inactive", "Active"}
STATUSES_EDIT = {"Archived", "Inactive", "Active"}
POTENTIAL_STATUSES = {
    "CV to be reviewed",
    "Review interview date and time",
    "Interview to be arranged",
    "Interview invitation sent",
    "Interview confirmed",
    "Entry accepted",
    "Onboarding email sent",
    "Induction confirmed",
    "Onboarding finalised",
    "Entry rejected",
    "Archived accepted entry",
    "Archived rejected entry",
}
ARRANGED_STATUSES = {"Interview invitation sent", "Interview confirmed", "Induction confirmed"}
PLATFORMS = {"Zoom", "Meet", ""}
INTERVIEWERS = {
    "Prof. Lic. Agustina Savini",
    "Prof. Brenda Sartori",
    "Prof. Marcela Romero",
    "Prof. Mgter. Pablo Demarchi",
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


def validate_member_form(form, allow_archived=False, require_complete=False):
    errors = []
    status_options = STATUSES_EDIT if allow_archived else STATUSES_CREATE

    status = form.get("status", "").strip()
    title = form.get("title", "").strip()
    full_name = form.get("full_name", "").strip()
    phone = form.get("phone", "").strip()
    email = form.get("email", "").strip()
    cv = form.get("cv", "").strip()
    profile_picture = form.get("profile_picture", "").strip()
    location_point = form.get("location_point", "").strip()
    started_in = form.get("started_in", "").strip()
    full_address_google_maps = form.get("full_address_google_maps", "").strip()
    city = form.get("city", "").strip()
    province = form.get("province", "").strip()
    country = form.get("country", "").strip()
    account_id = form.get("account_id", "").strip()
    account_owner = form.get("account_owner", "").strip()
    roles = form.getlist("roles")
    has_car = form.get("has_car", "").strip()

    if not status or status not in status_options:
        errors.append("Status is required.")
    if not full_name:
        errors.append("Full name is required.")
    if require_complete:
        if not title:
            errors.append("Title is required.")
        if not roles:
            errors.append("At least one role is required.")
        if not phone:
            errors.append("Phone is required.")
        if not email:
            errors.append("Email is required.")
        if not has_car:
            errors.append("Has a car is required.")
        if not started_in:
            errors.append("Started in is required.")
        if not full_address_google_maps:
            errors.append("Full address is required.")
        if not city:
            errors.append("City is required.")
        if not province:
            errors.append("Province is required.")
        if not country:
            errors.append("Country is required.")
        if not cv:
            errors.append("CV is required.")
        if not profile_picture:
            errors.append("Profile picture is required.")
        if not account_id:
            errors.append("Account ID is required.")
        if not account_owner:
            errors.append("Account owner is required.")
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


def validate_potential_acceptance_draft_form(form):
    errors = []
    status = form.get("status", "").strip()
    email = form.get("email", "").strip()
    cv = form.get("cv", "").strip()
    profile_picture = form.get("profile_picture", "").strip()
    started_in = form.get("started_in", "").strip()
    roles = form.getlist("roles")
    has_car = form.get("has_car", "").strip()

    if status and status not in STATUSES_CREATE:
        errors.append("Status is invalid.")
    if email and not EMAIL_RE.match(email):
        errors.append("Email must be a valid email address.")
    if cv and not is_valid_url(cv):
        errors.append("CV must be a valid http or https URL.")
    if profile_picture and not is_valid_url(profile_picture):
        errors.append("Profile picture must be a valid http or https URL.")
    if started_in and not YEAR_RE.match(started_in):
        errors.append("Started in must be a four-digit year.")
    if any(role not in ROLES for role in roles):
        errors.append("Roles contains an invalid value.")
    if has_car not in HAS_CAR:
        errors.append("Has a car contains an invalid value.")

    return errors


def validate_potential_form(form, require_status=True, require_cv=False):
    errors = []
    status = form.get("status", "").strip()
    full_name = form.get("full_name", "").strip()
    email = form.get("email", "").strip()
    cv = form.get("cv", "").strip()
    interview_date = form.get("interview_date", "").strip()
    interview_time = form.get("interview_time", "").strip()
    platform = form.get("platform", "").strip()
    interviewer = form.get("interviewer", "").strip()

    if require_status and (not status or status not in POTENTIAL_STATUSES):
        errors.append("Status is required.")
    if not full_name:
        errors.append("Full name is required.")
    if email and not EMAIL_RE.match(email):
        errors.append("Email must be a valid email address.")
    if require_cv and not cv:
        errors.append("CV is required.")
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
