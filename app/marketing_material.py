"""Restricted editor and revocable, read-only marketing share."""
import secrets
from datetime import datetime, timezone
from functools import wraps
from urllib.parse import urlsplit

from flask import Blueprint, abort, jsonify, redirect, render_template, request, session, url_for

from app import db, login_required, validate_csrf
from app.models import ExamSession, MarketingMaterialInfo, MarketingMaterialShare
from app.rich_text import sanitize_instructions

marketing_bp = Blueprint("marketing", __name__)


def permission(edit=False):
    def decorate(view):
        @wraps(view)
        @login_required
        def wrapped(*args, **kwargs):
            from app.routes import require_menu_edit, require_menu_view
            (require_menu_edit if edit else require_menu_view)("pre_session_control_tower")
            return view(*args, **kwargs)
        return wrapped
    return decorate


def distinct(values):
    return list(dict.fromkeys(values))


def valid_folder(value):
    try:
        parsed = urlsplit(value)
        return parsed.scheme in {"http", "https"} and bool(parsed.hostname) and not parsed.username and not parsed.password
    except ValueError:
        return False


def sort_marketing_rows(rows):
    search = request.args.get("q", "").strip()
    formats = ("Online", "Online at exam centre", "Onsite")
    selected_format = next((value for value in formats if value.casefold() == request.args.get("format", "").strip().casefold()), "")
    rows[:] = [row for row in rows
               if (not search or any(search.casefold() in name.casefold() for name in row["names"]))
               and (not selected_format or any(selected_format.casefold() == value.strip().casefold() for value in row["formats"]))]
    columns = {"exam_session": "names", "date": "dates", "format": "formats", "city": "cities"}
    column = request.args.get("sort", "date")
    if column not in columns:
        column = "date"
    direction = "desc" if request.args.get("dir") == "desc" else "asc"
    field = columns[column]

    def key(row):
        values = row[field]
        return min(values) if column == "date" else " ".join(values).casefold()

    populated = [row for row in rows if row[field]]
    empty = [row for row in rows if not row[field]]
    rows[:] = sorted(populated, key=key, reverse=direction == "desc") + empty

    def sort_url(target):
        filters = {}
        if search:
            filters["q"] = search
        if selected_format:
            filters["format"] = selected_format
        return url_for(request.endpoint, **(request.view_args or {}), sort=target,
                       dir="desc" if target == column and direction == "asc" else "asc", **filters)

    return {"sort_column": column, "sort_direction": direction, "sort_url": sort_url,
            "search": search, "selected_format": selected_format, "format_options": formats}


def marketing_rows():
    from app.routes import latest_active_exam_session_year, exam_session_concat_component_map
    year = latest_active_exam_session_year()
    selected = ExamSession.query.filter(db.extract("year", ExamSession.session_date) == year).all()
    components = exam_session_concat_component_map()
    selected_ids = set().union(*(components.get(record.id, {record.id}) for record in selected)) if selected else set()
    records = {record.id: record for record in ExamSession.query.filter(ExamSession.id.in_(selected_ids)).all()} if selected_ids else {}
    infos = {info.session_id: info for info in MarketingMaterialInfo.query.filter(MarketingMaterialInfo.session_id.in_(selected_ids)).all()} if selected_ids else {}
    rows, seen = [], set()
    for record in sorted(selected, key=lambda item: (item.session_date, item.id)):
        ids = components.get(record.id, {record.id})
        anchor = min(ids)
        if anchor in seen:
            continue
        seen.add(anchor)
        group = sorted((records[key] for key in ids if key in records), key=lambda item: (item.session_date, item.id))
        notes = [infos[item.id] for item in group if item.id in infos]
        info = next((note for note in notes if note.content or note.title), notes[0] if notes else None)
        folders = distinct((item.session_pictures_folder_url or "").strip() for item in group if (item.session_pictures_folder_url or "").strip())
        conflict = len(folders) > 1
        folder = folders[0] if len(folders) == 1 and valid_folder(folders[0]) else ""
        cities, city_keys = [], set()
        for item in group:
            city = ", ".join(value.strip() for value in [item.city or "", item.province or ""] if value.strip())
            if city and city.casefold() not in city_keys:
                cities.append(city)
                city_keys.add(city.casefold())
        rows.append({"id": anchor, "names": [item.exam_session_name for item in group],
                     "dates": distinct(item.session_date for item in group), "formats": distinct(item.format for item in group),
                     "cities": cities, "folder": "" if conflict else folder,
                     "folder_error": "Conflicting Session pictures folders. Configure the same folder for every concatenated session." if conflict else "Invalid Session pictures folder URL." if folders and not folder else "",
                     "sessions": [{"id": item.id, "name": item.exam_session_name, "year": item.session_date.year} for item in group],
                     "title": info.title if info else "", "content": sanitize_instructions(info.content) if info else ""})
    return year, rows


@marketing_bp.after_request
def private_response(response):
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    return response


@marketing_bp.get("/marketing-material")
@permission()
def index():
    from app.routes import user_can_edit
    year, rows = marketing_rows()
    sorting = sort_marketing_rows(rows)
    share = db.session.get(MarketingMaterialShare, 1)
    session.setdefault("csrf_token", secrets.token_urlsafe(32))
    return render_template("marketing_material/index.html", rows=rows, year=year, public=False,
        can_edit=user_can_edit("pre_session_control_tower"), csrf_token=session["csrf_token"], share=share,
        share_url=url_for("marketing.shared", token=share.token, _external=True) if share else "", **sorting)


@marketing_bp.post("/marketing-material/share")
@permission(edit=True)
def manage_share():
    if not validate_csrf():
        abort(400)
    action = request.form.get("action")
    if action not in {"enable", "disable", "regenerate"}:
        abort(400)
    share = db.session.get(MarketingMaterialShare, 1)
    if share is None:
        share = MarketingMaterialShare(id=1, token=secrets.token_urlsafe(32))
        db.session.add(share)
    if action == "regenerate":
        share.token = secrets.token_urlsafe(32)
    share.enabled = action != "disable"
    db.session.commit()
    return redirect(url_for("marketing.index"))


@marketing_bp.get("/marketing-material/shared/<token>")
def shared(token):
    share = MarketingMaterialShare.query.filter_by(token=token).first_or_404()
    if not share.enabled:
        abort(410)
    year, rows = marketing_rows()
    sorting = sort_marketing_rows(rows)
    # Public output is allowlisted; no editing endpoints or internal error details.
    fields = {"id", "names", "dates", "formats", "cities", "folder", "title", "content"}
    safe_rows = [{key: value for key, value in row.items() if key in fields} for row in rows]
    return render_template("marketing_material/index.html", rows=safe_rows, year=year, public=True, can_edit=False, **sorting)


@marketing_bp.post("/marketing-material/sessions/<int:session_id>/info")
@permission(edit=True)
def save_info(session_id):
    from app.routes import monthly_unified_total_session_ids
    if not validate_csrf():
        abort(400)
    record = ExamSession.query.get_or_404(session_id)
    title, content = request.form.get("title", "").strip(), request.form.get("instructions", "")
    if len(title) > 200 or len(content) > 50000:
        return jsonify(ok=False, error="Title must be 200 characters or fewer and content 50,000 characters or fewer."), 400
    content = sanitize_instructions(content)
    # Copy to each member so the text remains available if the group is later split.
    for member_id in monthly_unified_total_session_ids(record):
        info = MarketingMaterialInfo.query.filter_by(session_id=member_id).first()
        if info is None:
            info = MarketingMaterialInfo(session_id=member_id)
            db.session.add(info)
        info.title, info.content = title, content
        info.updated_by = session.get("user_email") or session.get("user")
        info.updated_at = datetime.now(timezone.utc)
    db.session.commit()
    return jsonify(ok=True, title=title, instructions=content)
