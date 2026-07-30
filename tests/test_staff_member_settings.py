import json
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
        staff_response = self.client().get("/staff-members")
        staff_html = staff_response.get_data(as_text=True)
        response = self.client().get("/potential-entries")
        html = response.get_data(as_text=True)

        self.assertEqual(staff_response.status_code, 200)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("Upcoming induction session date and time options", staff_html)
        self.assertIn("Upcoming induction session date and time options", html)
        self.assertIn('name="upcoming_induction_session_date"', html)
        self.assertIn('data-date-mask', html)
        self.assertIn('data-date-future-or-today', html)
        self.assertIn('name="upcoming_induction_session_start_time"', html)
        self.assertIn('name="upcoming_induction_session_end_time"', html)
        self.assertIn('data-time-mask', html)
        self.assertIn('data-induction-option-start-time', html)
        self.assertIn('data-induction-option-end-time', html)
        self.assertIn('data-add-induction-option', html)
        self.assertIn('data-remove-induction-option', html)
        self.assertIn('data-induction-options-more', html)
        self.assertIn('data-max-options="10"', html)
        self.assertEqual(html.count('data-induction-option-row'), 1)
        self.assertLess(html.index("<span>Potential entries</span>"), html.index("<span>Staff members</span>"))
        self.assertIn('aria-label="Potential entries"', html)
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
                "upcoming_induction_session_date": "15/08/2026",
                "upcoming_induction_session_start_time": "09:30",
                "upcoming_induction_session_end_time": "11:00",
            },
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)
        settings = StaffMembersSettings.query.one()
        self.assertEqual(settings.upcoming_induction_session_date, date(2026, 8, 15))
        self.assertEqual(settings.upcoming_induction_session_start_time, time(9, 30))
        self.assertEqual(settings.upcoming_induction_session_end_time, time(11, 0))
        self.assertEqual(
            json.loads(settings.upcoming_induction_session_options),
            [{"date": "15/08/2026", "start_time": "09:30", "end_time": "11:00"}],
        )

        self.assertEqual(response.headers["Location"], "/potential-entries")

        response = client.get("/potential-entries")
        html = response.get_data(as_text=True)
        self.assertIn('value="15/08/2026"', html)
        self.assertIn('value="09:30"', html)
        self.assertIn('value="11:00"', html)

    def test_staff_members_settings_persist_multiple_options(self):
        client = self.client()
        response = client.post(
            "/staff-members/settings",
            data={
                "csrf_token": "token",
                "upcoming_induction_session_date": ["15/08/2026", "16/08/2026"],
                "upcoming_induction_session_start_time": ["09:30", "14:00"],
                "upcoming_induction_session_end_time": ["11:00", "15:30"],
            },
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)
        settings = StaffMembersSettings.query.one()
        self.assertEqual(settings.upcoming_induction_session_date, date(2026, 8, 15))
        self.assertEqual(
            json.loads(settings.upcoming_induction_session_options),
            [
                {"date": "15/08/2026", "start_time": "09:30", "end_time": "11:00"},
                {"date": "16/08/2026", "start_time": "14:00", "end_time": "15:30"},
            ],
        )

        self.assertEqual(response.headers["Location"], "/potential-entries")

        response = client.get("/potential-entries")
        html = response.get_data(as_text=True)
        self.assertEqual(html.count('data-induction-option-row'), 2)
        self.assertIn('value="16/08/2026"', html)
        self.assertIn('value="14:00"', html)
        self.assertIn('value="15:30"', html)

    def test_staff_members_settings_reject_more_than_ten_options(self):
        client = self.client()
        response = client.post(
            "/staff-members/settings",
            data={
                "csrf_token": "token",
                "upcoming_induction_session_date": ["15/08/2026"] * 11,
                "upcoming_induction_session_start_time": ["09:30"] * 11,
                "upcoming_induction_session_end_time": ["11:00"] * 11,
            },
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(StaffMembersSettings.query.count(), 0)

    def test_staff_members_settings_reject_past_or_invalid_dates(self):
        client = self.client()
        invalid_payloads = [
            {
                "upcoming_induction_session_date": "17/07/2026",
                "upcoming_induction_session_start_time": "09:30",
                "upcoming_induction_session_end_time": "11:00",
            },
            {
                "upcoming_induction_session_date": "31/02/2027",
                "upcoming_induction_session_start_time": "09:30",
                "upcoming_induction_session_end_time": "11:00",
            },
            {
                "upcoming_induction_session_date": "32/08/2026",
                "upcoming_induction_session_start_time": "09:30",
                "upcoming_induction_session_end_time": "11:00",
            },
            {
                "upcoming_induction_session_date": "15/13/2026",
                "upcoming_induction_session_start_time": "09:30",
                "upcoming_induction_session_end_time": "11:00",
            },
        ]

        for payload in invalid_payloads:
            payload["csrf_token"] = "token"
            response = client.post("/staff-members/settings", data=payload, follow_redirects=False)
            self.assertEqual(response.status_code, 302)

        self.assertEqual(StaffMembersSettings.query.count(), 0)

    def test_staff_members_settings_cleans_past_induction_options_on_render(self):
        db.session.add(
            StaffMembersSettings(
                upcoming_induction_session_options=json.dumps([
                    {"date": "17/07/2026", "start_time": "09:30", "end_time": "11:00"},
                    {"date": "15/08/2026", "start_time": "14:00", "end_time": "15:30"},
                ])
            )
        )
        db.session.commit()

        html = self.client().get("/potential-entries").get_data(as_text=True)

        self.assertNotIn('value="17/07/2026"', html)
        self.assertIn('value="15/08/2026"', html)
        self.assertEqual(html.count('data-induction-option-row'), 1)

    def test_staff_members_settings_leaves_empty_row_when_all_induction_options_are_past(self):
        db.session.add(
            StaffMembersSettings(
                upcoming_induction_session_options=json.dumps([
                    {"date": "17/07/2026", "start_time": "09:30", "end_time": "11:00"},
                ])
            )
        )
        db.session.commit()

        html = self.client().get("/potential-entries").get_data(as_text=True)

        self.assertNotIn('value="17/07/2026"', html)
        self.assertNotIn('value="09:30"', html)
        self.assertNotIn('value="11:00"', html)
        self.assertEqual(html.count('data-induction-option-row'), 1)
        self.assertIn('name="upcoming_induction_session_date"', html)

    def test_staff_members_settings_reject_invalid_or_incomplete_range(self):
        client = self.client()
        invalid_payloads = [
            {
                "upcoming_induction_session_date": "15/08/2026",
                "upcoming_induction_session_start_time": "11:00",
                "upcoming_induction_session_end_time": "11:00",
            },
            {
                "upcoming_induction_session_date": "15/08/2026",
                "upcoming_induction_session_start_time": "12:00",
                "upcoming_induction_session_end_time": "11:00",
            },
            {
                "upcoming_induction_session_date": "15/08/2026",
                "upcoming_induction_session_start_time": "",
                "upcoming_induction_session_end_time": "11:00",
            },
            {
                "upcoming_induction_session_date": "15/08/2026",
                "upcoming_induction_session_start_time": "24:00",
                "upcoming_induction_session_end_time": "25:00",
            },
            {
                "upcoming_induction_session_date": "15/08/2026",
                "upcoming_induction_session_start_time": "09:60",
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
        potential_entry = PotentialEntry(status="Interview to be arranged", full_name="Potential Person")
        db.session.add_all([staff_member, potential_entry])
        db.session.commit()
        staff_id = staff_member.id
        potential_id = potential_entry.id

        response = self.client().post(
            "/staff-members/settings",
            data={
                "csrf_token": "token",
                "upcoming_induction_session_date": "15/08/2026",
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
