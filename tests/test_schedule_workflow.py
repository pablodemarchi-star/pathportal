import json
import os
import subprocess
import unittest
from datetime import date, datetime, time, timedelta, timezone

os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from sqlalchemy.exc import IntegrityError

from app import create_app, db
from app.models import (
    AcademicStaff,
    ExamSession,
    CertificationYearConfiguration,
    ExaminerCertificationYear,
    ExamSessionCommunicationsChecklistItem,
    ExamSessionCommunicationsControl,
    ExamSessionCommunicationsEvent,
    ExamSessionExaminerAssignment,
    ExaminerCertificationAnnualMeetingSelection,
    ExaminerCertificationFut1Selection,
    ExaminerCertificationRemoteTrainingSelection,
    ExamSessionFinanceControl,
    ExamSessionFinanceEvent,
    ExamSessionIncident,
    ExamSessionIncidentChecklistItem,
    ExamSessionIncidentEvent,
    ExamSessionIncidentImpactReview,
    ExamSessionIncidentReviewFlag,
    ExamSessionInternAssignment,
    ExamSessionJourneyShare,
    ExamSessionLogistics,
    ExamSessionLogisticsControl,
    ExamSessionLogisticsConcept,
    ExamSessionLogisticsConceptNote,
    ExamSessionMonthlyCandidateTotal,
    ExamSessionMonthlyRegistration,
    ExamSessionPackageChecklistItem,
    ExamSessionPackageEvent,
    ExamSessionPackageUnit,
    ExamSessionScheduleEvent,
    ExamSessionScheduleWorkflow,
    ExamSessionShipmentBundle,
    ExamSessionShipmentBundleSession,
    ExamSessionShipmentChecklistItem,
    ExamSessionShipmentEvent,
    ExamSessionSinapsisChecklistItem,
    ExamSessionSinapsisControl,
    ExamSessionSinapsisEvent,
    ExamSessionStaffingControl,
    ExamSessionSupervisorAssignment,
    ExamSessionYear,
    PotentialEntry,
    StaffPaymentSettings,
    Provider,
    ProviderType,
    InternStageYear,
    InternStage2Selection,
    InternStage3Selection,
    InternStageFutSelection,
    InternStageRemoteTrainingSelection,
    SupervisorCertificationAnnualMeetingSelection,
    SupervisorCertificationFutSelection,
    SupervisorCertificationRemoteTrainingSelection,
    SupervisorCertificationYear,
)
from app.routes import (
    apply_schedule_workflow_transition,
    available_schedule_transitions,
    communications_readiness_contract,
    core_readiness_contract,
    exam_session_pending_status_tooltip,
    exam_session_overall_statuses_by_session_ids,
    ensure_incident_review_flags_for_high_priority_incident,
    finance_readiness_contract,
    get_exam_session_shipment_recipient_supervisor,
    incident_impact_assessment_contract,
    incident_impact_matrix_for_type,
    incident_review_flag_assisted_actions,
    incident_review_flag_action_contract,
    incident_review_flags_contract,
    incidents_readiness_contract,
    journey_countdown,
    logistics_control_contract,
    logistics_readiness_contract,
    monthly_candidate_requirement_contracts,
    my_action_row_from_schedule_view,
    operational_readiness_contract,
    packages_action_contract,
    packages_readiness_contract,
    path_session_journey_contract,
    promote_potential_entry_exam_session_assignments,
    reconcile_auto_shipment_bundles,
    shipment_bundle_readiness_contract,
    shipment_planning_action_contract,
    shipment_planning_contract,
    shipments_action_contract,
    review_flags_for_area,
    session_activity_timeline_contract,
    session_readiness_contract,
    session_shipment_contract,
    sinapsis_readiness_contract,
    sort_my_actions,
    priority_action_contract,
    schedule_gate_status,
    schedule_workflow_health,
    schedule_workflow_view,
    staffing_readiness_contract,
    staffing_control_contract,
)


class ScheduleWorkflowTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config["TESTING"] = True
        self.ctx = self.app.app_context()
        self.ctx.push()
        db.drop_all()
        db.create_all()
        self.session_record = ExamSession(
            exam_session_name="June exam session",
            category="Path School",
            status="Pending",
            session_date=date(2026, 6, 25),
            shifts="Morning",
            modules="Speaking",
            format="Online",
            details_url="https://example.com/sinapsis",
        )
        db.session.add(self.session_record)
        db.session.commit()

    def login_client(self):
        client = self.app.test_client()
        with client.session_transaction() as user_session:
            user_session["user"] = "admin"
            user_session["csrf_token"] = "token"
        return client

    def create_package_unit_record(self, status="Not started", expected=None, actual=None, session_record=None):
        session_record = session_record or self.session_record
        unit = ExamSessionPackageUnit(
            exam_session_id=session_record.id,
            room_name="Room 1",
            module_name="Speaking",
            expected_candidate_count=expected,
            actual_label_count=actual,
            status=status,
        )
        db.session.add(unit)
        db.session.flush()
        from app.routes import ensure_package_session_checklist_items, ensure_package_unit_checklist_items
        ensure_package_session_checklist_items(session_record.id)
        ensure_package_unit_checklist_items(unit)
        db.session.commit()
        return unit

    def approve_schedule(self):
        db.session.add(ExamSessionScheduleWorkflow(
            exam_session_id=self.session_record.id,
            status="Approved",
        ))
        db.session.commit()

    def create_incident_review_flag_record(
        self,
        affected_area="packages",
        status="Needs review",
        due_at=None,
        severity="Medium",
        incident_status="Open",
        title="Supervisor replacement",
        session_record=None,
    ):
        session_record = session_record or self.session_record
        incident = ExamSessionIncident(
            exam_session_id=session_record.id,
            incident_type="Supervisor changed",
            title=title,
            severity=severity,
            status=incident_status,
            responsible_department="ADMIN",
            due_at=due_at,
        )
        flag = ExamSessionIncidentReviewFlag(
            exam_session=session_record,
            incident=incident,
            impact_key=f"supervisor_changed:{affected_area}",
            affected_area=affected_area,
            status=status,
            reason="Package labels or supervisor documentation may need review.",
        )
        db.session.add(flag)
        db.session.commit()
        return flag

    def confirm_staffing(self):
        db.session.add_all([
            ExamSessionSupervisorAssignment(exam_session_id=self.session_record.id, team_member_id=1, participation_status="Confirmed", is_shipment_recipient=True),
            ExamSessionExaminerAssignment(exam_session_id=self.session_record.id, team_member_id=2, participation_status="Confirmed"),
            ExamSessionInternAssignment(exam_session_id=self.session_record.id, team_member_id=3, participation_status="Confirmed"),
        ])
        db.session.commit()

    def create_supervisor(self, staff_id=1, name="Dana Montalvo"):
        supervisor = AcademicStaff(
            id=staff_id,
            status="Active",
            full_name=name,
            roles="Supervisor",
            full_address_google_maps="Av. Siempre Viva 123",
            city="Cordoba",
            province="Cordoba",
        )
        db.session.add(supervisor)
        db.session.commit()
        return supervisor

    def create_potential_entry(self, entry_id=100, name="Ceeriolo", status="Interview confirmed"):
        entry = PotentialEntry(
            id=entry_id,
            status=status,
            full_name=name,
            email=f"{name.lower()}@example.com",
            is_rejected=status in {"Entry rejected", "Archived rejected entry"},
        )
        db.session.add(entry)
        db.session.commit()
        return entry

    def build_staff_preconfirmation_email(self, dataset):
        with open("app/static/js/app.js", encoding="utf-8") as handle:
            js = handle.read()
        start = js.index("const cleanEmailValue")
        end = js.index("const buildSuccessfulApplicationEmail")
        script = (
            js[start:end]
            + "\nconst button = { dataset: "
            + json.dumps({"staffPreconfirmationEmailPayload": json.dumps(dataset)})
            + " };\n"
            + "console.log(JSON.stringify(buildStaffPreconfirmationEmail(button)));\n"
        )
        result = subprocess.run(["node", "-e", script], check=True, capture_output=True, text=True)
        return json.loads(result.stdout)

    def build_staff_official_confirmation_email(self, dataset):
        with open("app/static/js/app.js", encoding="utf-8") as handle:
            js = handle.read()
        start = js.index("const cleanEmailValue")
        end = js.index("const initInvitationEmailCopyButtons")
        script = (
            js[start:end]
            + "\nconst button = { dataset: "
            + json.dumps({"staffOfficialConfirmationEmailPayload": json.dumps(dataset)})
            + " };\n"
            + "console.log(JSON.stringify(buildStaffOfficialConfirmationEmail(button)));\n"
        )
        result = subprocess.run(["node", "-e", script], check=True, capture_output=True, text=True)
        return json.loads(result.stdout)

    def assign_confirmed_supervisor(self, session_record=None, supervisor_id=1):
        session_record = session_record or self.session_record
        db.session.add(ExamSessionSupervisorAssignment(
            exam_session_id=session_record.id,
            team_member_id=supervisor_id,
            participation_status="Confirmed",
            is_shipment_recipient=True,
        ))
        db.session.commit()

    def mark_session_packages_quality_checked(self, session_record=None):
        session_record = session_record or self.session_record
        unit = self.create_package_unit_record(status="Quality checked", expected=10, actual=10, session_record=session_record)
        for item in ExamSessionPackageChecklistItem.query.filter_by(package_unit_id=unit.id).all():
            item.is_checked = True
        for item in ExamSessionPackageChecklistItem.query.filter_by(exam_session_id=session_record.id, scope="SESSION").all():
            item.is_checked = True
        db.session.commit()
        return unit

    def create_planning_ready_session(self, name, session_date, supervisor_id=1, packages_ready=True):
        session_record = ExamSession(
            exam_session_name=name,
            category="Path School",
            status="Pending",
            session_date=session_date,
            shifts="Morning",
            modules="Speaking",
            format="Online",
        )
        db.session.add(session_record)
        db.session.flush()
        db.session.add(ExamSessionScheduleWorkflow(exam_session_id=session_record.id, status="Approved"))
        db.session.commit()
        self.assign_confirmed_supervisor(session_record, supervisor_id=supervisor_id)
        if packages_ready:
            self.mark_session_packages_quality_checked(session_record)
        else:
            self.create_package_unit_record(status="Pre-packing", expected=10, actual=10, session_record=session_record)
        return session_record

    def test_exam_session_delete_form_uses_path_password(self):
        client = self.login_client()
        response = client.get("/exam-session-planner")
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn(f'/exam-session-planner/sessions/{self.session_record.id}/delete', html)
        self.assertIn('data-confirm-password-value="Path1234"', html)
        self.assertIn('name="deletion_password"', html)

    def test_exam_session_form_shows_minimum_candidates_without_table_column(self):
        client = self.login_client()
        response = client.get("/exam-session-planner?session_year=2026")
        html = response.get_data(as_text=True)
        table_head = html.split("<thead>", 1)[1].split("</thead>", 1)[0]

        self.assertEqual(response.status_code, 200)
        self.assertIn("Minimum number of candidates required", html)
        self.assertIn('name="minimum_candidates_required" value="30" min="0" step="1"', html)
        self.assertIn("Exam session organised by", html)
        self.assertIn('name="exam_session_organised_by" value="the exam centre" checked', html)
        self.assertIn('name="exam_session_organised_by" value="Path Examinations"', html)
        self.assertIn('name="format" value="Online at exam centre"', html)
        self.assertLess(html.index('name="format" value="Onsite"'), html.index('name="format" value="Online"'))
        self.assertLess(html.index('name="format" value="Online"'), html.index('name="format" value="Online at exam centre"'))
        self.assertNotIn("Minimum number of candidates required", table_head)

    def test_exam_session_planner_shows_pending_date_confirmation_chip_by_default(self):
        client = self.login_client()
        response = client.get("/exam-session-planner?session_year=2026")
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.session_record.date_confirmation_status, "Pending")
        self.assertIn('data-date-confirmation-chip', html)
        self.assertIn('data-status="Pending"', html)
        self.assertIn('date-confirmation-pending', html)

    def test_exam_session_date_confirmation_status_updates(self):
        client = self.login_client()
        response = client.post(
            f"/exam-session-planner/sessions/{self.session_record.id}/date-confirmation-status",
            data={"csrf_token": "token", "date_confirmation_status": "Waiting for confirmation"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["date_confirmation_status"], "Waiting for confirmation")
        self.assertEqual(db.session.get(ExamSession, self.session_record.id).date_confirmation_status, "Waiting for confirmation")

        response = client.post(
            f"/exam-session-planner/sessions/{self.session_record.id}/date-confirmation-status",
            data={"csrf_token": "token", "date_confirmation_status": "Confirmed"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(db.session.get(ExamSession, self.session_record.id).date_confirmation_status, "Confirmed")

    def test_exam_session_date_confirmation_status_rejects_invalid_status(self):
        client = self.login_client()
        response = client.post(
            f"/exam-session-planner/sessions/{self.session_record.id}/date-confirmation-status",
            data={"csrf_token": "token", "date_confirmation_status": "Done"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(db.session.get(ExamSession, self.session_record.id).date_confirmation_status, "Pending")

    def test_exam_session_member_duplication_tag_renders_in_matching_role_column(self):
        supervisor = self.create_supervisor()
        other_session = ExamSession(
            exam_session_name="Same day session",
            category="Path School",
            status="Pending",
            session_date=self.session_record.session_date,
            shifts="Afternoon",
            modules="Speaking",
            format="Online",
            details_url="https://example.com/other",
        )
        db.session.add(other_session)
        db.session.flush()
        db.session.add_all([
            ExamSessionSupervisorAssignment(
                exam_session_id=self.session_record.id,
                team_member_id=supervisor.id,
                participation_status="Confirmed",
            ),
            ExamSessionSupervisorAssignment(
                exam_session_id=other_session.id,
                team_member_id=supervisor.id,
                participation_status="Confirmed",
            ),
        ])
        db.session.commit()

        client = self.login_client()
        response = client.get("/exam-session-planner?session_year=2026")
        html = response.get_data(as_text=True)
        first_row = html.split("<tbody>", 1)[1].split("<tr data-session-row", 1)[1].split("</tr>", 1)[0]
        cells = first_row.split("<td")

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("Member duplication", cells[4])
        self.assertIn("Member duplication", cells[8])
        self.assertNotIn("Member duplication", cells[9])
        self.assertNotIn("Member duplication", cells[10])

    def test_exam_session_supervisor_assignment_supports_remote_checkbox(self):
        supervisor = self.create_supervisor()
        client = self.login_client()

        response = client.get(f"/exam-session-planner?session_year=2026&open_session_modal={self.session_record.id}")
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("Remote", html)
        self.assertIn('name="supervisor_remote_', html)
        self.assertNotIn('name="examiner_remote_', html)
        self.assertNotIn('name="intern_remote_', html)

        response = client.post(
            f"/exam-session-planner/sessions/{self.session_record.id}/members",
            data={
                "csrf_token": "token",
                "session_year": "2026",
                "supervisor_row_keys": "new-1",
                "supervisor_assignment_id_new-1": "",
                "supervisor_team_member_id_new-1": str(supervisor.id),
                "supervisor_remote_new-1": "1",
                "supervisor_participation_status_new-1": "Pending",
            },
            follow_redirects=True,
        )
        assignment = ExamSessionSupervisorAssignment.query.filter_by(
            exam_session_id=self.session_record.id,
            team_member_id=supervisor.id,
        ).one()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(assignment.is_remote)

    def test_exam_session_supervisor_summary_identifies_remote_roles(self):
        supervisor = self.create_supervisor()
        db.session.add_all([
            ExamSessionSupervisorAssignment(
                exam_session_id=self.session_record.id,
                team_member_id=supervisor.id,
                is_remote=True,
                participation_status="Pending",
            ),
            ExamSessionSupervisorAssignment(
                exam_session_id=self.session_record.id,
                participation_status="Pending",
            ),
            ExamSessionSupervisorAssignment(
                exam_session_id=self.session_record.id,
                is_remote=True,
                participation_status="Pending",
            ),
        ])
        db.session.commit()

        client = self.login_client()
        response = client.get("/exam-session-planner?session_year=2026")
        html = " ".join(response.get_data(as_text=True).split())

        self.assertEqual(response.status_code, 200)
        self.assertIn("3 supervisors required (2 remote)", html)
        self.assertIn("Dana Montalvo <em>(remote, pending)</em>", html)
        self.assertIn("1 remote role to cover", html)

    def test_exam_session_supervisor_summary_omits_remote_count_when_all_remote(self):
        supervisor = self.create_supervisor()
        db.session.add(
            ExamSessionSupervisorAssignment(
                exam_session_id=self.session_record.id,
                team_member_id=supervisor.id,
                is_remote=True,
                participation_status="Pending",
            )
        )
        db.session.commit()

        client = self.login_client()
        response = client.get("/exam-session-planner?session_year=2026")
        html = " ".join(response.get_data(as_text=True).split())

        self.assertEqual(response.status_code, 200)
        self.assertIn("1 supervisor required (remote)", html)
        self.assertNotIn("1 supervisor required (1 remote)", html)

    def test_exam_session_name_shows_path_organiser_note_when_selected(self):
        self.session_record.exam_session_organised_by = "Path Examinations"
        db.session.commit()

        client = self.login_client()
        response = client.get("/exam-session-planner?session_year=2026")
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("June exam session", html)
        self.assertIn("Organised by Path Examinations", html)

    def test_exam_session_create_and_update_persist_minimum_candidates_required(self):
        client = self.login_client()
        response = client.post(
            "/exam-session-planner/sessions",
            data={
                "csrf_token": "token",
                "session_year": "2026",
                "exam_session_name": "July exam session",
                "category": "Path School",
                "status": "Pending",
                "session_date": "20/07/2026",
                "minimum_candidates_required": "45",
                "exam_session_organised_by": "Path Examinations",
                "shifts": "Morning",
                "modules": "Speaking",
                "format": "Online at exam centre",
                "full_address_google_maps": "Av. Example 123",
                "city": "Buenos Aires",
                "province": "Buenos Aires",
                "details_url": "https://example.com/details",
            },
            follow_redirects=True,
        )
        created_session = ExamSession.query.filter_by(exam_session_name="July exam session").one()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(created_session.minimum_candidates_required, 45)
        self.assertEqual(created_session.exam_session_organised_by, "Path Examinations")
        self.assertEqual(created_session.format, "Online at exam centre")
        self.assertEqual(created_session.full_address_google_maps, "Av. Example 123")
        self.assertEqual(created_session.city, "Buenos Aires")
        self.assertEqual(created_session.province, "Buenos Aires")
        self.assertEqual(created_session.date_confirmation_status, "Pending")

        response = client.post(
            f"/exam-session-planner/sessions/{created_session.id}",
            data={
                "csrf_token": "token",
                "session_year": "2026",
                "exam_session_name": "July exam session",
                "category": "Path School",
                "status": "Pending",
                "session_date": "20/07/2026",
                "minimum_candidates_required": "0",
                "exam_session_organised_by": "the exam centre",
                "shifts": "Morning",
                "modules": "Speaking",
                "format": "Online",
                "details_url": "https://example.com/details",
            },
            follow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(db.session.get(ExamSession, created_session.id).minimum_candidates_required, 0)
        self.assertEqual(db.session.get(ExamSession, created_session.id).exam_session_organised_by, "the exam centre")
        self.assertEqual(db.session.get(ExamSession, created_session.id).full_address_google_maps, "")

    def test_exam_session_rejects_invalid_minimum_candidates_required(self):
        client = self.login_client()
        response = client.post(
            "/exam-session-planner/sessions",
            data={
                "csrf_token": "token",
                "session_year": "2026",
                "exam_session_name": "Invalid candidates session",
                "category": "Path School",
                "status": "Pending",
                "session_date": "20/07/2026",
                "minimum_candidates_required": "-1",
                "shifts": "Morning",
                "modules": "Speaking",
                "format": "Online",
            },
            follow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            "Minimum number of candidates required must be a whole number of 0 or more.",
            response.get_data(as_text=True),
        )
        self.assertIsNone(ExamSession.query.filter_by(exam_session_name="Invalid candidates session").first())

    def test_exam_session_delete_requires_path_password(self):
        client = self.login_client()
        self.create_supervisor()
        self.confirm_staffing()
        db.session.add(ExamSessionJourneyShare(exam_session_id=self.session_record.id, audience="institution", token="journey-token"))
        db.session.add(ExamSessionStaffingControl(exam_session_id=self.session_record.id, staffing_due_at=date(2026, 6, 10)))
        db.session.add(ExamSessionLogisticsControl(exam_session_id=self.session_record.id, logistics_due_at=date(2026, 6, 12)))
        db.session.add(ExamSessionMonthlyRegistration(exam_session_id=self.session_record.id, month=6, module="Speaking", registration_number=12))
        db.session.add(ExamSessionMonthlyCandidateTotal(exam_session_id=self.session_record.id, month=6, total_candidates=12))
        logistics_concept = ExamSessionLogisticsConcept(exam_session_id=self.session_record.id, status="Confirmed", provider="Courier", currency="ARS", fee=100)
        db.session.add(logistics_concept)
        db.session.flush()
        db.session.add(ExamSessionLogisticsConceptNote(logistics_concept_id=logistics_concept.id, comment="Ready"))
        finance, sinapsis, communications = self.mark_session_external_readiness_ready()
        db.session.add(ExamSessionFinanceEvent(finance_control_id=finance.id, new_status="Cleared"))
        db.session.add(ExamSessionSinapsisEvent(sinapsis_control_id=sinapsis.id, new_status="Ready"))
        db.session.add(ExamSessionCommunicationsEvent(communications_control_id=communications.id, new_status="Completed"))
        package_unit = self.create_package_unit_record(status="Quality checked", expected=12, actual=12)
        db.session.add(ExamSessionPackageEvent(package_unit_id=package_unit.id, event_type="status", new_status="Quality checked"))
        incident_flag = self.create_incident_review_flag_record(status="Needs review")
        impact_review = ExamSessionIncidentImpactReview(
            incident_id=incident_flag.incident_id,
            impact_key=incident_flag.impact_key,
            affected_area=incident_flag.affected_area,
            status="Review suggested",
        )
        db.session.add(impact_review)
        shipment_bundle = self.create_shipment_bundle_record(status="Ready to dispatch")
        db.session.commit()
        logistics_concept_id = logistics_concept.id
        package_unit_id = package_unit.id
        incident_flag_id = incident_flag.id
        shipment_bundle_id = shipment_bundle.id

        response = client.post(
            f"/exam-session-planner/sessions/{self.session_record.id}/delete",
            data={"csrf_token": "token", "session_year": "2026", "deletion_password": "7284"},
            follow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("Permanent delete password is not valid.", response.get_data(as_text=True))
        self.assertIsNotNone(db.session.get(ExamSession, self.session_record.id))

        response = client.post(
            f"/exam-session-planner/sessions/{self.session_record.id}/delete",
            data={"csrf_token": "token", "session_year": "2026", "deletion_password": "Path1234"},
            follow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("Exam session deleted successfully.", response.get_data(as_text=True))
        self.assertIsNone(db.session.get(ExamSession, self.session_record.id))
        self.assertIsNone(db.session.get(ExamSessionLogisticsConcept, logistics_concept_id))
        self.assertIsNone(db.session.get(ExamSessionPackageUnit, package_unit_id))
        self.assertIsNone(db.session.get(ExamSessionIncidentReviewFlag, incident_flag_id))
        self.assertEqual(ExamSessionShipmentBundleSession.query.filter_by(bundle_id=shipment_bundle_id).count(), 0)

    def create_shipment_bundle_record(self, status="Preparing bundle", dispatch_due_at=None, session_record=None):
        session_record = session_record or self.session_record
        bundle = ExamSessionShipmentBundle(
            supervisor_staff_id=1,
            delivery_address="Av. Siempre Viva 123",
            courier="Correo Argentino",
            status=status,
            dispatch_due_at=dispatch_due_at,
        )
        db.session.add(bundle)
        db.session.flush()
        db.session.add(ExamSessionShipmentBundleSession(bundle_id=bundle.id, exam_session_id=session_record.id))
        from app.routes import ensure_shipment_checklist_items
        ensure_shipment_checklist_items(bundle)
        db.session.commit()
        return bundle

    def mark_session_external_readiness_ready(self, session_record=None):
        session_record = session_record or self.session_record
        finance = ExamSessionFinanceControl(
            exam_session_id=session_record.id,
            status="Cleared",
        )
        sinapsis = ExamSessionSinapsisControl(
            exam_session_id=session_record.id,
            status="Ready",
        )
        communications = ExamSessionCommunicationsControl(
            exam_session_id=session_record.id,
            status="Completed",
        )
        db.session.add_all([finance, sinapsis, communications])
        db.session.flush()
        from app.routes import ensure_communications_checklist_items, ensure_sinapsis_checklist_items
        ensure_sinapsis_checklist_items(sinapsis)
        ensure_communications_checklist_items(communications)
        for item in ExamSessionSinapsisChecklistItem.query.filter_by(sinapsis_control_id=sinapsis.id).all():
            item.is_checked = True
        for item in ExamSessionCommunicationsChecklistItem.query.filter_by(communications_control_id=communications.id).all():
            item.is_checked = True
        db.session.commit()
        return finance, sinapsis, communications

    def mark_session_operationally_ready(self):
        self.approve_schedule()
        self.create_supervisor()
        self.confirm_staffing()
        self.mark_session_packages_quality_checked()
        bundle = self.create_shipment_bundle_record(status="Recipient review successful")
        for item in ExamSessionShipmentChecklistItem.query.filter_by(bundle_id=bundle.id).all():
            item.is_checked = True
        db.session.commit()
        return bundle

    def pre_session_data_counts(self):
        return {
            "finance_controls": ExamSessionFinanceControl.query.count(),
            "sinapsis_controls": ExamSessionSinapsisControl.query.count(),
            "communications_controls": ExamSessionCommunicationsControl.query.count(),
            "incidents": ExamSessionIncident.query.count(),
            "review_flags": ExamSessionIncidentReviewFlag.query.count(),
            "package_units": ExamSessionPackageUnit.query.count(),
            "shipment_bundles": ExamSessionShipmentBundle.query.count(),
            "shipment_links": ExamSessionShipmentBundleSession.query.count(),
            "schedule_events": ExamSessionScheduleEvent.query.count(),
            "finance_events": ExamSessionFinanceEvent.query.count(),
            "sinapsis_events": ExamSessionSinapsisEvent.query.count(),
            "communications_events": ExamSessionCommunicationsEvent.query.count(),
            "incident_events": ExamSessionIncidentEvent.query.count(),
            "package_events": ExamSessionPackageEvent.query.count(),
            "shipment_events": ExamSessionShipmentEvent.query.count(),
        }

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def test_view_without_workflow_is_not_started_without_creating_record(self):
        view = schedule_workflow_view(self.session_record, None, today=date(2026, 6, 1))

        self.assertEqual(view["status"], "Not started")
        self.assertEqual(view["schedule_gate"]["label"], "Blocked")
        self.assertFalse(view["schedule_gate"]["is_ready"])
        self.assertEqual(view["next_action"], "Start preparing schedules")
        self.assertEqual(view["responsible"], "MANAGEMENT")
        self.assertEqual(view["review_round"], 0)
        self.assertEqual(view["health"], "Deadline missing")
        self.assertEqual(ExamSessionScheduleWorkflow.query.count(), 0)

    def test_schedule_gate_blocks_all_non_approved_statuses(self):
        for status in ["Not started", "In progress", "Ready to send", "Sent for review", "Changes requested"]:
            workflow = ExamSessionScheduleWorkflow(
                exam_session_id=self.session_record.id,
                status=status,
            )
            gate = schedule_gate_status(workflow)

            self.assertEqual(gate["status"], "blocked")
            self.assertEqual(gate["label"], "Blocked")
            self.assertFalse(gate["is_ready"])

    def test_schedule_gate_ready_only_when_approved(self):
        workflow = ExamSessionScheduleWorkflow(
            exam_session_id=self.session_record.id,
            status="Approved",
        )

        gate = schedule_gate_status(workflow)

        self.assertEqual(gate["status"], "ready")
        self.assertEqual(gate["label"], "Ready")
        self.assertTrue(gate["is_ready"])

    def test_invalid_transition_from_not_started_to_approved_is_rejected(self):
        workflow, error = apply_schedule_workflow_transition(
            self.session_record,
            "approve",
            created_by="admin",
        )
        db.session.rollback()

        self.assertIsNone(workflow)
        self.assertEqual(error, "This schedule workflow action is not allowed from the current status.")
        self.assertEqual(ExamSessionScheduleEvent.query.count(), 0)

    def test_valid_send_for_review_increments_review_round_and_records_event(self):
        due_at = date(2026, 6, 20)
        workflow, error = apply_schedule_workflow_transition(
            self.session_record,
            "start_preparation",
            due_at=due_at,
            created_by="admin",
        )
        self.assertIsNone(error)
        workflow, error = apply_schedule_workflow_transition(
            self.session_record,
            "mark_ready",
            due_at=due_at + timedelta(days=1),
            created_by="admin",
        )
        self.assertIsNone(error)
        workflow, error = apply_schedule_workflow_transition(
            self.session_record,
            "send_for_review",
            due_at=due_at + timedelta(days=2),
            created_by="admin",
        )
        db.session.commit()

        self.assertIsNone(error)
        self.assertEqual(workflow.status, "Sent for review")
        self.assertEqual(workflow.review_round, 1)
        self.assertIsNotNone(workflow.last_sent_at)
        self.assertEqual(ExamSessionScheduleEvent.query.count(), 3)

    def test_requested_changes_requires_note(self):
        due_at = date(2026, 6, 20)
        apply_schedule_workflow_transition(self.session_record, "start_preparation", due_at=due_at)
        apply_schedule_workflow_transition(self.session_record, "mark_ready", due_at=due_at)
        apply_schedule_workflow_transition(self.session_record, "send_for_review", due_at=due_at)

        workflow, error = apply_schedule_workflow_transition(
            self.session_record,
            "record_changes",
            due_at=due_at,
            note="",
        )
        db.session.rollback()

        self.assertIsNone(workflow)
        self.assertEqual(error, "Please add a note for this schedule workflow action.")

    def test_approval_clears_active_deadline(self):
        due_at = date(2026, 6, 20)
        apply_schedule_workflow_transition(self.session_record, "start_preparation", due_at=due_at)
        apply_schedule_workflow_transition(self.session_record, "mark_ready", due_at=due_at)
        apply_schedule_workflow_transition(self.session_record, "send_for_review", due_at=due_at)
        workflow, error = apply_schedule_workflow_transition(self.session_record, "approve")
        db.session.commit()

        self.assertIsNone(error)
        self.assertEqual(workflow.status, "Approved")
        self.assertIsNone(workflow.next_action_due_at)
        self.assertIsNotNone(workflow.approved_at)
        self.assertEqual(schedule_workflow_health("Approved", None), "Completed")

    def test_available_transitions_are_state_specific(self):
        labels = [item["label"] for item in available_schedule_transitions("Sent for review")]

        self.assertIn("Record requested changes", labels)
        self.assertIn("Mark schedules as approved", labels)
        self.assertIn("Update deadline", labels)
        self.assertNotIn("Continue editing schedules", labels)

    def test_core_readiness_precedence_and_ready_counts(self):
        schedule_blocked = {
            "status": "blocked",
            "label": "Blocked",
            "message": "Schedule blocked.",
            "is_ready": False,
        }
        schedule_ready = {
            "status": "ready",
            "label": "Ready",
            "message": "Schedule ready.",
            "is_ready": True,
        }
        staffing_ready = {
            "status": "confirmed",
            "ready": True,
            "totals": {
                "required": 1,
                "assigned": 1,
                "open_positions": 0,
                "pending_assigned": 0,
                "sent": 0,
                "confirmed": 1,
            },
            "by_role": {},
            "blockers": [],
        }
        staffing_open = {
            "status": "open_positions",
            "ready": False,
            "totals": {
                "required": 1,
                "assigned": 0,
                "open_positions": 1,
                "pending_assigned": 0,
                "sent": 0,
                "confirmed": 0,
            },
            "by_role": {},
            "open_position_details": [{"role": "Examiner"}],
            "blockers": [],
        }
        logistics_ready = {
            "status": "confirmed",
            "ready": True,
            "final_email_ready": True,
            "applies": True,
            "total_concepts": 1,
            "confirmed_concepts": 1,
            "has_files_url": True,
            "blocking_concepts": [],
            "blockers": [],
        }
        logistics_in_progress = {
            "status": "in_progress",
            "ready": False,
            "final_email_ready": False,
            "applies": True,
            "total_concepts": 1,
            "confirmed_concepts": 0,
            "has_files_url": True,
            "blocking_concepts": [{"id": 1, "status": "Pending", "provider": "Hotel"}],
            "blockers": [{"code": "LOGISTICS_CONCEPTS_PENDING", "message": "Waiting for all logistics concepts to be confirmed."}],
        }
        logistics_missing_link = {
            "status": "confirmed",
            "ready": True,
            "final_email_ready": False,
            "applies": True,
            "total_concepts": 1,
            "confirmed_concepts": 1,
            "has_files_url": False,
            "blocking_concepts": [],
            "blockers": [{"code": "LOGISTICS_FILES_URL_MISSING", "message": "Add the Check logistics files link before copying the final email."}],
        }
        logistics_not_applicable = {
            "status": "not_applicable",
            "ready": True,
            "final_email_ready": True,
            "applies": False,
            "total_concepts": 0,
            "confirmed_concepts": 0,
            "has_files_url": False,
            "blocking_concepts": [],
            "blockers": [],
        }

        blocked = core_readiness_contract(schedule_blocked, staffing_ready, logistics_ready)
        self.assertEqual(blocked["status"], "blocked")
        self.assertEqual(blocked["ready_requirements"], 2)
        self.assertEqual(blocked["summary"], "2 / 3 requirements ready")

        blocked_with_other_pending = core_readiness_contract(schedule_blocked, staffing_open, logistics_in_progress)
        self.assertEqual(blocked_with_other_pending["status"], "blocked")
        self.assertIn("Schedule approval is still pending.", [item["message"] for item in blocked_with_other_pending["blockers"]])
        self.assertIn("1 Examiner position still needs to be filled.", [item["message"] for item in blocked_with_other_pending["blockers"]])
        self.assertIn("A logistics concept is still Pending.", [item["message"] for item in blocked_with_other_pending["blockers"]])

        staffing_pending = core_readiness_contract(schedule_ready, staffing_open, logistics_ready)
        self.assertEqual(staffing_pending["status"], "in_progress")

        logistics_pending = core_readiness_contract(schedule_ready, staffing_ready, logistics_missing_link)
        self.assertEqual(logistics_pending["status"], "in_progress")

        not_applicable_ready = core_readiness_contract(schedule_ready, staffing_ready, logistics_not_applicable)
        self.assertEqual(not_applicable_ready["status"], "ready_for_next_stage")
        self.assertEqual(not_applicable_ready["ready_requirements"], 3)

        duplicated = core_readiness_contract(
            schedule_ready,
            staffing_open,
            logistics_in_progress,
            staffing={"label": "Open positions", "status": "open_positions", "blockers": ["Shared blocker"]},
            logistics={"label": "In progress", "status": "in_progress", "blockers": ["Shared blocker"]},
        )
        self.assertEqual(
            [blocker["message"] for blocker in duplicated["blockers"]].count("Shared blocker"),
            1,
        )

    def test_core_readiness_needs_review_fail_closed(self):
        schedule_ready = {"status": "ready", "label": "Ready", "is_ready": True}
        staffing_invalid = {"status": "invalid", "ready": False, "blockers": []}
        staffing_ready = {"status": "confirmed", "ready": True, "totals": {}, "by_role": {}, "blockers": []}
        logistics_ready = {
            "status": "confirmed",
            "ready": True,
            "final_email_ready": True,
            "applies": True,
            "total_concepts": 1,
            "confirmed_concepts": 1,
            "has_files_url": True,
            "blockers": [],
        }
        logistics_unknown = {"status": "mystery", "final_email_ready": True, "blockers": []}

        self.assertEqual(
            core_readiness_contract(schedule_ready, staffing_invalid, logistics_ready)["status"],
            "needs_review",
        )
        self.assertEqual(
            core_readiness_contract(schedule_ready, staffing_ready, logistics_unknown)["status"],
            "needs_review",
        )
        self.assertEqual(
            core_readiness_contract({"status": "mystery", "is_ready": True}, staffing_ready, logistics_ready)["status"],
            "needs_review",
        )
        self.assertEqual(
            core_readiness_contract(schedule_ready, None, logistics_ready)["status"],
            "needs_review",
        )

    def test_operational_readiness_contract_precedence_and_shipments(self):
        schedule_ready = {"status": "ready", "label": "Ready", "is_ready": True}
        schedule_blocked = {"status": "blocked", "label": "Blocked", "is_ready": False}
        staffing_ready = {"status": "confirmed", "ready": True, "totals": {}, "by_role": {}, "blockers": []}
        staffing_invalid = {"status": "invalid", "ready": False, "totals": {}, "by_role": {}, "blockers": []}
        logistics_ready = {
            "status": "confirmed",
            "ready": True,
            "final_email_ready": True,
            "applies": True,
            "total_concepts": 1,
            "confirmed_concepts": 1,
            "has_files_url": True,
            "blocking_concepts": [],
            "blockers": [],
        }
        packages_ready = {
            "status": "quality_checked",
            "label": "Quality checked",
            "ready": True,
            "summary": "1 / 1 packages checked",
            "blockers": [],
        }
        packages_pending = {
            "status": "pre_packing_in_progress",
            "label": "Pre-packing in progress",
            "ready": False,
            "summary": "0 / 1 packages impersonal ready",
            "blockers": ["Packages must be quality checked."],
        }
        shipment_ready = {
            "status": "Recipient review successful",
            "label": "Recipient review successful",
            "summary": "Recipient review complete",
            "bundle": object(),
            "readiness": {},
        }
        shipment_delivered = {
            "status": "Delivered successfully",
            "label": "Delivered successfully",
            "summary": "Pending recipient review",
            "bundle": object(),
            "readiness": {},
        }
        shipment_discrepancy = {
            "status": "Recipient review with discrepancy",
            "label": "Recipient review with discrepancy",
            "summary": "Review required",
            "bundle": object(),
            "readiness": {},
        }

        ready = operational_readiness_contract(schedule_ready, staffing_ready, logistics_ready, packages_ready, shipment_ready)
        self.assertEqual(ready["status"], "operationally_ready")
        self.assertTrue(ready["is_ready"])
        self.assertEqual(ready["ready_requirements"], 5)
        self.assertIn("does not include Finance, Sinapsis readiness, Communications, Incidents or Incident review flags", ready["scope_note"])

        delivered_pending_review = operational_readiness_contract(schedule_ready, staffing_ready, logistics_ready, packages_ready, shipment_delivered)
        self.assertEqual(delivered_pending_review["status"], "in_progress")
        self.assertIn("recipient review is still pending", [item for item in delivered_pending_review["requirements"] if item["key"] == "shipments"][0]["message"])

        blocked = operational_readiness_contract(schedule_blocked, staffing_ready, logistics_ready, packages_ready, shipment_ready)
        self.assertEqual(blocked["status"], "blocked")
        self.assertEqual(blocked["ready_requirements"], 4)

        packages_in_progress = operational_readiness_contract(schedule_ready, staffing_ready, logistics_ready, packages_pending, shipment_ready)
        self.assertEqual(packages_in_progress["status"], "in_progress")
        self.assertIn("Packages must be quality checked.", [blocker["message"] for blocker in packages_in_progress["blockers"]])

        needs_review = operational_readiness_contract(schedule_blocked, staffing_invalid, logistics_ready, packages_ready, shipment_ready)
        self.assertEqual(needs_review["status"], "needs_review")

        discrepancy = operational_readiness_contract(schedule_ready, staffing_ready, logistics_ready, packages_ready, shipment_discrepancy)
        self.assertEqual(discrepancy["status"], "needs_review")
        self.assertIn("Recipient review reported a discrepancy", [blocker["message"] for blocker in discrepancy["blockers"]][0])

    def test_session_readiness_contract_precedence(self):
        operational_ready = {
            "status": "operationally_ready",
            "label": "Operationally ready",
            "is_ready": True,
            "message": "Schedule approval, staffing, staff logistics, packages and shipments are complete.",
            "blockers": [],
        }
        operational_blocked = {
            "status": "blocked",
            "label": "Blocked",
            "is_ready": False,
            "message": "Schedule approval is required before the session can move through the operational pre-session flow.",
            "blockers": [{"code": "SCHEDULE_APPROVAL_REQUIRED", "message": "Schedule approval is still pending."}],
        }
        operational_review = {
            "status": "needs_review",
            "label": "Needs review",
            "is_ready": False,
            "message": "Some operational readiness data is inconsistent or requires review.",
            "blockers": [],
        }
        finance_cleared = {"raw_status": "Cleared", "label": "Cleared", "can_proceed": True, "message": "Finance confirmed this session can proceed.", "blockers": []}
        finance_conditional = {"raw_status": "Conditional clearance", "label": "Conditional clearance", "can_proceed": True, "message": "Finance allows this session to proceed with a condition pending.", "blockers": []}
        finance_exception = {"raw_status": "Exception approved", "label": "Exception approved", "can_proceed": True, "message": "Finance approved an exception for this session.", "blockers": []}
        finance_not_reviewed = {"raw_status": "Not reviewed", "label": "Not reviewed", "can_proceed": False, "message": "Finance has not reviewed this session yet.", "blockers": []}
        finance_hold = {"raw_status": "Finance hold", "label": "Finance hold", "can_proceed": False, "message": "Finance has placed this session on hold.", "blockers": [{"code": "FINANCE_HOLD", "message": "Finance has placed this session on hold."}]}
        sinapsis_ready = {"label": "Ready", "ready": True, "message": "Sinapsis has been verified.", "blockers": []}
        sinapsis_correction = {"label": "Needs correction", "ready": False, "message": "Sinapsis setup needs correction before the session.", "blockers": []}
        communications_ready = {"label": "Completed", "ready": True, "message": "Communications have been completed for this session.", "blockers": []}
        incidents_ready = {"status": "none", "label": "No active incidents", "active_count": 0, "critical_count": 0, "high_count": 0, "message": "No active incidents.", "blockers": []}
        incidents_resolved = {"status": "resolved", "label": "No active incidents", "active_count": 0, "critical_count": 0, "high_count": 0, "message": "All incidents are resolved or cancelled.", "blockers": []}
        incidents_high = {"status": "active", "label": "Active incidents", "active_count": 1, "critical_count": 0, "high_count": 1, "message": "1 active incidents.", "blockers": []}
        incidents_critical = {"status": "critical", "label": "Critical incident", "active_count": 1, "critical_count": 1, "high_count": 0, "message": "1 active incidents, 1 critical.", "blockers": [{"code": "CRITICAL_INCIDENT", "message": "Wrong recipient"}]}
        incidents_review = {"status": "needs_review", "label": "Needs review", "active_count": 0, "critical_count": 0, "high_count": 0, "message": "Incident data needs review.", "blockers": [{"code": "INCIDENT_DATA_NEEDS_REVIEW", "message": "Incident data needs review."}]}
        review_flags_ready = incident_review_flags_contract(self.session_record, flags=[])
        review_flags_active = dict(
            review_flags_ready,
            status="active",
            label="Review required",
            ready=False,
            active_flags_count=1,
            by_area={"packages": [{"id": 1}]},
        )
        review_flags_invalid = dict(
            review_flags_ready,
            status="needs_review",
            label="Needs review",
            ready=False,
            data_needs_review=True,
            invalid_flags_count=1,
        )

        self.assertEqual(session_readiness_contract(operational_review, finance_cleared, sinapsis_ready, communications_ready, incidents_ready, review_flags_ready)["status"], "needs_review")
        hold = session_readiness_contract(operational_ready, finance_hold, sinapsis_ready, communications_ready, incidents_ready, review_flags_ready)
        self.assertEqual(hold["status"], "blocked")
        self.assertEqual(hold["message"], "This session is currently under Finance hold.")
        self.assertIn("This session is currently under Finance hold.", [blocker["message"] for blocker in hold["blockers"]])
        self.assertEqual(session_readiness_contract(operational_blocked, finance_not_reviewed, sinapsis_ready, communications_ready, incidents_ready, review_flags_ready)["status"], "blocked")
        self.assertEqual(session_readiness_contract(operational_ready, finance_not_reviewed, sinapsis_ready, communications_ready, incidents_ready, review_flags_ready)["status"], "in_progress")
        ready = session_readiness_contract(operational_ready, finance_conditional, sinapsis_ready, communications_ready, incidents_ready, review_flags_ready)
        self.assertEqual(ready["status"], "session_ready")
        self.assertEqual(ready["ready_requirements"], 6)
        self.assertEqual(ready["total_requirements"], 6)
        self.assertIn("Incident review flags", [requirement["label"] for requirement in ready["requirements"]])
        self.assertEqual(session_readiness_contract(operational_ready, finance_exception, sinapsis_ready, communications_ready, incidents_ready, review_flags_ready)["status"], "session_ready")
        self.assertEqual(session_readiness_contract(operational_ready, finance_cleared, sinapsis_ready, communications_ready, incidents_resolved, review_flags_ready)["status"], "session_ready")
        self.assertEqual(session_readiness_contract(operational_ready, finance_cleared, sinapsis_correction, communications_ready, incidents_ready, review_flags_ready)["status"], "in_progress")
        self.assertEqual(session_readiness_contract(operational_ready, finance_cleared, sinapsis_ready, communications_ready, incidents_high, review_flags_ready)["status"], "in_progress")
        critical = session_readiness_contract(operational_ready, finance_cleared, sinapsis_ready, communications_ready, incidents_critical, review_flags_active)
        self.assertEqual(critical["status"], "blocked")
        self.assertEqual(critical["message"], "This session has a critical active incident.")
        self.assertIn("There is 1 critical active incident.", [item["message"] for item in critical["requirements"] if item["key"] == "incidents"][0])
        active_review = session_readiness_contract(operational_ready, finance_cleared, sinapsis_ready, communications_ready, incidents_resolved, review_flags_active)
        self.assertEqual(active_review["status"], "in_progress")
        self.assertEqual(active_review["ready_requirements"], 5)
        self.assertIn("There is 1 incident review flag requiring attention.", [item["message"] for item in active_review["requirements"] if item["key"] == "incident_review_flags"][0])
        self.assertIn("There is 1 incident review flag requiring attention.", [blocker["message"] for blocker in active_review["blockers"]])
        self.assertEqual(session_readiness_contract(operational_ready, finance_hold, sinapsis_ready, communications_ready, incidents_ready, review_flags_active)["status"], "blocked")
        self.assertEqual(session_readiness_contract(operational_ready, finance_hold, sinapsis_ready, communications_ready, incidents_review, review_flags_active)["status"], "needs_review")
        self.assertEqual(session_readiness_contract(operational_ready, finance_cleared, sinapsis_ready, communications_ready, incidents_ready, review_flags_invalid)["status"], "needs_review")
        self.assertEqual(session_readiness_contract(operational_ready, {"raw_status": "Mystery", "label": "Mystery"}, sinapsis_ready, communications_ready, incidents_ready, review_flags_ready)["status"], "needs_review")
        self.assertEqual(session_readiness_contract(operational_ready, finance_cleared, {"label": "Mystery"}, communications_ready, incidents_ready, review_flags_ready)["status"], "needs_review")
        invalid_control = type("InvalidControl", (), {"status": "Mystery"})()
        normalized_invalid_finance = {
            "raw_status": "Not reviewed",
            "status": "not_reviewed",
            "label": "Not reviewed",
            "can_proceed": False,
            "message": "Finance has not reviewed this session yet.",
            "blockers": [],
            "control": invalid_control,
        }
        self.assertEqual(session_readiness_contract(operational_ready, normalized_invalid_finance, sinapsis_ready, communications_ready, incidents_ready, review_flags_ready)["status"], "needs_review")
        self.assertEqual(session_readiness_contract(operational_ready, finance_cleared, sinapsis_ready, communications_ready, incidents_ready, None)["status"], "needs_review")

    def test_priority_action_contract_precedence(self):
        schedule_blocked = {"status": "blocked", "label": "Blocked", "is_ready": False}
        schedule_ready = {"status": "ready", "label": "Ready", "is_ready": True}
        staffing_ready = {
            "status": "confirmed",
            "ready": True,
            "totals": {"open_positions": 0, "pending_assigned": 0, "sent": 0},
            "open_position_details": [],
        }
        staffing_invalid = {"status": "invalid", "ready": False}
        staffing_not_configured = {
            "status": "not_configured",
            "ready": False,
            "totals": {"open_positions": 0, "pending_assigned": 0, "sent": 0},
            "open_position_details": [],
        }
        staffing_open = {
            "status": "open_positions",
            "ready": False,
            "totals": {"open_positions": 1, "pending_assigned": 0, "sent": 0},
            "open_position_details": [{"role": "Examiner"}],
        }
        staffing_awaiting = {
            "status": "awaiting_confirmations",
            "ready": False,
            "totals": {"open_positions": 0, "pending_assigned": 1, "sent": 1},
            "open_position_details": [],
        }
        logistics_ready = {
            "status": "confirmed",
            "ready": True,
            "final_email_ready": True,
            "total_concepts": 1,
            "confirmed_concepts": 1,
            "blockers": [],
        }
        logistics_not_applicable = {
            "status": "not_applicable",
            "ready": True,
            "final_email_ready": True,
            "total_concepts": 0,
            "confirmed_concepts": 0,
            "blockers": [],
        }
        logistics_configuration_required = {
            "status": "configuration_required",
            "ready": False,
            "final_email_ready": False,
            "total_concepts": 0,
            "confirmed_concepts": 0,
            "blockers": [{"code": "LOGISTICS_CONCEPTS_MISSING"}],
        }
        logistics_in_progress = {
            "status": "in_progress",
            "ready": False,
            "final_email_ready": False,
            "total_concepts": 3,
            "confirmed_concepts": 1,
            "blockers": [{"code": "LOGISTICS_CONCEPTS_PENDING"}],
        }
        logistics_files_missing = {
            "status": "confirmed",
            "ready": True,
            "final_email_ready": False,
            "total_concepts": 2,
            "confirmed_concepts": 2,
            "blockers": [{"code": "LOGISTICS_FILES_URL_MISSING"}],
        }
        core_needs_review = {"status": "needs_review"}
        core_blocked = {"status": "blocked"}
        core_in_progress = {"status": "in_progress"}
        core_ready = {"status": "ready_for_next_stage"}

        review = priority_action_contract(
            schedule_status="Not started",
            schedule_gate=schedule_blocked,
            schedule_responsible="MANAGEMENT",
            staffing_contract=staffing_invalid,
            logistics_contract=logistics_ready,
            core_readiness=core_needs_review,
        )
        self.assertEqual(review["action_key"], "review_readiness_data")

        schedule_start = priority_action_contract(
            schedule_status="Not started",
            schedule_gate=schedule_blocked,
            schedule_responsible="MANAGEMENT",
            staffing_contract=staffing_ready,
            logistics_contract=logistics_ready,
            core_readiness=core_blocked,
        )
        self.assertEqual(schedule_start["label"], "Start schedule preparation")
        self.assertEqual(schedule_start["source_label"], "Schedule")
        self.assertEqual(schedule_start["responsible"], "MANAGEMENT")

        due_at = date(2026, 6, 30)
        schedule_progress = priority_action_contract(
            schedule_status="In progress",
            schedule_gate=schedule_blocked,
            schedule_responsible="MANAGEMENT",
            schedule_deadline=due_at,
            staffing_contract=staffing_open,
            logistics_contract=logistics_in_progress,
            core_readiness=core_blocked,
        )
        self.assertEqual(schedule_progress["label"], "Complete schedules in Sinapsis")
        self.assertEqual(schedule_progress["deadline"], due_at)

        self.assertEqual(priority_action_contract("Approved", schedule_ready, "Completed", None, staffing_not_configured, logistics_ready, core_in_progress)["action_key"], "configure_staff_roles")
        staffing_owner = {
            "responsible_label": "ADMIN",
            "deadline": due_at,
            "deadline_label": "",
            "deadline_status": "upcoming",
        }
        staffing_priority = priority_action_contract(
            "Approved",
            schedule_ready,
            "Completed",
            date(2026, 7, 15),
            staffing_open,
            logistics_in_progress,
            core_in_progress,
            staffing_control=staffing_owner,
        )
        self.assertEqual(staffing_priority["action_key"], "assign_open_staff_roles")
        self.assertEqual(staffing_priority["responsible"], "ADMIN")
        self.assertEqual(staffing_priority["deadline"], due_at)
        self.assertEqual(priority_action_contract("Approved", schedule_ready, "Completed", due_at, staffing_awaiting, logistics_in_progress, core_in_progress)["action_key"], "follow_up_staff_confirmations")
        logistics_priority = priority_action_contract(
            "Approved",
            schedule_ready,
            "Completed",
            due_at,
            staffing_ready,
            logistics_configuration_required,
            core_in_progress,
            staffing_control=staffing_owner,
        )
        self.assertEqual(logistics_priority["action_key"], "configure_logistics_requirements")
        self.assertEqual(logistics_priority["responsible"], "ADMIN")
        self.assertEqual(logistics_priority["deadline_label"], "Not set")
        logistics_owner = {
            "responsible_label": "ADMIN",
            "deadline": date(2026, 7, 3),
            "deadline_label": "",
            "deadline_status": "upcoming",
        }
        logistics_with_owner = priority_action_contract(
            "Approved",
            schedule_ready,
            "Completed",
            due_at,
            staffing_ready,
            logistics_in_progress,
            core_in_progress,
            staffing_control=staffing_owner,
            logistics_control=logistics_owner,
        )
        self.assertEqual(logistics_with_owner["action_key"], "complete_logistics_arrangements")
        self.assertEqual(logistics_with_owner["responsible"], "ADMIN")
        self.assertEqual(logistics_with_owner["deadline"], date(2026, 7, 3))
        self.assertEqual(priority_action_contract("Approved", schedule_ready, "Completed", due_at, staffing_ready, logistics_in_progress, core_in_progress)["action_key"], "complete_logistics_arrangements")
        self.assertEqual(priority_action_contract("Approved", schedule_ready, "Completed", due_at, staffing_ready, logistics_files_missing, core_in_progress)["action_key"], "add_logistics_files_link")
        ready_not_applicable = priority_action_contract("Approved", schedule_ready, "Completed", None, staffing_ready, logistics_not_applicable, core_ready)
        self.assertEqual(ready_not_applicable["action_key"], "ready_for_next_stage")
        self.assertEqual(ready_not_applicable["responsible"], "")
        self.assertEqual(ready_not_applicable["deadline_label"], "-")
        self.assertEqual(
            priority_action_contract("Approved", {"status": "mystery"}, "Completed", None, staffing_ready, logistics_ready, core_ready)["action_key"],
            "review_readiness_data",
        )
        self.assertEqual(
            priority_action_contract("Approved", schedule_ready, "Completed", None, None, logistics_ready, core_ready)["action_key"],
            "review_readiness_data",
        )

    def test_my_action_rows_are_pending_and_sorted_by_urgency(self):
        base_session = self.session_record
        review_session = ExamSession(
            exam_session_name="Needs review action",
            category="Path School",
            status="Pending",
            session_date=date(2026, 7, 5),
            shifts="Morning",
            modules="Speaking",
            format="Online",
        )
        upcoming_session = ExamSession(
            exam_session_name="Upcoming action",
            category="Path School",
            status="Pending",
            session_date=date(2026, 7, 1),
            shifts="Morning",
            modules="Speaking",
            format="Online",
        )
        ready_session = ExamSession(
            exam_session_name="Ready action",
            category="Path School",
            status="Pending",
            session_date=date(2026, 7, 2),
            shifts="Morning",
            modules="Speaking",
            format="Online",
        )
        db.session.add_all([review_session, upcoming_session, ready_session])
        db.session.commit()
        today = date(2026, 6, 25)
        rows = [
            my_action_row_from_schedule_view({
                "session": base_session,
                "priority_action": {
                    "action_key": "complete_schedules_in_sinapsis",
                    "label": "Complete schedules in Sinapsis",
                    "source": "schedule",
                    "source_label": "Schedule",
                    "description": "Schedule work is pending.",
                    "responsible": "MANAGEMENT",
                    "deadline": date(2026, 6, 20),
                    "deadline_label": None,
                    "is_complete": False,
                },
            }, today=today),
            my_action_row_from_schedule_view({
                "session": review_session,
                "priority_action": {
                    "action_key": "review_readiness_data",
                    "label": "Review readiness data",
                    "source": "readiness",
                    "source_label": "Readiness",
                    "description": "Some readiness data is inconsistent or incomplete and needs to be reviewed.",
                    "responsible": "Not assigned",
                    "deadline": None,
                    "deadline_label": "Not set",
                    "is_complete": False,
                },
            }, today=today),
            my_action_row_from_schedule_view({
                "session": upcoming_session,
                "priority_action": {
                    "action_key": "assign_open_staff_roles",
                    "label": "Assign staff to open roles",
                    "source": "staffing",
                    "source_label": "Staffing",
                    "description": "1 Examiner position still needs to be filled.",
                    "responsible": "ADMIN",
                    "deadline": date(2026, 7, 1),
                    "deadline_label": "",
                    "deadline_status": "upcoming",
                    "is_complete": False,
                },
            }, today=today),
            my_action_row_from_schedule_view({
                "session": ready_session,
                "priority_action": {
                    "action_key": "ready_for_next_stage",
                    "label": "Ready for next stage",
                    "source": "core_readiness",
                    "source_label": "Core readiness",
                    "description": "Schedule approval, staffing and logistics are complete.",
                    "responsible": "",
                    "deadline": None,
                    "deadline_label": "-",
                    "is_complete": True,
                },
            }, today=today),
        ]

        sorted_rows = sort_my_actions([row for row in rows if row])

        self.assertEqual([row["status_label"] for row in sorted_rows], ["Needs review", "Overdue", "Upcoming"])
        self.assertEqual(sorted_rows[0]["action_label"], "Review readiness data")
        self.assertEqual(sorted_rows[1]["deadline_display"], "Overdue")
        self.assertEqual(sorted_rows[2]["deadline_display"], "01/07/2026")

    def test_staffing_control_contract_deadline_statuses(self):
        pending_staffing = {"ready": False}
        ready_staffing = {"ready": True}
        overdue_control = ExamSessionStaffingControl(staffing_due_at=date(2026, 6, 20), note="Overdue")
        today_control = ExamSessionStaffingControl(staffing_due_at=date(2026, 6, 25), note="Today")
        future_control = ExamSessionStaffingControl(staffing_due_at=date(2026, 6, 30), note="Future")

        self.assertEqual(
            staffing_control_contract(overdue_control, pending_staffing, today=date(2026, 6, 25))["deadline_label"],
            "Overdue",
        )
        self.assertEqual(
            staffing_control_contract(today_control, pending_staffing, today=date(2026, 6, 25))["deadline_label"],
            "Due today",
        )
        future = staffing_control_contract(future_control, pending_staffing, today=date(2026, 6, 25))
        self.assertEqual(future["deadline_status"], "upcoming")
        self.assertEqual(future["deadline"], date(2026, 6, 30))
        completed = staffing_control_contract(overdue_control, ready_staffing, today=date(2026, 6, 25))
        self.assertEqual(completed["deadline_status"], "completed")
        self.assertEqual(completed["deadline_label"], "Completed")
        self.assertFalse(completed["is_overdue"])

    def test_logistics_control_contract_deadline_statuses(self):
        pending_logistics = {"final_email_ready": False}
        ready_logistics = {"final_email_ready": True}
        overdue_control = ExamSessionLogisticsControl(logistics_due_at=date(2026, 6, 20), note="Overdue")
        today_control = ExamSessionLogisticsControl(logistics_due_at=date(2026, 6, 25), note="Today")
        future_control = ExamSessionLogisticsControl(logistics_due_at=date(2026, 6, 30), note="Future")

        self.assertEqual(
            logistics_control_contract(overdue_control, pending_logistics, today=date(2026, 6, 25))["deadline_label"],
            "Overdue",
        )
        self.assertEqual(
            logistics_control_contract(today_control, pending_logistics, today=date(2026, 6, 25))["deadline_label"],
            "Due today",
        )
        future = logistics_control_contract(future_control, pending_logistics, today=date(2026, 6, 25))
        self.assertEqual(future["deadline_status"], "upcoming")
        self.assertEqual(future["deadline"], date(2026, 6, 30))
        completed = logistics_control_contract(overdue_control, ready_logistics, today=date(2026, 6, 25))
        self.assertEqual(completed["deadline_status"], "completed")
        self.assertEqual(completed["deadline_label"], "Completed")
        self.assertFalse(completed["is_overdue"])

    def test_finance_readiness_contract_statuses_and_deadlines(self):
        not_reviewed = finance_readiness_contract(None, today=date(2026, 6, 25))
        self.assertEqual(not_reviewed["status"], "not_reviewed")
        self.assertFalse(not_reviewed["can_proceed"])
        self.assertTrue(not_reviewed["requires_action"])
        self.assertEqual(not_reviewed["responsible"], "FINANCE")
        self.assertEqual(not_reviewed["deadline_label"], "Not set")

        hold = ExamSessionFinanceControl(
            status="Finance hold",
            finance_due_at=date(2026, 6, 20),
            note="Commercial block.",
        )
        hold_contract = finance_readiness_contract(hold, today=date(2026, 6, 25))
        self.assertEqual(hold_contract["deadline_label"], "Overdue")
        self.assertFalse(hold_contract["can_proceed"])
        self.assertEqual(hold_contract["blockers"][0]["code"], "FINANCE_HOLD")

        cleared = ExamSessionFinanceControl(
            status="Cleared",
            finance_due_at=date(2026, 6, 20),
        )
        cleared_contract = finance_readiness_contract(cleared, today=date(2026, 6, 25))
        self.assertTrue(cleared_contract["can_proceed"])
        self.assertFalse(cleared_contract["requires_action"])
        self.assertEqual(cleared_contract["deadline_status"], "complete")

    def test_exam_session_overall_status_requires_logistics_files_link(self):
        session_record = ExamSession(
            exam_session_name="Logistics files required",
            category="Path School",
            status="Pending",
            session_date=date(2026, 6, 26),
            shifts="Morning",
            modules="Speaking",
            format="Online",
        )
        db.session.add(session_record)
        db.session.flush()
        db.session.add_all([
            ExamSessionSupervisorAssignment(
                exam_session_id=session_record.id,
                team_member_id=1,
                participation_status="Confirmed",
                logistics_enabled=True,
            ),
            ExamSessionLogisticsConcept(
                exam_session_id=session_record.id,
                provider="Flight",
                status="Confirmed",
            ),
        ])
        db.session.commit()

        statuses = exam_session_overall_statuses_by_session_ids([session_record.id])

        self.assertEqual(statuses[session_record.id], "Pending")

    def test_exam_session_overall_status_requires_logistics_concepts_when_enabled(self):
        session_record = ExamSession(
            exam_session_name="Logistics concepts required",
            category="Path School",
            status="Pending",
            session_date=date(2026, 6, 27),
            shifts="Morning",
            modules="Speaking",
            format="Online",
        )
        db.session.add(session_record)
        db.session.flush()
        db.session.add_all([
            ExamSessionSupervisorAssignment(
                exam_session_id=session_record.id,
                team_member_id=1,
                participation_status="Confirmed",
                logistics_enabled=True,
            ),
            ExamSessionLogistics(
                exam_session_id=session_record.id,
                logistics_files_url="https://example.com/logistics",
            ),
            ExamSessionMonthlyCandidateTotal(
                exam_session_id=session_record.id,
                month=6,
                total_candidates=30,
            ),
        ])
        db.session.commit()

        statuses = exam_session_overall_statuses_by_session_ids([session_record.id])

        self.assertEqual(statuses[session_record.id], "Pending")

    def test_exam_session_overall_status_confirms_when_staffing_and_logistics_final_ready(self):
        session_record = ExamSession(
            exam_session_name="Logistics final ready",
            category="Path School",
            status="Pending",
            session_date=date(2026, 6, 28),
            shifts="Morning",
            modules="Speaking",
            format="Online",
            emergency_contact_not_required=True,
        )
        db.session.add(session_record)
        db.session.flush()
        db.session.add_all([
            ExamSessionSupervisorAssignment(
                exam_session_id=session_record.id,
                team_member_id=1,
                participation_status="Confirmed",
                logistics_enabled=True,
            ),
            ExamSessionLogisticsConcept(
                exam_session_id=session_record.id,
                provider="Flight",
                status="Confirmed",
            ),
            ExamSessionLogistics(
                exam_session_id=session_record.id,
                logistics_files_url="https://example.com/logistics",
            ),
            ExamSessionMonthlyCandidateTotal(
                exam_session_id=session_record.id,
                month=6,
                total_candidates=30,
            ),
        ])
        db.session.commit()

        statuses = exam_session_overall_statuses_by_session_ids([session_record.id])

        self.assertEqual(statuses[session_record.id], "Confirmed")

    def test_exam_session_overall_status_requires_emergency_contact_decision(self):
        session_record = ExamSession(
            exam_session_name="Emergency decision required",
            category="Path School",
            status="Pending",
            session_date=date(2026, 6, 29),
            shifts="Morning",
            modules="Speaking",
            format="Online",
        )
        db.session.add(session_record)
        db.session.flush()
        db.session.add_all([
            ExamSessionSupervisorAssignment(
                exam_session_id=session_record.id,
                team_member_id=1,
                participation_status="Confirmed",
            ),
            ExamSessionMonthlyCandidateTotal(
                exam_session_id=session_record.id,
                month=6,
                total_candidates=30,
            ),
        ])
        db.session.commit()

        statuses = exam_session_overall_statuses_by_session_ids([session_record.id])
        self.assertEqual(statuses[session_record.id], "Pending")

        session_record.emergency_contact_not_required = True
        db.session.commit()
        statuses = exam_session_overall_statuses_by_session_ids([session_record.id])
        self.assertEqual(statuses[session_record.id], "Confirmed")

    def test_exam_session_overall_status_requires_shipment_recipient_for_onsite(self):
        session_record = ExamSession(
            exam_session_name="Onsite shipment required",
            category="Path School",
            status="Pending",
            session_date=date(2026, 6, 30),
            shifts="Morning",
            modules="Speaking",
            format="Onsite",
            emergency_contact_not_required=True,
        )
        db.session.add(session_record)
        db.session.flush()
        assignment = ExamSessionSupervisorAssignment(
            exam_session_id=session_record.id,
            team_member_id=1,
            participation_status="Confirmed",
        )
        db.session.add_all([
            assignment,
            ExamSessionMonthlyCandidateTotal(
                exam_session_id=session_record.id,
                month=6,
                total_candidates=30,
            ),
        ])
        db.session.commit()

        statuses = exam_session_overall_statuses_by_session_ids([session_record.id])
        self.assertEqual(statuses[session_record.id], "Pending")

        assignment.is_shipment_recipient = True
        db.session.commit()
        statuses = exam_session_overall_statuses_by_session_ids([session_record.id])
        self.assertEqual(statuses[session_record.id], "Confirmed")

    def test_exam_session_overall_status_requires_minimum_candidates_from_latest_active_month(self):
        session_record = ExamSession(
            exam_session_name="Candidates required",
            category="Path School",
            status="Pending",
            session_date=date(2026, 7, 1),
            minimum_candidates_required=30,
            shifts="Morning",
            modules="Speaking",
            format="Online",
            emergency_contact_not_required=True,
        )
        db.session.add(session_record)
        db.session.flush()
        db.session.add_all([
            ExamSessionSupervisorAssignment(
                exam_session_id=session_record.id,
                team_member_id=1,
                participation_status="Confirmed",
            ),
            ExamSessionMonthlyCandidateTotal(
                exam_session_id=session_record.id,
                month=6,
                total_candidates=28,
            ),
        ])
        db.session.commit()

        statuses = exam_session_overall_statuses_by_session_ids([session_record.id])

        self.assertEqual(statuses[session_record.id], "Pending")

        session_record.minimum_candidates_required = 28
        db.session.commit()
        statuses = exam_session_overall_statuses_by_session_ids([session_record.id])
        self.assertEqual(statuses[session_record.id], "Confirmed")

    def test_exam_session_pending_tooltip_lists_minimum_candidates_gap(self):
        session_record = ExamSession(
            exam_session_name="Candidates tooltip",
            category="Path School",
            status="Pending",
            session_date=date(2026, 7, 2),
            minimum_candidates_required=30,
            shifts="Morning",
            modules="Speaking",
            format="Online",
            emergency_contact_not_required=True,
        )
        db.session.add(session_record)
        db.session.flush()
        assignment = ExamSessionSupervisorAssignment(
            exam_session_id=session_record.id,
            team_member_id=1,
            participation_status="Confirmed",
        )
        db.session.add_all([
            assignment,
            ExamSessionMonthlyCandidateTotal(
                exam_session_id=session_record.id,
                month=6,
                total_candidates=28,
            ),
        ])
        db.session.commit()
        candidate_contract = monthly_candidate_requirement_contracts([session_record.id])[session_record.id]
        tooltip = exam_session_pending_status_tooltip(
            staffing_readiness_contract([assignment], [], []),
            logistics_readiness_contract([assignment], [], None),
            session_record,
            [assignment],
            candidate_contract,
        )

        self.assertIn("Minimum number of candidates not met: 28/30", tooltip)

    def test_monthly_registration_update_recalculates_exam_session_status(self):
        session_record = ExamSession(
            exam_session_name="Candidates route status",
            category="Path School",
            status="Pending",
            session_date=date(2026, 7, 3),
            minimum_candidates_required=30,
            shifts="Morning",
            modules="Speaking",
            format="Online",
            emergency_contact_not_required=True,
        )
        db.session.add(session_record)
        db.session.flush()
        db.session.add(ExamSessionSupervisorAssignment(
            exam_session_id=session_record.id,
            team_member_id=1,
            participation_status="Confirmed",
        ))
        db.session.commit()

        client = self.login_client()
        response = client.post(
            f"/monthly-exam-session-registrations/{session_record.id}/7",
            data={
                "csrf_token": "token",
                "total_candidates": "30",
                "registration_Speaking": "30",
            },
            follow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(db.session.get(ExamSession, session_record.id).status, "Confirmed")

        response = client.post(
            f"/monthly-exam-session-registrations/{session_record.id}/7",
            data={
                "csrf_token": "token",
                "total_candidates": "29",
                "registration_Speaking": "29",
            },
            follow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(db.session.get(ExamSession, session_record.id).status, "Pending")

    def test_deadline_error_redirect_reopens_attempted_action_form(self):
        client = self.login_client()

        response = client.post(
            f"/pre-session-control-tower/sessions/{self.session_record.id}/schedule",
            data={
                "csrf_token": "token",
                "action_key": "start_preparation",
                "next_action_due_at": "",
            },
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn("open_schedule_modal", response.headers["Location"])
        self.assertIn("open_schedule_action=start_preparation", response.headers["Location"])

    def test_staffing_control_view_does_not_create_record(self):
        client = self.login_client()

        response = client.get("/pre-session-control-tower?session_year=2026&view=sessions")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(ExamSessionStaffingControl.query.count(), 0)
        html = response.data.decode()
        self.assertIn("Responsible department", html)
        self.assertIn("ADMIN", html)
        self.assertIn("Responsible person", html)
        self.assertIn("Not assigned", html)
        self.assertIn("Staffing deadline", html)
        self.assertIn("Not set", html)

    def test_staffing_control_create_update_and_invalid_date(self):
        client = self.login_client()

        response = client.post(
            f"/pre-session-control-tower/sessions/{self.session_record.id}/staffing-control",
            data={
                "csrf_token": "token",
                "schedule_status": "Not started",
                "staffing_due_at": "2026-06-30",
                "note": "Call candidates before Friday.",
            },
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("open_schedule_modal", response.headers["Location"])
        self.assertIn("session_year=2026", response.headers["Location"])
        self.assertIn("schedule_status=Not+started", response.headers["Location"])
        control = ExamSessionStaffingControl.query.filter_by(exam_session_id=self.session_record.id).one()
        self.assertEqual(control.staffing_due_at, date(2026, 6, 30))
        self.assertEqual(control.note, "Call candidates before Friday.")
        self.assertEqual(control.updated_by, "admin")

        response = client.post(
            f"/pre-session-control-tower/sessions/{self.session_record.id}/staffing-control",
            data={
                "csrf_token": "token",
                "staffing_due_at": "2026-07-01",
                "note": "Updated note.",
            },
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(ExamSessionStaffingControl.query.count(), 1)
        self.assertEqual(control.staffing_due_at, date(2026, 7, 1))
        self.assertEqual(control.note, "Updated note.")

        response = client.post(
            f"/pre-session-control-tower/sessions/{self.session_record.id}/staffing-control",
            data={
                "csrf_token": "token",
                "staffing_due_at": "not-a-date",
                "note": "Should not save.",
            },
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("open_staffing_control=1", response.headers["Location"])
        self.assertEqual(ExamSessionStaffingControl.query.count(), 1)
        self.assertEqual(control.staffing_due_at, date(2026, 7, 1))
        self.assertEqual(control.note, "Updated note.")

    def test_package_unit_create_valid_and_generates_checklists(self):
        client = self.login_client()

        response = client.post(
            f"/pre-session-control-tower/sessions/{self.session_record.id}/packages/units",
            data={
                "csrf_token": "token",
                "room_name": " Room   1 ",
                "module_name": "Speaking",
                "expected_candidate_count": "12",
                "actual_label_count": "12",
                "has_nep_candidates": "1",
                "package_deadline": "2026-07-01",
                "note": "Prepare labels early.",
            },
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)
        unit = ExamSessionPackageUnit.query.one()
        self.assertEqual(unit.room_name, "Room 1")
        self.assertEqual(unit.module_name, "Speaking")
        self.assertEqual(unit.expected_candidate_count, 12)
        self.assertEqual(unit.actual_label_count, 12)
        self.assertTrue(unit.has_nep_candidates)
        self.assertEqual(unit.responsible_department, "LOGISTICS")
        self.assertEqual(unit.package_deadline, date(2026, 7, 1))
        self.assertEqual(ExamSessionPackageChecklistItem.query.filter_by(package_unit_id=unit.id).count(), 7)
        self.assertEqual(ExamSessionPackageChecklistItem.query.filter_by(exam_session_id=self.session_record.id, scope="SESSION").count(), 8)
        self.assertEqual(ExamSessionPackageEvent.query.filter_by(package_unit_id=unit.id, event_type="PACKAGE_UNIT_CREATED").count(), 1)

    def test_package_unit_rejects_invalid_required_and_negative_values(self):
        client = self.login_client()

        for payload in (
            {"room_name": "", "module_name": "Speaking"},
            {"room_name": "Room 1", "module_name": ""},
            {"room_name": "Room 1", "module_name": "Speaking", "expected_candidate_count": "-1"},
        ):
            data = {"csrf_token": "token", **payload}
            response = client.post(
                f"/pre-session-control-tower/sessions/{self.session_record.id}/packages/units",
                data=data,
                follow_redirects=False,
            )
            self.assertEqual(response.status_code, 302)
        self.assertEqual(ExamSessionPackageUnit.query.count(), 0)

    def test_package_pre_packing_requires_approved_schedule(self):
        client = self.login_client()
        unit = self.create_package_unit_record()

        response = client.post(
            f"/pre-session-control-tower/packages/units/{unit.id}/status",
            data={"csrf_token": "token", "new_status": "Pre-packing"},
            follow_redirects=True,
        )
        self.assertIn(b"Schedule approval is required before package pre-packing can begin.", response.data)
        self.assertEqual(ExamSessionPackageUnit.query.get(unit.id).status, "Not started")

        self.approve_schedule()
        response = client.post(
            f"/pre-session-control-tower/packages/units/{unit.id}/status",
            data={"csrf_token": "token", "new_status": "Pre-packing"},
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(ExamSessionPackageUnit.query.get(unit.id).status, "Pre-packing")

    def test_package_label_count_mismatch_blocks_advance_and_match_resolves(self):
        client = self.login_client()
        self.approve_schedule()
        unit = self.create_package_unit_record(status="Pre-packing", expected=10, actual=9)

        apply_item = ExamSessionPackageChecklistItem.query.filter_by(package_unit_id=unit.id, item_key="apply_labels").one()
        response = client.post(
            f"/pre-session-control-tower/packages/checklist-items/{apply_item.id}",
            data={"csrf_token": "token", "is_checked": "1"},
            follow_redirects=True,
        )
        self.assertIn(b"Label count mismatch. Report the issue to MANAGEMENT/ADMIN before continuing.", response.data)
        self.assertFalse(ExamSessionPackageChecklistItem.query.get(apply_item.id).is_checked)

        response = client.post(
            f"/pre-session-control-tower/packages/units/{unit.id}/status",
            data={"csrf_token": "token", "new_status": "Impersonal package ready"},
            follow_redirects=True,
        )
        self.assertIn(b"Label count mismatch. Report the issue to MANAGEMENT/ADMIN before continuing.", response.data)

        response = client.post(
            f"/pre-session-control-tower/packages/units/{unit.id}",
            data={
                "csrf_token": "token",
                "room_name": "Room 1",
                "module_name": "Speaking",
                "expected_candidate_count": "10",
                "actual_label_count": "10",
            },
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)
        unit = ExamSessionPackageUnit.query.get(unit.id)
        self.assertEqual(unit.expected_candidate_count, unit.actual_label_count)

    def test_package_pre_packing_complete_allows_impersonal_ready(self):
        client = self.login_client()
        self.approve_schedule()
        unit = self.create_package_unit_record(status="Pre-packing", expected=10, actual=10)
        for item in ExamSessionPackageChecklistItem.query.filter_by(package_unit_id=unit.id, phase="PRE_PACKING").all():
            item.is_checked = True
        db.session.commit()

        response = client.post(
            f"/pre-session-control-tower/packages/units/{unit.id}/status",
            data={"csrf_token": "token", "new_status": "Impersonal package ready"},
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(ExamSessionPackageUnit.query.get(unit.id).status, "Impersonal package ready")

    def test_package_final_assembly_requires_staffing_ready_and_quality_requires_checklist(self):
        client = self.login_client()
        self.approve_schedule()
        unit = self.create_package_unit_record(status="Ready to personalize", expected=10, actual=10)
        for item in ExamSessionPackageChecklistItem.query.filter_by(package_unit_id=unit.id, phase="PRE_PACKING").all():
            item.is_checked = True
        db.session.commit()

        response = client.post(
            f"/pre-session-control-tower/packages/units/{unit.id}/status",
            data={"csrf_token": "token", "new_status": "Final assembly"},
            follow_redirects=True,
        )
        self.assertIn(b"Staffing must be ready before final package assembly can begin.", response.data)
        self.assertEqual(ExamSessionPackageUnit.query.get(unit.id).status, "Ready to personalize")

        self.confirm_staffing()
        response = client.post(
            f"/pre-session-control-tower/packages/units/{unit.id}/status",
            data={"csrf_token": "token", "new_status": "Final assembly"},
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(ExamSessionPackageUnit.query.get(unit.id).status, "Final assembly")

        response = client.post(
            f"/pre-session-control-tower/packages/units/{unit.id}/status",
            data={"csrf_token": "token", "new_status": "Personalized"},
            follow_redirects=True,
        )
        self.assertIn(b"Complete the required final assembly checklist", response.data)
        for item in ExamSessionPackageChecklistItem.query.filter_by(package_unit_id=unit.id, phase="FINAL_ASSEMBLY").all():
            if item.item_key != "add_nep_label":
                item.is_checked = True
        db.session.commit()
        response = client.post(
            f"/pre-session-control-tower/packages/units/{unit.id}/status",
            data={"csrf_token": "token", "new_status": "Personalized"},
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)
        response = client.post(
            f"/pre-session-control-tower/packages/units/{unit.id}/status",
            data={"csrf_token": "token", "new_status": "Quality checked"},
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(ExamSessionPackageUnit.query.get(unit.id).status, "Quality checked")

    def test_package_reopening_requires_note_and_invalid_transition_is_rejected(self):
        client = self.login_client()
        self.approve_schedule()
        self.confirm_staffing()
        unit = self.create_package_unit_record(status="Quality checked", expected=10, actual=10)

        response = client.post(
            f"/pre-session-control-tower/packages/units/{unit.id}/status",
            data={"csrf_token": "token", "new_status": "Personalized", "note": ""},
            follow_redirects=True,
        )
        self.assertIn(b"A note is required when reopening or moving a package backwards.", response.data)
        self.assertEqual(ExamSessionPackageUnit.query.get(unit.id).status, "Quality checked")

        response = client.post(
            f"/pre-session-control-tower/packages/units/{unit.id}/status",
            data={"csrf_token": "token", "new_status": "Not started", "note": "Wrong jump"},
            follow_redirects=True,
        )
        self.assertIn(b"This package status transition is not allowed.", response.data)

        response = client.post(
            f"/pre-session-control-tower/packages/units/{unit.id}/status",
            data={"csrf_token": "token", "new_status": "Personalized", "note": "Reopened for check."},
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(ExamSessionPackageUnit.query.get(unit.id).status, "Personalized")

    def test_packages_readiness_contract_states(self):
        self.assertEqual(
            packages_readiness_contract(self.session_record, [], [], schedule_gate={"is_ready": False}, staffing_contract={"ready": False})["status"],
            "not_configured",
        )
        unit = self.create_package_unit_record(expected=10, actual=9)
        contract = packages_readiness_contract(self.session_record, [unit], [], schedule_gate={"is_ready": True}, staffing_contract={"ready": False})
        self.assertEqual(contract["status"], "blocked_discrepancy")

        unit.expected_candidate_count = 10
        unit.actual_label_count = 10
        unit.status = "Impersonal package ready"
        for item in unit.checklist_items:
            if item.phase == "PRE_PACKING":
                item.is_checked = True
        session_items = ExamSessionPackageChecklistItem.query.filter_by(exam_session_id=self.session_record.id, scope="SESSION").all()
        for item in session_items:
            if item.phase == "PRE_PACKING":
                item.is_checked = True
        db.session.commit()
        self.assertEqual(packages_readiness_contract(self.session_record, [unit], session_items, schedule_gate={"is_ready": True}, staffing_contract={"ready": False})["status"], "impersonal_ready")

        unit.status = "Ready to personalize"
        db.session.commit()
        self.assertEqual(packages_readiness_contract(self.session_record, [unit], session_items, schedule_gate={"is_ready": True}, staffing_contract={"ready": True})["status"], "ready_for_final_assembly")

        unit.status = "Quality checked"
        for item in unit.checklist_items:
            if item.phase == "FINAL_ASSEMBLY" and item.item_key != "add_nep_label":
                item.is_checked = True
        for item in session_items:
            if item.phase == "FINAL_ASSEMBLY":
                item.is_checked = True
        db.session.commit()
        self.assertEqual(packages_readiness_contract(self.session_record, [unit], session_items, schedule_gate={"is_ready": True}, staffing_contract={"ready": True})["status"], "quality_checked")

    def test_packages_action_contract_uses_package_status_and_deadlines(self):
        self.assertIsNone(packages_action_contract(
            self.session_record,
            {"status": "not_configured"},
            schedule_gate={"is_ready": False},
            staffing_contract={"ready": False},
            package_units=[],
        ))
        action = packages_action_contract(
            self.session_record,
            {"status": "not_configured"},
            schedule_gate={"is_ready": True},
            staffing_contract={"ready": False},
            package_units=[],
        )
        self.assertEqual(action["action_key"], "configure_package_units")
        self.assertEqual(action["responsible"], "LOGISTICS")

        unit = self.create_package_unit_record(status="Pre-packing", expected=10, actual=9)
        unit.package_deadline = date(2026, 6, 20)
        db.session.commit()
        action = packages_action_contract(
            self.session_record,
            {"status": "blocked_discrepancy"},
            schedule_gate={"is_ready": True},
            staffing_contract={"ready": False},
            package_units=[unit],
        )
        self.assertEqual(action["action_key"], "resolve_package_discrepancy")
        self.assertEqual(action["deadline"], date(2026, 6, 20))

        action = packages_action_contract(
            self.session_record,
            {"status": "impersonal_ready"},
            schedule_gate={"is_ready": True},
            staffing_contract={"ready": False},
            package_units=[unit],
        )
        self.assertIsNone(action)

        action = packages_action_contract(
            self.session_record,
            {"status": "mystery"},
            schedule_gate={"is_ready": True},
            staffing_contract={"ready": True},
            package_units=[unit],
        )
        self.assertEqual(action["action_key"], "review_package_data")

    def test_control_tower_packages_render_and_does_not_change_core(self):
        self.approve_schedule()
        self.create_package_unit_record(status="Pre-packing", expected=10, actual=9)
        client = self.login_client()

        response = client.get("/pre-session-control-tower?session_year=2026&view=sessions")
        html = response.data.decode()

        self.assertEqual(response.status_code, 200)
        self.assertIn("<th>Packages</th>", html)
        self.assertLess(html.index("<th>Logistics</th>"), html.index("<th>Packages</th>"))
        self.assertLess(html.index("<th>Packages</th>"), html.index("<th>Shipment</th>"))
        self.assertIn("Room 1", html)
        self.assertIn("Label count mismatch. Report the issue to MANAGEMENT/ADMIN before continuing.", html)
        self.assertIn("This status only covers schedule approval, staffing and logistics.", html)

        response = client.get("/pre-session-control-tower?session_year=2026&view=my-actions")
        html = response.data.decode()
        table_start = html.index('aria-label="My actions"')
        table_end = html.index('<div class="modal"', table_start)
        self.assertIn("Packages", html[table_start:table_end])
        self.assertIn("Resolve package discrepancy", html[table_start:table_end])
        self.assertIn("LOGISTICS", html[table_start:table_end])
        self.assertNotIn("Room 1", html[table_start:table_end])

    def test_control_tower_my_actions_includes_packages_as_parallel_lane(self):
        self.approve_schedule()
        db.session.add(ExamSessionSupervisorAssignment(exam_session_id=self.session_record.id))
        db.session.commit()
        unit = self.create_package_unit_record(status="Not started", expected=10, actual=10)
        unit.package_deadline = date(2026, 6, 30)
        db.session.commit()
        client = self.login_client()

        response = client.get("/pre-session-control-tower?session_year=2026&view=my-actions")
        html = response.data.decode()
        table_start = html.index('aria-label="My actions"')
        table_end = html.index('<div class="modal"', table_start)
        actions_table = html[table_start:table_end]

        self.assertIn("Assign staff to open roles", actions_table)
        self.assertIn("Start package pre-packing", actions_table)
        self.assertIn("Staffing", actions_table)
        self.assertIn("Packages", actions_table)
        self.assertIn("LOGISTICS", actions_table)

        response = client.get("/pre-session-control-tower?session_year=2026&view=my-actions&action_source=Packages&action_responsible=LOGISTICS")
        html = response.data.decode()
        table_start = html.index('aria-label="My actions"')
        table_end = html.index('<div class="modal"', table_start)
        filtered_table = html[table_start:table_end]

        self.assertIn("Start package pre-packing", filtered_table)
        self.assertNotIn("Assign staff to open roles", filtered_table)
        self.assertIn('option value="Packages" selected', html)
        self.assertIn('option value="LOGISTICS" selected', html)

    def test_control_tower_my_actions_skips_packages_blocked_by_schedule(self):
        self.create_package_unit_record(status="Not started", expected=10, actual=10)
        client = self.login_client()

        response = client.get("/pre-session-control-tower?session_year=2026&view=my-actions")
        html = response.data.decode()
        table_start = html.index('aria-label="My actions"')
        table_end = html.index('<div class="modal"', table_start)
        actions_table = html[table_start:table_end]

        self.assertIn("Start schedule preparation", actions_table)
        self.assertNotIn("Start package pre-packing", actions_table)

    def test_shipment_bundle_create_generates_checklist_and_history(self):
        self.create_supervisor()
        self.assign_confirmed_supervisor()
        client = self.login_client()

        response = client.post(
            f"/pre-session-control-tower/sessions/{self.session_record.id}/shipments/bundles",
            data={
                "csrf_token": "token",
                "supervisor_staff_id": "1",
                "delivery_address": "Av. Siempre Viva 123",
                "delivery_city": "Cordoba",
                "delivery_province": "Cordoba",
                "courier": "",
                "included_session_ids": [str(self.session_record.id)],
                "note": "Initial bundle.",
            },
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)
        bundle = ExamSessionShipmentBundle.query.one()
        self.assertEqual(bundle.courier, "Correo Argentino")
        self.assertEqual(bundle.responsible_department, "LOGISTICS")
        self.assertEqual(ExamSessionShipmentBundleSession.query.filter_by(bundle_id=bundle.id).count(), 1)
        self.assertEqual(ExamSessionShipmentChecklistItem.query.filter_by(bundle_id=bundle.id).count(), 5)
        self.assertEqual(ExamSessionShipmentEvent.query.filter_by(bundle_id=bundle.id, event_type="SHIPMENT_BUNDLE_CREATED").count(), 1)

    def test_shipment_recipient_helper_uses_marked_assignment_and_ignores_empty_rows(self):
        self.create_supervisor(staff_id=1, name="Laura Mendez")
        self.create_supervisor(staff_id=4, name="Mateo Silva")
        self.create_supervisor(staff_id=7, name="Ana Torres")
        db.session.add(ExamSessionSupervisorAssignment(
            exam_session_id=self.session_record.id,
            team_member_id=None,
            participation_status="Confirmed",
            is_shipment_recipient=True,
        ))
        db.session.add(ExamSessionSupervisorAssignment(
            exam_session_id=self.session_record.id,
            team_member_id=1,
            participation_status="Pending",
        ))
        db.session.add(ExamSessionSupervisorAssignment(
            exam_session_id=self.session_record.id,
            team_member_id=4,
            participation_status="Confirmed",
            is_shipment_recipient=True,
        ))
        db.session.add(ExamSessionSupervisorAssignment(
            exam_session_id=self.session_record.id,
            team_member_id=7,
            participation_status="Confirmed",
        ))
        db.session.commit()

        assignments = (
            ExamSessionSupervisorAssignment.query.filter_by(exam_session_id=self.session_record.id)
            .order_by(ExamSessionSupervisorAssignment.created_on.asc(), ExamSessionSupervisorAssignment.id.asc())
            .all()
        )
        recipient = get_exam_session_shipment_recipient_supervisor(assignments)

        self.assertEqual(recipient.id, 4)

        for assignment in assignments:
            assignment.team_member_id = None
        db.session.commit()
        self.assertIsNone(get_exam_session_shipment_recipient_supervisor(assignments))

    def test_exam_session_planner_shows_manual_shipment_recipient_controls(self):
        self.create_supervisor(staff_id=1, name="Laura Mendez")
        self.create_supervisor(staff_id=4, name="Mateo Silva")
        self.session_record.format = "Onsite"
        provider_type = ProviderType(name="Transport", is_system=False, color_key="provider-type-1")
        db.session.add(provider_type)
        db.session.flush()
        provider = Provider(
            provider_type_id=provider_type.id,
            name="Path Shuttle",
            full_address="Main Avenue 123",
            available_in_logistics=True,
        )
        db.session.add(provider)
        db.session.add(ExamSessionSupervisorAssignment(
            exam_session_id=self.session_record.id,
            team_member_id=1,
            participation_status="Confirmed",
        ))
        db.session.add(ExamSessionSupervisorAssignment(
            exam_session_id=self.session_record.id,
            team_member_id=4,
            participation_status="Confirmed",
        ))
        db.session.add(ExamSessionSupervisorAssignment(
            exam_session_id=self.session_record.id,
            team_member_id=None,
            participation_status="Pending",
        ))
        db.session.commit()
        client = self.login_client()

        response = client.get("/exam-session-planner?session_year=2026")
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("data-shipment-recipient-checkbox", html)
        self.assertIn("data-shipment-recipient-picker", html)
        self.assertIn('value="supervisor:existing-', html)
        self.assertIn("staff-card-grid", html)
        self.assertIn("staff-assignment-card", html)
        self.assertNotIn("<th>Staff member</th>", html)
        self.assertNotIn("<th>Participation</th>", html)
        self.assertIn("Add supervisor", html)
        self.assertIn("Add examiner", html)
        self.assertIn("Assignment", html)
        self.assertIn("Time & distance", html)
        self.assertIn("Fees", html)
        self.assertIn("Contact", html)
        self.assertIn("data-staff-collapsible-section", html)
        self.assertIn("data-staff-section-toggle", html)
        self.assertIn("staff-card-header-tags", html)
        self.assertIn("data-staff-header-participation", html)
        self.assertIn("data-staff-header-logistics", html)
        self.assertIn("staff-card-assignment-block is-collapsed", html)
        self.assertIn("staff-card-time-block is-collapsed", html)
        self.assertIn("staff-card-fees-block is-collapsed", html)
        self.assertIn("data-team-member-select", html)
        self.assertIn("data-participation-select", html)
        self.assertIn("data-logistics-control", html)
        self.assertIn("Does not apply", html)
        self.assertIn("Simple logistics", html)
        self.assertIn("Complex logistics", html)
        self.assertNotIn("data-logistics-checkbox", html)
        self.assertIn("data-km-field", html)
        self.assertIn("data-time-range-stack", html)
        self.assertIn("data-role-fee-display", html)
        self.assertIn("data-device-dep-display", html)
        self.assertIn("data-commuting-cell", html)
        self.assertIn("data-fuel-cell", html)
        self.assertIn("data-vehicle-cell", html)
        self.assertIn("data-seniority-display", html)
        self.assertIn("data-total-fee-cell", html)
        self.assertIn("data-staff-email-cell", html)
        self.assertIn("data-copy-invitation-email", html)
        self.assertIn("Pre-confirmation email", html)
        self.assertIn("Official confirmation email", html)
        self.assertIn("Final information email", html)
        self.assertIn("data-staff-preconfirmation-email", html)
        self.assertIn("data-staff-confirmation-email", html)
        self.assertIn("data-staff-final-information-email", html)
        self.assertIn("data-remove-supervisor-row", html)
        self.assertNotIn("<th>Non-available</th>", html)
        self.assertIn("Non-available staff members", html)
        self.assertIn("data-session-non-available-picker", html)
        self.assertIn("data-row-non-available-fields", html)
        format_column_index = html.index("<th>Format</th>")
        supervisors_column_index = html.index("<th>Supervisors</th>", format_column_index)
        examiners_column_index = html.index("<th>Examiners</th>", supervisors_column_index)
        interns_column_index = html.index("<th>Interns</th>", examiners_column_index)
        logistics_column_index = html.index("<th>Logistics</th>", interns_column_index)
        self.assertLess(format_column_index, supervisors_column_index)
        self.assertLess(supervisors_column_index, examiners_column_index)
        self.assertLess(examiners_column_index, interns_column_index)
        self.assertLess(interns_column_index, logistics_column_index)
        self.assertIn("3 supervisors required", html)
        self.assertIn("Laura Mendez", html)
        self.assertIn("Mateo Silva", html)
        self.assertIn("(confirmed)", html)
        self.assertIn("1 role to cover", html)
        self.assertIn("Supervisors cost", html)
        self.assertIn("Examiners cost", html)
        self.assertIn("Interns cost", html)

    def test_exam_session_planner_hides_shipment_recipient_control_for_online_sessions(self):
        supervisor = self.create_supervisor(staff_id=1, name="Laura Mendez")
        db.session.add(ExamSessionSupervisorAssignment(
            exam_session_id=self.session_record.id,
            team_member_id=supervisor.id,
            participation_status="Confirmed",
        ))
        db.session.commit()
        client = self.login_client()

        online_html = client.get("/exam-session-planner?session_year=2026").get_data(as_text=True)
        self.assertNotIn("data-shipment-recipient-checkbox", online_html)
        self.assertNotIn("🚚", online_html)

        self.session_record.format = "Onsite"
        db.session.commit()
        onsite_html = client.get("/exam-session-planner?session_year=2026").get_data(as_text=True)
        self.assertIn("data-shipment-recipient-checkbox", onsite_html)
        self.assertIn("🚚", onsite_html)

    def test_exam_session_members_can_save_examiner_as_shipment_recipient(self):
        supervisor = self.create_supervisor(staff_id=1, name="Laura Mendez")
        examiner = AcademicStaff(id=2, status="Active", full_name="Noah Rivers", roles="Examiner")
        self.session_record.format = "Onsite"
        db.session.add(examiner)
        db.session.flush()
        supervisor_assignment = ExamSessionSupervisorAssignment(
            exam_session_id=self.session_record.id,
            team_member_id=supervisor.id,
            participation_status="Confirmed",
        )
        examiner_assignment = ExamSessionExaminerAssignment(
            exam_session_id=self.session_record.id,
            team_member_id=examiner.id,
            participation_status="Confirmed",
        )
        db.session.add_all([supervisor_assignment, examiner_assignment])
        db.session.commit()
        client = self.login_client()

        response = client.post(
            f"/exam-session-planner/sessions/{self.session_record.id}/members",
            data={
                "csrf_token": "token",
                "session_year": "2026",
                "modal_action": "save",
                "session_non_available_member_ids": "",
                "supervisor_row_keys": f"existing-{supervisor_assignment.id}",
                f"supervisor_assignment_id_existing-{supervisor_assignment.id}": str(supervisor_assignment.id),
                f"supervisor_team_member_id_existing-{supervisor_assignment.id}": str(supervisor.id),
                f"supervisor_participation_status_existing-{supervisor_assignment.id}": "Confirmed",
                f"supervisor_logistics_type_existing-{supervisor_assignment.id}": "Does not apply",
                "examiner_row_keys": f"existing-{examiner_assignment.id}",
                f"examiner_assignment_id_existing-{examiner_assignment.id}": str(examiner_assignment.id),
                f"examiner_team_member_id_existing-{examiner_assignment.id}": str(examiner.id),
                f"examiner_participation_status_existing-{examiner_assignment.id}": "Confirmed",
                f"examiner_logistics_type_existing-{examiner_assignment.id}": "Does not apply",
                "shipment_recipient_assignment": f"examiner:existing-{examiner_assignment.id}",
            },
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)
        db.session.refresh(supervisor_assignment)
        db.session.refresh(examiner_assignment)
        self.assertFalse(supervisor_assignment.is_shipment_recipient)
        self.assertTrue(examiner_assignment.is_shipment_recipient)

        html = client.get("/exam-session-planner?session_year=2026").get_data(as_text=True)
        recipient_start = html.index('data-shipment-recipient-row="true"')
        recipient_fragment = html[recipient_start - 800:recipient_start + 800]
        self.assertIn("Noah Rivers", recipient_fragment)
        self.assertNotIn("Laura Mendez", recipient_fragment)

    def test_exam_session_planner_renders_one_preconfirmation_button_per_assigned_staff_card(self):
        supervisor = self.create_supervisor(staff_id=1, name="Laura Mendez")
        examiner = AcademicStaff(id=2, status="Active", full_name="Noah Rivers", roles="Examiner")
        intern = AcademicStaff(id=3, status="Active", full_name="Iris Lane", roles="Intern")
        db.session.add_all([
            examiner,
            intern,
            ExamSessionSupervisorAssignment(
                exam_session_id=self.session_record.id,
                team_member_id=supervisor.id,
                participation_status="Pending",
            ),
            ExamSessionExaminerAssignment(
                exam_session_id=self.session_record.id,
                team_member_id=examiner.id,
                participation_status="Pending",
            ),
            ExamSessionInternAssignment(
                exam_session_id=self.session_record.id,
                team_member_id=intern.id,
                participation_status="Pending",
            ),
        ])
        db.session.commit()

        response = self.login_client().get("/exam-session-planner?session_year=2026")
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(html.count("data-staff-preconfirmation-email"), 3)
        self.assertIn("data-preconfirmation-certifications", html)
        self.assertIn("data-session-date-email=\"Thursday 25 June 2026\"", html)
        self.assertIn("data-session-shift=\"Morning\"", html)

    def test_exam_session_planner_modal_lists_assigned_staff_dietary_requirements(self):
        supervisor = self.create_supervisor(staff_id=1, name="Laura Mendez")
        supervisor.title = "Lic."
        supervisor.dietary_requirements = "Gluten-free meal"
        examiner = AcademicStaff(
            id=2,
            status="Active",
            title="Mr",
            full_name="Noah Rivers",
            roles="Examiner",
            dietary_requirements="Vegetarian lunch",
        )
        other_session = ExamSession(
            exam_session_name="Same date session",
            status="Pending",
            session_date=self.session_record.session_date,
            shifts="Afternoon",
            modules="Speaking",
            format="Online",
        )
        db.session.add_all([examiner, other_session])
        db.session.flush()
        db.session.add_all([
            ExamSessionSupervisorAssignment(
                exam_session_id=self.session_record.id,
                team_member_id=supervisor.id,
                participation_status="Pending",
            ),
            ExamSessionSupervisorAssignment(
                exam_session_id=other_session.id,
                team_member_id=supervisor.id,
                participation_status="Pending",
            ),
            ExamSessionExaminerAssignment(
                exam_session_id=self.session_record.id,
                team_member_id=examiner.id,
                participation_status="Pending",
            ),
        ])
        db.session.commit()

        response = self.login_client().get("/exam-session-planner?session_year=2026")
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("same-date-conflict-alert", html)
        self.assertIn("dietary-requirements-alert", html)
        self.assertLess(
            html.index("same-date-conflict-alert"),
            html.index("dietary-requirements-alert"),
        )
        self.assertIn("Dietary requirements for Laura Mendez: Gluten-free meal", html)
        self.assertIn("Dietary requirements for Noah Rivers: Vegetarian lunch", html)
        self.assertIn("session-dietary-requirements-tag", html)
        self.assertIn(">Dietary requirements</span>", html)
        self.assertIn(
            "Dietary requirements for Laura Mendez: Gluten-free meal&#10;Dietary requirements for Noah Rivers: Vegetarian lunch",
            html,
        )
        self.assertIn('data-title="Lic."', html)
        self.assertIn('data-dietary-requirements="Gluten-free meal"', html)
        self.assertIn('data-title="Mr"', html)
        self.assertIn('data-dietary-requirements="Vegetarian lunch"', html)

    def test_staff_preconfirmation_email_for_supervisor_includes_session_and_certification(self):
        payload = self.build_staff_preconfirmation_email({
            "full_name": "Laura Mendez",
            "role": "Supervisor",
            "session_name": "London Bridge",
            "session_date": "Thursday 10 December 2026",
            "shift": "Morning",
            "format": "Onsite",
            "address": "Pilar, Buenos Aires",
            "certifications": {
                "Supervisor": {
                    "remote_training_period": "from Monday 20 July 2026 to Friday 24 July 2026",
                    "annual_meeting": "Friday 31 July 2026 from 9 to 16 h (GMT-3)",
                },
            },
        })

        self.assertNotIn("error", payload)
        self.assertIn("Dear Laura Mendez,", payload["text"])
        self.assertIn("Participation awaiting your pre-confirmation", payload["html"])
        self.assertIn("pre-selected as a <strong>Supervisor</strong>", payload["html"])
        self.assertIn("<strong>Exam session:</strong> London Bridge", payload["html"])
        self.assertIn("<strong>Date:</strong> Thursday 10 December 2026", payload["html"])
        self.assertIn("<strong>Shift:</strong> Morning", payload["html"])
        self.assertIn("<strong>Format:</strong> Onsite", payload["html"])
        self.assertIn("<strong>Address:</strong> Pilar, Buenos Aires", payload["html"])
        self.assertIn("SUPERVISOR CERTIFICATION", payload["html"])
        self.assertIn("Remote training period:", payload["html"])
        self.assertIn("Further information, such as platform access details", payload["text"])
        self.assertIn("<strong>pre-confirming your availability for the assigned exam session and training programme</strong>", payload["html"])
        self.assertNotIn("undefined", payload["html"])
        self.assertNotIn("null", payload["html"])
        self.assertNotIn("None", payload["html"])

    def test_staff_preconfirmation_email_for_examiner_validates_certification_dates(self):
        payload = self.build_staff_preconfirmation_email({
            "full_name": "Noah Rivers",
            "role": "Examiner",
            "session_name": "London Bridge",
            "session_date": "Thursday 10 December 2026",
            "format": "Online",
            "certifications": {
                "Examiner": {
                    "remote_training_period": "",
                    "annual_meeting": "Friday 31 July 2026 from 10 to 16 h (GMT-3)",
                },
            },
        })

        self.assertEqual(payload["error"], "Examiner certification dates are not configured.")

    def test_staff_preconfirmation_email_for_intern_omits_training_programme(self):
        payload = self.build_staff_preconfirmation_email({
            "full_name": "Iris Lane",
            "role": "Intern",
            "session_name": "Online Bridge",
            "session_date": "Friday 11 December 2026",
            "format": "Online",
            "certifications": {},
        })

        self.assertNotIn("error", payload)
        self.assertIn("pre-selected as a <strong>Intern</strong>", payload["html"])
        self.assertNotIn("EXAMINER CERTIFICATION", payload["html"])
        self.assertNotIn("SUPERVISOR CERTIFICATION", payload["html"])
        self.assertNotIn("training programme for this role", payload["text"])
        self.assertNotIn("assigned exam session and training programme", payload["text"])
        self.assertIn("assigned exam session.", payload["text"])
        self.assertNotIn("<strong>Address:</strong>", payload["html"])

    def test_staff_preconfirmation_email_requires_onsite_address(self):
        payload = self.build_staff_preconfirmation_email({
            "full_name": "Laura Mendez",
            "role": "Supervisor",
            "session_name": "London Bridge",
            "session_date": "Thursday 10 December 2026",
            "format": "Onsite",
            "address": "",
            "certifications": {
                "Supervisor": {
                    "remote_training_period": "from Monday 20 July 2026 to Friday 24 July 2026",
                    "annual_meeting": "Friday 31 July 2026 from 9 to 16 h (GMT-3)",
                },
            },
        })

        self.assertEqual(payload["error"], "Exam session address is required for onsite sessions.")

    def test_exam_session_planner_renders_existing_official_confirmation_button_without_duplicates(self):
        supervisor = self.create_supervisor(staff_id=1, name="Laura Mendez")
        self.session_record.format = "Onsite"
        self.session_record.full_address_google_maps = "Pilar, Buenos Aires"
        db.session.add(ExamSessionSupervisorAssignment(
            exam_session_id=self.session_record.id,
            team_member_id=supervisor.id,
            participation_status="Confirmed",
        ))
        db.session.add(StaffPaymentSettings(next_payment_date=date(2026, 12, 27)))
        db.session.commit()

        html = self.login_client().get("/exam-session-planner?session_year=2026").get_data(as_text=True)

        self.assertEqual(html.count("data-staff-confirmation-email"), 1)
        self.assertIn("Official confirmation email", html)
        self.assertIn('data-staff-payment-next-payment-date="27/12/2026"', html)
        self.assertNotIn(">Confirmation email</button>", html)

    def test_exam_session_planner_disables_official_confirmation_button_for_online_session(self):
        supervisor = self.create_supervisor(staff_id=1, name="Laura Mendez")
        db.session.add(ExamSessionSupervisorAssignment(
            exam_session_id=self.session_record.id,
            team_member_id=supervisor.id,
            participation_status="Confirmed",
        ))
        db.session.commit()

        html = self.login_client().get("/exam-session-planner?session_year=2026").get_data(as_text=True)

        self.assertIn("Official confirmation email is only available for onsite sessions.", html)
        self.assertRegex(html, r"data-staff-confirmation-email[^>]*disabled")

    def official_confirmation_base_payload(self, **overrides):
        payload = {
            "full_name": "Laura Mendez",
            "role": "Supervisor",
            "session_name": "London Bridge",
            "session_date": "Thursday, December 10th, 2026",
            "time_ranges": ["10.50 to 12.30 h"],
            "format": "Onsite",
            "address": "Pilar, Buenos Aires",
            "fee_lines": [
                {"label": "Role fee", "value": "ARS 22.000"},
                {"label": "Device depreciation", "value": "ARS 6.000"},
                {"label": "Commuting", "value": "ARS 20.000"},
                {"label": "Fuel", "value": "ARS 2.000"},
                {"label": "Vehicle depreciation", "value": "ARS 2.000"},
                {"label": "Seniority", "value": "ARS 2.200"},
            ],
            "total_fee": "ARS 54.200",
            "logistics_status": "Simple logistics",
            "logistics_url": "https://example.com/logistics",
            "next_payment_date": "27/12/2026",
            "contacts": [
                {
                    "label": "Supervisor 1",
                    "role": "Supervisor",
                    "assigned": True,
                    "name": "Laura Mendez",
                    "title": "Lic.",
                    "phone": "+5491128508482",
                    "dietaryRequirements": "Celiaque",
                    "seniority": True,
                    "status": "Confirmed",
                    "statusTone": "green",
                },
                {
                    "label": "Examiner 1",
                    "role": "Examiner",
                    "assigned": True,
                    "name": "Noah Rivers",
                    "title": "Mr",
                    "phone": "",
                    "status": "To be confirmed",
                    "statusTone": "yellow",
                },
                {
                    "label": "Intern 1",
                    "role": "Intern",
                    "assigned": False,
                    "emptyMessage": "This intern has not been assigned yet",
                },
            ],
        }
        payload.update(overrides)
        return payload

    def test_staff_official_confirmation_email_for_supervisor_contains_required_sections(self):
        result = self.build_staff_official_confirmation_email(self.official_confirmation_base_payload())

        self.assertNotIn("error", result)
        self.assertIn("OFFICIAL CONFIRMATION", result["html"])
        self.assertIn("Path exam session official confirmation", result["html"])
        self.assertIn("Dear Laura Mendez,", result["text"])
        self.assertIn("Participation awaiting your confirmation", result["html"])
        self.assertIn("selected as a <strong>Supervisor</strong>", result["html"])
        self.assertIn("EXAM SESSION INFORMATION", result["html"])
        self.assertIn("Thursday, December 10th, 2026", result["text"])
        self.assertIn("10.50 to 12.30 h GMT-3", result["html"])
        self.assertIn("<em style=", result["html"])
        self.assertIn("50 minutes", result["text"])
        self.assertIn("📍 Venue", result["html"])
        self.assertIn("Pilar, Buenos Aires", result["html"])
        self.assertIn("FEES AND INVOICE", result["html"])
        self.assertIn("Role fee", result["html"])
        self.assertIn("Device depreciation", result["html"])
        self.assertIn("TOTAL FEE:", result["html"])
        self.assertIn("ARS 54.200", result["html"])
        self.assertNotIn("unified invoice with the TOTAL FEE", result["text"])
        self.assertIn("<em><u>Once all your exam sessions are over</u></em>", result["html"])
        self.assertIn("background:#f1f3f2;border:1px solid #d9dfdc;border-radius:10px", result["html"])
        self.assertIn("font:400 13px/1.5 Arial, Helvetica, sans-serif", result["html"])
        self.assertIn('href="mailto:finance@pathexaminations.com"', result["html"])
        self.assertIn("<strong><u>finance@pathexaminations.com</u></strong>", result["html"])
        self.assertIn("<strong>sum of the total fees</strong>", result["html"])
        self.assertIn('href="https://drive.google.com/drive/u/0/my-drive"', result["html"])
        self.assertIn("<strong>attached sample</strong>", result["html"])
        self.assertIn("Payments will be processed on <strong>27/12/2026</strong>", result["html"])
        self.assertIn("<strong>at 5:00 pm (GMT-3)</strong>", result["html"])
        self.assertIn("Bellis Ignis Group SRL", result["text"])
        self.assertIn("SESSION MATERIALS", result["html"])
        self.assertLess(
            result["html"].index("Exam session schedule"),
            result["html"].index("Exam box shipment"),
        )
        self.assertLess(
            result["html"].index("Exam box shipment"),
            result["html"].index("Material for examiners"),
        )
        self.assertIn("Once you confirm your participation as a Supervisor, our Logistics team will contact you in due course to arrange the delivery of the materials for your assigned exam session(s).", result["html"])
        self.assertIn("Exam box shipment\nView material:", result["text"])
        self.assertIn("Supervisor guidelines", result["html"])
        self.assertIn("View material", result["html"])
        self.assertIn("STAFF MEMBERS AND EMERGENCY LINES", result["html"])
        self.assertIn("Path emergency lines for any urgent matters", result["html"])
        self.assertIn("Path emergency lines for any urgent matters", result["text"])
        self.assertNotIn("this exam session, as well as the Path emergency line for any urgent matters", result["html"])
        self.assertIn("Lic. Laura Mendez", result["html"])
        self.assertIn("Mr Noah Rivers", result["html"])
        self.assertLess(
            result["html"].index(">Senior</span>"),
            result["html"].index(">Confirmed</span>"),
        )
        self.assertIn("Confirmed", result["html"])
        self.assertIn("To be confirmed", result["html"])
        self.assertIn("Celiaque", result["html"])
        self.assertIn("background:#e7f5f8", result["html"])
        self.assertIn("Lic. Laura Mendez (Senior) (Confirmed) - Dietary requirements: Celiaque", result["text"])
        self.assertIn("This intern has not been assigned yet", result["html"])
        self.assertIn("Phone number not available", result["text"])
        self.assertIn('href="https://wa.me/5491128508482"', result["html"])
        self.assertIn("+5491128508482 (https://wa.me/5491128508482)", result["text"])
        self.assertIn("Emergency lines", result["text"])
        self.assertNotIn("Please contact your Supervisor first before using these emergency lines.", result["text"])
        self.assertIn("https://wa.me/5491150954847", result["html"])
        self.assertIn("https://wa.me/5491133945761", result["html"])
        self.assertIn("https://wa.me/5491155692629", result["html"])
        self.assertIn("https://wa.me/5491128508482", result["html"])
        self.assertIn("- Path Examinations office at +5491150954847", result["text"])
        self.assertNotIn("EXAM SESSION MATERIAL", result["html"])
        self.assertIn("TRAVEL AND COMMUTING", result["html"])
        self.assertIn('href="https://example.com/logistics"', result["html"])
        self.assertIn("EXAM SESSION FINAL CHECKS", result["html"])
        self.assertIn("Click here to confirm participation and material reception", result["html"])
        self.assertIn("mailto:admin%40pathexaminations.com", result["html"])
        self.assertNotIn("undefined", result["html"])
        self.assertNotIn("null", result["html"])
        self.assertNotIn("None", result["html"])

    def test_staff_official_confirmation_email_for_examiner_uses_examiner_sections(self):
        result = self.build_staff_official_confirmation_email(self.official_confirmation_base_payload(
            full_name="Noah Rivers",
            role="Examiner",
            logistics_status="Does not apply",
            logistics_url="",
            fee_lines=[{"label": "Role fee", "value": "ARS 22.000"}],
            total_fee="ARS 22.000",
        ))

        self.assertNotIn("error", result)
        self.assertIn("selected as an <strong>Examiner</strong>", result["html"])
        self.assertIn("30 minutes", result["text"])
        self.assertIn("Examiner guidelines", result["html"])
        self.assertIn("This section contains the materials needed to conduct the Listening and speaking module.", result["html"])
        self.assertNotIn("Listening and Speaking Module", result["html"])
        self.assertIn("ATTENDANCE, MARKS AND RECORDINGS", result["html"])
        self.assertIn("Please contact your Supervisor first before using these emergency lines.", result["text"])
        self.assertNotIn("EXAM SESSION MATERIAL", result["html"])
        self.assertNotIn("Supervisor guidelines", result["html"])

    def test_staff_official_confirmation_email_for_intern_omits_material_and_final_instruction_sections(self):
        result = self.build_staff_official_confirmation_email(self.official_confirmation_base_payload(
            full_name="Iris Lane",
            role="Intern",
            logistics_status="Complex logistics",
            logistics_url="https://example.com/complex-logistics",
            fee_lines=[{"label": "Role fee", "value": "ARS 10.000"}],
            total_fee="ARS 10.000",
        ))

        self.assertNotIn("error", result)
        self.assertIn("selected as an <strong>Intern</strong>", result["html"])
        self.assertIn("30 minutes", result["text"])
        self.assertIn("All relevant information and documents for your trip or commute can be found", result["text"])
        self.assertIn("Please contact your Supervisor first before using these emergency lines.", result["text"])
        self.assertNotIn("SESSION MATERIALS", result["html"])
        self.assertNotIn("ATTENDANCE, MARKS AND RECORDINGS", result["html"])
        self.assertNotIn("EXAM SESSION FINAL CHECKS", result["html"])
        self.assertNotIn("EXAM SESSION MATERIAL", result["html"])

    def test_staff_official_confirmation_email_validations(self):
        online = self.build_staff_official_confirmation_email(self.official_confirmation_base_payload(format="Online"))
        missing_time = self.build_staff_official_confirmation_email(self.official_confirmation_base_payload(time_ranges=[]))
        missing_total = self.build_staff_official_confirmation_email(self.official_confirmation_base_payload(total_fee="-"))
        missing_logistics_url = self.build_staff_official_confirmation_email(self.official_confirmation_base_payload(logistics_url=""))
        missing_next_payment_date = self.build_staff_official_confirmation_email(self.official_confirmation_base_payload(next_payment_date=""))

        self.assertEqual(online["error"], "Official confirmation email is only available for onsite sessions.")
        self.assertEqual(missing_time["error"], "Staff member time range is required for official confirmation emails.")
        self.assertEqual(missing_total["error"], "Total fee is required for official confirmation emails.")
        self.assertEqual(missing_logistics_url["error"], "Logistics folder link is required for simple logistics.")
        self.assertEqual(missing_next_payment_date["error"], "Next payment date is required for official confirmation emails.")

    def test_exam_session_logistics_confirmed_status_requires_password(self):
        supervisor = self.create_supervisor(staff_id=1, name="Laura Mendez")
        db.session.add(ExamSessionSupervisorAssignment(
            exam_session_id=self.session_record.id,
            team_member_id=supervisor.id,
            participation_status="Confirmed",
            logistics_enabled=True,
            logistics_type="Simple logistics",
        ))
        provider_type = ProviderType(name="Transport", is_system=False, color_key="provider-type-1")
        db.session.add(provider_type)
        db.session.commit()
        client = self.login_client()
        base_payload = {
            "csrf_token": "token",
            "session_year": "2026",
            "modal_action": "save",
            "logistics_files_url": "https://example.com/logistics",
            "logistics_concept_row_keys": "new-1",
            "logistics_concept_id_new-1": "",
            "logistics_status_new-1": "Confirmed",
            "logistics_currency_new-1": "ARS",
            "logistics_fee_new-1": "",
        }

        response = client.post(
            f"/exam-session-planner/sessions/{self.session_record.id}/members",
            data=base_payload,
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(ExamSessionLogisticsConcept.query.count(), 0)

        response = client.post(
            f"/exam-session-planner/sessions/{self.session_record.id}/members",
            data={**base_payload, "logistics_confirmation_password": "Check"},
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(ExamSessionLogisticsConcept.query.count(), 0)

        response = client.post(
            f"/exam-session-planner/sessions/{self.session_record.id}/members",
            data={
                **base_payload,
                "logistics_confirmation_password": "Check",
                "logistics_provider_type_id_new-1": str(provider_type.id),
            },
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)
        concept = ExamSessionLogisticsConcept.query.one()
        self.assertEqual(concept.status, "Confirmed")

    def test_exam_session_member_logistics_type_persists_complex_state(self):
        supervisor = self.create_supervisor(staff_id=1, name="Laura Mendez")
        client = self.login_client()

        response = client.post(
            f"/exam-session-planner/sessions/{self.session_record.id}/members",
            data={
                "csrf_token": "token",
                "session_year": "2026",
                "modal_action": "save",
                "supervisor_row_keys": "new-1",
                "supervisor_assignment_id_new-1": "",
                "supervisor_team_member_id_new-1": str(supervisor.id),
                "supervisor_participation_status_new-1": "Pending",
                "supervisor_logistics_type_new-1": "Complex logistics",
            },
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)
        assignment = ExamSessionSupervisorAssignment.query.filter_by(
            exam_session_id=self.session_record.id,
            team_member_id=supervisor.id,
        ).one()
        self.assertTrue(assignment.logistics_enabled)
        self.assertEqual(assignment.logistics_type, "Complex logistics")

        response = client.get("/exam-session-planner?session_year=2026")
        html = response.get_data(as_text=True)

        self.assertIn('value="Complex logistics" selected', html)
        self.assertIn("staff-logistics-complex-logistics", html)
        self.assertNotIn("<th>Shipment recipient</th>", html)
        self.assertNotIn('name="shipment_recipient"', html)
        for status in [
            "Pending",
            "Pre-confirmation sent",
            "Pre-confirmed",
            "Official confirmation sent",
            "Confirmed",
        ]:
            self.assertIn(f'<option value="{status}"', html)

    def test_certification_year_settings_render_and_persist_for_examiner_and_supervisor(self):
        client = self.login_client()

        examiner_response = client.get("/annual-certification-programme?certification_year=2026")
        examiner_html = examiner_response.get_data(as_text=True)

        self.assertEqual(examiner_response.status_code, 200)
        self.assertIn("Annual meeting date & time", examiner_html)
        self.assertIn("Remote training period", examiner_html)
        self.assertIn('placeholder="DD/MM/YYYY to DD/MM/YYYY"', examiner_html)
        self.assertIn('pattern="\\d{2}/\\d{2}/\\d{4} to \\d{2}/\\d{2}/\\d{4}"', examiner_html)
        self.assertIn('data-remote-training-period', examiner_html)
        self.assertIn('data-certification-year="2026"', examiner_html)
        self.assertIn('name="annual_meeting_date"', examiner_html)
        self.assertIn('placeholder="DD/MM/YYYY"', examiner_html)
        self.assertIn('data-date-mask', examiner_html)
        self.assertIn('data-date-future-or-today', examiner_html)
        self.assertIn('name="annual_meeting_time"', examiner_html)
        self.assertIn('data-annual-meeting-time', examiner_html)
        self.assertIn('data-time-mask', examiner_html)
        self.assertLess(examiner_html.index("Remote training period"), examiner_html.index("Annual meeting date & time"))
        self.assertIn('placeholder="hh:mm"', examiner_html)
        self.assertIn("/annual-certification-programme/year-settings", examiner_html)

        intern_response = client.get("/intern-stages?certification_year=2026")
        intern_html = intern_response.get_data(as_text=True)
        self.assertEqual(intern_response.status_code, 200)
        self.assertIn("Internship stages", intern_html)
        self.assertNotIn("Remote training period", intern_html)
        self.assertNotIn("Annual meeting date & time", intern_html)
        self.assertNotIn('name="remote_training_period"', intern_html)
        self.assertNotIn('name="annual_meeting_date"', intern_html)

        response = client.post(
            "/annual-certification-programme/year-settings",
            data={
                "csrf_token": "token",
                "certification_year": "2026",
                "annual_meeting_date": "10/08/2026",
                "annual_meeting_time": "14:30",
                "remote_training_period": "11/08/2026 to 20/08/2026",
            },
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)
        examiner_config = CertificationYearConfiguration.query.filter_by(
            module_key="examiner_certification",
            year=2026,
        ).one()
        self.assertEqual(examiner_config.annual_meeting_date, date(2026, 8, 10))
        self.assertEqual(examiner_config.annual_meeting_time, time(14, 30))
        self.assertEqual(examiner_config.remote_training_start_date, date(2026, 8, 11))
        self.assertEqual(examiner_config.remote_training_end_date, date(2026, 8, 20))

        supervisor_response = client.get("/supervisor-certification?certification_year=2026")
        supervisor_html = supervisor_response.get_data(as_text=True)

        self.assertEqual(supervisor_response.status_code, 200)
        self.assertIn("/supervisor-certification/year-settings", supervisor_html)
        self.assertIn('placeholder="DD/MM/YYYY to DD/MM/YYYY"', supervisor_html)

        response = client.post(
            "/supervisor-certification/year-settings",
            data={
                "csrf_token": "token",
                "certification_year": "2026",
                "annual_meeting_date": "12/09/2026",
                "annual_meeting_time": "09:05",
                "remote_training_period": "13/09/2026 to 18/09/2026",
            },
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)
        supervisor_config = CertificationYearConfiguration.query.filter_by(
            module_key="supervisor_certification",
            year=2026,
        ).one()
        self.assertEqual(supervisor_config.annual_meeting_date, date(2026, 9, 12))
        self.assertEqual(supervisor_config.annual_meeting_time, time(9, 5))
        self.assertEqual(supervisor_config.remote_training_start_date, date(2026, 9, 13))
        self.assertEqual(supervisor_config.remote_training_end_date, date(2026, 9, 18))

    def test_certification_sections_default_to_latest_active_year(self):
        client = self.login_client()
        db.session.add_all([
            ExaminerCertificationYear(year=2026, is_archived=False),
            ExaminerCertificationYear(year=2027, is_archived=False),
            SupervisorCertificationYear(year=2026, is_archived=False),
            SupervisorCertificationYear(year=2027, is_archived=False),
            InternStageYear(year=2026, is_archived=False),
            InternStageYear(year=2027, is_archived=False),
        ])
        db.session.commit()

        cases = [
            "/annual-certification-programme",
            "/supervisor-certification",
            "/intern-stages",
        ]
        for url in cases:
            with self.subTest(url=url):
                response = client.get(url)
                html = response.get_data(as_text=True)
                self.assertEqual(response.status_code, 200)
                self.assertRegex(
                    html,
                    r'class="year-tab\s+active"[^>]*certification_year=2027[^>]*>2027</a>',
                )

    def test_intern_stages_email_actions_open_gmail_with_pending_stage_bccs(self):
        client = self.login_client()
        stage_1_member = AcademicStaff(
            status="Active",
            full_name="Stage One Pending",
            roles="Intern",
            email="stage1@example.com",
        )
        stage_2_member = AcademicStaff(
            status="Active",
            full_name="Stage Two Pending",
            roles="Intern",
            email="stage2@example.com",
        )
        stage_3_member = AcademicStaff(
            status="Active",
            full_name="Stage Three Pending",
            roles="Intern",
            email="stage3@example.com",
        )
        completed_member = AcademicStaff(
            status="Active",
            full_name="Completed Intern",
            roles="Intern",
            email="done@example.com",
        )
        no_email_member = AcademicStaff(
            status="Active",
            full_name="No Email Intern",
            roles="Intern",
        )
        db.session.add_all([
            stage_1_member,
            stage_2_member,
            stage_3_member,
            completed_member,
            no_email_member,
        ])
        db.session.flush()
        db.session.add_all([
            InternStageRemoteTrainingSelection(
                member_id=stage_2_member.id,
                year=2026,
                status="Completed",
            ),
            InternStageRemoteTrainingSelection(
                member_id=stage_3_member.id,
                year=2026,
                status="Completed",
            ),
            InternStage3Selection(
                member_id=stage_3_member.id,
                year=2026,
                status="Completed",
            ),
            InternStageRemoteTrainingSelection(
                member_id=completed_member.id,
                year=2026,
                status="Completed",
            ),
            InternStage3Selection(
                member_id=completed_member.id,
                year=2026,
                status="Completed",
            ),
            InternStage2Selection(
                member_id=completed_member.id,
                year=2026,
                status="Completed",
            ),
        ])
        db.session.commit()

        response = client.get("/intern-stages?certification_year=2026")
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("Send email to Stage 1 interns", html)
        self.assertIn("Send email to Stage 2 interns", html)
        self.assertIn("Send email to Stage 3 interns", html)
        self.assertIn("https://mail.google.com/mail/?view=cm&amp;fs=1&amp;bcc=stage1%40example.com", html)
        self.assertIn("https://mail.google.com/mail/?view=cm&amp;fs=1&amp;bcc=stage2%40example.com", html)
        self.assertIn("https://mail.google.com/mail/?view=cm&amp;fs=1&amp;bcc=stage3%40example.com", html)
        self.assertNotIn("done%40example.com", html)
        self.assertNotIn("no-email", html)

    def test_certification_bulk_actions_include_send_email_for_selected_members(self):
        client = self.login_client()
        examiner = AcademicStaff(
            status="Active",
            full_name="Email Examiner",
            roles="Examiner",
            email="examiner@example.com",
        )
        supervisor = AcademicStaff(
            status="Active",
            full_name="Email Supervisor",
            roles="Supervisor",
            email="supervisor@example.com",
        )
        intern = AcademicStaff(
            status="Active",
            full_name="Email Intern",
            roles="Intern",
            email="intern@example.com",
        )
        db.session.add_all([examiner, supervisor, intern])
        db.session.commit()

        cases = [
            ("/annual-certification-programme?certification_year=2026", "examiner@example.com"),
            ("/supervisor-certification?certification_year=2026", "supervisor@example.com"),
            ("/intern-stages?certification_year=2026", "intern@example.com"),
        ]
        for url, email in cases:
            with self.subTest(url=url):
                response = client.get(url)
                html = response.get_data(as_text=True)
                self.assertEqual(response.status_code, 200)
                self.assertIn("Bulk actions", html)
                self.assertIn("Send email", html)
                self.assertIn("data-bulk-email-link", html)
                self.assertIn(f'data-member-email="{email}"', html)

    def test_certification_sections_status_filter_and_history_note_counts(self):
        client = self.login_client()
        history = "01/01/2026 09:00 - admin\nFirst note\n\n02/01/2026 10:00 - admin\nSecond note\n\n03/01/2026 11:00 - admin\nThird note"
        examiner = AcademicStaff(
            status="Active",
            full_name="Active Examiner Notes",
            roles="Examiner",
            email="active-examiner@example.com",
            interview=history,
        )
        supervisor = AcademicStaff(
            status="Active",
            full_name="Active Supervisor Notes",
            roles="Supervisor",
            email="active-supervisor@example.com",
            interview=history,
        )
        intern = AcademicStaff(
            status="Active",
            full_name="Active Intern Notes",
            roles="Intern",
            email="active-intern@example.com",
            interview=history,
        )
        db.session.add_all([examiner, supervisor, intern])
        db.session.commit()

        cases = [
            ("/annual-certification-programme?certification_year=2026", "Active Examiner Notes", ["Pending", "In progress", "Certified"]),
            ("/supervisor-certification?certification_year=2026", "Active Supervisor Notes", ["Pending", "In progress", "Certified"]),
            ("/intern-stages?certification_year=2026", "Active Intern Notes", ["Pending", "In progress", "Completed"]),
        ]
        for base_url, member_name, status_options in cases:
            with self.subTest(base_url=base_url):
                response = client.get(base_url)
                html = response.get_data(as_text=True)
                self.assertEqual(response.status_code, 200)
                self.assertIn('<select name="status">', html)
                self.assertIn('<option value="">All statuses</option>', html)
                for role in ["Examiner", "RSG", "Supervisor", "Intern"]:
                    self.assertIn(f'name="roles" value="{role}"', html)
                for status_option in status_options:
                    self.assertIn(f'<option value="{status_option}"', html)

                pending_response = client.get(f"{base_url}&status=Pending")
                pending_html = pending_response.get_data(as_text=True)
                self.assertEqual(pending_response.status_code, 200)
                self.assertIn(member_name, pending_html)
                self.assertIn("Notes (3)", pending_html)

                in_progress_response = client.get(f"{base_url}&status=In+progress")
                in_progress_html = in_progress_response.get_data(as_text=True)
                self.assertEqual(in_progress_response.status_code, 200)
                self.assertNotIn(member_name, in_progress_html)

        staff_response = client.get("/staff-members")
        staff_html = staff_response.get_data(as_text=True)
        self.assertEqual(staff_response.status_code, 200)
        self.assertIn("Active Examiner Notes", staff_html)
        self.assertIn("Notes (3)", staff_html)

    def test_staff_members_bulk_email_and_history_sort(self):
        client = self.login_client()
        no_notes = AcademicStaff(
            status="Active",
            full_name="Alpha No Notes",
            roles="Examiner",
            email="alpha@example.com",
        )
        one_note = AcademicStaff(
            status="Active",
            full_name="Beta One Note",
            roles="Examiner",
            email="beta@example.com",
            interview="01/01/2026 09:00 - admin\nOnly note",
        )
        three_notes = AcademicStaff(
            status="Active",
            full_name="Gamma Three Notes",
            roles="Examiner",
            email="gamma@example.com",
            interview="01/01/2026 09:00 - admin\nFirst note\n\n02/01/2026 10:00 - admin\nSecond note\n\n03/01/2026 11:00 - admin\nThird note",
        )
        db.session.add_all([no_notes, one_note, three_notes])
        db.session.commit()

        response = client.get("/staff-members?sort=history&dir=desc")
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("data-bulk-email-link", html)
        self.assertIn("Send email", html)
        self.assertIn('data-member-email="alpha@example.com"', html)
        self.assertIn('data-member-email="beta@example.com"', html)
        self.assertIn('data-member-email="gamma@example.com"', html)
        self.assertIn("Notes (3)", html)
        self.assertIn("Notes (1)", html)
        self.assertLess(html.index("Gamma Three Notes"), html.index("Beta One Note"))
        self.assertLess(html.index("Beta One Note"), html.index("Alpha No Notes"))

    def test_examiner_and_supervisor_certification_table_sorting(self):
        client = self.login_client()
        examiner_low = AcademicStaff(
            status="Active",
            full_name="Alpha Examiner",
            roles="Examiner",
            email="alpha-examiner@example.com",
        )
        examiner_high = AcademicStaff(
            status="Active",
            full_name="Beta Examiner",
            roles="Examiner",
            email="beta-examiner@example.com",
            interview="01/01/2026 09:00 - admin\nFirst note\n\n02/01/2026 10:00 - admin\nSecond note",
        )
        supervisor_low = AcademicStaff(
            status="Active",
            full_name="Alpha Supervisor",
            roles="Supervisor",
            email="alpha-supervisor@example.com",
        )
        supervisor_high = AcademicStaff(
            status="Active",
            full_name="Beta Supervisor",
            roles="Supervisor",
            email="beta-supervisor@example.com",
        )
        db.session.add_all([examiner_low, examiner_high, supervisor_low, supervisor_high])
        db.session.flush()
        db.session.add_all([
            ExaminerCertificationRemoteTrainingSelection(
                member_id=examiner_high.id,
                year=2026,
                status="Certified",
            ),
            ExaminerCertificationAnnualMeetingSelection(
                member_id=examiner_high.id,
                year=2026,
                status="Attended",
            ),
            ExaminerCertificationFut1Selection(
                member_id=examiner_high.id,
                year=2026,
                option_name="FUT 1",
                status="completed",
            ),
            ExaminerCertificationFut1Selection(
                member_id=examiner_high.id,
                year=2026,
                option_name="FUT 2",
                status="pending",
            ),
            ExaminerCertificationFut1Selection(
                member_id=examiner_low.id,
                year=2026,
                option_name="FUT 1",
                status="pending",
            ),
            SupervisorCertificationRemoteTrainingSelection(
                member_id=supervisor_high.id,
                year=2026,
                status="Certified",
            ),
            SupervisorCertificationAnnualMeetingSelection(
                member_id=supervisor_high.id,
                year=2026,
                status="Attended",
            ),
            SupervisorCertificationFutSelection(
                member_id=supervisor_high.id,
                year=2026,
                option_name="FUT 1",
                status="completed",
            ),
            SupervisorCertificationFutSelection(
                member_id=supervisor_high.id,
                year=2026,
                option_name="FUT 2",
                status="pending",
            ),
            SupervisorCertificationFutSelection(
                member_id=supervisor_low.id,
                year=2026,
                option_name="FUT 1",
                status="pending",
            ),
        ])
        db.session.commit()

        cases = [
            ("/annual-certification-programme?certification_year=2026&sort=fut&dir=desc", "Beta Examiner", "Alpha Examiner"),
            ("/supervisor-certification?certification_year=2026&sort=fut&dir=desc", "Beta Supervisor", "Alpha Supervisor"),
        ]
        for url, first_name, second_name in cases:
            with self.subTest(url=url):
                response = client.get(url)
                html = response.get_data(as_text=True)
                self.assertEqual(response.status_code, 200)
                for sort_column in ["status", "full_name", "history", "annual_meeting", "remote_training", "fut"]:
                    self.assertIn(f"sort={sort_column}", html)
                self.assertLess(html.index(first_name), html.index(second_name))

    def test_intern_stages_table_sorting(self):
        client = self.login_client()
        intern_low = AcademicStaff(
            status="Active",
            full_name="Alpha Intern",
            roles="Intern",
            email="alpha-intern@example.com",
        )
        intern_high = AcademicStaff(
            status="Active",
            full_name="Beta Intern",
            roles="Intern",
            email="beta-intern@example.com",
            interview="01/01/2026 09:00 - admin\nFirst note\n\n02/01/2026 10:00 - admin\nSecond note",
        )
        db.session.add_all([intern_low, intern_high])
        db.session.flush()
        db.session.add_all([
            InternStageRemoteTrainingSelection(
                member_id=intern_high.id,
                year=2026,
                status="Completed",
            ),
            InternStage3Selection(
                member_id=intern_high.id,
                year=2026,
                status="Completed",
            ),
            InternStage2Selection(
                member_id=intern_high.id,
                year=2026,
                status="Completed",
            ),
            InternStageFutSelection(
                member_id=intern_high.id,
                year=2026,
                option_name="FUT 1",
                status="completed",
            ),
            InternStageFutSelection(
                member_id=intern_high.id,
                year=2026,
                option_name="FUT 2",
                status="pending",
            ),
            InternStageFutSelection(
                member_id=intern_low.id,
                year=2026,
                option_name="FUT 1",
                status="pending",
            ),
        ])
        db.session.commit()

        response = client.get("/intern-stages?certification_year=2026&sort=fut&dir=desc")
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        for sort_column in ["status", "full_name", "history", "stage_1", "stage_2", "fut", "stage_3"]:
            self.assertIn(f"sort={sort_column}", html)
        self.assertLess(html.index("Beta Intern"), html.index("Alpha Intern"))

    def test_certification_year_settings_reject_other_year_and_invalid_range(self):
        client = self.login_client()
        db.session.add(ExaminerCertificationYear(year=2026, is_archived=False))
        db.session.commit()

        response = client.post(
            "/annual-certification-programme/year-settings",
            data={
                "csrf_token": "token",
                "certification_year": "2026",
                "annual_meeting_date": "17/07/2026",
                "annual_meeting_time": "14:30",
                "remote_training_period": "",
            },
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(CertificationYearConfiguration.query.count(), 0)

        response = client.post(
            "/annual-certification-programme/year-settings",
            data={
                "csrf_token": "token",
                "certification_year": "2026",
                "annual_meeting_date": "",
                "annual_meeting_time": "14:30",
                "remote_training_period": "",
            },
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)
        config = CertificationYearConfiguration.query.filter_by(
            module_key="examiner_certification",
            year=2026,
        ).one()
        self.assertIsNone(config.annual_meeting_date)
        self.assertIsNone(config.annual_meeting_time)
        db.session.delete(config)
        db.session.commit()

        response = client.post(
            "/annual-certification-programme/year-settings",
            data={
                "csrf_token": "token",
                "certification_year": "2026",
                "annual_meeting_date": "",
                "annual_meeting_time": "",
                "remote_training_period": "11/08/2027 to 20/08/2027",
            },
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(CertificationYearConfiguration.query.count(), 0)

        response = client.post(
            "/annual-certification-programme/year-settings",
            data={
                "csrf_token": "token",
                "certification_year": "2026",
                "annual_meeting_date": "10/03/2027",
                "annual_meeting_time": "",
                "remote_training_period": "",
            },
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(CertificationYearConfiguration.query.count(), 0)

        response = client.post(
            "/annual-certification-programme/year-settings",
            data={
                "csrf_token": "token",
                "certification_year": "2026",
                "annual_meeting_date": "",
                "annual_meeting_time": "",
                "remote_training_period": "20/08/2026 to 11/08/2026",
            },
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(CertificationYearConfiguration.query.count(), 0)

        response = client.post(
            "/annual-certification-programme/year-settings",
            data={
                "csrf_token": "token",
                "certification_year": "2026",
                "annual_meeting_date": "",
                "annual_meeting_time": "",
                "remote_training_period": "11/08/2026 to 11/08/2026",
            },
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(CertificationYearConfiguration.query.count(), 0)

        response = client.post(
            "/annual-certification-programme/year-settings",
            data={
                "csrf_token": "token",
                "certification_year": "2026",
                "annual_meeting_date": "11/08/2026",
                "annual_meeting_time": "24:00",
                "remote_training_period": "",
            },
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(CertificationYearConfiguration.query.count(), 0)

    def test_certification_year_settings_clean_past_annual_meeting_on_render(self):
        client = self.login_client()
        db.session.add_all([
            ExaminerCertificationYear(year=2026, is_archived=False),
            SupervisorCertificationYear(year=2026, is_archived=False),
            CertificationYearConfiguration(
                module_key="examiner_certification",
                year=2026,
                annual_meeting_date=date(2026, 7, 17),
                annual_meeting_time=time(14, 30),
            ),
            CertificationYearConfiguration(
                module_key="supervisor_certification",
                year=2026,
                annual_meeting_date=date(2026, 7, 17),
                annual_meeting_time=time(9, 5),
            ),
        ])
        db.session.commit()

        examiner_html = client.get("/annual-certification-programme?certification_year=2026").get_data(as_text=True)
        supervisor_html = client.get("/supervisor-certification?certification_year=2026").get_data(as_text=True)

        self.assertNotIn('value="17/07/2026"', examiner_html)
        self.assertNotIn('value="14:30"', examiner_html)
        self.assertNotIn('value="17/07/2026"', supervisor_html)
        self.assertNotIn('value="09:05"', supervisor_html)

    def test_certification_year_settings_clean_past_remote_training_on_render(self):
        client = self.login_client()
        db.session.add_all([
            ExaminerCertificationYear(year=2026, is_archived=False),
            SupervisorCertificationYear(year=2026, is_archived=False),
            CertificationYearConfiguration(
                module_key="examiner_certification",
                year=2026,
                remote_training_start_date=date(2026, 7, 10),
                remote_training_end_date=date(2026, 7, 17),
            ),
            CertificationYearConfiguration(
                module_key="supervisor_certification",
                year=2026,
                remote_training_start_date=date(2026, 8, 10),
                remote_training_end_date=date(2026, 8, 15),
            ),
        ])
        db.session.commit()

        examiner_html = client.get("/annual-certification-programme?certification_year=2026").get_data(as_text=True)
        supervisor_html = client.get("/supervisor-certification?certification_year=2026").get_data(as_text=True)

        self.assertNotIn('value="10/07/2026 to 17/07/2026"', examiner_html)
        self.assertIn('value="10/08/2026 to 15/08/2026"', supervisor_html)

    def test_session_header_non_available_staff_persists_to_assignment_rows(self):
        assigned_supervisor = self.create_supervisor(staff_id=1, name="Laura Mendez")
        unavailable_supervisor = self.create_supervisor(staff_id=4, name="Mateo Silva")
        client = self.login_client()

        response = client.post(
            f"/exam-session-planner/sessions/{self.session_record.id}/members",
            data={
                "csrf_token": "token",
                "session_year": "2026",
                "modal_action": "save",
                "supervisor_row_keys": "new-1",
                "supervisor_assignment_id_new-1": "",
                "supervisor_team_member_id_new-1": str(assigned_supervisor.id),
                "supervisor_non_available_member_ids_new-1": ["", str(unavailable_supervisor.id)],
                "supervisor_participation_status_new-1": "Pending",
                "supervisor_logistics_type_new-1": "Does not apply",
            },
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)
        assignment = ExamSessionSupervisorAssignment.query.filter_by(
            exam_session_id=self.session_record.id,
            team_member_id=assigned_supervisor.id,
        ).one()
        self.assertEqual(assignment.non_available_ids(), [unavailable_supervisor.id])

    def test_exam_session_planner_lists_potential_entries_after_staff_options(self):
        supervisor = self.create_supervisor(staff_id=1, name="Laura Mendez")
        potential_entry = self.create_potential_entry(entry_id=100, name="Ceeriolo")
        self.create_potential_entry(entry_id=101, name="Rejected Person", status="Entry rejected")
        self.create_potential_entry(entry_id=104, name="On Hold Person", status="Entry accepted (on hold)")
        self.create_potential_entry(entry_id=102, name="Mr hi", status="Onboarding finalised")
        self.create_potential_entry(entry_id=103, name="Archived Accepted", status="Archived accepted entry")
        client = self.login_client()

        html = client.get("/exam-session-planner?session_year=2026").get_data(as_text=True)

        self.assertIn(f'data-value="{supervisor.id}"', html)
        self.assertIn('data-value="potential:100"', html)
        self.assertIn("Ceeriolo (potential entry)", html)
        self.assertLess(html.index('data-value="1"'), html.index('data-value="potential:100"'))
        self.assertNotIn("Rejected Person (potential entry)", html)
        self.assertNotIn("On Hold Person (potential entry)", html)
        self.assertNotIn("Mr hi (potential entry)", html)
        self.assertNotIn("Archived Accepted (potential entry)", html)

    def test_exam_session_planner_saves_potential_entry_assignment_with_limited_status(self):
        potential_entry = self.create_potential_entry(entry_id=100, name="Ceeriolo")
        client = self.login_client()

        response = client.post(
            f"/exam-session-planner/sessions/{self.session_record.id}/members",
            data={
                "csrf_token": "token",
                "session_year": "2026",
                "modal_action": "save",
                "supervisor_row_keys": "new-1",
                "supervisor_assignment_id_new-1": "",
                "supervisor_team_member_id_new-1": "potential:100",
                "supervisor_participation_status_new-1": "Pre-confirmed",
                "supervisor_logistics_type_new-1": "Does not apply",
            },
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)
        assignment = ExamSessionSupervisorAssignment.query.filter_by(
            exam_session_id=self.session_record.id,
            potential_entry_id=potential_entry.id,
        ).one()
        self.assertIsNone(assignment.team_member_id)
        self.assertEqual(assignment.participation_status, "Pre-confirmed")

        html = client.get("/exam-session-planner?session_year=2026").get_data(as_text=True)
        row_start = html.index("Ceeriolo (potential entry)")
        row_end = html.index("</article>", row_start)
        potential_row_html = html[row_start:row_end]
        self.assertIn("Pre-confirmation email", potential_row_html)
        self.assertNotIn("Official confirmation email", potential_row_html)
        self.assertNotIn("Final information email", potential_row_html)

    def test_exam_session_planner_rejects_confirmed_status_for_potential_entry_assignment(self):
        self.create_potential_entry(entry_id=100, name="Ceeriolo")
        client = self.login_client()

        response = client.post(
            f"/exam-session-planner/sessions/{self.session_record.id}/members",
            data={
                "csrf_token": "token",
                "session_year": "2026",
                "modal_action": "save",
                "supervisor_row_keys": "new-1",
                "supervisor_assignment_id_new-1": "",
                "supervisor_team_member_id_new-1": "potential:100",
                "supervisor_participation_status_new-1": "Confirmed",
                "supervisor_logistics_type_new-1": "Does not apply",
            },
            follow_redirects=True,
        )
        html = response.get_data(as_text=True)

        self.assertIn("Potential entries can only use Pending, Pre-confirmation sent or Pre-confirmed participation status.", html)
        self.assertEqual(ExamSessionSupervisorAssignment.query.count(), 0)

    def test_potential_entry_assignment_blocks_rejection(self):
        potential_entry = self.create_potential_entry(entry_id=100, name="Ceeriolo")
        db.session.add(ExamSessionExaminerAssignment(
            exam_session_id=self.session_record.id,
            potential_entry_id=potential_entry.id,
            participation_status="Pending",
        ))
        db.session.commit()
        client = self.login_client()

        response = client.post(
            f"/potential-entries/{potential_entry.id}/reject",
            data={"csrf_token": "token"},
            follow_redirects=True,
        )
        html = response.get_data(as_text=True)
        db.session.refresh(potential_entry)

        self.assertIn("Entry cannot be rejected because it is still assigned to exam sessions.", html)
        self.assertEqual(potential_entry.status, "Interview confirmed")
        self.assertFalse(potential_entry.is_rejected)

    def test_potential_entry_assignment_blocks_on_hold_for_active_sessions(self):
        potential_entry = self.create_potential_entry(entry_id=100, name="Ceeriolo")
        db.session.add(ExamSessionExaminerAssignment(
            exam_session_id=self.session_record.id,
            potential_entry_id=potential_entry.id,
            participation_status="Pending",
        ))
        db.session.commit()
        client = self.login_client()
        future_date = (date.today() + timedelta(days=7)).strftime("%d/%m/%Y")

        response = client.post(
            f"/potential-entries/{potential_entry.id}/cv-review/accept-application-on-hold",
            data={
                "csrf_token": "token",
                "interview_outcome_status": "attended",
                "interview_has_car": "Yes",
                "interview_roles": ["Examiner"],
                "entry_acceptance_outcome": "on_hold",
                "reactivation_date": future_date,
            },
            follow_redirects=True,
        )
        html = response.get_data(as_text=True)
        db.session.refresh(potential_entry)

        self.assertIn("Entry cannot be put on hold because it is currently assigned to active exam sessions.", html)
        self.assertEqual(potential_entry.status, "Interview confirmed")

    def test_potential_entry_assignment_allows_on_hold_for_archived_session_year(self):
        potential_entry = self.create_potential_entry(entry_id=100, name="Ceeriolo")
        db.session.add_all([
            ExamSessionYear(year=self.session_record.session_date.year, is_archived=True),
            ExamSessionExaminerAssignment(
                exam_session_id=self.session_record.id,
                potential_entry_id=potential_entry.id,
                participation_status="Pending",
            ),
        ])
        db.session.commit()
        client = self.login_client()
        future_date = (date.today() + timedelta(days=7)).strftime("%d/%m/%Y")

        response = client.post(
            f"/potential-entries/{potential_entry.id}/cv-review/accept-application-on-hold",
            data={
                "csrf_token": "token",
                "interview_outcome_status": "attended",
                "interview_has_car": "Yes",
                "interview_roles": ["Examiner"],
                "entry_acceptance_outcome": "on_hold",
                "reactivation_date": future_date,
            },
            follow_redirects=False,
        )
        db.session.refresh(potential_entry)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(potential_entry.status, "Entry accepted (on hold)")

    def test_potential_entry_assignments_are_promoted_to_staff_member_assignments(self):
        potential_entry = self.create_potential_entry(entry_id=100, name="Ceeriolo")
        member = AcademicStaff(status="Active", full_name="Ceeriolo", roles="Examiner")
        db.session.add_all([
            member,
            ExamSessionExaminerAssignment(
                exam_session_id=self.session_record.id,
                potential_entry_id=potential_entry.id,
                participation_status="Pre-confirmed",
            ),
        ])
        self.session_record.non_available_member_ids = '["potential:100"]'
        db.session.flush()

        promote_potential_entry_exam_session_assignments(potential_entry, member)
        db.session.commit()

        assignment = ExamSessionExaminerAssignment.query.one()
        self.assertEqual(assignment.team_member_id, member.id)
        self.assertIsNone(assignment.potential_entry_id)
        db.session.refresh(self.session_record)
        self.assertEqual(self.session_record.non_available_ids(), [member.id])

    def test_session_header_non_available_staff_persists_on_session_without_assignment_rows(self):
        unavailable_supervisor = self.create_supervisor(staff_id=4, name="Mateo Silva")
        client = self.login_client()

        response = client.post(
            f"/exam-session-planner/sessions/{self.session_record.id}/members",
            data={
                "csrf_token": "token",
                "session_year": "2026",
                "modal_action": "save",
                "session_non_available_member_ids": ["", str(unavailable_supervisor.id)],
            },
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)
        db.session.refresh(self.session_record)
        self.assertEqual(self.session_record.non_available_ids(), [unavailable_supervisor.id])

        html = client.get("/exam-session-planner?session_year=2026").get_data(as_text=True)
        self.assertIn('name="session_non_available_member_ids"', html)
        self.assertIn(f'value="{unavailable_supervisor.id}"', html)
        self.assertIn("checked", html)

    def test_session_header_non_available_staff_can_be_cleared(self):
        unavailable_supervisor = self.create_supervisor(staff_id=4, name="Mateo Silva")
        self.session_record.non_available_member_ids = f"[{unavailable_supervisor.id}]"
        db.session.commit()
        client = self.login_client()

        response = client.post(
            f"/exam-session-planner/sessions/{self.session_record.id}/members",
            data={
                "csrf_token": "token",
                "session_year": "2026",
                "modal_action": "save",
                "session_non_available_member_ids": "",
            },
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)
        db.session.refresh(self.session_record)
        self.assertEqual(self.session_record.non_available_ids(), [])

    def test_session_emergency_contact_requires_active_staff_member(self):
        active_contact = AcademicStaff(id=8, status="Active", full_name="Mara Ruiz", roles="")
        inactive_contact = AcademicStaff(id=9, status="Inactive", full_name="Retired Contact", roles="")
        db.session.add_all([active_contact, inactive_contact])
        db.session.commit()
        client = self.login_client()

        html = client.get("/exam-session-planner?session_year=2026").get_data(as_text=True)
        self.assertIn("Emergency contact required", html)
        self.assertIn('name="emergency_contact_member_id"', html)
        self.assertIn("Mara Ruiz", html)
        self.assertNotIn("Retired Contact", html)

        invalid_response = client.post(
            f"/exam-session-planner/sessions/{self.session_record.id}/members",
            data={
                "csrf_token": "token",
                "session_year": "2026",
                "modal_action": "save",
                "session_non_available_member_ids": "",
                "emergency_contact_required": "1",
                "emergency_contact_member_id": str(inactive_contact.id),
            },
            follow_redirects=False,
        )

        self.assertEqual(invalid_response.status_code, 302)
        db.session.refresh(self.session_record)
        self.assertFalse(self.session_record.emergency_contact_required)
        self.assertIsNone(self.session_record.emergency_contact_member_id)

        valid_response = client.post(
            f"/exam-session-planner/sessions/{self.session_record.id}/members",
            data={
                "csrf_token": "token",
                "session_year": "2026",
                "modal_action": "save",
                "session_non_available_member_ids": "",
                "emergency_contact_required": "1",
                "emergency_contact_member_id": str(active_contact.id),
            },
            follow_redirects=False,
        )

        self.assertEqual(valid_response.status_code, 302)
        db.session.refresh(self.session_record)
        self.assertTrue(self.session_record.emergency_contact_required)
        self.assertEqual(self.session_record.emergency_contact_member_id, active_contact.id)

    def test_session_emergency_contact_is_cleared_when_not_required(self):
        active_contact = AcademicStaff(id=8, status="Active", full_name="Mara Ruiz", roles="")
        db.session.add(active_contact)
        self.session_record.emergency_contact_required = True
        self.session_record.emergency_contact_member_id = active_contact.id
        db.session.commit()
        client = self.login_client()

        response = client.post(
            f"/exam-session-planner/sessions/{self.session_record.id}/members",
            data={
                "csrf_token": "token",
                "session_year": "2026",
                "modal_action": "save",
                "session_non_available_member_ids": "",
            },
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)
        db.session.refresh(self.session_record)
        self.assertFalse(self.session_record.emergency_contact_required)
        self.assertIsNone(self.session_record.emergency_contact_member_id)

    def test_session_emergency_contact_not_required_hides_contact_requirement(self):
        active_contact = AcademicStaff(id=8, status="Active", full_name="Mara Ruiz", roles="")
        db.session.add(active_contact)
        db.session.commit()
        client = self.login_client()

        html = client.get("/exam-session-planner?session_year=2026").get_data(as_text=True)
        self.assertIn("Emergency contact required", html)
        self.assertIn("Emergency contact NOT required", html)

        response = client.post(
            f"/exam-session-planner/sessions/{self.session_record.id}/members",
            data={
                "csrf_token": "token",
                "session_year": "2026",
                "modal_action": "save",
                "session_non_available_member_ids": "",
                "emergency_contact_required": "1",
                "emergency_contact_not_required": "1",
                "emergency_contact_member_id": str(active_contact.id),
            },
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)
        db.session.refresh(self.session_record)
        self.assertFalse(self.session_record.emergency_contact_required)
        self.assertTrue(self.session_record.emergency_contact_not_required)
        self.assertIsNone(self.session_record.emergency_contact_member_id)

    def test_auto_shipment_bundles_group_by_supervisor_number_deadline_and_idempotency(self):
        self.create_supervisor(staff_id=1, name="Laura Mendez")
        first = self.create_planning_ready_session("Axis English", date(2026, 7, 9), supervisor_id=1, packages_ready=False)
        second = self.create_planning_ready_session("Lincoln", date(2026, 7, 12), supervisor_id=1, packages_ready=False)

        reconcile_auto_shipment_bundles([first, second], today=date(2026, 6, 20))
        reconcile_auto_shipment_bundles([first, second], today=date(2026, 6, 20))

        bundles = ExamSessionShipmentBundle.query.order_by(ExamSessionShipmentBundle.id.asc()).all()
        self.assertEqual(len(bundles), 1)
        bundle = bundles[0]
        self.assertTrue(bundle.auto_managed)
        self.assertEqual(bundle.dispatch_due_at, date(2026, 6, 29))
        self.assertRegex(bundle.bundle_number, r"^\d+-26$")
        self.assertEqual(ExamSessionShipmentBundleSession.query.count(), 2)
        self.assertEqual({link.exam_session_id for link in bundle.session_links}, {first.id, second.id})

    def test_auto_shipment_bundles_separate_supervisors_and_skip_missing_supervisor(self):
        self.create_supervisor(staff_id=1, name="Laura Mendez")
        self.create_supervisor(staff_id=4, name="Mateo Silva")
        first = self.create_planning_ready_session("Axis English", date(2026, 7, 9), supervisor_id=1, packages_ready=False)
        second = self.create_planning_ready_session("Lincoln", date(2026, 7, 12), supervisor_id=4, packages_ready=False)
        without_supervisor = ExamSession(
            exam_session_name="No supervisor",
            category="Path School",
            status="Pending",
            session_date=date(2026, 7, 15),
            shifts="Morning",
            modules="Speaking",
            format="Online",
        )
        db.session.add(without_supervisor)
        db.session.commit()

        reconcile_auto_shipment_bundles([first, second, without_supervisor], today=date(2026, 6, 20))

        self.assertEqual(ExamSessionShipmentBundle.query.count(), 2)
        self.assertIsNone(ExamSessionShipmentBundleSession.query.filter_by(exam_session_id=without_supervisor.id).first())

    def test_auto_shipment_bundle_blocked_contract_and_session_display(self):
        self.create_supervisor(staff_id=1, name="Laura Mendez")
        first = self.create_planning_ready_session("Axis English", date(2026, 7, 9), supervisor_id=1, packages_ready=True)
        second = self.create_planning_ready_session("Lincoln", date(2026, 7, 12), supervisor_id=1, packages_ready=False)
        reconcile_auto_shipment_bundles([first, second], today=date(2026, 6, 20))
        bundle = ExamSessionShipmentBundle.query.one()
        links = {link.exam_session_id: link for link in ExamSessionShipmentBundleSession.query.all()}

        readiness = shipment_bundle_readiness_contract(bundle)
        self.assertEqual(readiness["packages_ready_count"], 1)
        self.assertEqual(readiness["sessions_count"], 2)
        first_contract = session_shipment_contract(first, links[first.id])
        second_contract = session_shipment_contract(second, links[second.id])
        self.assertEqual(first_contract["label"], "BLOCKED")
        self.assertIn("Waiting for other sessions", first_contract["secondary_lines"])
        self.assertIn("Blocking bundle - Packages pending", second_contract["secondary_lines"])

    def test_auto_shipment_bundle_overdue_split_is_idempotent_and_keeps_confirmed_unblocked(self):
        self.create_supervisor(staff_id=1, name="Laura Mendez")
        confirmed = self.create_planning_ready_session("Axis English", date(2026, 7, 9), supervisor_id=1, packages_ready=True)
        pending_one = self.create_planning_ready_session("Lincoln", date(2026, 7, 12), supervisor_id=1, packages_ready=False)
        pending_two = self.create_planning_ready_session("North Institute", date(2026, 7, 15), supervisor_id=1, packages_ready=False)

        reconcile_auto_shipment_bundles([confirmed, pending_one, pending_two], today=date(2026, 6, 30))
        reconcile_auto_shipment_bundles([confirmed, pending_one, pending_two], today=date(2026, 6, 30))

        bundles = ExamSessionShipmentBundle.query.order_by(ExamSessionShipmentBundle.id.asc()).all()
        self.assertEqual(len(bundles), 3)
        self.assertEqual(ExamSessionShipmentBundleSession.query.count(), 3)
        confirmed_link = ExamSessionShipmentBundleSession.query.filter_by(exam_session_id=confirmed.id).one()
        confirmed_contract = session_shipment_contract(confirmed, confirmed_link)
        self.assertNotEqual(confirmed_contract["label"], "BLOCKED")
        self.assertEqual(ExamSessionShipmentEvent.query.filter_by(event_type="AUTO_BUNDLE_SPLIT").count(), 1)
        self.assertEqual(len({bundle.bundle_number for bundle in bundles}), 3)

    def test_auto_shipment_bundle_deadline_today_does_not_split(self):
        self.create_supervisor(staff_id=1, name="Laura Mendez")
        first = self.create_planning_ready_session("Deadline today A", date(2026, 7, 9), supervisor_id=1, packages_ready=True)
        second = self.create_planning_ready_session("Deadline today B", date(2026, 7, 12), supervisor_id=1, packages_ready=False)

        reconcile_auto_shipment_bundles([first, second], today=date(2026, 6, 29))

        bundle = ExamSessionShipmentBundle.query.one()
        self.assertEqual(bundle.dispatch_due_at, date(2026, 6, 29))
        self.assertEqual(ExamSessionShipmentBundleSession.query.filter_by(bundle_id=bundle.id).count(), 2)
        self.assertEqual(ExamSessionShipmentEvent.query.filter_by(event_type="AUTO_BUNDLE_SPLIT").count(), 0)

    def test_auto_shipment_bundle_overdue_split_with_no_confirmed_creates_individual_bundles(self):
        self.create_supervisor(staff_id=1, name="Laura Mendez")
        first = self.create_planning_ready_session("Pending split A", date(2026, 7, 9), supervisor_id=1, packages_ready=False)
        second = self.create_planning_ready_session("Pending split B", date(2026, 7, 12), supervisor_id=1, packages_ready=False)
        third = self.create_planning_ready_session("Pending split C", date(2026, 7, 15), supervisor_id=1, packages_ready=False)

        reconcile_auto_shipment_bundles([first, second, third], today=date(2026, 6, 30))
        reconcile_auto_shipment_bundles([first, second, third], today=date(2026, 6, 30))

        bundles = ExamSessionShipmentBundle.query.order_by(ExamSessionShipmentBundle.id.asc()).all()
        self.assertEqual(len(bundles), 3)
        self.assertEqual(ExamSessionShipmentBundleSession.query.count(), 3)
        self.assertEqual(sorted(len(bundle.session_links) for bundle in bundles), [1, 1, 1])
        self.assertEqual(ExamSessionShipmentEvent.query.filter_by(event_type="AUTO_BUNDLE_SPLIT").count(), 1)

    def test_auto_shipment_bundle_uses_first_supervisor_when_multiple_are_assigned(self):
        self.create_supervisor(staff_id=1, name="Laura Mendez")
        self.create_supervisor(staff_id=4, name="Mateo Silva")
        multiple = self.create_planning_ready_session("Multiple supervisors", date(2026, 7, 9), supervisor_id=1, packages_ready=False)
        db.session.add(ExamSessionSupervisorAssignment(
            exam_session_id=multiple.id,
            team_member_id=4,
            participation_status="Confirmed",
        ))
        db.session.commit()

        reconcile_auto_shipment_bundles([multiple], today=date(2026, 6, 20))
        client = self.login_client()
        response = client.get("/pre-session-control-tower?session_year=2026&view=sessions")
        html = response.get_data(as_text=True)

        bundle = ExamSessionShipmentBundle.query.one()
        self.assertEqual(bundle.supervisor_staff_id, 1)
        self.assertEqual(ExamSessionShipmentBundleSession.query.filter_by(exam_session_id=multiple.id).count(), 1)
        self.assertIn("Multiple supervisors", html)
        self.assertIn("Bundle", html)

    def test_auto_shipment_bundles_group_by_first_recipient_and_split_different_first_recipients(self):
        self.create_supervisor(staff_id=1, name="Laura Mendez")
        self.create_supervisor(staff_id=4, name="Mateo Silva")
        first = self.create_planning_ready_session("First recipient A", date(2026, 7, 9), supervisor_id=1, packages_ready=False)
        second = self.create_planning_ready_session("First recipient B", date(2026, 7, 12), supervisor_id=1, packages_ready=False)
        third = self.create_planning_ready_session("Other first recipient", date(2026, 7, 15), supervisor_id=4, packages_ready=False)
        for session_record, extra_supervisor_id in [(first, 4), (second, 4), (third, 1)]:
            db.session.add(ExamSessionSupervisorAssignment(
                exam_session_id=session_record.id,
                team_member_id=extra_supervisor_id,
                participation_status="Confirmed",
            ))
        db.session.commit()

        reconcile_auto_shipment_bundles([first, second, third], today=date(2026, 6, 20))
        reconcile_auto_shipment_bundles([first, second, third], today=date(2026, 6, 20))

        bundles = ExamSessionShipmentBundle.query.order_by(ExamSessionShipmentBundle.supervisor_staff_id.asc()).all()
        self.assertEqual([bundle.supervisor_staff_id for bundle in bundles], [1, 4])
        self.assertEqual(ExamSessionShipmentBundleSession.query.count(), 3)
        self.assertEqual(
            {
                link.exam_session_id
                for link in ExamSessionShipmentBundleSession.query.filter_by(bundle_id=bundles[0].id).all()
            },
            {first.id, second.id},
        )
        self.assertEqual(
            {
                link.exam_session_id
                for link in ExamSessionShipmentBundleSession.query.filter_by(bundle_id=bundles[1].id).all()
            },
            {third.id},
        )

    def test_auto_reconciliation_moves_session_when_first_supervisor_changes_pre_dispatch(self):
        self.create_supervisor(staff_id=1, name="Laura Mendez")
        self.create_supervisor(staff_id=4, name="Mateo Silva")
        session_record = self.create_planning_ready_session("Recipient change", date(2026, 7, 9), supervisor_id=1, packages_ready=False)
        db.session.add(ExamSessionSupervisorAssignment(
            exam_session_id=session_record.id,
            team_member_id=4,
            participation_status="Confirmed",
        ))
        db.session.commit()
        reconcile_auto_shipment_bundles([session_record], today=date(2026, 6, 20))
        original_bundle = ExamSessionShipmentBundle.query.one()
        assignments = (
            ExamSessionSupervisorAssignment.query.filter_by(exam_session_id=session_record.id)
            .order_by(ExamSessionSupervisorAssignment.created_on.asc(), ExamSessionSupervisorAssignment.id.asc())
            .all()
        )
        assignments[0].team_member_id = 4
        assignments[1].team_member_id = 1
        db.session.commit()

        reconcile_auto_shipment_bundles([session_record], today=date(2026, 6, 20))

        link = ExamSessionShipmentBundleSession.query.filter_by(exam_session_id=session_record.id).one()
        self.assertEqual(link.bundle.supervisor_staff_id, 4)
        self.assertNotEqual(link.bundle_id, original_bundle.id)
        self.assertEqual(ExamSessionShipmentBundleSession.query.filter_by(exam_session_id=session_record.id).count(), 1)
        self.assertEqual(ExamSessionShipmentEvent.query.filter_by(bundle_id=original_bundle.id, event_type="SESSION_REMOVED_FROM_AUTO_BUNDLE").count(), 1)

    def test_auto_reconciliation_removes_session_when_shipment_recipient_is_cleared(self):
        self.create_supervisor(staff_id=1, name="Laura Mendez")
        session_record = self.create_planning_ready_session("Shipment cleared", date(2026, 7, 9), supervisor_id=1, packages_ready=False)
        reconcile_auto_shipment_bundles([session_record], today=date(2026, 6, 20))
        self.assertEqual(ExamSessionShipmentBundleSession.query.filter_by(exam_session_id=session_record.id).count(), 1)

        assignment = ExamSessionSupervisorAssignment.query.filter_by(
            exam_session_id=session_record.id,
            team_member_id=1,
        ).one()
        assignment.is_shipment_recipient = False
        db.session.commit()

        reconcile_auto_shipment_bundles([session_record], today=date(2026, 6, 20))

        self.assertEqual(ExamSessionShipmentBundleSession.query.filter_by(exam_session_id=session_record.id).count(), 0)
        self.assertEqual(ExamSessionShipmentBundle.query.count(), 0)
        self.assertEqual(session_shipment_contract(session_record)["status"], "not_bundled")

    def test_auto_reconciliation_does_not_move_when_first_supervisor_changes_on_protected_bundle(self):
        self.create_supervisor(staff_id=1, name="Laura Mendez")
        self.create_supervisor(staff_id=4, name="Mateo Silva")
        for protected_status in ["Dispatched", "Recipient review successful"]:
            session_record = self.create_planning_ready_session(f"Protected {protected_status}", date(2026, 7, 9), supervisor_id=1, packages_ready=False)
            db.session.add(ExamSessionSupervisorAssignment(
                exam_session_id=session_record.id,
                team_member_id=4,
                participation_status="Confirmed",
            ))
            db.session.commit()
            reconcile_auto_shipment_bundles([session_record], today=date(2026, 6, 20))
            bundle = ExamSessionShipmentBundle.query.filter_by(supervisor_staff_id=1).order_by(ExamSessionShipmentBundle.id.desc()).first()
            bundle.status = protected_status
            assignments = (
                ExamSessionSupervisorAssignment.query.filter_by(exam_session_id=session_record.id)
                .order_by(ExamSessionSupervisorAssignment.created_on.asc(), ExamSessionSupervisorAssignment.id.asc())
                .all()
            )
            assignments[0].team_member_id = 4
            assignments[1].team_member_id = 1
            db.session.commit()

            reconcile_auto_shipment_bundles([session_record], today=date(2026, 6, 20))

            link = ExamSessionShipmentBundleSession.query.filter_by(exam_session_id=session_record.id).one()
            self.assertEqual(link.bundle_id, bundle.id)
            self.assertEqual(link.bundle.supervisor_staff_id, 1)

    def test_auto_reconciliation_does_not_modify_post_dispatch_bundle(self):
        self.create_supervisor(staff_id=1, name="Laura Mendez")
        dispatched_session = self.create_planning_ready_session("Dispatched shipment", date(2026, 7, 9), supervisor_id=1, packages_ready=False)
        dispatched_bundle = self.create_shipment_bundle_record(status="Dispatched", dispatch_due_at=date(2026, 6, 29), session_record=dispatched_session)
        dispatched_bundle.auto_managed = True
        dispatched_bundle.bundle_year = 2026
        new_session = self.create_planning_ready_session("New post dispatch session", date(2026, 7, 12), supervisor_id=1, packages_ready=False)
        db.session.commit()

        reconcile_auto_shipment_bundles([dispatched_session, new_session], today=date(2026, 6, 30))

        dispatched_bundle = ExamSessionShipmentBundle.query.get(dispatched_bundle.id)
        self.assertEqual(dispatched_bundle.dispatch_due_at, date(2026, 6, 29))
        self.assertEqual(ExamSessionShipmentBundleSession.query.filter_by(bundle_id=dispatched_bundle.id).count(), 1)
        self.assertEqual(ExamSessionShipmentBundleSession.query.filter_by(exam_session_id=new_session.id).count(), 1)
        self.assertNotEqual(ExamSessionShipmentBundleSession.query.filter_by(exam_session_id=new_session.id).one().bundle_id, dispatched_bundle.id)

    def test_control_tower_defaults_to_bundles_and_bundle_detail_reuses_sessions_table(self):
        self.create_supervisor(staff_id=1, name="Laura Mendez")
        self.create_planning_ready_session("Axis English", date(2026, 7, 9), supervisor_id=1, packages_ready=True)
        self.create_planning_ready_session("Lincoln", date(2026, 7, 12), supervisor_id=1, packages_ready=True)
        client = self.login_client()

        response = client.get("/pre-session-control-tower?session_year=2026")
        html = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn('>Bundles</a>', html)
        self.assertIn('>Sessions</a>', html)
        self.assertIn("<th>Bundle number</th>", html)
        self.assertIn("<th>Exam sessions</th>", html)
        self.assertIn("Open bundle", html)
        self.assertIn("Axis English", html)
        bundle = ExamSessionShipmentBundle.query.one()

        detail = client.get(f"/pre-session-control-tower?session_year=2026&view=bundle&bundle_id={bundle.id}")
        detail_html = detail.get_data(as_text=True)
        self.assertIn(f"Bundle {bundle.bundle_number}", detail_html)
        self.assertIn("Back to Bundles", detail_html)
        self.assertIn("<th>Shipment</th>", detail_html)
        self.assertIn("Axis English", detail_html)
        self.assertIn("Lincoln", detail_html)
        self.assertLess(detail_html.index("Axis English"), detail_html.index("Lincoln"))

    def test_bundle_detail_only_shows_sessions_for_selected_bundle(self):
        self.create_supervisor(staff_id=1, name="Laura Mendez")
        self.create_supervisor(staff_id=4, name="Mateo Silva")
        first = self.create_planning_ready_session("Selected bundle session", date(2026, 7, 9), supervisor_id=1, packages_ready=True)
        other = self.create_planning_ready_session("Other bundle session", date(2026, 7, 10), supervisor_id=4, packages_ready=True)
        reconcile_auto_shipment_bundles([first, other], today=date(2026, 6, 20))
        selected_link = ExamSessionShipmentBundleSession.query.filter_by(exam_session_id=first.id).one()
        client = self.login_client()

        response = client.get(f"/pre-session-control-tower?session_year=2026&view=bundle&bundle_id={selected_link.bundle_id}")
        html = response.get_data(as_text=True)
        table = html[html.index('aria-label="Schedule preparation and approval"'):html.index('<div class="modal"', html.index('aria-label="Schedule preparation and approval"'))]

        self.assertIn("Selected bundle session", table)
        self.assertNotIn("Other bundle session", table)
        self.assertIn('data-modal-scroll-target="packages-', table)
        self.assertIn('data-modal-scroll-target="shipments-', table)
        self.assertIn('data-modal-scroll-target="readiness-', table)

    def test_bundles_view_hides_completed_bundles_but_keeps_active_statuses(self):
        self.create_supervisor()
        active_statuses = [
            "Preparing bundle",
            "Ready to dispatch",
            "Dispatched",
            "Delivered successfully",
            "Recipient review with discrepancy",
        ]
        for index, status in enumerate(active_statuses, start=1):
            session_record = self.create_planning_ready_session(
                f"Active bundle {index}",
                date(2026, 8, index),
                packages_ready=True,
            )
            self.create_shipment_bundle_record(status=status, dispatch_due_at=date(2026, 7, index), session_record=session_record)
        completed_session = self.create_planning_ready_session("Completed bundle session", date(2026, 8, 20), packages_ready=True)
        completed_bundle = self.create_shipment_bundle_record(status="Recipient review successful", dispatch_due_at=date(2026, 7, 20), session_record=completed_session)
        client = self.login_client()

        response = client.get("/pre-session-control-tower?session_year=2026")
        html = response.get_data(as_text=True)
        table = html[html.index('aria-label="Shipment bundles"'):html.index('<div class="modal"', html.index('aria-label="Shipment bundles"'))]

        self.assertEqual(response.status_code, 200)
        for status in active_statuses:
            self.assertIn(status if status != "Delivered successfully" else "Delivered successfully", table)
        self.assertNotIn(f"Bundle {completed_bundle.bundle_number}", table)
        self.assertNotIn("Completed bundle session", table)
        self.assertEqual(ExamSessionShipmentBundle.query.filter_by(status="Recipient review successful").count(), 1)

    def test_bundles_view_empty_state_when_all_bundles_completed(self):
        self.create_supervisor()
        completed_session = self.create_planning_ready_session("Completed only session", date(2026, 8, 20), packages_ready=True)
        self.create_shipment_bundle_record(status="Recipient review successful", dispatch_due_at=date(2026, 7, 20), session_record=completed_session)
        client = self.login_client()

        response = client.get("/pre-session-control-tower?session_year=2026")
        html = response.get_data(as_text=True)

        self.assertIn("No pending shipment bundles.", html)
        self.assertIn("All current shipment bundles are either completed or not yet available.", html)

    def test_completed_bundle_remains_visible_in_sessions_and_detail(self):
        self.create_supervisor()
        completed_session = self.create_planning_ready_session("Completed shipment session", date(2026, 8, 20), packages_ready=False)
        completed_bundle = self.create_shipment_bundle_record(status="Recipient review successful", dispatch_due_at=date(2026, 7, 20), session_record=completed_session)
        client = self.login_client()

        sessions_response = client.get("/pre-session-control-tower?session_year=2026&view=sessions")
        sessions_html = sessions_response.get_data(as_text=True)
        table = sessions_html[sessions_html.index('aria-label="Schedule preparation and approval"'):sessions_html.index('<div class="modal"', sessions_html.index('aria-label="Schedule preparation and approval"'))]

        self.assertIn("Completed shipment session", table)
        self.assertIn(f"Bundle {completed_bundle.bundle_number}", table)
        self.assertIn("Bundle completed", table)
        self.assertIn("Recipient review successful", table)
        self.assertNotIn("BLOCKED", table)
        self.assertNotIn("Blocking bundle", table)
        self.assertNotIn("Waiting for other sessions", table)

        detail = client.get(f"/pre-session-control-tower?session_year=2026&view=bundle&bundle_id={completed_bundle.id}")
        detail_html = detail.get_data(as_text=True)
        self.assertIn(f"Bundle {completed_bundle.bundle_number}", detail_html)
        self.assertIn("This bundle has completed the shipment process.", detail_html)
        self.assertIn("Completed shipment session", detail_html)

    def test_auto_reconciliation_does_not_modify_completed_bundle_and_creates_new_bundle(self):
        self.create_supervisor()
        completed_session = self.create_planning_ready_session("Closed shipment", date(2026, 7, 9), packages_ready=False)
        completed_bundle = self.create_shipment_bundle_record(status="Recipient review successful", dispatch_due_at=date(2026, 6, 29), session_record=completed_session)
        original_deadline = completed_bundle.dispatch_due_at
        new_session = self.create_planning_ready_session("New shipment after close", date(2026, 7, 12), packages_ready=False)

        reconcile_auto_shipment_bundles([completed_session, new_session], today=date(2026, 6, 30))
        reconcile_auto_shipment_bundles([completed_session, new_session], today=date(2026, 6, 30))

        completed_bundle = ExamSessionShipmentBundle.query.get(completed_bundle.id)
        self.assertEqual(completed_bundle.dispatch_due_at, original_deadline)
        self.assertEqual(ExamSessionShipmentBundleSession.query.filter_by(bundle_id=completed_bundle.id).count(), 1)
        self.assertEqual(ExamSessionShipmentBundle.query.count(), 2)
        new_link = ExamSessionShipmentBundleSession.query.filter_by(exam_session_id=new_session.id).one()
        self.assertNotEqual(new_link.bundle_id, completed_bundle.id)

    def test_shipment_ready_to_dispatch_requires_quality_checked_packages_and_checklist(self):
        self.create_supervisor()
        self.assign_confirmed_supervisor()
        client = self.login_client()
        client.post(
            f"/pre-session-control-tower/sessions/{self.session_record.id}/shipments/bundles",
            data={
                "csrf_token": "token",
                "supervisor_staff_id": "1",
                "delivery_address": "Av. Siempre Viva 123",
                "included_session_ids": [str(self.session_record.id)],
            },
            follow_redirects=False,
        )
        bundle = ExamSessionShipmentBundle.query.one()

        response = client.post(
            f"/pre-session-control-tower/shipments/bundles/{bundle.id}/status",
            data={"csrf_token": "token", "current_session_id": str(self.session_record.id), "new_status": "Ready to dispatch"},
            follow_redirects=True,
        )
        self.assertIn(b"All included sessions must have packages quality checked before the bundle can be marked as ready to dispatch.", response.data)
        self.assertEqual(ExamSessionShipmentBundle.query.get(bundle.id).status, "Preparing bundle")

        self.mark_session_packages_quality_checked()
        for item in ExamSessionShipmentChecklistItem.query.filter_by(bundle_id=bundle.id).all():
            item.is_checked = True
        db.session.commit()
        contract = shipment_bundle_readiness_contract(bundle)
        self.assertTrue(contract["ready_to_dispatch"])

        response = client.post(
            f"/pre-session-control-tower/shipments/bundles/{bundle.id}/status",
            data={"csrf_token": "token", "current_session_id": str(self.session_record.id), "new_status": "Ready to dispatch"},
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(ExamSessionShipmentBundle.query.get(bundle.id).status, "Ready to dispatch")

    def test_shipment_transitions_tracking_delivery_and_recipient_review(self):
        self.create_supervisor()
        self.assign_confirmed_supervisor()
        self.mark_session_packages_quality_checked()
        bundle = ExamSessionShipmentBundle(
            supervisor_staff_id=1,
            delivery_address="Av. Siempre Viva 123",
            courier="Correo Argentino",
            status="Ready to dispatch",
        )
        db.session.add(bundle)
        db.session.flush()
        db.session.add(ExamSessionShipmentBundleSession(bundle_id=bundle.id, exam_session_id=self.session_record.id))
        from app.routes import ensure_shipment_checklist_items
        ensure_shipment_checklist_items(bundle)
        db.session.commit()
        client = self.login_client()

        response = client.post(
            f"/pre-session-control-tower/shipments/bundles/{bundle.id}/status",
            data={"csrf_token": "token", "current_session_id": str(self.session_record.id), "new_status": "In transit to post office"},
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(ExamSessionShipmentBundle.query.get(bundle.id).status, "In transit to post office")

        response = client.post(
            f"/pre-session-control-tower/shipments/bundles/{bundle.id}/status",
            data={"csrf_token": "token", "current_session_id": str(self.session_record.id), "new_status": "Dispatched"},
            follow_redirects=True,
        )
        self.assertIn(b"Tracking number is required before marking the shipment as dispatched.", response.data)

        response = client.post(
            f"/pre-session-control-tower/shipments/bundles/{bundle.id}/status",
            data={"csrf_token": "token", "current_session_id": str(self.session_record.id), "new_status": "Dispatched", "tracking_number": "CA123"},
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)
        bundle = ExamSessionShipmentBundle.query.get(bundle.id)
        self.assertEqual(bundle.status, "Dispatched")
        self.assertEqual(bundle.tracking_number, "CA123")
        self.assertIsNotNone(bundle.dispatched_at)

        for new_status in ["Recipient notified", "In transit to recipient", "Delivered successfully"]:
            response = client.post(
                f"/pre-session-control-tower/shipments/bundles/{bundle.id}/status",
                data={"csrf_token": "token", "current_session_id": str(self.session_record.id), "new_status": new_status},
                follow_redirects=False,
            )
            self.assertEqual(response.status_code, 302)
        bundle = ExamSessionShipmentBundle.query.get(bundle.id)
        self.assertEqual(bundle.status, "Delivered successfully")
        self.assertIsNotNone(bundle.delivered_at)

        response = client.post(
            f"/pre-session-control-tower/shipments/bundles/{bundle.id}/status",
            data={"csrf_token": "token", "current_session_id": str(self.session_record.id), "new_status": "Recipient review with discrepancy"},
            follow_redirects=True,
        )
        self.assertIn(b"A note is required when recording a recipient review discrepancy.", response.data)

        response = client.post(
            f"/pre-session-control-tower/shipments/bundles/{bundle.id}/status",
            data={"csrf_token": "token", "current_session_id": str(self.session_record.id), "new_status": "Recipient review with discrepancy", "note": "Missing tape."},
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)
        bundle = ExamSessionShipmentBundle.query.get(bundle.id)
        self.assertEqual(bundle.status, "Recipient review with discrepancy")
        self.assertIsNotNone(bundle.recipient_reviewed_at)

    def test_control_tower_shipments_render_without_my_actions_or_core_changes(self):
        self.create_supervisor()
        self.assign_confirmed_supervisor()
        self.mark_session_packages_quality_checked()
        bundle = ExamSessionShipmentBundle(
            supervisor_staff_id=1,
            delivery_address="Av. Siempre Viva 123",
            courier="Correo Argentino",
            tracking_number="CA123",
            status="Dispatched",
        )
        db.session.add(bundle)
        db.session.flush()
        db.session.add(ExamSessionShipmentBundleSession(bundle_id=bundle.id, exam_session_id=self.session_record.id))
        from app.routes import ensure_shipment_checklist_items
        ensure_shipment_checklist_items(bundle)
        db.session.commit()
        client = self.login_client()

        response = client.get("/pre-session-control-tower?session_year=2026&view=sessions")
        html = response.data.decode()

        self.assertEqual(response.status_code, 200)
        self.assertIn("<th>Shipment</th>", html)
        self.assertLess(html.index("<th>Packages</th>"), html.index("<th>Shipment</th>"))
        self.assertLess(html.index("<th>Shipment</th>"), html.index("<th>Finance</th>"))
        self.assertIn("Tracking: CA123", html)
        self.assertIn("Shipments", html)
        self.assertIn("Shipment history", html)
        self.assertIn("This status only covers schedule approval, staffing and logistics.", html)

        response = client.get("/pre-session-control-tower?session_year=2026&view=my-actions")
        html = response.data.decode()
        table_start = html.index('aria-label="My actions"')
        table_end = html.index('<div class="modal"', table_start)
        actions_table = html[table_start:table_end]
        self.assertIn("Notify recipient", actions_table)
        self.assertIn("Shipments", actions_table)
        self.assertIn("LOGISTICS", actions_table)
        self.assertIn('option value="Shipments"', html)

    def test_shipments_action_contract_states_and_deadlines(self):
        self.assertIsNone(shipments_action_contract(
            self.session_record,
            {"status": "not_bundled"},
            {"ready": False},
        ))
        action = shipments_action_contract(
            self.session_record,
            {"status": "not_bundled"},
            {"ready": True},
        )
        self.assertEqual(action["action_key"], "create_shipment_bundle")
        self.assertEqual(action["responsible"], "LOGISTICS")

        self.create_supervisor()
        self.assign_confirmed_supervisor()
        self.mark_session_packages_quality_checked()
        status_expectations = {
            "Ready to dispatch": "dispatch_shipment_bundle",
            "In transit to post office": "confirm_shipment_dispatch",
            "Dispatched": "notify_shipment_recipient",
            "Recipient notified": "track_shipment_to_recipient",
            "In transit to recipient": "monitor_shipment_delivery",
            "Delayed": "resolve_shipment_delay",
            "Delivered successfully": "complete_recipient_review",
            "Recipient review with discrepancy": "resolve_recipient_review_discrepancy",
        }
        for status, action_key in status_expectations.items():
            bundle = self.create_shipment_bundle_record(status=status, dispatch_due_at=date(2026, 6, 30))
            contract = {
                "status": status,
                "bundle": bundle,
                "bundle_id": bundle.id,
                "readiness": shipment_bundle_readiness_contract(bundle),
            }
            action = shipments_action_contract(self.session_record, contract, {"ready": True})
            self.assertEqual(action["action_key"], action_key)
            if status not in {"Delivered successfully", "Recipient review with discrepancy"}:
                self.assertEqual(action["deadline"], date(2026, 6, 30))
            db.session.delete(bundle)
            db.session.commit()

        bundle = self.create_shipment_bundle_record(status="Recipient review successful")
        contract = {
            "status": "Recipient review successful",
            "bundle": bundle,
            "bundle_id": bundle.id,
            "readiness": shipment_bundle_readiness_contract(bundle),
        }
        self.assertIsNone(shipments_action_contract(self.session_record, contract, {"ready": True}))
        bundle.status = "Mystery"
        db.session.commit()
        contract["status"] = "Mystery"
        action = shipments_action_contract(self.session_record, contract, {"ready": True})
        self.assertEqual(action["action_key"], "review_shipment_data")

    def test_control_tower_my_actions_shipments_not_bundled_requires_packages_ready(self):
        self.create_supervisor()
        self.assign_confirmed_supervisor()
        client = self.login_client()

        response = client.get("/pre-session-control-tower?session_year=2026&view=my-actions")
        html = response.data.decode()
        table_start = html.index('aria-label="My actions"')
        table_end = html.index('<div class="modal"', table_start)
        self.assertNotIn("Create shipment bundle", html[table_start:table_end])

        self.approve_schedule()
        self.confirm_staffing()
        self.mark_session_packages_quality_checked()
        response = client.get("/pre-session-control-tower?session_year=2026&view=my-actions")
        html = response.data.decode()
        table_start = html.index('aria-label="My actions"')
        table_end = html.index('<div class="modal"', table_start)
        actions_table = html[table_start:table_end]

        self.assertIn("Create shipment bundle", actions_table)
        self.assertIn("Shipments", actions_table)
        self.assertIn("LOGISTICS", actions_table)

    def test_control_tower_my_actions_shipments_filters_counts_and_deadlines(self):
        self.create_supervisor()
        self.assign_confirmed_supervisor()
        self.approve_schedule()
        self.confirm_staffing()
        self.mark_session_packages_quality_checked()
        today = datetime.now().date()
        self.create_shipment_bundle_record(status="Ready to dispatch", dispatch_due_at=today)
        client = self.login_client()

        response = client.get("/pre-session-control-tower?session_year=2026&view=my-actions&action_source=Shipments&action_responsible=LOGISTICS&action_status=Due+today")
        html = response.data.decode()
        table_start = html.index('aria-label="My actions"')
        table_end = html.index('<div class="modal"', table_start)
        actions_table = html[table_start:table_end]

        self.assertIn("Dispatch shipment bundle", actions_table)
        self.assertIn("Due today", actions_table)
        self.assertIn('option value="Shipments" selected', html)
        self.assertIn('option value="LOGISTICS" selected', html)
        self.assertIn('option value="Due today" selected', html)
        self.assertIn('<strong>1</strong>', html)

    def test_control_tower_my_actions_shipments_deduplicates_multi_session_bundle(self):
        self.create_supervisor()
        self.assign_confirmed_supervisor()
        other_session = ExamSession(
            exam_session_name="Second bundled session",
            category="Path School",
            status="Pending",
            session_date=date(2026, 6, 26),
            shifts="Morning",
            modules="Speaking",
            format="Online",
        )
        db.session.add(other_session)
        db.session.commit()
        self.assign_confirmed_supervisor(other_session)
        self.mark_session_packages_quality_checked()
        self.mark_session_packages_quality_checked(other_session)
        bundle = self.create_shipment_bundle_record(status="Delayed", dispatch_due_at=None)
        db.session.add(ExamSessionShipmentBundleSession(bundle_id=bundle.id, exam_session_id=other_session.id))
        db.session.commit()
        client = self.login_client()

        response = client.get("/pre-session-control-tower?session_year=2026&view=my-actions&action_source=Shipments")
        html = response.data.decode()
        table_start = html.index('aria-label="My actions"')
        table_end = html.index('<div class="modal"', table_start)
        actions_table = html[table_start:table_end]

        self.assertEqual(actions_table.count("Resolve shipment delay"), 1)
        self.assertIn("Bundle: Dana Montalvo", actions_table)
        self.assertIn("2 sessions", actions_table)
        self.assertIn('data-open-modal="schedule-workflow-', actions_table)

    def test_control_tower_my_actions_shipments_skips_preparing_when_only_packages_missing(self):
        self.create_supervisor()
        self.assign_confirmed_supervisor()
        bundle = self.create_shipment_bundle_record(status="Preparing bundle")
        for item in ExamSessionShipmentChecklistItem.query.filter_by(bundle_id=bundle.id).all():
            item.is_checked = True
        db.session.commit()
        client = self.login_client()

        response = client.get("/pre-session-control-tower?session_year=2026&view=my-actions")
        html = response.data.decode()
        table_start = html.index('aria-label="My actions"')
        table_end = html.index('<div class="modal"', table_start)
        actions_table = html[table_start:table_end]

        self.assertNotIn("Complete shipment bundle preparation", actions_table)
        self.assertNotIn("Shipments", actions_table)

    def test_shipment_planning_needs_review_and_address_needed(self):
        planning = shipment_planning_contract(
            self.session_record,
            all_year_sessions=[self.session_record],
            supervisor_assignments_by_session={},
            shipment_links_by_session={},
            packages_contracts_by_session={self.session_record.id: {"ready": False}},
            today=date(2026, 6, 20),
        )
        self.assertEqual(planning["status"], "needs_review")

        self.create_supervisor()
        self.assign_confirmed_supervisor()
        second_supervisor = AcademicStaff(id=2, status="Active", full_name="Second Supervisor", roles="Supervisor")
        db.session.add(second_supervisor)
        db.session.add(ExamSessionSupervisorAssignment(
            exam_session_id=self.session_record.id,
            team_member_id=2,
            participation_status="Confirmed",
        ))
        db.session.commit()
        planning = shipment_planning_contract(
            self.session_record,
            all_year_sessions=[self.session_record],
            supervisor_assignments_by_session={self.session_record.id: ExamSessionSupervisorAssignment.query.filter_by(exam_session_id=self.session_record.id).all()},
            shipment_links_by_session={},
            packages_contracts_by_session={self.session_record.id: {"ready": False}},
            today=date(2026, 6, 20),
        )
        self.assertEqual(planning["status"], "waiting_for_packages")
        self.assertEqual(planning["supervisor"]["id"], 1)

        ExamSessionSupervisorAssignment.query.filter_by(team_member_id=2).delete()
        AcademicStaff.query.filter_by(id=1).update({"full_address_google_maps": ""})
        db.session.commit()
        planning = shipment_planning_contract(
            self.session_record,
            all_year_sessions=[self.session_record],
            supervisor_assignments_by_session={self.session_record.id: ExamSessionSupervisorAssignment.query.filter_by(exam_session_id=self.session_record.id).all()},
            shipment_links_by_session={},
            packages_contracts_by_session={self.session_record.id: {"ready": False}},
            today=date(2026, 6, 20),
        )
        self.assertEqual(planning["status"], "delivery_address_needed")

    def test_shipment_planning_bundle_recommended_possible_split_and_overdue(self):
        self.create_supervisor()
        self.assign_confirmed_supervisor()
        other_session = ExamSession(
            exam_session_name="Later session",
            category="Path School",
            status="Pending",
            session_date=date(2026, 7, 20),
            shifts="Morning",
            modules="Speaking",
            format="Online",
        )
        db.session.add(other_session)
        db.session.commit()
        self.assign_confirmed_supervisor(other_session)
        assignments = {
            self.session_record.id: ExamSessionSupervisorAssignment.query.filter_by(exam_session_id=self.session_record.id).all(),
            other_session.id: ExamSessionSupervisorAssignment.query.filter_by(exam_session_id=other_session.id).all(),
        }
        sessions = [self.session_record, other_session]

        planning = shipment_planning_contract(
            self.session_record,
            all_year_sessions=sessions,
            supervisor_assignments_by_session=assignments,
            shipment_links_by_session={},
            packages_contracts_by_session={self.session_record.id: {"ready": True}, other_session.id: {"ready": True}},
            today=date(2026, 6, 10),
        )
        self.assertEqual(planning["status"], "bundle_recommended")
        self.assertEqual(planning["dispatch_deadline"], date(2026, 6, 15))

        planning = shipment_planning_contract(
            self.session_record,
            all_year_sessions=sessions,
            supervisor_assignments_by_session=assignments,
            shipment_links_by_session={},
            packages_contracts_by_session={self.session_record.id: {"ready": True}, other_session.id: {"ready": False}},
            today=date(2026, 6, 10),
        )
        self.assertEqual(planning["status"], "bundle_possible")

        planning = shipment_planning_contract(
            self.session_record,
            all_year_sessions=sessions,
            supervisor_assignments_by_session=assignments,
            shipment_links_by_session={},
            packages_contracts_by_session={self.session_record.id: {"ready": True}, other_session.id: {"ready": False}},
            today=date(2026, 6, 14),
        )
        self.assertEqual(planning["status"], "split_required")

        planning = shipment_planning_contract(
            self.session_record,
            all_year_sessions=sessions,
            supervisor_assignments_by_session=assignments,
            shipment_links_by_session={},
            packages_contracts_by_session={self.session_record.id: {"ready": True}, other_session.id: {"ready": False}},
            today=date(2026, 6, 16),
        )
        self.assertEqual(planning["status"], "dispatch_overdue")

    def test_shipment_planning_existing_bundle_overdue_risk_and_completed(self):
        self.create_supervisor()
        self.assign_confirmed_supervisor()
        self.mark_session_packages_quality_checked()
        bundle = self.create_shipment_bundle_record(status="Preparing bundle")
        link = ExamSessionShipmentBundleSession.query.filter_by(bundle_id=bundle.id).one()
        assignments = {self.session_record.id: ExamSessionSupervisorAssignment.query.filter_by(exam_session_id=self.session_record.id).all()}
        packages = {self.session_record.id: {"ready": True}}
        planning = shipment_planning_contract(
            self.session_record,
            all_year_sessions=[self.session_record],
            supervisor_assignments_by_session=assignments,
            shipment_links_by_session={self.session_record.id: link},
            packages_contracts_by_session=packages,
            today=date(2026, 6, 16),
        )
        self.assertEqual(planning["status"], "dispatch_overdue")

        bundle.status = "Dispatched"
        db.session.commit()
        planning = shipment_planning_contract(
            self.session_record,
            all_year_sessions=[self.session_record],
            supervisor_assignments_by_session=assignments,
            shipment_links_by_session={self.session_record.id: link},
            packages_contracts_by_session=packages,
            today=date(2026, 6, 23),
        )
        self.assertEqual(planning["status"], "delivery_at_risk")

        bundle.status = "Recipient review successful"
        db.session.commit()
        planning = shipment_planning_contract(
            self.session_record,
            all_year_sessions=[self.session_record],
            supervisor_assignments_by_session=assignments,
            shipment_links_by_session={self.session_record.id: link},
            packages_contracts_by_session=packages,
            today=date(2026, 6, 30),
        )
        self.assertEqual(planning["status"], "completed")

    def test_control_tower_sessions_view_reconciles_auto_shipment_bundle_idempotently(self):
        self.create_supervisor()
        self.approve_schedule()
        self.confirm_staffing()
        self.mark_session_packages_quality_checked()
        before_bundles = ExamSessionShipmentBundle.query.count()
        client = self.login_client()

        response = client.get("/pre-session-control-tower?session_year=2026&view=sessions")
        html = response.data.decode()

        self.assertEqual(response.status_code, 200)
        self.assertIn("Planning:", html)
        self.assertIn("Shipment planning", html)
        self.assertIn("Dispatch deadline", html)
        self.assertIn("Related sessions", html)
        self.assertNotIn("Create recommended bundle", html)
        self.assertEqual(ExamSessionShipmentBundle.query.count(), before_bundles + 1)
        bundle = ExamSessionShipmentBundle.query.one()
        self.assertTrue(bundle.auto_managed)
        self.assertEqual(ExamSessionShipmentBundleSession.query.filter_by(bundle_id=bundle.id).count(), 1)

        client.get("/pre-session-control-tower?session_year=2026&view=sessions")
        self.assertEqual(ExamSessionShipmentBundle.query.count(), before_bundles + 1)
        self.assertEqual(ExamSessionShipmentBundleSession.query.filter_by(bundle_id=bundle.id).count(), 1)

        response = client.get("/pre-session-control-tower?session_year=2026&view=my-actions")
        html = response.data.decode()
        self.assertNotIn("Create shipment bundle", html)
        self.assertIn("Complete shipment bundle preparation", html)
        self.assertNotIn("Bundle recommended", html[html.index('aria-label="My actions"'):html.index('<div class="modal"', html.index('aria-label="My actions"'))])

    def test_shipment_planning_action_contract_mapping_and_deduplication(self):
        base_planning = {
            "status": "needs_review",
            "dispatch_deadline": None,
            "supervisor": {"id": 1, "name": "Dana Montalvo"},
            "delivery_address": "Av. Siempre Viva 123",
            "earliest_session_date": date(2026, 6, 25),
            "candidate_sessions": [{"id": self.session_record.id, "name": self.session_record.exam_session_name, "date": self.session_record.session_date, "packages_ready": False}],
            "current_bundle": None,
        }
        action = shipment_planning_action_contract(self.session_record, base_planning)
        self.assertEqual(action["action_key"], "review_shipment_planning_data")
        self.assertEqual(action["source_label"], "Shipment planning")
        self.assertEqual(action["responsible"], "LOGISTICS")

        planning = dict(base_planning, status="delivery_address_needed")
        self.assertEqual(shipment_planning_action_contract(self.session_record, planning)["action_key"], "add_shipment_delivery_address")
        planning = dict(base_planning, status="bundle_recommended", dispatch_deadline=date(2026, 6, 15))
        self.assertEqual(shipment_planning_action_contract(self.session_record, planning)["action_key"], "review_bundle_recommendation")
        planning = dict(base_planning, status="bundle_possible", dispatch_deadline=date(2026, 6, 15))
        self.assertEqual(shipment_planning_action_contract(self.session_record, planning)["action_key"], "monitor_possible_bundle")
        planning = dict(base_planning, status="split_required", dispatch_deadline=date(2026, 6, 15))
        self.assertEqual(shipment_planning_action_contract(self.session_record, planning)["action_key"], "review_split_shipment_requirement")
        planning = dict(base_planning, status="mystery", dispatch_deadline=date(2026, 6, 15))
        self.assertEqual(shipment_planning_action_contract(self.session_record, planning)["action_key"], "review_shipment_planning_data")

        package_action = {"action_key": "continue_package_pre_packing"}
        planning = dict(base_planning, status="waiting_for_packages")
        self.assertIsNone(shipment_planning_action_contract(self.session_record, planning, packages_action=package_action))

        shipments_action = {"source": "shipments", "action_key": "dispatch_shipment_bundle", "deadline": date(2026, 6, 15)}
        planning = dict(base_planning, status="dispatch_overdue", dispatch_deadline=date(2026, 6, 15))
        self.assertIsNone(shipment_planning_action_contract(self.session_record, planning, shipments_action=shipments_action))
        shipments_action = {"source": "shipments", "action_key": "resolve_shipment_delay"}
        planning = dict(base_planning, status="delivery_at_risk")
        self.assertIsNone(shipment_planning_action_contract(self.session_record, planning, shipments_action=shipments_action))

    def test_control_tower_my_actions_includes_shipment_planning_filter_and_counts(self):
        self.create_supervisor()
        first_session = ExamSession(
            exam_session_name="First shipment planning session",
            category="Path School",
            status="Pending",
            session_date=date(2026, 8, 20),
            shifts="Morning",
            modules="Speaking",
            format="Online",
        )
        other_session = ExamSession(
            exam_session_name="Later shipment planning session",
            category="Path School",
            status="Pending",
            session_date=date(2026, 9, 3),
            shifts="Morning",
            modules="Speaking",
            format="Online",
        )
        db.session.add_all([first_session, other_session])
        db.session.flush()
        db.session.add_all([
            ExamSessionScheduleWorkflow(exam_session_id=first_session.id, status="Approved"),
            ExamSessionScheduleWorkflow(exam_session_id=other_session.id, status="Approved"),
        ])
        db.session.commit()
        self.assign_confirmed_supervisor(first_session)
        self.assign_confirmed_supervisor(other_session)
        self.mark_session_packages_quality_checked(first_session)
        self.mark_session_packages_quality_checked(other_session)
        client = self.login_client()

        response = client.get("/pre-session-control-tower?session_year=2026&view=my-actions&action_source=Shipment+planning&action_responsible=LOGISTICS&action_status=Upcoming")
        html = response.data.decode()
        table_start = html.index('aria-label="My actions"')
        table_end = html.index('<div class="modal"', table_start)
        actions_table = html[table_start:table_end]

        self.assertIn("Review bundle recommendation", actions_table)
        self.assertIn("Shipment planning", actions_table)
        self.assertIn("LOGISTICS", actions_table)
        self.assertIn("Upcoming", actions_table)
        self.assertIn('option value="Shipment planning" selected', html)
        self.assertIn('option value="LOGISTICS" selected', html)
        self.assertIn('option value="Upcoming" selected', html)
        self.assertEqual(actions_table.count("Review bundle recommendation"), 1)

    def test_control_tower_my_actions_planning_split_and_waiting_dedup(self):
        self.create_supervisor()
        today = datetime.now().date()
        first_session = ExamSession(
            exam_session_name="Ready shipment split session",
            category="Path School",
            status="Pending",
            session_date=today + timedelta(days=10),
            shifts="Morning",
            modules="Speaking",
            format="Online",
        )
        other_session = ExamSession(
            exam_session_name="Unready later shipment session",
            category="Path School",
            status="Pending",
            session_date=today + timedelta(days=22),
            shifts="Morning",
            modules="Speaking",
            format="Online",
        )
        db.session.add_all([first_session, other_session])
        db.session.flush()
        db.session.add_all([
            ExamSessionScheduleWorkflow(exam_session_id=first_session.id, status="Approved"),
            ExamSessionScheduleWorkflow(exam_session_id=other_session.id, status="Approved"),
        ])
        db.session.commit()
        self.assign_confirmed_supervisor(first_session)
        self.assign_confirmed_supervisor(other_session)
        self.mark_session_packages_quality_checked(first_session)
        self.create_package_unit_record(status="Pre-packing", expected=10, actual=10, session_record=other_session)
        client = self.login_client()

        response = client.get("/pre-session-control-tower?session_year=2026&view=my-actions&action_source=Shipment+planning")
        html = response.data.decode()
        table_start = html.index('aria-label="My actions"')
        table_end = html.index('<div class="modal"', table_start)
        actions_table = html[table_start:table_end]

        self.assertIn("Review split shipment requirement", actions_table)
        self.assertEqual(actions_table.count("Review split shipment requirement"), 1)
        self.assertNotIn("Wait for packages before shipment planning", actions_table)

    def test_control_tower_my_actions_planning_overdue_and_risk_dedup(self):
        self.create_supervisor()
        self.approve_schedule()
        self.confirm_staffing()
        self.mark_session_packages_quality_checked()
        bundle = self.create_shipment_bundle_record(status="Delayed", dispatch_due_at=None)
        client = self.login_client()

        response = client.get("/pre-session-control-tower?session_year=2026&view=my-actions&action_source=Shipment+planning")
        html = response.data.decode()
        table_start = html.index('aria-label="My actions"')
        table_end = html.index('<div class="modal"', table_start)
        actions_table = html[table_start:table_end]
        self.assertNotIn("Follow up delivery risk", actions_table)

        bundle.status = "Preparing bundle"
        db.session.commit()
        response = client.get("/pre-session-control-tower?session_year=2026&view=my-actions&action_source=Shipment+planning")
        html = response.data.decode()
        table_start = html.index('aria-label="My actions"')
        table_end = html.index('<div class="modal"', table_start)
        actions_table = html[table_start:table_end]
        self.assertIn("Resolve overdue dispatch", actions_table)

    def test_control_tower_shipment_planning_assisted_recommended_bundle_create(self):
        self.create_supervisor()
        first_session = self.create_planning_ready_session("Ready bundle A", date(2026, 8, 20))
        second_session = self.create_planning_ready_session("Ready bundle B", date(2026, 9, 3))
        client = self.login_client()

        response = client.get("/pre-session-control-tower?session_year=2026&open_schedule_modal=%s" % first_session.id)
        html = response.data.decode()

        self.assertEqual(response.status_code, 200)
        self.assertIn("Suggested assisted action", html)
        self.assertIn("Create recommended bundle", html)
        self.assertIn("Ready bundle A", html)
        self.assertIn("Ready bundle B", html)
        self.assertEqual(ExamSessionShipmentBundle.query.count(), 0)

        response = client.post(
            f"/pre-session-control-tower/sessions/{first_session.id}/shipments/bundles",
            data={
                "csrf_token": "token",
                "view": "sessions",
                "assisted_action_key": "assisted_create_recommended_bundle",
                "supervisor_staff_id": "1",
                "delivery_address": "Av. Siempre Viva 123",
                "delivery_city": "Cordoba",
                "delivery_province": "Cordoba",
                "courier": "Correo Argentino",
                "dispatch_due_at": "2026-08-10",
                "included_session_ids": [str(first_session.id), str(second_session.id)],
                "note": "Confirmed by logistics.",
            },
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)
        bundle = ExamSessionShipmentBundle.query.one()
        self.assertEqual(bundle.status, "Preparing bundle")
        self.assertEqual(bundle.delivery_address, "Av. Siempre Viva 123")
        self.assertEqual({link.exam_session_id for link in bundle.session_links}, {first_session.id, second_session.id})
        self.assertTrue(bundle.checklist_items)
        event = ExamSessionShipmentEvent.query.filter_by(bundle_id=bundle.id, event_type="SHIPMENT_BUNDLE_CREATED").one()
        self.assertIn("Shipment bundle created from planning recommendation.", event.note)

    def test_control_tower_shipment_planning_assisted_revalidates_changed_recommendation(self):
        self.create_supervisor()
        first_session = self.create_planning_ready_session("Ready possible bundle", date(2026, 8, 20))
        waiting_session = self.create_planning_ready_session("Waiting possible bundle", date(2026, 9, 3), packages_ready=False)
        client = self.login_client()

        response = client.post(
            f"/pre-session-control-tower/sessions/{first_session.id}/shipments/bundles",
            data={
                "csrf_token": "token",
                "view": "sessions",
                "assisted_action_key": "assisted_create_recommended_bundle",
                "supervisor_staff_id": "1",
                "delivery_address": "Av. Siempre Viva 123",
                "courier": "Correo Argentino",
                "included_session_ids": [str(first_session.id), str(waiting_session.id)],
            },
            follow_redirects=True,
        )
        html = response.data.decode()

        self.assertEqual(response.status_code, 200)
        self.assertIn("Shipment planning recommendation has changed. Please review the current planning details and try again.", html)
        self.assertIn("Review possible bundle", html)
        self.assertEqual(ExamSessionShipmentBundle.query.count(), 0)

    def test_control_tower_shipment_planning_assisted_possible_and_waiting_ui(self):
        self.create_supervisor()
        first_session = self.create_planning_ready_session("Ready possible session", date(2026, 8, 20))
        waiting_session = self.create_planning_ready_session("Waiting possible session", date(2026, 9, 3), packages_ready=False)
        client = self.login_client()

        response = client.get("/pre-session-control-tower?session_year=2026&open_schedule_modal=%s" % first_session.id)
        html = response.data.decode()
        self.assertIn("Review possible bundle", html)
        self.assertIn("Create bundle with ready sessions", html)
        self.assertIn("Sessions still waiting for packages will need a separate shipment or a later bundle.", html)
        self.assertIn("Waiting possible session", html)

        response = client.get("/pre-session-control-tower?session_year=2026&open_schedule_modal=%s" % waiting_session.id)
        html = response.data.decode()
        waiting_start = html.index('id="schedule-workflow-%s"' % waiting_session.id)
        waiting_end = html.find('<div class="modal"', waiting_start + 1)
        waiting_panel = html[waiting_start:waiting_end if waiting_end != -1 else len(html)]
        self.assertIn("Packages must be quality checked before shipment can be created.", waiting_panel)
        self.assertNotIn("Create bundle with ready sessions", waiting_panel)

    def test_logistics_control_view_does_not_create_record(self):
        client = self.login_client()

        response = client.get("/pre-session-control-tower?session_year=2026&view=sessions")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(ExamSessionLogisticsControl.query.count(), 0)
        html = response.data.decode()
        self.assertIn("Logistics deadline", html)
        self.assertIn("Save logistics details", html)

    def test_logistics_control_create_update_and_invalid_date(self):
        client = self.login_client()

        response = client.post(
            f"/pre-session-control-tower/sessions/{self.session_record.id}/logistics-control",
            data={
                "csrf_token": "token",
                "schedule_status": "Not started",
                "logistics_due_at": "2026-06-30",
                "note": "Book hotel before final communication.",
            },
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("open_schedule_modal", response.headers["Location"])
        self.assertIn("session_year=2026", response.headers["Location"])
        self.assertIn("schedule_status=Not+started", response.headers["Location"])
        control = ExamSessionLogisticsControl.query.filter_by(exam_session_id=self.session_record.id).one()
        self.assertEqual(control.logistics_due_at, date(2026, 6, 30))
        self.assertEqual(control.note, "Book hotel before final communication.")
        self.assertEqual(control.updated_by, "admin")

        response = client.post(
            f"/pre-session-control-tower/sessions/{self.session_record.id}/logistics-control",
            data={
                "csrf_token": "token",
                "logistics_due_at": "2026-07-01",
                "note": "Updated logistics note.",
            },
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(ExamSessionLogisticsControl.query.count(), 1)
        self.assertEqual(control.logistics_due_at, date(2026, 7, 1))
        self.assertEqual(control.note, "Updated logistics note.")

        response = client.post(
            f"/pre-session-control-tower/sessions/{self.session_record.id}/logistics-control",
            data={
                "csrf_token": "token",
                "logistics_due_at": "not-a-date",
                "note": "Should not save.",
            },
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("open_logistics_control=1", response.headers["Location"])
        self.assertEqual(ExamSessionLogisticsControl.query.count(), 1)
        self.assertEqual(control.logistics_due_at, date(2026, 7, 1))
        self.assertEqual(control.note, "Updated logistics note.")

    def test_finance_control_view_does_not_create_record(self):
        client = self.login_client()

        response = client.get("/pre-session-control-tower?session_year=2026&view=sessions")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(ExamSessionFinanceControl.query.count(), 0)
        html = response.data.decode()
        self.assertIn("<th>Finance</th>", html)
        self.assertIn("Edit finance status", html)
        self.assertIn("Save finance status", html)

    def test_finance_control_create_event_and_validation(self):
        client = self.login_client()

        response = client.post(
            f"/pre-session-control-tower/sessions/{self.session_record.id}/finance-control",
            data={
                "csrf_token": "token",
                "schedule_status": "Not started",
                "finance_status": "Finance hold",
                "finance_due_at": "2026-06-24",
                "evidence_url": "https://example.com/evidence",
                "note": "Payment needs director review.",
            },
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn("open_schedule_modal", response.headers["Location"])
        self.assertEqual(ExamSessionFinanceControl.query.count(), 1)
        control = ExamSessionFinanceControl.query.filter_by(exam_session_id=self.session_record.id).one()
        self.assertEqual(control.status, "Finance hold")
        self.assertEqual(control.finance_due_at, date(2026, 6, 24))
        self.assertEqual(control.evidence_url, "https://example.com/evidence")
        self.assertEqual(control.responsible_department, "FINANCE")
        self.assertEqual(control.updated_by, "admin")
        self.assertIsNotNone(control.reviewed_at)
        self.assertIsNotNone(control.hold_at)
        self.assertEqual(ExamSessionFinanceEvent.query.count(), 1)

        response = client.post(
            f"/pre-session-control-tower/sessions/{self.session_record.id}/finance-control",
            data={
                "csrf_token": "token",
                "finance_status": "Cleared",
                "finance_due_at": "2026-06-25",
                "evidence_url": "not-a-url",
                "note": "Should not save.",
            },
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("open_finance_control=1", response.headers["Location"])
        self.assertEqual(control.status, "Finance hold")
        self.assertEqual(ExamSessionFinanceEvent.query.count(), 1)

        response = client.post(
            f"/pre-session-control-tower/sessions/{self.session_record.id}/finance-control",
            data={
                "csrf_token": "token",
                "finance_status": "Cleared",
                "finance_due_at": "2026-06-25",
                "note": "",
            },
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("open_finance_control=1", response.headers["Location"])
        self.assertEqual(control.status, "Finance hold")
        self.assertEqual(ExamSessionFinanceEvent.query.count(), 1)

        response = client.post(
            f"/pre-session-control-tower/sessions/{self.session_record.id}/finance-control",
            data={
                "csrf_token": "token",
                "finance_status": "Cleared",
                "finance_due_at": "2026-06-25",
                "note": "Hold resolved by Finance.",
            },
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(control.status, "Cleared")
        self.assertEqual(control.finance_due_at, date(2026, 6, 25))
        self.assertIsNotNone(control.cleared_at)
        self.assertIsNone(control.hold_at)
        self.assertEqual(ExamSessionFinanceEvent.query.count(), 2)

    def test_control_tower_my_actions_includes_finance(self):
        db.session.add(ExamSessionFinanceControl(
            exam_session_id=self.session_record.id,
            status="Payment follow-up required",
            finance_due_at=date(2026, 6, 20),
            note="Awaiting payment confirmation.",
        ))
        db.session.commit()
        client = self.login_client()

        response = client.get("/pre-session-control-tower?session_year=2026&view=my-actions&action_source=Finance&action_responsible=FINANCE&action_status=Overdue")

        self.assertEqual(response.status_code, 200)
        html = response.data.decode()
        self.assertIn("Follow up finance payment", html)
        self.assertIn("Payment follow-up or financial communication is required.", html)
        self.assertIn("FINANCE", html)

    def test_sinapsis_readiness_contract_statuses_checklist_and_deadlines(self):
        not_reviewed = sinapsis_readiness_contract(self.session_record, None, today=date(2026, 6, 25))
        self.assertEqual(not_reviewed["status"], "not_reviewed")
        self.assertFalse(not_reviewed["ready"])
        self.assertTrue(not_reviewed["requires_action"])
        self.assertEqual(not_reviewed["responsible"], "ADMIN")
        self.assertEqual(not_reviewed["checklist_total"], 9)
        self.assertTrue(not_reviewed["details_url_available"])

        control = ExamSessionSinapsisControl(
            exam_session_id=self.session_record.id,
            status="Needs correction",
            sinapsis_due_at=date(2026, 6, 20),
            note="Candidates missing.",
        )
        db.session.add(control)
        db.session.flush()
        items = [
            ExamSessionSinapsisChecklistItem(
                sinapsis_control_id=control.id,
                item_key=f"item_{index}",
                label=f"Item {index}",
                is_required=True,
                is_checked=index < 3,
                display_order=index,
            )
            for index in range(1, 10)
        ]
        db.session.add_all(items)
        db.session.commit()

        correction = sinapsis_readiness_contract(self.session_record, control, checklist_items=items, today=date(2026, 6, 25))
        self.assertEqual(correction["deadline_label"], "Overdue")
        self.assertEqual(correction["checklist_checked"], 2)
        self.assertFalse(correction["ready"])

        for item in items:
            item.is_checked = True
        control.status = "Ready"
        ready = sinapsis_readiness_contract(self.session_record, control, checklist_items=items, today=date(2026, 6, 25))
        self.assertTrue(ready["ready"])
        self.assertFalse(ready["requires_action"])
        self.assertEqual(ready["deadline_status"], "complete")

    def test_sinapsis_control_view_does_not_create_record(self):
        client = self.login_client()

        response = client.get("/pre-session-control-tower?session_year=2026&view=sessions")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(ExamSessionSinapsisControl.query.count(), 0)
        html = response.data.decode()
        self.assertIn("<th>Sinapsis</th>", html)
        self.assertNotIn("<th>Sinapsis readiness</th>", html)
        self.assertIn("Sinapsis readiness", html)
        self.assertIn("Edit Sinapsis status", html)
        self.assertIn("Save Sinapsis status", html)
        self.assertIn("Open link", html)

    def test_sinapsis_control_create_checklist_validation_and_ready(self):
        client = self.login_client()

        response = client.post(
            f"/pre-session-control-tower/sessions/{self.session_record.id}/sinapsis-control",
            data={
                "csrf_token": "token",
                "schedule_status": "Not started",
                "sinapsis_status": "In progress",
                "sinapsis_due_at": "2026-06-24",
                "evidence_url": "https://example.com/evidence",
                "note": "Initial Sinapsis review.",
            },
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn("open_schedule_modal", response.headers["Location"])
        control = ExamSessionSinapsisControl.query.filter_by(exam_session_id=self.session_record.id).one()
        self.assertEqual(control.status, "In progress")
        self.assertEqual(control.sinapsis_due_at, date(2026, 6, 24))
        self.assertEqual(control.evidence_url, "https://example.com/evidence")
        self.assertEqual(control.responsible_department, "ADMIN")
        self.assertIsNotNone(control.reviewed_at)
        self.assertEqual(ExamSessionSinapsisChecklistItem.query.filter_by(sinapsis_control_id=control.id).count(), 9)
        self.assertEqual(ExamSessionSinapsisEvent.query.count(), 1)

        response = client.post(
            f"/pre-session-control-tower/sessions/{self.session_record.id}/sinapsis-control",
            data={
                "csrf_token": "token",
                "sinapsis_status": "Needs correction",
                "note": "",
            },
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("open_sinapsis_control=1", response.headers["Location"])
        self.assertEqual(control.status, "In progress")

        response = client.post(
            f"/pre-session-control-tower/sessions/{self.session_record.id}/sinapsis-control",
            data={
                "csrf_token": "token",
                "sinapsis_status": "Ready",
                "note": "",
            },
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("open_sinapsis_control=1", response.headers["Location"])
        self.assertEqual(control.status, "In progress")

        for item in ExamSessionSinapsisChecklistItem.query.filter_by(sinapsis_control_id=control.id).all():
            item.is_checked = True
        db.session.commit()
        response = client.post(
            f"/pre-session-control-tower/sessions/{self.session_record.id}/sinapsis-control",
            data={
                "csrf_token": "token",
                "sinapsis_status": "Ready",
                "sinapsis_due_at": "2026-06-20",
                "note": "",
            },
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(control.status, "Ready")
        self.assertIsNotNone(control.ready_at)

        response = client.post(
            f"/pre-session-control-tower/sessions/{self.session_record.id}/sinapsis-control",
            data={
                "csrf_token": "token",
                "sinapsis_status": "Needs correction",
                "note": "",
            },
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("open_sinapsis_control=1", response.headers["Location"])
        self.assertEqual(control.status, "Ready")

    def test_sinapsis_checklist_update_and_counts(self):
        control = ExamSessionSinapsisControl(
            exam_session_id=self.session_record.id,
            status="In progress",
        )
        db.session.add(control)
        db.session.flush()
        item = ExamSessionSinapsisChecklistItem(
            sinapsis_control_id=control.id,
            item_key="session_visible",
            label="Session visible in Sinapsis",
            description="Verify access.",
            is_required=True,
            display_order=1,
        )
        db.session.add(item)
        db.session.commit()
        client = self.login_client()

        response = client.post(
            f"/pre-session-control-tower/sessions/{self.session_record.id}/sinapsis-checklist/{item.id}",
            data={
                "csrf_token": "token",
                "is_checked": "1",
                "checklist_note": "Visible.",
            },
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(item.is_checked)
        self.assertIsNotNone(item.checked_at)
        self.assertEqual(item.checked_by, "admin")
        self.assertEqual(item.note, "Visible.")
        self.assertEqual(ExamSessionSinapsisEvent.query.count(), 1)

        response = client.post(
            f"/pre-session-control-tower/sessions/{self.session_record.id}/sinapsis-checklist/{item.id}",
            data={
                "csrf_token": "token",
                "is_checked": "0",
                "checklist_note": "",
            },
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(item.is_checked)
        self.assertIsNone(item.checked_at)
        self.assertIsNone(item.checked_by)

    def test_control_tower_my_actions_includes_sinapsis(self):
        db.session.add(ExamSessionSinapsisControl(
            exam_session_id=self.session_record.id,
            status="Needs correction",
            sinapsis_due_at=date(2026, 6, 20),
            note="Correct candidates.",
        ))
        db.session.commit()
        client = self.login_client()

        response = client.get("/pre-session-control-tower?session_year=2026&view=my-actions&action_source=Sinapsis&action_responsible=ADMIN&action_status=Overdue")

        self.assertEqual(response.status_code, 200)
        html = response.data.decode()
        self.assertIn("Correct Sinapsis setup", html)
        self.assertIn("Sinapsis setup needs correction before the session.", html)
        self.assertIn("ADMIN", html)

    def test_communications_readiness_contract_statuses_checklist_and_deadlines(self):
        not_started = communications_readiness_contract(None, today=date(2026, 6, 25))
        self.assertEqual(not_started["status"], "not_started")
        self.assertFalse(not_started["ready"])
        self.assertTrue(not_started["requires_action"])
        self.assertEqual(not_started["responsible"], "ADMIN")
        self.assertEqual(not_started["checklist_total"], 8)
        self.assertEqual(not_started["staff_checklist_total"], 4)
        self.assertEqual(not_started["exam_centre_checklist_total"], 4)

        control = ExamSessionCommunicationsControl(
            exam_session_id=self.session_record.id,
            status="Needs follow-up",
            communications_due_at=date(2026, 6, 20),
            note="Waiting for centre confirmation.",
        )
        db.session.add(control)
        db.session.flush()
        items = []
        for index in range(1, 9):
            group_key = "STAFF_COMMUNICATIONS" if index <= 4 else "EXAM_CENTRE_COMMUNICATIONS"
            items.append(ExamSessionCommunicationsChecklistItem(
                communications_control_id=control.id,
                group_key=group_key,
                item_key=f"item_{index}",
                label=f"Item {index}",
                is_required=True,
                is_checked=index in {1, 2, 5},
                display_order=index,
            ))
        db.session.add_all(items)
        db.session.commit()

        follow_up = communications_readiness_contract(control, checklist_items=items, today=date(2026, 6, 25))
        self.assertEqual(follow_up["deadline_label"], "Overdue")
        self.assertEqual(follow_up["checklist_checked"], 3)
        self.assertEqual(follow_up["staff_checklist_checked"], 2)
        self.assertEqual(follow_up["exam_centre_checklist_checked"], 1)
        self.assertFalse(follow_up["ready"])

        for item in items:
            item.is_checked = True
        control.status = "Completed"
        completed = communications_readiness_contract(control, checklist_items=items, today=date(2026, 6, 25))
        self.assertTrue(completed["ready"])
        self.assertFalse(completed["requires_action"])
        self.assertEqual(completed["deadline_status"], "complete")

    def test_communications_control_view_does_not_create_record(self):
        client = self.login_client()

        response = client.get("/pre-session-control-tower?session_year=2026&view=sessions")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(ExamSessionCommunicationsControl.query.count(), 0)
        html = response.data.decode()
        self.assertIn("<th>Communications</th>", html)
        self.assertIn("Edit communications status", html)
        self.assertIn("Save communications status", html)
        self.assertIn("Staff communications", html)
        self.assertIn("Exam centre communications", html)

    def test_communications_control_create_checklist_validation_and_completed(self):
        client = self.login_client()

        response = client.post(
            f"/pre-session-control-tower/sessions/{self.session_record.id}/communications-control",
            data={
                "csrf_token": "token",
                "schedule_status": "Not started",
                "communications_status": "In progress",
                "communications_due_at": "2026-06-24",
                "evidence_url": "https://example.com/comms",
                "note": "Preparing messages.",
            },
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)
        control = ExamSessionCommunicationsControl.query.filter_by(exam_session_id=self.session_record.id).one()
        self.assertEqual(control.status, "In progress")
        self.assertEqual(control.communications_due_at, date(2026, 6, 24))
        self.assertEqual(control.evidence_url, "https://example.com/comms")
        self.assertEqual(control.responsible_department, "ADMIN")
        self.assertIsNotNone(control.started_at)
        self.assertEqual(ExamSessionCommunicationsChecklistItem.query.filter_by(communications_control_id=control.id).count(), 8)
        self.assertEqual(ExamSessionCommunicationsEvent.query.count(), 1)

        response = client.post(
            f"/pre-session-control-tower/sessions/{self.session_record.id}/communications-control",
            data={
                "csrf_token": "token",
                "communications_status": "Needs follow-up",
                "note": "",
            },
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("open_communications_control=1", response.headers["Location"])
        self.assertEqual(control.status, "In progress")

        response = client.post(
            f"/pre-session-control-tower/sessions/{self.session_record.id}/communications-control",
            data={
                "csrf_token": "token",
                "communications_status": "Completed",
                "note": "",
            },
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("open_communications_control=1", response.headers["Location"])
        self.assertEqual(control.status, "In progress")

        for item in ExamSessionCommunicationsChecklistItem.query.filter_by(communications_control_id=control.id).all():
            item.is_checked = True
        db.session.commit()
        response = client.post(
            f"/pre-session-control-tower/sessions/{self.session_record.id}/communications-control",
            data={
                "csrf_token": "token",
                "communications_status": "Completed",
                "communications_due_at": "2026-06-20",
                "note": "",
            },
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(control.status, "Completed")
        self.assertIsNotNone(control.completed_at)

        response = client.post(
            f"/pre-session-control-tower/sessions/{self.session_record.id}/communications-control",
            data={
                "csrf_token": "token",
                "communications_status": "Needs follow-up",
                "note": "",
            },
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("open_communications_control=1", response.headers["Location"])
        self.assertEqual(control.status, "Completed")

    def test_communications_checklist_update_and_counts(self):
        control = ExamSessionCommunicationsControl(
            exam_session_id=self.session_record.id,
            status="In progress",
        )
        db.session.add(control)
        db.session.flush()
        item = ExamSessionCommunicationsChecklistItem(
            communications_control_id=control.id,
            group_key="STAFF_COMMUNICATIONS",
            item_key="final_staff_structure_sent",
            label="Final staff structure communication sent or registered",
            description="Confirm final communication.",
            is_required=True,
            display_order=1,
        )
        db.session.add(item)
        db.session.commit()
        client = self.login_client()

        response = client.post(
            f"/pre-session-control-tower/sessions/{self.session_record.id}/communications-checklist/{item.id}",
            data={
                "csrf_token": "token",
                "is_checked": "1",
                "checklist_note": "Sent.",
            },
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(item.is_checked)
        self.assertIsNotNone(item.checked_at)
        self.assertEqual(item.checked_by, "admin")
        self.assertEqual(item.note, "Sent.")
        self.assertEqual(ExamSessionCommunicationsEvent.query.count(), 1)

        response = client.post(
            f"/pre-session-control-tower/sessions/{self.session_record.id}/communications-checklist/{item.id}",
            data={
                "csrf_token": "token",
                "is_checked": "0",
                "checklist_note": "",
            },
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(item.is_checked)
        self.assertIsNone(item.checked_at)
        self.assertIsNone(item.checked_by)

    def test_control_tower_my_actions_includes_communications(self):
        db.session.add(ExamSessionCommunicationsControl(
            exam_session_id=self.session_record.id,
            status="Needs follow-up",
            communications_due_at=date(2026, 6, 20),
            note="Confirm exam centre message.",
        ))
        db.session.commit()
        client = self.login_client()

        response = client.get("/pre-session-control-tower?session_year=2026&view=my-actions&action_source=Communications&action_responsible=ADMIN&action_status=Overdue")

        self.assertEqual(response.status_code, 200)
        html = response.data.decode()
        self.assertIn("Follow up communications", html)
        self.assertIn("Communications need follow-up before they can be completed.", html)
        self.assertIn("ADMIN", html)

    def test_incident_create_validation_checklist_and_event(self):
        client = self.login_client()

        response = client.post(
            f"/pre-session-control-tower/sessions/{self.session_record.id}/incidents",
            data={
                "csrf_token": "token",
                "incident_type": "Shipment at risk",
                "title": "Courier delay",
                "description": "Tracking is not moving.",
                "severity": "High",
                "responsible_department": "LOGISTICS",
                "due_at": "2026-06-20",
                "evidence_url": "https://example.com/tracking",
                "note": "Needs follow-up.",
            },
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn("open_schedule_modal", response.headers["Location"])
        incident = ExamSessionIncident.query.filter_by(exam_session_id=self.session_record.id).one()
        self.assertEqual(incident.incident_type, "Shipment at risk")
        self.assertEqual(incident.status, "Open")
        self.assertEqual(incident.responsible_department, "LOGISTICS")
        self.assertEqual(ExamSessionIncidentChecklistItem.query.filter_by(incident_id=incident.id).count(), 6)
        self.assertEqual(ExamSessionIncidentEvent.query.filter_by(incident_id=incident.id, event_type="created").count(), 1)
        self.assertEqual(ExamSessionIncidentEvent.query.filter_by(incident_id=incident.id, event_type="review_flag_auto_created").count(), 2)

        response = client.post(
            f"/pre-session-control-tower/sessions/{self.session_record.id}/incidents",
            data={
                "csrf_token": "token",
                "incident_type": "Other",
                "title": "Critical without note",
                "severity": "Critical",
                "responsible_department": "ADMIN",
            },
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(ExamSessionIncident.query.count(), 1)

        response = client.post(
            f"/pre-session-control-tower/sessions/{self.session_record.id}/incidents",
            data={
                "csrf_token": "token",
                "incident_type": "",
                "title": "Missing type",
                "severity": "Medium",
                "responsible_department": "ADMIN",
            },
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(ExamSessionIncident.query.count(), 1)

    def test_incident_state_machine_resolution_and_checklist(self):
        incident = ExamSessionIncident(
            exam_session_id=self.session_record.id,
            incident_type="Other",
            title="Generic incident",
            severity="Medium",
            status="Open",
            responsible_department="ADMIN",
            due_at=date(2026, 6, 20),
        )
        db.session.add(incident)
        db.session.flush()
        item = ExamSessionIncidentChecklistItem(
            incident_id=incident.id,
            item_key="other_1",
            label="Describe the issue clearly.",
            description="Describe the issue clearly.",
            is_required=True,
            display_order=1,
        )
        db.session.add(item)
        db.session.commit()
        client = self.login_client()

        response = client.post(
            f"/pre-session-control-tower/sessions/{self.session_record.id}/incidents/{incident.id}",
            data={
                "csrf_token": "token",
                "incident_status": "Resolved",
                "severity": "Medium",
                "responsible_department": "ADMIN",
                "note": "Resolved.",
            },
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(ExamSessionIncident.query.get(incident.id).status, "Open")

        response = client.post(
            f"/pre-session-control-tower/sessions/{self.session_record.id}/incidents/{incident.id}/checklist/{item.id}",
            data={
                "csrf_token": "token",
                "is_checked": "1",
                "checklist_note": "Done",
            },
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)
        item = ExamSessionIncidentChecklistItem.query.get(item.id)
        self.assertTrue(item.is_checked)
        self.assertIsNotNone(item.checked_at)
        self.assertEqual(item.checked_by, "admin")

        response = client.post(
            f"/pre-session-control-tower/sessions/{self.session_record.id}/incidents/{incident.id}",
            data={
                "csrf_token": "token",
                "incident_status": "Resolved",
                "severity": "Medium",
                "responsible_department": "ADMIN",
                "note": "Resolved after checklist.",
            },
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)
        incident = ExamSessionIncident.query.get(incident.id)
        self.assertEqual(incident.status, "Resolved")
        self.assertIsNotNone(incident.resolved_at)

        response = client.post(
            f"/pre-session-control-tower/sessions/{self.session_record.id}/incidents/{incident.id}",
            data={
                "csrf_token": "token",
                "incident_status": "In progress",
                "severity": "Medium",
                "responsible_department": "ADMIN",
                "note": "",
            },
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(ExamSessionIncident.query.get(incident.id).status, "Resolved")

        response = client.post(
            f"/pre-session-control-tower/sessions/{self.session_record.id}/incidents/{incident.id}",
            data={
                "csrf_token": "token",
                "incident_status": "In progress",
                "severity": "Medium",
                "responsible_department": "ADMIN",
                "note": "Reopened.",
            },
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)
        incident = ExamSessionIncident.query.get(incident.id)
        self.assertEqual(incident.status, "In progress")
        self.assertIsNone(incident.resolved_at)

    def test_incidents_contract_counts_and_needs_review(self):
        self.assertEqual(incidents_readiness_contract(self.session_record, [], today=date(2026, 6, 25))["status"], "none")
        open_incident = ExamSessionIncident(
            exam_session_id=self.session_record.id,
            incident_type="Shipment at risk",
            title="Critical shipment",
            severity="Critical",
            status="Open",
            responsible_department="LOGISTICS",
            due_at=date(2026, 6, 20),
        )
        resolved_incident = ExamSessionIncident(
            exam_session_id=self.session_record.id,
            incident_type="Other",
            title="Closed incident",
            severity="Low",
            status="Resolved",
            responsible_department="ADMIN",
        )
        db.session.add_all([open_incident, resolved_incident])
        db.session.commit()

        contract = incidents_readiness_contract(self.session_record, [open_incident, resolved_incident], today=date(2026, 6, 25))
        self.assertEqual(contract["status"], "critical")
        self.assertEqual(contract["active_count"], 1)
        self.assertEqual(contract["critical_count"], 1)
        self.assertEqual(contract["overdue_count"], 1)
        self.assertEqual(contract["resolved_count"], 1)

        open_incident.status = "Mystery"
        db.session.commit()
        self.assertEqual(incidents_readiness_contract(self.session_record, [open_incident], today=date(2026, 6, 25))["status"], "needs_review")

    def test_incident_impact_assessment_matrix_and_defaults(self):
        expected_areas = {
            "Staff member unavailable": ["Staffing", "Logistics", "Communications", "Sinapsis readiness"],
            "Flight cancelled": ["Logistics", "Staffing", "Communications"],
            "Supervisor changed": ["Staffing", "Packages", "Shipments", "Communications", "Sinapsis readiness"],
            "Package sent to wrong supervisor": ["Packages", "Shipments", "Incidents"],
            "Shipment at risk": ["Shipments", "Communications"],
            "Recipient review discrepancy": ["Shipments", "Packages"],
            "Finance hold escalation": ["Finance", "Communications"],
            "Sinapsis issue": ["Sinapsis readiness"],
            "Venue or date change": ["Schedule", "Packages", "Shipments", "Sinapsis readiness", "Communications"],
            "Schedule change after approval": ["Schedule", "Packages", "Sinapsis readiness", "Communications"],
            "Other": ["Incidents"],
        }
        for incident_type, areas in expected_areas.items():
            incident = ExamSessionIncident(
                exam_session_id=self.session_record.id,
                incident_type=incident_type,
                title=f"{incident_type} incident",
                severity="Medium",
                status="Open",
                responsible_department="ADMIN",
            )
            contract = incident_impact_assessment_contract(incident, impact_reviews=[])
            self.assertEqual([impact["affected_area_label"] for impact in contract["impacts"]], areas)
            self.assertTrue(all(impact["status"] == "Review suggested" for impact in contract["impacts"]))
            self.assertEqual(contract["summary"]["review_suggested"], len(areas))
        unknown_incident = ExamSessionIncident(
            exam_session_id=self.session_record.id,
            incident_type="Unknown type",
            title="Unknown incident",
            severity="Medium",
            status="Open",
            responsible_department="ADMIN",
        )
        self.assertEqual(
            [impact["affected_area_label"] for impact in incident_impact_assessment_contract(unknown_incident, impact_reviews=[])["impacts"]],
            ["Incidents"],
        )

    def test_auto_incident_review_flags_created_only_for_high_priority_non_other_incidents(self):
        for severity in ("Low", "Medium"):
            incident = ExamSessionIncident(
                exam_session_id=self.session_record.id,
                incident_type="Supervisor changed",
                title=f"{severity} supervisor change",
                severity=severity,
                status="Open",
                responsible_department="ADMIN",
            )
            db.session.add(incident)
            db.session.flush()
            summary = ensure_incident_review_flags_for_high_priority_incident(incident, actor="admin")
            self.assertEqual(summary["created"], 0)
            self.assertEqual(summary["skipped_reason"], "severity_not_high_priority")

        other_incident = ExamSessionIncident(
            exam_session_id=self.session_record.id,
            incident_type="Other",
            title="Other high incident",
            severity="High",
            status="Open",
            responsible_department="ADMIN",
        )
        db.session.add(other_incident)
        db.session.flush()
        summary = ensure_incident_review_flags_for_high_priority_incident(other_incident, actor="admin")
        db.session.commit()

        self.assertEqual(summary["created"], 0)
        self.assertEqual(summary["skipped_reason"], "other_incident_type")
        self.assertEqual(ExamSessionIncidentReviewFlag.query.count(), 0)

    def test_auto_incident_review_flags_create_expected_matrix_flags_and_are_idempotent(self):
        incident = ExamSessionIncident(
            exam_session_id=self.session_record.id,
            incident_type="Supervisor changed",
            title="Supervisor changed",
            severity="High",
            status="Open",
            responsible_department="ADMIN",
        )
        db.session.add(incident)
        db.session.flush()

        first_summary = ensure_incident_review_flags_for_high_priority_incident(incident, actor="admin")
        second_summary = ensure_incident_review_flags_for_high_priority_incident(incident, actor="admin")
        db.session.commit()

        expected_impacts = incident_impact_matrix_for_type("Supervisor changed")
        self.assertEqual(first_summary["created"], len(expected_impacts))
        self.assertEqual(second_summary["created"], 0)
        self.assertEqual(second_summary["skipped_existing"], len(expected_impacts))
        self.assertEqual(ExamSessionIncidentReviewFlag.query.filter_by(incident_id=incident.id).count(), len(expected_impacts))
        self.assertEqual(
            {flag.affected_area for flag in ExamSessionIncidentReviewFlag.query.filter_by(incident_id=incident.id).all()},
            {"staffing", "packages", "shipments", "communications", "sinapsis"},
        )
        self.assertEqual(
            ExamSessionIncidentEvent.query.filter_by(incident_id=incident.id, event_type="review_flag_auto_created").count(),
            len(expected_impacts),
        )
        self.assertTrue(all(flag.status == "Needs review" for flag in incident.review_flags))
        self.assertTrue(all("Automatically created" in flag.note for flag in incident.review_flags))

    def test_auto_incident_review_flags_reopen_reviewed_and_dismissed_flags(self):
        incident = ExamSessionIncident(
            exam_session_id=self.session_record.id,
            incident_type="Shipment at risk",
            title="Shipment at risk",
            severity="Critical",
            status="Open",
            responsible_department="LOGISTICS",
        )
        reviewed_flag = ExamSessionIncidentReviewFlag(
            exam_session=self.session_record,
            incident=incident,
            impact_key="shipment_at_risk:shipments",
            affected_area="shipments",
            status="Reviewed",
            reason="Delivery timing may affect the exam session.",
            reviewed_by="admin",
        )
        dismissed_flag = ExamSessionIncidentReviewFlag(
            exam_session=self.session_record,
            incident=incident,
            impact_key="shipment_at_risk:communications",
            affected_area="communications",
            status="Dismissed",
            reason="Affected parties may need updated information if delivery risk increases.",
            dismissed_by="admin",
        )
        db.session.add_all([reviewed_flag, dismissed_flag])
        db.session.flush()

        summary = ensure_incident_review_flags_for_high_priority_incident(incident, actor="admin")
        db.session.commit()

        self.assertEqual(summary["created"], 0)
        self.assertEqual(summary["reopened"], 2)
        self.assertEqual(ExamSessionIncidentReviewFlag.query.filter_by(incident_id=incident.id).count(), 2)
        for flag in (reviewed_flag, dismissed_flag):
            self.assertEqual(flag.status, "Needs review")
            self.assertIsNone(flag.reviewed_by)
            self.assertIsNone(flag.dismissed_by)
            self.assertIn("Automatically reopened", flag.note)
        self.assertEqual(
            ExamSessionIncidentEvent.query.filter_by(incident_id=incident.id, event_type="review_flag_auto_reopened").count(),
            2,
        )

    def test_auto_incident_review_flags_created_on_create_and_update_routes(self):
        client = self.login_client()

        response = client.post(
            f"/pre-session-control-tower/sessions/{self.session_record.id}/incidents",
            data={
                "csrf_token": "token",
                "incident_type": "Staff member unavailable",
                "title": "Examiner unavailable",
                "severity": "Critical",
                "responsible_department": "ADMIN",
                "note": "Critical staffing risk.",
            },
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)
        incident = ExamSessionIncident.query.filter_by(title="Examiner unavailable").one()
        self.assertEqual(
            {flag.affected_area for flag in incident.review_flags},
            {"staffing", "logistics", "communications", "sinapsis"},
        )
        self.assertEqual(ExamSessionIncidentReviewFlag.query.filter_by(incident_id=incident.id).count(), 4)

        medium_incident = ExamSessionIncident(
            exam_session_id=self.session_record.id,
            incident_type="Supervisor changed",
            title="Supervisor changed",
            severity="Medium",
            status="Open",
            responsible_department="ADMIN",
        )
        db.session.add(medium_incident)
        db.session.commit()
        response = client.post(
            f"/pre-session-control-tower/sessions/{self.session_record.id}/incidents/{medium_incident.id}",
            data={
                "csrf_token": "token",
                "incident_status": "Open",
                "severity": "High",
                "responsible_department": "ADMIN",
                "note": "Escalated.",
            },
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(ExamSessionIncidentReviewFlag.query.filter_by(incident_id=medium_incident.id).count(), 5)
        self.assertEqual(
            ExamSessionIncidentEvent.query.filter_by(incident_id=medium_incident.id, event_type="review_flag_auto_created").count(),
            5,
        )

    def test_auto_incident_review_flags_do_not_close_when_severity_drops_and_reopen_on_reopen(self):
        client = self.login_client()
        incident = ExamSessionIncident(
            exam_session_id=self.session_record.id,
            incident_type="Shipment at risk",
            title="Shipment at risk",
            severity="High",
            status="Open",
            responsible_department="LOGISTICS",
        )
        db.session.add(incident)
        db.session.flush()
        ensure_incident_review_flags_for_high_priority_incident(incident, actor="admin")
        db.session.commit()

        response = client.post(
            f"/pre-session-control-tower/sessions/{self.session_record.id}/incidents/{incident.id}",
            data={
                "csrf_token": "token",
                "incident_status": "Open",
                "severity": "Medium",
                "responsible_department": "LOGISTICS",
            },
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            {flag.status for flag in ExamSessionIncidentReviewFlag.query.filter_by(incident_id=incident.id).all()},
            {"Needs review"},
        )

        for flag in incident.review_flags:
            flag.status = "Reviewed"
            flag.reviewed_by = "admin"
        incident.status = "Resolved"
        incident.severity = "Critical"
        db.session.commit()
        response = client.post(
            f"/pre-session-control-tower/sessions/{self.session_record.id}/incidents/{incident.id}",
            data={
                "csrf_token": "token",
                "incident_status": "In progress",
                "severity": "Critical",
                "responsible_department": "LOGISTICS",
                "note": "Risk is active again.",
            },
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            {flag.status for flag in ExamSessionIncidentReviewFlag.query.filter_by(incident_id=incident.id).all()},
            {"Needs review"},
        )
        self.assertEqual(
            ExamSessionIncidentEvent.query.filter_by(incident_id=incident.id, event_type="review_flag_auto_reopened").count(),
            2,
        )

    def test_incident_impact_review_route_validation_and_event(self):
        incident = ExamSessionIncident(
            exam_session_id=self.session_record.id,
            incident_type="Supervisor changed",
            title="Supervisor changed",
            severity="Medium",
            status="Open",
            responsible_department="ADMIN",
        )
        db.session.add(incident)
        db.session.commit()
        client = self.login_client()
        impact_key = "supervisor_changed:staffing"

        response = client.post(
            f"/pre-session-control-tower/sessions/{self.session_record.id}/incidents/{incident.id}/impact-review",
            data={
                "csrf_token": "token",
                "impact_key": impact_key,
                "status": "Reviewed",
                "note": "Staffing checked.",
            },
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("open_schedule_modal", response.headers["Location"])
        review = ExamSessionIncidentImpactReview.query.filter_by(incident_id=incident.id, impact_key=impact_key).one()
        self.assertEqual(review.status, "Reviewed")
        self.assertEqual(review.note, "Staffing checked.")
        self.assertIsNotNone(review.reviewed_at)
        self.assertEqual(review.reviewed_by, "admin")
        self.assertEqual(ExamSessionIncidentEvent.query.filter_by(incident_id=incident.id, event_type="impact_reviewed").count(), 1)

        response = client.post(
            f"/pre-session-control-tower/sessions/{self.session_record.id}/incidents/{incident.id}/impact-review",
            data={
                "csrf_token": "token",
                "impact_key": impact_key,
                "status": "Not applicable",
                "note": "",
            },
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(ExamSessionIncidentImpactReview.query.count(), 1)
        self.assertEqual(ExamSessionIncidentImpactReview.query.get(review.id).status, "Reviewed")

        response = client.post(
            f"/pre-session-control-tower/sessions/{self.session_record.id}/incidents/{incident.id}/impact-review",
            data={
                "csrf_token": "token",
                "impact_key": impact_key,
                "status": "Not applicable",
                "note": "No staffing change needed.",
            },
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(ExamSessionIncidentImpactReview.query.count(), 1)
        review = ExamSessionIncidentImpactReview.query.get(review.id)
        self.assertEqual(review.status, "Not applicable")
        self.assertEqual(review.note, "No staffing change needed.")
        self.assertEqual(ExamSessionIncidentEvent.query.filter_by(incident_id=incident.id, event_type="impact_marked_not_applicable").count(), 1)

        response = client.post(
            f"/pre-session-control-tower/sessions/{self.session_record.id}/incidents/{incident.id}/impact-review",
            data={
                "csrf_token": "token",
                "impact_key": "supervisor_changed:finance",
                "status": "Reviewed",
                "note": "Invalid key.",
            },
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(ExamSessionIncidentImpactReview.query.count(), 1)

    def test_incident_review_flag_lifecycle_and_contract(self):
        unit = self.create_package_unit_record(status="Quality checked")
        incident = ExamSessionIncident(
            exam_session_id=self.session_record.id,
            incident_type="Supervisor changed",
            title="Supervisor changed",
            severity="High",
            status="Open",
            responsible_department="ADMIN",
        )
        db.session.add(incident)
        db.session.commit()
        client = self.login_client()
        impact_key = "supervisor_changed:packages"

        response = client.post(
            f"/pre-session-control-tower/sessions/{self.session_record.id}/incidents/{incident.id}/review-flags",
            data={
                "csrf_token": "token",
                "impact_key": impact_key,
                "affected_area": "packages",
                "note": "Check labels after supervisor handover.",
            },
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(ExamSessionPackageUnit.query.get(unit.id).status, "Quality checked")
        flag = ExamSessionIncidentReviewFlag.query.filter_by(incident_id=incident.id, impact_key=impact_key).one()
        self.assertEqual(flag.status, "Needs review")
        self.assertEqual(flag.affected_area, "packages")
        self.assertEqual(flag.note, "Check labels after supervisor handover.")
        self.assertIn("Package", flag.reason)
        self.assertEqual(ExamSessionIncidentEvent.query.filter_by(incident_id=incident.id, event_type="review_flag_created").count(), 1)

        contract = incident_review_flags_contract(self.session_record, flags=[flag])
        self.assertEqual(contract["active_flags_count"], 1)
        self.assertEqual(review_flags_for_area(contract, "packages")[0]["id"], flag.id)
        impact_contract = incident_impact_assessment_contract(incident, impact_reviews=[], review_flags=[flag])
        package_impact = next(impact for impact in impact_contract["impacts"] if impact["impact_key"] == impact_key)
        self.assertFalse(package_impact["can_flag_for_review"])
        self.assertEqual(package_impact["review_flag"]["status"], "Needs review")

        response = client.post(
            f"/pre-session-control-tower/sessions/{self.session_record.id}/incidents/{incident.id}/review-flags",
            data={
                "csrf_token": "token",
                "impact_key": impact_key,
                "affected_area": "packages",
                "note": "Duplicate.",
            },
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(ExamSessionIncidentReviewFlag.query.count(), 1)

        response = client.post(
            f"/pre-session-control-tower/review-flags/{flag.id}/reviewed",
            data={"csrf_token": "token", "note": "Labels reviewed."},
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)
        flag = ExamSessionIncidentReviewFlag.query.get(flag.id)
        self.assertEqual(flag.status, "Reviewed")
        self.assertEqual(flag.reviewed_by, "admin")
        self.assertEqual(flag.note, "Labels reviewed.")
        self.assertEqual(ExamSessionIncidentEvent.query.filter_by(incident_id=incident.id, event_type="review_flag_reviewed").count(), 1)

        response = client.post(
            f"/pre-session-control-tower/sessions/{self.session_record.id}/incidents/{incident.id}/review-flags",
            data={
                "csrf_token": "token",
                "impact_key": impact_key,
                "affected_area": "packages",
                "note": "Recheck after new material.",
            },
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)
        flag = ExamSessionIncidentReviewFlag.query.get(flag.id)
        self.assertEqual(flag.status, "Needs review")
        self.assertIsNone(flag.reviewed_at)
        self.assertEqual(flag.note, "Recheck after new material.")
        self.assertEqual(ExamSessionIncidentEvent.query.filter_by(incident_id=incident.id, event_type="review_flag_reopened").count(), 1)

        response = client.post(
            f"/pre-session-control-tower/review-flags/{flag.id}/dismiss",
            data={"csrf_token": "token", "note": ""},
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(ExamSessionIncidentReviewFlag.query.get(flag.id).status, "Needs review")

        response = client.post(
            f"/pre-session-control-tower/review-flags/{flag.id}/dismiss",
            data={"csrf_token": "token", "note": "Already covered by package checklist."},
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)
        flag = ExamSessionIncidentReviewFlag.query.get(flag.id)
        self.assertEqual(flag.status, "Dismissed")
        self.assertEqual(flag.dismissed_by, "admin")
        self.assertEqual(flag.note, "Already covered by package checklist.")
        self.assertEqual(ExamSessionIncidentEvent.query.filter_by(incident_id=incident.id, event_type="review_flag_dismissed").count(), 1)

    def test_incident_review_flags_contract_marks_inconsistent_data(self):
        incident = ExamSessionIncident(
            exam_session_id=self.session_record.id,
            incident_type="Supervisor changed",
            title="Invalid review flag",
            severity="Medium",
            status="Open",
            responsible_department="ADMIN",
        )
        flag = ExamSessionIncidentReviewFlag(
            exam_session=self.session_record,
            incident=incident,
            impact_key="supervisor_changed:unknown",
            affected_area="unknown_area",
            status="Unexpected",
            reason="Invalid data.",
        )
        db.session.add(flag)
        db.session.commit()

        contract = incident_review_flags_contract(self.session_record, flags=[flag])

        self.assertEqual(contract["status"], "needs_review")
        self.assertTrue(contract["data_needs_review"])
        self.assertEqual(contract["invalid_flags_count"], 1)
        self.assertFalse(contract["ready"])

    def test_incident_review_flag_validation_and_rendering(self):
        incident = ExamSessionIncident(
            exam_session_id=self.session_record.id,
            incident_type="Supervisor changed",
            title="Supervisor changed",
            severity="Medium",
            status="Open",
            responsible_department="ADMIN",
        )
        db.session.add(incident)
        db.session.commit()
        client = self.login_client()

        response = client.post(
            f"/pre-session-control-tower/sessions/{self.session_record.id}/incidents/{incident.id}/review-flags",
            data={
                "csrf_token": "token",
                "impact_key": "supervisor_changed:packages",
                "affected_area": "finance",
                "note": "Wrong lane.",
            },
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(ExamSessionIncidentReviewFlag.query.count(), 0)

        review = ExamSessionIncidentImpactReview(
            incident_id=incident.id,
            impact_key="supervisor_changed:packages",
            affected_area="packages",
            status="Not applicable",
            note="No packages affected.",
        )
        db.session.add(review)
        db.session.commit()
        response = client.post(
            f"/pre-session-control-tower/sessions/{self.session_record.id}/incidents/{incident.id}/review-flags",
            data={
                "csrf_token": "token",
                "impact_key": "supervisor_changed:packages",
                "affected_area": "packages",
                "note": "Forced post.",
            },
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(ExamSessionIncidentReviewFlag.query.count(), 0)

        review.status = "Reviewed"
        review.note = "Ready for flag."
        db.session.add(review)
        db.session.commit()
        response = client.post(
            f"/pre-session-control-tower/sessions/{self.session_record.id}/incidents/{incident.id}/review-flags",
            data={
                "csrf_token": "token",
                "impact_key": "supervisor_changed:packages",
                "affected_area": "packages",
                "note": "Render in lane.",
            },
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)

        response = client.get("/pre-session-control-tower?session_year=2026&view=sessions")
        html = response.data.decode()
        self.assertEqual(response.status_code, 200)
        self.assertIn("Incident review required", html)
        self.assertIn("Review flag active", html)
        self.assertIn("Flag for review", html)
        self.assertIn("Mark as reviewed", html)
        self.assertIn("Dismiss review flag", html)
        self.assertIn("Supervisor changed", html)

    def test_incident_review_flag_assisted_schedule_reopen(self):
        db.session.add(ExamSessionScheduleWorkflow(
            exam_session_id=self.session_record.id,
            status="Approved",
        ))
        flag = self.create_incident_review_flag_record(affected_area="schedule")
        actions = incident_review_flag_assisted_actions(flag)["actions"]
        self.assertEqual(actions[0]["action_key"], "assisted_reopen_schedule")
        client = self.login_client()

        response = client.post(
            f"/pre-session-control-tower/review-flags/{flag.id}/assisted-action",
            data={
                "csrf_token": "token",
                "action_key": "assisted_reopen_schedule",
                "note": "Schedule may need changes.",
                "due_at": "2026-06-26",
            },
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)
        workflow = ExamSessionScheduleWorkflow.query.filter_by(exam_session_id=self.session_record.id).one()
        self.assertEqual(workflow.status, "In progress")
        self.assertEqual(workflow.next_action_due_at, date(2026, 6, 26))
        self.assertEqual(ExamSessionScheduleEvent.query.filter_by(workflow_id=workflow.id).count(), 1)
        self.assertEqual(ExamSessionIncidentReviewFlag.query.get(flag.id).status, "Needs review")
        self.assertEqual(ExamSessionIncidentEvent.query.filter_by(incident_id=flag.incident_id, event_type="assisted_impact_action_executed").count(), 1)

    def test_incident_review_flag_assisted_schedule_not_approved_opens_only(self):
        db.session.add(ExamSessionScheduleWorkflow(
            exam_session_id=self.session_record.id,
            status="In progress",
        ))
        flag = self.create_incident_review_flag_record(affected_area="schedule")
        actions = incident_review_flag_assisted_actions(flag)["actions"]
        self.assertEqual(actions[0]["action_key"], "assisted_open_schedule")
        self.assertTrue(actions[0]["is_navigation"])
        client = self.login_client()

        response = client.post(
            f"/pre-session-control-tower/review-flags/{flag.id}/assisted-action",
            data={
                "csrf_token": "token",
                "action_key": "assisted_reopen_schedule",
                "note": "Forced invalid reopen.",
                "due_at": "2026-06-26",
            },
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)
        workflow = ExamSessionScheduleWorkflow.query.filter_by(exam_session_id=self.session_record.id).one()
        self.assertEqual(workflow.status, "In progress")
        self.assertEqual(ExamSessionScheduleEvent.query.count(), 0)
        self.assertEqual(ExamSessionIncidentEvent.query.filter_by(incident_id=flag.incident_id, event_type="assisted_impact_action_executed").count(), 0)

    def test_incident_review_flag_assisted_navigation_actions_do_not_modify_derived_lanes(self):
        staffing_flag = self.create_incident_review_flag_record(affected_area="staffing")
        logistics_flag = self.create_incident_review_flag_record(affected_area="logistics")
        shipment_flag = self.create_incident_review_flag_record(affected_area="shipments")
        bundle = self.create_shipment_bundle_record(status="Ready to dispatch")

        self.assertEqual(incident_review_flag_assisted_actions(staffing_flag)["actions"][0]["action_key"], "assisted_open_staffing")
        self.assertEqual(incident_review_flag_assisted_actions(logistics_flag)["actions"][0]["action_key"], "assisted_open_logistics")
        self.assertEqual(incident_review_flag_assisted_actions(shipment_flag)["actions"][0]["action_key"], "assisted_open_shipments")
        client = self.login_client()
        response = client.post(
            f"/pre-session-control-tower/review-flags/{shipment_flag.id}/assisted-action",
            data={"csrf_token": "token", "action_key": "assisted_open_shipments", "note": "Open follow-up."},
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(ExamSessionShipmentBundle.query.get(bundle.id).status, "Ready to dispatch")
        self.assertEqual(ExamSessionIncidentEvent.query.filter_by(incident_id=shipment_flag.incident_id, event_type="assisted_impact_action_executed").count(), 1)

    def test_incident_review_flag_assisted_packages_marks_units_needs_review_with_note(self):
        unit = self.create_package_unit_record(status="Quality checked")
        flag = self.create_incident_review_flag_record(affected_area="packages")
        client = self.login_client()

        response = client.post(
            f"/pre-session-control-tower/review-flags/{flag.id}/assisted-action",
            data={"csrf_token": "token", "action_key": "assisted_mark_packages_needs_review", "note": ""},
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(ExamSessionPackageUnit.query.get(unit.id).status, "Quality checked")

        response = client.post(
            f"/pre-session-control-tower/review-flags/{flag.id}/assisted-action",
            data={"csrf_token": "token", "action_key": "assisted_mark_packages_needs_review", "note": "Package labels need review."},
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(ExamSessionPackageUnit.query.get(unit.id).status, "Needs review")
        self.assertEqual(ExamSessionPackageEvent.query.filter_by(package_unit_id=unit.id, event_type="STATUS_CHANGED").count(), 1)
        self.assertEqual(ExamSessionIncidentReviewFlag.query.get(flag.id).status, "Needs review")
        self.assertEqual(ExamSessionIncidentEvent.query.filter_by(incident_id=flag.incident_id, event_type="assisted_impact_action_executed").count(), 1)

    def test_incident_review_flag_assisted_finance_sinapsis_and_communications(self):
        finance_flag = self.create_incident_review_flag_record(affected_area="finance")
        sinapsis_flag = self.create_incident_review_flag_record(affected_area="sinapsis")
        communications_flag = self.create_incident_review_flag_record(affected_area="communications")
        client = self.login_client()

        response = client.post(
            f"/pre-session-control-tower/review-flags/{finance_flag.id}/assisted-action",
            data={"csrf_token": "token", "action_key": "assisted_finance_payment_follow_up", "note": "Payment requires follow-up."},
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(ExamSessionFinanceControl.query.filter_by(exam_session_id=self.session_record.id).one().status, "Payment follow-up required")
        self.assertEqual(ExamSessionFinanceEvent.query.count(), 1)

        response = client.post(
            f"/pre-session-control-tower/review-flags/{finance_flag.id}/assisted-action",
            data={"csrf_token": "token", "action_key": "assisted_finance_hold", "note": "Finance must hold this session."},
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(ExamSessionFinanceControl.query.filter_by(exam_session_id=self.session_record.id).one().status, "Finance hold")
        self.assertEqual(ExamSessionFinanceEvent.query.count(), 2)

        response = client.post(
            f"/pre-session-control-tower/review-flags/{sinapsis_flag.id}/assisted-action",
            data={"csrf_token": "token", "action_key": "assisted_sinapsis_needs_correction", "note": "Sinapsis data needs correction."},
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(ExamSessionSinapsisControl.query.filter_by(exam_session_id=self.session_record.id).one().status, "Needs correction")
        self.assertEqual(ExamSessionSinapsisEvent.query.count(), 1)

        response = client.post(
            f"/pre-session-control-tower/review-flags/{communications_flag.id}/assisted-action",
            data={"csrf_token": "token", "action_key": "assisted_communications_needs_follow_up", "note": "Communication must be updated."},
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(ExamSessionCommunicationsControl.query.filter_by(exam_session_id=self.session_record.id).one().status, "Needs follow-up")
        self.assertEqual(ExamSessionCommunicationsEvent.query.count(), 1)
        self.assertEqual(
            ExamSessionIncidentEvent.query.filter_by(event_type="assisted_impact_action_executed").count(),
            4,
        )
        self.assertEqual(ExamSessionIncidentReviewFlag.query.get(finance_flag.id).status, "Needs review")
        self.assertEqual(ExamSessionIncidentReviewFlag.query.get(sinapsis_flag.id).status, "Needs review")
        self.assertEqual(ExamSessionIncidentReviewFlag.query.get(communications_flag.id).status, "Needs review")

    def test_incident_review_flag_assisted_action_rejects_invalid_inactive_and_missing_note(self):
        flag = self.create_incident_review_flag_record(affected_area="finance")
        reviewed_flag = self.create_incident_review_flag_record(affected_area="packages", status="Reviewed")
        dismissed_flag = self.create_incident_review_flag_record(affected_area="shipments", status="Dismissed")
        client = self.login_client()

        response = client.post(
            f"/pre-session-control-tower/review-flags/{flag.id}/assisted-action",
            data={"csrf_token": "token", "action_key": "not_real", "note": "Invalid."},
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)
        response = client.post(
            f"/pre-session-control-tower/review-flags/{flag.id}/assisted-action",
            data={"csrf_token": "token", "action_key": "assisted_finance_hold", "note": ""},
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)
        response = client.post(
            f"/pre-session-control-tower/review-flags/{reviewed_flag.id}/assisted-action",
            data={"csrf_token": "token", "action_key": "assisted_mark_packages_needs_review", "note": "Should reject."},
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)
        response = client.post(
            f"/pre-session-control-tower/review-flags/{dismissed_flag.id}/assisted-action",
            data={"csrf_token": "token", "action_key": "assisted_open_shipments", "note": "Should reject."},
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)

        self.assertEqual(ExamSessionFinanceControl.query.count(), 0)
        self.assertEqual(ExamSessionIncidentEvent.query.filter_by(event_type="assisted_impact_action_executed").count(), 0)

    def test_incident_review_flag_blocks_session_ready_visuals_only(self):
        ready_session = self.create_planning_ready_session("Flagged ready session", date(2026, 8, 1))
        self.create_shipment_bundle_record(status="Recipient review successful", session_record=ready_session)
        self.mark_session_external_readiness_ready(ready_session)
        self.create_incident_review_flag_record(
            affected_area="packages",
            incident_status="Resolved",
            session_record=ready_session,
        )
        client = self.login_client()

        response = client.get("/pre-session-control-tower?session_year=2026&view=sessions")
        html = response.data.decode()
        self.assertEqual(response.status_code, 200)
        row_start = html.index("Flagged ready session")
        row_end = html.index("</tr>", row_start)
        row = html[row_start:row_end]
        self.assertIn("In progress", row)
        self.assertIn("5 / 6 requirements ready", row)
        self.assertIn("There is 1 incident review flag requiring attention.", row)

        modal_start = html.index(f'id="schedule-workflow-{ready_session.id}"')
        modal_end = html.index('<section class="staffing-control-section incidents-control-section"', modal_start)
        modal = html[modal_start:modal_end]
        self.assertIn("Session readiness", modal)
        self.assertIn("5 of 6 requirements are ready.", modal)
        self.assertIn("Incident review flags", modal)
        self.assertIn("There is 1 incident review flag requiring attention.", modal)
        self.assertIn("This status covers Operational readiness, Finance, Sinapsis readiness, Communications, Incidents and Incident review flags.", modal)

    def test_incident_review_flag_action_contract_mapping_and_deadlines(self):
        today = date(2026, 6, 25)
        expected_responsibles = {
            "packages": "LOGISTICS",
            "shipments": "LOGISTICS",
            "staffing": "ADMIN",
            "logistics": "ADMIN",
            "schedule": "MANAGEMENT",
            "finance": "FINANCE",
            "sinapsis": "ADMIN",
            "communications": "ADMIN",
        }
        for area, responsible in expected_responsibles.items():
            flag = self.create_incident_review_flag_record(affected_area=area, due_at=date(2026, 7, 1))
            action = incident_review_flag_action_contract(flag, today=today)
            self.assertEqual(action["action_key"], f"incident_review:{flag.id}")
            self.assertEqual(action["source_label"], "Incident review")
            self.assertEqual(action["responsible"], responsible)
            self.assertEqual(action["deadline"], date(2026, 7, 1))
            self.assertEqual(action["deadline_status"], "upcoming")
            self.assertIn("Supervisor changed", action["description"])
            self.assertNotIn("supervisor_changed", action["label"])
            self.assertNotIn(str(flag.id), action["description"])

        sinapsis_flag = self.create_incident_review_flag_record(affected_area="sinapsis")
        self.assertEqual(
            incident_review_flag_action_contract(sinapsis_flag, today=today)["label"],
            "Review Sinapsis readiness due to incident",
        )
        package_flag = self.create_incident_review_flag_record(affected_area="packages")
        self.assertEqual(
            incident_review_flag_action_contract(package_flag, today=today)["label"],
            "Review Packages due to incident",
        )
        no_due_flag = self.create_incident_review_flag_record(affected_area="finance")
        self.assertEqual(incident_review_flag_action_contract(no_due_flag, today=today)["deadline_status"], "not_set")
        overdue_flag = self.create_incident_review_flag_record(affected_area="shipments", due_at=date(2026, 6, 20))
        self.assertEqual(incident_review_flag_action_contract(overdue_flag, today=today)["deadline_status"], "overdue")
        due_today_flag = self.create_incident_review_flag_record(affected_area="staffing", due_at=today)
        self.assertEqual(incident_review_flag_action_contract(due_today_flag, today=today)["deadline_status"], "due_today")

        critical_flag = self.create_incident_review_flag_record(affected_area="communications", severity="Critical")
        self.assertIn("Critical incident.", incident_review_flag_action_contract(critical_flag, today=today)["description"])
        reviewed_flag = self.create_incident_review_flag_record(affected_area="packages", status="Reviewed")
        dismissed_flag = self.create_incident_review_flag_record(affected_area="packages", status="Dismissed")
        self.assertIsNone(incident_review_flag_action_contract(reviewed_flag, today=today))
        self.assertIsNone(incident_review_flag_action_contract(dismissed_flag, today=today))

    def test_control_tower_my_actions_includes_incident_review_flags(self):
        today = date(2026, 6, 25)
        package_flag = self.create_incident_review_flag_record(
            affected_area="packages",
            due_at=date(2026, 6, 20),
            severity="Critical",
        )
        self.create_incident_review_flag_record(affected_area="sinapsis", due_at=date(2026, 7, 1))
        self.create_incident_review_flag_record(affected_area="finance", status="Reviewed", due_at=today)
        self.create_incident_review_flag_record(affected_area="shipments", status="Dismissed", due_at=today)
        before = ExamSessionIncidentReviewFlag.query.count()
        client = self.login_client()

        response = client.get("/pre-session-control-tower?session_year=2026&view=my-actions")
        html = response.data.decode()
        table_start = html.index('aria-label="My actions"')
        table_end = html.index('<div class="modal"', table_start)
        actions_table = html[table_start:table_end]

        self.assertEqual(response.status_code, 200)
        self.assertEqual(ExamSessionIncidentReviewFlag.query.count(), before)
        self.assertIn("Incident review", html)
        self.assertIn("Review Packages due to incident", actions_table)
        self.assertIn("Review Sinapsis readiness due to incident", actions_table)
        self.assertIn("Critical incident.", actions_table)
        self.assertIn("LOGISTICS", actions_table)
        self.assertIn("ADMIN", actions_table)
        self.assertIn("Overdue", actions_table)
        self.assertIn('data-modal-scroll-target="packages-%s"' % self.session_record.id, actions_table)
        self.assertNotIn("Review Finance due to incident", actions_table)
        self.assertNotIn("Review Shipments due to incident", actions_table)
        self.assertLess(actions_table.index("Review Packages due to incident"), actions_table.index("Review Sinapsis readiness due to incident"))

        response = client.get("/pre-session-control-tower?session_year=2026&view=my-actions&action_source=Incident+review")
        html = response.data.decode()
        table_start = html.index('aria-label="My actions"')
        table_end = html.index('<div class="modal"', table_start)
        filtered_table = html[table_start:table_end]
        self.assertIn("Review Packages due to incident", filtered_table)
        self.assertIn("Review Sinapsis readiness due to incident", filtered_table)
        self.assertNotIn("Start schedule preparation", filtered_table)
        self.assertIn('option value="Incident review" selected', html)

        response = client.get("/pre-session-control-tower?session_year=2026&view=my-actions&action_source=Incident+review&action_responsible=LOGISTICS&action_status=Overdue")
        html = response.data.decode()
        table_start = html.index('aria-label="My actions"')
        table_end = html.index('<div class="modal"', table_start)
        filtered_table = html[table_start:table_end]
        self.assertIn("Review Packages due to incident", filtered_table)
        self.assertNotIn("Review Sinapsis readiness due to incident", filtered_table)
        self.assertIn('option value="LOGISTICS" selected', html)
        self.assertIn('option value="Overdue" selected', html)
        self.assertIn(f'data-open-modal="schedule-workflow-{package_flag.exam_session_id}"', filtered_table)

    def test_incident_review_flags_in_my_actions_edge_cases(self):
        resolved_flag = self.create_incident_review_flag_record(
            affected_area="staffing",
            incident_status="Resolved",
            due_at=date(2026, 6, 25),
            title="Resolved but pending review",
        )
        no_due_flag = self.create_incident_review_flag_record(affected_area="logistics")
        other_session = ExamSession(
            exam_session_name="Second review session",
            category="Path School",
            status="Pending",
            session_date=date(2026, 7, 5),
            shifts="Morning",
            modules="Speaking",
            format="Online",
        )
        db.session.add(other_session)
        db.session.commit()
        self.create_incident_review_flag_record(affected_area="schedule", session_record=other_session)
        empty_review_flags = incident_review_flags_contract(self.session_record, flags=[])
        readiness_before = session_readiness_contract(
            {"ready": True, "status": "ready"},
            {"raw_status": "Cleared", "label": "Cleared"},
            {"raw_status": "Ready", "label": "Ready"},
            {"raw_status": "Completed", "label": "Completed"},
            {"status": "none", "label": "No active incidents", "active_count": 0, "critical_count": 0, "high_count": 0, "message": "No active incidents.", "blockers": []},
            empty_review_flags,
        )
        client = self.login_client()

        response = client.get("/pre-session-control-tower?session_year=2026&view=my-actions&action_source=Incident+review")
        html = response.data.decode()
        table_start = html.index('aria-label="My actions"')
        table_end = html.index('<div class="modal"', table_start)
        actions_table = html[table_start:table_end]

        self.assertEqual(response.status_code, 200)
        self.assertEqual(actions_table.count(f"incident_review:{resolved_flag.id}"), 0)
        self.assertIn("Review Staffing due to incident", actions_table)
        self.assertIn("Review Logistics due to incident", actions_table)
        self.assertIn("Review Schedule due to incident", actions_table)
        self.assertIn("Not set", actions_table)
        self.assertIn('data-modal-scroll-target="staffing-%s"' % self.session_record.id, actions_table)
        self.assertIn('data-modal-scroll-target="logistics-%s"' % no_due_flag.exam_session_id, actions_table)
        self.assertIn('data-modal-scroll-target="schedule-actions-%s"' % other_session.id, actions_table)
        self.assertEqual(
            readiness_before["status"],
            session_readiness_contract(
                {"ready": True, "status": "ready"},
                {"raw_status": "Cleared", "label": "Cleared"},
                {"raw_status": "Ready", "label": "Ready"},
                {"raw_status": "Completed", "label": "Completed"},
                {"status": "none", "label": "No active incidents", "active_count": 0, "critical_count": 0, "high_count": 0, "message": "No active incidents.", "blockers": []},
                empty_review_flags,
            )["status"],
        )

    def test_control_tower_incidents_column_manage_and_my_actions(self):
        open_incident = ExamSessionIncident(
            exam_session_id=self.session_record.id,
            incident_type="Staff member unavailable",
            title="Examiner unavailable",
            severity="Medium",
            status="Open",
            responsible_department="ADMIN",
            due_at=date(2026, 6, 25),
        )
        critical_incident = ExamSessionIncident(
            exam_session_id=self.session_record.id,
            incident_type="Package sent to wrong supervisor",
            title="Wrong recipient",
            severity="Critical",
            status="Waiting external",
            responsible_department="LOGISTICS",
            due_at=date(2026, 6, 20),
        )
        db.session.add_all([open_incident, critical_incident])
        db.session.commit()
        review_count_before = ExamSessionIncidentImpactReview.query.count()
        client = self.login_client()

        response = client.get("/pre-session-control-tower?session_year=2026&view=sessions")
        html = response.data.decode()
        self.assertEqual(ExamSessionIncidentImpactReview.query.count(), review_count_before)
        self.assertEqual(response.status_code, 200)
        self.assertLess(html.index("<th>Session readiness</th>"), html.index("<th>Incidents</th>"))
        self.assertLess(html.index("<th>Incidents</th>"), html.index("<th>Priority action</th>"))
        self.assertIn("Create incident", html)
        self.assertIn("Active incidents", html)
        self.assertIn("Examiner unavailable", html)
        self.assertIn("Wrong recipient", html)
        self.assertIn("Playbook", html)
        self.assertIn("Potential impact", html)
        self.assertIn("These areas may require review because of this incident.", html)
        self.assertIn("Review staff assignment and replacement need.", html)
        self.assertIn("Mark as reviewed", html)
        self.assertIn("Mark as not applicable", html)
        self.assertIn("This session has a critical active incident.", html)
        self.assertIn("There is 1 critical active incident.", html)

        response = client.get("/pre-session-control-tower?session_year=2026&view=my-actions&action_source=Incidents")
        html = response.data.decode()
        self.assertEqual(response.status_code, 200)
        self.assertIn("Review incident", html)
        self.assertIn("Resolve critical incident", html)
        self.assertIn("Examiner unavailable", html)
        self.assertIn("Wrong recipient", html)

        response = client.get("/pre-session-control-tower?session_year=2026&view=my-actions&action_source=Incidents&action_responsible=LOGISTICS&action_status=Overdue")
        html = response.data.decode()
        self.assertEqual(response.status_code, 200)
        self.assertIn("Resolve critical incident", html)
        self.assertNotIn("Review incident", html[html.index('aria-label="My actions"'):html.index('<div class="modal"', html.index('aria-label="My actions"'))])

    def test_control_tower_render_shows_schedule_gate_and_year_summary(self):
        approved_session = ExamSession(
            exam_session_name="Approved session",
            category="Path School",
            status="Pending",
            session_date=date(2026, 7, 1),
            shifts="Morning",
            modules="Speaking",
            format="Online",
        )
        other_year_session = ExamSession(
            exam_session_name="Other year session",
            category="Path School",
            status="Pending",
            session_date=date(2027, 7, 1),
            shifts="Morning",
            modules="Speaking",
            format="Online",
        )
        db.session.add_all([approved_session, other_year_session])
        db.session.flush()
        db.session.add(ExamSessionScheduleWorkflow(
            exam_session_id=approved_session.id,
            status="Approved",
        ))
        db.session.add(ExamSessionScheduleWorkflow(
            exam_session_id=other_year_session.id,
            status="Approved",
        ))
        db.session.commit()
        client = self.login_client()

        response = client.get("/pre-session-control-tower?session_year=2026&view=sessions")
        html = response.data.decode()

        self.assertEqual(response.status_code, 200)
        self.assertIn("<th>Action</th>", html)
        self.assertLess(html.index("<th>Action</th>"), html.index("<th>Session</th>"))
        self.assertIn("<th>Schedule</th>", html)
        self.assertNotIn("<th>Schedule status</th>", html)
        self.assertNotIn("<th>Schedule gate</th>", html)
        self.assertIn("Schedule blocked", html)
        self.assertIn("Schedule ready", html)
        self.assertIn("Gate: Ready", html)
        self.assertIn("Gate: Blocked", html)
        self.assertIn("This session cannot move to the next pre-session stages until the schedules are approved.", html)
        self.assertIn("Schedules are approved. The session can move to the next pre-session stages.", html)
        self.assertNotIn("Other year session", html)

    def test_control_tower_sessions_table_uses_contextual_modal_targets(self):
        client = self.login_client()

        response = client.get("/pre-session-control-tower?session_year=2026&view=sessions")
        html = response.data.decode()
        session_id = self.session_record.id
        table_start = html.index('aria-label="Schedule preparation and approval"')
        table_end = html.index('<div class="modal"', table_start)
        sessions_table = html[table_start:table_end]

        self.assertEqual(response.status_code, 200)
        self.assertIn("Session overview", sessions_table)
        self.assertIn("<th>Schedule</th>", sessions_table)
        self.assertNotIn("<th>Schedule status</th>", sessions_table)
        self.assertNotIn("<th>Schedule gate</th>", sessions_table)
        self.assertNotIn("<th>Core readiness</th>", sessions_table)
        self.assertNotIn("<th>Operational readiness</th>", sessions_table)
        self.assertNotIn("<th>Review round</th>", sessions_table)
        self.assertNotIn("<th>Responsible</th>", sessions_table)
        self.assertNotIn("<th>Deadline</th>", sessions_table)
        self.assertIn("Gate:", sessions_table)
        self.assertIn(f'data-open-modal="schedule-workflow-{session_id}" data-modal-scroll-target="overview-{session_id}" data-modal-mode="overview"', sessions_table)
        for target, label in [
            ("schedule-actions", "Review schedule"),
            ("staffing", "Manage staffing"),
            ("logistics", "Review logistics"),
            ("packages", "Manage packages"),
            ("shipments", "Track shipment"),
            ("readiness", "View readiness"),
            ("finance", "Review finance"),
            ("sinapsis", "Check Sinapsis"),
            ("communications", "Review communications"),
            ("incidents", "Open incidents"),
        ]:
            self.assertIn(f'data-modal-scroll-target="{target}-{session_id}"', sessions_table)
            self.assertIn(f'data-modal-target-label="{label}"', sessions_table)
            self.assertIn(f'aria-label="{label} for {self.session_record.exam_session_name}"', sessions_table)
        self.assertIn("contextual-cell-trigger", sessions_table)
        self.assertNotIn(">Manage</button>", sessions_table)

    def test_control_tower_my_actions_tab_filters_and_excludes_ready_actions(self):
        staffing_session = ExamSession(
            exam_session_name="Staffing action session",
            category="Path School",
            status="Pending",
            session_date=date(2026, 7, 1),
            shifts="Morning",
            modules="Speaking",
            format="Online",
        )
        logistics_session = ExamSession(
            exam_session_name="Logistics action session",
            category="Path School",
            status="Pending",
            session_date=date(2026, 7, 2),
            shifts="Morning",
            modules="Speaking",
            format="Online",
        )
        ready_session = ExamSession(
            exam_session_name="Ready action session",
            category="Path School",
            status="Pending",
            session_date=date(2026, 7, 3),
            shifts="Morning",
            modules="Speaking",
            format="Online",
        )
        db.session.add_all([staffing_session, logistics_session, ready_session])
        db.session.flush()
        db.session.add_all([
            ExamSessionScheduleWorkflow(exam_session_id=staffing_session.id, status="Approved"),
            ExamSessionSupervisorAssignment(exam_session_id=staffing_session.id),
            ExamSessionStaffingControl(
                exam_session_id=staffing_session.id,
                staffing_due_at=date(2099, 1, 1),
                note="Cover open role.",
            ),
            ExamSessionScheduleWorkflow(exam_session_id=logistics_session.id, status="Approved"),
            ExamSessionSupervisorAssignment(
                exam_session_id=logistics_session.id,
                team_member_id=1,
                participation_status="Confirmed",
                logistics_enabled=True,
            ),
            ExamSessionScheduleWorkflow(exam_session_id=ready_session.id, status="Approved"),
            ExamSessionSupervisorAssignment(
                exam_session_id=ready_session.id,
                team_member_id=2,
                participation_status="Confirmed",
            ),
            ExamSessionExaminerAssignment(
                exam_session_id=ready_session.id,
                team_member_id=3,
                participation_status="Confirmed",
            ),
            ExamSessionInternAssignment(
                exam_session_id=ready_session.id,
                team_member_id=4,
                participation_status="Confirmed",
            ),
        ])
        db.session.commit()
        client = self.login_client()

        response = client.get("/pre-session-control-tower?session_year=2026&view=my-actions")
        html = response.data.decode()
        table_start = html.index('aria-label="My actions"')
        table_end = html.index('<div class="modal"', table_start)
        actions_table = html[table_start:table_end]

        self.assertEqual(response.status_code, 200)
        self.assertIn("Sessions", html)
        self.assertIn("My actions", html)
        self.assertLess(actions_table.index("<th>Manage</th>"), actions_table.index("<th>Priority action</th>"))
        self.assertIn("Start schedule preparation", actions_table)
        self.assertIn("Assign staff to open roles", actions_table)
        self.assertIn("Configure logistics requirements", actions_table)
        self.assertIn("MANAGEMENT", actions_table)
        self.assertIn("ADMIN", actions_table)
        self.assertIn("Upcoming", actions_table)
        self.assertNotIn("Ready for next stage", actions_table)
        self.assertIn(f'data-open-modal="schedule-workflow-{staffing_session.id}"', actions_table)

        response = client.get("/pre-session-control-tower?session_year=2026&view=my-actions&action_source=Staffing&action_responsible=ADMIN&action_status=Upcoming")
        html = response.data.decode()
        table_start = html.index('aria-label="My actions"')
        table_end = html.index('<div class="modal"', table_start)
        filtered_table = html[table_start:table_end]

        self.assertIn("Assign staff to open roles", filtered_table)
        self.assertIn("Staffing action session", filtered_table)
        self.assertNotIn("Start schedule preparation", filtered_table)
        self.assertNotIn("Configure logistics requirements", filtered_table)
        self.assertIn('option value="Staffing" selected', html)
        self.assertIn('option value="ADMIN" selected', html)
        self.assertIn('option value="Upcoming" selected', html)

        response = client.get("/pre-session-control-tower?session_year=2026&view=my-actions&action_source=Readiness")
        html = response.data.decode()
        self.assertIn("No pending actions for the selected year.", html)
        self.assertIn("Sessions that are ready for the next stage are not shown in My actions.", html)

    def test_uat_session_ready_end_to_end_no_pending_actions_and_no_get_side_effects(self):
        self.mark_session_operationally_ready()
        self.mark_session_external_readiness_ready()
        client = self.login_client()
        counts_before = self.pre_session_data_counts()

        response = client.get("/pre-session-control-tower?session_year=2026&view=sessions")
        all_sessions_html = response.data.decode()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.pre_session_data_counts(), counts_before)
        self.assertIn("Ready for next stage", all_sessions_html)
        self.assertIn("Operationally ready", all_sessions_html)
        self.assertIn("Session ready", all_sessions_html)
        self.assertIn("No active incidents", all_sessions_html)
        self.assertIn("No active review flags", all_sessions_html)

        response = client.get("/pre-session-control-tower?session_year=2026&view=my-actions")
        my_actions_html = response.data.decode()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.pre_session_data_counts(), counts_before)
        actions_start = my_actions_html.index('aria-label="My actions"')
        actions_end = my_actions_html.index('<div class="modal"', actions_start)
        actions_table = my_actions_html[actions_start:actions_end]
        self.assertIn("No pending actions for the selected year.", actions_table)
        self.assertNotIn("Ready for next stage", actions_table)
        self.assertNotIn("June exam session", actions_table)

        response = client.get(f"/pre-session-control-tower?session_year=2026&open_schedule_modal={self.session_record.id}")
        manage_html = response.data.decode()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.pre_session_data_counts(), counts_before)
        self.assertIn(f'id="overview-{self.session_record.id}"', manage_html)
        self.assertIn(f'id="schedule-actions-{self.session_record.id}"', manage_html)
        self.assertIn(f'id="readiness-{self.session_record.id}"', manage_html)
        for technical_token in [
            "undefined",
            "null",
            "{&quot;",
            "Institution approval",
            "Waiting for institution",
        ]:
            self.assertNotIn(technical_token, manage_html)

    def test_uat_external_incident_blockers_do_not_create_false_session_ready(self):
        self.mark_session_operationally_ready()
        finance, sinapsis, communications = self.mark_session_external_readiness_ready()
        finance.status = "Finance hold"
        sinapsis.status = "Not reviewed"
        communications.status = "Needs follow-up"
        for item in ExamSessionCommunicationsChecklistItem.query.filter_by(communications_control_id=communications.id).limit(1).all():
            item.is_checked = False
        db.session.add(ExamSessionIncident(
            exam_session_id=self.session_record.id,
            incident_type="Package sent to wrong supervisor",
            title="Wrong recipient",
            severity="Critical",
            status="Open",
            responsible_department="LOGISTICS",
            due_at=date(2026, 6, 20),
        ))
        db.session.commit()
        client = self.login_client()

        response = client.get("/pre-session-control-tower?session_year=2026&view=sessions")
        html = response.data.decode()
        self.assertEqual(response.status_code, 200)
        self.assertIn("Operationally ready", html)
        self.assertIn("Finance hold", html)
        self.assertIn("Sinapsis has not been reviewed for this session yet.", html)
        self.assertIn("Communications need follow-up before they can be completed.", html)
        self.assertIn("This session has a critical active incident.", html)
        self.assertIn("Potential impact", html)
        self.assertNotIn("Session ready", html[html.index("<tbody>"):html.index('<div class="modal"')])

        response = client.get("/pre-session-control-tower?session_year=2026&view=my-actions")
        my_actions_html = response.data.decode()
        actions_start = my_actions_html.index('aria-label="My actions"')
        actions_end = my_actions_html.index('<div class="modal"', actions_start)
        actions_table = my_actions_html[actions_start:actions_end]
        self.assertIn("Resolve finance hold", actions_table)
        self.assertIn("Review Sinapsis readiness", actions_table)
        self.assertIn("Follow up communications", actions_table)
        self.assertIn("Resolve critical incident", actions_table)
        self.assertNotIn("Ready for next stage", actions_table)

    def test_session_activity_timeline_empty_state_and_no_side_effects(self):
        counts_before = self.pre_session_data_counts()

        timeline = session_activity_timeline_contract(self.session_record)

        self.assertEqual(timeline["total_events"], 0)
        self.assertEqual(timeline["events"], [])
        self.assertEqual(timeline["sources"], [])
        self.assertEqual(self.pre_session_data_counts(), counts_before)

        client = self.login_client()
        response = client.get("/pre-session-control-tower?session_year=2026&view=sessions")
        html = response.data.decode()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.pre_session_data_counts(), counts_before)
        self.assertIn("Session activity timeline", html)
        self.assertIn("No activity recorded for this session yet.", html)
        self.assertIn(f'id="activity-{self.session_record.id}"', html)
        self.assertIn(f'href="#activity-{self.session_record.id}"', html)

    def test_session_activity_timeline_consolidates_sources_and_sorts_descending(self):
        base_time = datetime(2026, 6, 25, 12, 0, tzinfo=timezone.utc)
        workflow = ExamSessionScheduleWorkflow(exam_session_id=self.session_record.id, status="Approved")
        package_unit = ExamSessionPackageUnit(
            exam_session_id=self.session_record.id,
            room_name="Room 1",
            module_name="Speaking",
            expected_candidate_count=10,
            actual_label_count=10,
            status="Quality checked",
        )
        finance = ExamSessionFinanceControl(exam_session_id=self.session_record.id, status="Cleared")
        sinapsis = ExamSessionSinapsisControl(exam_session_id=self.session_record.id, status="Ready")
        communications = ExamSessionCommunicationsControl(exam_session_id=self.session_record.id, status="Completed")
        incident = ExamSessionIncident(
            exam_session_id=self.session_record.id,
            incident_type="Supervisor changed",
            title="Supervisor replacement",
            severity="High",
            status="Resolved",
            responsible_department="ADMIN",
        )
        db.session.add_all([workflow, package_unit, finance, sinapsis, communications, incident])
        db.session.flush()
        bundle = ExamSessionShipmentBundle(
            supervisor_staff_id=1,
            delivery_address="Av. Siempre Viva 123",
            courier="Correo Argentino",
            status="Dispatched",
        )
        db.session.add(bundle)
        db.session.flush()
        db.session.add(ExamSessionShipmentBundleSession(bundle_id=bundle.id, exam_session_id=self.session_record.id))
        db.session.add_all([
            ExamSessionScheduleEvent(
                workflow_id=workflow.id,
                previous_status="Sent for review",
                new_status="Approved",
                note="Approved after final review.",
                due_at=date(2026, 6, 26),
                created_by="Pablo",
                created_at=base_time,
            ),
            ExamSessionPackageEvent(
                package_unit_id=package_unit.id,
                event_type="STATUS_CHANGED",
                previous_status="Personalized",
                new_status="Quality checked",
                created_by="Logistics",
                created_at=base_time + timedelta(minutes=1),
            ),
            ExamSessionShipmentEvent(
                bundle_id=bundle.id,
                event_type="STATUS_CHANGED",
                previous_status="Ready to dispatch",
                new_status="Dispatched",
                tracking_number="123456789",
                created_by="Logistics",
                created_at=base_time + timedelta(minutes=2),
            ),
            ExamSessionFinanceEvent(
                finance_control_id=finance.id,
                event_type="updated",
                previous_status="Not reviewed",
                new_status="Cleared",
                created_at=base_time + timedelta(minutes=3),
            ),
            ExamSessionSinapsisEvent(
                sinapsis_control_id=sinapsis.id,
                event_type="updated",
                previous_status="In progress",
                new_status="Ready",
                note=None,
                created_by=None,
                created_at=base_time + timedelta(minutes=4),
            ),
            ExamSessionCommunicationsEvent(
                communications_control_id=communications.id,
                event_type="updated",
                previous_status="In progress",
                new_status="Completed",
                created_by="Admin",
                created_at=base_time + timedelta(minutes=5),
            ),
            ExamSessionIncidentEvent(
                incident_id=incident.id,
                event_type="review_flag_created",
                previous_status=None,
                new_status=None,
                note="Packages flagged for review due to Supervisor changed.",
                created_by="Admin",
                created_at=base_time + timedelta(minutes=6),
            ),
            ExamSessionIncidentEvent(
                incident_id=incident.id,
                event_type="updated",
                previous_status="Open",
                new_status="Resolved",
                created_by="Admin",
                created_at=base_time + timedelta(minutes=7),
            ),
        ])
        db.session.commit()

        timeline = session_activity_timeline_contract(self.session_record)
        descriptions = [event["description"] for event in timeline["events"]]
        titles = [event["title"] for event in timeline["events"]]

        self.assertEqual(timeline["total_events"], 8)
        self.assertEqual(timeline["events"][0]["title"], "Incident updated")
        self.assertEqual(timeline["events"][0]["description"], "Supervisor changed \u00b7 Supervisor replacement \u00b7 Open \u2192 Resolved")
        self.assertEqual(timeline["events"][-1]["title"], "Schedule status changed")
        self.assertIn("Schedule", timeline["sources"])
        self.assertIn("Packages", timeline["sources"])
        self.assertIn("Shipments", timeline["sources"])
        self.assertIn("Finance", timeline["sources"])
        self.assertIn("Sinapsis readiness", timeline["sources"])
        self.assertIn("Communications", timeline["sources"])
        self.assertIn("Incidents", timeline["sources"])
        self.assertIn("Incident review", timeline["sources"])
        self.assertIn("Sent for review \u2192 Approved", descriptions)
        self.assertIn("Room 1 \u00b7 Speaking \u00b7 Personalized \u2192 Quality checked", descriptions)
        self.assertIn("Ready to dispatch \u2192 Dispatched", descriptions)
        self.assertIn("Not reviewed \u2192 Cleared", descriptions)
        self.assertIn("In progress \u2192 Ready", descriptions)
        self.assertIn("In progress \u2192 Completed", descriptions)
        self.assertIn("Incident review flag created", titles)
        self.assertIn("Unknown user", [event["created_by"] for event in timeline["events"]])
        self.assertFalse(any(event["note"] == "None" for event in timeline["events"]))

        client = self.login_client()
        response = client.get(f"/pre-session-control-tower?session_year=2026&open_schedule_modal={self.session_record.id}")
        html = response.data.decode()

        self.assertEqual(response.status_code, 200)
        self.assertIn("Session activity timeline", html)
        self.assertIn("Schedule status changed", html)
        self.assertIn("Package status changed", html)
        self.assertIn("Shipment status changed", html)
        self.assertIn("Finance status changed", html)
        self.assertIn("Sinapsis readiness updated", html)
        self.assertIn("Communications status changed", html)
        self.assertIn("Incident review flag created", html)
        self.assertIn("Tracking", html)
        self.assertIn("123456789", html)
        self.assertIn("Unknown user", html)
        for technical_token in ["undefined", "null", "{&quot;", "STATUS_CHANGED", "review_flag_created"]:
            self.assertNotIn(technical_token, html)

    def test_path_session_journey_countdown_labels_are_date_based(self):
        today = date(2026, 6, 20)

        self.assertEqual(journey_countdown(date(2026, 7, 2), today=today)["label"], "12 days to go")
        self.assertEqual(journey_countdown(date(2026, 6, 21), today=today)["label"], "1 day to go")
        self.assertEqual(journey_countdown(date(2026, 6, 20), today=today)["label"], "Exam day is today")
        past = journey_countdown(date(2026, 6, 19), today=today)
        self.assertTrue(past["has_passed"])
        self.assertEqual(past["days_to_go"], 0)
        self.assertEqual(past["label"], "This Path exam session has taken place.")

    def test_path_session_journey_contract_separates_institution_and_public_safety(self):
        self.session_record.session_date = date(2026, 7, 2)
        self.session_record.city = "Cordoba"
        self.session_record.province = "Cordoba"
        db.session.add(ExamSessionFinanceControl(
            exam_session_id=self.session_record.id,
            status="Finance hold",
            note="Internal debt note",
        ))
        self.create_incident_review_flag_record(
            affected_area="packages",
            status="Needs review",
            title="Package discrepancy",
        )
        db.session.commit()

        institution = path_session_journey_contract(self.session_record, "institution", today=date(2026, 6, 20))
        public = path_session_journey_contract(self.session_record, "public", today=date(2026, 6, 20))

        self.assertEqual(institution["title"], "Path Session Journey \u2014 for institutions")
        self.assertEqual(public["title"], "Path Session Journey \u2014 for families and candidates")
        self.assertTrue(institution["administrative_readiness"]["visible"])
        self.assertEqual(institution["administrative_readiness"]["label"], "Administrative & payment readiness")
        self.assertEqual(institution["administrative_readiness"]["status"], "On hold")
        self.assertFalse(public["administrative_readiness"]["visible"])
        public_text = " ".join(
            [public["hero_message"], public["final_message"]]
            + [milestone["label"] for milestone in public["milestones"]]
            + [milestone["message"] for milestone in public["milestones"]]
            + public["next_steps"]
        )
        for forbidden in [
            "Finance",
            "Payment follow-up required",
            "Finance hold",
            "Incident",
            "Review flag",
            "Tracking",
            "NEP",
            "Discrepancy",
            "Overdue",
            "Blocked",
            "hold",
        ]:
            self.assertNotIn(forbidden, public_text)
        institution_text = " ".join(
            [institution["hero_message"], institution["final_message"]]
            + [milestone["label"] for milestone in institution["milestones"]]
            + [milestone["message"] for milestone in institution["milestones"]]
        )
        self.assertNotIn("Package discrepancy", institution_text)
        self.assertNotIn("Internal debt note", institution_text)

    def test_path_session_journey_milestones_follow_safe_readiness_sources(self):
        self.mark_session_operationally_ready()
        self.mark_session_external_readiness_ready()

        institution = path_session_journey_contract(self.session_record, "institution", today=date(2026, 6, 20))
        milestones = {milestone["key"]: milestone for milestone in institution["milestones"]}

        self.assertEqual(milestones["schedule"]["status"], "completed")
        self.assertEqual(milestones["staffing"]["status"], "completed")
        self.assertEqual(milestones["materials_prepared"]["status"], "completed")
        self.assertEqual(milestones["materials_dispatched"]["status"], "completed")
        self.assertEqual(milestones["materials_delivered"]["status"], "completed")
        self.assertEqual(milestones["session_ready"]["status"], "completed")
        self.assertEqual(institution["overall_label"], "Everything ready")

    def test_path_session_journey_preview_and_share_routes_are_read_only_and_safe(self):
        self.mark_session_operationally_ready()
        db.session.add(ExamSessionFinanceControl(
            exam_session_id=self.session_record.id,
            status="Payment follow-up required",
        ))
        db.session.commit()
        client = self.login_client()

        unauthenticated = self.app.test_client().get(
            f"/pre-session-control-tower/sessions/{self.session_record.id}/journey/public/preview"
        )
        self.assertEqual(unauthenticated.status_code, 302)
        tokens_before = ExamSessionJourneyShare.query.count()
        counts_before = self.pre_session_data_counts()
        preview = client.get(
            f"/pre-session-control-tower/sessions/{self.session_record.id}/journey/public/preview"
        )
        self.assertEqual(preview.status_code, 200)
        self.assertIn("Path Session Journey \u2014 for families and candidates", preview.data.decode())
        self.assertEqual(ExamSessionJourneyShare.query.count(), tokens_before)
        self.assertEqual(self.pre_session_data_counts(), counts_before)

        invalid = self.app.test_client().get("/path-session-journey/not-a-real-token/public")
        self.assertEqual(invalid.status_code, 404)
        self.assertIn("This journey link is no longer available.", invalid.data.decode())

        first_post = client.post(
            f"/pre-session-control-tower/sessions/{self.session_record.id}/journey-share/institution/enable",
            data={"csrf_token": "token", "schedule_status": "", "view": "sessions"},
        )
        self.assertEqual(first_post.status_code, 302)
        institution_share = ExamSessionJourneyShare.query.filter_by(exam_session_id=self.session_record.id, audience="institution").one()
        second_post = client.post(
            f"/pre-session-control-tower/sessions/{self.session_record.id}/journey-share/institution/enable",
            data={"csrf_token": "token", "schedule_status": "", "view": "sessions"},
        )
        self.assertEqual(second_post.status_code, 302)
        self.assertEqual(ExamSessionJourneyShare.query.filter_by(exam_session_id=self.session_record.id).count(), 1)
        self.assertEqual(ExamSessionJourneyShare.query.first().token, institution_share.token)

        counts_before_share = self.pre_session_data_counts()
        mismatched_public_share = self.app.test_client().get(f"/path-session-journey/{institution_share.token}/public")
        self.assertEqual(mismatched_public_share.status_code, 404)
        public_enable = client.post(
            f"/pre-session-control-tower/sessions/{self.session_record.id}/journey-share/public/enable",
            data={"csrf_token": "token", "schedule_status": "", "view": "sessions"},
        )
        self.assertEqual(public_enable.status_code, 302)
        public_share_record = ExamSessionJourneyShare.query.filter_by(exam_session_id=self.session_record.id, audience="public").one()
        self.assertNotEqual(institution_share.token, public_share_record.token)
        public_share = self.app.test_client().get(f"/path-session-journey/{public_share_record.token}/public")
        public_html = public_share.data.decode()
        self.assertEqual(public_share.status_code, 200)
        self.assertIn("Thank you for being part of the Path experience", public_html)
        self.assertIn("Milestones", public_html)
        for forbidden in [
            "Finance",
            "Payment follow-up required",
            "Incident",
            "Review flag",
            "Tracking",
            "NEP",
            "Discrepancy",
            "Overdue",
            "Blocked",
        ]:
            self.assertNotIn(forbidden, public_html)
        self.assertEqual(self.pre_session_data_counts(), counts_before_share)

        institution_response = self.app.test_client().get(f"/path-session-journey/{institution_share.token}/institution")
        institution_html = institution_response.data.decode()
        self.assertEqual(institution_response.status_code, 200)
        self.assertIn("Administrative &amp; payment readiness", institution_html)

        public_share_record.is_enabled = False
        db.session.commit()
        disabled = self.app.test_client().get(f"/path-session-journey/{public_share_record.token}/public")
        self.assertEqual(disabled.status_code, 410)
        self.assertIn("This journey link is no longer available.", disabled.data.decode())

    def test_path_session_journey_pages_filter_sensitive_strings_and_use_safe_status_labels(self):
        self.session_record.session_date = date(2026, 7, 2)
        self.session_record.city = "Cordoba"
        self.session_record.province = "Cordoba"
        self.approve_schedule()
        self.create_supervisor()
        self.confirm_staffing()
        package_unit = self.create_package_unit_record(status="Pre-packing", expected=10, actual=9)
        package_unit.has_nep_candidates = True
        package_unit.note = "Internal note about Package discrepancy and NEP"
        bundle = self.create_shipment_bundle_record(status="Dispatched")
        bundle.tracking_number = "TRACK-123456"
        finance = ExamSessionFinanceControl(
            exam_session_id=self.session_record.id,
            status="Finance hold",
            note="debt collection issue",
        )
        incident = ExamSessionIncident(
            exam_session_id=self.session_record.id,
            incident_type="Staff replacement",
            title="Label mismatch",
            severity="High",
            status="Open",
            responsible_department="ADMIN",
            description="Internal note",
        )
        flag = ExamSessionIncidentReviewFlag(
            exam_session=self.session_record,
            incident=incident,
            impact_key="staff_replacement:packages",
            affected_area="packages",
            status="Needs review",
            reason="Review flag reason",
        )
        db.session.add_all([finance, incident, flag])
        db.session.commit()
        institution_share = ExamSessionJourneyShare(
            exam_session_id=self.session_record.id,
            audience="institution",
            token="safe-token-for-qa",
            created_by="admin",
        )
        public_share = ExamSessionJourneyShare(
            exam_session_id=self.session_record.id,
            audience="public",
            token="safe-public-token-for-qa",
            created_by="admin",
        )
        db.session.add_all([institution_share, public_share])
        db.session.commit()

        public_response = self.app.test_client().get(f"/path-session-journey/{public_share.token}/public")
        institution_response = self.app.test_client().get(f"/path-session-journey/{institution_share.token}/institution")
        public_html = public_response.data.decode()
        institution_html = institution_response.data.decode()

        self.assertEqual(public_response.status_code, 200)
        self.assertEqual(institution_response.status_code, 200)
        self.assertIn("Your Path exam day is getting closer", public_html)
        self.assertIn("Coming soon", public_html)
        self.assertIn("Follow the key milestones as we prepare your upcoming Path exam session.", institution_html)
        self.assertIn("Administrative &amp; payment readiness", institution_html)
        self.assertIn("On hold", institution_html)
        self.assertIn("The session requires administrative/payment clearance before moving forward.", institution_html)
        public_forbidden = [
            "Finance",
            "Finance hold",
            "Payment follow-up required",
            "Administrative &amp; payment readiness",
            "Administrative & payment readiness",
            "Action required",
            "On hold",
            "Blocked",
            "Overdue",
            "Incident",
            "Incidents",
            "Review flag",
            "Review flags",
            "Tracking",
            "Tracking number",
            "TRACK-123456",
            "NEP",
            "Discrepancy",
            "Package discrepancy",
            "Staff replacement",
            "Internal note",
            "Needs review",
            "Courier risk",
            "Shipment delayed",
            "Label mismatch",
            "Technical",
            "undefined",
            "null",
            "None",
            "JSON",
            "event_type",
            "internal_id",
        ]
        institution_forbidden = [
            "Incident",
            "Review flag",
            "Tracking number",
            "TRACK-123456",
            "NEP",
            "Staff phone",
            "Staff email",
            "Internal note",
            "Package discrepancy",
            "Label mismatch",
            "undefined",
            "null",
            "None",
            "JSON",
            "event_type",
            "internal_id",
            "debt",
            "delinquency",
            "collection issue",
        ]
        for forbidden in public_forbidden:
            self.assertNotIn(forbidden, public_html)
        for forbidden in institution_forbidden:
            self.assertNotIn(forbidden, institution_html)

    def test_path_session_journey_invalid_audience_and_revoked_gets_have_no_side_effects(self):
        share = ExamSessionJourneyShare(
            exam_session_id=self.session_record.id,
            audience="institution",
            token="revoked-token-for-qa",
            created_by="admin",
            revoked_at=datetime(2026, 6, 20, 12, 0, tzinfo=timezone.utc),
        )
        db.session.add(share)
        db.session.commit()
        counts_before = self.pre_session_data_counts()
        token_count_before = ExamSessionJourneyShare.query.count()

        invalid_audience = self.app.test_client().get(f"/path-session-journey/{share.token}/not-public")
        audience_mismatch = self.app.test_client().get(f"/path-session-journey/{share.token}/public")
        revoked = self.app.test_client().get(f"/path-session-journey/{share.token}/institution")

        self.assertEqual(invalid_audience.status_code, 404)
        self.assertEqual(audience_mismatch.status_code, 404)
        self.assertEqual(revoked.status_code, 410)
        self.assertIn("This journey link is no longer available.", invalid_audience.data.decode())
        self.assertIn("Please contact Path Examinations if you need an updated link.", revoked.data.decode())
        self.assertEqual(self.pre_session_data_counts(), counts_before)
        self.assertEqual(ExamSessionJourneyShare.query.count(), token_count_before)

    def test_path_session_journey_sharing_controls_are_independent_by_audience(self):
        client = self.login_client()

        institution_enable = client.post(
            f"/pre-session-control-tower/sessions/{self.session_record.id}/journey-share/institution/enable",
            data={"csrf_token": "token", "schedule_status": "", "view": "sessions"},
        )
        self.assertEqual(institution_enable.status_code, 302)
        institution_share = ExamSessionJourneyShare.query.filter_by(
            exam_session_id=self.session_record.id,
            audience="institution",
        ).one()
        self.assertTrue(institution_share.is_enabled)
        self.assertIsNone(ExamSessionJourneyShare.query.filter_by(
            exam_session_id=self.session_record.id,
            audience="public",
        ).first())

        public_enable = client.post(
            f"/pre-session-control-tower/sessions/{self.session_record.id}/journey-share/public/enable",
            data={"csrf_token": "token", "schedule_status": "", "view": "sessions"},
        )
        self.assertEqual(public_enable.status_code, 302)
        public_share = ExamSessionJourneyShare.query.filter_by(
            exam_session_id=self.session_record.id,
            audience="public",
        ).one()
        self.assertTrue(public_share.is_enabled)
        self.assertNotEqual(institution_share.token, public_share.token)
        duplicate = ExamSessionJourneyShare(
            exam_session_id=self.session_record.id,
            audience="public",
            token="duplicate-public-audience",
        )
        db.session.add(duplicate)
        with self.assertRaises(IntegrityError):
            db.session.commit()
        db.session.rollback()

        public_token = public_share.token
        institution_token = institution_share.token
        disable_institution = client.post(
            f"/pre-session-control-tower/sessions/{self.session_record.id}/journey-share/institution/disable",
            data={"csrf_token": "token", "schedule_status": "", "view": "sessions"},
        )
        self.assertEqual(disable_institution.status_code, 302)
        db.session.refresh(institution_share)
        db.session.refresh(public_share)
        self.assertFalse(institution_share.is_enabled)
        self.assertTrue(public_share.is_enabled)
        self.assertEqual(public_share.token, public_token)
        self.assertEqual(self.app.test_client().get(f"/path-session-journey/{institution_token}/institution").status_code, 410)
        self.assertEqual(self.app.test_client().get(f"/path-session-journey/{public_token}/public").status_code, 200)

        regenerate_public = client.post(
            f"/pre-session-control-tower/sessions/{self.session_record.id}/journey-share/public/regenerate",
            data={"csrf_token": "token", "schedule_status": "", "view": "sessions"},
        )
        self.assertEqual(regenerate_public.status_code, 302)
        db.session.refresh(institution_share)
        db.session.refresh(public_share)
        self.assertFalse(institution_share.is_enabled)
        self.assertTrue(public_share.is_enabled)
        self.assertEqual(institution_share.token, institution_token)
        self.assertNotEqual(public_share.token, public_token)
        regenerated_public_token = public_share.token
        self.assertEqual(self.app.test_client().get(f"/path-session-journey/{public_token}/public").status_code, 404)
        self.assertEqual(self.app.test_client().get(f"/path-session-journey/{public_share.token}/public").status_code, 200)

        enable_institution = client.post(
            f"/pre-session-control-tower/sessions/{self.session_record.id}/journey-share/institution/enable",
            data={"csrf_token": "token", "schedule_status": "", "view": "sessions"},
        )
        self.assertEqual(enable_institution.status_code, 302)
        db.session.refresh(institution_share)
        db.session.refresh(public_share)
        self.assertTrue(institution_share.is_enabled)
        self.assertTrue(public_share.is_enabled)
        self.assertEqual(public_share.token, regenerated_public_token)

    def test_path_session_journey_public_past_session_copy_is_careful(self):
        self.session_record.session_date = date(2026, 6, 1)
        db.session.commit()

        journey = path_session_journey_contract(self.session_record, "public", today=date(2026, 6, 20))

        self.assertTrue(journey["countdown"]["has_passed"])
        self.assertEqual(journey["countdown"]["label"], "This Path exam session has taken place.")
        self.assertIn("Thank you for being part of the Path experience", journey["hero_message"])
        self.assertIn("Thank you for being part of the Path experience", journey["final_message"])

    def test_control_tower_manage_shows_path_session_journey_controls(self):
        client = self.login_client()

        response = client.get("/pre-session-control-tower?session_year=2026&open_schedule_modal=1&manage_target=journey")
        html = response.data.decode()

        self.assertEqual(response.status_code, 200)
        self.assertIn("Path Session Journey", html)
        self.assertIn("Institution journey", html)
        self.assertIn("Families and candidates journey", html)
        self.assertIn("Link not generated", html)
        self.assertIn("Enable link", html)
        self.assertIn("Preview", html)
        self.assertIn(f'id="journey-{self.session_record.id}"', html)
        self.assertIn(f'href="#journey-{self.session_record.id}"', html)

        client.post(
            f"/pre-session-control-tower/sessions/{self.session_record.id}/journey-share/institution/enable",
            data={"csrf_token": "token", "schedule_status": "", "view": "sessions"},
        )
        response = client.get("/pre-session-control-tower?session_year=2026&open_schedule_modal=1&manage_target=journey")
        html = response.data.decode()

        self.assertEqual(response.status_code, 200)
        self.assertIn("Institution: Enabled", html)
        self.assertIn("Public: Link not generated", html)
        self.assertIn("Copy link", html)
        self.assertIn("Disable link", html)
        self.assertIn("Regenerate link", html)
        self.assertIn("This will make the current journey link unavailable. You can enable it again later.", html)
        self.assertIn("This will replace the current journey link. Anyone with the previous link will no longer be able to access it.", html)
        self.assertIn("/path-session-journey/", html)

    def test_control_tower_manage_modal_ux_structure_and_targets(self):
        client = self.login_client()

        response = client.get("/pre-session-control-tower?session_year=2026&view=my-actions")
        html = response.data.decode()
        session_id = self.session_record.id
        modal_start = html.index(f'id="schedule-workflow-{session_id}"')
        modal = html[modal_start:]
        actions_start = html.index('aria-label="My actions"')
        actions_end = html.index('<div class="modal"', actions_start)
        actions_table = html[actions_start:actions_end]

        self.assertEqual(response.status_code, 200)
        self.assertIn('role="dialog"', modal)
        self.assertIn('aria-modal="true"', modal)
        self.assertIn(f'aria-labelledby="schedule-workflow-title-{session_id}"', modal)
        self.assertIn('aria-label="Close modal"', modal)
        self.assertIn("View full session overview", modal)
        self.assertIn(f'data-overview-target="overview-{session_id}"', modal)
        self.assertIn("data-focused-context", modal)
        self.assertIn(f'id="overview-{session_id}"', modal)
        self.assertIn("A quick operational snapshot for this exam session.", modal)
        self.assertIn("Priority action", modal)
        self.assertIn("Key blockers", modal)
        self.assertIn("Quick links", modal)
        self.assertIn("Readiness summary", modal)
        self.assertIn("Journey sharing", modal)
        self.assertIn("Recent activity", modal)
        for href, label in [
            (f'#schedule-actions-{session_id}', "Review schedule"),
            (f'#staffing-{session_id}', "Manage staffing"),
            (f'#logistics-{session_id}', "Review logistics"),
            (f'#packages-{session_id}', "Manage packages"),
            (f'#shipments-{session_id}', "Track shipment"),
            (f'#finance-{session_id}', "Review finance"),
            (f'#sinapsis-{session_id}', "Check Sinapsis"),
            (f'#communications-{session_id}', "Review communications"),
            (f'#incidents-{session_id}', "Open incidents"),
            (f'#readiness-{session_id}', "View readiness"),
            (f'#journey-{session_id}', "Manage journey sharing"),
        ]:
            self.assertIn(f'href="{href}"', modal)
            self.assertIn(label, modal)
        self.assertIn('aria-label="Manage modal sections"', modal)
        self.assertIn(f'id="schedule-overview-{session_id}"', modal)
        self.assertIn(f'id="schedule-actions-{session_id}"', modal)
        self.assertIn(f'id="schedule-{session_id}"', modal)
        self.assertIn(f'id="readiness-{session_id}"', modal)
        self.assertIn(f'id="history-{session_id}"', modal)
        for target in [
            "staffing",
            "logistics",
            "packages",
            "shipments",
            "finance",
            "sinapsis",
            "communications",
            "incidents",
        ]:
            self.assertIn(f'id="{target}-{session_id}"', modal)
            self.assertIn(f'id="{target}-{session_id}" data-control-section data-default-collapsed="true"', modal)
        self.assertIn(f'id="schedule-actions-{session_id}" data-control-section data-default-collapsed="true"', modal)
        self.assertIn(f'id="journey-{session_id}" data-control-section data-default-collapsed="true"', modal)
        self.assertIn(f'id="activity-{session_id}" data-control-section data-default-collapsed="true"', modal)
        self.assertIn(f'data-modal-scroll-target="schedule-actions-{session_id}"', actions_table)

    def test_control_tower_staffing_read_only_summary_and_modal(self):
        no_staff_session = ExamSession(
            exam_session_name="No staffing",
            category="Path School",
            status="Pending",
            session_date=date(2026, 7, 1),
            shifts="Morning",
            modules="Speaking",
            format="Online",
        )
        confirmed_session = ExamSession(
            exam_session_name="Confirmed staffing",
            category="Path School",
            status="Pending",
            session_date=date(2026, 7, 2),
            shifts="Morning",
            modules="Speaking",
            format="Online",
        )
        awaiting_session = ExamSession(
            exam_session_name="Awaiting staffing",
            category="Path School",
            status="Pending",
            session_date=date(2026, 7, 3),
            shifts="Morning",
            modules="Speaking",
            format="Online",
        )
        invalid_session = ExamSession(
            exam_session_name="Invalid staffing",
            category="Path School",
            status="Pending",
            session_date=date(2026, 7, 4),
            shifts="Morning",
            modules="Speaking",
            format="Online",
        )
        db.session.add_all([no_staff_session, confirmed_session, awaiting_session, invalid_session])
        db.session.flush()
        db.session.add_all([
            ExamSessionScheduleWorkflow(exam_session_id=confirmed_session.id, status="Approved"),
            ExamSessionSupervisorAssignment(exam_session_id=self.session_record.id),
            ExamSessionSupervisorAssignment(exam_session_id=confirmed_session.id, team_member_id=1, participation_status="Confirmed"),
            ExamSessionExaminerAssignment(exam_session_id=confirmed_session.id, team_member_id=2, participation_status="Confirmed"),
            ExamSessionInternAssignment(exam_session_id=confirmed_session.id, team_member_id=3, participation_status="Confirmed"),
            ExamSessionSupervisorAssignment(exam_session_id=awaiting_session.id, team_member_id=4, participation_status="Pending"),
            ExamSessionExaminerAssignment(exam_session_id=awaiting_session.id, team_member_id=5, participation_status="Pre-confirmation sent"),
            ExamSessionSupervisorAssignment(exam_session_id=invalid_session.id, team_member_id=6, participation_status="Unexpected"),
        ])
        db.session.commit()
        client = self.login_client()

        response = client.get("/pre-session-control-tower?session_year=2026&view=sessions")
        html = response.data.decode()

        self.assertEqual(response.status_code, 200)
        self.assertIn("<th>Staffing</th>", html)
        self.assertLess(html.index("<th>Action</th>"), html.index("<th>Session</th>"))
        self.assertLess(html.index("<th>Schedule</th>"), html.index("<th>Staffing</th>"))
        self.assertIn("Not configured", html)
        self.assertIn("No staff roles configured", html)
        self.assertNotIn("0 / 0 confirmed", html)
        self.assertIn("Open positions", html)
        self.assertIn("0 / 1 confirmed", html)
        self.assertIn("1 role to cover", html)
        self.assertIn("Awaiting confirmations", html)
        self.assertIn("2 awaiting confirmations", html)
        self.assertIn("Ready", html)
        self.assertIn("3 / 3 confirmed", html)
        self.assertIn("Supervisor", html)
        self.assertIn("Examiner", html)
        self.assertIn("Intern", html)
        self.assertIn("Needs review", html)
        self.assertIn("Staffing data needs to be reviewed before the session can be considered ready.", html)
        self.assertIn("Schedule approval is required before proceeding with the official staffing stage.", html)
        ready_modal_start = html.index('id="schedule-workflow-{}'.format(confirmed_session.id))
        ready_modal_end = html.index('id="schedule-workflow-{}'.format(awaiting_session.id))
        self.assertNotIn(
            "Schedule approval is required before proceeding with the official staffing stage.",
            html[ready_modal_start:ready_modal_end],
        )
        self.assertIn(
            f"/exam-session-planner?session_year=2026&amp;open_session_modal={self.session_record.id}",
            html,
        )
        self.assertNotIn("data-team-member-select", html)

    def test_control_tower_logistics_read_only_states_and_column_order(self):
        no_logistics_session = ExamSession(
            exam_session_name="No logistics",
            category="Path School",
            status="Pending",
            session_date=date(2026, 7, 1),
            shifts="Morning",
            modules="Speaking",
            format="Online",
        )
        configuration_session = ExamSession(
            exam_session_name="Needs logistics setup",
            category="Path School",
            status="Pending",
            session_date=date(2026, 7, 2),
            shifts="Morning",
            modules="Speaking",
            format="Online",
        )
        pending_session = ExamSession(
            exam_session_name="Pending logistics",
            category="Path School",
            status="Pending",
            session_date=date(2026, 7, 3),
            shifts="Morning",
            modules="Speaking",
            format="Online",
        )
        payment_session = ExamSession(
            exam_session_name="Payment logistics",
            category="Path School",
            status="Pending",
            session_date=date(2026, 7, 4),
            shifts="Morning",
            modules="Speaking",
            format="Online",
        )
        ready_session = ExamSession(
            exam_session_name="Ready logistics",
            category="Path School",
            status="Pending",
            session_date=date(2026, 7, 5),
            shifts="Morning",
            modules="Speaking",
            format="Online",
        )
        missing_link_session = ExamSession(
            exam_session_name="Missing link logistics",
            category="Path School",
            status="Pending",
            session_date=date(2026, 7, 6),
            shifts="Morning",
            modules="Speaking",
            format="Online",
        )
        db.session.add_all([
            no_logistics_session,
            configuration_session,
            pending_session,
            payment_session,
            ready_session,
            missing_link_session,
        ])
        db.session.flush()
        db.session.add_all([
            ExamSessionSupervisorAssignment(
                exam_session_id=configuration_session.id,
                team_member_id=1,
                participation_status="Confirmed",
                logistics_enabled=True,
            ),
            ExamSessionSupervisorAssignment(
                exam_session_id=pending_session.id,
                team_member_id=2,
                participation_status="Confirmed",
                logistics_enabled=True,
            ),
            ExamSessionLogisticsConcept(
                exam_session_id=pending_session.id,
                provider="Flight",
                status="Pending",
            ),
            ExamSessionSupervisorAssignment(
                exam_session_id=payment_session.id,
                team_member_id=3,
                participation_status="Confirmed",
                logistics_enabled=True,
            ),
            ExamSessionLogisticsConcept(
                exam_session_id=payment_session.id,
                provider="Hotel",
                status="Pre-confirmed",
            ),
            ExamSessionSupervisorAssignment(
                exam_session_id=ready_session.id,
                team_member_id=4,
                participation_status="Confirmed",
                logistics_enabled=True,
            ),
            ExamSessionLogisticsConcept(
                exam_session_id=ready_session.id,
                provider="Local transport",
                status="Confirmed",
            ),
            ExamSessionLogistics(
                exam_session_id=ready_session.id,
                logistics_files_url="https://example.com/ready-files",
            ),
            ExamSessionSupervisorAssignment(
                exam_session_id=missing_link_session.id,
                team_member_id=5,
                participation_status="Confirmed",
                logistics_enabled=True,
            ),
            ExamSessionLogisticsConcept(
                exam_session_id=missing_link_session.id,
                provider="Hotel",
                status="Confirmed",
            ),
        ])
        db.session.commit()
        client = self.login_client()

        response = client.get("/pre-session-control-tower?session_year=2026&view=sessions")
        html = response.data.decode()

        self.assertEqual(response.status_code, 200)
        self.assertLess(html.index("<th>Action</th>"), html.index("<th>Session</th>"))
        self.assertLess(html.index("<th>Staffing</th>"), html.index("<th>Logistics</th>"))
        self.assertLess(html.index("<th>Logistics</th>"), html.index("<th>Priority action</th>"))
        self.assertIn("Not applicable", html)
        self.assertIn("No logistics required", html)
        self.assertNotIn("0 / 0 concepts confirmed", html)
        self.assertIn("Configuration required", html)
        self.assertIn("1 member requires logistics", html)
        self.assertIn("In progress", html)
        self.assertIn("0 / 1 concepts confirmed", html)
        self.assertIn("Pre-confirmed", html)
        self.assertNotIn("Payment scheduled", html)
        self.assertIn("Ready", html)
        self.assertIn("1 / 1 concepts confirmed", html)
        self.assertIn("Files link missing", html)
        self.assertIn("logistics-control-status-files-link-missing", html)

    def test_control_tower_logistics_manage_detail_and_links(self):
        staff_one = AcademicStaff(
            status="Active",
            full_name="Dana Montalvo",
            roles="Supervisor",
        )
        staff_two = AcademicStaff(
            status="Active",
            full_name="Maria Gomez",
            roles="Examiner",
        )
        inactive_staff = AcademicStaff(
            status="Inactive",
            full_name="Inactive Person",
            roles="Intern",
        )
        detail_session = ExamSession(
            exam_session_name="Detailed logistics",
            category="Path School",
            status="Pending",
            session_date=date(2026, 8, 1),
            shifts="Morning",
            modules="Speaking",
            format="Online",
        )
        db.session.add_all([staff_one, staff_two, inactive_staff, detail_session])
        db.session.flush()
        db.session.add_all([
            ExamSessionScheduleWorkflow(
                exam_session_id=detail_session.id,
                status="Approved",
            ),
            ExamSessionSupervisorAssignment(
                exam_session_id=detail_session.id,
                team_member_id=staff_one.id,
                participation_status="Confirmed",
                logistics_enabled=True,
            ),
            ExamSessionExaminerAssignment(
                exam_session_id=detail_session.id,
                team_member_id=staff_two.id,
                participation_status="Confirmed",
                logistics_enabled=True,
            ),
            ExamSessionInternAssignment(
                exam_session_id=detail_session.id,
                team_member_id=inactive_staff.id,
                participation_status="Confirmed",
                logistics_enabled=True,
            ),
            ExamSessionInternAssignment(
                exam_session_id=detail_session.id,
                team_member_id=None,
                participation_status="Confirmed",
                logistics_enabled=True,
            ),
            ExamSessionLogisticsConcept(
                exam_session_id=detail_session.id,
                provider="Flight",
                status="Confirmed",
            ),
            ExamSessionLogisticsConcept(
                exam_session_id=detail_session.id,
                provider="Hotel",
                status="In progress",
            ),
            ExamSessionLogistics(
                exam_session_id=detail_session.id,
                logistics_files_url="https://example.com/logistics-files",
            ),
        ])
        db.session.commit()
        client = self.login_client()

        response = client.get("/pre-session-control-tower?session_year=2026&view=sessions")
        html = response.data.decode()

        self.assertEqual(response.status_code, 200)
        self.assertIn("3 members require logistics", html)
        self.assertIn("Dana Montalvo", html)
        self.assertIn("Dana Montalvo &mdash; Supervisor", html)
        self.assertIn("Maria Gomez &mdash; Examiner", html)
        self.assertNotIn("Inactive Person &mdash; Intern", html)
        self.assertIn("Flight", html)
        self.assertIn("Hotel is still In progress.", html)
        self.assertIn('href="https://example.com/logistics-files"', html)
        self.assertIn("Open logistics files", html)
        self.assertIn(
            f"/exam-session-planner?session_year=2026&amp;open_session_modal={detail_session.id}",
            html,
        )
        self.assertNotIn("data-add-logistics-concept", html)
        self.assertNotIn("data-logistics-checkbox", html)

    def test_control_tower_logistics_schedule_gate_notice_only_when_blocked(self):
        blocked_session = ExamSession(
            exam_session_name="Blocked logistics gate",
            category="Path School",
            status="Pending",
            session_date=date(2026, 9, 1),
            shifts="Morning",
            modules="Speaking",
            format="Online",
        )
        ready_session = ExamSession(
            exam_session_name="Ready logistics gate",
            category="Path School",
            status="Pending",
            session_date=date(2026, 9, 2),
            shifts="Morning",
            modules="Speaking",
            format="Online",
        )
        db.session.add_all([blocked_session, ready_session])
        db.session.flush()
        db.session.add_all([
            ExamSessionScheduleWorkflow(exam_session_id=ready_session.id, status="Approved"),
            ExamSessionSupervisorAssignment(
                exam_session_id=blocked_session.id,
                team_member_id=1,
                participation_status="Confirmed",
                logistics_enabled=True,
            ),
            ExamSessionLogisticsConcept(
                exam_session_id=blocked_session.id,
                provider="Flight",
                status="Pending",
            ),
            ExamSessionSupervisorAssignment(
                exam_session_id=ready_session.id,
                team_member_id=2,
                participation_status="Confirmed",
                logistics_enabled=True,
            ),
            ExamSessionLogisticsConcept(
                exam_session_id=ready_session.id,
                provider="Flight",
                status="Pending",
            ),
        ])
        db.session.commit()
        client = self.login_client()

        response = client.get("/pre-session-control-tower?session_year=2026&view=sessions")
        html = response.data.decode()
        notice = "Schedule approval is required before proceeding with the operational logistics stage."

        self.assertEqual(response.status_code, 200)
        self.assertIn("In progress", html)
        self.assertIn(notice, html)
        ready_modal_start = html.index(f'id="schedule-workflow-{ready_session.id}"')
        self.assertNotIn(notice, html[ready_modal_start:])

    def test_control_tower_core_readiness_column_modal_and_no_persistence(self):
        blocked_session = ExamSession(
            exam_session_name="Blocked core readiness",
            category="Path School",
            status="Pending",
            session_date=date(2026, 10, 1),
            shifts="Morning",
            modules="Speaking",
            format="Online",
        )
        staffing_open_session = ExamSession(
            exam_session_name="Staffing open core readiness",
            category="Path School",
            status="Pending",
            session_date=date(2026, 10, 2),
            shifts="Morning",
            modules="Speaking",
            format="Online",
        )
        logistics_config_session = ExamSession(
            exam_session_name="Logistics config core readiness",
            category="Path School",
            status="Pending",
            session_date=date(2026, 10, 3),
            shifts="Morning",
            modules="Speaking",
            format="Online",
        )
        ready_not_applicable_session = ExamSession(
            exam_session_name="Ready without logistics core readiness",
            category="Path School",
            status="Pending",
            session_date=date(2026, 10, 4),
            shifts="Morning",
            modules="Speaking",
            format="Online",
        )
        all_ready_session = ExamSession(
            exam_session_name="All ready core readiness",
            category="Path School",
            status="Pending",
            session_date=date(2026, 10, 5),
            shifts="Morning",
            modules="Speaking",
            format="Online",
        )
        db.session.add_all([
            blocked_session,
            staffing_open_session,
            logistics_config_session,
            ready_not_applicable_session,
            all_ready_session,
        ])
        db.session.flush()
        db.session.add_all([
            ExamSessionScheduleWorkflow(exam_session_id=staffing_open_session.id, status="Approved"),
            ExamSessionScheduleWorkflow(exam_session_id=logistics_config_session.id, status="Approved"),
            ExamSessionScheduleWorkflow(exam_session_id=ready_not_applicable_session.id, status="Approved"),
            ExamSessionScheduleWorkflow(exam_session_id=all_ready_session.id, status="Approved"),
            ExamSessionSupervisorAssignment(
                exam_session_id=blocked_session.id,
                team_member_id=1,
                participation_status="Confirmed",
                logistics_enabled=True,
            ),
            ExamSessionLogisticsConcept(
                exam_session_id=blocked_session.id,
                provider="Flight",
                status="Confirmed",
            ),
            ExamSessionLogistics(
                exam_session_id=blocked_session.id,
                logistics_files_url="https://example.com/blocked-files",
            ),
            ExamSessionSupervisorAssignment(exam_session_id=staffing_open_session.id),
            ExamSessionSupervisorAssignment(
                exam_session_id=logistics_config_session.id,
                team_member_id=2,
                participation_status="Confirmed",
                logistics_enabled=True,
            ),
            ExamSessionSupervisorAssignment(
                exam_session_id=ready_not_applicable_session.id,
                team_member_id=3,
                participation_status="Confirmed",
            ),
            ExamSessionSupervisorAssignment(
                exam_session_id=all_ready_session.id,
                team_member_id=4,
                participation_status="Confirmed",
                logistics_enabled=True,
            ),
            ExamSessionLogisticsConcept(
                exam_session_id=all_ready_session.id,
                provider="Hotel",
                status="Confirmed",
            ),
            ExamSessionLogistics(
                exam_session_id=all_ready_session.id,
                logistics_files_url="https://example.com/all-ready-files",
            ),
        ])
        db.session.commit()
        counts_before = {
            "sessions": ExamSession.query.count(),
            "workflows": ExamSessionScheduleWorkflow.query.count(),
            "events": ExamSessionScheduleEvent.query.count(),
            "logistics": ExamSessionLogistics.query.count(),
            "concepts": ExamSessionLogisticsConcept.query.count(),
        }
        client = self.login_client()

        response = client.get("/pre-session-control-tower?session_year=2026&view=sessions")
        html = response.data.decode()
        counts_after = {
            "sessions": ExamSession.query.count(),
            "workflows": ExamSessionScheduleWorkflow.query.count(),
            "events": ExamSessionScheduleEvent.query.count(),
            "logistics": ExamSessionLogistics.query.count(),
            "concepts": ExamSessionLogisticsConcept.query.count(),
        }

        self.assertEqual(response.status_code, 200)
        self.assertEqual(counts_before, counts_after)
        self.assertLess(html.index("<th>Action</th>"), html.index("<th>Session</th>"))
        self.assertLess(html.index("<th>Logistics</th>"), html.index("<th>Packages</th>"))
        self.assertNotIn("<th>Core readiness</th>", html)
        self.assertNotIn("<th>Operational readiness</th>", html)
        self.assertNotIn("<th>Next action</th>", html)
        self.assertIn("Priority action", html)
        self.assertIn("Core readiness", html)
        self.assertIn("This status only covers schedule approval, staffing and logistics.", html)
        self.assertIn("Blocked", html)
        self.assertIn("2 of 3 requirements are ready.", html)
        self.assertIn("Schedule approval is required", html)
        self.assertIn("In progress", html)
        self.assertIn("Ready for next stage", html)
        self.assertIn("3 of 3 requirements are ready.", html)
        self.assertIn("Schedule approval", html)
        self.assertIn("Staffing", html)
        self.assertIn("Logistics", html)
        self.assertIn("Logistics is enabled for 1 member, but no concepts have been configured.", html)
        self.assertIn("Assign staff to open roles", html)
        self.assertIn("Configure logistics requirements", html)
        self.assertIn("Ready for next stage", html)
        self.assertIn("Source: Staffing", html)
        self.assertIn("Source: Logistics", html)
        self.assertIn("Source: Core readiness", html)
        staffing_row_start = html.index("Staffing open core readiness")
        logistics_row_start = html.index("Logistics config core readiness")
        ready_row_start = html.index("Ready without logistics core readiness")
        staffing_row = html[staffing_row_start:logistics_row_start]
        logistics_row = html[logistics_row_start:ready_row_start]
        ready_row = html[ready_row_start:html.index("All ready core readiness")]
        self.assertIn("Assign staff to open roles", staffing_row)
        self.assertIn("ADMIN", staffing_row)
        self.assertIn("Not set", staffing_row)
        self.assertNotIn("Completed</span>", staffing_row)
        self.assertIn("Configure logistics requirements", logistics_row)
        self.assertIn("ADMIN", logistics_row)
        self.assertIn("Not set", logistics_row)
        self.assertNotIn("Completed</span>", logistics_row)
        self.assertIn("Ready for next stage", ready_row)
        self.assertIn("— · Completed", ready_row)
        ready_modal_start = html.index(f'id="schedule-workflow-{ready_not_applicable_session.id}"')
        next_modal_start = html.index(f'id="schedule-workflow-{all_ready_session.id}"')
        ready_modal = html[ready_modal_start:next_modal_start]
        self.assertIn("Not applicable", ready_modal)
        self.assertIn("No logistics required for this session.", ready_modal)
        self.assertIn("Priority action", ready_modal)

    def test_control_tower_operational_readiness_column_modal_and_no_persistence(self):
        self.create_supervisor()
        delivered_session = self.create_planning_ready_session("Delivered operational readiness", date(2026, 11, 1))
        ready_session = self.create_planning_ready_session("Ready operational readiness", date(2026, 11, 2))
        self.create_shipment_bundle_record(status="Delivered successfully", session_record=delivered_session)
        self.create_shipment_bundle_record(status="Recipient review successful", session_record=ready_session)
        counts_before = {
            "sessions": ExamSession.query.count(),
            "workflows": ExamSessionScheduleWorkflow.query.count(),
            "bundles": ExamSessionShipmentBundle.query.count(),
            "bundle_links": ExamSessionShipmentBundleSession.query.count(),
            "events": ExamSessionShipmentEvent.query.count(),
        }
        client = self.login_client()

        response = client.get("/pre-session-control-tower?session_year=2026&view=sessions")
        html = response.data.decode()
        counts_after = {
            "sessions": ExamSession.query.count(),
            "workflows": ExamSessionScheduleWorkflow.query.count(),
            "bundles": ExamSessionShipmentBundle.query.count(),
            "bundle_links": ExamSessionShipmentBundleSession.query.count(),
            "events": ExamSessionShipmentEvent.query.count(),
        }

        self.assertEqual(response.status_code, 200)
        self.assertEqual(counts_before, counts_after)
        self.assertNotIn("<th>Core readiness</th>", html)
        self.assertNotIn("<th>Operational readiness</th>", html)
        self.assertLess(html.index("<th>Communications</th>"), html.index("<th>Session readiness</th>"))
        self.assertLess(html.index("<th>Session readiness</th>"), html.index("<th>Priority action</th>"))
        self.assertIn("Operational readiness", html)
        self.assertIn("Session readiness", html)
        self.assertIn("This status covers schedule approval, staffing, staff logistics, packages and shipments. It does not include Finance, Sinapsis readiness, Communications, Incidents or Incident review flags.", html)
        self.assertIn("This status covers Operational readiness, Finance, Sinapsis readiness, Communications, Incidents and Incident review flags.", html)
        self.assertIn("Operationally ready", html)
        self.assertIn("5 of 5 requirements are ready.", html)
        self.assertIn("3 / 6 requirements ready", html)
        self.assertIn("4 of 5 requirements are ready.", html)
        self.assertIn("Shipment was delivered successfully, but recipient review is still pending.", html)
        delivered_row_start = html.index("Delivered operational readiness")
        ready_row_start = html.index("Ready operational readiness")
        delivered_modal_start = html.index(f'id="schedule-workflow-{delivered_session.id}"')
        delivered_modal_end = html.index(f'id="schedule-workflow-{ready_session.id}"')
        delivered_row = html[delivered_modal_start:delivered_modal_end]
        self.assertIn("In progress", delivered_row)
        self.assertIn("4 of 5 requirements are ready.", delivered_row)
        ready_modal_start = html.index(f'id="schedule-workflow-{ready_session.id}"')
        ready_modal = html[ready_modal_start:]
        self.assertIn("Operational readiness", ready_modal)
        self.assertIn("Session readiness", ready_modal)
        self.assertIn("Schedule approval, staffing, staff logistics, packages and shipments are complete.", ready_modal)
        self.assertIn("Finance has not reviewed this session yet.", ready_modal)
        self.assertIn("No active incidents.", ready_modal)
        self.assertIn("Shipments", ready_modal)
        self.assertIn("Shipment delivery and recipient review are complete.", ready_modal)

    def test_control_tower_core_readiness_awaiting_and_files_link_missing_are_in_progress(self):
        awaiting_session = ExamSession(
            exam_session_name="Awaiting core readiness",
            category="Path School",
            status="Pending",
            session_date=date(2026, 11, 1),
            shifts="Morning",
            modules="Speaking",
            format="Online",
        )
        missing_link_session = ExamSession(
            exam_session_name="Missing logistics link core readiness",
            category="Path School",
            status="Pending",
            session_date=date(2026, 11, 2),
            shifts="Morning",
            modules="Speaking",
            format="Online",
        )
        db.session.add_all([awaiting_session, missing_link_session])
        db.session.flush()
        db.session.add_all([
            ExamSessionScheduleWorkflow(exam_session_id=awaiting_session.id, status="Approved"),
            ExamSessionScheduleWorkflow(exam_session_id=missing_link_session.id, status="Approved"),
            ExamSessionSupervisorAssignment(
                exam_session_id=awaiting_session.id,
                team_member_id=1,
                participation_status="Official confirmation sent",
            ),
            ExamSessionSupervisorAssignment(
                exam_session_id=missing_link_session.id,
                team_member_id=2,
                participation_status="Confirmed",
                logistics_enabled=True,
            ),
            ExamSessionLogisticsConcept(
                exam_session_id=missing_link_session.id,
                provider="Flight",
                status="Confirmed",
            ),
        ])
        db.session.commit()
        client = self.login_client()

        response = client.get("/pre-session-control-tower?session_year=2026&view=sessions")
        html = response.data.decode()

        self.assertEqual(response.status_code, 200)
        awaiting_index = html.index("Awaiting core readiness")
        missing_link_index = html.index("Missing logistics link core readiness")
        self.assertIn("In progress", html[awaiting_index:missing_link_index])
        self.assertIn("In progress", html[missing_link_index:])
        self.assertIn("1 staff member is awaiting confirmation.", html)
        self.assertIn("All concepts are confirmed, but the logistics files link is missing.", html)


if __name__ == "__main__":
    unittest.main()
