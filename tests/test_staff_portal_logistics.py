import os
import unittest
from datetime import date

os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from app import create_app, db
from app.models import (AcademicStaff, ExamSession, ExamSessionScheduleWorkflow,
                        ExamSessionExaminerAssignment, ExamSessionSupervisorAssignment,
                        ExamSessionInternAssignment, StaffExamSessionSubmission, StaffExamSessionsShare,
                        ExamSessionLogistics, ExamSessionLogisticsConcept, ProviderType)
from app.routes import complex_logistics_staff_members_for_session, save_exam_session_logistics


class StaffPortalLogisticsTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config["TESTING"] = True
        self.context = self.app.app_context()
        self.context.push()
        db.drop_all()
        db.create_all()
        self.record = ExamSession(exam_session_name="Logistics validation", category="Path School",
                                  status="Pending", session_date=date(2026, 11, 10),
                                  shifts="Morning", modules="Speaking", format="Onsite")
        self.person = AcademicStaff(full_name="Test Staff", status="Active", roles="Supervisor, Examiner, Intern")
        db.session.add_all([self.record, self.person])
        db.session.flush()
        db.session.add(ExamSessionScheduleWorkflow(exam_session_id=self.record.id, status="Approved"))
        db.session.commit()
        self.client = self.app.test_client()
        with self.client.session_transaction() as state:
            state.update(user="admin", csrf_token="test")

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def add(self, role, assignment_id):
        return self.client.post(
            f"/pre-session-control-tower/sessions/{self.record.id}/staffing-assignments/{role}/{assignment_id}/submit",
            data={"csrf_token": "test"}, headers={"Accept": "application/json"})

    def test_each_onsite_role_requires_a_logistics_selection(self):
        for role, model in [("supervisor", ExamSessionSupervisorAssignment),
                            ("examiner", ExamSessionExaminerAssignment), ("intern", ExamSessionInternAssignment)]:
            assignment = model(exam_session_id=self.record.id, team_member_id=self.person.id,
                               staffing_role_check_verified=True, participation_status="Pre-confirmed",
                               logistics_type="", logistics_enabled=True)
            db.session.add(assignment)
            db.session.commit()
            before = StaffExamSessionSubmission.query.count()
            response = self.add(role, assignment.id)
            self.assertEqual(response.status_code, 400)
            self.assertIn("Select Logistics", response.json["error"])
            self.assertEqual(StaffExamSessionSubmission.query.count(), before)
            for value in ["Does not apply", "Uber ride", "Complex Uber ride", "Complex logistics", "Carpooling"]:
                assignment.logistics_type = value
                db.session.commit()
                self.assertEqual(self.add(role, assignment.id).status_code, 200)

    def test_remote_supervisor_only_accepts_does_not_apply(self):
        assignment = ExamSessionSupervisorAssignment(exam_session_id=self.record.id, team_member_id=self.person.id,
            staffing_role_check_verified=True, participation_status="Pre-confirmed", is_remote=True)
        db.session.add(assignment)
        for value in ["", "Uber ride", "Complex Uber ride", "Complex logistics", "Carpooling"]:
            assignment.logistics_type = value
            db.session.commit()
            response = self.add("supervisor", assignment.id)
            self.assertEqual(response.status_code, 400)
            self.assertIn("Does not apply", response.json["error"])
            self.assertEqual(StaffExamSessionSubmission.query.count(), 0)
            self.assertEqual(StaffExamSessionsShare.query.count(), 0)
        assignment.logistics_type = "Does not apply"
        db.session.commit()
        self.assertEqual(self.add("supervisor", assignment.id).status_code, 200)

    def test_emergency_contact_does_not_require_logistics(self):
        self.record.emergency_contact_member_id = self.person.id
        self.record.emergency_contact_required = True
        self.record.emergency_contact_role_check_verified = True
        self.record.emergency_contact_participation_status = "Pre-confirmed"
        db.session.commit()
        self.assertEqual(self.add("emergency_contact", self.record.id).status_code, 200)

    def portal_assignment(self, role="examiner"):
        model = ExamSessionSupervisorAssignment if role == "supervisor" else ExamSessionExaminerAssignment
        assignment = model(exam_session_id=self.record.id, team_member_id=self.person.id,
                           staffing_role_check_verified=True, participation_status="Confirmed",
                           logistics_type="Does not apply")
        share = StaffExamSessionsShare(person_ref=str(self.person.id), token="travel-test")
        db.session.add_all([assignment, share])
        db.session.flush()
        db.session.add(StaffExamSessionSubmission(share_id=share.id, exam_session_id=self.record.id,
                                                assignment_type=role, assignment_id=assignment.id))
        db.session.add(ExamSessionLogistics(exam_session_id=self.record.id,
                                           logistics_files_url="https://example.com/travel"))
        db.session.commit()
        return assignment

    def portal_page(self):
        response = self.client.get("/my-exam-sessions/travel-test")
        self.assertEqual(response.status_code, 200)
        return response.get_data(as_text=True)

    def test_exam_centre_contacts_role_scope_and_gmt3_day_boundaries(self):
        import json
        from datetime import datetime, timezone
        from types import SimpleNamespace
        from app.routes import staff_exam_centre_contacts
        self.record.contact_points = json.dumps([{"full_name": "Centre Person", "phone": "12345", "email": "centre@example.com"}])
        ordinary = SimpleNamespace(is_shipment_recipient=False, is_remote=False)
        remote = SimpleNamespace(is_shipment_recipient=False, is_remote=True)
        recipient = SimpleNamespace(is_shipment_recipient=True)
        on_day = datetime(2026, 11, 10, 12, tzinfo=timezone.utc)
        for role, assignment in [("supervisor", ordinary), ("supervisor", remote), ("examiner", recipient), ("emergency_contact", self.record)]:
            with self.subTest(role=role):
                self.assertEqual(len(staff_exam_centre_contacts(self.record, role, assignment, "Confirmed", now=on_day)["contacts"]), 1)
                self.assertIsNone(staff_exam_centre_contacts(self.record, role, assignment, "Pre-confirmed", now=on_day))
        for role in ["examiner", "intern"]:
            self.assertIsNone(staff_exam_centre_contacts(self.record, role, ordinary, "Confirmed", now=on_day))
        for moment, available in [
            (datetime(2026, 11, 10, 2, 59, 59, tzinfo=timezone.utc), False),
            (datetime(2026, 11, 10, 3, tzinfo=timezone.utc), True),
            (datetime(2026, 11, 11, 2, 59, 59, tzinfo=timezone.utc), True),
            (datetime(2026, 11, 11, 3, tzinfo=timezone.utc), False),
        ]:
            result = staff_exam_centre_contacts(self.record, "supervisor", ordinary, "Confirmed", now=moment)
            self.assertEqual(result["available"], available)
            self.assertEqual(len(result["contacts"]), 1 if available else 0)
        self.record.contact_points = "[]"
        self.assertIsNone(staff_exam_centre_contacts(self.record, "supervisor", ordinary, "Confirmed", now=on_day))

    def test_exam_centre_contacts_portal_live_updates_and_hidden_data(self):
        import json
        from datetime import datetime, timezone
        from unittest.mock import patch
        from app.routes import staff_exam_centre_contacts
        assignment = self.portal_assignment()
        assignment.is_shipment_recipient = True
        contacts = [{"full_name": "Centre First", "phone": "+54 11 1234 5678", "email": "centre-first@example.com"},
                    {"full_name": "Centre Second", "phone": "999999", "email": "centre-second@example.com"}]
        self.record.contact_points = json.dumps(contacts)
        db.session.commit()
        def page_at(moment):
            with patch("app.routes.staff_exam_centre_contacts", side_effect=lambda record, role, assignment, status:
                       staff_exam_centre_contacts(record, role, assignment, status, now=moment)):
                return self.portal_page()
        before = page_at(datetime(2026, 11, 10, 2, 59, tzinfo=timezone.utc))
        self.assertIn("Exam centre contact information", before)
        self.assertIn("Available on exam day only", before)
        for contact in contacts:
            for value in contact.values():
                self.assertNotIn(value, before)
        moment = datetime(2026, 11, 10, 3, tzinfo=timezone.utc)
        page = page_at(moment)
        self.assertLess(page.index("Your session team"), page.index('aria-label="Exam centre contact information"'))
        self.assertNotIn("Available on exam day only", page)
        self.assertNotIn("Calls only – No messages", page)
        for contact in contacts:
            for value in contact.values():
                self.assertIn(value, page)
        contacts[0]["phone"] = "UPDATED-PHONE"
        self.record.contact_points = json.dumps(contacts)
        db.session.commit()
        updated = page_at(moment)
        self.assertIn("UPDATED-PHONE", updated)
        self.assertNotIn("+54 11 1234 5678", updated)
        after = page_at(datetime(2026, 11, 11, 3, tzinfo=timezone.utc))
        self.assertNotIn("UPDATED-PHONE", after)
        self.assertIn("Available on exam day only", after)
        assignment.participation_status = "Pre-confirmed"
        db.session.commit()
        self.assertNotIn("Exam centre contact information", page_at(moment))
        assignment.participation_status = "Confirmed"
        self.record.contact_points = "[]"
        db.session.commit()
        self.assertNotIn("Exam centre contact information", page_at(moment))

    def test_travel_texts_labels_and_bold_for_each_option(self):
        assignment = self.portal_assignment()
        db.session.add(ExamSessionLogisticsConcept(exam_session_id=self.record.id,
            instructions_html="<p>Travel instructions</p>", staff_members=[self.person]))
        db.session.commit()
        for value in ["Does not apply", "Uber ride", "Complex Uber ride", "Complex logistics"]:
            assignment.logistics_type = value
            db.session.commit()
            page = self.portal_page()
            self.assertIn(f'<span class="staff-detail-role">{value}</span>', page)
            self.assertIn(f'>{value}</div>', page)
            self.assertEqual('data-staff-logistics-instructions-open' in page, value.startswith("Complex"))
            if value == "Does not apply":
                self.assertIn('arrive 30 minutes before the start of the exam session.', page)
                self.assertNotIn('Open logistics folder ↗', page)
            else:
                self.assertIn('href="https://example.com/travel"', page)
                self.assertIn('<strong>Reimbursements</strong>', page)
                self.assertIn('<strong>Do not include these expenses in your final invoice.</strong>', page)
            if value in {"Uber ride", "Complex Uber ride"}:
                self.assertIn('arrive 30 minutes before the start of your first assigned module.', page)
                self.assertIn('<strong>official Uber or Cabify receipts</strong>', page)
                self.assertIn('<strong>pick-up and drop-off locations, date and time of the journey, and total fare</strong>', page)
            if value == "Complex logistics":
                self.assertIn('<strong>travel or commute</strong>', page)
                self.assertIn('<strong>additional expenses previously approved by Path Examinations</strong>', page)

    def test_supervisor_arrival_is_fifty_minutes_and_legacy_uber_is_normalized(self):
        assignment = self.portal_assignment("supervisor")
        self.assertIn('arrive 50 minutes before the start of the exam session.', self.portal_page())
        assignment.logistics_type = "Uber"
        db.session.commit()
        page = self.portal_page()
        self.assertIn('<span class="staff-detail-role">Uber ride</span>', page)
        self.assertIn('arrive 50 minutes before the start of your first assigned module.', page)

    def test_carpooling_examiner_portal(self):
        self.assert_carpooling_portal("examiner", 30)

    def test_carpooling_supervisor_portal(self):
        self.assert_carpooling_portal("supervisor", 50)

    def assert_carpooling_portal(self, role, minutes):
        assignment = self.portal_assignment(role)
        assignment.logistics_type = "Carpooling"
        concept = ExamSessionLogisticsConcept(exam_session_id=self.record.id,
            instructions_html="<p>Meet at the shared vehicle.</p>", staff_members=[self.person])
        other = AcademicStaff(full_name="Other traveller", status="Active", roles="Examiner")
        db.session.add_all([concept, other])
        db.session.flush()
        db.session.add(ExamSessionLogisticsConcept(exam_session_id=self.record.id,
            instructions_html="PRIVATE CARPOOL INSTRUCTIONS", staff_members=[other]))
        db.session.commit()
        page = self.portal_page()
        self.assertIn('>Carpooling</div>', page)
        self.assertIn('<span class="staff-detail-role">Carpooling</span>', page)
        self.assertIn('Your journey to the exam centre will involve sharing a vehicle with other staff members. Please read and follow the important instructions below, as specific procedures and requirements must be observed.', page)
        self.assertIn('data-staff-logistics-instructions-open>View instructions</button>', page)
        self.assertIn('<p>Meet at the shared vehicle.</p>', page)
        self.assertNotIn('PRIVATE CARPOOL INSTRUCTIONS', page)
        self.assertIn(f'Make sure you plan your journey accordingly, allow sufficient travel time and arrive {minutes} minutes before the start of your first assigned module.', page)
        self.assertIn(self.person, complex_logistics_staff_members_for_session(self.record.id))

    def test_instructions_are_scoped_to_member_and_session_and_progress_updates(self):
        assignment = self.portal_assignment()
        assignment.logistics_type = "Complex Uber ride"
        own = ExamSessionLogisticsConcept(exam_session_id=self.record.id, status="Pending",
            instructions_html='<ul><li><b>Your instructions</b></li></ul>', staff_members=[self.person])
        other_person = AcademicStaff(full_name="Other member", status="Active", roles="Examiner")
        other_record = ExamSession(exam_session_name="Other session", category="Path School", status="Pending",
            session_date=date(2026, 12, 10), shifts="Morning", modules="Speaking", format="Onsite")
        db.session.add_all([own, other_person, other_record])
        db.session.flush()
        db.session.add_all([
            ExamSessionLogisticsConcept(exam_session_id=self.record.id, instructions_html="PRIVATE OTHER MEMBER", staff_members=[other_person]),
            ExamSessionLogisticsConcept(exam_session_id=other_record.id, instructions_html="PRIVATE OTHER SESSION", staff_members=[self.person])])
        db.session.commit()
        self.assertIn(self.person, complex_logistics_staff_members_for_session(self.record.id))
        page = self.portal_page()
        self.assertIn('<ul><li><b>Your instructions</b></li></ul>', page)
        self.assertNotIn('PRIVATE OTHER', page)
        assignment.logistics_type = "Complex logistics"
        db.session.commit()
        self.assertIn('staff-detail-logistics-progress">In progress</span>', self.portal_page())
        own.status = "Confirmed"
        db.session.commit()
        self.assertIn('staff-detail-logistics-progress is-confirmed">Confirmed</span>', self.portal_page())

    def test_multiple_concepts_have_separate_titled_buttons_and_dialogs(self):
        assignment = self.portal_assignment()
        assignment.logistics_type = "Carpooling"
        for title, content in [("Traslado de ida", "Outbound instructions"), ("Traslado de vuelta", "Return instructions")]:
            db.session.add(ExamSessionLogisticsConcept(exam_session_id=self.record.id,
                instructions_title=title, instructions_html=content, staff_members=[self.person]))
        db.session.commit()
        page = self.portal_page()
        for title in ["Traslado de ida", "Traslado de vuelta"]:
            self.assertIn(f'View instructions | {title}</button>', page)
        import re
        items = re.findall(r'<div data-staff-logistics-instructions-item>(.*?)</dialog>', page, re.S)
        self.assertEqual(len(items), 2)
        self.assertIn("Outbound instructions", items[0])
        self.assertNotIn("Return instructions", items[0])
        self.assertIn("Return instructions", items[1])
        self.assertNotIn("Outbound instructions", items[1])

    def test_planner_logistics_requires_folder_and_lists_all_active_staff(self):
        members = []
        for index, value in enumerate(["Uber ride", "Complex Uber ride", "Complex logistics", "Does not apply", ""]):
            person = AcademicStaff(full_name=f"Logistics person {index}", status="Active", roles="Examiner")
            db.session.add(person)
            db.session.flush()
            db.session.add(ExamSessionExaminerAssignment(exam_session_id=self.record.id,
                team_member_id=person.id, participation_status="Pending", logistics_type=value))
            members.append(person)
        provider_type = ProviderType(name="Transport")
        concept = ExamSessionLogisticsConcept(exam_session_id=self.record.id, status="Pending")
        db.session.add_all([provider_type, concept])
        db.session.commit()
        self.assertEqual({item.id for item in complex_logistics_staff_members_for_session(self.record.id)},
                         {item.id for item in members[:3]})
        for value in ["", "not-a-url"]:
            with self.app.test_request_context(method="POST", data={"logistics_files_url": value}):
                self.assertFalse(save_exam_session_logistics(self.record))
        key = f"existing-{concept.id}"
        with self.app.test_request_context(method="POST", data={
            "logistics_files_url": "https://example.com/logistics",
            "logistics_concept_row_keys": key, f"logistics_concept_id_{key}": str(concept.id),
            f"logistics_provider_type_id_{key}": str(provider_type.id),
            f"logistics_staff_member_ids_{key}": [str(item.id) for item in members[:3]],
        }):
            self.assertTrue(save_exam_session_logistics(self.record))
            db.session.commit()
        self.assertEqual({item.id for item in concept.staff_members}, {item.id for item in members[:3]})
        page = self.client.get('/exam-session-planner?session_year=2026').get_data(as_text=True)
        for person in members[:3]:
            self.assertIn(f'<span>{person.full_name}</span>', page)

    def test_planner_without_active_logistics_does_not_require_folder(self):
        assignment = ExamSessionExaminerAssignment(exam_session_id=self.record.id, team_member_id=self.person.id,
                                                  logistics_type="Does not apply")
        db.session.add(assignment)
        db.session.commit()
        with self.app.test_request_context(method="POST", data={"logistics_files_url": ""}):
            self.assertTrue(save_exam_session_logistics(self.record))

    def test_planner_save_rejects_missing_link_without_persisting_changes(self):
        assignment = ExamSessionExaminerAssignment(exam_session_id=self.record.id, team_member_id=self.person.id,
                                                  logistics_type="Does not apply", participation_status="Pending")
        db.session.add(assignment)
        db.session.commit()
        key = f"existing-{assignment.id}"
        response = self.client.post(f'/exam-session-planner/sessions/{self.record.id}/members',
            headers={"Accept": "application/json"}, data={
                "csrf_token": "test", "session_year": "2026", "examiner_row_keys": key,
                f"examiner_assignment_id_{key}": str(assignment.id),
                f"examiner_team_member_id_{key}": str(self.person.id),
                f"examiner_participation_status_{key}": "Pending",
                f"examiner_logistics_type_{key}": "Uber ride", "logistics_files_url": "",
            })
        self.assertEqual(response.status_code, 400)
        self.assertIn("Configure the Logistics folder link", response.json["error"])
        self.assertEqual(db.session.get(ExamSessionExaminerAssignment, assignment.id).logistics_type, "Does not apply")

    def test_uber_options_disable_fuel_even_if_submitted(self):
        self.person.has_car = "Yes"
        assignment = ExamSessionExaminerAssignment(exam_session_id=self.record.id, team_member_id=self.person.id,
                                                  logistics_type="Does not apply", participation_status="Pending", km=100)
        provider_type = ProviderType(name="Transport")
        concept = ExamSessionLogisticsConcept(exam_session_id=self.record.id, status="Pending")
        db.session.add_all([assignment, provider_type, concept])
        db.session.commit()
        key = f"existing-{assignment.id}"
        concept_key = f"existing-{concept.id}"
        for value in ["Does not apply", "Uber ride", "Complex Uber ride", "Complex logistics", "Carpooling"]:
            response = self.client.post(f'/exam-session-planner/sessions/{self.record.id}/members',
                headers={"Accept": "application/json"}, data={
                    "csrf_token": "test", "session_year": "2026", "examiner_row_keys": key,
                    f"examiner_assignment_id_{key}": str(assignment.id),
                    f"examiner_team_member_id_{key}": str(self.person.id),
                    f"examiner_participation_status_{key}": "Pending",
                    f"examiner_logistics_type_{key}": value, f"examiner_km_{key}": "100",
                    f"examiner_fuel_enabled_{key}": "1", f"examiner_fuel_{key}": "100",
                    f"examiner_fuel_currency_{key}": "ARS", f"examiner_vehicle_dep_{key}": "50",
                    "logistics_files_url": "https://example.com/logistics",
                    "logistics_concept_row_keys": concept_key,
                    f"logistics_concept_id_{concept_key}": str(concept.id),
                    f"logistics_provider_type_id_{concept_key}": str(provider_type.id),
                    f"logistics_staff_member_ids_{concept_key}": str(self.person.id),
                })
            self.assertEqual(response.status_code, 200, response.json)
            item = db.session.get(ExamSessionExaminerAssignment, assignment.id)
            blocked = value in {"Uber ride", "Complex Uber ride"}
            self.assertEqual(item.fuel_enabled, not blocked)
            if blocked:
                self.assertFalse(item.fuel)
                self.assertFalse(item.vehicle_dep)


if __name__ == "__main__":
    unittest.main()
