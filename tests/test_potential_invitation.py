import os
import unittest
from datetime import date, time

os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from app import create_app, db
from app.models import PotentialEntry, StaffMembersSettings


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
        self.assertIn(f'data-full-name="{entry.full_name}"', html)
        self.assertIn('data-interview-date="2026-07-02"', html)
        self.assertIn('data-interview-time="10:00:00"', html)
        self.assertIn('data-platform="Zoom"', html)
        self.assertNotIn("Successful application email", html)
        self.assertNotIn("Unsuccessful application email", html)
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
        self.assertNotIn("Successful application email", html)
        self.assertNotIn("Unsuccessful application email", html)

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
        self.assertIn("Successful application email", html)
        self.assertIn("Unsuccessful application email", html)
        self.assertIn('data-copy-potential-outcome="successful"', html)
        self.assertIn('data-copy-potential-outcome="unsuccessful"', html)
        self.assertIn('data-induction-date="15/07/2026"', html)
        self.assertIn('data-induction-start-time="10:00"', html)
        self.assertIn('data-induction-end-time="12:00"', html)

    def test_outcome_buttons_do_not_show_outside_interview_arranged_status(self):
        self.add_entry(status="To be interviewed", interview_invitation_sent=True)
        response = self.client().get("/")
        html = response.get_data(as_text=True)

        self.assertNotIn("Successful application email", html)
        self.assertNotIn("Unsuccessful application email", html)

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
        self.assertIn("Upcoming induction session date and time is not configured.", js)
        self.assertIn("Upcoming online induction session", js)
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


if __name__ == "__main__":
    unittest.main()
