import os
import unittest
from datetime import date, time

os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from app import create_app, db
from app.models import AcademicStaff, PotentialEntry, StaffMembersSettings


class StaffMemberSettingsTest(unittest.TestCase):
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

    def test_staff_members_settings_render_empty_without_creating_record(self):
        response = self.client().get("/")
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("Upcoming induction session date and time", html)
        self.assertIn('name="upcoming_induction_session_date"', html)
        self.assertIn('name="upcoming_induction_session_start_time"', html)
        self.assertIn('name="upcoming_induction_session_end_time"', html)
        self.assertLess(html.index("Potential entries"), html.index("Upcoming induction session date and time"))
        self.assertLess(html.index("Upcoming induction session date and time"), html.index("staff-bulk-export-form"))
        self.assertNotIn("undefined", html)
        self.assertNotIn("null", html)
        self.assertNotIn("None", html)
        self.assertEqual(StaffMembersSettings.query.count(), 0)

    def test_staff_members_settings_persist_and_render_on_reload(self):
        client = self.client()
        response = client.post(
            "/staff-members/settings",
            data={
                "csrf_token": "token",
                "upcoming_induction_session_date": "15/07/2026",
                "upcoming_induction_session_start_time": "09:30",
                "upcoming_induction_session_end_time": "11:00",
            },
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)
        settings = StaffMembersSettings.query.one()
        self.assertEqual(settings.upcoming_induction_session_date, date(2026, 7, 15))
        self.assertEqual(settings.upcoming_induction_session_start_time, time(9, 30))
        self.assertEqual(settings.upcoming_induction_session_end_time, time(11, 0))

        response = client.get("/")
        html = response.get_data(as_text=True)
        self.assertIn('value="15/07/2026"', html)
        self.assertIn('value="09:30"', html)
        self.assertIn('value="11:00"', html)

    def test_staff_members_settings_reject_invalid_or_incomplete_range(self):
        client = self.client()
        invalid_payloads = [
            {
                "upcoming_induction_session_date": "15/07/2026",
                "upcoming_induction_session_start_time": "11:00",
                "upcoming_induction_session_end_time": "11:00",
            },
            {
                "upcoming_induction_session_date": "15/07/2026",
                "upcoming_induction_session_start_time": "12:00",
                "upcoming_induction_session_end_time": "11:00",
            },
            {
                "upcoming_induction_session_date": "15/07/2026",
                "upcoming_induction_session_start_time": "",
                "upcoming_induction_session_end_time": "11:00",
            },
        ]

        for payload in invalid_payloads:
            payload["csrf_token"] = "token"
            response = client.post("/staff-members/settings", data=payload, follow_redirects=False)
            self.assertEqual(response.status_code, 302)

        self.assertEqual(StaffMembersSettings.query.count(), 0)

    def test_staff_members_settings_does_not_modify_staff_or_potential_entries(self):
        staff_member = AcademicStaff(status="Active", full_name="Staff Person", roles="Examiner")
        potential_entry = PotentialEntry(status="To be interviewed", full_name="Potential Person")
        db.session.add_all([staff_member, potential_entry])
        db.session.commit()
        staff_id = staff_member.id
        potential_id = potential_entry.id

        response = self.client().post(
            "/staff-members/settings",
            data={
                "csrf_token": "token",
                "upcoming_induction_session_date": "15/07/2026",
                "upcoming_induction_session_start_time": "09:30",
                "upcoming_induction_session_end_time": "11:00",
            },
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(AcademicStaff.query.count(), 1)
        self.assertEqual(PotentialEntry.query.count(), 1)
        self.assertEqual(db.session.get(AcademicStaff, staff_id).full_name, "Staff Person")
        self.assertEqual(db.session.get(PotentialEntry, potential_id).full_name, "Potential Person")


if __name__ == "__main__":
    unittest.main()
