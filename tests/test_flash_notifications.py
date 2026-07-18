import os
import unittest

os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from flask import flash, render_template_string

from app import create_app, db


class FlashNotificationTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config["TESTING"] = True
        self.app.config["WTF_CSRF_ENABLED"] = False
        self.ctx = self.app.app_context()
        self.ctx.push()
        db.drop_all()
        db.create_all()

        @self.app.route("/flash-notification-test")
        def flash_notification_test():
            flash("Saved successfully.", "success")
            flash("Something went wrong.", "error")
            flash("Please check this warning.", "warning")
            flash("For your information.", "info")
            return render_template_string("{% extends 'base.html' %}{% block content %}<p>Flash test</p>{% endblock %}")

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def test_each_flash_renders_dismiss_button(self):
        response = self.app.test_client().get("/flash-notification-test")
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("Saved successfully.", html)
        self.assertIn("Something went wrong.", html)
        self.assertIn("Please check this warning.", html)
        self.assertIn("For your information.", html)
        self.assertEqual(html.count('data-dismissible-flash'), 4)
        self.assertEqual(html.count('data-dismiss-flash'), 4)
        self.assertEqual(html.count('type="button" aria-label="Dismiss notification"'), 4)

    def test_success_error_warning_and_info_have_close_buttons(self):
        response = self.app.test_client().get("/flash-notification-test")
        html = response.get_data(as_text=True)

        for category in ("success", "error", "warning", "info"):
            self.assertRegex(
                html,
                rf'<div class="flash {category}" data-dismissible-flash>[\s\S]*?<button class="flash-close-button" type="button" aria-label="Dismiss notification" data-dismiss-flash>',
            )

    def test_flash_text_is_not_changed(self):
        response = self.app.test_client().get("/flash-notification-test")
        html = response.get_data(as_text=True)

        self.assertIn('<span class="flash-message">Saved successfully.</span>', html)
        self.assertIn('<span class="flash-message">Something went wrong.</span>', html)

    def test_flash_javascript_has_delegated_single_notification_dismissal(self):
        with open("app/static/js/app.js", encoding="utf-8") as script_file:
            script = script_file.read()

        self.assertIn('document.addEventListener("click"', script)
        self.assertIn("[data-dismiss-flash]", script)
        self.assertIn('closest?.("[data-dismissible-flash], .flash")', script)
        self.assertIn("flash.remove()", script)
        self.assertIn("!stack.children.length", script)


if __name__ == "__main__":
    unittest.main()
