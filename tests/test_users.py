import os
import unittest

os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from sqlalchemy.exc import IntegrityError

from app import create_app, db
from app.models import User, USER_DEPARTMENTS


class UsersTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config["TESTING"] = True
        self.ctx = self.app.app_context()
        self.ctx.push()
        db.drop_all()
        db.create_all()
        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def admin_client(self):
        client = self.app.test_client()
        with client.session_transaction() as user_session:
            user_session["user"] = "Admin User"
            user_session["user_id"] = 1
            user_session["user_full_name"] = "Admin User"
            user_session["user_email"] = "admin@example.com"
            user_session["user_department"] = "Admin"
            user_session["csrf_token"] = "token"
        return client

    def non_admin_client(self):
        client = self.app.test_client()
        with client.session_transaction() as user_session:
            user_session["user"] = "Finance User"
            user_session["user_department"] = "Finance"
            user_session["csrf_token"] = "token"
        return client

    def create_user_record(self, email="person@example.com", password="secret123", department="Admin", is_active=True):
        user = User(
            full_name="Person Example",
            email=email,
            department=department,
            is_active=is_active,
        )
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        return user

    def test_user_model_hashes_password_and_unique_email(self):
        self.assertIn("Admin", USER_DEPARTMENTS)
        user = self.create_user_record(password="plain-secret")
        self.assertNotEqual(user.password_hash, "plain-secret")
        self.assertNotIn("plain-secret", user.password_hash)
        self.assertTrue(user.check_password("plain-secret"))

        duplicate = User(
            full_name="Duplicate",
            email="person@example.com",
            department="Finance",
            password_hash="hash",
        )
        db.session.add(duplicate)
        with self.assertRaises(IntegrityError):
            db.session.commit()
        db.session.rollback()

    def test_admin_can_create_user_with_normalized_email(self):
        response = self.admin_client().post(
            "/users",
            data={
                "csrf_token": "token",
                "full_name": "  New User  ",
                "email": "NEW.USER@EXAMPLE.COM",
                "department": "Finance",
                "password": "secret123",
            },
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)
        user = User.query.filter_by(email="new.user@example.com").first()
        self.assertIsNotNone(user)
        self.assertEqual(user.full_name, "New User")
        self.assertEqual(user.department, "Finance")
        self.assertTrue(user.is_active)
        self.assertTrue(user.check_password("secret123"))

    def test_create_user_validation_errors(self):
        client = self.admin_client()
        response = client.post(
            "/users",
            data={"csrf_token": "token", "full_name": "", "email": "", "department": "", "password": ""},
            follow_redirects=True,
        )
        body = response.get_data(as_text=True)
        self.assertIn("Full name is required.", body)
        self.assertIn("Email is required.", body)
        self.assertIn("Department is required.", body)
        self.assertIn("Password is required.", body)

        self.create_user_record(email="taken@example.com")
        response = client.post(
            "/users",
            data={
                "csrf_token": "token",
                "full_name": "Taken",
                "email": "taken@example.com",
                "department": "Admin",
                "password": "secret123",
            },
            follow_redirects=True,
        )
        self.assertIn("Email already exists.", response.get_data(as_text=True))

    def test_active_user_can_login_and_session_is_populated(self):
        user = self.create_user_record(email="login@example.com", password="secret123", department="Logistics")
        response = self.client.post(
            "/login",
            data={"email": "LOGIN@EXAMPLE.COM", "password": "secret123"},
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)
        with self.client.session_transaction() as user_session:
            self.assertEqual(user_session["user_id"], user.id)
            self.assertEqual(user_session["user_email"], "login@example.com")
            self.assertEqual(user_session["user_full_name"], "Person Example")
            self.assertEqual(user_session["user_department"], "Logistics")

    def test_invalid_or_inactive_login_uses_generic_error(self):
        self.create_user_record(email="inactive@example.com", password="secret123", is_active=False)
        response = self.client.post(
            "/login",
            data={"email": "inactive@example.com", "password": "secret123"},
        )
        self.assertIn("Invalid email or password.", response.get_data(as_text=True))
        response = self.client.post(
            "/login",
            data={"email": "missing@example.com", "password": "secret123"},
        )
        self.assertIn("Invalid email or password.", response.get_data(as_text=True))
        response = self.client.post(
            "/login",
            data={"email": "inactive@example.com", "password": "wrong"},
        )
        self.assertIn("Invalid email or password.", response.get_data(as_text=True))

    def test_users_access_requires_admin(self):
        self.assertEqual(self.client.get("/users").status_code, 302)
        self.assertEqual(self.non_admin_client().get("/users").status_code, 403)
        self.assertEqual(self.admin_client().get("/users").status_code, 200)
        response = self.non_admin_client().post(
            "/users",
            data={
                "csrf_token": "token",
                "full_name": "Blocked",
                "email": "blocked@example.com",
                "department": "Admin",
                "password": "secret123",
            },
        )
        self.assertEqual(response.status_code, 403)

    def test_users_ui_contains_menu_modal_and_no_password_hash(self):
        user = self.create_user_record(email="visible@example.com", password="secret123", department="Management")
        response = self.admin_client().get("/users")
        body = response.get_data(as_text=True)
        self.assertIn("Users", body)
        self.assertIn("New user", body)
        self.assertIn("Full name", body)
        self.assertIn("Email", body)
        self.assertIn("Department", body)
        self.assertIn("Password", body)
        self.assertIn("visible@example.com", body)
        self.assertIn("Management", body)
        self.assertIn("Active", body)
        self.assertNotIn(user.password_hash, body)


if __name__ == "__main__":
    unittest.main()
