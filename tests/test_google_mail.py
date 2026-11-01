import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from app import create_app, db
from app.google_mail import SEND_SCOPE, read_connection, save_connection


class GoogleMailTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.environment = patch.dict(os.environ, {
            "GOOGLE_OAUTH_CLIENT_ID": "client-test", "GOOGLE_OAUTH_CLIENT_SECRET": "secret-test",
            "GOOGLE_OAUTH_REDIRECT_URI": "http://localhost/integrations/google/callback",
            "GMAIL_ACCOUNT_EMAIL": "pablo.demarchi@pathexaminations.com",
            "GMAIL_TOKEN_FILE": str(Path(self.temp.name) / "token.json"),
        })
        self.environment.start()
        self.app = create_app()
        self.app.config["TESTING"] = True
        self.ctx = self.app.app_context()
        self.ctx.push()
        db.drop_all()
        db.create_all()
        self.client = self.app.test_client()
        with self.client.session_transaction() as session:
            session.update(user="admin", user_department="Admin", csrf_token="test")

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()
        self.environment.stop()
        self.temp.cleanup()

    def connect(self):
        response = self.client.post("/integrations/google/connect", data={"csrf_token": "test"})
        return parse_qs(urlsplit(response.location).query)

    def test_connection_requests_send_scope_offline_access_and_pkce(self):
        values = self.connect()
        self.assertIn(SEND_SCOPE, values["scope"][0])
        self.assertNotIn("gmail.readonly", values["scope"][0])
        self.assertEqual(values["access_type"], ["offline"])
        self.assertEqual(values["code_challenge_method"], ["S256"])
        self.assertTrue(values["state"][0])
        self.assertNotIn("secret-test", str(values))

    def test_success_is_persistent_private_and_does_not_send_mail(self):
        state = self.connect()["state"][0]
        with patch("app.google_mail.google_json", side_effect=[
            {"access_token": "access-test", "refresh_token": "refresh-test", "scope": SEND_SCOPE},
            {"email": "pablo.demarchi@pathexaminations.com", "email_verified": True},
        ]) as network:
            response = self.client.get("/integrations/google/callback", query_string={"state": state, "code": "code-test"}, follow_redirects=True)
        self.assertEqual(network.call_count, 2)
        self.assertEqual(response.status_code, 200)
        self.assertIn("Google account connected", response.get_data(as_text=True))
        for secret in ["access-test", "refresh-test", "secret-test", "code-test"]:
            self.assertNotIn(secret, response.get_data(as_text=True))
        self.assertEqual(read_connection()["refresh_token"], "refresh-test")
        self.assertEqual((Path(self.temp.name) / "token.json").stat().st_mode & 0o777, 0o600)
        self.assertEqual(response.headers["Cache-Control"], "private, no-store")
        with patch("app.google_mail.google_json") as network:
            self.client.get("/integrations/google/callback", query_string={"state": state, "code": "code-test"})
            network.assert_not_called()

    def test_invalid_or_expired_state_never_contacts_google(self):
        self.connect()
        with patch("app.google_mail.google_json") as network:
            self.client.get("/integrations/google/callback?state=invalid&code=secret")
            network.assert_not_called()
        state = self.connect()["state"][0]
        with self.client.session_transaction() as session:
            saved = session["google_mail_oauth"]
            saved["started"] = time.time() - 700
            session["google_mail_oauth"] = saved
        with patch("app.google_mail.google_json") as network:
            self.client.get("/integrations/google/callback", query_string={"state": state, "code": "test"})
            network.assert_not_called()

    def test_wrong_account_or_missing_scope_does_not_replace_connection(self):
        save_connection({"account": "existing", "refresh_token": "existing-token"})
        for tokens, identity in [
            ({"access_token": "access", "refresh_token": "new-token", "scope": "openid"}, {}),
            ({"access_token": "access", "refresh_token": "new-token", "scope": SEND_SCOPE}, {"email": "someone@example.com", "email_verified": True}),
        ]:
            state = self.connect()["state"][0]
            with patch("app.google_mail.google_json", side_effect=[tokens, identity]):
                self.client.get("/integrations/google/callback", query_string={"state": state, "code": "test"})
            self.assertEqual(read_connection()["refresh_token"], "existing-token")

    def test_authorization_requires_administrator_and_csrf(self):
        self.assertEqual(self.app.test_client().get("/integrations/google").status_code, 302)
        self.assertEqual(self.client.post("/integrations/google/connect").status_code, 400)
        with self.client.session_transaction() as session:
            session["user_department"] = "Logistics"
        self.assertEqual(self.client.get("/integrations/google").status_code, 403)

    def test_mismatched_domain_does_not_start_authorization(self):
        with patch.dict(os.environ, {"GOOGLE_OAUTH_REDIRECT_URI": "https://portal.pathinternalportal.com/integrations/google/callback"}):
            response = self.client.post("/integrations/google/connect", data={"csrf_token": "test"})
        self.assertEqual(urlsplit(response.location).path, "/integrations/google")
        with self.client.session_transaction() as session:
            self.assertNotIn("google_mail_oauth", session)
