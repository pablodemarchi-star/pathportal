import json
import os
import subprocess
import unittest
from datetime import date, time

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
    StaffPayment,
    StaffMembersSettings,
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

    def add_entry(self, **overrides):
        values = {
            "status": "Interview arranged",
            "full_name": "Jane Candidate",
            "email": "jane@example.com",
            "interview_date": "2026-07-02",
            "interview_time": "10:00:00",
            "platform": "Zoom",
            "interviewer": "Prof. Mgter. Pablo Demarchi | Managing Director",
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

    def test_interview_arranged_entry_shows_email_invitation_button(self):
        entry = self.add_entry()
        response = self.client().get("/")
        html = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(entry.interview_invitation_sent)
        self.assertIn("Email invitation", html)
        self.assertIn("data-copy-potential-invitation", html)
        self.assertIn("Invitation sent", html)
        self.assertIn("data-invitation-sent-action", html)
        self.assertIn("Copy the email invitation first.", html)
        self.assertIn('data-potential-gmail-email="jane@example.com"', html)
        self.assertIn("Open Gmail compose", html)
        self.assertIn(f'data-full-name="{entry.full_name}"', html)
        self.assertIn('data-interview-date="2026-07-02"', html)
        self.assertIn('data-interview-time="10:00:00"', html)
        self.assertIn('data-platform="Zoom"', html)
        self.assertNotIn("Accept email", html)
        self.assertNotIn("Reject email", html)
        self.assertNotIn("data-zoom-link", html)
        self.assertNotIn("data-zoom-id", html)
        self.assertNotIn("data-zoom-password", html)
        self.assertNotIn("data-meet-link", html)

    def test_non_arranged_entry_does_not_show_email_invitation_button(self):
        self.add_entry(status="To be interviewed", platform="", interview_date="", interview_time="")
        response = self.client().get("/")
        html = response.get_data(as_text=True)
        self.assertNotIn("Email invitation", html)
        self.assertNotIn("data-copy-potential-invitation", html)
        self.assertNotIn("Accept email", html)
        self.assertNotIn("Reject email", html)

    def test_potential_entry_missing_contact_details_show_recorded_messages(self):
        self.add_entry(email="", phone="", city="", province="", cv="")
        response = self.client().get("/")
        html = response.get_data(as_text=True)
        self.assertIn("No email recorded", html)
        self.assertIn("No phone recorded", html)
        self.assertIn("No city or province recorded", html)
        self.assertIn("No CV recorded", html)
        self.assertNotIn("data-potential-gmail-email", html)

    def test_potential_entry_city_and_province_render_on_same_line(self):
        self.add_entry(city="Moreno", province="Pumbis")
        response = self.client().get("/")
        html = response.get_data(as_text=True)
        self.assertIn("Moreno, Pumbis", html)

    def test_rejected_potential_entry_shows_permanent_delete_action(self):
        entry = self.add_entry(is_rejected=True)
        response = self.client().get("/?show_rejected=1")
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("Rejected potential entries", html)
        self.assertIn(f'/potential-entries/{entry.id}/delete', html)
        self.assertIn("Delete permanently", html)
        self.assertIn('data-confirm-password-value="Path1234"', html)
        self.assertIn('name="deletion_password"', html)

        active_response = self.client().get("/")
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
        response = self.client().get("/?show_archived=1")
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

    def test_potential_entries_order_by_interview_date_and_time_with_missing_dates_last(self):
        self.add_entry(
            full_name="Far Candidate",
            email="far@example.com",
            interview_date="2026-07-03",
            interview_time="09:00:00",
        )
        self.add_entry(
            full_name="No Date Candidate",
            email="nodate@example.com",
            interview_date="",
            interview_time="",
        )
        self.add_entry(
            full_name="Unarranged Candidate",
            email="unarranged@example.com",
            status="To be interviewed",
            interview_date="2026-07-01",
            interview_time="07:00:00",
        )
        self.add_entry(
            full_name="Near Candidate",
            email="near@example.com",
            interview_date="2026-07-01",
            interview_time="12:00:00",
        )
        self.add_entry(
            full_name="Earliest Candidate",
            email="earliest@example.com",
            interview_date="2026-07-01",
            interview_time="08:00:00",
        )

        response = self.client().get("/")
        html = response.get_data(as_text=True)

        self.assertLess(html.index("Earliest Candidate"), html.index("Near Candidate"))
        self.assertLess(html.index("Near Candidate"), html.index("Far Candidate"))
        self.assertLess(html.index("Far Candidate"), html.index("No Date Candidate"))
        self.assertLess(html.index("Far Candidate"), html.index("Unarranged Candidate"))

    def test_meet_entry_uses_platform_without_manual_access_data(self):
        self.add_entry(platform="Meet")
        response = self.client().get("/")
        html = response.get_data(as_text=True)
        self.assertIn('data-platform="Meet"', html)
        self.assertNotIn("data-meet-link", html)
        self.assertNotIn("data-zoom-link", html)
        self.assertIn("Email invitation", html)

    def test_potential_form_creates_interview_without_manual_access_details(self):
        response = self.client().post(
            "/potential-entries",
            data={
                "csrf_token": "token",
                "status": "Interview arranged",
                "full_name": "New Candidate",
                "email": "new@example.com",
                "phone": "",
                "city": "",
                "province": "",
                "cv": "",
                "interview_date": "2026-07-02",
                "interview_time": "10:00:00",
                "platform": "Zoom",
                "interviewer": "Prof. Mgter. Pablo Demarchi | Managing Director",
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
        self.assertEqual(updated_entry.status, "Interview arranged")
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
        html = self.client().get("/").get_data(as_text=True)

        self.assertIn("Staff members | Path Examinations", html)
        self.assertIn(">Staff members</p>", html)
        self.assertIn("<h1>Staff members</h1>", html)
        self.assertNotIn("<h1>Academic staff</h1>", html)
        self.assertIn("Accept as staff member", html)
        self.assertNotIn("Accept as academic staff", html)
        self.assertIn('data-modal-form="create-member"', html)
        self.assertIn('name="title" value="" maxlength="120" required', html)
        self.assertIn('name="phone" value="" maxlength="80" required', html)
        self.assertIn('name="email" type="email" value="" maxlength="160" required', html)
        self.assertIn('name="has_car" required', html)
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

        has_car_html = self.client().get("/?sort=has_car&dir=asc").get_data(as_text=True)
        self.assertIn("sort=has_car", has_car_html)
        self.assertLess(has_car_html.index("No Car Staff"), has_car_html.index("One Session Staff"))

        status_html = self.client().get("/?sort=status&dir=desc").get_data(as_text=True)
        self.assertIn("sort=status", status_html)
        self.assertLess(status_html.index("Inactive Staff"), status_html.index("No Car Staff"))

        sessions_html = self.client().get("/?sort=sessions&dir=desc").get_data(as_text=True)
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

        html = self.client().get("/").get_data(as_text=True)
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

        response = self.client().get("/")
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("Interview invitation already sent.", html)
        self.assertIn("disabled", html)
        self.assertIn("Invitation sent", html)
        self.assertIn(f"Undo invitation sent for {entry.full_name}", html)
        self.assertIn("Accept email", html)
        self.assertIn("Reject email", html)
        self.assertIn('data-copy-potential-outcome="successful"', html)
        self.assertIn('data-copy-potential-outcome="unsuccessful"', html)
        self.assertIn('data-induction-date="15/07/2026"', html)
        self.assertIn('data-induction-start-time="10:00"', html)
        self.assertIn('data-induction-end-time="12:00"', html)

    def test_outcome_buttons_do_not_show_outside_interview_arranged_status(self):
        self.add_entry(status="To be interviewed", interview_invitation_sent=True)
        response = self.client().get("/")
        html = response.get_data(as_text=True)

        self.assertNotIn("Accept email", html)
        self.assertNotIn("Reject email", html)

    def test_potential_form_does_not_show_manual_access_fields(self):
        response = self.client().get("/")
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
        self.assertIn("Confirm your availability for <strong>ONE</strong> of the upcoming online induction sessions:", js)
        self.assertIn("Confirm your availability for ONE of the upcoming online induction sessions:", js)
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
        self.assertIn("Confirm your availability for <strong>ONE</strong> of the upcoming online induction sessions:", result["html"])
        self.assertIn("Confirm your availability for ONE of the upcoming online induction sessions:", result["text"])
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
