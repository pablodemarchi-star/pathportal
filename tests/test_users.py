import os
import unittest

os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from sqlalchemy.exc import IntegrityError

from app import create_app, db
from app.models import MENU_PERMISSIONS, User, UserMenuPermission, USER_DEPARTMENTS, VALID_MENU_PERMISSION_KEYS


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

    def create_user_record(
        self,
        email="person@example.com",
        password="secret123",
        department="Admin",
        is_active=True,
        is_superadmin=False,
        can_only_be_edited_by_superadmin=False,
    ):
        user = User(
            full_name="Person Example",
            email=email,
            department=department,
            is_active=is_active,
            is_superadmin=is_superadmin,
            can_only_be_edited_by_superadmin=can_only_be_edited_by_superadmin,
        )
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        return user

    def html_fragment(self, html, start_marker, end_marker=None):
        start = html.index(start_marker)
        if end_marker:
            end = html.index(end_marker, start)
            return html[start:end]
        return html[start:]

    def permission_client(self, permissions, email="perm@example.com", department="Finance", is_superadmin=False):
        user = self.create_user_record(email=email, department=department, is_superadmin=is_superadmin)
        for menu_key in VALID_MENU_PERMISSION_KEYS:
            values = permissions.get(menu_key, {})
            can_edit = bool(values.get("edit"))
            db.session.add(
                UserMenuPermission(
                    user_id=user.id,
                    menu_key=menu_key,
                    can_view=bool(values.get("view") or can_edit),
                    can_edit=can_edit,
                    can_manage_permissions=bool(values.get("manage")),
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

    def add_menu_permission(self, user, menu_key, view=False, edit=False, manage=False):
        permission = UserMenuPermission(
            user_id=user.id,
            menu_key=menu_key,
            can_view=bool(view or edit),
            can_edit=bool(edit),
            can_manage_permissions=bool(manage),
        )
        db.session.add(permission)
        db.session.commit()
        return permission

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

    def test_user_menu_permission_model_enforces_edit_implies_view(self):
        user = self.create_user_record(email="permissions@example.com")
        permission = UserMenuPermission(
            user_id=user.id,
            menu_key="users",
            can_view=False,
            can_edit=True,
        )
        db.session.add(permission)
        db.session.commit()
        self.assertTrue(permission.can_view)
        self.assertTrue(permission.can_edit)

        empty_permission = UserMenuPermission(
            user_id=user.id,
            menu_key="fees",
            can_view=False,
            can_edit=False,
        )
        db.session.add(empty_permission)
        db.session.commit()
        self.assertFalse(empty_permission.can_view)
        self.assertFalse(empty_permission.can_edit)

    def test_user_menu_permission_scope_is_independent_from_edit(self):
        user = self.create_user_record(email="scope-independent@example.com")
        permission = UserMenuPermission(
            user_id=user.id,
            menu_key="fees",
            can_view=False,
            can_edit=False,
            can_manage_permissions=True,
        )
        db.session.add(permission)
        db.session.commit()
        self.assertFalse(permission.can_view)
        self.assertFalse(permission.can_edit)
        self.assertTrue(permission.can_manage_permissions)

    def test_user_model_has_superadmin_field(self):
        user = self.create_user_record(email="super-field@example.com", is_superadmin=True)
        self.assertTrue(user.is_superadmin)

    def test_user_model_has_superadmin_only_edit_field(self):
        user = self.create_user_record(email="protected-field@example.com")
        protected_user = self.create_user_record(
            email="protected-field-true@example.com",
            can_only_be_edited_by_superadmin=True,
        )
        self.assertFalse(user.can_only_be_edited_by_superadmin)
        self.assertTrue(protected_user.can_only_be_edited_by_superadmin)

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
        self.assertFalse(any(permission.can_view or permission.can_edit for permission in user.menu_permissions))

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

    def test_login_page_has_password_visibility_toggle_and_no_greeting(self):
        response = self.client.get("/login")
        body = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn('name="password" type="password"', body)
        self.assertIn('data-password-toggle', body)
        self.assertIn('data-password-input="login-password"', body)
        self.assertIn('aria-label="Show password"', body)
        self.assertNotIn("Hello,", body)

    def test_logged_in_layout_shows_escaped_full_name_greeting(self):
        user = self.create_user_record(email="hello@example.com", password="secret123", department="Logistics")
        user.full_name = "Pablo <Admin>"
        db.session.add(UserMenuPermission(user_id=user.id, menu_key="staff_members", can_view=True))
        db.session.commit()

        response = self.client.post(
            "/login",
            data={"email": "hello@example.com", "password": "secret123"},
            follow_redirects=True,
        )
        body = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("Hello, Pablo &lt;Admin&gt;!", body)
        self.assertNotIn("Hello, Pablo <Admin>!", body)

    def test_logged_in_greeting_falls_back_without_empty_values(self):
        client = self.app.test_client()
        with client.session_transaction() as user_session:
            user_session["user"] = "fallback@example.com"
            user_session["user_full_name"] = ""
            user_session["user_email"] = "fallback@example.com"
            user_session["csrf_token"] = "token"

        response = client.get("/")
        body = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("Hello, fallback@example.com!", body)
        self.assertNotIn("Hello, None", body)
        self.assertNotIn("Hello, null", body)
        self.assertNotIn("Hello, undefined", body)

    def test_logout_clears_greeting_from_login_page(self):
        client = self.app.test_client()
        with client.session_transaction() as user_session:
            user_session["user"] = "Logout User"
            user_session["user_full_name"] = "Logout User"
            user_session["user_email"] = "logout@example.com"
            user_session["csrf_token"] = "token"

        response = client.post("/logout", follow_redirects=True)
        body = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("Internal team portal", body)
        self.assertNotIn("Hello, Logout User", body)

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
        inactive_user = self.create_user_record(
            email="inactive-visible@example.com",
            password="secret123",
            department="Finance",
            is_active=False,
        )
        response = self.admin_client().get("/users")
        body = response.get_data(as_text=True)
        self.assertIn("Users", body)
        self.assertIn("New user", body)
        self.assertIn("Full name", body)
        self.assertIn("Email", body)
        self.assertIn("Department", body)
        self.assertIn("Password", body)
        self.assertIn("visible@example.com", body)
        self.assertIn("MANAGEMENT", body)
        self.assertIn("users-department-chip", body)
        self.assertIn("status-active", body)
        self.assertIn("FINANCE", body)
        self.assertIn("status-inactive", body)
        self.assertIn("Active", body)
        self.assertNotIn(user.password_hash, body)
        self.assertNotIn(inactive_user.password_hash, body)
        self.assertIn("Menu permissions", body)
        self.assertIn("Permission management scope", body)
        self.assertIn("Can manage permissions", body)
        for _menu_key, label in MENU_PERMISSIONS:
            self.assertIn(label, body)
        self.assertIn("View information", body)
        self.assertIn("Edit information", body)
        self.assertNotIn("Superadmin", body)

    def test_users_view_only_can_list_but_not_mutate(self):
        client, _user = self.permission_client({"users": {"view": True}})
        response = client.get("/users")
        body = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn("View-only access", body)
        self.assertIn("Your account can view this menu, but does not have permission to edit information.", body)
        self.assertNotIn("New user", body)
        self.assertNotIn("Edit user", body)

        response = client.post(
            "/users",
            data={
                "csrf_token": "token",
                "full_name": "Blocked",
                "email": "blocked@example.com",
                "department": "Finance",
                "password": "secret123",
            },
            headers={"Referer": "http://localhost/users"},
        )
        self.assertEqual(response.status_code, 403)
        body = response.get_data(as_text=True)
        self.assertIn("Access denied", body)
        self.assertIn("Your account does not have permission to perform this action.", body)
        self.assertIn("Back to previous page", body)
        self.assertIn("app-shell", body)
        self.assertNotIn("<title>403 Forbidden</title>", body)
        self.assertIsNone(User.query.filter_by(email="blocked@example.com").first())

    def test_users_edit_can_create_permissions_and_backend_corrects_view(self):
        client, _user = self.permission_client({"users": {"edit": True, "manage": True}, "fees": {"view": True, "manage": True}})
        response = client.post(
            "/users",
            data={
                "csrf_token": "token",
                "full_name": "Permitted",
                "email": "permitted@example.com",
                "department": "Finance",
                "password": "secret123",
                "permissions[users][edit]": "1",
                "permissions[fees][edit]": "1",
                "scope[fees][manage]": "1",
            },
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)
        user = User.query.filter_by(email="permitted@example.com").first()
        fee_permission = UserMenuPermission.query.filter_by(user_id=user.id, menu_key="fees").first()
        self.assertTrue(fee_permission.can_view)
        self.assertTrue(fee_permission.can_edit)
        self.assertTrue(fee_permission.can_manage_permissions)

    def test_self_permissions_are_read_only_and_post_is_blocked(self):
        client, user = self.permission_client({
            "users": {"edit": True, "manage": True},
            "fees": {"view": True, "manage": True},
        })
        response = client.get("/users")
        body = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(user.email, body)
        own_modal = self.html_fragment(body, f'id="edit-user-{user.id}"')
        self.assertIn('data-permission-edit="users"', own_modal)
        self.assertIn("disabled", own_modal)
        self.assertIn('data-permission-read-only="true"', own_modal)
        self.assertRegex(
            own_modal,
            r'(?s)name="scope\[users\]\[manage\]".*data-permission-scope="users".*disabled',
        )

        response = client.post(
            f"/users/{user.id}",
            data={
                "csrf_token": "token",
                "full_name": user.full_name,
                "email": user.email,
                "department": user.department,
                "status": "Active",
                "permissions[fees][edit]": "1",
            },
        )
        self.assertEqual(response.status_code, 403)
        fee_permission = UserMenuPermission.query.filter_by(user_id=user.id, menu_key="fees").first()
        self.assertFalse(fee_permission.can_edit)

    def test_superadmin_bypasses_permissions_and_sees_all_rows_and_field(self):
        client, superadmin = self.permission_client({}, email="super@example.com", department="Admin", is_superadmin=True)
        response = client.get("/users")
        body = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn("Superadmin", body)
        self.assertIn("Can only be edited by superadmin", body)
        self.assertIn("Staff members", body)
        self.assertIn("Providers", body)
        self.assertIn("Permission management scope", body)
        self.assertIn(superadmin.email, body)

    def test_superadmin_can_create_and_update_superadmin_only_edit_users(self):
        client, _superadmin = self.permission_client({}, email="protected-super@example.com", department="Admin", is_superadmin=True)
        response = client.post(
            "/users",
            data={
                "csrf_token": "token",
                "full_name": "Protected User",
                "email": "protected-user@example.com",
                "department": "Finance",
                "password": "secret123",
                "can_only_be_edited_by_superadmin": "1",
            },
        )
        self.assertEqual(response.status_code, 302)
        user = User.query.filter_by(email="protected-user@example.com").first()
        self.assertIsNotNone(user)
        self.assertTrue(user.can_only_be_edited_by_superadmin)

        response = client.post(
            f"/users/{user.id}",
            data={
                "csrf_token": "token",
                "full_name": "Protected User",
                "email": "protected-user@example.com",
                "department": "Finance",
                "status": "Active",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(User.query.get(user.id).can_only_be_edited_by_superadmin)

    def test_non_superadmin_cannot_see_or_edit_superadmin_only_edit_users(self):
        protected_user = self.create_user_record(
            email="protected-visible@example.com",
            department="Finance",
            can_only_be_edited_by_superadmin=True,
        )
        client, _editor = self.permission_client({"users": {"edit": True, "manage": True}}, email="protected-editor@example.com")
        response = client.get("/users")
        body = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn("protected-visible@example.com", body)
        self.assertNotIn("Can only be edited by superadmin", body)
        self.assertNotIn("can_only_be_edited_by_superadmin", body)
        self.assertNotIn(f'data-open-modal="edit-user-{protected_user.id}"', body)
        self.assertNotIn(f'id="edit-user-{protected_user.id}"', body)

        response = client.post(
            f"/users/{protected_user.id}",
            data={
                "csrf_token": "token",
                "full_name": "Manipulated Name",
                "email": protected_user.email,
                "department": protected_user.department,
                "status": "Inactive",
                "permissions[users][edit]": "1",
                "scope[users][manage]": "1",
            },
        )
        self.assertEqual(response.status_code, 403)
        body = response.get_data(as_text=True)
        self.assertIn("Access denied", body)
        self.assertIn("Your account does not have permission to perform this action.", body)
        db.session.refresh(protected_user)
        self.assertEqual(protected_user.full_name, "Person Example")
        self.assertTrue(protected_user.is_active)
        self.assertTrue(protected_user.can_only_be_edited_by_superadmin)

    def test_non_superadmin_cannot_set_superadmin_only_edit_by_post(self):
        client, _editor = self.permission_client({"users": {"edit": True, "manage": True}}, email="protected-injector@example.com")
        response = client.post(
            "/users",
            data={
                "csrf_token": "token",
                "full_name": "Injected Protected",
                "email": "injected-protected@example.com",
                "department": "Finance",
                "password": "secret123",
                "can_only_be_edited_by_superadmin": "1",
            },
        )
        self.assertEqual(response.status_code, 403)
        self.assertIsNone(User.query.filter_by(email="injected-protected@example.com").first())

    def test_non_superadmin_cannot_see_or_edit_superadmin_profile(self):
        superadmin = self.create_user_record(email="hidden-super@example.com", department="Admin", is_superadmin=True)
        client, _editor = self.permission_client({
            "users": {"edit": True, "manage": True},
        }, email="regular-editor@example.com")
        response = client.get("/users")
        body = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("hidden-super@example.com", body)
        self.assertNotIn("Superadmin", body)
        self.assertNotIn("is_superadmin", body)

        response = client.post(
            f"/users/{superadmin.id}",
            data={
                "csrf_token": "token",
                "full_name": "Edited",
                "email": "hidden-super@example.com",
                "department": "Admin",
                "status": "Active",
            },
        )
        self.assertEqual(response.status_code, 403)
        self.assertIn("Access denied", response.get_data(as_text=True))
        self.assertNotIn("Superadmin", response.get_data(as_text=True))

    def test_non_superadmin_cannot_set_superadmin_by_post(self):
        client, _editor = self.permission_client({"users": {"edit": True, "manage": True}}, email="not-super@example.com")
        response = client.post(
            "/users",
            data={
                "csrf_token": "token",
                "full_name": "Injected Super",
                "email": "injected-super@example.com",
                "department": "Admin",
                "password": "secret123",
                "is_superadmin": "1",
            },
        )
        self.assertEqual(response.status_code, 403)
        self.assertIsNone(User.query.filter_by(email="injected-super@example.com").first())

    def test_superadmin_uniqueness_and_active_lockout_are_enforced(self):
        client, superadmin = self.permission_client({}, email="unique-super@example.com", department="Admin", is_superadmin=True)
        target = self.create_user_record(email="regular-target@example.com", department="Admin")
        response = client.post(
            f"/users/{target.id}",
            data={
                "csrf_token": "token",
                "full_name": target.full_name,
                "email": target.email,
                "department": target.department,
                "status": "Active",
                "is_superadmin": "1",
            },
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(User.query.get(target.id).is_superadmin)

        response = client.post(
            f"/users/{superadmin.id}",
            data={
                "csrf_token": "token",
                "full_name": superadmin.full_name,
                "email": superadmin.email,
                "department": superadmin.department,
                "status": "Inactive",
            },
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("At least one active Superadmin is required.", response.get_data(as_text=True))
        self.assertTrue(User.query.get(superadmin.id).is_active)

    def test_permission_management_scope_visibility_depends_on_target_users_edit(self):
        editor_client, _editor = self.permission_client({
            "users": {"edit": True, "manage": True},
            "fees": {"view": True, "manage": True},
        })
        no_users_edit = self.create_user_record(email="no-users-edit@example.com", department="Finance")
        db.session.add(UserMenuPermission(user_id=no_users_edit.id, menu_key="fees", can_view=True, can_edit=True, can_manage_permissions=True))
        users_edit = self.create_user_record(email="users-edit@example.com", department="Finance")
        db.session.add(UserMenuPermission(user_id=users_edit.id, menu_key="users", can_view=True, can_edit=True, can_manage_permissions=True))
        db.session.commit()

        response = editor_client.get("/users")
        body = response.get_data(as_text=True)
        create_modal = self.html_fragment(body, 'id="create-user"', f'id="edit-user-{no_users_edit.id}"')
        no_users_edit_modal = self.html_fragment(body, f'id="edit-user-{no_users_edit.id}"', f'id="edit-user-{users_edit.id}"')
        users_edit_modal = self.html_fragment(body, f'id="edit-user-{users_edit.id}"')

        self.assertIn("data-permission-management-scope", create_modal)
        self.assertIn("hidden", create_modal)
        self.assertIn("data-permission-management-scope", no_users_edit_modal)
        self.assertIn("hidden", no_users_edit_modal)
        self.assertIn("data-permission-management-scope", users_edit_modal)
        self.assertNotIn("data-permission-management-scope\n  hidden", users_edit_modal)
        self.assertIn('data-permission-edit="users"', users_edit_modal)

    def test_limited_permission_management_scope_limits_visible_rows(self):
        client, _user = self.permission_client({
            "users": {"edit": True},
            "exam_session_planner": {"view": True, "manage": True},
            "pre_session_control_tower": {"view": True, "manage": True},
        })
        response = client.get("/users")
        body = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn("Menu permissions", body)
        self.assertIn("Permission management scope", body)
        self.assertIn("You can only manage permissions for the menus assigned to your permission management scope.", body)
        self.assertIn("Exam session planner", body)
        self.assertIn("Pre-session Control Tower", body)
        self.assertNotIn("Staff members", body)
        self.assertNotIn("Fees", body)
        self.assertNotIn("Providers", body)

    def test_manage_scope_without_own_menu_permission_is_not_visible_or_editable(self):
        client, _editor = self.permission_client({
            "users": {"edit": True, "manage": True},
            "fees": {"manage": True},
            "staff_payments": {"manage": True},
        }, email="scope-without-permission@example.com")
        target = self.create_user_record(email="scope-without-permission-target@example.com", department="Finance")
        target.full_name = "ZZZ Scope Without Permission Target"
        db.session.commit()
        self.add_menu_permission(target, "fees", view=True, edit=True, manage=True)
        self.add_menu_permission(target, "staff_payments", view=True, edit=True, manage=True)

        response = client.get("/users")
        body = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        create_modal = self.html_fragment(body, 'id="create-user"', f'id="edit-user-{target.id}"')
        target_modal = self.html_fragment(body, f'id="edit-user-{target.id}"')
        self.assertNotIn("Fees", create_modal)
        self.assertNotIn("Staff payments", create_modal)
        self.assertNotIn("Fees", target_modal)
        self.assertNotIn("Staff payments", target_modal)

        response = client.post(
            f"/users/{target.id}",
            data={
                "csrf_token": "token",
                "full_name": "Manipulated",
                "email": target.email,
                "department": target.department,
                "status": "Active",
                "permissions[fees][view]": "1",
            },
        )
        self.assertEqual(response.status_code, 403)
        db.session.refresh(target)
        self.assertEqual(target.full_name, "ZZZ Scope Without Permission Target")

    def test_non_superadmin_edit_modal_shows_only_permission_intersection(self):
        client, _editor = self.permission_client({
            "staff_members": {"view": True, "manage": True},
            "examiner_certification": {"view": True, "manage": True},
            "supervisor_certification": {"view": True, "manage": True},
            "users": {"edit": True, "manage": True},
        }, email="intersection-editor@example.com")
        target = self.create_user_record(email="intersection-target@example.com", department="Finance")
        target.full_name = "ZZZ Intersection Target"
        db.session.commit()
        self.add_menu_permission(target, "staff_members", view=True, edit=True)
        self.add_menu_permission(target, "examiner_certification", view=True)
        self.add_menu_permission(target, "supervisor_certification", view=True, edit=True)
        self.add_menu_permission(target, "fees", view=True, edit=True, manage=True)

        response = client.get("/users")
        body = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        target_modal = self.html_fragment(body, f'id="edit-user-{target.id}"')

        self.assertIn("Staff members", target_modal)
        self.assertIn("Examiner certification", target_modal)
        self.assertIn("Supervisor certification", target_modal)
        self.assertNotIn("Fees", target_modal)
        self.assertNotIn('data-permission-edit="users"', target_modal)
        self.assertNotIn(">Users<", target_modal)

    def test_intersection_preserves_hidden_permissions_and_blocks_manipulated_post(self):
        client, _editor = self.permission_client({
            "staff_members": {"view": True, "manage": True},
            "examiner_certification": {"view": True, "manage": True},
            "supervisor_certification": {"view": True, "manage": True},
            "users": {"edit": True, "manage": True},
        }, email="intersection-save-editor@example.com")
        target = self.create_user_record(email="intersection-save-target@example.com", department="Finance")
        target.full_name = "ZZZ Intersection Save Target"
        db.session.commit()
        self.add_menu_permission(target, "staff_members", view=True, edit=False)
        self.add_menu_permission(target, "examiner_certification", view=True, edit=True)
        self.add_menu_permission(target, "supervisor_certification", view=True, edit=True)
        self.add_menu_permission(target, "fees", view=True, edit=True, manage=True)

        response = client.post(
            f"/users/{target.id}",
            data={
                "csrf_token": "token",
                "full_name": "Intersection Updated",
                "email": target.email,
                "department": target.department,
                "status": "Active",
                "permissions[staff_members][edit]": "1",
            },
        )
        self.assertEqual(response.status_code, 302)
        fees_permission = UserMenuPermission.query.filter_by(user_id=target.id, menu_key="fees").first()
        staff_permission = UserMenuPermission.query.filter_by(user_id=target.id, menu_key="staff_members").first()
        self.assertTrue(fees_permission.can_view)
        self.assertTrue(fees_permission.can_edit)
        self.assertTrue(fees_permission.can_manage_permissions)
        self.assertTrue(staff_permission.can_edit)

        response = client.post(
            f"/users/{target.id}",
            data={
                "csrf_token": "token",
                "full_name": "Manipulated Intersection",
                "email": target.email,
                "department": target.department,
                "status": "Active",
                "permissions[fees][view]": "1",
            },
        )
        self.assertEqual(response.status_code, 403)
        db.session.refresh(fees_permission)
        db.session.refresh(target)
        self.assertEqual(target.full_name, "Intersection Updated")
        self.assertTrue(fees_permission.can_view)
        self.assertTrue(fees_permission.can_edit)
        self.assertTrue(fees_permission.can_manage_permissions)

    def test_superadmin_edit_modal_is_not_limited_by_permission_intersection(self):
        client, _superadmin = self.permission_client({}, email="intersection-super@example.com", department="Admin", is_superadmin=True)
        target = self.create_user_record(email="intersection-super-target@example.com", department="Finance")
        target.full_name = "ZZZ Intersection Super Target"
        db.session.commit()
        self.add_menu_permission(target, "fees", view=True, edit=True)

        response = client.get("/users")
        body = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        target_modal = self.html_fragment(body, f'id="edit-user-{target.id}"')

        self.assertIn("Staff members", target_modal)
        self.assertIn("Fees", target_modal)
        self.assertIn('data-permission-edit="users"', target_modal)

    def test_limited_scope_preserves_hidden_permissions_on_update(self):
        client, _editor = self.permission_client({
            "users": {"edit": True},
            "fees": {"view": True, "manage": True},
        })
        target = self.create_user_record(email="target@example.com", department="Finance")
        db.session.add(UserMenuPermission(user_id=target.id, menu_key="staff_members", can_view=True, can_edit=True, can_manage_permissions=True))
        db.session.add(UserMenuPermission(user_id=target.id, menu_key="fees", can_view=True, can_edit=False, can_manage_permissions=False))
        db.session.add(UserMenuPermission(user_id=target.id, menu_key="users", can_view=True, can_edit=True, can_manage_permissions=True))
        db.session.commit()

        response = client.post(
            f"/users/{target.id}",
            data={
                "csrf_token": "token",
                "full_name": "Target Updated",
                "email": "target@example.com",
                "department": "Finance",
                "status": "Active",
                "permissions[fees][view]": "1",
            },
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)
        staff_permission = UserMenuPermission.query.filter_by(user_id=target.id, menu_key="staff_members").first()
        fee_permission = UserMenuPermission.query.filter_by(user_id=target.id, menu_key="fees").first()
        self.assertTrue(staff_permission.can_view)
        self.assertTrue(staff_permission.can_edit)
        self.assertTrue(staff_permission.can_manage_permissions)
        self.assertTrue(fee_permission.can_view)
        self.assertFalse(fee_permission.can_edit)

    def test_scope_is_cleared_when_saved_user_lacks_users_edit(self):
        client, _editor = self.permission_client({
            "users": {"edit": True, "manage": True},
            "fees": {"view": True, "manage": True},
        })
        response = client.post(
            "/users",
            data={
                "csrf_token": "token",
                "full_name": "No Users Edit",
                "email": "no-users-scope@example.com",
                "department": "Finance",
                "password": "secret123",
                "permissions[fees][view]": "1",
                "scope[fees][manage]": "1",
            },
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)
        user = User.query.filter_by(email="no-users-scope@example.com").first()
        fee_permission = UserMenuPermission.query.filter_by(user_id=user.id, menu_key="fees").first()
        self.assertTrue(fee_permission.can_view)
        self.assertFalse(fee_permission.can_manage_permissions)

    def test_limited_scope_blocks_manipulated_post_outside_scope(self):
        client, _editor = self.permission_client({
            "users": {"edit": True},
            "fees": {"view": True, "manage": True},
        })
        target = self.create_user_record(email="blocked-target@example.com", department="Finance")
        db.session.add(UserMenuPermission(user_id=target.id, menu_key="staff_members", can_view=False, can_edit=False, can_manage_permissions=False))
        db.session.commit()

        response = client.post(
            f"/users/{target.id}",
            data={
                "csrf_token": "token",
                "full_name": "Blocked Target",
                "email": "blocked-target@example.com",
                "department": "Finance",
                "status": "Active",
                "permissions[staff_members][edit]": "1",
            },
        )
        self.assertEqual(response.status_code, 403)
        staff_permission = UserMenuPermission.query.filter_by(user_id=target.id, menu_key="staff_members").first()
        self.assertFalse(staff_permission.can_view)
        self.assertFalse(staff_permission.can_edit)

    def test_limited_scope_create_user_cannot_assign_hidden_permissions(self):
        client, _editor = self.permission_client({
            "users": {"edit": True},
            "fees": {"view": True, "manage": True},
        })
        response = client.post(
            "/users",
            data={
                "csrf_token": "token",
                "full_name": "Scoped New",
                "email": "scoped-new@example.com",
                "department": "Finance",
                "password": "secret123",
                "permissions[fees][view]": "1",
                "permissions[staff_members][edit]": "1",
            },
        )
        self.assertEqual(response.status_code, 403)
        self.assertIsNone(User.query.filter_by(email="scoped-new@example.com").first())

        response = client.post(
            "/users",
            data={
                "csrf_token": "token",
                "full_name": "Scoped New",
                "email": "scoped-new@example.com",
                "department": "Finance",
                "password": "secret123",
                "permissions[fees][view]": "1",
            },
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)
        user = User.query.filter_by(email="scoped-new@example.com").first()
        self.assertIsNotNone(user)
        self.assertIsNotNone(UserMenuPermission.query.filter_by(user_id=user.id, menu_key="fees").first())
        self.assertIsNone(UserMenuPermission.query.filter_by(user_id=user.id, menu_key="staff_members").first())

    def test_cannot_remove_last_active_users_permission_manager(self):
        client, user = self.permission_client({"users": {"edit": True, "manage": True}})
        response = client.post(
            f"/users/{user.id}",
            data={
                "csrf_token": "token",
                "full_name": user.full_name,
                "email": user.email,
                "department": user.department,
                "status": "Active",
                "permissions[users][edit]": "1",
            },
        )
        self.assertEqual(response.status_code, 403)
        self.assertIn("Access denied", response.get_data(as_text=True))

    def test_sidebar_hides_menus_without_permission(self):
        client, _user = self.permission_client({
            "staff_members": {"view": True},
            "fees": {"view": True},
        })
        response = client.get("/")
        body = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn("Staff members", body)
        self.assertIn("Fees", body)
        self.assertNotIn("Exam session planner", body)
        self.assertNotIn("Pre-session Control Tower", body)
        self.assertNotIn(">Users<", body)

    def test_view_only_banner_repeats_on_key_menus_and_not_for_edit(self):
        view_only_client, _user = self.permission_client({
            "staff_members": {"view": True},
            "exam_session_planner": {"view": True},
            "pre_session_control_tower": {"view": True},
            "fees": {"view": True},
            "providers": {"view": True},
            "users": {"view": True},
        })
        for url in ("/", "/exam-session-planner", "/pre-session-control-tower", "/fees", "/providers", "/users"):
            response = view_only_client.get(url)
            self.assertEqual(response.status_code, 200, url)
            self.assertIn("View-only access", response.get_data(as_text=True), url)

        edit_client, _user = self.permission_client({
            "staff_members": {"edit": True},
            "fees": {"edit": True},
            "providers": {"edit": True},
            "users": {"edit": True},
        }, email="edit-perm@example.com")
        for url in ("/", "/fees", "/providers", "/users"):
            response = edit_client.get(url)
            self.assertEqual(response.status_code, 200, url)
            self.assertNotIn("View-only access", response.get_data(as_text=True), url)

    def test_direct_url_requires_menu_view_and_post_requires_edit(self):
        client, _user = self.permission_client({"fees": {"view": True}})
        self.assertEqual(client.get("/fees").status_code, 200)
        response = client.get("/providers")
        self.assertEqual(response.status_code, 403)
        body = response.get_data(as_text=True)
        self.assertIn("Access denied", body)
        self.assertIn("Your account does not have permission to view this menu.", body)
        self.assertIn("Go back", body)
        self.assertIn("app-shell", body)
        response = client.post(
            "/fees",
            data={
                "csrf_token": "token",
                "fee_description": "Blocked fee",
                "currency": "USD",
                "fee_value": "10",
                "unit_of_measure": "Per session",
            },
        )
        self.assertEqual(response.status_code, 403)
        self.assertIn("Access denied", response.get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
