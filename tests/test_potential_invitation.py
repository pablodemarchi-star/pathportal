import json
import os
import subprocess
import unittest
from datetime import date, datetime, time, timezone

os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from app import create_app, db
from app.models import (
    AcademicStaff,
    ExamSession,
    ExamSessionExaminerAssignment,
    ExamSessionInternAssignment,
    ExamSessionShipmentBundle,
    ExamSessionShipmentBundleSession,
    ExamSessionShipmentChecklistItem,
    ExamSessionShipmentEvent,
    ExamSessionSupervisorAssignment,
    PotentialEntry,
    PotentialEntryStatusTrack,
    StaffPayment,
    StaffMembersSettings,
    User,
    UserMenuPermission,
)


class PotentialInvitationTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config["TESTING"] = True
        self.ctx = self.app.app_context()
        self.ctx.push()
        db.drop_all()
        db.create_all()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def client(self):
        client = self.app.test_client()
        with client.session_transaction() as user_session:
            user_session["user"] = "admin"
            user_session["user_department"] = "Admin"
            user_session["csrf_token"] = "token"
        return client

    def permission_client(self, *, can_view=True, can_edit=False, department="Admissions"):
        user = User(full_name="Permission User", email="permission@example.com", department=department, is_active=True)
        user.set_password("secret123")
        db.session.add(user)
        db.session.flush()
        db.session.add(
            UserMenuPermission(
                user_id=user.id,
                menu_key="staff_members",
                can_view=can_view or can_edit,
                can_edit=can_edit,
            )
        )
        db.session.commit()
        client = self.app.test_client()
        with client.session_transaction() as user_session:
            user_session["user"] = user.full_name
            user_session["user_id"] = user.id
            user_session["user_full_name"] = user.full_name
            user_session["user_email"] = user.email
            user_session["user_department"] = user.department
            user_session["csrf_token"] = "token"
        return client, user

    def add_entry(self, **overrides):
        values = {
            "status": "Interview invitation sent",
            "full_name": "Jane Candidate",
            "email": "jane@example.com",
            "interview_date": "2026-07-02",
            "interview_time": "10:00:00",
            "platform": "Zoom",
            "interviewer": "Prof. Mgter. Pablo Demarchi",
        }
        values.update(overrides)
        entry = PotentialEntry(**values)
        db.session.add(entry)
        db.session.commit()
        return entry

    def add_member(self, **overrides):
        values = {
            "status": "Active",
            "title": "Prof.",
            "full_name": "Jane Staff",
            "roles": "Examiner",
            "phone": "555-000",
            "email": "jane.staff@example.com",
            "has_car": "Yes",
            "started_in": "2026",
            "full_address_google_maps": "742 Evergreen Terrace",
            "city": "CABA",
            "province": "Buenos Aires",
            "country": "Argentina",
            "cv": "https://example.com/cv.pdf",
            "account_id": "ACC-1",
            "account_owner": "Path",
            "profile_picture": "https://example.com/profile.jpg",
        }
        values.update(overrides)
        member = AcademicStaff(**values)
        db.session.add(member)
        db.session.commit()
        return member

    def build_successful_application_email(self, dataset):
        with open("app/static/js/app.js", encoding="utf-8") as handle:
            js = handle.read()
        start = js.index("const cleanEmailValue")
        end = js.index("const buildUnsuccessfulApplicationEmail")
        script = (
            js[start:end]
            + "\nconst button = { dataset: "
            + json.dumps(dataset)
            + " };\nconsole.log(JSON.stringify(buildSuccessfulApplicationEmail(button)));\n"
        )
        result = subprocess.run(["node", "-e", script], check=True, capture_output=True, text=True)
        return json.loads(result.stdout)

    def build_interview_invitation_email(self, dataset):
        with open("app/static/js/app.js", encoding="utf-8") as handle:
            js = handle.read()
        start = js.index("const cleanEmailValue")
        end = js.index("const buildUnsuccessfulApplicationEmail")
        script = (
            js[start:end]
            + "\nconst root = { dataset: "
            + json.dumps(dataset)
            + " };\nconst button = { closest: () => root };\n"
            + "const payload = buildInterviewInvitationEmail(button);\n"
            + "const gmailUrl = payload.error ? '' : buildInterviewInvitationGmailUrl(payload);\n"
            + "console.log(JSON.stringify({ payload, gmailUrl }));\n"
        )
        result = subprocess.run(["node", "-e", script], check=True, capture_output=True, text=True)
        return json.loads(result.stdout)

    def build_entry_accepted_email(self, dataset, require_email=False):
        with open("app/static/js/app.js", encoding="utf-8") as handle:
            js = handle.read()
        start = js.index("const cleanEmailValue")
        end = js.index("const roleLabelForSection")
        script = (
            js[start:end]
            + "\nconst root = { dataset: "
            + json.dumps(dataset)
            + " };\nconst button = { closest: () => root };\n"
            + f"const payload = buildEntryAcceptedApplicationEmail(button, {str(require_email).lower()});\n"
            + "const gmailUrl = payload.error ? '' : buildEntryAcceptedGmailUrl(payload);\n"
            + "console.log(JSON.stringify({ payload, gmailUrl }));\n"
        )
        result = subprocess.run(["node", "-e", script], check=True, capture_output=True, text=True)
        return json.loads(result.stdout)

    def build_entry_accepted_whatsapp_message(self, dataset):
        with open("app/static/js/app.js", encoding="utf-8") as handle:
            js = handle.read()
        start = js.index("const cleanEmailValue")
        end = js.index("const roleLabelForSection")
        script = (
            js[start:end]
            + "\nconst root = { dataset: "
            + json.dumps(dataset)
            + " };\nconst button = { closest: () => root };\n"
            + "console.log(JSON.stringify(buildEntryAcceptedWhatsAppMessage(button)));\n"
        )
        result = subprocess.run(["node", "-e", script], check=True, capture_output=True, text=True)
        return json.loads(result.stdout)

    def add_session(self, **overrides):
        values = {
            "exam_session_name": "Future session",
            "category": "Exam",
            "status": "Draft",
            "session_date": date(2026, 7, 20),
            "shifts": "AM",
            "modules": "Speaking",
            "format": "Online",
        }
        values.update(overrides)
        session_record = ExamSession(**values)
        db.session.add(session_record)
        db.session.commit()
        return session_record

    def test_interview_invitation_sent_entry_shows_follow_up_action(self):
        entry = self.add_entry()
        response = self.client().get("/potential-entries")
        html = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(entry.interview_invitation_sent)
        self.assertIn('data-potential-gmail-email="jane@example.com"', html)
        self.assertIn("Open Gmail compose", html)
        self.assertIn("Follow up invitation to confirm or cancel interview", html)
        self.assertIn("<span class=\"responsible-chip users-department-chip\">ADMIN</span>", html)
        self.assertNotIn("Email invitation", html)
        self.assertNotIn("data-copy-potential-invitation", html)
        self.assertNotIn("data-invitation-sent-action", html)
        self.assertNotIn("Accept email", html)
        self.assertNotIn("Reject email", html)
        self.assertNotIn("data-zoom-link", html)
        self.assertNotIn("data-zoom-id", html)
        self.assertNotIn("data-zoom-password", html)
        self.assertNotIn("data-meet-link", html)

    def test_non_arranged_entry_does_not_show_email_invitation_button(self):
        self.add_entry(status="Interview to be arranged", platform="", interview_date="", interview_time="")
        response = self.client().get("/potential-entries")
        html = response.get_data(as_text=True)
        self.assertNotIn("Email invitation", html)
        self.assertNotIn("data-copy-potential-invitation", html)
        self.assertNotIn("Accept email", html)
        self.assertNotIn("Reject email", html)

    def test_potential_entry_missing_contact_details_show_recorded_messages(self):
        self.add_entry(email="", phone="", city="", province="", cv="")
        response = self.client().get("/potential-entries")
        html = response.get_data(as_text=True)
        self.assertIn("No email recorded", html)
        self.assertIn("No phone recorded", html)
        self.assertIn("No city or province recorded", html)
        self.assertIn("No CV recorded", html)
        self.assertNotIn("data-potential-gmail-email", html)

    def test_potential_entry_city_and_province_render_in_table_columns(self):
        self.add_entry(city="Moreno", province="Pumbis")
        response = self.client().get("/potential-entries")
        html = response.get_data(as_text=True)
        self.assertIn('href="/potential-entries?sort=city&amp;dir=asc"', html)
        self.assertIn('href="/potential-entries?sort=province&amp;dir=asc"', html)
        self.assertIn("<td>Moreno</td>", html)
        self.assertIn("<td>Pumbis</td>", html)

    def test_potential_entry_table_derives_department_and_action_from_status(self):
        cases = [
            ("CV to be reviewed", "MANAGEMENT", "Review CV for Admin to arrange interview"),
            ("Review interview date and time", "MANAGEMENT", "Review date and time options for initial interview"),
            ("Interview to be arranged", "ADMIN", "Send interview invitation to potential entry"),
            ("Interview invitation sent", "ADMIN", "Follow up invitation to confirm or cancel interview"),
            ("Interview confirmed", "MANAGEMENT", "Hold meeting with potential entry"),
            ("Entry accepted", "ADMIN", "Check notes and send successful application email to potential entry"),
            ("Onboarding email sent", "ADMIN", "Follow up onboarding email to confirm or turn down application"),
            ("Induction confirmed", "ADMIN", "Follow up on induction session status to finalise onboarding process"),
            ("Onboarding finalised", "-", "Onboarding process finalised"),
        ]
        for index, (status, _department, _action) in enumerate(cases, start=1):
            self.add_entry(
                status=status,
                full_name=f"Candidate {index}",
                email=f"candidate{index}@example.com",
            )

        response = self.client().get("/potential-entries")
        html = response.get_data(as_text=True)

        for _status, department, action in cases:
            if department == "-":
                self.assertIn('<span class="muted">-</span>', html)
            else:
                self.assertIn(f'<span class="responsible-chip users-department-chip">{department}</span>', html)
            self.assertIn(action, html)

    def test_potential_entry_create_does_not_create_status_track(self):
        self.client().post(
            "/potential-entries",
            data={
                "csrf_token": "token",
                "status": "CV to be reviewed",
                "full_name": "Trackless Candidate",
                "email": "trackless@example.com",
                "phone": "",
                "city": "",
                "province": "",
                "cv": "",
                "interview_date": "",
                "interview_time": "",
                "platform": "",
                "interviewer": "",
            },
        )

        self.assertEqual(PotentialEntry.query.count(), 1)
        self.assertEqual(PotentialEntryStatusTrack.query.count(), 0)

    def test_potential_entry_status_update_creates_track_with_user_department(self):
        client, user = self.permission_client(can_edit=True, department="Admissions")
        entry = self.add_entry(status="CV to be reviewed", full_name="Tracked Candidate", email="tracked@example.com")

        response = client.post(
            f"/potential-entries/{entry.id}",
            data={
                "csrf_token": "token",
                "status": "Entry accepted",
                "full_name": "Tracked Candidate",
                "phone": "",
                "email": "tracked@example.com",
                "city": "",
                "province": "",
                "cv": "",
                "interview_date": "",
                "interview_time": "",
                "platform": "",
                "interviewer": "",
            },
            follow_redirects=True,
        )
        track = PotentialEntryStatusTrack.query.one()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(track.potential_entry_id, entry.id)
        self.assertEqual(track.previous_status, "CV to be reviewed")
        self.assertEqual(track.new_status, "Entry accepted")
        self.assertIsNotNone(track.changed_at)
        self.assertEqual(track.changed_by_department, "ADMISSIONS")
        self.assertEqual(track.changed_by_user_id, user.id)

    def test_potential_entry_save_without_status_change_does_not_create_track(self):
        entry = self.add_entry(status="CV to be reviewed", full_name="No Track Candidate", email="notrack@example.com")

        self.client().post(
            f"/potential-entries/{entry.id}",
            data={
                "csrf_token": "token",
                "status": "CV to be reviewed",
                "full_name": "No Track Candidate Updated",
                "phone": "",
                "email": "notrack@example.com",
                "city": "",
                "province": "",
                "cv": "",
                "interview_date": "",
                "interview_time": "",
                "platform": "",
                "interviewer": "",
            },
        )

        self.assertEqual(PotentialEntryStatusTrack.query.count(), 0)

    def test_potential_status_track_renders_in_perform_action_modal_and_empty_state(self):
        entry = self.add_entry(status="CV to be reviewed", full_name="Modal Track Candidate")
        db.session.add(
            PotentialEntryStatusTrack(
                potential_entry_id=entry.id,
                previous_status="CV to be reviewed",
                new_status="Interview to be arranged",
                changed_at=datetime(2026, 10, 20, 13, 24, tzinfo=timezone.utc),
                changed_by_department="ADMIN",
            )
        )
        db.session.commit()

        html = self.client().get("/potential-entries").get_data(as_text=True)
        track_fragment = html[html.index("CV to be reviewed → Interview to be arranged") - 300:]
        track_fragment = track_fragment[: track_fragment.index("</section>")]

        self.assertIn("Status track", html)
        self.assertIn("CV to be reviewed → Interview to be arranged", html)
        self.assertIn("20/10/2026 · 10:24 am · ADMIN", html)
        self.assertNotIn("potential_entry_id", html)
        self.assertNotIn("undefined", track_fragment)
        self.assertNotIn("null", track_fragment)
        self.assertNotIn("None", track_fragment)

        empty_entry = self.add_entry(status="CV to be reviewed", full_name="Empty Track Candidate")
        empty_html = self.client().get("/potential-entries").get_data(as_text=True)
        self.assertIn(f'id="cv-review-potential-entry-{empty_entry.id}"', empty_html)
        self.assertIn("No status changes recorded yet.", empty_html)

    def test_status_track_renders_newest_first_and_get_does_not_create_track(self):
        entry = self.add_entry(status="CV to be reviewed")
        db.session.add_all([
            PotentialEntryStatusTrack(
                potential_entry_id=entry.id,
                previous_status="CV to be reviewed",
                new_status="Interview to be arranged",
                changed_at=datetime(2026, 10, 18, 12, 15, tzinfo=timezone.utc),
                changed_by_department="ADMISSIONS",
            ),
            PotentialEntryStatusTrack(
                potential_entry_id=entry.id,
                previous_status="Interview to be arranged",
                new_status="Interview invitation sent",
                changed_at=datetime(2026, 10, 20, 13, 24, tzinfo=timezone.utc),
                changed_by_department="ADMIN",
            ),
        ])
        db.session.commit()

        html = self.client().get("/potential-entries").get_data(as_text=True)
        self.client().get("/potential-entries")

        self.assertLess(
            html.index("Interview to be arranged → Interview invitation sent"),
            html.index("CV to be reviewed → Interview to be arranged"),
        )
        self.assertEqual(PotentialEntryStatusTrack.query.count(), 2)

    def test_status_changing_actions_create_track_and_note_actions_do_not(self):
        entry = self.add_entry(status="CV to be reviewed")
        response = self.client().post(
            f"/potential-entries/{entry.id}/cv-review/proceed",
            data={
                "csrf_token": "token",
                "cv_review_notes": "",
                "cv_review_note_department": "",
                "interview_option_date": "31/12/2099",
                "interview_option_time": "10:00",
                "interview_option_platform": "Zoom",
                "interview_option_interviewer": "Prof. Mgter. Pablo Demarchi",
            },
            follow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)
        track = PotentialEntryStatusTrack.query.one()
        self.assertEqual(track.previous_status, "CV to be reviewed")
        self.assertEqual(track.new_status, "Interview to be arranged")

        self.client().post(
            f"/potential-entries/{entry.id}/cv-review/add-note",
            data={"csrf_token": "token", "cv_review_notes": "Follow-up note", "cv_review_note_department": "Admin"},
            follow_redirects=True,
        )
        self.assertEqual(PotentialEntryStatusTrack.query.count(), 1)

    def test_reject_action_creates_status_track_and_double_submit_does_not_duplicate(self):
        entry = self.add_entry(status="CV to be reviewed")

        self.client().post(
            f"/potential-entries/{entry.id}/cv-review/reject",
            data={"csrf_token": "token"},
            follow_redirects=True,
        )
        self.client().post(
            f"/potential-entries/{entry.id}/cv-review/reject",
            data={"csrf_token": "token"},
            follow_redirects=True,
        )

        track = PotentialEntryStatusTrack.query.one()
        self.assertEqual(track.previous_status, "CV to be reviewed")
        self.assertEqual(track.new_status, "Entry rejected")

    def test_view_only_user_can_see_status_track_but_cannot_create_it(self):
        client, _user = self.permission_client(can_view=True, can_edit=False, department="Finance")
        entry = self.add_entry(status="CV to be reviewed")
        db.session.add(
            PotentialEntryStatusTrack(
                potential_entry_id=entry.id,
                previous_status="CV to be reviewed",
                new_status="Interview to be arranged",
                changed_at=datetime(2026, 10, 20, 13, 24, tzinfo=timezone.utc),
                changed_by_department="FINANCE",
            )
        )
        db.session.commit()

        html = client.get("/potential-entries").get_data(as_text=True)
        response = client.post(
            f"/potential-entries/{entry.id}/cv-review/reject",
            data={"csrf_token": "token"},
            follow_redirects=False,
        )

        self.assertIn("Status track", html)
        self.assertIn("CV to be reviewed → Interview to be arranged", html)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(PotentialEntryStatusTrack.query.count(), 1)

    def test_onboarding_finalised_row_hides_department_and_action_button(self):
        entry = self.add_entry(status="Onboarding finalised", full_name="Finalised Candidate")
        response = self.client().get("/potential-entries")
        html = response.get_data(as_text=True)
        name_index = html.index("Finalised Candidate")
        row_start = html.rfind("<tr>", 0, name_index)
        row_html = html[row_start:]
        row_html = row_html[:row_html.index("</tr>")]

        self.assertEqual(response.status_code, 200)
        self.assertIn('<span class="badge potential-status-onboarding-finalised">Onboarding finalised</span>', row_html)
        self.assertGreaterEqual(row_html.count('<span class="muted">-</span>'), 3)
        self.assertIn("Onboarding process finalised", row_html)
        self.assertNotIn("Perform action", row_html)
        self.assertNotIn(f'data-open-modal="edit-potential-entry-{entry.id}"', row_html)

    def test_create_potential_entry_allows_onboarding_email_sent_status(self):
        response = self.client().post(
            "/potential-entries",
            data={
                "csrf_token": "token",
                "status": "Onboarding email sent",
                "full_name": "Onboarding Candidate",
                "phone": "",
                "email": "onboarding@example.com",
                "city": "",
                "province": "",
                "cv": "",
                "interview_date": "",
                "interview_time": "",
                "platform": "",
                "interviewer": "",
            },
            follow_redirects=True,
        )
        html = response.get_data(as_text=True)
        entry = PotentialEntry.query.filter_by(email="onboarding@example.com").first()

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("Status is required.", html)
        self.assertIsNotNone(entry)
        self.assertEqual(entry.status, "Onboarding email sent")
        self.assertIn("Onboarding email sent", html)
        self.assertIn("Follow up onboarding email to confirm or turn down application", html)

    def test_onboarding_email_sent_perform_action_shows_follow_up_modal(self):
        entry = self.add_entry(status="Onboarding email sent")
        response = self.client().get("/potential-entries")
        html = response.get_data(as_text=True)
        modal_html = html[html.index(f'id="interview-arrange-potential-entry-{entry.id}"'):]
        modal_html = modal_html[:modal_html.index(f'id="potential-note-{entry.id}"')]

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            f'<button class="mini-button potential-perform-action" type="button" data-open-modal="interview-arrange-potential-entry-{entry.id}">Perform action</button>',
            html,
        )
        self.assertIn("Notes", modal_html)
        self.assertIn('class="potential-cv-review-fields potential-interview-arrangement-fields"', modal_html)
        self.assertNotIn("Information for interview arrangement", modal_html)
        self.assertIn("Confirm application", modal_html)
        self.assertIn("Turn down application", modal_html)
        self.assertIn('class="onboarding-follow-up-wrap"', modal_html)
        self.assertLess(
            modal_html.index('class="cv-review-notes-box"'),
            modal_html.index('class="onboarding-follow-up-wrap"'),
        )
        self.assertIn('data-onboarding-follow-up', modal_html)
        self.assertIn('data-onboarding-panel="confirm"', modal_html)
        self.assertIn('data-onboarding-panel="turn_down"', modal_html)
        self.assertIn("Title *", modal_html)
        self.assertIn("Full address copied from Google Maps *", modal_html)
        self.assertIn("Country *", modal_html)
        self.assertIn("Profile picture *", modal_html)
        self.assertIn("Bank account number *", modal_html)
        self.assertIn("Bank account holder", modal_html)
        self.assertIn("full name *", modal_html)
        self.assertIn("ID *", modal_html)
        self.assertIn("Confirmed induction session date and time", modal_html)
        self.assertIn("Trainer", modal_html)
        self.assertIn("The Entry has been removed from all pre-assigned exam session participations.", modal_html)
        self.assertIn("The Trainer has been notified that the Entry will not attend the induction session.", modal_html)
        self.assertIn("Save and close", modal_html)
        self.assertIn('data-onboarding-turn-down-button', modal_html)
        self.assertIn('data-onboarding-confirm-button', modal_html)

    def test_onboarding_confirm_application_requires_required_fields(self):
        entry = self.add_entry(status="Onboarding email sent")
        response = self.client().post(
            f"/potential-entries/{entry.id}/onboarding/confirm",
            data={"csrf_token": "token", "onboarding_follow_up_choice": "confirm"},
            follow_redirects=True,
        )
        html = response.get_data(as_text=True)
        updated_entry = db.session.get(PotentialEntry, entry.id)

        self.assertEqual(response.status_code, 200)
        self.assertIn("Title is required.", html)
        self.assertEqual(updated_entry.status, "Onboarding email sent")

    def test_onboarding_confirm_application_rejects_past_induction_datetime(self):
        entry = self.add_entry(status="Onboarding email sent")
        response = self.client().post(
            f"/potential-entries/{entry.id}/onboarding/confirm",
            data={
                "csrf_token": "token",
                "onboarding_follow_up_choice": "confirm",
                "title": "Prof.",
                "full_address_google_maps": "https://maps.google.com/?q=Path",
                "country": "Argentina",
                "profile_picture": "https://example.com/profile.jpg",
                "account_id": "123456",
                "account_owner": "Jane Candidate",
                "account_owner_id": "ID-123",
                "interview_date": "2020-01-01",
                "interview_time": "10:30",
                "platform": "Zoom",
                "interviewer": "Prof. Brenda Sartori",
            },
            follow_redirects=True,
        )
        html = response.get_data(as_text=True)
        updated_entry = db.session.get(PotentialEntry, entry.id)

        self.assertEqual(response.status_code, 200)
        self.assertIn("Confirmed induction session date and time cannot be in the past.", html)
        self.assertEqual(updated_entry.status, "Onboarding email sent")

    def test_onboarding_confirm_application_saves_required_fields(self):
        entry = self.add_entry(status="Onboarding email sent")
        response = self.client().post(
            f"/potential-entries/{entry.id}/onboarding/confirm",
            data={
                "csrf_token": "token",
                "onboarding_follow_up_choice": "confirm",
                "title": "Prof.",
                "full_address_google_maps": "https://maps.google.com/?q=Path",
                "country": "Argentina",
                "profile_picture": "https://example.com/profile.jpg",
                "account_id": "123456",
                "account_owner": "Jane Candidate",
                "account_owner_id": "ID-123",
                "interview_date": "2026-08-10",
                "interview_time": "10:30",
                "platform": "Zoom",
                "interviewer": "Prof. Brenda Sartori",
            },
            follow_redirects=True,
        )
        html = response.get_data(as_text=True)
        updated_entry = db.session.get(PotentialEntry, entry.id)

        self.assertEqual(response.status_code, 200)
        self.assertIn("Induction confirmed.", html)
        self.assertEqual(updated_entry.status, "Induction confirmed")
        self.assertEqual(updated_entry.onboarding_follow_up_choice, "confirm")
        self.assertEqual(updated_entry.title, "Prof.")
        self.assertEqual(updated_entry.full_address_google_maps, "https://maps.google.com/?q=Path")
        self.assertEqual(updated_entry.country, "Argentina")
        self.assertEqual(updated_entry.profile_picture, "https://example.com/profile.jpg")
        self.assertEqual(updated_entry.account_id, "123456")
        self.assertEqual(updated_entry.account_owner, "Jane Candidate")
        self.assertEqual(updated_entry.account_owner_id, "ID-123")
        self.assertEqual(updated_entry.interview_date, "2026-08-10")
        self.assertEqual(updated_entry.interview_time, "10:30:00")
        self.assertEqual(updated_entry.platform, "Zoom")
        self.assertEqual(updated_entry.interviewer, "Prof. Brenda Sartori")

    def test_onboarding_turn_down_requires_both_checks(self):
        entry = self.add_entry(status="Onboarding email sent")
        response = self.client().post(
            f"/potential-entries/{entry.id}/onboarding/turn-down",
            data={
                "csrf_token": "token",
                "onboarding_follow_up_choice": "turn_down",
                "onboarding_turn_down_sessions_removed": "1",
            },
            follow_redirects=True,
        )
        html = response.get_data(as_text=True)
        updated_entry = db.session.get(PotentialEntry, entry.id)

        self.assertEqual(response.status_code, 200)
        self.assertIn("The Trainer has been notified that the Entry will not attend the induction session is required.", html)
        self.assertEqual(updated_entry.status, "Onboarding email sent")
        self.assertFalse(updated_entry.is_rejected)

    def test_onboarding_turn_down_marks_entry_rejected_when_checks_complete(self):
        entry = self.add_entry(status="Onboarding email sent")
        response = self.client().post(
            f"/potential-entries/{entry.id}/onboarding/turn-down",
            data={
                "csrf_token": "token",
                "onboarding_follow_up_choice": "turn_down",
                "onboarding_turn_down_sessions_removed": "1",
                "onboarding_turn_down_trainer_notified": "1",
            },
            follow_redirects=True,
        )
        html = response.get_data(as_text=True)
        updated_entry = db.session.get(PotentialEntry, entry.id)

        self.assertEqual(response.status_code, 200)
        self.assertIn("Application turned down.", html)
        self.assertEqual(updated_entry.status, "Entry rejected")
        self.assertTrue(updated_entry.is_rejected)
        self.assertTrue(updated_entry.onboarding_turn_down_sessions_removed)
        self.assertTrue(updated_entry.onboarding_turn_down_trainer_notified)

    def test_interview_confirmed_status_cell_shows_meeting_details(self):
        self.add_entry(
            status="Interview confirmed",
            interview_date="2026-08-10",
            interview_time="10:00:00",
            platform="Meet",
            interviewer="Prof. Lic. Agustina Savini | Team Leader",
        )
        response = self.client().get("/potential-entries")
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn('<span class="badge potential-status-interview-confirmed">Interview confirmed</span>', html)
        self.assertIn('class="potential-status-meta"', html)
        self.assertIn("10/08/2026 · 10:00", html)
        self.assertIn("google-meet.png", html)
        self.assertIn("Google Meet", html)
        self.assertIn("Prof. Lic. Agustina Savini", html)
        self.assertNotIn("Team Leader", html)

    def test_induction_confirmed_status_cell_shows_induction_details(self):
        self.add_entry(
            status="Induction confirmed",
            interview_date="2026-08-10",
            interview_time="10:30:00",
            platform="Zoom",
            interviewer="Prof. Brenda Sartori",
        )
        response = self.client().get("/potential-entries")
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn('<span class="badge potential-status-induction-confirmed">Induction confirmed</span>', html)
        self.assertIn('class="potential-status-meta"', html)
        self.assertIn("10/08/2026 · 10:30", html)
        self.assertIn("zoom.png", html)
        self.assertIn("Zoom", html)
        self.assertIn("Prof. Brenda Sartori", html)

    def test_induction_confirmed_perform_action_shows_induction_status_modal(self):
        entry = self.add_entry(
            status="Induction confirmed",
            cv_review_interview_options=json.dumps([
                {"date": "10/08/2026", "time": "10:00", "platform": "Zoom", "interviewer": "Prof. Brenda Sartori"},
            ]),
            interview_date="2026-08-10",
            interview_time="10:30:00",
            platform="Zoom",
            interviewer="Prof. Brenda Sartori",
        )
        response = self.client().get("/potential-entries")
        html = response.get_data(as_text=True)
        modal_html = html[html.index(f'id="interview-arrange-potential-entry-{entry.id}"'):]
        modal_html = modal_html[:modal_html.index(f'id="potential-note-{entry.id}"')]

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            f'<button class="mini-button potential-perform-action" type="button" data-open-modal="interview-arrange-potential-entry-{entry.id}">Perform action</button>',
            html,
        )
        self.assertIn("Potential entry review", modal_html)
        self.assertIn("Potential entry information", modal_html)
        self.assertIn("Notes", modal_html)
        self.assertIn("Induction session status", modal_html)
        self.assertIn('name="induction_session_status" value="no_show"', modal_html)
        self.assertIn(">No-show</span>", modal_html)
        self.assertIn('name="induction_session_status" value="reschedule"', modal_html)
        self.assertIn(">Reschedule</span>", modal_html)
        self.assertIn('name="induction_session_status" value="attended"', modal_html)
        self.assertIn(">Attended</span>", modal_html)
        self.assertIn('data-induction-status-panel="reschedule" hidden', modal_html)
        self.assertIn("Set new date and time", modal_html)
        self.assertIn('name="interview_option_date"', modal_html)
        self.assertIn('value="10/08/2026"', modal_html)
        self.assertIn('name="interview_option_time"', modal_html)
        self.assertIn('value="10:30"', modal_html)
        self.assertIn('name="interview_option_platform"', modal_html)
        self.assertIn('name="interview_option_interviewer"', modal_html)
        self.assertIn('data-induction-status-panel="attended" hidden', modal_html)
        self.assertIn("Exam session participation statuses have been updated to Pre-confirmed", modal_html)
        self.assertIn("The trainer has been notified of this change", modal_html)
        self.assertIn('name="induction_reschedule_trainer_notified"', modal_html)
        self.assertIn("Save and close", modal_html)
        self.assertIn('data-induction-reject-button', modal_html)
        self.assertIn(">Reject entry</button>", modal_html)
        self.assertIn('data-induction-reschedule-button', modal_html)
        self.assertIn(">Reschedule</button>", modal_html)
        self.assertIn('data-induction-activate-button', modal_html)
        self.assertIn(">Activate as Staff member</button>", modal_html)

    def test_induction_confirmed_reschedule_save_updates_meeting_details(self):
        entry = self.add_entry(
            status="Induction confirmed",
            interview_date="2026-08-10",
            interview_time="10:30:00",
            platform="Zoom",
            interviewer="Prof. Brenda Sartori",
            cv_review_interview_options=json.dumps([
                {"date": "10/08/2026", "time": "10:30", "platform": "Zoom", "interviewer": "Prof. Brenda Sartori"},
            ]),
        )
        response = self.client().post(
            f"/potential-entries/{entry.id}/cv-review/save",
            data={
                "csrf_token": "token",
                "induction_session_status": "reschedule",
                "interview_option_date": ["12/08/2026"],
                "interview_option_time": ["11:15"],
                "interview_option_platform": "Meet",
                "interview_option_interviewer": "Prof. Marcela Romero",
                "induction_reschedule_trainer_notified": "1",
            },
            follow_redirects=True,
        )
        html = response.get_data(as_text=True)
        updated_entry = db.session.get(PotentialEntry, entry.id)

        self.assertEqual(response.status_code, 200)
        self.assertIn("CV review saved.", html)
        self.assertEqual(updated_entry.status, "Induction confirmed")
        self.assertEqual(updated_entry.interview_date, "2026-08-12")
        self.assertEqual(updated_entry.interview_time, "11:15:00")
        self.assertEqual(updated_entry.platform, "Meet")
        self.assertEqual(updated_entry.interviewer, "Prof. Marcela Romero")
        self.assertEqual(json.loads(updated_entry.cv_review_interview_options), [
            {"date": "12/08/2026", "time": "11:15", "platform": "Meet", "interviewer": "Prof. Marcela Romero"},
        ])

    def test_induction_confirmed_reject_entry_marks_entry_rejected(self):
        entry = self.add_entry(status="Induction confirmed")
        response = self.client().post(
            f"/potential-entries/{entry.id}/induction/reject",
            data={
                "csrf_token": "token",
                "induction_session_status": "no_show",
            },
            follow_redirects=True,
        )
        html = response.get_data(as_text=True)
        updated_entry = db.session.get(PotentialEntry, entry.id)

        self.assertEqual(response.status_code, 200)
        self.assertIn("Entry rejected.", html)
        self.assertEqual(updated_entry.status, "Entry rejected")
        self.assertTrue(updated_entry.is_rejected)
        self.assertEqual(updated_entry.induction_session_status, "no_show")

    def test_induction_confirmed_reschedule_action_keeps_status(self):
        entry = self.add_entry(status="Induction confirmed")
        response = self.client().post(
            f"/potential-entries/{entry.id}/induction/reschedule",
            data={
                "csrf_token": "token",
                "induction_session_status": "reschedule",
                "interview_option_date": ["12/08/2026"],
                "interview_option_time": ["11:15"],
                "interview_option_platform": "Meet",
                "interview_option_interviewer": "Prof. Marcela Romero",
                "induction_reschedule_trainer_notified": "1",
            },
            follow_redirects=True,
        )
        html = response.get_data(as_text=True)
        updated_entry = db.session.get(PotentialEntry, entry.id)

        self.assertEqual(response.status_code, 200)
        self.assertIn("Induction rescheduled.", html)
        self.assertEqual(updated_entry.status, "Induction confirmed")
        self.assertEqual(updated_entry.induction_session_status, "reschedule")
        self.assertEqual(updated_entry.interview_date, "2026-08-12")
        self.assertEqual(updated_entry.interview_time, "11:15:00")
        self.assertEqual(updated_entry.platform, "Meet")
        self.assertEqual(updated_entry.interviewer, "Prof. Marcela Romero")

    def test_induction_confirmed_activate_as_staff_member_creates_active_member(self):
        entry = self.add_entry(
            status="Induction confirmed",
            title="Prof.",
            full_name="Final Candidate",
            phone="555-100",
            email="final@example.com",
            has_car="Yes",
            acceptance_roles="Examiner,RSG",
            full_address_google_maps="https://maps.google.com/?q=Path",
            city="CABA",
            province="Buenos Aires",
            country="Argentina",
            cv="https://example.com/cv.pdf",
            profile_picture="https://example.com/profile.jpg",
            account_id="ACC-123",
            account_owner="Final Candidate",
            interview="CV review - Admin: Ready.",
        )
        response = self.client().post(
            f"/potential-entries/{entry.id}/induction/activate",
            data={
                "csrf_token": "token",
                "induction_session_status": "attended",
                "exam_session_participation_statuses_pre_confirmed": "1",
            },
            follow_redirects=True,
        )
        html = response.get_data(as_text=True)
        updated_entry = db.session.get(PotentialEntry, entry.id)
        member = AcademicStaff.query.filter_by(email="final@example.com").first()

        self.assertEqual(response.status_code, 200)
        self.assertIn("Entry activated as Staff member.", html)
        self.assertEqual(updated_entry.status, "Onboarding finalised")
        self.assertEqual(updated_entry.induction_session_status, "attended")
        self.assertTrue(updated_entry.exam_session_participation_statuses_pre_confirmed)
        self.assertIsNotNone(member)
        self.assertEqual(member.status, "Active")
        self.assertEqual(member.full_name, "Final Candidate")
        self.assertEqual(member.roles, "Examiner,RSG")
        self.assertEqual(member.has_car, "Yes")
        self.assertEqual(member.started_in, "2026")
        self.assertEqual(member.full_address_google_maps, "https://maps.google.com/?q=Path")

    def test_cv_review_entry_perform_action_opens_review_modal(self):
        entry = self.add_entry(status="CV to be reviewed", cv="https://example.com/cv.pdf")
        response = self.client().get("/potential-entries")
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            f'<button class="mini-button potential-perform-action" type="button" data-open-modal="cv-review-potential-entry-{entry.id}">Perform action</button>',
            html,
        )
        self.assertIn('id="cv-review-potential-entry-', html)
        self.assertIn("Potential entry review", html)
        self.assertIn("Potential entry information", html)
        self.assertIn("<dt>Full name</dt>", html)
        self.assertIn("CV review", html)
        self.assertIn("Date and time options for interview", html)
        self.assertIn('name="interview_option_date"', html)
        self.assertIn('placeholder="DD/MM/YYYY"', html)
        self.assertIn('name="interview_option_time"', html)
        self.assertIn('placeholder="HH:mm"', html)
        self.assertIn('name="interview_option_platform"', html)
        self.assertIn('data-interview-option-platform-preview', html)
        self.assertIn('name="interview_option_interviewer"', html)
        self.assertIn("Prof. Lic. Agustina Savini", html)
        self.assertIn('aria-label="Add interview date and time option"', html)
        self.assertIn("+ Add option", html)
        self.assertIn('aria-label="Remove interview date and time option"', html)
        self.assertIn('data-remove-interview-option aria-label="Remove interview date and time option" title="Remove option" hidden', html)
        self.assertIn(">h.</span>", html)
        self.assertIn("Add internal notes about this application...", html)
        self.assertIn('data-edit-potential-info', html)
        self.assertIn('data-potential-info-edit hidden', html)
        self.assertIn('name="cv_review_note_department" required', html)
        self.assertIn('class="cv-review-notes-panel"', html)
        self.assertIn("<option value=\"Admin\"", html)
        self.assertIn("<option value=\"Admissions\"", html)
        self.assertIn("<option value=\"Finance\"", html)
        self.assertIn("<option value=\"Logistics\"", html)
        self.assertIn("<option value=\"Management\"", html)
        self.assertIn(">Add</button>", html)
        self.assertIn("Save and close", html)
        self.assertIn('class="success-button"', html)
        self.assertIn("data-proceed-interview-button", html)
        self.assertIn("formnovalidate\n                disabled\n              >Proceed to interview</button>", html)
        self.assertIn('data-close-modal>Cancel</button>', html)
        self.assertIn("Reject application", html)
        self.assertIn("Proceed to interview", html)
        self.assertIn("Are you sure you want to reject this application?", html)
        self.assertIn("Are you sure you want to proceed to interview?", html)
        self.assertIn(f'/potential-entries/{entry.id}/cv-review/add-note', html)
        self.assertIn(f'/potential-entries/{entry.id}/cv-review/save', html)
        self.assertIn(f'/potential-entries/{entry.id}/cv-review/reject', html)
        self.assertIn(f'/potential-entries/{entry.id}/cv-review/proceed', html)

    def test_interview_to_be_arranged_perform_action_opens_readonly_email_modal(self):
        entry = self.add_entry(
            status="Interview to be arranged",
            cv_review_interview_options=json.dumps([
                {"date": "13/08/2026", "time": "15:00", "platform": "Zoom", "interviewer": "Prof. Lic. Agustina Savini | Team Leader"},
                {"date": "10/08/2026", "time": "10:00", "platform": "Zoom", "interviewer": "Prof. Lic. Agustina Savini | Team Leader"},
                {"date": "", "time": "", "platform": "Zoom", "interviewer": "Prof. Lic. Agustina Savini | Team Leader"},
            ]),
            interviewer="",
        )
        response = self.client().get("/potential-entries")
        html = response.get_data(as_text=True)
        modal_html = html[html.index(f'id="interview-arrange-potential-entry-{entry.id}"'):]
        modal_html = modal_html[:modal_html.index(f'id="potential-note-{entry.id}"')]

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            f'<button class="mini-button potential-perform-action" type="button" data-open-modal="interview-arrange-potential-entry-{entry.id}">Perform action</button>',
            html,
        )
        self.assertIn("Potential entry review", modal_html)
        self.assertIn("Potential entry information", modal_html)
        self.assertIn("data-edit-potential-info", modal_html)
        self.assertIn("data-potential-info-edit hidden", modal_html)
        self.assertIn('name="full_name" value="Jane Candidate" required maxlength="160"', modal_html)
        self.assertIn("Information for interview arrangement", modal_html)
        self.assertIn('for="interview-arrange-notes-', modal_html)
        self.assertIn('name="cv_review_notes"', modal_html)
        self.assertIn('name="cv_review_note_department" required', modal_html)
        self.assertIn(">Add</button>", modal_html)
        self.assertNotIn("potential-readonly-history", modal_html)
        self.assertIn("Option 1", modal_html)
        self.assertIn("Monday 10 August 2026, 10:00", modal_html)
        self.assertIn("Option 2", modal_html)
        self.assertIn("Thursday 13 August 2026, 15:00", modal_html)
        self.assertLess(modal_html.index("Monday 10 August 2026, 10:00"), modal_html.index("Thursday 13 August 2026, 15:00"))
        self.assertNotIn("Option 3", modal_html)
        self.assertNotIn("2026-08-10", modal_html)
        self.assertNotIn("undefined", modal_html)
        self.assertNotIn("null", modal_html)
        self.assertNotIn("None", modal_html)
        self.assertNotIn('name="interview_option_date"', modal_html)
        self.assertNotIn('name="interview_option_time"', modal_html)
        self.assertNotIn("data-add-interview-option", modal_html)
        self.assertNotIn("data-remove-interview-option", modal_html)
        self.assertIn("Send email", modal_html)
        self.assertIn('data-interviewer="Prof. Lic. Agustina Savini"', modal_html)
        self.assertNotIn("Team Leader", modal_html)
        self.assertIn("data-send-interview-invitation-email", modal_html)
        self.assertIn("data-copy-interview-invitation-email", modal_html)
        self.assertIn('aria-label="Copy interview invitation email"', modal_html)
        self.assertIn('data-close-modal>Cancel</button>', modal_html)
        self.assertIn("Save and close", modal_html)
        self.assertIn("Mark it as Sent", modal_html)
        self.assertIn(f'/potential-entries/{entry.id}/cv-review/save', modal_html)
        self.assertIn(f'/potential-entries/{entry.id}/interview-invitation/mark-sent', modal_html)
        self.assertNotIn("Reject application", modal_html)
        self.assertNotIn("Proceed to interview", modal_html)

    def test_interview_to_be_arranged_add_note_preserves_options_and_status(self):
        options = [
            {"date": "10/08/2026", "time": "10:00", "platform": "Zoom", "interviewer": "Prof. Lic. Agustina Savini"},
        ]
        entry = self.add_entry(
            status="Interview to be arranged",
            interview="",
            cv_review_interview_options=json.dumps(options),
        )
        response = self.client().post(
            f"/potential-entries/{entry.id}/cv-review/add-note",
            data={
                "csrf_token": "token",
                "cv_review_notes": "Candidate asked for details before invitation.",
                "cv_review_note_department": "Admin",
            },
            follow_redirects=True,
        )
        html = response.get_data(as_text=True)
        updated_entry = db.session.get(PotentialEntry, entry.id)

        self.assertEqual(response.status_code, 200)
        self.assertIn("Note added.", html)
        self.assertIn(f'id="interview-arrange-potential-entry-{entry.id}" aria-hidden="false"', html)
        self.assertEqual(updated_entry.status, "Interview to be arranged")
        self.assertEqual(json.loads(updated_entry.cv_review_interview_options), options)
        self.assertIn("CV review - Admin: Candidate asked for details before invitation.", updated_entry.interview)

    def test_interview_to_be_arranged_mark_it_as_sent_updates_status_and_preserves_options(self):
        options = [
            {"date": "10/08/2026", "time": "10:00", "platform": "Zoom", "interviewer": "Prof. Lic. Agustina Savini"},
        ]
        entry = self.add_entry(
            status="Interview to be arranged",
            interview="",
            interview_invitation_sent=False,
            cv_review_interview_options=json.dumps(options),
        )
        response = self.client().post(
            f"/potential-entries/{entry.id}/interview-invitation/mark-sent",
            data={
                "csrf_token": "token",
                "cv_review_notes": "Invitation sent after confirming details.",
                "cv_review_note_department": "Admin",
            },
            follow_redirects=True,
        )
        html = response.get_data(as_text=True)
        updated_entry = db.session.get(PotentialEntry, entry.id)

        self.assertEqual(response.status_code, 200)
        self.assertIn("Interview invitation marked as sent.", html)
        self.assertEqual(updated_entry.status, "Interview invitation sent")
        self.assertTrue(updated_entry.interview_invitation_sent)
        self.assertEqual(json.loads(updated_entry.cv_review_interview_options), options)
        self.assertIn("CV review - Admin: Invitation sent after confirming details.", updated_entry.interview)

    def test_interview_invitation_sent_perform_action_opens_confirmation_modal(self):
        entry = self.add_entry(
            status="Interview invitation sent",
            cv_review_interview_options=json.dumps([
                {"date": "10/08/2026", "time": "10:00", "platform": "Zoom", "interviewer": "Prof. Lic. Agustina Savini"},
            ]),
        )
        response = self.client().get("/potential-entries")
        html = response.get_data(as_text=True)
        modal_html = html[html.index(f'id="interview-arrange-potential-entry-{entry.id}"'):]
        modal_html = modal_html[:modal_html.index(f'id="potential-note-{entry.id}"')]

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            f'<button class="mini-button potential-perform-action" type="button" data-open-modal="interview-arrange-potential-entry-{entry.id}">Perform action</button>',
            html,
        )
        self.assertIn("Interview invitation sent", modal_html)
        self.assertIn("Confirm the interview date and time", modal_html)
        self.assertIn("No reply", modal_html)
        self.assertIn('name="selected_interview_option"', modal_html)
        self.assertIn('data-interview-confirm-root', modal_html)
        self.assertIn('data-interview-no-reply', modal_html)
        self.assertIn('data-interview-option-choice', modal_html)
        self.assertIn("Monday 10 August 2026, 10:00", modal_html)
        self.assertIn("Cancel", modal_html)
        self.assertIn("Review date/time options", modal_html)
        self.assertIn("Turn down application", modal_html)
        self.assertIn("Interview confirmed", modal_html)
        self.assertIn(f'/potential-entries/{entry.id}/interview/review-date-time-options', modal_html)
        self.assertIn(f'/potential-entries/{entry.id}/interview/turn-down', modal_html)
        self.assertIn(f'/potential-entries/{entry.id}/interview/confirm', modal_html)
        self.assertNotIn("Mark it as Sent", modal_html)
        self.assertNotIn("Proceed to interview", modal_html)
        self.assertNotIn("Reject application", modal_html)

    def test_interview_invitation_sent_confirm_button_updates_status(self):
        options = [
            {"date": "10/08/2026", "time": "10:00", "platform": "Zoom", "interviewer": "Prof. Lic. Agustina Savini"},
        ]
        entry = self.add_entry(
            status="Interview invitation sent",
            interview="",
            cv_review_interview_options=json.dumps(options),
        )
        response = self.client().post(
            f"/potential-entries/{entry.id}/interview/confirm",
            data={
                "csrf_token": "token",
                "selected_interview_option": "0",
                "cv_review_notes": "Candidate confirmed interview date and time.",
                "cv_review_note_department": "Admin",
            },
            follow_redirects=True,
        )
        html = response.get_data(as_text=True)
        updated_entry = db.session.get(PotentialEntry, entry.id)

        self.assertEqual(response.status_code, 200)
        self.assertIn("Interview confirmed.", html)
        self.assertEqual(updated_entry.status, "Interview confirmed")
        self.assertEqual(updated_entry.interview_date, "2026-08-10")
        self.assertEqual(updated_entry.interview_time, "10:00:00")
        self.assertEqual(updated_entry.platform, "Zoom")
        self.assertEqual(updated_entry.interviewer, "Prof. Lic. Agustina Savini")
        self.assertEqual(json.loads(updated_entry.cv_review_interview_options), options)
        self.assertIn("CV review - Admin: Candidate confirmed interview date and time.", updated_entry.interview)

    def test_interview_invitation_sent_confirm_requires_selected_option(self):
        entry = self.add_entry(
            status="Interview invitation sent",
            cv_review_interview_options=json.dumps([
                {"date": "10/08/2026", "time": "10:00", "platform": "Zoom", "interviewer": "Prof. Lic. Agustina Savini"},
            ]),
        )
        response = self.client().post(
            f"/potential-entries/{entry.id}/interview/confirm",
            data={"csrf_token": "token"},
            follow_redirects=True,
        )
        html = response.get_data(as_text=True)
        updated_entry = db.session.get(PotentialEntry, entry.id)

        self.assertEqual(response.status_code, 200)
        self.assertIn("Select one interview date and time option before confirming the interview.", html)
        self.assertEqual(updated_entry.status, "Interview invitation sent")

    def test_interview_invitation_sent_no_reply_turns_down_application(self):
        entry = self.add_entry(status="Interview invitation sent")
        response = self.client().post(
            f"/potential-entries/{entry.id}/interview/turn-down",
            data={
                "csrf_token": "token",
                "interview_no_reply": "1",
            },
            follow_redirects=True,
        )
        html = response.get_data(as_text=True)
        updated_entry = db.session.get(PotentialEntry, entry.id)

        self.assertEqual(response.status_code, 200)
        self.assertIn("Application turned down.", html)
        self.assertEqual(updated_entry.status, "Entry rejected")
        self.assertTrue(updated_entry.is_rejected)

    def test_interview_invitation_sent_review_options_moves_to_review_status(self):
        entry = self.add_entry(status="Interview invitation sent")
        response = self.client().post(
            f"/potential-entries/{entry.id}/interview/review-date-time-options",
            data={"csrf_token": "token"},
            follow_redirects=True,
        )
        html = response.get_data(as_text=True)
        updated_entry = db.session.get(PotentialEntry, entry.id)

        self.assertEqual(response.status_code, 200)
        self.assertIn("Interview date/time options moved to review.", html)
        self.assertEqual(updated_entry.status, "Review interview date and time")
        self.assertIn("Review date and time options for initial interview", html)
        self.assertIn("Review interview date and time", html)

    def test_interview_confirmed_perform_action_shows_outcome_fields(self):
        entry = self.add_entry(
            status="Interview confirmed",
            has_car="Yes",
            acceptance_roles="Examiner,Other",
            interview_no_show=True,
            entry_added_in_sessions_pre_confirmation=True,
        )
        response = self.client().get("/potential-entries")
        html = response.get_data(as_text=True)
        modal_html = html[html.index(f'id="interview-arrange-potential-entry-{entry.id}"'):]
        modal_html = modal_html[:modal_html.index(f'id="potential-note-{entry.id}"')]

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            f'<button class="mini-button potential-perform-action" type="button" data-open-modal="interview-arrange-potential-entry-{entry.id}">Perform action</button>',
            html,
        )
        self.assertIn("Interview confirmed", modal_html)
        self.assertIn("Notes", modal_html)
        self.assertIn('name="interview_no_show" value="1" data-interview-no-show checked', modal_html)
        self.assertIn("No-show", modal_html)
        self.assertIn("Has a car", modal_html)
        self.assertIn('type="radio" name="interview_has_car" value="Yes" checked disabled', modal_html)
        self.assertIn('type="radio" name="interview_has_car" value="No"', modal_html)
        self.assertIn('class="potential-interview-role-picker"', modal_html)
        self.assertIn('class="staff-fut-options potential-interview-role-options"', modal_html)
        self.assertIn('type="checkbox" name="interview_roles" value="Examiner" checked disabled', modal_html)
        self.assertIn('type="checkbox" name="interview_roles" value="RSG"', modal_html)
        self.assertIn('type="checkbox" name="interview_roles" value="Supervisor"', modal_html)
        self.assertIn('type="checkbox" name="interview_roles" value="Other" checked disabled', modal_html)
        self.assertIn('name="entry_added_in_sessions_pre_confirmation"', modal_html)
        self.assertIn('name="entry_added_in_sessions_pre_confirmation"\n                      value="1"\n                      checked\n                      disabled', modal_html)
        self.assertIn("Entry added in sessions for pre-confirmation", modal_html)
        self.assertIn("Entry rejected", modal_html)
        self.assertIn(f'/potential-entries/{entry.id}/cv-review/decline-application', modal_html)
        self.assertIn("Entry accepted", modal_html)
        self.assertIn(f'/potential-entries/{entry.id}/cv-review/accept-application', modal_html)
        self.assertIn('data-application-accepted-button', modal_html)
        self.assertIn('disabled title="No-show entries cannot be accepted."', modal_html)
        self.assertNotIn("Save and close", modal_html)
        self.assertNotIn("Information for interview arrangement", modal_html)
        self.assertNotIn("Send email", modal_html)

    def test_interview_confirmed_save_and_close_persists_outcome_fields_and_note(self):
        entry = self.add_entry(
            status="Interview confirmed",
            interview="",
            has_car="No",
            acceptance_roles="",
            interview_no_show=False,
        )
        response = self.client().post(
            f"/potential-entries/{entry.id}/cv-review/save",
            data={
                "csrf_token": "token",
                "cv_review_notes": "Candidate did not attend the interview.",
                "cv_review_note_department": "Management",
                "interview_no_show": "1",
                "interview_has_car": "Yes",
                "interview_roles": ["Examiner", "Other"],
                "entry_added_in_sessions_pre_confirmation": "1",
            },
            follow_redirects=True,
        )
        html = response.get_data(as_text=True)
        updated_entry = db.session.get(PotentialEntry, entry.id)

        self.assertEqual(response.status_code, 200)
        self.assertIn("CV review saved.", html)
        self.assertEqual(updated_entry.status, "Interview confirmed")
        self.assertTrue(updated_entry.interview_no_show)
        self.assertFalse(updated_entry.entry_added_in_sessions_pre_confirmation)
        self.assertEqual(updated_entry.has_car, "")
        self.assertEqual(updated_entry.roles_list(), [])
        self.assertIn("CV review - Management: Candidate did not attend the interview.", updated_entry.interview)

    def test_interview_confirmed_application_accepted_saves_outcome_fields_and_status(self):
        entry = self.add_entry(
            status="Interview confirmed",
            interview="",
            has_car="No",
            acceptance_roles="",
            interview_no_show=False,
        )
        response = self.client().post(
            f"/potential-entries/{entry.id}/cv-review/accept-application",
            data={
                "csrf_token": "token",
                "cv_review_notes": "Candidate is ready to continue.",
                "cv_review_note_department": "Management",
                "interview_has_car": "Yes",
                "interview_roles": ["RSG", "Supervisor"],
                "entry_added_in_sessions_pre_confirmation": "1",
            },
            follow_redirects=True,
        )
        html = response.get_data(as_text=True)
        updated_entry = db.session.get(PotentialEntry, entry.id)

        self.assertEqual(response.status_code, 200)
        self.assertIn("Application accepted.", html)
        self.assertEqual(updated_entry.status, "Entry accepted")
        self.assertFalse(updated_entry.is_rejected)
        self.assertFalse(updated_entry.interview_no_show)
        self.assertTrue(updated_entry.entry_added_in_sessions_pre_confirmation)
        self.assertEqual(updated_entry.has_car, "Yes")
        self.assertEqual(updated_entry.roles_list(), ["RSG", "Supervisor"])
        self.assertIn("CV review - Management: Candidate is ready to continue.", updated_entry.interview)

    def test_interview_confirmed_application_accepted_requires_outcome_fields(self):
        entry = self.add_entry(status="Interview confirmed")
        response = self.client().post(
            f"/potential-entries/{entry.id}/cv-review/accept-application",
            data={
                "csrf_token": "token",
                "interview_has_car": "Yes",
                "interview_roles": ["Examiner"],
            },
            follow_redirects=True,
        )
        html = response.get_data(as_text=True)
        updated_entry = db.session.get(PotentialEntry, entry.id)

        self.assertEqual(response.status_code, 200)
        self.assertIn("Entry added in sessions for pre-confirmation is required.", html)
        self.assertEqual(updated_entry.status, "Interview confirmed")

    def test_interview_confirmed_application_declined_saves_outcome_fields_and_status(self):
        entry = self.add_entry(
            status="Interview confirmed",
            interview="",
            has_car="Yes",
            acceptance_roles="Examiner",
            interview_no_show=False,
        )
        response = self.client().post(
            f"/potential-entries/{entry.id}/cv-review/decline-application",
            data={
                "csrf_token": "token",
                "cv_review_notes": "Candidate declined the opportunity.",
                "cv_review_note_department": "Management",
                "interview_no_show": "1",
                "interview_has_car": "No",
                "interview_roles": ["Other"],
                "entry_added_in_sessions_pre_confirmation": "1",
            },
            follow_redirects=True,
        )
        html = response.get_data(as_text=True)
        updated_entry = db.session.get(PotentialEntry, entry.id)

        self.assertEqual(response.status_code, 200)
        self.assertIn("Application declined.", html)
        self.assertEqual(updated_entry.status, "Entry rejected")
        self.assertTrue(updated_entry.is_rejected)
        self.assertIsNotNone(updated_entry.rejected_on)
        self.assertTrue(updated_entry.interview_no_show)
        self.assertFalse(updated_entry.entry_added_in_sessions_pre_confirmation)
        self.assertEqual(updated_entry.has_car, "")
        self.assertEqual(updated_entry.roles_list(), [])
        self.assertIn("CV review - Management: Candidate declined the opportunity.", updated_entry.interview)

    def test_interview_confirmed_application_accepted_is_blocked_when_no_show_is_checked(self):
        entry = self.add_entry(
            status="Interview confirmed",
            interview="",
            has_car="Yes",
            acceptance_roles="Examiner",
            interview_no_show=False,
        )
        response = self.client().post(
            f"/potential-entries/{entry.id}/cv-review/accept-application",
            data={
                "csrf_token": "token",
                "interview_no_show": "1",
                "interview_has_car": "Yes",
                "interview_roles": ["Examiner"],
            },
            follow_redirects=True,
        )
        html = response.get_data(as_text=True)
        updated_entry = db.session.get(PotentialEntry, entry.id)

        self.assertEqual(response.status_code, 200)
        self.assertIn("No-show entries cannot be accepted.", html)
        self.assertEqual(updated_entry.status, "Interview confirmed")
        self.assertFalse(updated_entry.interview_no_show)
        self.assertEqual(updated_entry.has_car, "Yes")
        self.assertEqual(updated_entry.roles_list(), ["Examiner"])

    def test_entry_accepted_perform_action_shows_notes_check_and_email_actions(self):
        entry = self.add_entry(
            status="Entry accepted",
            phone="+54 (9) 11-5555-0000",
            entry_accepted_notes_checked=False,
        )
        db.session.add(
            StaffMembersSettings(
                upcoming_induction_session_options=json.dumps([
                    {"date": "10/08/2026", "start_time": "10:00", "end_time": "12:00"},
                ])
            )
        )
        db.session.commit()

        response = self.client().get("/potential-entries")
        html = response.get_data(as_text=True)
        modal_html = html[html.index(f'id="interview-arrange-potential-entry-{entry.id}"'):]
        modal_html = modal_html[:modal_html.index(f'id="potential-note-{entry.id}"')]

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            f'<button class="mini-button potential-perform-action" type="button" data-open-modal="interview-arrange-potential-entry-{entry.id}">Perform action</button>',
            html,
        )
        self.assertIn("Potential entry information", modal_html)
        self.assertIn("Notes", modal_html)
        self.assertIn("Entry accepted action", modal_html)
        self.assertIn("Notes have been checked", modal_html)
        self.assertIn('name="entry_accepted_notes_checked"', modal_html)
        self.assertIn('data-entry-accepted-notes-checked', modal_html)
        self.assertNotIn('name="entry_accepted_notes_checked"\n                      value="1"\n                      data-entry-accepted-notes-checked\n                      data-action="/potential-entries/1/entry-accepted/notes-checked"\n                      checked', modal_html)
        self.assertIn("Send email", modal_html)
        self.assertIn('data-send-entry-accepted-email', modal_html)
        self.assertIn('data-copy-entry-accepted-email', modal_html)
        self.assertIn('aria-label="Copy application acceptance email"', modal_html)
        self.assertIn("Mark as email sent", modal_html)
        self.assertIn('name="entry_accepted_email_sent"', modal_html)
        self.assertIn('data-induction-options=', modal_html)
        self.assertIn("Send WhatsApp", modal_html)
        self.assertIn('href="https://wa.me/5491155550000"', modal_html)
        self.assertIn('target="_blank"', modal_html)
        self.assertIn('rel="noopener noreferrer"', modal_html)
        self.assertIn('data-send-entry-accepted-whatsapp', modal_html)
        self.assertIn('data-copy-entry-accepted-whatsapp', modal_html)
        self.assertIn('aria-label="Copy WhatsApp message"', modal_html)
        self.assertIn("Mark as WhatsApp sent", modal_html)
        self.assertIn('name="entry_accepted_whatsapp_sent"', modal_html)
        self.assertIn("Onboarding email sent", modal_html)
        self.assertIn('data-onboarding-email-sent-button', modal_html)
        self.assertIn('disabled title="Complete all three checks before marking onboarding email as sent."', modal_html)
        self.assertNotIn('href="https://wa.me/"', modal_html)
        self.assertNotIn("Reject application", modal_html)
        self.assertNotIn("Proceed to interview", modal_html)

    def test_entry_accepted_whatsapp_action_is_disabled_without_phone(self):
        entry = self.add_entry(status="Entry accepted", phone="")
        response = self.client().get("/potential-entries")
        html = response.get_data(as_text=True)
        modal_html = html[html.index(f'id="interview-arrange-potential-entry-{entry.id}"'):]
        modal_html = modal_html[:modal_html.index(f'id="potential-note-{entry.id}"')]

        self.assertIn("Send WhatsApp", modal_html)
        self.assertIn("No phone number available.", modal_html)
        self.assertIn('title="No phone number available."', modal_html)
        self.assertIn('data-copy-entry-accepted-whatsapp', modal_html)
        self.assertNotIn("https://wa.me/", modal_html)

    def test_entry_accepted_notes_checked_persists_without_changing_status(self):
        entry = self.add_entry(status="Entry accepted", entry_accepted_notes_checked=False)
        response = self.client().post(
            f"/potential-entries/{entry.id}/entry-accepted/notes-checked",
            data={"csrf_token": "token", "entry_accepted_notes_checked": "1"},
            follow_redirects=True,
        )
        updated_entry = db.session.get(PotentialEntry, entry.id)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(updated_entry.entry_accepted_notes_checked)
        self.assertEqual(updated_entry.status, "Entry accepted")

    def test_entry_accepted_sent_checkboxes_persist_without_changing_status(self):
        entry = self.add_entry(
            status="Entry accepted",
            entry_accepted_email_sent=False,
            entry_accepted_whatsapp_sent=False,
        )

        email_response = self.client().post(
            f"/potential-entries/{entry.id}/entry-accepted/notes-checked",
            data={"csrf_token": "token", "entry_accepted_email_sent": "1"},
            follow_redirects=True,
        )
        whatsapp_response = self.client().post(
            f"/potential-entries/{entry.id}/entry-accepted/notes-checked",
            data={"csrf_token": "token", "entry_accepted_whatsapp_sent": "1"},
            follow_redirects=True,
        )
        updated_entry = db.session.get(PotentialEntry, entry.id)

        self.assertEqual(email_response.status_code, 200)
        self.assertEqual(whatsapp_response.status_code, 200)
        self.assertTrue(updated_entry.entry_accepted_email_sent)
        self.assertTrue(updated_entry.entry_accepted_whatsapp_sent)
        self.assertEqual(updated_entry.status, "Entry accepted")

    def test_entry_accepted_onboarding_button_enabled_when_all_checks_are_complete(self):
        entry = self.add_entry(
            status="Entry accepted",
            entry_accepted_notes_checked=True,
            entry_accepted_email_sent=True,
            entry_accepted_whatsapp_sent=True,
        )
        response = self.client().get("/potential-entries")
        html = response.get_data(as_text=True)
        modal_html = html[html.index(f'id="interview-arrange-potential-entry-{entry.id}"'):]
        modal_html = modal_html[:modal_html.index(f'id="potential-note-{entry.id}"')]

        self.assertIn("Onboarding email sent", modal_html)
        self.assertIn('data-onboarding-email-sent-button', modal_html)
        self.assertNotIn('disabled title="Complete all three checks before marking onboarding email as sent."', modal_html)

    def test_entry_accepted_onboarding_email_sent_requires_all_checks(self):
        entry = self.add_entry(
            status="Entry accepted",
            entry_accepted_notes_checked=True,
            entry_accepted_email_sent=True,
            entry_accepted_whatsapp_sent=False,
        )
        response = self.client().post(
            f"/potential-entries/{entry.id}/entry-accepted/onboarding-email-sent",
            data={"csrf_token": "token"},
            follow_redirects=True,
        )
        html = response.get_data(as_text=True)
        updated_entry = db.session.get(PotentialEntry, entry.id)

        self.assertEqual(response.status_code, 200)
        self.assertIn("Complete all three checks before marking onboarding email as sent.", html)
        self.assertEqual(updated_entry.status, "Entry accepted")

    def test_entry_accepted_onboarding_email_sent_changes_status_when_checks_complete(self):
        entry = self.add_entry(
            status="Entry accepted",
            entry_accepted_notes_checked=True,
            entry_accepted_email_sent=True,
            entry_accepted_whatsapp_sent=True,
        )
        response = self.client().post(
            f"/potential-entries/{entry.id}/entry-accepted/onboarding-email-sent",
            data={"csrf_token": "token"},
            follow_redirects=True,
        )
        html = response.get_data(as_text=True)
        updated_entry = db.session.get(PotentialEntry, entry.id)

        self.assertEqual(response.status_code, 200)
        self.assertIn("Onboarding email sent.", html)
        self.assertEqual(updated_entry.status, "Onboarding email sent")
        self.assertIn("Follow up onboarding email to confirm or turn down application", html)

    def test_entry_accepted_email_gmail_url_uses_subject_without_body(self):
        result = self.build_entry_accepted_email(
            {
                "fullName": "Jane Candidate",
                "email": "jane@example.com",
                "inductionOptions": json.dumps([
                    {"date": "10/08/2026", "start_time": "10:00", "end_time": "12:00"},
                ]),
            },
            require_email=True,
        )

        self.assertNotIn("error", result["payload"])
        self.assertIn("Jane Candidate", result["payload"]["text"])
        self.assertIn("We are delighted to inform you", result["payload"]["text"])
        self.assertIn("role of Examiner", result["payload"]["text"])
        self.assertIn("Confirm your availability for ONE of the upcoming online induction session:", result["payload"]["text"])
        self.assertIn("Confirm your availability for <strong>ONE</strong> of the upcoming online induction session:", result["payload"]["html"])
        self.assertIn("Monday 10 August 2026", result["payload"]["text"])
        self.assertIn("10:00–12:00", result["payload"]["text"])
        self.assertIn('href="https://drive.google.com/file/d/1FfzKcWq8pED3qv5yuzx2L9n_VEx0ZysM/view?usp=sharing"', result["payload"]["html"])
        self.assertIn("https://drive.google.com/file/d/1FfzKcWq8pED3qv5yuzx2L9n_VEx0ZysM/view?usp=sharing", result["payload"]["text"])
        self.assertIn("https://zoom.us/j/7284728472", result["payload"]["text"])
        self.assertIn("728 472 8472", result["payload"]["text"])
        self.assertIn("Password: path", result["payload"]["text"])
        self.assertNotIn("Meet", result["payload"]["html"])
        self.assertIn("to=jane%40example.com", result["gmailUrl"])
        self.assertIn("su=Your%20application%20has%20been%20accepted", result["gmailUrl"])
        self.assertNotIn("body=", result["gmailUrl"])

    def test_entry_accepted_send_email_requires_email(self):
        result = self.build_entry_accepted_email(
            {
                "fullName": "Jane Candidate",
                "email": "",
                "inductionOptions": json.dumps([
                    {"date": "10/08/2026", "start_time": "10:00", "end_time": "12:00"},
                ]),
            },
            require_email=True,
        )

        self.assertEqual(result["payload"], {"error": "Potential entry email is required."})

    def test_entry_accepted_whatsapp_message_uses_full_name_and_required_copy(self):
        result = self.build_entry_accepted_whatsapp_message({"fullName": "Jane Candidate"})

        self.assertNotIn("error", result)
        self.assertIn("Hi Jane Candidate!", result["text"])
        self.assertNotIn("XXXX", result["text"])
        self.assertIn("I'm Brenda from Path International Examinations.", result["text"])
        self.assertIn("your application has been accepted", result["text"])
        self.assertIn("✅ Read, complete, sign, and return the contract.", result["text"])
        self.assertIn("✅ Confirm your availability for one of the induction sessions.", result["text"])
        self.assertIn("✅ Confirm your availability for the remote training period and the Annual Staff Meeting.", result["text"])
        self.assertIn("✅ Pre-confirm your participation in your assigned exam sessions.", result["text"])
        self.assertIn("✅ Send us a profile photo with a white background, which will be used for your physical staff ID card.", result["text"])
        self.assertIn("Kind regards,\nBrenda", result["text"])

    def test_entry_accepted_whatsapp_message_requires_full_name(self):
        result = self.build_entry_accepted_whatsapp_message({"fullName": ""})

        self.assertEqual(result, {"error": "Potential entry full name is required."})

    def test_interview_invitation_email_generation_uses_options_platform_and_gmail_body(self):
        result = self.build_interview_invitation_email({
            "fullName": "Jane Candidate",
            "email": "jane@example.com",
            "platform": "Zoom",
            "interviewer": "Prof. Lic. Agustina Savini",
            "options": json.dumps([
                {"date": "13/08/2026", "time": "15:00"},
                {"date": "10/08/2026", "time": "10:00"},
                {"date": "", "time": ""},
            ]),
        })
        payload = result["payload"]

        self.assertNotIn("error", payload)
        self.assertEqual(payload["subject"], "Interview invitation: Path International Examinations")
        self.assertIn("Dear Jane Candidate", payload["text"])
        self.assertIn("with Prof. Lic. Agustina Savini", payload["text"])
        self.assertIn("Please review the following options and reply to let us know which date and time works best for you:", payload["text"])
        self.assertIn("Option 1: Monday 10 August 2026, 10:00", payload["text"])
        self.assertIn("Option 2: Thursday 13 August 2026, 15:00", payload["text"])
        self.assertNotIn("Option 3", payload["text"])
        self.assertIn("If none of these times work for you", payload["text"])
        self.assertIn("https://zoom.us/j/7284728472", payload["text"])
        self.assertIn("728 472 8472", payload["text"])
        self.assertIn("Password: path", payload["text"])
        self.assertNotIn("meet.google.com", payload["text"])
        with open("app/static/js/app.js", encoding="utf-8") as handle:
            self.assertIn("text/html", handle.read())
        self.assertIn("https://mail.google.com/mail/?view=cm&fs=1&to=jane%40example.com", result["gmailUrl"])
        self.assertIn("su=Interview%20invitation%3A%20Path%20International%20Examinations", result["gmailUrl"])
        self.assertNotIn("body=", result["gmailUrl"])
        with open("app/static/js/app.js", encoding="utf-8") as handle:
            js = handle.read()
        self.assertIn("Interview invitation copied. Paste it into Gmail to keep the design.", js)
        self.assertIn("Gmail opened. If the invitation was not copied, use the copy button and paste it manually.", js)

    def test_interview_invitation_email_generation_uses_meet_and_validates_required_data(self):
        meet_result = self.build_interview_invitation_email({
            "fullName": "Jane Candidate",
            "email": "jane@example.com",
            "platform": "Meet",
            "interviewer": "our team",
            "options": json.dumps([{"date": "10/08/2026", "time": "10:00"}]),
        })
        missing_email = self.build_interview_invitation_email({
            "fullName": "Jane Candidate",
            "email": "",
            "platform": "Meet",
            "interviewer": "our team",
            "options": json.dumps([{"date": "10/08/2026", "time": "10:00"}]),
        })
        missing_options = self.build_interview_invitation_email({
            "fullName": "Jane Candidate",
            "email": "jane@example.com",
            "platform": "Meet",
            "interviewer": "our team",
            "options": json.dumps([]),
        })
        partial_option = self.build_interview_invitation_email({
            "fullName": "Jane Candidate",
            "email": "jane@example.com",
            "platform": "Meet",
            "interviewer": "our team",
            "options": json.dumps([{"date": "10/08/2026", "time": ""}]),
        })

        self.assertIn("https://meet.google.com/zrv-ucir-ugc", meet_result["payload"]["text"])
        self.assertNotIn("zoom.us", meet_result["payload"]["text"])
        self.assertEqual(missing_email["payload"]["error"], "Potential entry email is required.")
        self.assertEqual(missing_options["payload"]["error"], "Interview date and time options are not configured.")
        self.assertEqual(partial_option["payload"]["error"], "Please complete all interview date and time options before sending the email.")

    def test_cv_review_reject_saves_notes_and_marks_entry_rejected(self):
        entry = self.add_entry(status="CV to be reviewed")
        response = self.client().post(
            f"/potential-entries/{entry.id}/cv-review/reject",
            data={
                "csrf_token": "token",
                "cv_review_notes": "Application is not aligned right now.",
                "cv_review_note_department": "Management",
            },
            follow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("Application rejected.", response.get_data(as_text=True))
        updated_entry = db.session.get(PotentialEntry, entry.id)
        self.assertEqual(updated_entry.status, "Entry rejected")
        self.assertTrue(updated_entry.is_rejected)
        self.assertIsNotNone(updated_entry.rejected_on)
        self.assertIn("CV review - Management: Application is not aligned right now.", updated_entry.interview)
        self.assertEqual(json.loads(updated_entry.cv_review_interview_options), [])

    def test_cv_review_note_requires_department(self):
        entry = self.add_entry(status="CV to be reviewed", interview="")
        response = self.client().post(
            f"/potential-entries/{entry.id}/cv-review/add-note",
            data={"csrf_token": "token", "cv_review_notes": "Missing department."},
            follow_redirects=True,
        )
        html = response.get_data(as_text=True)
        updated_entry = db.session.get(PotentialEntry, entry.id)

        self.assertEqual(response.status_code, 200)
        self.assertIn("Department is required.", html)
        self.assertEqual(updated_entry.interview, "")

    def test_cv_review_add_note_saves_comment_and_keeps_modal_open(self):
        entry = self.add_entry(status="CV to be reviewed")
        response = self.client().post(
            f"/potential-entries/{entry.id}/cv-review/add-note",
            data={
                "csrf_token": "token",
                "cv_review_notes": "Please compare references.",
                "cv_review_note_department": "Admin",
                "interview_option_date": ["31/12/2099"],
                "interview_option_time": ["09:30"],
            },
            follow_redirects=True,
        )
        html = response.get_data(as_text=True)
        updated_entry = db.session.get(PotentialEntry, entry.id)

        self.assertEqual(response.status_code, 200)
        self.assertIn("Note added.", html)
        self.assertIn(f'id="cv-review-potential-entry-{entry.id}" aria-hidden="false"', html)
        self.assertRegex(html, r"\d{2}/\d{2}/\d{4} - \d{2}:\d{2} h\.")
        self.assertIn('<span class="responsible-chip potential-note-department-chip">Admin</span>', html)
        self.assertIn("Please compare references.", html)
        self.assertIn('data-potential-note-delete hidden', html)
        self.assertEqual(updated_entry.status, "CV to be reviewed")
        self.assertIn("CV review - Admin: Please compare references.", updated_entry.interview)
        self.assertEqual(json.loads(updated_entry.cv_review_interview_options), [{"date": "31/12/2099", "time": "09:30", "platform": "", "interviewer": ""}])

    def test_cv_review_note_can_be_deleted(self):
        entry = self.add_entry(status="CV to be reviewed")
        entry.interview = "04/07/2026 - 20:14 h.\nCV review - Admin: First note\n\n04/07/2026 - 20:15 h.\nCV review - Finance: Second note"
        db.session.commit()

        response = self.client().post(
            f"/potential-entries/{entry.id}/cv-review/notes/delete",
            data={"csrf_token": "token", "note_index": "0"},
            follow_redirects=True,
        )
        html = response.get_data(as_text=True)
        updated_entry = db.session.get(PotentialEntry, entry.id)

        self.assertEqual(response.status_code, 200)
        self.assertIn("Note deleted.", html)
        self.assertNotIn("First note", updated_entry.interview)
        self.assertIn("Second note", updated_entry.interview)
        self.assertIn(f'id="cv-review-potential-entry-{entry.id}" aria-hidden="false"', html)

    def test_cv_review_save_and_close_saves_without_status_change(self):
        entry = self.add_entry(status="CV to be reviewed")
        response = self.client().post(
            f"/potential-entries/{entry.id}/cv-review/save",
            data={
                "csrf_token": "token",
                "cv_review_notes": "Save this note without moving status.",
                "cv_review_note_department": "Admissions",
                "interview_option_date": ["31/12/2099"],
                "interview_option_time": ["10:00"],
            },
            follow_redirects=True,
        )
        html = response.get_data(as_text=True)
        updated_entry = db.session.get(PotentialEntry, entry.id)

        self.assertEqual(response.status_code, 200)
        self.assertIn("CV review saved.", html)
        self.assertNotIn(f'id="cv-review-potential-entry-{entry.id}" aria-hidden="false"', html)
        self.assertEqual(updated_entry.status, "CV to be reviewed")
        self.assertIn("CV review - Admissions: Save this note without moving status.", updated_entry.interview)
        self.assertEqual(json.loads(updated_entry.cv_review_interview_options), [{"date": "31/12/2099", "time": "10:00", "platform": "", "interviewer": ""}])

    def test_cv_review_proceed_saves_notes_and_moves_to_interview_stage(self):
        entry = self.add_entry(status="CV to be reviewed")
        response = self.client().post(
            f"/potential-entries/{entry.id}/cv-review/proceed",
            data={
                "csrf_token": "token",
                "cv_review_notes": "Strong application. Arrange interview.",
                "cv_review_note_department": "Management",
                "interview_option_date": ["31/12/2099", "01/01/2100"],
                "interview_option_time": ["09:30", "10:00"],
                "interview_option_platform": ["Zoom", "Meet"],
                "interview_option_interviewer": [
                    "Prof. Lic. Agustina Savini",
                    "Prof. Mgter. Pablo Demarchi",
                ],
            },
            follow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("Application moved to interview stage.", response.get_data(as_text=True))
        updated_entry = db.session.get(PotentialEntry, entry.id)
        self.assertEqual(updated_entry.status, "Interview to be arranged")
        self.assertFalse(updated_entry.is_rejected)
        self.assertIsNone(updated_entry.rejected_on)
        self.assertIn("CV review - Management: Strong application. Arrange interview.", updated_entry.interview)
        self.assertEqual(
            json.loads(updated_entry.cv_review_interview_options),
            [
                {
                    "date": "31/12/2099",
                    "time": "09:30",
                    "platform": "Zoom",
                    "interviewer": "Prof. Lic. Agustina Savini",
                },
                {
                    "date": "01/01/2100",
                    "time": "10:00",
                    "platform": "Zoom",
                    "interviewer": "Prof. Lic. Agustina Savini",
                },
            ],
        )

    def test_cv_review_proceed_requires_at_least_one_interview_option(self):
        entry = self.add_entry(status="CV to be reviewed", interview="")
        response = self.client().post(
            f"/potential-entries/{entry.id}/cv-review/proceed",
            data={
                "csrf_token": "token",
                "cv_review_notes": "Ready to move.",
                "cv_review_note_department": "Management",
                "interview_option_date": [""],
                "interview_option_time": [""],
            },
            follow_redirects=True,
        )
        html = response.get_data(as_text=True)
        updated_entry = db.session.get(PotentialEntry, entry.id)

        self.assertEqual(response.status_code, 200)
        self.assertIn("Please configure at least one interview date and time option before proceeding to interview.", html)
        self.assertIn(f'id="cv-review-potential-entry-{entry.id}" aria-hidden="false"', html)
        self.assertEqual(updated_entry.status, "CV to be reviewed")
        self.assertEqual(updated_entry.interview, "")

    def test_cv_review_proceed_requires_platform_and_interviewer(self):
        entry = self.add_entry(status="CV to be reviewed", interview="")
        response = self.client().post(
            f"/potential-entries/{entry.id}/cv-review/proceed",
            data={
                "csrf_token": "token",
                "cv_review_notes": "Ready to move.",
                "cv_review_note_department": "Management",
                "interview_option_date": ["31/12/2099"],
                "interview_option_time": ["10:00"],
            },
            follow_redirects=True,
        )
        html = response.get_data(as_text=True)
        updated_entry = db.session.get(PotentialEntry, entry.id)

        self.assertEqual(response.status_code, 200)
        self.assertIn("Please select a valid platform.", html)
        self.assertIn("Please select an interviewer.", html)
        self.assertIn(f'id="cv-review-potential-entry-{entry.id}" aria-hidden="false"', html)
        self.assertEqual(updated_entry.status, "CV to be reviewed")
        self.assertEqual(updated_entry.interview, "")

    def test_cv_review_reject_does_not_require_interview_option(self):
        entry = self.add_entry(status="CV to be reviewed")
        response = self.client().post(
            f"/potential-entries/{entry.id}/cv-review/reject",
            data={
                "csrf_token": "token",
                "cv_review_notes": "Reject without dates.",
                "cv_review_note_department": "Management",
                "interview_option_date": [""],
                "interview_option_time": [""],
            },
            follow_redirects=True,
        )
        updated_entry = db.session.get(PotentialEntry, entry.id)

        self.assertEqual(response.status_code, 200)
        self.assertIn("Application rejected.", response.get_data(as_text=True))
        self.assertEqual(updated_entry.status, "Entry rejected")
        self.assertEqual(json.loads(updated_entry.cv_review_interview_options), [])

    def test_cv_review_actions_reject_entries_outside_cv_review_status(self):
        entry = self.add_entry(status="Interview invitation sent", interview="")
        response = self.client().post(
            f"/potential-entries/{entry.id}/cv-review/proceed",
            data={"csrf_token": "token", "cv_review_notes": "Manipulated transition.", "cv_review_note_department": "Admin"},
            follow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("This application can only be reviewed while its status is CV to be reviewed or Review interview date and time.", response.get_data(as_text=True))
        updated_entry = db.session.get(PotentialEntry, entry.id)
        self.assertEqual(updated_entry.status, "Interview invitation sent")
        self.assertEqual(updated_entry.interview, "")

    def test_cv_review_option_validation_blocks_partial_or_invalid_options(self):
        cases = [
            (["31/12/2099"], [""], "Please complete both date and time for each interview option."),
            ([""], ["10:00"], "Please complete both date and time for each interview option."),
            (["01/01/2020"], ["10:00"], "Interview date cannot be in the past."),
            (["31/02/2099"], ["10:00"], "Please enter a valid interview date."),
            (["31/12/2099"], ["25:00"], "Please enter a valid interview time."),
            (["31/12/2099"], ["10:61"], "Please enter a valid interview time."),
        ]
        for dates, times, message in cases:
            entry = self.add_entry(status="CV to be reviewed", interview="")
            response = self.client().post(
                f"/potential-entries/{entry.id}/cv-review/proceed",
                data={
                    "csrf_token": "token",
                    "cv_review_notes": "Keep this draft",
                    "cv_review_note_department": "Finance",
                    "interview_option_date": dates,
                    "interview_option_time": times,
                },
                follow_redirects=True,
            )
            html = response.get_data(as_text=True)
            updated_entry = db.session.get(PotentialEntry, entry.id)

            self.assertEqual(response.status_code, 200)
            self.assertIn(message, html)
            self.assertIn(f'id="cv-review-potential-entry-{entry.id}" aria-hidden="false"', html)
            self.assertIn("Keep this draft", html)
            self.assertEqual(updated_entry.status, "CV to be reviewed")
            self.assertEqual(updated_entry.interview, "")

    def test_cv_review_options_enforce_maximum_five(self):
        entry = self.add_entry(status="CV to be reviewed")
        response = self.client().post(
            f"/potential-entries/{entry.id}/cv-review/proceed",
            data={
                "csrf_token": "token",
                "interview_option_date": ["31/12/2099"] * 6,
                "interview_option_time": ["10:00"] * 6,
            },
            follow_redirects=True,
        )

        self.assertIn("A maximum of 5 interview options is allowed.", response.get_data(as_text=True))
        self.assertEqual(db.session.get(PotentialEntry, entry.id).status, "CV to be reviewed")

    def test_cv_review_modal_limits_rendered_existing_options_to_five(self):
        entry = self.add_entry(
            status="CV to be reviewed",
            cv_review_interview_options=json.dumps([
                {"date": "31/12/2099", "time": "10:00", "platform": "Zoom", "interviewer": "Prof. Lic. Agustina Savini"},
                {"date": "01/01/2100", "time": "10:00", "platform": "Meet", "interviewer": ""},
                {"date": "02/01/2100", "time": "10:00"},
                {"date": "03/01/2100", "time": "10:00"},
                {"date": "04/01/2100", "time": "10:00"},
                {"date": "05/01/2100", "time": "10:00"},
            ]),
        )

        html = self.client().get("/potential-entries").get_data(as_text=True)
        modal_html = html[html.index(f'id="cv-review-potential-entry-{entry.id}"'):]
        modal_html = modal_html[:modal_html.index('id="potential-note-')]
        self.assertEqual(modal_html.count('name="interview_option_date"'), 5)
        self.assertEqual(modal_html.count('name="interview_option_platform"'), 1)
        self.assertEqual(modal_html.count('name="interview_option_interviewer"'), 1)
        self.assertLess(modal_html.rindex('data-interview-option-row'), modal_html.index('name="interview_option_platform"'))
        self.assertLess(modal_html.index('name="interview_option_platform"'), modal_html.index('name="interview_option_interviewer"'))
        self.assertIn('value="04/01/2100"', modal_html)
        self.assertNotIn('value="05/01/2100"', modal_html)
        self.assertIn('<option value="Zoom" selected>Zoom</option>', modal_html)
        self.assertIn("Prof. Lic. Agustina Savini", modal_html)

    def test_interview_option_date_mask_allows_year_digits(self):
        with open("app/static/js/app.js", encoding="utf-8") as handle:
            js = handle.read()

        self.assertIn('replace(/\\D/g, "").slice(0, 8)', js)
        self.assertIn('return `${digits.slice(0, 2)}/${digits.slice(2, 4)}/${digits.slice(4)}`;', js)

    def test_rejected_potential_entry_shows_permanent_delete_action(self):
        entry = self.add_entry(is_rejected=True)
        response = self.client().get("/potential-entries?show_rejected=1")
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("Show active entries", html)
        self.assertIn('href="/potential-entries?show_rejected=1&amp;sort=status&amp;dir=asc"', html)
        self.assertIn('href="/potential-entries?show_rejected=1&amp;sort=department&amp;dir=asc"', html)
        self.assertIn("<th>Action description</th>", html)
        self.assertIn("<th>Action</th>", html)
        self.assertLess(html.index("Full name\n            <span>"), html.index("City\n            <span>"))
        self.assertLess(html.index("City\n            <span>"), html.index("Province\n            <span>"))
        self.assertLess(html.index("Province\n            <span>"), html.index("<th>CV</th>"))
        self.assertLess(html.index("<th>CV</th>"), html.index("Department\n            <span>"))
        self.assertLess(html.index("Department\n            <span>"), html.index("<th>Action description</th>"))
        self.assertLess(html.index("<th>Action description</th>"), html.index("<th>Action</th>"))
        self.assertIn("Entry rejected", html)
        self.assertIn("Perform action", html)
        self.assertIn(f'/potential-entries/{entry.id}/delete', html)
        self.assertIn("Delete permanently", html)
        self.assertIn('data-confirm-password-value="Path1234"', html)
        self.assertIn('name="deletion_password"', html)

        active_response = self.client().get("/potential-entries")
        self.assertNotIn(f'/potential-entries/{entry.id}/delete', active_response.get_data(as_text=True))

    def test_rejected_potential_entry_delete_requires_path_password(self):
        entry = self.add_entry(is_rejected=True)
        response = self.client().post(
            f"/potential-entries/{entry.id}/delete",
            data={"csrf_token": "token", "deletion_password": "wrong"},
            follow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("Potential entry delete password is not valid.", response.get_data(as_text=True))
        self.assertIsNotNone(db.session.get(PotentialEntry, entry.id))

        response = self.client().post(
            f"/potential-entries/{entry.id}/delete",
            data={"csrf_token": "token", "deletion_password": "Path1234"},
            follow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("Rejected potential entry permanently deleted.", response.get_data(as_text=True))
        self.assertIsNone(db.session.get(PotentialEntry, entry.id))

    def test_archived_staff_member_delete_requires_path_password(self):
        member = self.add_member(status="Archived", full_name="Archived Staff", email="archived@example.com")
        session_record = self.add_session()
        db.session.add_all(
            [
                StaffPayment(member_id=member.id, year=2026),
                ExamSessionSupervisorAssignment(
                    exam_session_id=session_record.id,
                    team_member_id=member.id,
                    participation_status="Confirmed",
                ),
                ExamSessionExaminerAssignment(
                    exam_session_id=session_record.id,
                    team_member_id=member.id,
                    participation_status="Confirmed",
                ),
                ExamSessionInternAssignment(
                    exam_session_id=session_record.id,
                    team_member_id=member.id,
                    participation_status="Confirmed",
                ),
            ]
        )
        bundle = ExamSessionShipmentBundle(
            supervisor_staff_id=member.id,
            delivery_address="742 Evergreen Terrace",
            delivery_city="CABA",
            delivery_province="Buenos Aires",
            courier="Correo Argentino",
            status="Preparing bundle",
        )
        db.session.add(bundle)
        db.session.flush()
        db.session.add_all(
            [
                ExamSessionShipmentBundleSession(bundle_id=bundle.id, exam_session_id=session_record.id),
                ExamSessionShipmentChecklistItem(
                    bundle_id=bundle.id,
                    item_key="label",
                    label="Label printed",
                    display_order=1,
                ),
                ExamSessionShipmentEvent(
                    bundle_id=bundle.id,
                    event_type="status",
                    new_status="Preparing bundle",
                ),
            ]
        )
        db.session.commit()
        bundle_id = bundle.id
        response = self.client().get("/staff-members?show_archived=1")
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn(f"/members/{member.id}/delete", html)
        self.assertIn('data-confirm-password-value="Path1234"', html)

        response = self.client().post(
            f"/members/{member.id}/delete",
            data={"csrf_token": "token", "deletion_password": "7284"},
            follow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("Permanent delete password is not valid.", response.get_data(as_text=True))
        self.assertIsNotNone(db.session.get(AcademicStaff, member.id))

        response = self.client().post(
            f"/members/{member.id}/delete",
            data={"csrf_token": "token", "deletion_password": "Path1234"},
            follow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("Archived member permanently deleted.", response.get_data(as_text=True))
        self.assertIsNone(db.session.get(AcademicStaff, member.id))
        self.assertEqual(StaffPayment.query.filter_by(member_id=member.id).count(), 0)
        self.assertEqual(ExamSessionSupervisorAssignment.query.filter_by(team_member_id=member.id).count(), 0)
        self.assertEqual(ExamSessionExaminerAssignment.query.filter_by(team_member_id=member.id).count(), 0)
        self.assertEqual(ExamSessionInternAssignment.query.filter_by(team_member_id=member.id).count(), 0)
        self.assertIsNone(db.session.get(ExamSessionShipmentBundle, bundle_id))
        self.assertEqual(ExamSessionShipmentBundleSession.query.filter_by(bundle_id=bundle_id).count(), 0)
        self.assertEqual(ExamSessionShipmentChecklistItem.query.filter_by(bundle_id=bundle_id).count(), 0)
        self.assertEqual(ExamSessionShipmentEvent.query.filter_by(bundle_id=bundle_id).count(), 0)

    def test_non_rejected_potential_entry_cannot_be_deleted(self):
        entry = self.add_entry(is_rejected=False)
        response = self.client().post(
            f"/potential-entries/{entry.id}/delete",
            data={"csrf_token": "token", "deletion_password": "Path1234"},
            follow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("Only rejected potential entries can be permanently deleted.", response.get_data(as_text=True))
        self.assertIsNotNone(db.session.get(PotentialEntry, entry.id))

    def test_potential_entries_default_order_shows_most_recently_updated_first(self):
        self.add_entry(
            full_name="Older Candidate",
            email="older@example.com",
            interview_date="2026-07-03",
            interview_time="09:00:00",
            updated_on=datetime(2026, 7, 1, 9, 0, tzinfo=timezone.utc),
        )
        self.add_entry(
            full_name="Newest Candidate",
            email="newest@example.com",
            interview_date="",
            interview_time="",
            updated_on=datetime(2026, 7, 3, 9, 0, tzinfo=timezone.utc),
        )
        self.add_entry(
            full_name="Middle Candidate",
            email="middle-updated@example.com",
            status="Interview to be arranged",
            interview_date="2026-07-01",
            interview_time="07:00:00",
            updated_on=datetime(2026, 7, 2, 9, 0, tzinfo=timezone.utc),
        )
        self.add_entry(
            full_name="Finalised Candidate",
            email="finalised@example.com",
            status="Onboarding finalised",
            interview_date="2026-07-01",
            interview_time="06:00:00",
            updated_on=datetime(2026, 7, 4, 9, 0, tzinfo=timezone.utc),
        )

        response = self.client().get("/potential-entries")
        html = response.get_data(as_text=True)

        self.assertLess(html.index("Newest Candidate"), html.index("Middle Candidate"))
        self.assertLess(html.index("Middle Candidate"), html.index("Older Candidate"))
        self.assertLess(html.index("Older Candidate"), html.index("Finalised Candidate"))

    def test_updated_potential_entry_moves_to_top_of_default_table(self):
        edited_entry = self.add_entry(
            full_name="Edited Candidate",
            email="edited@example.com",
            city="Original city",
            updated_on=datetime(2026, 7, 1, 9, 0, tzinfo=timezone.utc),
        )
        self.add_entry(
            full_name="Previously Newer Candidate",
            email="previously-newer@example.com",
            updated_on=datetime(2026, 7, 3, 9, 0, tzinfo=timezone.utc),
        )

        response = self.client().post(
            f"/potential-entries/{edited_entry.id}",
            data={
                "csrf_token": "token",
                "status": edited_entry.status,
                "full_name": edited_entry.full_name,
                "phone": edited_entry.phone or "",
                "email": edited_entry.email,
                "city": "Updated city",
                "province": edited_entry.province or "",
                "cv": edited_entry.cv or "",
                "interview_date": edited_entry.interview_date,
                "interview_time": edited_entry.interview_time,
                "platform": edited_entry.platform,
                "interviewer": edited_entry.interviewer,
            },
            follow_redirects=True,
        )
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertLess(html.index("Edited Candidate"), html.index("Previously Newer Candidate"))
        self.assertEqual(db.session.get(PotentialEntry, edited_entry.id).city, "Updated city")

    def test_potential_entries_filter_by_status_and_department(self):
        self.add_entry(full_name="Admin Candidate", email="admin@example.com", status="Interview to be arranged")
        self.add_entry(full_name="Management Candidate", email="management@example.com", status="CV to be reviewed")
        self.add_entry(full_name="Confirmed Candidate", email="confirmed@example.com", status="Interview confirmed")
        self.add_entry(full_name="Finalised Candidate", email="finalised-filter@example.com", status="Onboarding finalised")

        response = self.client().get("/potential-entries?department=MANAGEMENT")
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn('<option value="MANAGEMENT" selected>MANAGEMENT</option>', html)
        self.assertIn("Management Candidate", html)
        self.assertIn("Confirmed Candidate", html)
        self.assertNotIn("Admin Candidate", html)
        self.assertNotIn("Finalised Candidate", html)

        status_response = self.client().get("/potential-entries?status=Interview+to+be+arranged")
        status_html = status_response.get_data(as_text=True)
        self.assertEqual(status_response.status_code, 200)
        self.assertIn('<option value="Interview to be arranged" selected>Interview to be arranged</option>', status_html)
        self.assertIn("Admin Candidate", status_html)
        self.assertNotIn("Management Candidate", status_html)

    def test_potential_entries_sort_links_and_ordering(self):
        self.add_entry(full_name="Zulu Candidate", email="zulu@example.com", status="Interview to be arranged", city="Rosario", province="Santa Fe")
        self.add_entry(full_name="Alpha Candidate", email="alpha@example.com", status="CV to be reviewed", city="Buenos Aires", province="Buenos Aires")
        self.add_entry(full_name="Middle Candidate", email="middle@example.com", status="Entry accepted", city="Cordoba", province="Cordoba")
        self.add_entry(full_name="Finalised Candidate", email="finalised-sort@example.com", status="Onboarding finalised", city="A City", province="A Province")

        response = self.client().get("/potential-entries?sort=full_name&dir=asc")
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn('href="/potential-entries?sort=status&amp;dir=asc"', html)
        self.assertIn('href="/potential-entries?sort=full_name&amp;dir=desc"', html)
        self.assertIn('href="/potential-entries?sort=city&amp;dir=asc"', html)
        self.assertIn('href="/potential-entries?sort=province&amp;dir=asc"', html)
        self.assertIn('href="/potential-entries?sort=department&amp;dir=asc"', html)
        self.assertLess(html.index("Alpha Candidate"), html.index("Middle Candidate"))
        self.assertLess(html.index("Middle Candidate"), html.index("Zulu Candidate"))
        self.assertLess(html.index("Zulu Candidate"), html.index("Finalised Candidate"))

        department_response = self.client().get("/potential-entries?sort=department&dir=desc")
        department_html = department_response.get_data(as_text=True)
        self.assertLess(department_html.index("Alpha Candidate"), department_html.index("Middle Candidate"))
        self.assertLess(department_html.index("Middle Candidate"), department_html.index("Finalised Candidate"))

    def test_meet_entry_uses_platform_without_manual_access_data(self):
        self.add_entry(platform="Meet")
        response = self.client().get("/potential-entries")
        html = response.get_data(as_text=True)
        self.assertNotIn("data-meet-link", html)
        self.assertNotIn("data-zoom-link", html)
        self.assertIn("Follow up invitation to confirm or cancel interview", html)
        self.assertNotIn("Email invitation", html)

    def test_potential_form_creates_interview_without_manual_access_details(self):
        response = self.client().post(
            "/potential-entries",
            data={
                "csrf_token": "token",
                "status": "Interview invitation sent",
                "full_name": "New Candidate",
                "email": "new@example.com",
                "phone": "",
                "city": "",
                "province": "",
                "cv": "",
                "interview_date": "2026-07-02",
                "interview_time": "10:00:00",
                "platform": "Zoom",
                "interviewer": "Prof. Mgter. Pablo Demarchi",
            },
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)
        entry = PotentialEntry.query.filter_by(email="new@example.com").first()
        self.assertIsNotNone(entry)
        self.assertEqual(entry.platform, "Zoom")
        self.assertEqual(entry.interview_date, "2026-07-02")
        self.assertEqual(entry.interview_time, "10:00:00")
        self.assertFalse(entry.interview_invitation_sent)

    def test_mark_and_undo_interview_invitation_sent_persists_without_status_side_effects(self):
        entry = self.add_entry()
        client = self.client()

        response = client.post(
            f"/potential-entries/{entry.id}/interview-invitation-sent",
            data={
                "csrf_token": "token",
                "interview_invitation_sent": "1",
                "next": "/?q=Jane",
            },
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/?q=Jane")
        updated_entry = db.session.get(PotentialEntry, entry.id)
        self.assertTrue(updated_entry.interview_invitation_sent)
        self.assertEqual(updated_entry.status, "Interview invitation sent")
        self.assertEqual(updated_entry.interview_date, "2026-07-02")
        self.assertEqual(updated_entry.interview_time, "10:00:00")
        self.assertEqual(updated_entry.platform, "Zoom")

        response = client.post(
            f"/potential-entries/{entry.id}/interview-invitation-sent",
            data={
                "csrf_token": "token",
                "interview_invitation_sent": "0",
                "next": "/?q=Jane",
            },
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(db.session.get(PotentialEntry, entry.id).interview_invitation_sent)

    def test_new_member_and_accept_member_forms_mark_complete_fields_required(self):
        self.add_entry(full_name="Required Candidate")
        staff_html = self.client().get("/staff-members").get_data(as_text=True)
        potential_html = self.client().get("/potential-entries").get_data(as_text=True)

        self.assertIn("Staff members | Path Examinations", staff_html)
        self.assertIn(">Staff members</p>", staff_html)
        self.assertIn("<h1>Staff members</h1>", staff_html)
        self.assertNotIn("<h1>Academic staff</h1>", staff_html)
        self.assertIn('data-modal-form="create-member"', staff_html)
        self.assertIn('name="title" value="" maxlength="120" required', staff_html)
        self.assertIn('name="phone" value="" maxlength="80" required', staff_html)
        self.assertIn('name="email" type="email" value="" maxlength="160" required', staff_html)
        self.assertIn('name="has_car" required', staff_html)
        self.assertIn("Potential entries | Path Examinations", potential_html)
        self.assertIn("Accept as staff member", potential_html)
        self.assertNotIn("Accept as academic staff", potential_html)
        html = staff_html + potential_html
        self.assertIn('name="started_in" type="text" inputmode="numeric" pattern="\\d{4}" value="" placeholder="2026" maxlength="4" required', html)
        self.assertIn('name="full_address_google_maps" value="" maxlength="500" required', html)
        self.assertIn('name="cv" type="url" value="" placeholder="https://example.com/cv" maxlength="500" required', html)
        self.assertIn('name="profile_picture" type="url" value="" placeholder="https://example.com/profile-picture" maxlength="500" required', html)
        self.assertIn('name="account_id" value="" maxlength="120" required', html)
        self.assertIn('name="account_owner" value="" maxlength="160" required', html)
        self.assertNotIn('name="seniority" type="checkbox" required', html)
        self.assertNotIn('textarea name="interview" rows="5" maxlength="4000" placeholder="Add a new interview note. It will be saved with date and time." required', html)

    def test_staff_members_can_sort_by_has_car_and_sessions(self):
        no_car = self.add_member(full_name="No Car Staff", email="no-car@example.com", has_car="No")
        one_session = self.add_member(full_name="One Session Staff", email="one-session@example.com", has_car="Yes")
        two_sessions = self.add_member(full_name="Two Sessions Staff", email="two-sessions@example.com", has_car="Yes")
        inactive = self.add_member(
            full_name="Inactive Staff",
            email="inactive-sort@example.com",
            status="Inactive",
            has_car="Yes",
        )
        first_session = self.add_session(exam_session_name="First counted session", session_date=date(2026, 7, 20))
        second_session = self.add_session(exam_session_name="Second counted session", session_date=date(2026, 8, 20))
        db.session.add_all(
            [
                ExamSessionExaminerAssignment(
                    exam_session_id=first_session.id,
                    team_member_id=one_session.id,
                    participation_status="Confirmed",
                ),
                ExamSessionExaminerAssignment(
                    exam_session_id=first_session.id,
                    team_member_id=two_sessions.id,
                    participation_status="Confirmed",
                ),
                ExamSessionSupervisorAssignment(
                    exam_session_id=second_session.id,
                    team_member_id=two_sessions.id,
                    participation_status="Confirmed",
                ),
                ExamSessionExaminerAssignment(
                    exam_session_id=second_session.id,
                    team_member_id=no_car.id,
                    participation_status="Pending",
                ),
            ]
        )
        db.session.commit()

        has_car_html = self.client().get("/staff-members?sort=has_car&dir=asc").get_data(as_text=True)
        self.assertIn("sort=has_car", has_car_html)
        self.assertLess(has_car_html.index("No Car Staff"), has_car_html.index("One Session Staff"))

        status_html = self.client().get("/staff-members?sort=status&dir=desc").get_data(as_text=True)
        self.assertIn("sort=status", status_html)
        self.assertLess(status_html.index("Inactive Staff"), status_html.index("No Car Staff"))

        sessions_html = self.client().get("/staff-members?sort=sessions&dir=desc").get_data(as_text=True)
        self.assertIn("sort=sessions", sessions_html)
        self.assertLess(sessions_html.index("Two Sessions Staff"), sessions_html.index("One Session Staff"))
        self.assertLess(sessions_html.index("One Session Staff"), sessions_html.index("No Car Staff"))

    def test_create_member_requires_complete_fields_except_seniority_and_history(self):
        response = self.client().post(
            "/members",
            data={
                "csrf_token": "token",
                "status": "Active",
                "title": "Prof.",
                "full_name": "Incomplete Member",
                "phone": "555-444",
            },
            follow_redirects=True,
        )

        html = response.get_data(as_text=True)
        self.assertEqual(AcademicStaff.query.count(), 0)
        self.assertIn("At least one role is required.", html)
        self.assertIn('class="modal is-open"', html)
        self.assertIn('id="create-member"', html)
        self.assertIn('value="Prof."', html)
        self.assertIn('value="Incomplete Member"', html)
        self.assertIn('value="555-444"', html)
        self.assertIn("Email is required.", html)
        self.assertIn("Has a car is required.", html)
        self.assertIn("Started in is required.", html)
        self.assertIn("Full address is required.", html)
        self.assertIn("City is required.", html)
        self.assertIn("Province is required.", html)
        self.assertIn("Country is required.", html)
        self.assertIn("CV is required.", html)
        self.assertIn("Profile picture is required.", html)
        self.assertIn("Account ID is required.", html)
        self.assertIn("Account owner is required.", html)

    def test_accept_potential_entry_requires_complete_member_fields_except_seniority_and_history(self):
        entry = self.add_entry(full_name="Incomplete Accepted Candidate")
        response = self.client().post(
            f"/potential-entries/{entry.id}/accept",
            data={
                "csrf_token": "token",
                "status": "Active",
                "title": "Prof.",
                "full_name": "Incomplete Accepted Candidate",
                "seniority": "on",
                "phone": "555-555",
                "has_car": "Yes",
            },
            follow_redirects=True,
        )

        html = response.get_data(as_text=True)
        self.assertEqual(AcademicStaff.query.count(), 0)
        updated_entry = db.session.get(PotentialEntry, entry.id)
        self.assertIsNotNone(updated_entry)
        self.assertEqual(updated_entry.title, "Prof.")
        self.assertTrue(updated_entry.seniority)
        self.assertEqual(updated_entry.phone, "555-555")
        self.assertEqual(updated_entry.has_car, "Yes")
        self.assertIn('class="modal is-open"', html)
        self.assertIn(f'id="accept-potential-entry-{entry.id}"', html)
        self.assertIn('value="Prof."', html)
        self.assertIn('value="555-555"', html)
        self.assertIn("At least one role is required.", html)
        self.assertIn("Email is required.", html)

    def test_member_cannot_be_inactivated_or_archived_when_assigned_to_future_session(self):
        member = self.add_member(full_name="Future Assigned Staff", email="future-assigned@example.com")
        session_record = self.add_session(exam_session_name="Future Blocking Session", session_date=date(2026, 7, 20))
        db.session.add(
            ExamSessionExaminerAssignment(
                exam_session_id=session_record.id,
                team_member_id=member.id,
                participation_status="Pending",
            )
        )
        db.session.commit()

        response = self.client().post(
            f"/members/{member.id}",
            data={
                "csrf_token": "token",
                "status": "Inactive",
                "full_name": "Future Assigned Staff",
            },
            follow_redirects=True,
        )

        html = response.get_data(as_text=True)
        self.assertIn("Future Blocking Session", html)
        self.assertIn("Remove the member from those sessions in Exam session planner", html)
        self.assertEqual(db.session.get(AcademicStaff, member.id).status, "Active")

    def test_bulk_status_change_blocks_members_assigned_to_future_sessions(self):
        member = self.add_member(full_name="Bulk Future Staff", email="bulk-future@example.com")
        session_record = self.add_session(exam_session_name="Bulk Future Session", session_date=date(2026, 9, 20))
        db.session.add(
            ExamSessionSupervisorAssignment(
                exam_session_id=session_record.id,
                team_member_id=member.id,
                participation_status="Confirmed",
            )
        )
        db.session.commit()

        response = self.client().post(
            "/members/bulk-update",
            data={
                "csrf_token": "token",
                "member_ids": [str(member.id)],
                "bulk_action": "status",
                "status": "Archived",
            },
            follow_redirects=True,
        )

        html = response.get_data(as_text=True)
        self.assertIn("Bulk Future Session", html)
        self.assertEqual(db.session.get(AcademicStaff, member.id).status, "Active")

    def test_save_acceptance_draft_persists_without_creating_member(self):
        entry = self.add_entry(full_name="Draft Candidate")
        response = self.client().post(
            f"/potential-entries/{entry.id}/accept-draft",
            data={
                "csrf_token": "token",
                "status": "Active",
                "title": "Prof.",
                "full_name": "Draft Candidate Updated",
                "seniority": "on",
                "roles": ["Examiner", "Supervisor"],
                "phone": "555-111",
                "email": "draft.updated@example.com",
                "has_car": "Yes",
                "started_in": "2026",
                "full_address_google_maps": "742 Evergreen Terrace",
                "city": "Moreno",
                "province": "Pumbis",
                "country": "Argentina",
                "cv": "https://example.com/cv.pdf",
                "profile_picture": "https://example.com/profile.jpg",
                "account_id": "ACC-1",
                "account_owner": "Path",
                "interview": "Draft note",
            },
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(AcademicStaff.query.count(), 0)
        updated_entry = db.session.get(PotentialEntry, entry.id)
        self.assertEqual(updated_entry.acceptance_status, "Active")
        self.assertEqual(updated_entry.title, "Prof.")
        self.assertEqual(updated_entry.full_name, "Draft Candidate Updated")
        self.assertTrue(updated_entry.seniority)
        self.assertEqual(updated_entry.roles_list(), ["Examiner", "Supervisor"])
        self.assertEqual(updated_entry.full_address_google_maps, "742 Evergreen Terrace")
        self.assertEqual(updated_entry.profile_picture, "https://example.com/profile.jpg")
        self.assertIn("Draft note", updated_entry.interview)

        html = self.client().get("/potential-entries").get_data(as_text=True)
        self.assertIn("Save", html)
        self.assertIn('data-acceptance-draft-save="/potential-entries/1/accept-draft"', html)
        self.assertIn('value="Draft Candidate Updated"', html)
        self.assertIn('value="742 Evergreen Terrace"', html)
        self.assertIn('value="https://example.com/profile.jpg"', html)
        self.assertIn('value="Examiner" checked', html)
        self.assertIn('value="Supervisor" checked', html)

    def test_save_acceptance_draft_allows_missing_required_member_fields(self):
        entry = self.add_entry(full_name="Partial Draft Candidate")
        response = self.client().post(
            f"/potential-entries/{entry.id}/accept-draft",
            data={
                "csrf_token": "token",
                "status": "",
                "full_name": "",
                "phone": "555-222",
                "email": "",
                "has_car": "",
                "started_in": "",
                "cv": "",
                "profile_picture": "",
            },
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(AcademicStaff.query.count(), 0)
        updated_entry = db.session.get(PotentialEntry, entry.id)
        self.assertEqual(updated_entry.full_name, "Partial Draft Candidate")
        self.assertEqual(updated_entry.acceptance_status, "")
        self.assertEqual(updated_entry.phone, "555-222")

    def test_save_acceptance_draft_persists_valid_fields_when_other_fields_are_invalid(self):
        entry = self.add_entry(
            full_name="Mixed Draft Candidate",
            has_car="No",
            started_in="2025",
            profile_picture="https://example.com/old.jpg",
        )
        response = self.client().post(
            f"/potential-entries/{entry.id}/accept-draft",
            data={
                "csrf_token": "token",
                "status": "Active",
                "full_name": "Mixed Draft Candidate",
                "seniority": "on",
                "roles": ["Examiner"],
                "phone": "555-333",
                "email": "mixed@example.com",
                "has_car": "Yes",
                "started_in": "20",
                "cv": "",
                "profile_picture": "not-a-url",
            },
            follow_redirects=True,
        )

        html = response.get_data(as_text=True)
        self.assertIn("Started in must be a four-digit year.", html)
        self.assertIn("Profile picture must be a valid http or https URL.", html)
        self.assertIn("Valid accepted form changes were saved.", html)
        updated_entry = db.session.get(PotentialEntry, entry.id)
        self.assertTrue(updated_entry.seniority)
        self.assertEqual(updated_entry.has_car, "Yes")
        self.assertEqual(updated_entry.acceptance_status, "Active")
        self.assertEqual(updated_entry.phone, "555-333")
        self.assertEqual(updated_entry.email, "mixed@example.com")
        self.assertEqual(updated_entry.started_in, "2025")
        self.assertEqual(updated_entry.profile_picture, "https://example.com/old.jpg")

    def test_sent_interview_invitation_shows_disabled_button_and_outcome_buttons(self):
        entry = self.add_entry(interview_invitation_sent=True)
        db.session.add(
            StaffMembersSettings(
                upcoming_induction_session_date=date(2026, 7, 15),
                upcoming_induction_session_start_time=time(10, 0),
                upcoming_induction_session_end_time=time(12, 0),
            )
        )
        db.session.commit()

        response = self.client().get("/potential-entries")
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("Follow up invitation to confirm or cancel interview", html)
        self.assertNotIn("Accept email", html)
        self.assertNotIn("Reject email", html)
        self.assertNotIn('data-copy-potential-outcome="successful"', html)
        self.assertNotIn('data-copy-potential-outcome="unsuccessful"', html)

    def test_outcome_buttons_do_not_show_outside_interview_arranged_status(self):
        self.add_entry(status="Interview to be arranged", interview_invitation_sent=True)
        response = self.client().get("/potential-entries")
        html = response.get_data(as_text=True)

        self.assertNotIn("Accept email", html)
        self.assertNotIn("Reject email", html)

    def test_potential_form_does_not_show_manual_access_fields(self):
        response = self.client().get("/potential-entries")
        html = response.get_data(as_text=True)
        self.assertIn("Platform", html)
        self.assertIn("Zoom", html)
        self.assertIn("Meet", html)
        self.assertNotIn("Zoom link", html)
        self.assertNotIn("Zoom ID", html)
        self.assertNotIn("Zoom password", html)
        self.assertNotIn("Meet link", html)

    def test_js_contains_html_and_plain_text_invitation_copy(self):
        with open("app/static/js/app.js", encoding="utf-8") as handle:
            js = handle.read()
        self.assertIn("Your interview with Path Examinations", js)
        self.assertIn("The Zoom access details are as follows:", js)
        self.assertIn("https://zoom.us/j/7284728472", js)
        self.assertIn("728 472 8472", js)
        self.assertIn('password: "path"', js)
        self.assertIn("The Meet access details are as follows:", js)
        self.assertIn("https://meet.google.com/zrv-ucir-ugc", js)
        self.assertIn("text/html", js)
        self.assertIn("text/plain", js)
        self.assertIn("Interview details are incomplete.", js)
        self.assertIn("enableInvitationSentAction", js)
        self.assertIn("data-invitation-sent-action", js)
        self.assertIn("Mark interview invitation as sent.", js)
        self.assertIn("buildPotentialGmailUrl", js)
        self.assertIn("https://mail.google.com/mail/?view=cm&fs=1&to=", js)
        self.assertIn("data-potential-gmail-email", js)
        self.assertIn("data-acceptance-draft-save", js)
        self.assertIn("form.submit()", js)
        gmail_helper = js[js.index("const buildPotentialGmailUrl"):js.index("const initPotentialGmailButtons")]
        self.assertNotIn("subject", gmail_helper)
        self.assertIn("undefined", js)

    def test_js_contains_potential_outcome_email_templates(self):
        with open("app/static/js/app.js", encoding="utf-8") as handle:
            js = handle.read()

        self.assertIn("buildSuccessfulApplicationEmail", js)
        self.assertIn("buildUnsuccessfulApplicationEmail", js)
        self.assertIn("Successful application", js)
        self.assertIn("Application update", js)
        self.assertIn("Your application has been accepted", js)
        self.assertIn("application for the role of Examiner", js)
        self.assertIn("this contract</a>", js)
        self.assertIn("1FfzKcWq8pED3qv5yuzx2L9n_VEx0ZysM", js)
        self.assertIn("Upcoming induction session date and time options are not configured.", js)
        self.assertIn("Please complete all induction session options before copying this email.", js)
        self.assertIn("Confirm your availability for <strong>ONE</strong> of the upcoming online induction session:", js)
        self.assertIn("Confirm your availability for ONE of the upcoming online induction session:", js)
        self.assertIn("https://zoom.us/j/7284728472", js)
        self.assertIn("728 472 8472", js)
        self.assertIn("Password: <strong>", js)
        self.assertIn("Successful application email copied.", js)
        self.assertIn("Unsuccessful application email copied.", js)
        self.assertIn("active examination sessions requiring additional examiners", js)
        self.assertIn("keep your profile in our database", js)
        self.assertIn("Potential entry full name is required.", js)
        successful_start = js.index("const buildSuccessfulApplicationEmail")
        unsuccessful_start = js.index("const buildUnsuccessfulApplicationEmail")
        successful_template = js[successful_start:unsuccessful_start]
        unsuccessful_template = js[unsuccessful_start:js.index("const initPotentialInvitationEmailButtons")]
        self.assertNotIn("Meet", successful_template)
        self.assertNotIn("Meet", unsuccessful_template)
        self.assertNotIn("Zoom", unsuccessful_template)
        self.assertNotIn("CONTRACT_LINK", unsuccessful_template)

    def test_successful_application_email_lists_sorted_induction_options(self):
        result = self.build_successful_application_email(
            {
                "fullName": "Jane Candidate",
                "inductionOptions": json.dumps(
                    [
                        {"date": "13/08/2026", "start_time": "15:00", "end_time": "17:00"},
                        {"date": "10/08/2026", "start_time": "10:00", "end_time": "12:00"},
                        {"date": "10/08/2026", "start_time": "08:00", "end_time": "09:00"},
                    ]
                ),
            }
        )

        self.assertNotIn("error", result)
        self.assertIn("Confirm your availability for <strong>ONE</strong> of the upcoming online induction session:", result["html"])
        self.assertIn("Confirm your availability for ONE of the upcoming online induction session:", result["text"])
        self.assertIn('href="https://drive.google.com/file/d/1FfzKcWq8pED3qv5yuzx2L9n_VEx0ZysM/view?usp=sharing"', result["html"])
        self.assertIn("this contract</a>", result["html"])
        self.assertIn("https://drive.google.com/file/d/1FfzKcWq8pED3qv5yuzx2L9n_VEx0ZysM/view?usp=sharing", result["text"])
        self.assertIn("The Zoom access details are as follows:", result["html"])
        self.assertIn("https://zoom.us/j/7284728472", result["text"])
        self.assertIn("728 472 8472", result["text"])
        self.assertIn("Password: path", result["text"])
        self.assertNotIn("Meet", result["html"])
        self.assertNotIn("Meet", result["text"])

        first = result["text"].index("Monday 10 August 2026\n08:00–09:00")
        second = result["text"].index("Monday 10 August 2026\n10:00–12:00")
        third = result["text"].index("Thursday 13 August 2026\n15:00–17:00")
        self.assertLess(first, second)
        self.assertLess(second, third)
        for output in (result["html"], result["text"]):
            self.assertIn("Monday 10 August 2026", output)
            self.assertIn("Thursday 13 August 2026", output)
            self.assertIn("10:00–12:00", output)
            self.assertNotIn("2026-08-10", output)
            self.assertNotIn("undefined", output)
            self.assertNotIn("null", output)
            self.assertNotIn("None", output)

    def test_successful_application_email_rejects_missing_induction_options(self):
        result = self.build_successful_application_email(
            {
                "fullName": "Jane Candidate",
                "inductionOptions": json.dumps([{"date": "", "start_time": "", "end_time": ""}]),
            }
        )

        self.assertEqual(result, {"error": "Upcoming induction session date and time options are not configured."})

    def test_successful_application_email_rejects_incomplete_induction_options(self):
        result = self.build_successful_application_email(
            {
                "fullName": "Jane Candidate",
                "inductionOptions": json.dumps(
                    [
                        {"date": "10/08/2026", "start_time": "10:00", "end_time": "12:00"},
                        {"date": "13/08/2026", "start_time": "", "end_time": "17:00"},
                    ]
                ),
            }
        )

        self.assertEqual(result, {"error": "Please complete all induction session options before copying this email."})


if __name__ == "__main__":
    unittest.main()
