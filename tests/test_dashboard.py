import os
import unittest
from datetime import date, timedelta

os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from app import create_app, db
from app.models import PotentialEntry, User, UserMenuPermission, VALID_MENU_PERMISSION_KEYS


class DashboardTest(unittest.TestCase):
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

    def client(self, *, user="Admin User", department="Admin"):
        client = self.app.test_client()
        with client.session_transaction() as user_session:
            user_session["user"] = user
            user_session["user_full_name"] = user
            user_session["user_department"] = department
            user_session["csrf_token"] = "token"
        return client

    def permission_client(self, permissions, *, full_name="Person Example", department="Finance"):
        user = User(full_name=full_name, email="person@example.com", department=department, is_active=True)
        user.set_password("secret123")
        db.session.add(user)
        db.session.flush()
        for menu_key in VALID_MENU_PERMISSION_KEYS:
            values = permissions.get(menu_key, {})
            can_edit = bool(values.get("edit"))
            db.session.add(
                UserMenuPermission(
                    user_id=user.id,
                    menu_key=menu_key,
                    can_view=bool(values.get("view") or can_edit),
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
        return client

    def add_entry(self, status, *, is_rejected=False):
        entry = PotentialEntry(
            status=status,
            full_name=f"{status} Candidate",
            email=f"{status.lower().replace(' ', '.')}@example.com",
            is_rejected=is_rejected,
        )
        db.session.add(entry)
        db.session.commit()
        return entry

    def test_dashboard_renders_title_news_and_department(self):
        response = self.client(user="Pablo Demarchi", department="Management").get("/")
        body = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("Dashboard | Path Examinations", body)
        self.assertIn("Hello, Pablo!", body)
        self.assertNotIn("Hello, Pablo Demarchi!", body)
        self.assertIn("Welcome back — here’s what needs your attention today.", body)
        self.assertIn("MANAGEMENT", body)
        self.assertIn("Path news", body)
        self.assertIn("No news available yet.", body)
        self.assertIn("This space will be used to share important Path updates with the team.", body)

    def test_dashboard_counts_active_potential_entries_that_need_action(self):
        self.add_entry("CV to be reviewed")
        self.add_entry("Interview invitation sent")
        self.add_entry("Induction confirmed")
        self.add_entry("Onboarding finalised")
        self.add_entry("Entry rejected", is_rejected=True)
        self.add_entry("Entry accepted (on hold)").reactivation_date = (date.today() + timedelta(days=7)).isoformat()
        self.add_entry("Entry accepted (on hold)").reactivation_date = date.today().isoformat()
        db.session.commit()

        response = self.client().get("/")
        body = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("Potential entries", body)
        self.assertIn("2 actions", body)
        self.assertNotIn("0 notes", body)
        self.assertIn("You have 2 actions to complete in this menu.", body)
        self.assertIn('href="/potential-entries?action_scope=my_actions"', body)
        self.assertIn(">Go to menu<", body)
        self.assertNotIn('<span class="dashboard-count-chip">2</span>', body)

    def test_dashboard_potential_entries_counters_pluralize_zero_and_one(self):
        zero_response = self.client().get("/")
        zero_body = zero_response.get_data(as_text=True)

        self.assertEqual(zero_response.status_code, 200)
        self.assertNotIn("0 actions", zero_body)
        self.assertNotIn("0 notes", zero_body)
        self.assertNotIn('aria-label="Potential entries counters"', zero_body)

        self.add_entry("Interview invitation sent")
        one_response = self.client().get("/")
        one_body = one_response.get_data(as_text=True)

        self.assertEqual(one_response.status_code, 200)
        self.assertIn("1 action", one_body)
        self.assertNotIn("0 notes", one_body)
        self.assertIn("You have 1 action to complete in this menu.", one_body)

    def test_management_dashboard_counts_only_management_potential_actions(self):
        self.add_entry("CV to be reviewed")
        self.add_entry("Interview confirmed")
        self.add_entry("Onboarding finalised")
        self.add_entry("Interview invitation sent")
        self.add_entry("Induction confirmed")
        self.add_entry("Archived accepted entry")
        future_hold = self.add_entry("Entry accepted (on hold)")
        future_hold.reactivation_date = (date.today() + timedelta(days=7)).isoformat()
        due_hold = self.add_entry("Entry accepted (on hold)")
        due_hold.reactivation_date = date.today().isoformat()
        db.session.commit()

        client = self.permission_client({"staff_members": {"view": True}}, department="Management")
        response = client.get("/")
        body = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("You have 4 actions to complete in this menu.", body)

    def test_dashboard_hides_potential_entries_card_without_permission(self):
        client = self.permission_client({"fees": {"view": True}})
        response = client.get("/")
        body = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("Dashboard | Path Examinations", body)
        self.assertNotIn("<h2>Potential entries</h2>", body)
        self.assertNotIn(">Go to menu<", body)

    def test_staff_members_table_moved_to_staff_members_route(self):
        response = self.client().get("/staff-members")
        body = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("Staff members | Path Examinations", body)
        self.assertIn("<h1>Staff members</h1>", body)
