import os
import unittest
from datetime import date, datetime, timedelta, timezone

os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from app import create_app, db
from app.models import (
    BillingRequest,
    ExamSession,
    ExamSessionScheduleNoteMention,
    ExamSessionScheduleWorkflow,
    ExamSessionShipmentBundle,
    ExamSessionShipmentBundleSession,
    ExamSessionStaffingNoteMention,
    ExamSessionSupervisorAssignment,
    FinanceConcept,
    PaymentRequest,
    PotentialEntry,
    User,
    UserMenuPermission,
    VALID_MENU_PERMISSION_KEYS,
)


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

    def permission_client(self, permissions, *, full_name="Person Example", department="Finance", email="person@example.com", is_superadmin=False):
        user = User(full_name=full_name, email=email, department=department, is_active=True, is_superadmin=is_superadmin)
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

    def add_finance_concept(self, name="Consultancy", applies_to="Both"):
        concept = FinanceConcept(name=name, applies_to=applies_to, is_active=True)
        db.session.add(concept)
        db.session.commit()
        return concept

    def add_payment_request(self, requester, *, status="Submitted", scheduled_payment_date=None, is_archived=False, request_number="PAY-2026-0001"):
        concept = FinanceConcept.query.first() or self.add_finance_concept()
        payment = PaymentRequest(
            request_number=request_number,
            requester_user_id=requester.id,
            requester_department=requester.department,
            description=f"{status} payment",
            concept_id=concept.id,
            concept_name_snapshot=concept.name,
            payee_name_snapshot="Payee Example",
            amount=100,
            currency="ARS",
            payment_method="Cash",
            scheduled_payment_date=scheduled_payment_date,
            status=status,
            is_archived=is_archived,
        )
        db.session.add(payment)
        db.session.commit()
        return payment

    def add_billing_request(self, requester, *, status="Requested", is_archived=False, request_number="INVOICE-2026-0001"):
        concept = FinanceConcept.query.first() or self.add_finance_concept()
        billing = BillingRequest(
            request_number=request_number,
            requester_user_id=requester.id,
            requester_department=requester.department,
            client_name_snapshot="Client Example",
            concept_id=concept.id,
            concept_name_snapshot=concept.name,
            description=f"{status} invoice",
            currency="ARS",
            amount=100,
            status=status,
            is_archived=is_archived,
        )
        db.session.add(billing)
        db.session.commit()
        return billing

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

    def test_dashboard_shows_finance_payment_actions_for_requester_departments(self):
        client = self.permission_client({"finance_requests": {"view": True}}, department="Logistics")
        requester = User.query.filter_by(email="person@example.com").one()
        other_user = User(full_name="Other User", email="other@example.com", department="Logistics", is_active=True)
        other_user.set_password("secret123")
        db.session.add(other_user)
        db.session.commit()
        self.add_payment_request(requester, status="Needs correction", request_number="PAY-2026-0001")
        self.add_payment_request(requester, status="Payment completed", request_number="PAY-2026-0002")
        self.add_payment_request(requester, status="On hold", request_number="PAY-2026-0006")
        self.add_payment_request(
            requester,
            status="Management approved",
            scheduled_payment_date=date.today() - timedelta(days=1),
            request_number="PAY-2026-0003",
        )
        self.add_payment_request(other_user, status="Payment completed", request_number="PAY-2026-0004")
        self.add_payment_request(requester, status="Payment cancelled", is_archived=True, request_number="PAY-2026-0005")

        response = client.get("/")
        body = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("<h2>Finance requests</h2>", body)
        self.assertIn("You have 4 actions to complete in this menu.", body)
        self.assertIn('aria-label="Finance requests counters"', body)
        self.assertIn('href="/finance-requests?tab=payment_requests">View actions in Payment requests</a>', body)

    def test_dashboard_shows_admin_invoice_actions_for_requested_cards(self):
        client = self.permission_client({"finance_requests": {"view": True}}, department="Admin")
        requester = User.query.filter_by(email="person@example.com").one()
        other_user = User(full_name="Other Admin", email="other-admin@example.com", department="Admin", is_active=True)
        other_user.set_password("secret123")
        db.session.add(other_user)
        db.session.commit()
        self.add_billing_request(requester, status="Invoice issued", request_number="INVOICE-2026-0001")
        self.add_billing_request(requester, status="Invoice cancelled", request_number="INVOICE-2026-0002")
        self.add_billing_request(other_user, status="Invoice issued", request_number="INVOICE-2026-0003")
        self.add_billing_request(requester, status="Invoice cancelled", is_archived=True, request_number="INVOICE-2026-0004")

        response = client.get("/")
        body = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("You have 2 actions to complete in this menu.", body)
        self.assertIn('href="/finance-requests?tab=billing_requests">View actions in Invoice requests</a>', body)

    def test_dashboard_shows_finance_today_actions_for_finance_users(self):
        client = self.permission_client({"finance_requests": {"view": True}}, department="Finance")
        requester = User.query.filter_by(email="person@example.com").one()
        self.add_payment_request(
            requester,
            status="Management approved",
            scheduled_payment_date=date.today(),
            request_number="PAY-2026-0001",
        )
        self.add_payment_request(
            requester,
            status="Payment scheduled",
            scheduled_payment_date=date.today() - timedelta(days=1),
            request_number="PAY-2026-0002",
        )
        self.add_payment_request(
            requester,
            status="Management approved",
            scheduled_payment_date=date.today() + timedelta(days=1),
            request_number="PAY-2026-0003",
        )
        self.add_billing_request(requester, status="Requested", request_number="INVOICE-2026-0001")

        response = client.get("/")
        body = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("You have 3 actions to complete in this menu.", body)
        self.assertIn(
            'href="/finance-requests?tab=finance_payments&amp;finance_filter=today">View actions in Finance actions</a>',
            body,
        )

    def test_dashboard_shows_superadmin_management_review_actions(self):
        client = self.permission_client(
            {},
            full_name="Super Admin",
            department="Management",
            email="super@example.com",
            is_superadmin=True,
        )
        requester = User.query.filter_by(email="super@example.com").one()
        other_user = User(full_name="Other Admin", email="other-super@example.com", department="Admin", is_active=True)
        other_user.set_password("secret123")
        db.session.add(other_user)
        db.session.commit()
        self.add_payment_request(requester, status="Submitted", request_number="PAY-2026-0001")
        self.add_payment_request(requester, status="Resubmitted", request_number="PAY-2026-0002")
        self.add_payment_request(requester, status="Management approved", request_number="PAY-2026-0003")
        self.add_payment_request(other_user, status="Payment completed", request_number="PAY-2026-0004")
        self.add_billing_request(other_user, status="Invoice issued", request_number="INVOICE-2026-0001")

        response = client.get("/")
        body = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("You have 2 actions to complete in this menu.", body)
        self.assertIn('href="/finance-requests?tab=management_review">View actions in Management review</a>', body)
        self.assertNotIn("View action in Payment requests", body)
        self.assertNotIn("View action in Invoice requests", body)

    def test_dashboard_shows_pre_session_card_with_department_actions(self):
        session_record = ExamSession(
            exam_session_name="Unassigned recipient session",
            category="Path School",
            status="Pending",
            session_date=date(2026, 8, 20),
            shifts="Morning",
            modules="Speaking",
            format="Onsite",
        )
        db.session.add(session_record)
        db.session.commit()
        client = self.permission_client({"pre_session_control_tower": {"view": True}}, department="Management")

        response = client.get("/?session_year=2026")
        body = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("<h2>Pre onsite session control tower</h2>", body)
        self.assertIn("You have 1 action to complete in this menu.", body)
        self.assertIn('aria-label="Pre onsite session control tower counters"', body)
        self.assertIn('aria-label="Pre onsite session control tower department actions"', body)
        self.assertIn('href="/pre-session-control-tower?session_year=2026&amp;view=bundles"', body)
        self.assertIn(">View action in Pending bundles</a>", body)
        self.assertNotIn('href="/pre-session-control-tower?view=my-actions&amp;action_responsible=MANAGEMENT"', body)

    def test_dashboard_pre_session_count_ignores_sessions_without_visible_department_chip(self):
        session_record = ExamSession(
            exam_session_name="Finance action session",
            category="Path School",
            status="Pending",
            session_date=date(2026, 8, 21),
            shifts="Morning",
            modules="Speaking",
            format="Onsite",
        )
        db.session.add(session_record)
        db.session.commit()
        client = self.permission_client({"pre_session_control_tower": {"view": True}}, department="Finance")

        response = client.get("/?session_year=2026")
        body = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("Everything is up to date in this menu.", body)
        self.assertNotIn("action to complete in this menu.", body)

    def test_dashboard_pre_session_count_ignores_sessions_hidden_online_formats(self):
        session_record = ExamSession(
            exam_session_name="Hidden online session",
            category="Path School",
            status="Pending",
            session_date=date(2026, 8, 22),
            shifts="Morning",
            modules="Speaking",
            format="Online",
        )
        db.session.add(session_record)
        db.session.commit()
        client = self.permission_client({"pre_session_control_tower": {"view": True}}, department="Finance")

        response = client.get("/?session_year=2026")
        body = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("Everything is up to date in this menu.", body)
        self.assertNotIn("action to complete in this menu.", body)

    def test_dashboard_pre_session_action_links_match_visible_department_chip_count(self):
        session_record = ExamSession(
            exam_session_name="Pending bundle session",
            category="Path School",
            status="Pending",
            session_date=date(2026, 8, 23),
            shifts="Morning",
            modules="Speaking",
            format="Onsite",
        )
        db.session.add(session_record)
        db.session.commit()

        client = self.permission_client(
            {"pre_session_control_tower": {"view": True}},
            full_name="Manager Example",
            department="Management",
        )
        response = client.get("/?session_year=2026")
        body = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("You have 1 action to complete in this menu.", body)
        self.assertEqual(body.count('href="/pre-session-control-tower?session_year=2026&amp;view=bundles"'), 1)
        self.assertIn(">View action in Pending bundles</a>", body)
        self.assertNotIn("Go to menu", body)

    def test_dashboard_bundle_action_link_opens_bundles_list(self):
        session_record = ExamSession(
            exam_session_name="Bundle action session",
            category="Path School",
            status="Pending",
            session_date=date(2026, 8, 26),
            shifts="Morning",
            modules="Speaking",
            format="Onsite",
        )
        db.session.add(session_record)
        db.session.flush()
        bundle = ExamSessionShipmentBundle(
            supervisor_staff_id=1,
            delivery_address="Test address",
            courier="Correo Argentino",
            status="Preparing bundle",
            dispatch_due_at=date(2026, 8, 10),
            bundle_number="6-26",
        )
        db.session.add(bundle)
        db.session.flush()
        db.session.add_all([
            ExamSessionShipmentBundleSession(
                bundle_id=bundle.id,
                exam_session_id=session_record.id,
            ),
            ExamSessionSupervisorAssignment(
                exam_session_id=session_record.id,
                team_member_id=1,
                participation_status="Confirmed",
                is_shipment_recipient=True,
            ),
        ])
        db.session.commit()

        client = self.permission_client({"pre_session_control_tower": {"view": True}}, department="Admin")
        response = client.get("/?session_year=2026")
        body = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn(">View action in Bundle 6-26</a>", body)
        self.assertIn('href="/pre-session-control-tower?session_year=2026&amp;view=bundles"', body)
        self.assertNotIn(
            f'href="/pre-session-control-tower?session_year=2026&amp;view=bundle&amp;bundle_id={bundle.id}">View action in Bundle 6-26</a>',
            body,
        )

    def test_pre_session_my_actions_url_no_longer_renders_list(self):
        client = self.permission_client({"pre_session_control_tower": {"view": True}}, department="Management")

        response = client.get("/pre-session-control-tower?session_year=2026&view=my-actions&action_responsible=MANAGEMENT")
        body = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("Shipment bundles", body)
        self.assertNotIn("My actions summary", body)
        self.assertNotIn("My actions filters", body)
        self.assertNotIn("No pending actions for the selected year.", body)

    def test_dashboard_pre_session_card_counts_unread_mentions(self):
        client = self.permission_client({"pre_session_control_tower": {"view": True}}, department="Admin")
        user = User.query.filter_by(email="person@example.com").one()
        session_record = ExamSession(
            exam_session_name="Mentioned control tower session",
            category="Path School",
            status="Pending",
            session_date=date(2026, 8, 20),
            shifts="Morning",
            modules="Speaking",
            format="Onsite",
        )
        db.session.add(session_record)
        db.session.flush()
        workflow = ExamSessionScheduleWorkflow(exam_session_id=session_record.id, status="Not started")
        db.session.add(workflow)
        db.session.flush()
        bundle = ExamSessionShipmentBundle(
            supervisor_staff_id=1,
            delivery_address="Test address",
            courier="Correo Argentino",
            status="Preparing bundle",
            dispatch_due_at=date(2026, 8, 10),
        )
        db.session.add(bundle)
        db.session.flush()
        db.session.add(ExamSessionShipmentBundleSession(
            bundle_id=bundle.id,
            exam_session_id=session_record.id,
        ))
        db.session.add_all([
            ExamSessionScheduleNoteMention(
                note_id="schedule-note-1",
                workflow_id=workflow.id,
                to_user_id=user.id,
                to_full_name=user.full_name,
                comment_text="Please read the schedule note.",
                is_read=False,
                created_on=datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc),
            ),
            ExamSessionStaffingNoteMention(
                note_id="staffing-note-1",
                exam_session_id=session_record.id,
                to_user_id=user.id,
                to_full_name=user.full_name,
                comment_text="Please read the staffing note.",
                is_read=False,
                created_on=datetime(2026, 8, 1, 13, 0, tzinfo=timezone.utc),
            ),
            ExamSessionStaffingNoteMention(
                note_id="staffing-note-read",
                exam_session_id=session_record.id,
                to_user_id=user.id,
                to_full_name=user.full_name,
                comment_text="Already read.",
                is_read=True,
                created_on=datetime(2026, 8, 1, 14, 0, tzinfo=timezone.utc),
            ),
        ])
        db.session.commit()

        response = client.get("/?session_year=2026")
        body = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("You have been mentioned in 2 notes in this menu.", body)
        self.assertIn('<span class="dashboard-count-chip dashboard-count-chip-note">2 notes</span>', body)
        self.assertIn("View note in Mentioned control tower session", body)
        self.assertNotIn("View note in Bundle", body)
        self.assertIn("highlight_note=staffing-note-1", body)
        self.assertIn("view=bundle", body)
        self.assertIn(f"bundle_id={bundle.id}", body)
        self.assertIn(f"open_schedule_modal={session_record.id}", body)
        self.assertIn("open_modal_target=staffing-notes", body)
        self.assertIn("highlight_note=schedule-note-1", body)
        self.assertNotIn('href="/pre-session-control-tower?view=sessions&amp;mentions=1"', body)

    def test_dashboard_pre_session_shipment_note_link_opens_shipment_modal(self):
        client = self.permission_client({"pre_session_control_tower": {"view": True}}, department="Admin")
        user = User.query.filter_by(email="person@example.com").one()
        session_record = ExamSession(
            exam_session_name="Shipment note session",
            category="Path School",
            status="Pending",
            session_date=date(2026, 8, 24),
            shifts="Morning",
            modules="Speaking",
            format="Onsite",
        )
        db.session.add(session_record)
        db.session.flush()
        bundle = ExamSessionShipmentBundle(
            supervisor_staff_id=1,
            delivery_address="Test address",
            courier="Correo Argentino",
            status="Preparing bundle",
            dispatch_due_at=date(2026, 8, 10),
            bundle_number="4-26",
        )
        db.session.add(bundle)
        db.session.flush()
        db.session.add(ExamSessionShipmentBundleSession(
            bundle_id=bundle.id,
            exam_session_id=session_record.id,
        ))
        db.session.add(ExamSessionStaffingNoteMention(
            note_id="shipment-note-1",
            exam_session_id=session_record.id,
            note_context="shipments",
            to_user_id=user.id,
            to_full_name=user.full_name,
            comment_text="Please read the shipment note.",
            is_read=False,
            created_on=datetime(2026, 8, 2, 13, 0, tzinfo=timezone.utc),
        ))
        db.session.commit()

        response = client.get("/?session_year=2026")
        body = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn(">View note in Bundle 4-26</a>", body)
        self.assertIn("open_modal_target=shipments-notes", body)
        self.assertIn("shipments_only=1", body)
        self.assertIn("close_view=bundles", body)
        self.assertIn("highlight_note=shipment-note-1", body)
        self.assertNotIn("open_modal_target=staffing-notes", body)

    def test_dashboard_pre_session_package_note_link_uses_session_label(self):
        client = self.permission_client({"pre_session_control_tower": {"view": True}}, department="Admin")
        user = User.query.filter_by(email="person@example.com").one()
        session_record = ExamSession(
            exam_session_name="Package note session",
            category="Path School",
            status="Pending",
            session_date=date(2026, 8, 25),
            shifts="Morning",
            modules="Speaking",
            format="Onsite",
        )
        db.session.add(session_record)
        db.session.flush()
        bundle = ExamSessionShipmentBundle(
            supervisor_staff_id=1,
            delivery_address="Test address",
            courier="Correo Argentino",
            status="Preparing bundle",
            dispatch_due_at=date(2026, 8, 10),
            bundle_number="5-26",
        )
        db.session.add(bundle)
        db.session.flush()
        db.session.add(ExamSessionShipmentBundleSession(
            bundle_id=bundle.id,
            exam_session_id=session_record.id,
        ))
        db.session.add(ExamSessionStaffingNoteMention(
            note_id="package-note-1",
            exam_session_id=session_record.id,
            note_context="packages",
            to_user_id=user.id,
            to_full_name=user.full_name,
            comment_text="Please read the package note.",
            is_read=False,
            created_on=datetime(2026, 8, 2, 14, 0, tzinfo=timezone.utc),
        ))
        db.session.commit()

        response = client.get("/?session_year=2026")
        body = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn(">View note in Package note session</a>", body)
        self.assertNotIn(">View note in Bundle 5-26</a>", body)
        self.assertIn("open_modal_target=packages-notes", body)
        self.assertIn("packages_only=1", body)
        self.assertIn("highlight_note=package-note-1", body)

    def test_dashboard_hides_pre_session_card_without_permission(self):
        client = self.permission_client({"fees": {"view": True}})
        response = client.get("/")
        body = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("<h2>Pre onsite session control tower</h2>", body)

    def test_staff_members_table_moved_to_staff_members_route(self):
        response = self.client().get("/staff-members")
        body = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("Staff members | Path Examinations", body)
        self.assertIn("<h1>Staff members</h1>", body)
