import os
import unittest
from datetime import date
from unittest.mock import patch

os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from app import create_app, db
from app.models import ExamSession, ExamSessionLogisticsConcept, ProviderType
from app.rich_text import sanitize_instructions
from app.routes import save_exam_session_logistics


class LogisticsInstructionsTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config["TESTING"] = True
        self.context = self.app.app_context()
        self.context.push()
        db.drop_all()
        db.create_all()
        self.record = ExamSession(exam_session_name="Instructions test", category="Path School",
                                  status="Pending", session_date=date(2026, 11, 10),
                                  shifts="Morning", modules="Speaking", format="Onsite")
        db.session.add(self.record)
        db.session.flush()
        self.concept = ExamSessionLogisticsConcept(exam_session_id=self.record.id)
        db.session.add(self.concept)
        db.session.commit()
        self.client = self.app.test_client()
        with self.client.session_transaction() as state:
            state.update(user="admin", csrf_token="test")
        self.url = f"/exam-session-planner/logistics-concepts/{self.concept.id}/instructions"

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def test_save_edit_delete_and_render(self):
        content = '<ul><li><b>Bring materials</b> <i>early</i></li></ul><font size="4">Large</font><a href="https://example.com">Link</a>'
        response = self.client.post(self.url, data={"csrf_token": "test", "instructions": content})
        self.assertEqual(response.status_code, 200)
        self.assertIn('<font size="4">', self.concept.instructions_html)
        page = self.client.get("/exam-session-planner?session_year=2026").get_data(as_text=True)
        self.assertLess(page.index('>Staff members</th>'), page.index('>Instructions</th>'))
        self.assertLess(page.index('>Instructions</th>'), page.index('>Provider details</th>'))
        self.assertIn('aria-label="View or edit instructions"', page)
        self.assertEqual(self.client.post(self.url, data={"csrf_token": "test", "instructions": "<p>Edited</p>"}).status_code, 200)
        self.assertEqual(self.concept.instructions_html, "<p>Edited</p>")
        self.assertEqual(self.client.post(self.url, data={"csrf_token": "test", "instructions": ""}).status_code, 200)
        self.assertEqual(self.concept.instructions_html, "")
        page = self.client.get("/exam-session-planner?session_year=2026").get_data(as_text=True)
        self.assertIn('aria-label="Add instructions"', page)

    def test_rejects_missing_csrf_view_only_and_oversize(self):
        self.assertEqual(self.client.post(self.url, data={"instructions": "text"}).status_code, 400)
        with patch("app.routes.user_can_edit", return_value=False):
            self.assertEqual(self.client.post(self.url, data={"csrf_token": "test", "instructions": "text"}).status_code, 403)
        self.assertEqual(self.client.post(self.url, data={"csrf_token": "test", "instructions": "x" * 50001}).status_code, 400)
        self.assertEqual(self.concept.instructions_html, "")

    def test_draft_instructions_save_with_new_concept(self):
        provider_type = ProviderType(name="Transport")
        db.session.add(provider_type)
        db.session.commit()
        with self.app.test_request_context(method="POST", data={
            "logistics_concept_row_keys": "new-1", "logistics_status_new-1": "Pending",
            "logistics_provider_type_id_new-1": str(provider_type.id),
            "logistics_instructions_new-1": "<ol><li><strong>First</strong></li></ol>",
        }):
            self.assertTrue(save_exam_session_logistics(self.record))
            db.session.commit()
        draft = ExamSessionLogisticsConcept.query.filter(ExamSessionLogisticsConcept.id != self.concept.id).one()
        self.assertEqual(draft.instructions_html, "<ol><li><strong>First</strong></li></ol>")

    def test_sanitizer_keeps_formatting_without_active_content(self):
        result = sanitize_instructions('<p onclick="bad()"><b>Bold</b><img src=x onerror=bad()><a href="javascript:bad()">bad</a><a href="https://[">invalid</a><iframe src="bad"></iframe></p>')
        self.assertIn("<b>Bold</b>", result)
        for unsafe in ("onclick", "onerror", "javascript:", "<img", "<iframe"):
            self.assertNotIn(unsafe, result)
        self.assertEqual(sanitize_instructions("<div><br></div>"), "")


if __name__ == "__main__":
    unittest.main()
