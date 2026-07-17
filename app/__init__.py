import os
import secrets
from functools import wraps

from dotenv import load_dotenv
from flask import Flask, g, redirect, render_template, request, session, url_for
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text
from werkzeug.security import check_password_hash, generate_password_hash

db = SQLAlchemy()
DEPLOY_SUPERADMIN_EMAIL = "pablo.demarchi@pathexaminations.com"


def create_app():
    load_dotenv()

    app = Flask(__name__, instance_relative_config=True)
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY") or secrets.token_hex(32)
    app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv(
        "DATABASE_URL", "sqlite:///academic_staff.db"
    )
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

    db.init_app(app)

    from app.models import (
        AcademicStaff,
        AnnualCertificationRecord,
        AnnualMeetingRecord,
        CertificationYearConfiguration,
        ExaminerCertificationAnnualMeetingSelection,
        ExaminerCertificationFut1Selection,
        ExaminerCertificationFut2Selection,
        ExaminerCertificationRemoteTrainingSelection,
        ExaminerCertificationYear,
        ExamSession,
        ExamSessionCommunicationsChecklistItem,
        ExamSessionCommunicationsControl,
        ExamSessionCommunicationsEvent,
        ExamSessionExaminerAssignment,
        ExamSessionFinanceControl,
        ExamSessionFinanceEvent,
        ExamSessionIncident,
        ExamSessionIncidentChecklistItem,
        ExamSessionIncidentEvent,
        ExamSessionIncidentImpactReview,
        ExamSessionIncidentReviewFlag,
        ExamSessionInternAssignment,
        ExamSessionJourneyShare,
        ExamSessionLogistics,
        ExamSessionLogisticsControl,
        ExamSessionLogisticsConcept,
        ExamSessionLogisticsConceptNote,
        ExamSessionMonthlyCandidateTotal,
        ExamSessionMonthlyRegistration,
        ExamSessionPackageChecklistItem,
        ExamSessionPackageEvent,
        ExamSessionPackageUnit,
        ExamSessionScheduleEvent,
        ExamSessionScheduleWorkflow,
        ExamSessionShipmentBundle,
        ExamSessionShipmentBundleSession,
        ExamSessionShipmentChecklistItem,
        ExamSessionShipmentEvent,
        ExamSessionSinapsisChecklistItem,
        ExamSessionSinapsisControl,
        ExamSessionSinapsisEvent,
        ExamSessionStaffingControl,
        ExamSessionSupervisorAssignment,
        ExamSessionYear,
        Fee,
        InternStage2Selection,
        InternStage3Selection,
        InternStageAnnualMeetingSelection,
        InternStageFutSelection,
        InternStageRemoteTrainingSelection,
        InternStageYear,
        PotentialEntry,
        PotentialEntryNoteMention,
        PotentialEntryPreassignedExamSession,
        PotentialEntryStatusTrack,
        Provider,
        ProviderHistory,
        ProviderType,
        Role,
        StaffMembersSettings,
        StaffPayment,
        StaffCertificationFut2Selection,
        StaffCertificationFutSelection,
        SupervisorCertificationAnnualMeetingSelection,
        SupervisorCertificationFutSelection,
        SupervisorCertificationRemoteTrainingSelection,
        SupervisorCertificationYear,
        User,
        UserMenuPermission,
        VALID_MENU_PERMISSION_KEYS,
    )
    from app.routes import staff_bp

    app.register_blueprint(staff_bp)

    @app.before_request
    def load_user():
        g.user = session.get("user")
        g.user_id = session.get("user_id")
        g.user_department = session.get("user_department")
        g.is_admin = session.get("user_department") == "Admin"
        g.current_user = None
        if g.user_id:
            current_user = User.query.get(g.user_id)
            if current_user and current_user.email == session.get("user_email"):
                g.current_user = current_user

    @app.after_request
    def set_security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        return response

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if g.user:
            return redirect(url_for("staff.dashboard"))

        error = None
        if request.method == "POST":
            email_or_username = request.form.get("email", request.form.get("username", "")).strip()
            password = request.form.get("password", "")
            normalized_email = email_or_username.lower()

            if User.query.count():
                user = User.query.filter_by(email=normalized_email).first()
                if user and user.is_active and check_password_hash(user.password_hash, password):
                    session.clear()
                    session["user"] = user.full_name
                    session["user_id"] = user.id
                    session["user_full_name"] = user.full_name
                    session["user_email"] = user.email
                    session["user_department"] = user.department
                    session["csrf_token"] = secrets.token_urlsafe(32)
                    return redirect(url_for("staff.dashboard"))
                error = "Invalid email or password."
            else:
                expected_username = os.getenv("ADMIN_USERNAME", "admin")
                password_hash = os.getenv("ADMIN_PASSWORD_HASH", "")

                if not password_hash or "replace-this-with-a-generated-hash" in password_hash:
                    password_hash = generate_password_hash("admin123", method="pbkdf2:sha256")

                if email_or_username == expected_username and check_password_hash(password_hash, password):
                    session.clear()
                    session["user"] = expected_username
                    session["user_full_name"] = expected_username
                    session["user_email"] = ""
                    session["user_department"] = "Admin"
                    session["csrf_token"] = secrets.token_urlsafe(32)
                    return redirect(url_for("staff.dashboard"))

                error = "Invalid email or password."

        return render_template("login.html", error=error)

    @app.route("/logout", methods=["POST"])
    def logout():
        session.clear()
        return redirect(url_for("login"))

    @app.errorhandler(403)
    def access_denied(error):
        message = getattr(error, "description", None) or "Your account does not have permission to perform this action."
        return render_template(
            "errors/403.html",
            message=message,
            previous_url=request.referrer,
            current_menu_key="",
            current_menu_can_view=False,
            current_menu_can_edit=False,
            current_user_is_view_only=False,
        ), 403

    with app.app_context():
        db.create_all()
        app_user_columns = {
            row[1] for row in db.session.execute(text("PRAGMA table_info(app_user)"))
        }
        if app_user_columns and "is_superadmin" not in app_user_columns:
            db.session.execute(text("ALTER TABLE app_user ADD COLUMN is_superadmin BOOLEAN NOT NULL DEFAULT 0"))
            db.session.commit()
        if app_user_columns and "can_only_be_edited_by_superadmin" not in app_user_columns:
            db.session.execute(text("ALTER TABLE app_user ADD COLUMN can_only_be_edited_by_superadmin BOOLEAN NOT NULL DEFAULT 0"))
            db.session.commit()
        user_menu_permission_columns = {
            row[1] for row in db.session.execute(text("PRAGMA table_info(user_menu_permission)"))
        }
        if user_menu_permission_columns and "can_manage_permissions" not in user_menu_permission_columns:
            db.session.execute(text("ALTER TABLE user_menu_permission ADD COLUMN can_manage_permissions BOOLEAN NOT NULL DEFAULT 0"))
            db.session.commit()
        fee_columns = {
            row[1] for row in db.session.execute(text("PRAGMA table_info(fee)"))
        }
        if fee_columns and "valid_through" not in fee_columns:
            db.session.execute(text("ALTER TABLE fee ADD COLUMN valid_through TEXT NOT NULL DEFAULT '[]'"))
            db.session.commit()
        certification_year_configuration_columns = {
            row[1] for row in db.session.execute(text("PRAGMA table_info(certification_year_configuration)"))
        }
        if certification_year_configuration_columns and "annual_meeting_time" not in certification_year_configuration_columns:
            db.session.execute(text("ALTER TABLE certification_year_configuration ADD COLUMN annual_meeting_time TIME"))
            db.session.commit()
        potential_entry_columns = {
            row[1] for row in db.session.execute(text("PRAGMA table_info(potential_entry)"))
        }
        staff_members_settings_columns = {
            row[1] for row in db.session.execute(text("PRAGMA table_info(staff_members_settings)"))
        }
        if staff_members_settings_columns and "upcoming_induction_session_options" not in staff_members_settings_columns:
            db.session.execute(text("ALTER TABLE staff_members_settings ADD COLUMN upcoming_induction_session_options TEXT"))
            db.session.commit()
        if potential_entry_columns and "interview_invitation_sent" not in potential_entry_columns:
            db.session.execute(text("ALTER TABLE potential_entry ADD COLUMN interview_invitation_sent BOOLEAN NOT NULL DEFAULT 0"))
            db.session.commit()
        if potential_entry_columns and "department" not in potential_entry_columns:
            db.session.execute(text("ALTER TABLE potential_entry ADD COLUMN department VARCHAR(40) NOT NULL DEFAULT 'Admissions'"))
            db.session.commit()
        if potential_entry_columns and "updated_on" not in potential_entry_columns:
            db.session.execute(text("ALTER TABLE potential_entry ADD COLUMN updated_on DATETIME"))
            db.session.execute(text("UPDATE potential_entry SET updated_on = COALESCE(created_on, CURRENT_TIMESTAMP) WHERE updated_on IS NULL"))
            db.session.commit()
        note_metadata_columns = {
            "from_user_id": "INTEGER",
            "from_full_name": "VARCHAR(160)",
            "from_department": "VARCHAR(40)",
            "to_user_id": "INTEGER",
            "to_full_name": "VARCHAR(160)",
            "to_department": "VARCHAR(40)",
            "updated_on": "DATETIME",
        }
        for table_name in ("provider_history", "exam_session_logistics_concept_note"):
            table_columns = {
                row[1] for row in db.session.execute(text(f"PRAGMA table_info({table_name})"))
            }
            for column_name, column_type in note_metadata_columns.items():
                if table_columns and column_name not in table_columns:
                    db.session.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}"))
                    if column_name == "updated_on":
                        db.session.execute(text(f"UPDATE {table_name} SET updated_on = COALESCE(created_on, CURRENT_TIMESTAMP) WHERE updated_on IS NULL"))
                    db.session.commit()
        db.session.execute(text("""
            CREATE TABLE IF NOT EXISTS potential_entry_note_mention (
                id INTEGER PRIMARY KEY,
                note_id VARCHAR(64) NOT NULL UNIQUE,
                related_entity_type VARCHAR(80) NOT NULL DEFAULT 'Potential entry',
                related_entity_id INTEGER NOT NULL,
                potential_entry_id INTEGER NOT NULL,
                from_user_id INTEGER,
                from_full_name VARCHAR(160),
                from_department VARCHAR(40),
                to_user_id INTEGER,
                to_full_name VARCHAR(160),
                to_department VARCHAR(40),
                comment_text TEXT NOT NULL,
                is_read BOOLEAN NOT NULL DEFAULT 0,
                read_by_user_id INTEGER,
                read_on DATETIME,
                created_on DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_on DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(potential_entry_id) REFERENCES potential_entry (id) ON DELETE CASCADE,
                FOREIGN KEY(from_user_id) REFERENCES app_user (id),
                FOREIGN KEY(to_user_id) REFERENCES app_user (id),
                FOREIGN KEY(read_by_user_id) REFERENCES app_user (id)
            )
        """))
        db.session.execute(text("CREATE INDEX IF NOT EXISTS ix_potential_entry_note_mention_to_read ON potential_entry_note_mention (to_user_id, is_read)"))
        db.session.execute(text("CREATE INDEX IF NOT EXISTS ix_potential_entry_note_mention_entry ON potential_entry_note_mention (potential_entry_id)"))
        db.session.commit()
        potential_entry_draft_columns = {
            "acceptance_status": "VARCHAR(40)",
            "title": "VARCHAR(120)",
            "seniority": "BOOLEAN NOT NULL DEFAULT 0",
            "acceptance_roles": "TEXT",
            "has_car": "VARCHAR(10)",
            "started_in": "VARCHAR(4)",
            "full_address_google_maps": "VARCHAR(500)",
            "country": "VARCHAR(120)",
            "profile_picture": "VARCHAR(500)",
            "account_id": "VARCHAR(120)",
            "account_owner": "VARCHAR(160)",
            "account_owner_id": "VARCHAR(120)",
            "cv_review_interview_options": "TEXT",
            "interview_no_show": "BOOLEAN NOT NULL DEFAULT 0",
            "entry_added_in_sessions_pre_confirmation": "BOOLEAN NOT NULL DEFAULT 0",
            "reactivation_date": "VARCHAR(10)",
            "entry_accepted_notes_checked": "BOOLEAN NOT NULL DEFAULT 0",
            "entry_accepted_email_sent": "BOOLEAN NOT NULL DEFAULT 0",
            "entry_accepted_whatsapp_sent": "BOOLEAN NOT NULL DEFAULT 0",
            "onboarding_follow_up_choice": "VARCHAR(20)",
            "onboarding_turn_down_sessions_removed": "BOOLEAN NOT NULL DEFAULT 0",
            "onboarding_turn_down_trainer_notified": "BOOLEAN NOT NULL DEFAULT 0",
            "induction_session_status": "VARCHAR(20)",
            "exam_session_participation_statuses_pre_confirmed": "BOOLEAN NOT NULL DEFAULT 0",
        }
        for column_name, column_type in potential_entry_draft_columns.items():
            if potential_entry_columns and column_name not in potential_entry_columns:
                db.session.execute(text(f"ALTER TABLE potential_entry ADD COLUMN {column_name} {column_type}"))
                db.session.commit()
        journey_share_columns = {
            row[1] for row in db.session.execute(text("PRAGMA table_info(exam_session_journey_share)"))
        }
        if journey_share_columns:
            if "audience" not in journey_share_columns:
                db.session.execute(text("ALTER TABLE exam_session_journey_share ADD COLUMN audience TEXT NOT NULL DEFAULT 'institution'"))
            if "revoked_by" not in journey_share_columns:
                db.session.execute(text("ALTER TABLE exam_session_journey_share ADD COLUMN revoked_by VARCHAR(120)"))
            if "regenerated_at" not in journey_share_columns:
                db.session.execute(text("ALTER TABLE exam_session_journey_share ADD COLUMN regenerated_at DATETIME"))
            if "regenerated_by" not in journey_share_columns:
                db.session.execute(text("ALTER TABLE exam_session_journey_share ADD COLUMN regenerated_by VARCHAR(120)"))
            db.session.execute(text("UPDATE exam_session_journey_share SET audience = 'institution' WHERE audience IS NULL OR audience = ''"))
            db.session.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_exam_session_journey_share_audience_idx ON exam_session_journey_share (exam_session_id, audience)"))
            db.session.commit()
        shipment_bundle_columns = {
            row[1] for row in db.session.execute(text("PRAGMA table_info(exam_session_shipment_bundle)"))
        }
        if shipment_bundle_columns:
            if "bundle_number" not in shipment_bundle_columns:
                db.session.execute(text("ALTER TABLE exam_session_shipment_bundle ADD COLUMN bundle_number VARCHAR(20)"))
            if "bundle_sequence" not in shipment_bundle_columns:
                db.session.execute(text("ALTER TABLE exam_session_shipment_bundle ADD COLUMN bundle_sequence INTEGER"))
            if "bundle_year" not in shipment_bundle_columns:
                db.session.execute(text("ALTER TABLE exam_session_shipment_bundle ADD COLUMN bundle_year INTEGER"))
            if "auto_managed" not in shipment_bundle_columns:
                db.session.execute(text("ALTER TABLE exam_session_shipment_bundle ADD COLUMN auto_managed BOOLEAN NOT NULL DEFAULT 0"))
            if "split_from_bundle_id" not in shipment_bundle_columns:
                db.session.execute(text("ALTER TABLE exam_session_shipment_bundle ADD COLUMN split_from_bundle_id INTEGER"))
            if "auto_split_at" not in shipment_bundle_columns:
                db.session.execute(text("ALTER TABLE exam_session_shipment_bundle ADD COLUMN auto_split_at DATETIME"))
            db.session.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_shipment_bundle_number_idx ON exam_session_shipment_bundle (bundle_number)"))
            db.session.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_shipment_bundle_year_sequence_idx ON exam_session_shipment_bundle (bundle_year, bundle_sequence)"))
            db.session.execute(text("CREATE INDEX IF NOT EXISTS ix_shipment_bundle_auto_supervisor_deadline ON exam_session_shipment_bundle (auto_managed, supervisor_staff_id, dispatch_due_at)"))
            db.session.commit()
            from app.routes import backfill_shipment_bundle_numbers
            backfill_shipment_bundle_numbers()
            db.session.commit()
        db.session.execute(
            text(
                """
                INSERT INTO intern_stage3_selection (member_id, status, year, created_on, updated_on)
                SELECT old.member_id, old.status, old.year, old.created_on, old.updated_on
                FROM intern_stage2_selection AS old
                WHERE old.status = 'With FUT'
                  AND NOT EXISTS (
                    SELECT 1
                    FROM intern_stage3_selection AS new
                    WHERE new.member_id = old.member_id
                      AND new.year = old.year
                  )
                """
            )
        )
        db.session.execute(
            text(
                """
                UPDATE intern_stage3_selection
                SET status = 'With FUT'
                WHERE EXISTS (
                    SELECT 1
                    FROM intern_stage2_selection AS old
                    WHERE old.member_id = intern_stage3_selection.member_id
                      AND old.year = intern_stage3_selection.year
                      AND old.status = 'With FUT'
                )
                """
            )
        )
        db.session.execute(text("DELETE FROM intern_stage2_selection WHERE status = 'With FUT'"))
        db.session.commit()
        db.session.execute(
            text(
                """
                INSERT INTO intern_stage3_selection (member_id, status, year, created_on, updated_on)
                SELECT
                    fut.member_id,
                    CASE
                        WHEN SUM(CASE WHEN fut.status != 'completed' THEN 1 ELSE 0 END) = 0 THEN 'Completed'
                        ELSE 'With FUT'
                    END AS status,
                    fut.year,
                    MIN(fut.created_on),
                    MAX(fut.updated_on)
                FROM intern_stage_fut_selection AS fut
                GROUP BY fut.member_id, fut.year
                HAVING NOT EXISTS (
                    SELECT 1
                    FROM intern_stage3_selection AS stage_2
                    WHERE stage_2.member_id = fut.member_id
                      AND stage_2.year = fut.year
                )
                """
            )
        )
        db.session.execute(
            text(
                """
                UPDATE intern_stage3_selection
                SET status = (
                    SELECT
                        CASE
                            WHEN SUM(CASE WHEN fut.status != 'completed' THEN 1 ELSE 0 END) = 0 THEN 'Completed'
                            ELSE 'With FUT'
                        END
                    FROM intern_stage_fut_selection AS fut
                    WHERE fut.member_id = intern_stage3_selection.member_id
                      AND fut.year = intern_stage3_selection.year
                )
                WHERE EXISTS (
                    SELECT 1
                    FROM intern_stage_fut_selection AS fut
                    WHERE fut.member_id = intern_stage3_selection.member_id
                      AND fut.year = intern_stage3_selection.year
                )
                """
            )
        )
        db.session.commit()
        for table_name in (
            "intern_stage_remote_training_selection",
            "intern_stage2_selection",
            "intern_stage3_selection",
        ):
            db.session.execute(text(f"UPDATE {table_name} SET status = 'Completed' WHERE status = 'Certified'"))
        db.session.commit()
        existing_columns = {
            row[1] for row in db.session.execute(text("PRAGMA table_info(academic_staff)"))
        }
        if "location_point" not in existing_columns:
            db.session.execute(text("ALTER TABLE academic_staff ADD COLUMN location_point VARCHAR(500)"))
            db.session.commit()
        if "started_in" not in existing_columns:
            db.session.execute(text("ALTER TABLE academic_staff ADD COLUMN started_in VARCHAR(4)"))
            db.session.commit()
        if "full_address_google_maps" not in existing_columns:
            db.session.execute(text("ALTER TABLE academic_staff ADD COLUMN full_address_google_maps VARCHAR(500)"))
            db.session.commit()
        if "seniority" not in existing_columns:
            db.session.execute(text("ALTER TABLE academic_staff ADD COLUMN seniority BOOLEAN NOT NULL DEFAULT 0"))
            db.session.commit()
        if "fut_checked" not in existing_columns:
            db.session.execute(text("ALTER TABLE academic_staff ADD COLUMN fut_checked BOOLEAN NOT NULL DEFAULT 0"))
            db.session.commit()
        if "meeting_fut_checked" not in existing_columns:
            db.session.execute(text("ALTER TABLE academic_staff ADD COLUMN meeting_fut_checked BOOLEAN NOT NULL DEFAULT 0"))
            db.session.commit()
        if "profile_picture" not in existing_columns:
            db.session.execute(text("ALTER TABLE academic_staff ADD COLUMN profile_picture VARCHAR(500)"))
            db.session.commit()
        if "title" not in existing_columns:
            db.session.execute(text("ALTER TABLE academic_staff ADD COLUMN title VARCHAR(120)"))
            db.session.commit()
        potential_columns = {
            row[1] for row in db.session.execute(text("PRAGMA table_info(potential_entry)"))
        }
        if potential_columns and "interview" not in potential_columns:
            db.session.execute(text("ALTER TABLE potential_entry ADD COLUMN interview TEXT"))
            db.session.commit()
        if potential_columns and "is_rejected" not in potential_columns:
            db.session.execute(text("ALTER TABLE potential_entry ADD COLUMN is_rejected BOOLEAN NOT NULL DEFAULT 0"))
            db.session.commit()
        if potential_columns and "rejected_on" not in potential_columns:
            db.session.execute(text("ALTER TABLE potential_entry ADD COLUMN rejected_on DATETIME"))
            db.session.commit()
        if potential_columns and "interview_date" not in potential_columns:
            db.session.execute(text("ALTER TABLE potential_entry ADD COLUMN interview_date VARCHAR(10)"))
            db.session.commit()
        if potential_columns and "interview_time" not in potential_columns:
            db.session.execute(text("ALTER TABLE potential_entry ADD COLUMN interview_time VARCHAR(8)"))
            db.session.commit()
        if potential_columns and "platform" not in potential_columns:
            db.session.execute(text("ALTER TABLE potential_entry ADD COLUMN platform VARCHAR(20)"))
            db.session.commit()
        if potential_columns and "interviewer" not in potential_columns:
            db.session.execute(text("ALTER TABLE potential_entry ADD COLUMN interviewer VARCHAR(220)"))
            db.session.commit()
        exam_session_columns = {
            row[1] for row in db.session.execute(text("PRAGMA table_info(exam_session)"))
        }
        if exam_session_columns and "exam_session_name" not in exam_session_columns:
            db.session.execute(
                text("ALTER TABLE exam_session ADD COLUMN exam_session_name VARCHAR(160) NOT NULL DEFAULT 'Untitled exam session'")
            )
            db.session.commit()
        if exam_session_columns and "category" not in exam_session_columns:
            db.session.execute(text("ALTER TABLE exam_session ADD COLUMN category VARCHAR(80) NOT NULL DEFAULT ''"))
            if "exam_centre_type" in exam_session_columns:
                db.session.execute(text("UPDATE exam_session SET category = exam_centre_type WHERE category = ''"))
            db.session.commit()
        if exam_session_columns and "rsg_enabled" not in exam_session_columns:
            db.session.execute(text("ALTER TABLE exam_session ADD COLUMN rsg_enabled BOOLEAN NOT NULL DEFAULT 0"))
            db.session.commit()
        if exam_session_columns and "pen_enabled" not in exam_session_columns:
            db.session.execute(text("ALTER TABLE exam_session ADD COLUMN pen_enabled BOOLEAN NOT NULL DEFAULT 0"))
            db.session.commit()
        if exam_session_columns and "pst_enabled" not in exam_session_columns:
            db.session.execute(text("ALTER TABLE exam_session ADD COLUMN pst_enabled BOOLEAN NOT NULL DEFAULT 0"))
            db.session.commit()
        if exam_session_columns and "rsg_enabled" in exam_session_columns:
            db.session.execute(text("UPDATE exam_session SET rsg_enabled = 0 WHERE format = 'Online' AND rsg_enabled = 1"))
            db.session.commit()
        if exam_session_columns and "full_address_google_maps" not in exam_session_columns:
            db.session.execute(text("ALTER TABLE exam_session ADD COLUMN full_address_google_maps VARCHAR(500)"))
            db.session.commit()
        if exam_session_columns and "city" not in exam_session_columns:
            db.session.execute(text("ALTER TABLE exam_session ADD COLUMN city VARCHAR(120)"))
            db.session.commit()
        if exam_session_columns and "province" not in exam_session_columns:
            db.session.execute(text("ALTER TABLE exam_session ADD COLUMN province VARCHAR(120)"))
            db.session.commit()
        if exam_session_columns and "shifts" not in exam_session_columns:
            db.session.execute(text("ALTER TABLE exam_session ADD COLUMN shifts VARCHAR(80) NOT NULL DEFAULT ''"))
            db.session.commit()
        if exam_session_columns and "status" in exam_session_columns:
            db.session.execute(text("UPDATE exam_session SET status = 'Pending' WHERE status IN ('Active', 'Inactive')"))
            db.session.commit()
        supervisor_assignment_columns = {
            row[1] for row in db.session.execute(text("PRAGMA table_info(exam_session_supervisor_assignment)"))
        }
        if supervisor_assignment_columns and "participation_status" in supervisor_assignment_columns:
            db.session.execute(
                text("UPDATE exam_session_supervisor_assignment SET participation_status = 'Pre-confirmation sent' WHERE participation_status = 'Sent'")
            )
            db.session.commit()
        if supervisor_assignment_columns and "km" not in supervisor_assignment_columns:
            db.session.execute(text("ALTER TABLE exam_session_supervisor_assignment ADD COLUMN km INTEGER"))
            db.session.commit()
        if supervisor_assignment_columns and "start_time" not in supervisor_assignment_columns:
            db.session.execute(text("ALTER TABLE exam_session_supervisor_assignment ADD COLUMN start_time VARCHAR(5)"))
            db.session.commit()
        if supervisor_assignment_columns and "end_time" not in supervisor_assignment_columns:
            db.session.execute(text("ALTER TABLE exam_session_supervisor_assignment ADD COLUMN end_time VARCHAR(5)"))
            db.session.commit()
        if supervisor_assignment_columns and "time_ranges" not in supervisor_assignment_columns:
            db.session.execute(text("ALTER TABLE exam_session_supervisor_assignment ADD COLUMN time_ranges TEXT"))
            db.session.commit()
        for column_name in ("role_fee", "device_dep", "commuting", "fuel", "vehicle_dep", "seniority_fee"):
            if supervisor_assignment_columns and column_name not in supervisor_assignment_columns:
                db.session.execute(text(f"ALTER TABLE exam_session_supervisor_assignment ADD COLUMN {column_name} VARCHAR(80)"))
                db.session.commit()
        supervisor_fee_columns = {
            "role_fee_currency": "VARCHAR(3)",
            "role_fee_base_value": "VARCHAR(40)",
            "role_fee_unit": "VARCHAR(30)",
            "role_fee_last_calculated_on": "DATETIME",
            "role_fee_last_recalculated_on": "DATETIME",
        }
        for column_name, column_type in supervisor_fee_columns.items():
            if supervisor_assignment_columns and column_name not in supervisor_assignment_columns:
                db.session.execute(text(f"ALTER TABLE exam_session_supervisor_assignment ADD COLUMN {column_name} {column_type}"))
                db.session.commit()
        examiner_assignment_columns = {
            row[1] for row in db.session.execute(text("PRAGMA table_info(exam_session_examiner_assignment)"))
        }
        if examiner_assignment_columns and "participation_status" in examiner_assignment_columns:
            db.session.execute(
                text("UPDATE exam_session_examiner_assignment SET participation_status = 'Pre-confirmation sent' WHERE participation_status = 'Sent'")
            )
            db.session.commit()
        for column_name, column_type in supervisor_fee_columns.items():
            if examiner_assignment_columns and column_name not in examiner_assignment_columns:
                db.session.execute(text(f"ALTER TABLE exam_session_examiner_assignment ADD COLUMN {column_name} {column_type}"))
                db.session.commit()
        intern_assignment_columns = {
            row[1] for row in db.session.execute(text("PRAGMA table_info(exam_session_intern_assignment)"))
        }
        if intern_assignment_columns and "participation_status" in intern_assignment_columns:
            db.session.execute(
                text("UPDATE exam_session_intern_assignment SET participation_status = 'Pre-confirmation sent' WHERE participation_status = 'Sent'")
            )
            db.session.commit()
        for column_name, column_type in supervisor_fee_columns.items():
            if intern_assignment_columns and column_name not in intern_assignment_columns:
                db.session.execute(text(f"ALTER TABLE exam_session_intern_assignment ADD COLUMN {column_name} {column_type}"))
                db.session.commit()
        device_dep_columns = {
            "logistics_enabled": "BOOLEAN DEFAULT 0 NOT NULL",
            "manual_fee_override": "BOOLEAN DEFAULT 0 NOT NULL",
            "device_dep_currency": "VARCHAR(3)",
            "device_dep_base_value": "VARCHAR(40)",
            "device_dep_unit": "VARCHAR(30)",
            "device_dep_last_calculated_on": "DATETIME",
            "device_dep_last_recalculated_on": "DATETIME",
            "commuting_currency": "VARCHAR(3)",
            "commuting_base_value": "VARCHAR(40)",
            "commuting_unit": "VARCHAR(30)",
            "commuting_last_calculated_on": "DATETIME",
            "commuting_last_recalculated_on": "DATETIME",
            "fuel_enabled": "BOOLEAN DEFAULT 0 NOT NULL",
            "fuel_currency": "VARCHAR(3)",
            "fuel_base_value": "VARCHAR(40)",
            "fuel_unit": "VARCHAR(30)",
            "fuel_last_calculated_on": "DATETIME",
            "fuel_last_recalculated_on": "DATETIME",
            "vehicle_dep_currency": "VARCHAR(3)",
            "vehicle_dep_base_value": "VARCHAR(40)",
            "vehicle_dep_unit": "VARCHAR(30)",
            "vehicle_dep_last_calculated_on": "DATETIME",
            "vehicle_dep_last_recalculated_on": "DATETIME",
            "seniority_applied": "BOOLEAN DEFAULT 0 NOT NULL",
            "seniority_percentage": "VARCHAR(10)",
            "seniority_currency": "VARCHAR(3)",
            "seniority_last_calculated_on": "DATETIME",
            "seniority_last_recalculated_on": "DATETIME",
            "fee_frozen_on": "DATETIME",
            "fee_frozen_status": "VARCHAR(20)",
            "logistics_type": "VARCHAR(40) DEFAULT 'Does not apply' NOT NULL",
        }
        assignment_tables = (
            "exam_session_supervisor_assignment",
            "exam_session_examiner_assignment",
            "exam_session_intern_assignment",
        )
        for table_name in assignment_tables:
            table_columns = {
                row[1] for row in db.session.execute(text(f"PRAGMA table_info({table_name})"))
            }
            for column_name, column_type in device_dep_columns.items():
                if table_columns and column_name not in table_columns:
                    db.session.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}"))
                    db.session.commit()
                    table_columns.add(column_name)
            if table_columns and "logistics_type" in table_columns and "logistics_enabled" in table_columns:
                db.session.execute(
                    text(
                        f"UPDATE {table_name} "
                        "SET logistics_type = 'Simple logistics' "
                        "WHERE logistics_enabled = 1 "
                        "AND (logistics_type IS NULL OR logistics_type = '' OR logistics_type = 'Does not apply')"
                    )
                )
                db.session.commit()
        logistics_concept_columns = {
            row[1] for row in db.session.execute(text("PRAGMA table_info(exam_session_logistics_concept)"))
        }
        if logistics_concept_columns and "provider_id" not in logistics_concept_columns:
            db.session.execute(text("ALTER TABLE exam_session_logistics_concept ADD COLUMN provider_id INTEGER"))
            db.session.commit()
        provider_columns = {
            row[1] for row in db.session.execute(text("PRAGMA table_info(provider)"))
        }
        if provider_columns and "available_in_logistics" not in provider_columns:
            db.session.execute(text("ALTER TABLE provider ADD COLUMN available_in_logistics BOOLEAN NOT NULL DEFAULT 1"))
            db.session.commit()
        if not ExaminerCertificationYear.query.filter_by(year=2026).first():
            db.session.add(ExaminerCertificationYear(year=2026, is_archived=False))
            db.session.commit()
        if not SupervisorCertificationYear.query.filter_by(year=2026).first():
            db.session.add(SupervisorCertificationYear(year=2026, is_archived=False))
            db.session.commit()
        if not InternStageYear.query.filter_by(year=2026).first():
            db.session.add(InternStageYear(year=2026, is_archived=False))
            db.session.commit()
        if not ExamSessionYear.query.filter_by(year=2026).first():
            db.session.add(ExamSessionYear(year=2026, is_archived=False))
            db.session.commit()
        for role_name in ("Examiner", "RSG", "Supervisor", "Intern"):
            if not Role.query.filter_by(name=role_name).first():
                db.session.add(Role(name=role_name))
        db.session.commit()
        provider_type_names = [
            "Hotel",
            "AirBnb",
            "Booking.com",
            "Airline",
            "Bus",
            "BusBud",
            "BusPlus",
            "Car rental",
            "Restaurant",
        ]
        provider_type_colors = [f"provider-type-{index}" for index in range(12)]
        for index, type_name in enumerate(provider_type_names):
            existing_type = ProviderType.query.filter(db.func.lower(ProviderType.name) == type_name.lower()).first()
            if existing_type:
                existing_type.is_system = True
                if not existing_type.color_key:
                    existing_type.color_key = provider_type_colors[index % len(provider_type_colors)]
            else:
                db.session.add(
                    ProviderType(
                        name=type_name,
                        is_system=True,
                        color_key=provider_type_colors[index % len(provider_type_colors)],
                    )
                )
        db.session.commit()
        if StaffCertificationFutSelection.query.count() and not ExaminerCertificationFut1Selection.query.filter_by(year=2026).first():
            for selection in StaffCertificationFutSelection.query.all():
                db.session.add(
                    ExaminerCertificationFut1Selection(
                        member_id=selection.member_id,
                        option_name=selection.option_name,
                        status=selection.status,
                        year=2026,
                    )
                )
            db.session.commit()
        if StaffCertificationFut2Selection.query.count() and not ExaminerCertificationFut2Selection.query.filter_by(year=2026).first():
            for selection in StaffCertificationFut2Selection.query.all():
                db.session.add(
                    ExaminerCertificationFut2Selection(
                        member_id=selection.member_id,
                        option_name=selection.option_name,
                        status=selection.status,
                        year=2026,
                    )
                )
            db.session.commit()
        legacy_remote_training = ExaminerCertificationRemoteTrainingSelection.query.filter_by(status="Not initiated").all()
        if legacy_remote_training:
            for selection in legacy_remote_training:
                selection.status = "Pending"
            db.session.commit()
        for user in User.query.all():
            existing_permission_keys = {permission.menu_key for permission in user.menu_permissions}
            for menu_key in set(VALID_MENU_PERMISSION_KEYS) - existing_permission_keys:
                db.session.add(
                    UserMenuPermission(
                        user_id=user.id,
                        menu_key=menu_key,
                        can_view=True,
                        can_edit=True,
                    )
                )
        db.session.flush()
        users_edit_user_ids = {
            permission.user_id
            for permission in UserMenuPermission.query.filter_by(menu_key="users", can_edit=True).all()
        }
        if users_edit_user_ids:
            UserMenuPermission.query.filter(
                UserMenuPermission.user_id.in_(users_edit_user_ids)
            ).update(
                {UserMenuPermission.can_manage_permissions: True},
                synchronize_session=False,
            )
        active_superadmins = User.query.filter_by(is_superadmin=True, is_active=True).order_by(User.id.asc()).all()
        if active_superadmins:
            primary_superadmin = active_superadmins[0]
            if len(active_superadmins) > 1:
                for extra_superadmin in active_superadmins[1:]:
                    extra_superadmin.is_superadmin = False
        else:
            primary_superadmin = (
                User.query.filter_by(is_active=True, department="Admin").order_by(User.id.asc()).first()
                or User.query.filter_by(is_active=True).order_by(User.id.asc()).first()
                or User.query.order_by(User.id.asc()).first()
            )
            if primary_superadmin:
                primary_superadmin.is_superadmin = True
        deployed_superadmin = User.query.filter_by(email=DEPLOY_SUPERADMIN_EMAIL).first()
        if deployed_superadmin:
            deployed_superadmin.is_active = True
            deployed_superadmin.is_superadmin = True
            User.query.filter(User.id != deployed_superadmin.id).update(
                {User.is_superadmin: False},
                synchronize_session=False,
            )
        db.session.commit()
    return app


def login_required(view):
    @wraps(view)
    def wrapped_view(**kwargs):
        if not g.user:
            return redirect(url_for("login"))
        return view(**kwargs)

    return wrapped_view


def validate_csrf():
    token = request.form.get("csrf_token")
    return token and token == session.get("csrf_token")
