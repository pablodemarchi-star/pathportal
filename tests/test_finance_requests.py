import os
import unittest
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from app import create_app, db
from app.models import (
    BillingRequest,
    BillingRequestEvent,
    FinanceClientContact,
    FinanceConcept,
    FinanceContact,
    PaymentRequest,
    PaymentRequestEvent,
    User,
    UserMenuPermission,
    VALID_MENU_PERMISSION_KEYS,
)
from app.routes import (
    finance_next_payment_run_date,
    reconcile_overdue_payment_requests,
    payment_calendar_groups,
    payment_is_delayed,
    payment_whatsapp_copy_contract,
)


class FinanceRequestsTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config["TESTING"] = True
        self.ctx = self.app.app_context()
        self.ctx.push()
        db.drop_all()
        db.create_all()
        self.concept = FinanceConcept(name="Accounting", applies_to="Both", is_active=True)
        db.session.add(self.concept)
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def create_user(self, email, department="Admissions", is_superadmin=False, view=True, edit=True):
        user = User(
            full_name=email.split("@")[0].title(),
            email=email,
            department=department,
            is_active=True,
            is_superadmin=is_superadmin,
            password_hash="hash",
        )
        db.session.add(user)
        db.session.flush()
        for menu_key in VALID_MENU_PERMISSION_KEYS:
            db.session.add(
                UserMenuPermission(
                    user_id=user.id,
                    menu_key=menu_key,
                    can_view=view if menu_key == "finance_requests" else False,
                    can_edit=edit if menu_key == "finance_requests" else False,
                )
            )
        db.session.commit()
        return user

    def client_for(self, user):
        client = self.app.test_client()
        with client.session_transaction() as user_session:
            user_session["user"] = user.full_name
            user_session["user_id"] = user.id
            user_session["user_full_name"] = user.full_name
            user_session["user_email"] = user.email
            user_session["user_department"] = user.department
            user_session["csrf_token"] = "token"
        return client

    def payment(self, requester, status="Submitted", scheduled_payment_date=None, is_archived=False):
        payment = PaymentRequest(
            request_number=f"PAY-2026-{PaymentRequest.query.count() + 1:04d}",
            requester_user_id=requester.id,
            requester_department=requester.department,
            description="Pay accounting service",
            concept_id=self.concept.id,
            concept_name_snapshot=self.concept.name,
            amount=Decimal("100.00"),
            currency="ARS",
            payment_method="Cash",
            status=status,
            scheduled_payment_date=scheduled_payment_date,
            is_archived=is_archived,
        )
        db.session.add(payment)
        db.session.commit()
        return payment

    def card_for(self, body, needle):
        needle_index = body.index(needle)
        start = body.rfind("<article", 0, needle_index)
        end = body.find("</article>", needle_index)
        self.assertNotEqual(start, -1)
        self.assertNotEqual(end, -1)
        return body[start : end + len("</article>")]

    def test_menu_exists_default_payment_requests_and_no_overview(self):
        user = self.create_user("requester@example.com")
        response = self.client_for(user).get("/finance-requests")
        body = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("Finance requests", body)
        self.assertIn("Payment requests", body)
        self.assertIn(">Show archived payments</a>", body)
        self.assertNotIn(">Show archived</a>", body)
        self.assertIn("finance-fixed-links", body)
        self.assertIn("finance-fixed-detail-link", body)
        self.assertLess(body.index("Payment requests</a>"), body.index("Path bank details</summary>"))
        self.assertLess(body.index("Path bank details</summary>"), body.index("Path invoicing details</summary>"))
        self.assertIn("finance-bank-details-menu", body)
        self.assertIn("PATH EXAMINATIONS BANK ACCOUNT DETAILS:", body)
        self.assertIn("DATOS DE LA CUENTA BANCARIA DE PATH EXAMINATIONS:", body)
        self.assertIn("<strong>Bank:</strong> Banco Galicia", body)
        self.assertIn("<strong>Entidad bancaria:</strong> Banco Galicia", body)
        self.assertIn("*PATH EXAMINATIONS BANK ACCOUNT DETAILS:*", body)
        self.assertIn("- *Bank:* Banco Galicia", body)
        self.assertIn("*DATOS DE LA CUENTA BANCARIA DE PATH EXAMINATIONS:*", body)
        self.assertIn("- *Entidad bancaria:* Banco Galicia", body)
        self.assertIn("DETAILS FOR ISSUING INVOICES TO PATH EXAMINATIONS:", body)
        self.assertIn("DATOS PARA EMITIR FACTURAS PARA PATH EXAMINATIONS:", body)
        self.assertIn("<strong>Registered company name:</strong> Bellis Ignis Group S.R.L.", body)
        self.assertIn("<strong>Razón social:</strong> Bellis Ignis Group S.R.L", body)
        self.assertIn("*DETAILS FOR ISSUING INVOICES TO PATH EXAMINATIONS:*", body)
        self.assertIn("- *VAT status:* Responsable Inscripto", body)
        self.assertIn("*DATOS PARA EMITIR FACTURAS PARA PATH EXAMINATIONS:*", body)
        self.assertIn("- *Condición frente al IVA:* Responsable Inscripto", body)
        self.assertNotIn(">Contacts<", body)
        self.assertNotIn(">Overview<", body)

    def test_finance_fixed_detail_links_use_plain_link_style(self):
        with open("app/static/css/styles.css", encoding="utf-8") as css_file:
            css = css_file.read()

        selector = ".finance-tabs .finance-fixed-detail-link"
        block = css[css.index(selector) : css.index("}", css.index(selector))]
        self.assertIn("border: 0;", block)
        self.assertIn("color: var(--path-blue-303up, #233a78);", block)
        self.assertIn("font-weight: 600;", block)
        self.assertIn("text-decoration: underline;", block)

    def test_finance_bank_details_dropdown_uses_small_right_aligned_menu(self):
        with open("app/static/css/styles.css", encoding="utf-8") as css_file:
            css = css_file.read()

        selector = ".finance-bank-details-menu"
        block = css[css.index(selector) : css.index("}", css.index(selector))]
        self.assertIn("position: absolute;", block)
        self.assertIn("right: 0;", block)
        self.assertIn("min-width: 330px;", block)

    def test_new_payment_request_button_only_shows_on_payment_requests_view(self):
        user = self.create_user("superadmin@example.com", is_superadmin=True)
        client = self.client_for(user)

        payment_body = client.get("/finance-requests?tab=payment_requests").get_data(as_text=True)
        finance_actions_body = client.get("/finance-requests?tab=finance_payments").get_data(as_text=True)
        invoice_body = client.get("/finance-requests?tab=billing_requests").get_data(as_text=True)
        management_body = client.get("/finance-requests?tab=management_review").get_data(as_text=True)
        concepts_body = client.get("/finance-requests?tab=concepts").get_data(as_text=True)

        self.assertIn('data-open-modal="new-payment-request-modal"', payment_body)
        self.assertIn('data-open-modal="new-payment-request-modal"', finance_actions_body)
        self.assertIn('name="source_tab" value="finance_payments"', finance_actions_body)
        self.assertIn('name="amount" inputmode="decimal" pattern="[0-9]+([.][0-9]+)?" value="" data-finance-amount required', payment_body)
        self.assertIn('name="amount" inputmode="decimal" pattern="[0-9]+([.][0-9]+)?" value="" data-finance-amount>', finance_actions_body)
        self.assertNotIn('data-open-modal="new-payment-request-modal"', invoice_body)
        self.assertNotIn('data-open-modal="new-payment-request-modal"', management_body)
        self.assertNotIn('data-open-modal="new-payment-request-modal"', concepts_body)

    def test_contacts_tab_redirects_to_default_payment_requests(self):
        user = self.create_user("requester@example.com")
        body = self.client_for(user).get("/finance-requests?tab=contacts").get_data(as_text=True)

        self.assertIn("Payment requests", body)
        self.assertNotIn(">Contacts<", body)
        self.assertNotIn("New contact", body)

    def test_calendar_tab_is_not_available_for_finance_users(self):
        user = self.create_user("finance@example.com", department="Finance")
        body = self.client_for(user).get("/finance-requests").get_data(as_text=True)

        self.assertIn("Finance actions", body)
        self.assertNotIn("Finance payments", body)
        self.assertNotIn(">Calendar<", body)
        self.assertNotIn("<h2>Calendar</h2>", body)

    def test_calendar_tab_request_falls_back_to_payment_requests(self):
        user = self.create_user("finance@example.com", department="Finance")
        body = self.client_for(user).get("/finance-requests?tab=calendar").get_data(as_text=True)

        self.assertIn("<h2>Payment requests</h2>", body)
        self.assertNotIn(">Calendar<", body)
        self.assertNotIn("<h2>Calendar</h2>", body)

    def test_concepts_view_renders_edit_controls_for_superadmin(self):
        user = self.create_user("admin@example.com", is_superadmin=True)
        db.session.add(FinanceConcept(name="Inactive concept", applies_to="Both", is_active=False))
        db.session.add(FinanceConcept(name="Invoice concept", applies_to="Billing", is_active=True))
        db.session.commit()

        body = self.client_for(user).get("/finance-requests?tab=concepts").get_data(as_text=True)

        self.assertIn("data-finance-concept-form", body)
        self.assertIn("data-finance-concept-create-button>Save concept", body)
        self.assertIn("data-finance-concept-save-button hidden>Save changes", body)
        self.assertIn("data-finance-concept-delete-button hidden>Delete concept", body)
        self.assertIn("data-edit-finance-concept", body)
        self.assertIn(f'data-concept-id="{self.concept.id}"', body)
        self.assertNotIn("Display order", body)
        self.assertIn('<span class="finance-status-chip status-inactive">Inactive</span>', body)
        self.assertIn('<option value="Billing">Invoice</option>', body)
        self.assertIn('<span class="finance-status-chip">Invoice</span>', body)

    def test_concepts_view_sorts_cards_alphabetically(self):
        user = self.create_user("admin@example.com", is_superadmin=True)
        db.session.add(FinanceConcept(name="Aardvark", applies_to="Both", display_order=999, is_active=True))
        db.session.add(FinanceConcept(name="Zulu", applies_to="Both", display_order=-1, is_active=True))
        db.session.commit()

        body = self.client_for(user).get("/finance-requests?tab=concepts").get_data(as_text=True)

        self.assertLess(body.index("Aardvark"), body.index("Accounting"))
        self.assertLess(body.index("Accounting"), body.index("Zulu"))

    def test_save_finance_concept_updates_existing_concept(self):
        user = self.create_user("admin@example.com", is_superadmin=True)

        response = self.client_for(user).post(
            "/finance-requests/concepts",
            data={
                "concept_id": str(self.concept.id),
                "name": "Updated Accounting",
                "description": "Updated description",
                "applies_to": "Payments",
                "is_active": "1",
            },
        )

        self.assertEqual(response.status_code, 302)
        concept = FinanceConcept.query.get(self.concept.id)
        self.assertEqual(concept.name, "Updated Accounting")
        self.assertEqual(concept.description, "Updated description")
        self.assertEqual(concept.applies_to, "Payments")

    def test_delete_finance_concept_removes_unused_concept(self):
        user = self.create_user("admin@example.com", is_superadmin=True)

        response = self.client_for(user).post(f"/finance-requests/concepts/{self.concept.id}/delete")

        self.assertEqual(response.status_code, 302)
        self.assertIsNone(FinanceConcept.query.get(self.concept.id))

    def test_delete_finance_concept_keeps_used_concept(self):
        user = self.create_user("admin@example.com", is_superadmin=True)
        self.payment(user)

        response = self.client_for(user).post(f"/finance-requests/concepts/{self.concept.id}/delete")

        self.assertEqual(response.status_code, 302)
        self.assertIsNotNone(FinanceConcept.query.get(self.concept.id))

    def test_payment_method_form_shows_conditional_field_hooks_and_no_echeque(self):
        user = self.create_user("requester@example.com")
        body = self.client_for(user).get("/finance-requests").get_data(as_text=True)

        self.assertIn('data-finance-payment-method', body)
        self.assertIn('data-finance-bank-fields', body)
        self.assertIn('data-finance-card-fields', body)
        self.assertIn("Already paid", body)
        self.assertIn("To be paid", body)
        self.assertNotIn("E-cheque", body)
        self.assertNotIn(">Other<", body)

    def test_payment_description_is_limited_to_card_two_line_length(self):
        user = self.create_user("requester@example.com")
        body = self.client_for(user).get("/finance-requests").get_data(as_text=True)
        self.assertIn('name="description" rows="3" maxlength="90"', body)

        response = self.client_for(user).post(
            "/finance-requests/payment-requests",
            data={
                "description": "x" * 91,
                "concept_id": str(self.concept.id),
                "currency": "ARS",
                "amount": "2500",
                "payment_method": "Cash",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn("open_staff_modal=new-payment-request-modal", response.headers["Location"])
        self.assertEqual(PaymentRequest.query.count(), 0)

    def test_payment_request_cards_use_wrapping_grid_and_latest_first(self):
        user = self.create_user("requester@example.com")
        first = self.payment(user)
        first.description = "First payment"
        second = self.payment(user)
        second.description = "Second payment"
        db.session.commit()

        body = self.client_for(user).get("/finance-requests").get_data(as_text=True)

        self.assertIn("finance-payment-request-grid", body)
        self.assertIn("finance-payment-requests-card", body)
        self.assertLess(body.index("Second payment"), body.index("First payment"))

    def test_management_review_cards_use_payment_request_card_grid(self):
        user = self.create_user("admin@example.com", is_superadmin=True)
        payment = self.payment(user, status="Submitted")
        resubmitted = self.payment(user, status="Resubmitted")

        body = self.client_for(user).get("/finance-requests?tab=management_review").get_data(as_text=True)

        self.assertIn("Management review", body)
        self.assertIn("finance-card-list finance-payment-request-grid", body)
        self.assertIn("finance-management-review-item", body)
        self.assertIn(payment.request_number, body)
        self.assertIn(resubmitted.request_number, body)
        self.assertIn("Payment details", body)
        self.assertIn(f'action="/finance-requests/payment-requests/{payment.id}/management"', body)
        self.assertIn('name="action" value="approve">Approve</button>', body)
        self.assertIn('data-management-review-comments', body)
        self.assertIn('name="action" value="needs_correction" data-requires-management-comment>Mark discrepancy</button>', body)
        self.assertIn('name="action" value="reject" data-requires-management-comment>Reject</button>', body)

    def test_submitted_payment_card_renders_edit_chip_and_modal(self):
        user = self.create_user("requester@example.com")
        payment = self.payment(user, status="Submitted")

        body = self.client_for(user).get("/finance-requests").get_data(as_text=True)

        self.assertIn(f'data-open-modal="edit-payment-request-{payment.id}"', body)
        self.assertIn("Edit payment request", body)
        self.assertIn("Save and close", body)
        self.assertIn("Delete request", body)
        self.assertIn("Are you sure you want to delete this payment request?", body)
        self.assertIn(f'action="/finance-requests/payment-requests/{payment.id}/edit"', body)
        self.assertIn(f'action="/finance-requests/payment-requests/{payment.id}/delete"', body)

    def test_needs_correction_payment_card_renders_edit_chip_and_modal(self):
        user = self.create_user("requester@example.com")
        payment = self.payment(user, status="Needs correction")

        body = self.client_for(user).get("/finance-requests").get_data(as_text=True)

        self.assertIn(f'data-open-modal="edit-payment-request-{payment.id}"', body)
        self.assertIn(">Update</button>", body)
        self.assertIn("Edit payment request", body)
        self.assertIn(">Resubmit</button>", body)
        self.assertIn(f'action="/finance-requests/payment-requests/{payment.id}/resubmit"', body)
        self.assertIn('name="tab" value="management_review"', body)
        self.assertNotIn("Save and close", body)
        self.assertNotIn(f'action="/finance-requests/payment-requests/{payment.id}/delete"', body)

    def test_resubmit_payment_request_sets_resubmitted_status_and_redirects_to_management_review(self):
        user = self.create_user("requester@example.com")
        payment = self.payment(user, status="Needs correction")

        response = self.client_for(user).post(
            f"/finance-requests/payment-requests/{payment.id}/resubmit",
            data={
                "description": payment.description,
                "concept_id": str(self.concept.id),
                "currency": payment.currency,
                "amount": str(payment.amount),
                "payment_method": payment.payment_method,
                "payment_date_mode": "asap",
                "tab": "management_review",
            },
        )

        db.session.refresh(payment)
        self.assertEqual(response.status_code, 302)
        self.assertIn("tab=management_review", response.headers["Location"])
        self.assertEqual(payment.status, "Resubmitted")

    def test_non_submitted_payment_card_does_not_render_edit_chip(self):
        user = self.create_user("requester@example.com")
        payment = self.payment(user, status="Management approved")

        body = self.client_for(user).get("/finance-requests").get_data(as_text=True)

        self.assertNotIn(f'data-open-modal="edit-payment-request-{payment.id}"', body)
        self.assertNotIn("Edit payment request", body)
        self.assertNotIn("Delete request", body)

    def test_management_approved_status_chip_displays_as_scheduled(self):
        user = self.create_user("requester@example.com")
        self.payment(user, status="Management approved")

        body = self.client_for(user).get("/finance-requests").get_data(as_text=True)

        self.assertIn('<span class="finance-status-chip status-management-approved">Scheduled</span>', body)
        self.assertNotIn(">Management approved</span>", body)

    def test_overdue_payment_requests_show_delayed_chip_without_changing_status(self):
        user = self.create_user("requester@example.com")
        scheduled = self.payment(user, status="Management approved", scheduled_payment_date=date.today() - timedelta(days=1))
        scheduled.description = "Overdue scheduled payment"
        processing = self.payment(user, status="Payment scheduled", scheduled_payment_date=date.today() - timedelta(days=2))
        processing.description = "Overdue processing payment"
        on_hold = self.payment(user, status="On hold", scheduled_payment_date=date.today() - timedelta(days=3))
        on_hold.description = "Overdue on hold payment"
        db.session.commit()

        body = self.client_for(user).get("/finance-requests?tab=payment_requests").get_data(as_text=True)

        scheduled_card = self.card_for(body, scheduled.description)
        self.assertIn('<span class="finance-status-chip status-management-approved">Scheduled</span>', scheduled_card)
        self.assertIn('<span class="finance-status-chip status-delayed">Delayed</span>', scheduled_card)
        processing_card = self.card_for(body, processing.description)
        self.assertIn('<span class="finance-status-chip status-payment-scheduled">Processing payment</span>', processing_card)
        self.assertIn('<span class="finance-status-chip status-delayed">Delayed</span>', processing_card)
        on_hold_card = self.card_for(body, on_hold.description)
        self.assertIn('<span class="finance-status-chip status-on-hold">On hold</span>', on_hold_card)
        self.assertIn('<span class="finance-status-chip status-delayed">Delayed</span>', on_hold_card)
        db.session.refresh(scheduled)
        db.session.refresh(processing)
        db.session.refresh(on_hold)
        self.assertEqual(scheduled.status, "Management approved")
        self.assertEqual(processing.status, "Payment scheduled")
        self.assertEqual(on_hold.status, "On hold")

    def test_finance_actions_shows_only_scheduled_cards_with_payment_request_grid(self):
        user = self.create_user("finance@example.com", department="Finance")
        scheduled = self.payment(user, status="Management approved", scheduled_payment_date=date.today())
        scheduled.description = "Scheduled payment"
        completed = self.payment(user, status="Payment completed")
        completed.description = "Completed payment"
        delayed = self.payment(user, status="Payment delayed")
        delayed.description = "Delayed payment"
        db.session.commit()

        body = self.client_for(user).get("/finance-requests?tab=finance_payments").get_data(as_text=True)

        self.assertIn("Finance actions", body)
        self.assertIn("finance-card-list finance-payment-request-grid", body)
        self.assertIn("Today (1)", body)
        self.assertIn("Tomorrow (0)", body)
        self.assertNotIn("Past", body)
        self.assertIn(scheduled.request_number, body)
        self.assertIn("Scheduled payment", body)
        self.assertIn('<span class="finance-status-chip status-management-approved">Scheduled</span>', body)
        self.assertIn("Payment proof", body)
        self.assertIn("data-payment-proof-input", body)
        self.assertIn("data-requires-payment-proof", body)
        self.assertIn("data-requires-empty-payment-proof", body)
        self.assertIn("Cancel payment", body)
        self.assertIn("Processing payment", body)
        self.assertIn("Complete payment", body)
        self.assertNotIn(completed.request_number, body)
        self.assertNotIn("Completed payment", body)
        self.assertNotIn(delayed.request_number, body)
        self.assertNotIn("Delayed payment", body)

    def test_finance_actions_created_payment_goes_to_pending_approval_filter_and_management_review(self):
        finance_user = self.create_user("finance@example.com", department="Finance")
        response = self.client_for(finance_user).post(
            "/finance-requests/payment-requests",
            data={
                "source_tab": "finance_payments",
                "description": "Finance-created pending payment",
                "concept_id": str(self.concept.id),
                "currency": "ARS",
                "amount": "2500",
                "payment_method": "Cash",
                "payment_date_mode": "specific",
                "scheduled_payment_date": (date.today() + timedelta(days=1)).strftime("%d/%m/%Y"),
            },
            follow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)
        payment = PaymentRequest.query.one()
        self.assertEqual(payment.status, "Pending approval")
        self.assertIn("finance_filter=pending_approval", response.request.path + "?" + response.request.query_string.decode())
        body = response.get_data(as_text=True)
        self.assertIn("Pending approval (1)", body)
        self.assertIn(payment.request_number, body)
        self.assertIn("Finance-created pending payment", body)
        self.assertIn('<span class="finance-status-chip status-pending-approval">Pending approval</span>', body)
        self.assertNotIn("Payment proof", self.card_for(body, "Finance-created pending payment"))

        superadmin = self.create_user("superadmin@example.com", is_superadmin=True)
        management_body = self.client_for(superadmin).get("/finance-requests?tab=management_review").get_data(as_text=True)
        self.assertIn(payment.request_number, management_body)
        self.assertIn("Finance-created pending payment", management_body)
        self.assertIn(f'action="/finance-requests/payment-requests/{payment.id}/management"', management_body)

    def test_finance_actions_can_create_pending_approval_payment_without_amount(self):
        finance_user = self.create_user("finance@example.com", department="Finance")
        response = self.client_for(finance_user).post(
            "/finance-requests/payment-requests",
            data={
                "source_tab": "finance_payments",
                "description": "Pending payment without amount",
                "concept_id": str(self.concept.id),
                "currency": "ARS",
                "amount": "",
                "payment_method": "Cash",
                "payment_date_mode": "specific",
                "scheduled_payment_date": (date.today() + timedelta(days=1)).strftime("%d/%m/%Y"),
            },
            follow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)
        payment = PaymentRequest.query.one()
        self.assertEqual(payment.status, "Pending approval")
        self.assertEqual(payment.amount, Decimal("0.00"))
        body = response.get_data(as_text=True)
        self.assertIn("Pending approval (1)", body)
        self.assertIn("Pending payment without amount", body)
        self.assertIn("Amount in ARS pending · Accounting · Cash", body)

    def test_management_review_pending_approval_without_amount_requires_set_amount_before_approval(self):
        finance_user = self.create_user("finance@example.com", department="Finance")
        superadmin = self.create_user("superadmin@example.com", is_superadmin=True)
        payment = self.payment(finance_user, status="Pending approval", scheduled_payment_date=date.today() + timedelta(days=1))
        payment.amount = Decimal("0.00")
        payment.currency = "USD"
        payment.description = "Pending approval without amount"
        db.session.commit()

        body = self.client_for(superadmin).get("/finance-requests?tab=management_review").get_data(as_text=True)
        card = self.card_for(body, "Pending approval without amount")

        self.assertIn("Amount in USD pending · Accounting · Cash", card)
        self.assertIn(f'data-open-modal="set-payment-amount-{payment.id}"', card)
        self.assertIn(">Set amount</button>", card)
        self.assertIn('name="action" value="approve" disabled aria-disabled="true"', body)
        self.assertIn(f'action="/finance-requests/payment-requests/{payment.id}/set-amount"', body)
        self.assertIn('<span class="finance-prefixed-input">', body)
        self.assertIn("<strong>USD</strong>", body)

        response = self.client_for(superadmin).post(
            f"/finance-requests/payment-requests/{payment.id}/management",
            data={
                "action": "approve",
                "scheduled_payment_date": (date.today() + timedelta(days=1)).isoformat(),
            },
            follow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)
        db.session.refresh(payment)
        self.assertEqual(payment.status, "Pending approval")
        self.assertIn("Amount must be set before approving this payment request.", response.get_data(as_text=True))

    def test_management_review_card_actions_are_fixed_to_card_bottom(self):
        with open("app/static/css/styles.css", encoding="utf-8") as css_file:
            css = css_file.read()

        card_selector = ".finance-management-review-item > .finance-request-card"
        card_block = css[css.index(card_selector) : css.index("}", css.index(card_selector))]
        actions_selector = ".finance-management-review-item > .finance-request-card > .finance-card-actions"
        actions_block = css[css.index(actions_selector) : css.index("}", css.index(actions_selector))]

        self.assertIn("position: relative;", card_block)
        self.assertIn("padding-bottom: calc(46px + 2mm);", card_block)
        self.assertIn("position: absolute;", actions_block)
        self.assertIn("bottom: 14px;", actions_block)

    def test_management_review_set_amount_enables_pending_approval_approval(self):
        finance_user = self.create_user("finance@example.com", department="Finance")
        superadmin = self.create_user("superadmin@example.com", is_superadmin=True)
        payment = self.payment(finance_user, status="Pending approval", scheduled_payment_date=date.today() + timedelta(days=1))
        payment.amount = Decimal("0.00")
        payment.description = "Pending approval amount to set"
        db.session.commit()

        response = self.client_for(superadmin).post(
            f"/finance-requests/payment-requests/{payment.id}/set-amount",
            data={"amount": "3500,50"},
            follow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)
        db.session.refresh(payment)
        self.assertEqual(payment.amount, Decimal("3500.50"))
        body = response.get_data(as_text=True)
        self.assertNotIn(f'data-open-modal="set-payment-amount-{payment.id}"', body)
        self.assertIn("ARS 3500.50 · Accounting · Cash", body)
        self.assertIn('name="action" value="approve">Approve</button>', body)

    def test_payment_requests_still_require_amount(self):
        user = self.create_user("requester@example.com")
        response = self.client_for(user).post(
            "/finance-requests/payment-requests",
            data={
                "source_tab": "payment_requests",
                "description": "Payment without amount",
                "concept_id": str(self.concept.id),
                "currency": "ARS",
                "amount": "",
                "payment_method": "Cash",
            },
            follow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(PaymentRequest.query.count(), 0)
        self.assertIn("Amount must be a valid number.", response.get_data(as_text=True))

    def test_management_approval_moves_pending_approval_payment_to_scheduled_finance_filter(self):
        finance_user = self.create_user("finance@example.com", department="Finance")
        superadmin = self.create_user("superadmin@example.com", is_superadmin=True)
        tomorrow = date.today() + timedelta(days=1)
        payment = self.payment(finance_user, status="Pending approval", scheduled_payment_date=tomorrow)
        payment.description = "Pending payment to approve"
        db.session.commit()

        response = self.client_for(superadmin).post(
            f"/finance-requests/payment-requests/{payment.id}/management",
            data={
                "action": "approve",
                "scheduled_payment_date": tomorrow.isoformat(),
            },
            follow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)
        db.session.refresh(payment)
        self.assertEqual(payment.status, "Management approved")
        finance_body = self.client_for(finance_user).get("/finance-requests?tab=finance_payments&finance_filter=tomorrow").get_data(as_text=True)
        self.assertIn(payment.request_number, finance_body)
        self.assertIn("Pending payment to approve", finance_body)
        self.assertIn("Tomorrow (1)", finance_body)
        self.assertNotIn("Pending approval (", finance_body)
        self.assertIn('<span class="finance-status-chip status-management-approved">Scheduled</span>', finance_body)

    def test_management_rejection_moves_pending_approval_payment_to_finance_archived_payments(self):
        finance_user = self.create_user("finance@example.com", department="Finance")
        superadmin = self.create_user("superadmin@example.com", is_superadmin=True)
        payment = self.payment(finance_user, status="Pending approval", scheduled_payment_date=date.today())
        payment.description = "Pending payment to reject"
        db.session.commit()

        response = self.client_for(superadmin).post(
            f"/finance-requests/payment-requests/{payment.id}/management",
            data={
                "action": "reject",
                "scheduled_payment_date": date.today().isoformat(),
                "management_comments": "Not approved",
            },
            follow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)
        db.session.refresh(payment)
        self.assertEqual(payment.status, "Rejected")
        finance_body = self.client_for(finance_user).get("/finance-requests?tab=finance_payments&show_archived=1").get_data(as_text=True)
        self.assertIn("Archived finance actions", finance_body)
        self.assertIn(payment.request_number, finance_body)
        self.assertIn("Pending payment to reject", finance_body)
        self.assertIn('<span class="finance-status-chip status-rejected">Rejected</span>', finance_body)

    def test_finance_actions_today_shows_invoice_request_cards(self):
        user = self.create_user("finance@example.com", department="Finance")
        billing = BillingRequest(
            request_number="INVOICE-2026-0001",
            requester_user_id=user.id,
            requester_department=user.department,
            client_name_snapshot="Client SA",
            concept_id=self.concept.id,
            concept_name_snapshot=self.concept.name,
            description=self.concept.name,
            currency="ARS",
            amount=Decimal("7609990.00"),
            client_tax_id="30-12345678-9",
            vat_status_invoice_type="Consumidor Final (factura B)",
            status="Requested",
        )
        db.session.add(billing)
        db.session.commit()

        today_body = self.client_for(user).get("/finance-requests?tab=finance_payments").get_data(as_text=True)
        tomorrow_body = self.client_for(user).get("/finance-requests?tab=finance_payments&finance_filter=tomorrow").get_data(as_text=True)

        self.assertIn("Today (1)", today_body)
        self.assertIn("Tomorrow (0)", today_body)
        self.assertLess(today_body.index("Show archived invoices"), today_body.index(">Show archived payments</a>"))
        self.assertIn("INVOICE-2026-0001", today_body)
        self.assertIn("<h3>Client: Client SA</h3>", today_body)
        self.assertIn("<summary>Invoice details</summary>", today_body)
        self.assertIn('<span class="copy-icon copy-language-label">EN</span>', today_body)
        self.assertIn('<span class="copy-icon copy-language-label">SP</span>', today_body)
        self.assertIn("Invoice WhatsApp message copied.", today_body)
        self.assertIn("Mensaje de WhatsApp de la factura copiado.", today_body)
        self.assertIn("The invoice for *Client SA* was updated to *Requested*", today_body)
        self.assertIn("La factura para *Client SA* fue actualizada a *Solicitada*", today_body)
        self.assertNotIn(f'data-open-modal="edit-billing-request-{billing.id}"', today_body)
        self.assertIn(f'action="/finance-requests/billing-requests/{billing.id}/finance"', today_body)
        self.assertIn("Invoice proof", today_body)
        self.assertIn('name="invoice_link"', today_body)
        self.assertIn('name="status" value="Invoice cancelled"', today_body)
        self.assertIn(">Cancel invoice</button>", today_body)
        self.assertIn("data-requires-empty-payment-proof", today_body)
        self.assertIn('name="status" value="Processing invoice"', today_body)
        self.assertIn(">Processing invoice</button>", today_body)
        self.assertIn('name="status" value="Invoice issued"', today_body)
        self.assertIn(">Issue invoice</button>", today_body)
        self.assertNotIn("No finance actions to process.", today_body)
        self.assertNotIn("INVOICE-2026-0001", tomorrow_body)

    def test_finance_actions_issue_invoice_requires_invoice_proof(self):
        user = self.create_user("finance@example.com", department="Finance")
        billing = BillingRequest(
            request_number="INVOICE-2026-0001",
            requester_user_id=user.id,
            requester_department=user.department,
            client_name_snapshot="Client SA",
            concept_id=self.concept.id,
            concept_name_snapshot=self.concept.name,
            description=self.concept.name,
            currency="ARS",
            amount=Decimal("7609990.00"),
            client_tax_id="30-12345678-9",
            vat_status_invoice_type="Consumidor Final (factura B)",
            status="Requested",
        )
        db.session.add(billing)
        db.session.commit()

        response = self.client_for(user).post(
            f"/finance-requests/billing-requests/{billing.id}/finance",
            data={"status": "Invoice issued", "finance_filter": "today"},
            follow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)
        db.session.refresh(billing)
        self.assertEqual(billing.status, "Requested")
        self.assertEqual(billing.invoice_link, None)
        self.assertIn("Invoice proof is required to issue an invoice.", response.get_data(as_text=True))

    def test_finance_actions_issue_invoice_saves_invoice_link(self):
        user = self.create_user("finance@example.com", department="Finance")
        billing = BillingRequest(
            request_number="INVOICE-2026-0001",
            requester_user_id=user.id,
            requester_department=user.department,
            client_name_snapshot="Client SA",
            concept_id=self.concept.id,
            concept_name_snapshot=self.concept.name,
            description=self.concept.name,
            currency="ARS",
            amount=Decimal("7609990.00"),
            client_tax_id="30-12345678-9",
            vat_status_invoice_type="Consumidor Final (factura B)",
            status="Requested",
        )
        db.session.add(billing)
        db.session.commit()

        response = self.client_for(user).post(
            f"/finance-requests/billing-requests/{billing.id}/finance",
            data={
                "status": "Invoice issued",
                "invoice_link": "https://example.com/invoice-proof",
                "finance_filter": "today",
            },
            follow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)
        db.session.refresh(billing)
        self.assertEqual(billing.status, "Invoice issued")
        self.assertEqual(billing.invoice_link, "https://example.com/invoice-proof")
        body = response.get_data(as_text=True)
        self.assertIn("Archived invoice actions", body)
        self.assertIn("Invoice no.", body)
        self.assertIn("Invoice proof", body)
        self.assertNotIn("<th>Description</th>", body)
        self.assertIn("INVOICE-2026-0001", body)
        self.assertIn('<span class="finance-status-chip status-invoice-issued">Invoice issued</span>', body)

        active_body = self.client_for(user).get("/finance-requests?tab=finance_payments").get_data(as_text=True)
        self.assertNotIn("INVOICE-2026-0001", active_body)

        archived_invoice_body = self.client_for(user).get("/finance-requests?tab=finance_payments&show_archived_invoices=1").get_data(as_text=True)
        self.assertIn("INVOICE-2026-0001", archived_invoice_body)
        self.assertIn('href="https://example.com/invoice-proof"', archived_invoice_body)

    def test_finance_actions_cancel_invoice_requires_empty_invoice_proof(self):
        user = self.create_user("finance@example.com", department="Finance")
        billing = BillingRequest(
            request_number="INVOICE-2026-0001",
            requester_user_id=user.id,
            requester_department=user.department,
            client_name_snapshot="Client SA",
            concept_id=self.concept.id,
            concept_name_snapshot=self.concept.name,
            description=self.concept.name,
            currency="ARS",
            amount=Decimal("7609990.00"),
            client_tax_id="30-12345678-9",
            vat_status_invoice_type="Consumidor Final (factura B)",
            status="Requested",
        )
        db.session.add(billing)
        db.session.commit()

        response = self.client_for(user).post(
            f"/finance-requests/billing-requests/{billing.id}/finance",
            data={
                "status": "Invoice cancelled",
                "invoice_link": "https://example.com/invoice-proof",
                "finance_filter": "today",
            },
            follow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)
        db.session.refresh(billing)
        self.assertEqual(billing.status, "Requested")
        self.assertIn("Invoice proof must be empty to cancel or process an invoice.", response.get_data(as_text=True))

    def test_finance_actions_cancel_invoice_moves_request_to_archived_invoices(self):
        user = self.create_user("finance@example.com", department="Finance")
        billing = BillingRequest(
            request_number="INVOICE-2026-0001",
            requester_user_id=user.id,
            requester_department=user.department,
            client_name_snapshot="Client SA",
            concept_id=self.concept.id,
            concept_name_snapshot=self.concept.name,
            description=self.concept.name,
            currency="ARS",
            amount=Decimal("7609990.00"),
            client_tax_id="30-12345678-9",
            vat_status_invoice_type="Consumidor Final (factura B)",
            status="Requested",
        )
        db.session.add(billing)
        db.session.commit()

        response = self.client_for(user).post(
            f"/finance-requests/billing-requests/{billing.id}/finance",
            data={"status": "Invoice cancelled", "finance_filter": "today"},
            follow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)
        db.session.refresh(billing)
        self.assertEqual(billing.status, "Invoice cancelled")
        body = response.get_data(as_text=True)
        self.assertIn("Archived invoice actions", body)
        self.assertIn("INVOICE-2026-0001", body)
        self.assertIn('<span class="finance-status-chip status-invoice-cancelled">Invoice cancelled</span>', body)

        active_body = self.client_for(user).get("/finance-requests?tab=finance_payments").get_data(as_text=True)
        self.assertNotIn("INVOICE-2026-0001", active_body)

    def test_archived_invoice_actions_can_be_sorted_by_configured_columns(self):
        user = self.create_user("finance@example.com", department="Finance")
        zeta = BillingRequest(
            request_number="INVOICE-2026-0002",
            requester_user_id=user.id,
            requester_department=user.department,
            client_name_snapshot="Zeta Client",
            concept_id=self.concept.id,
            concept_name_snapshot="Training",
            description="Zeta invoice",
            currency="ARS",
            amount=Decimal("200.00"),
            client_tax_id="30-22222222-2",
            vat_status_invoice_type="Consumidor Final (factura B)",
            status="Invoice cancelled",
        )
        alpha = BillingRequest(
            request_number="INVOICE-2026-0001",
            requester_user_id=user.id,
            requester_department=user.department,
            client_name_snapshot="Alpha Client",
            concept_id=self.concept.id,
            concept_name_snapshot=self.concept.name,
            description="Alpha invoice",
            currency="ARS",
            amount=Decimal("100.00"),
            client_tax_id="30-11111111-1",
            vat_status_invoice_type="Consumidor Final (factura B)",
            status="Invoice issued",
            invoice_link="https://example.com/invoice",
        )
        db.session.add_all([zeta, alpha])
        db.session.commit()

        body = self.client_for(user).get(
            "/finance-requests?tab=finance_payments&show_archived_invoices=1&sort=client&dir=asc"
        ).get_data(as_text=True)

        self.assertIn("Archived invoice actions", body)
        for column in ("invoice_no", "final_date", "status", "client", "concept"):
            self.assertIn(f"sort={column}", body)
        self.assertIn('class="table-sort is-active"', body)
        self.assertIn("show_archived_invoices=1", body)
        self.assertLess(body.index("Alpha Client"), body.index("Zeta Client"))

    def test_finance_actions_processing_invoice_sets_status_with_empty_invoice_proof(self):
        user = self.create_user("finance@example.com", department="Finance")
        billing = BillingRequest(
            request_number="INVOICE-2026-0001",
            requester_user_id=user.id,
            requester_department=user.department,
            client_name_snapshot="Client SA",
            concept_id=self.concept.id,
            concept_name_snapshot=self.concept.name,
            description=self.concept.name,
            currency="ARS",
            amount=Decimal("7609990.00"),
            client_tax_id="30-12345678-9",
            vat_status_invoice_type="Consumidor Final (factura B)",
            status="Requested",
        )
        db.session.add(billing)
        db.session.commit()

        response = self.client_for(user).post(
            f"/finance-requests/billing-requests/{billing.id}/finance",
            data={"status": "Processing invoice", "finance_filter": "today"},
            follow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)
        db.session.refresh(billing)
        self.assertEqual(billing.status, "Processing invoice")
        self.assertEqual(billing.invoice_link, "")

    def test_overdue_scheduled_and_processing_payments_stay_in_today_finance_actions(self):
        user = self.create_user("finance@example.com", department="Finance")
        scheduled = self.payment(user, status="Management approved", scheduled_payment_date=date.today() - timedelta(days=1))
        scheduled.description = "Overdue scheduled finance action"
        processing = self.payment(user, status="Payment scheduled", scheduled_payment_date=date.today() - timedelta(days=2))
        processing.description = "Overdue processing finance action"
        db.session.commit()

        body = self.client_for(user).get("/finance-requests?tab=finance_payments").get_data(as_text=True)

        self.assertIn("Today (2)", body)
        self.assertIn(scheduled.request_number, body)
        self.assertIn(processing.request_number, body)
        self.assertIn('<span class="finance-status-chip status-delayed">Delayed</span>', self.card_for(body, scheduled.description))
        self.assertIn('<span class="finance-status-chip status-delayed">Delayed</span>', self.card_for(body, processing.description))
        self.assertNotIn("Tomorrow (2)", body)

    def test_finance_actions_processing_payment_keeps_request_in_finance_actions(self):
        user = self.create_user("finance@example.com", department="Finance")
        payment = self.payment(user, status="Management approved", scheduled_payment_date=date.today())

        response = self.client_for(user).post(
            f"/finance-requests/payment-requests/{payment.id}/finance",
            data={
                "status": "Payment scheduled",
                "scheduled_payment_date": date.today().isoformat(),
                "finance_filter": "today",
            },
            follow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)
        db.session.refresh(payment)
        self.assertEqual(payment.status, "Payment scheduled")
        body = response.get_data(as_text=True)
        self.assertIn(payment.request_number, body)
        self.assertIn('<span class="finance-status-chip status-payment-scheduled">Processing payment</span>', body)
        self.assertIn("Processing payment", body)
        self.assertIn('value="Payment scheduled" disabled aria-disabled="true"', body)

    def test_finance_actions_processing_payment_preserves_current_filter(self):
        user = self.create_user("finance@example.com", department="Finance")
        future_date = date.today() + timedelta(days=14)
        payment = self.payment(user, status="Management approved", scheduled_payment_date=future_date)
        filter_key = f"date:{future_date.isoformat()}"

        response = self.client_for(user).post(
            f"/finance-requests/payment-requests/{payment.id}/finance",
            data={
                "status": "Payment scheduled",
                "scheduled_payment_date": future_date.isoformat(),
                "finance_filter": filter_key,
            },
            follow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)
        db.session.refresh(payment)
        self.assertEqual(payment.status, "Payment scheduled")
        body = response.get_data(as_text=True)
        self.assertIn(payment.request_number, body)
        self.assertIn(future_date.strftime("%d/%m/%Y"), body)
        self.assertIn('<span class="finance-status-chip status-payment-scheduled">Processing payment</span>', body)

    def test_scheduled_payment_request_card_shows_put_on_hold_button(self):
        user = self.create_user("finance@example.com", department="Finance")
        payment = self.payment(user, status="Management approved", scheduled_payment_date=date.today())

        body = self.client_for(user).get("/finance-requests?tab=payment_requests").get_data(as_text=True)

        self.assertIn(payment.request_number, body)
        self.assertIn("Put on hold", body)
        self.assertIn("Are you sure you want to put this payment on hold?", body)

    def test_superadmin_sees_payment_request_buttons_for_all_cards(self):
        requester = self.create_user("requester@example.com", department="Admissions")
        superadmin = self.create_user("superadmin@example.com", department="Admin", is_superadmin=True)
        submitted = self.payment(requester, status="Submitted")
        submitted.description = "Submitted by someone else"
        scheduled = self.payment(requester, status="Management approved", scheduled_payment_date=date.today())
        scheduled.description = "Scheduled by someone else"
        on_hold = self.payment(requester, status="On hold", scheduled_payment_date=date.today())
        on_hold.description = "On hold by someone else"
        completed = self.payment(requester, status="Payment completed")
        completed.description = "Completed by someone else"
        db.session.commit()

        body = self.client_for(superadmin).get("/finance-requests?tab=payment_requests").get_data(as_text=True)

        self.assertIn(f'data-open-modal="edit-payment-request-{submitted.id}"', self.card_for(body, submitted.description))
        self.assertIn("Put on hold", self.card_for(body, scheduled.description))
        on_hold_card = self.card_for(body, on_hold.description)
        self.assertIn(">Release</button>", on_hold_card)
        self.assertIn(">Cancel</button>", on_hold_card)
        self.assertIn(">Archive</button>", self.card_for(body, completed.description))

    def test_management_sees_payment_request_buttons_except_superadmin_only(self):
        requester = self.create_user("requester@example.com", department="Admissions")
        management = self.create_user("management@example.com", department="Management")
        standard = self.payment(requester, status="Submitted")
        standard.description = "Standard payment visible to management"
        restricted = self.payment(requester, status="Submitted")
        restricted.description = "Restricted payment visible to management"
        restricted.visibility_mode = "Restricted"
        superadmin_only = self.payment(requester, status="Submitted")
        superadmin_only.description = "Superadmin only payment hidden from management"
        superadmin_only.visibility_mode = "Superadmin only"
        db.session.commit()

        body = self.client_for(management).get("/finance-requests?tab=payment_requests").get_data(as_text=True)

        self.assertIn(f'data-open-modal="edit-payment-request-{standard.id}"', self.card_for(body, standard.description))
        self.assertIn(f'data-open-modal="edit-payment-request-{restricted.id}"', self.card_for(body, restricted.description))
        self.assertNotIn(superadmin_only.description, body)

    def test_operational_users_only_see_payment_request_buttons_on_their_cards(self):
        owner = self.create_user("finance@example.com", department="Finance")
        other_requester = self.create_user("other@example.com", department="Admissions")
        own_payment = self.payment(owner, status="Management approved", scheduled_payment_date=date.today())
        own_payment.description = "Own scheduled payment"
        other_payment = self.payment(other_requester, status="Management approved", scheduled_payment_date=date.today())
        other_payment.description = "Other scheduled payment"
        db.session.commit()

        body = self.client_for(owner).get("/finance-requests?tab=payment_requests").get_data(as_text=True)

        self.assertIn("Put on hold", self.card_for(body, own_payment.description))
        self.assertNotIn("Put on hold", self.card_for(body, other_payment.description))

    def test_putting_scheduled_payment_on_hold_removes_it_from_finance_actions(self):
        user = self.create_user("finance@example.com", department="Finance")
        payment = self.payment(user, status="Management approved", scheduled_payment_date=date.today())

        response = self.client_for(user).post(
            f"/finance-requests/payment-requests/{payment.id}/hold",
            data={"tab": "payment_requests"},
            follow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)
        db.session.refresh(payment)
        self.assertEqual(payment.status, "On hold")

        finance_body = self.client_for(user).get("/finance-requests?tab=finance_payments").get_data(as_text=True)
        self.assertNotIn(payment.request_number, finance_body)

    def test_finance_actions_complete_payment_moves_request_to_finance_archived(self):
        user = self.create_user("finance@example.com", department="Finance")
        payment = self.payment(user, status="Management approved", scheduled_payment_date=date.today())
        payment.description = "Ready to complete"
        db.session.commit()

        response = self.client_for(user).post(
            f"/finance-requests/payment-requests/{payment.id}/finance",
            data={
                "status": "Payment completed",
                "scheduled_payment_date": date.today().isoformat(),
                "payment_proof_url": "https://example.com/payment-proof",
            },
            follow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)
        db.session.refresh(payment)
        self.assertEqual(payment.status, "Payment completed")
        self.assertEqual(payment.payment_proof_url, "https://example.com/payment-proof")
        self.assertIsNotNone(payment.payment_completed_at)
        self.assertFalse(payment.is_archived)
        body = response.get_data(as_text=True)
        self.assertIn("Archived finance actions", body)
        self.assertIn("Payment no.", body)
        self.assertIn("Full info", body)
        self.assertIn(payment.request_number, body)
        self.assertIn("Ready to complete", body)
        self.assertIn('<span class="finance-status-chip status-payment-completed">Payment completed</span>', body)

        payment_requests_body = self.client_for(user).get("/finance-requests?tab=payment_requests").get_data(as_text=True)
        self.assertIn(payment.request_number, payment_requests_body)
        self.assertIn("Ready to complete", payment_requests_body)
        self.assertIn(">Archive</button>", payment_requests_body)

        archived_payment_requests_body = self.client_for(user).get("/finance-requests?tab=payment_requests&show_archived=1").get_data(as_text=True)
        self.assertNotIn(payment.request_number, archived_payment_requests_body)

    def test_finance_actions_complete_payment_requires_payment_proof(self):
        user = self.create_user("finance@example.com", department="Finance")
        payment = self.payment(user, status="Management approved", scheduled_payment_date=date.today())

        response = self.client_for(user).post(
            f"/finance-requests/payment-requests/{payment.id}/finance",
            data={
                "status": "Payment completed",
                "scheduled_payment_date": date.today().isoformat(),
                "finance_filter": "today",
            },
            follow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)
        db.session.refresh(payment)
        self.assertEqual(payment.status, "Management approved")
        self.assertIsNone(payment.payment_completed_at)
        self.assertIn("Payment proof is required to complete a payment.", response.get_data(as_text=True))

    def test_finance_actions_cancel_payment_does_not_require_payment_proof(self):
        user = self.create_user("finance@example.com", department="Finance")
        payment = self.payment(user, status="Management approved", scheduled_payment_date=date.today())

        response = self.client_for(user).post(
            f"/finance-requests/payment-requests/{payment.id}/finance",
            data={
                "status": "Payment cancelled",
                "scheduled_payment_date": date.today().isoformat(),
            },
            follow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)
        db.session.refresh(payment)
        self.assertEqual(payment.status, "Payment cancelled")
        self.assertEqual(payment.payment_proof_url, "")
        self.assertFalse(payment.is_archived)
        body = response.get_data(as_text=True)
        self.assertIn("Archived finance actions", body)
        self.assertIn(payment.request_number, body)
        self.assertIn('<span class="finance-status-chip status-payment-cancelled">Payment cancelled</span>', body)

        payment_requests_body = self.client_for(user).get("/finance-requests?tab=payment_requests").get_data(as_text=True)
        self.assertIn(payment.request_number, payment_requests_body)
        self.assertIn(">Archive</button>", payment_requests_body)

    def test_finance_actions_cancel_payment_requires_empty_payment_proof(self):
        user = self.create_user("finance@example.com", department="Finance")
        payment = self.payment(user, status="Management approved", scheduled_payment_date=date.today())

        response = self.client_for(user).post(
            f"/finance-requests/payment-requests/{payment.id}/finance",
            data={
                "status": "Payment cancelled",
                "scheduled_payment_date": date.today().isoformat(),
                "payment_proof_url": "https://example.com/payment-proof",
                "finance_filter": "today",
            },
            follow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)
        db.session.refresh(payment)
        self.assertEqual(payment.status, "Management approved")
        self.assertFalse(payment.payment_proof_url)
        self.assertIn("Payment proof must be empty to cancel or process a payment.", response.get_data(as_text=True))

    def test_finance_actions_processing_payment_requires_empty_payment_proof(self):
        user = self.create_user("finance@example.com", department="Finance")
        payment = self.payment(user, status="Management approved", scheduled_payment_date=date.today())

        response = self.client_for(user).post(
            f"/finance-requests/payment-requests/{payment.id}/finance",
            data={
                "status": "Payment scheduled",
                "scheduled_payment_date": date.today().isoformat(),
                "payment_proof_url": "https://example.com/payment-proof",
                "finance_filter": "today",
            },
            follow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)
        db.session.refresh(payment)
        self.assertEqual(payment.status, "Management approved")
        self.assertFalse(payment.payment_proof_url)
        self.assertIn("Payment proof must be empty to cancel or process a payment.", response.get_data(as_text=True))

    def test_finance_actions_builds_future_date_filters(self):
        user = self.create_user("finance@example.com", department="Finance")
        future_date = date.today() + timedelta(days=28)
        future = self.payment(user, status="Management approved", scheduled_payment_date=future_date)
        future.description = "Future scheduled payment"
        tomorrow = self.payment(user, status="Management approved", scheduled_payment_date=date.today() + timedelta(days=1))
        tomorrow.description = "Tomorrow scheduled payment"
        db.session.commit()

        body = self.client_for(user).get("/finance-requests?tab=finance_payments").get_data(as_text=True)

        self.assertIn("Today (0)", body)
        self.assertIn("Tomorrow (1)", body)
        self.assertIn(f"{future_date.strftime('%d/%m/%Y')} (1)", body)
        self.assertNotIn(future.request_number, body)

        body = self.client_for(user).get(
            f"/finance-requests?tab=finance_payments&finance_filter=date:{future_date.isoformat()}"
        ).get_data(as_text=True)

        self.assertIn(future.request_number, body)
        self.assertIn("Future scheduled payment", body)
        self.assertNotIn(tomorrow.request_number, body)

    def test_delete_submitted_payment_request_removes_request(self):
        user = self.create_user("requester@example.com")
        payment = self.payment(user, status="Submitted")

        response = self.client_for(user).post(f"/finance-requests/payment-requests/{payment.id}/delete")

        self.assertEqual(response.status_code, 302)
        self.assertIsNone(PaymentRequest.query.get(payment.id))

    def test_delete_non_submitted_payment_request_is_forbidden(self):
        user = self.create_user("requester@example.com")
        payment = self.payment(user, status="Management approved")

        response = self.client_for(user).post(f"/finance-requests/payment-requests/{payment.id}/delete")

        self.assertEqual(response.status_code, 403)
        self.assertIsNotNone(PaymentRequest.query.get(payment.id))

    def test_payment_request_card_shows_created_datetime_as_requested(self):
        user = self.create_user("requester@example.com")
        payment = self.payment(user)
        payment.created_on = datetime(2026, 8, 15, 15, 30, tzinfo=timezone.utc)
        db.session.commit()

        body = self.client_for(user).get("/finance-requests").get_data(as_text=True)

        self.assertIn("Requested: 15/08/2026 · 12:30 pm", body)
        self.assertIn(f"Requester: {user.full_name} · {user.department}", body)
        self.assertIn("Completed: not yet", body)
        self.assertIn("Receipt: not yet", body)
        self.assertNotIn("Requested: Not set", body)

    def test_payment_request_cards_hide_optional_panels_without_content(self):
        user = self.create_user("requester@example.com")
        self.payment(user)

        body = self.client_for(user).get("/finance-requests").get_data(as_text=True)

        self.assertNotIn("<summary>Supporting documents</summary>", body)
        self.assertNotIn("Details and actions", body)
        self.assertIn("<summary>Payment details</summary>", body)
        self.assertNotIn("<summary>Comments", body)
        self.assertIn("<summary>Status track</summary>", body)
        self.assertNotIn("Edit request", body)
        self.assertNotIn("Save finance update", body)

    def test_payment_request_card_details_precedes_supporting_documents_and_shows_bank_data(self):
        user = self.create_user("requester@example.com")
        payment = self.payment(user)
        payment.payment_method = "Bank transfer"
        payment.supporting_documentation_url = "https://example.com/supporting-doc"
        payment.bank_details_snapshot = (
            '{"account_holder": "Provider SA", "account_number": "000123", '
            '"alias": "provider.path", "tax_id": "20-12345678-9"}'
        )
        db.session.commit()

        body = self.client_for(user).get("/finance-requests").get_data(as_text=True)
        details_panel = body[
            body.index("<summary>Payment details</summary>") : body.index("<summary>Supporting documents</summary>")
        ]

        self.assertLess(body.index("<summary>Payment details</summary>"), body.index("<summary>Supporting documents</summary>"))
        self.assertIn("<strong>Payment method:</strong> Bank transfer", details_panel)
        self.assertIn("<strong>Account holder:</strong> Provider SA", details_panel)
        self.assertIn("<strong>CBU / CVU:</strong> 000123", details_panel)
        self.assertIn("<strong>Alias:</strong> provider.path", details_panel)
        self.assertIn("<strong>Tax ID / CUIL / CUIT:</strong> 20-12345678-9", details_panel)
        self.assertIn('data-copy-text="000123"', details_panel)
        self.assertIn('aria-label="Copy CBU / CVU"', details_panel)
        self.assertIn('data-copy-text="provider.path"', details_panel)
        self.assertIn('aria-label="Copy Alias"', details_panel)
        self.assertIn('data-copy-text="20-12345678-9"', details_panel)
        self.assertIn('aria-label="Copy Tax ID"', details_panel)
        self.assertNotIn('aria-label="Copy Account holder"', details_panel)

    def test_payment_request_card_details_shows_card_payment_status(self):
        user = self.create_user("requester@example.com")
        payment = self.payment(user)
        payment.payment_method = "Card"
        payment.bank_details_snapshot = '{"card_payment_status": "Already paid"}'
        db.session.commit()

        body = self.client_for(user).get("/finance-requests").get_data(as_text=True)
        details_panel = body[
            body.index("<summary>Payment details</summary>") : body.index("<summary>Status track</summary>")
        ]

        self.assertIn("<strong>Payment method:</strong> Card", details_panel)
        self.assertIn("<strong>Card payment status:</strong> Already paid", details_panel)
        self.assertNotIn("Account holder:", details_panel)

    def test_payment_request_card_shows_supporting_documents_block_only_when_link_exists(self):
        user = self.create_user("requester@example.com")
        payment = self.payment(user)
        payment.supporting_documentation_url = "https://example.com/supporting-doc"
        db.session.commit()

        body = self.client_for(user).get("/finance-requests").get_data(as_text=True)

        self.assertIn("<summary>Supporting documents</summary>", body)
        self.assertIn('<a href="https://example.com/supporting-doc" target="_blank" rel="noopener">View documents here</a>', body)
        self.assertNotIn("Details and actions", body)

    def test_payment_request_card_shows_comments_block_only_when_comments_exist(self):
        user = self.create_user("requester@example.com")
        payment = self.payment(user)
        payment.requester_comments = "Please review before paying."
        db.session.commit()

        body = self.client_for(user).get("/finance-requests").get_data(as_text=True)
        comments_panel = body[
            body.index("<summary>Comments (1)</summary>") : body.index("<summary>Status track</summary>")
        ]

        self.assertIn("<summary>Comments (1)</summary>", body)
        self.assertIn("Please review before paying.", comments_panel)
        self.assertNotIn("Documentation", comments_panel)
        self.assertNotIn("Status track", comments_panel)

    def test_payment_request_card_comments_title_shows_comment_count(self):
        user = self.create_user("requester@example.com")
        payment = self.payment(user)
        payment.requester_comments = "Requester note"
        payment.management_comments = "Management note"
        db.session.commit()

        body = self.client_for(user).get("/finance-requests").get_data(as_text=True)

        self.assertIn("<summary>Comments (2)</summary>", body)

    def test_payment_request_card_status_track_shows_only_status_events(self):
        user = self.create_user("requester@example.com")
        payment = self.payment(user)
        payment.supporting_documentation_url = "https://example.com/supporting-doc"
        payment.requester_comments = "Requester note"
        db.session.add(
            PaymentRequestEvent(
                payment_request_id=payment.id,
                event_type="Status changed",
                previous_status="Submitted",
                new_status="Approved",
                comment="Approved for payment.",
                created_by_department="Management",
                created_on=datetime(2026, 8, 15, 15, 30, tzinfo=timezone.utc),
            )
        )
        db.session.commit()

        body = self.client_for(user).get("/finance-requests").get_data(as_text=True)
        status_panel = body[body.index("<summary>Status track</summary>") :]
        status_panel = status_panel[: status_panel.index('<div class="finance-card-actions">')]

        self.assertIn("Status changed", status_panel)
        self.assertIn("Submitted → Approved · Management · 15/08/2026 · 12:30 pm", status_panel)
        self.assertIn("Approved for payment.", status_panel)
        self.assertNotIn("View documents here", status_panel)
        self.assertNotIn("Requester note", status_panel)

    def test_payment_request_card_shows_receipt_link_when_payment_proof_exists(self):
        user = self.create_user("requester@example.com")
        payment = self.payment(user, status="Payment completed")
        payment.payment_proof_url = "https://example.com/payment-proof"
        payment.payment_completed_at = datetime(2026, 8, 15, 15, 30, tzinfo=timezone.utc)
        db.session.commit()

        body = self.client_for(user).get("/finance-requests").get_data(as_text=True)

        self.assertIn('Receipt: <a href="https://example.com/payment-proof" target="_blank" rel="noopener">click here</a>', body)

    def test_payment_copy_icon_uses_whatsapp_message_for_payment_request(self):
        user = self.create_user("requester@example.com")
        payment = self.payment(user, status="Payment scheduled", scheduled_payment_date=date(2026, 10, 30))
        payment.payee_name_snapshot = "Xxxxx Xxxxx"
        payment.requester_comments = "Internal requester note"
        payment.management_comments = "Internal management note"
        payment.finance_comments = "Internal finance note"
        payment.bank_details_snapshot = '{"account_number": "000123", "alias": "provider.path"}'
        db.session.add(
            PaymentRequestEvent(
                payment_request_id=payment.id,
                event_type="Payment scheduled",
                new_status="Payment scheduled",
                created_on=datetime(2026, 10, 20, 14, 50, tzinfo=timezone.utc),
            )
        )
        db.session.commit()

        contract = payment_whatsapp_copy_contract(payment)

        self.assertEqual(contract["error"], "")
        self.assertIn("*PAY-2026-0001*", contract["message"])
        self.assertIn("The payment to *Xxxxx Xxxxx* was updated to *Payment Scheduled* on *20/10/2026 at 11:50h.*", contract["message"])
        self.assertIn("*Path International Examinations*", contract["message"])
        self.assertNotIn("30/10/2026", contract["message"])
        self.assertNotIn("View the payment receipt here", contract["message"])
        self.assertNotIn("undefined", contract["message"])
        self.assertNotIn("null", contract["message"])
        self.assertNotIn("None", contract["message"])
        self.assertNotIn("<strong>", contract["message"])
        self.assertNotIn("Payment ID", contract["message"])
        self.assertNotIn("payment_id", contract["message"])
        self.assertNotIn("000123", contract["message"])
        self.assertNotIn("provider.path", contract["message"])
        self.assertNotIn("Internal requester note", contract["message"])
        self.assertNotIn("Internal management note", contract["message"])
        self.assertNotIn("Internal finance note", contract["message"])

        body = self.client_for(user).get("/finance-requests?tab=payment_requests").get_data(as_text=True)
        self.assertIn("Payment WhatsApp message copied.", body)
        self.assertIn('<span class="copy-icon copy-language-label">EN</span>', body)
        self.assertIn('<span class="copy-icon copy-language-label">SP</span>', body)
        self.assertIn("The payment to *Xxxxx Xxxxx* was updated to *Payment Scheduled* on *20/10/2026 at 11:50h.*", body)
        self.assertIn("El pago a *Xxxxx Xxxxx* fue actualizado a *Pago programado* el *20/10/2026 a las 11:50 h.*", body)

    def test_payment_whatsapp_message_uses_updated_on_fallback_when_status_event_is_missing(self):
        user = self.create_user("requester@example.com")
        payment = self.payment(user, status="Payment delayed", scheduled_payment_date=date(2026, 10, 30))
        payment.payee_name_snapshot = "Fallback Vendor"
        payment.updated_on = datetime(2026, 10, 21, 13, 5, tzinfo=timezone.utc)
        db.session.commit()

        contract = payment_whatsapp_copy_contract(payment)

        self.assertEqual(contract["error"], "")
        self.assertIn("*Payment Delayed*", contract["message"])
        self.assertIn("*21/10/2026 at 10:05h.*", contract["message"])
        self.assertNotIn("View the payment receipt here", contract["message"])

    def test_completed_payment_whatsapp_message_requires_and_includes_payment_proof(self):
        user = self.create_user("requester@example.com")
        payment = self.payment(user, status="Payment completed")
        payment.payee_name_snapshot = "Paid Vendor"
        payment.payment_proof_url = "https://example.com/payment-proof"
        db.session.add(
            PaymentRequestEvent(
                payment_request_id=payment.id,
                event_type="Payment completed",
                new_status="Payment completed",
                created_on=datetime(2026, 10, 22, 16, 20, tzinfo=timezone.utc),
            )
        )
        db.session.commit()

        contract = payment_whatsapp_copy_contract(payment)

        self.assertEqual(contract["error"], "")
        self.assertIn("*Payment Completed*", contract["message"])
        self.assertIn("*View the payment receipt here:* https://example.com/payment-proof", contract["message"])

        spanish_contract = payment_whatsapp_copy_contract(payment, "sp")

        self.assertEqual(spanish_contract["error"], "")
        self.assertIn("*Pago completado*", spanish_contract["message"])
        self.assertIn("El pago a *Paid Vendor* fue actualizado a *Pago completado* el *22/10/2026 a las 13:20 h.*", spanish_contract["message"])
        self.assertIn("*Ver el comprobante del pago aquí:* https://example.com/payment-proof", spanish_contract["message"])

        payment.payment_proof_url = ""
        db.session.commit()
        contract = payment_whatsapp_copy_contract(payment)

        self.assertEqual(contract["message"], "")
        self.assertEqual(contract["error"], "Payment proof link is required to copy a completed payment message.")

    def test_payment_whatsapp_message_requires_payment_number_and_payee(self):
        user = self.create_user("requester@example.com")
        payment = self.payment(user, status="Submitted")
        payment.request_number = ""
        db.session.commit()

        self.assertEqual(payment_whatsapp_copy_contract(payment)["error"], "Payment number is required to copy this message.")

        payment.request_number = "PAY-2026-9999"
        payment.payee_name_snapshot = ""
        db.session.commit()

        self.assertEqual(payment_whatsapp_copy_contract(payment)["error"], "Payee name is required to copy this message.")

    def test_payment_date_field_uses_radios_and_specific_date_hook(self):
        user = self.create_user("requester@example.com")
        body = self.client_for(user).get("/finance-requests").get_data(as_text=True)

        self.assertIn("Payment date", body)
        self.assertIn("In the next payment run", body)
        self.assertIn("finance-payment-run-date", body)
        self.assertIn("data-finance-payment-date-recalculated", body)
        self.assertIn(finance_next_payment_run_date().strftime("%d/%m/%Y"), body)
        self.assertIn("On a specific date", body)
        self.assertIn('data-finance-specific-payment-date', body)
        self.assertIn('placeholder="DD/MM/YYYY"', body)
        self.assertIn("data-date-mask", body)
        self.assertIn("data-date-future-or-today", body)
        self.assertIn("data-finance-business-date", body)
        self.assertIn("Payments cannot be processed on Saturdays, Sundays or public holidays.", body)

    def test_finance_next_payment_run_date_uses_next_business_day_after_13_days(self):
        self.assertEqual(finance_next_payment_run_date(date(2026, 8, 15)), date(2026, 8, 31))
        self.assertEqual(finance_next_payment_run_date(date(2026, 9, 29)), date(2026, 10, 13))
        self.assertEqual(finance_next_payment_run_date(date(2026, 2, 3)), date(2026, 2, 18))

    def test_contact_payee_is_single_autocomplete_field(self):
        user = self.create_user("requester@example.com")
        contact = FinanceContact(
            display_name="Provider SA",
            default_concept_id=self.concept.id,
            default_payment_method="Bank transfer",
            account_holder="Provider SA",
            account_number="000123",
            alias="PROVIDER.SA",
            tax_id="30-12345678-9",
            is_active=True,
        )
        db.session.add(contact)
        db.session.commit()

        body = self.client_for(user).get("/finance-requests").get_data(as_text=True)

        self.assertIn("Contact / Payee", body)
        self.assertIn("data-finance-payee-picker", body)
        self.assertIn("data-finance-payee-input", body)
        self.assertIn("data-finance-payee-menu", body)
        self.assertIn("data-finance-payee-forget", body)
        self.assertIn("Provider SA", body)
        self.assertIn(f'data-concept-id="{self.concept.id}"', body)
        self.assertIn('data-payment-method="Bank transfer"', body)
        self.assertIn('data-account-number="000123"', body)
        self.assertNotIn("Payee name", body)
        self.assertNotIn("payee_contact_id", body)

    def test_contact_can_be_forgotten_from_saved_payee_list(self):
        user = self.create_user("requester@example.com")
        contact = FinanceContact(display_name="Provider SA", is_active=True)
        db.session.add(contact)
        db.session.commit()

        response = self.client_for(user).post(
            f"/finance-requests/contacts/{contact.id}/forget",
            headers={"X-Requested-With": "XMLHttpRequest"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["ok"], True)
        db.session.refresh(contact)
        self.assertFalse(contact.is_active)

        body = self.client_for(user).get("/finance-requests").get_data(as_text=True)
        self.assertNotIn("Provider SA", body)

    def test_visibility_field_only_renders_for_management_and_superadmin(self):
        requester = self.create_user("requester@example.com", department="Admissions")
        management = self.create_user("management@example.com", department="Management")
        superadmin = self.create_user("superadmin@example.com", department="Admin", is_superadmin=True)

        requester_body = self.client_for(requester).get("/finance-requests").get_data(as_text=True)
        management_body = self.client_for(management).get("/finance-requests").get_data(as_text=True)
        superadmin_body = self.client_for(superadmin).get("/finance-requests").get_data(as_text=True)

        self.assertNotIn("Visibility", requester_body)
        self.assertIn("Visibility", management_body)
        self.assertIn("Visibility", superadmin_body)

    def test_non_management_post_cannot_set_payment_visibility(self):
        user = self.create_user("requester@example.com", department="Admissions")
        response = self.client_for(user).post(
            "/finance-requests/payment-requests",
            data={
                "description": "Restricted attempt",
                "concept_id": str(self.concept.id),
                "currency": "ARS",
                "amount": "2500",
                "payment_method": "Cash",
                "visibility_mode": "Superadmin only",
            },
            follow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)
        payment = PaymentRequest.query.one()
        self.assertEqual(payment.visibility_mode, "Standard")

    def test_user_with_edit_can_create_payment_request(self):
        user = self.create_user("requester@example.com")
        response = self.client_for(user).post(
            "/finance-requests/payment-requests",
            data={
                "description": "New local payment",
                "concept_id": str(self.concept.id),
                "currency": "ARS",
                "amount": "2500",
                "payment_method": "Cash",
                "visibility_mode": "Standard",
            },
            follow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)
        payment = PaymentRequest.query.one()
        self.assertEqual(payment.status, "Submitted")
        self.assertTrue(payment.request_number.startswith("PAY-"))
        self.assertEqual(payment.concept_name_snapshot, "Accounting")

    def test_payment_amount_accepts_comma_decimal_separator(self):
        user = self.create_user("requester@example.com")
        response = self.client_for(user).post(
            "/finance-requests/payment-requests",
            data={
                "description": "Comma decimal payment",
                "concept_id": str(self.concept.id),
                "currency": "ARS",
                "amount": "2500,75",
                "payment_method": "Cash",
            },
            follow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(PaymentRequest.query.one().amount, Decimal("2500.75"))

    def test_new_payment_run_mode_saves_automatic_payment_date(self):
        user = self.create_user("requester@example.com")
        response = self.client_for(user).post(
            "/finance-requests/payment-requests",
            data={
                "description": "New local payment",
                "concept_id": str(self.concept.id),
                "currency": "ARS",
                "amount": "2500",
                "payment_method": "Cash",
                "payment_date_mode": "asap",
            },
            follow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)
        payment = PaymentRequest.query.one()
        self.assertEqual(payment.payment_date_mode, "asap")
        self.assertEqual(payment.scheduled_payment_date, finance_next_payment_run_date())

    def test_existing_asap_payment_date_is_kept_unless_requester_recalculates(self):
        user = self.create_user("requester@example.com")
        payment = self.payment(user, status="Needs correction", scheduled_payment_date=date(2026, 9, 1))
        payment.payment_date_mode = "asap"
        db.session.commit()
        client = self.client_for(user)

        response = client.post(
            f"/finance-requests/payment-requests/{payment.id}/edit",
            data={
                "description": "Corrected payment",
                "concept_id": str(self.concept.id),
                "currency": "ARS",
                "amount": "2500",
                "payment_method": "Cash",
                "payment_date_mode": "asap",
                "payment_date_recalculated": "0",
            },
            follow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)
        db.session.refresh(payment)
        self.assertEqual(payment.scheduled_payment_date, date(2026, 9, 1))

        response = client.post(
            f"/finance-requests/payment-requests/{payment.id}/edit",
            data={
                "description": "Corrected payment again",
                "concept_id": str(self.concept.id),
                "currency": "ARS",
                "amount": "2500",
                "payment_method": "Cash",
                "payment_date_mode": "asap",
                "payment_date_recalculated": "1",
            },
            follow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)
        db.session.refresh(payment)
        self.assertEqual(payment.scheduled_payment_date, finance_next_payment_run_date())

    def test_contact_payee_text_links_existing_contact_by_name(self):
        user = self.create_user("requester@example.com")
        contact = FinanceContact(display_name="Provider SA", is_active=True)
        db.session.add(contact)
        db.session.commit()

        response = self.client_for(user).post(
            "/finance-requests/payment-requests",
            data={
                "description": "Payment to provider",
                "concept_id": str(self.concept.id),
                "payee_name": "Provider SA",
                "currency": "ARS",
                "amount": "2500",
                "payment_method": "Cash",
            },
            follow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)
        payment = PaymentRequest.query.one()
        self.assertEqual(payment.payee_contact_id, contact.id)
        self.assertEqual(payment.payee_name_snapshot, "Provider SA")
        db.session.refresh(contact)
        self.assertEqual(contact.default_concept_id, self.concept.id)
        self.assertEqual(contact.default_payment_method, "Cash")

    def test_contact_payee_text_allows_new_payee_name(self):
        user = self.create_user("requester@example.com")
        response = self.client_for(user).post(
            "/finance-requests/payment-requests",
            data={
                "description": "Payment to new provider",
                "concept_id": str(self.concept.id),
                "payee_name": "New Provider",
                "currency": "ARS",
                "amount": "2500",
                "payment_method": "Cash",
            },
            follow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)
        payment = PaymentRequest.query.one()
        contact = FinanceContact.query.filter_by(display_name="New Provider").one()
        self.assertEqual(payment.payee_contact_id, contact.id)
        self.assertEqual(payment.payee_name_snapshot, "New Provider")
        self.assertEqual(contact.default_concept_id, self.concept.id)
        self.assertEqual(contact.default_payment_method, "Cash")
        self.assertTrue(contact.is_active)

    def test_new_bank_payment_saves_payee_contact_defaults(self):
        user = self.create_user("requester@example.com")
        response = self.client_for(user).post(
            "/finance-requests/payment-requests",
            data={
                "description": "Payment to bank provider",
                "concept_id": str(self.concept.id),
                "payee_name": "Bank Provider",
                "currency": "ARS",
                "amount": "2500",
                "payment_method": "Bank transfer",
                "account_holder": "Bank Provider LLC",
                "account_number": "000123",
                "alias": "BANK.PROVIDER",
                "tax_id": "30-12345678-9",
            },
            follow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)
        contact = FinanceContact.query.filter_by(display_name="Bank Provider").one()
        payment = PaymentRequest.query.one()
        self.assertEqual(payment.payee_contact_id, contact.id)
        self.assertEqual(contact.default_concept_id, self.concept.id)
        self.assertEqual(contact.default_payment_method, "Bank transfer")
        self.assertEqual(contact.account_holder, "Bank Provider LLC")
        self.assertEqual(contact.account_number, "000123")
        self.assertEqual(contact.alias, "BANK.PROVIDER")
        self.assertEqual(contact.tax_id, "30-12345678-9")

    def test_bank_payment_missing_account_identifier_reopens_new_payment_modal(self):
        user = self.create_user("requester@example.com")
        response = self.client_for(user).post(
            "/finance-requests/payment-requests",
            data={
                "description": "Payment missing bank details",
                "concept_id": str(self.concept.id),
                "payee_name": "Bank Provider",
                "currency": "ARS",
                "amount": "2500",
                "payment_method": "Bank transfer",
                "account_holder": "Bank Provider LLC",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn("open_staff_modal=new-payment-request-modal", response.headers["Location"])
        self.assertEqual(PaymentRequest.query.count(), 0)

    def test_bank_payment_missing_account_holder_reopens_new_payment_modal(self):
        user = self.create_user("requester@example.com")
        response = self.client_for(user).post(
            "/finance-requests/payment-requests",
            data={
                "description": "Payment missing account holder",
                "concept_id": str(self.concept.id),
                "payee_name": "Bank Provider",
                "currency": "ARS",
                "amount": "2500",
                "payment_method": "Deposit",
                "account_number": "000123",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn("open_staff_modal=new-payment-request-modal", response.headers["Location"])
        self.assertEqual(PaymentRequest.query.count(), 0)

    def test_latest_payment_overwrites_saved_payee_contact_defaults(self):
        user = self.create_user("requester@example.com")
        contact = FinanceContact(
            display_name="Provider SA",
            default_concept_id=self.concept.id,
            default_payment_method="Bank transfer",
            account_holder="Old Holder",
            account_number="OLD123",
            alias="OLD.ALIAS",
            tax_id="OLD-TAX",
            is_active=False,
        )
        db.session.add(contact)
        db.session.commit()

        response = self.client_for(user).post(
            "/finance-requests/payment-requests",
            data={
                "description": "Latest provider payment",
                "concept_id": str(self.concept.id),
                "payee_name": "Provider SA",
                "currency": "ARS",
                "amount": "2500",
                "payment_method": "Deposit",
                "account_holder": "New Holder",
                "account_number": "NEW123",
                "alias": "NEW.ALIAS",
                "tax_id": "NEW-TAX",
            },
            follow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)
        db.session.refresh(contact)
        self.assertTrue(contact.is_active)
        self.assertEqual(contact.default_concept_id, self.concept.id)
        self.assertEqual(contact.default_payment_method, "Deposit")
        self.assertEqual(contact.account_holder, "New Holder")
        self.assertEqual(contact.account_number, "NEW123")
        self.assertEqual(contact.alias, "NEW.ALIAS")
        self.assertEqual(contact.tax_id, "NEW-TAX")

    def test_card_payment_requires_card_payment_status(self):
        user = self.create_user("requester@example.com")
        response = self.client_for(user).post(
            "/finance-requests/payment-requests",
            data={
                "description": "New card payment",
                "concept_id": str(self.concept.id),
                "currency": "ARS",
                "amount": "2500",
                "payment_method": "Card",
                "visibility_mode": "Standard",
            },
            follow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(PaymentRequest.query.count(), 0)
        self.assertIn("Select whether the card payment is already paid or to be paid.", response.get_data(as_text=True))

    def test_specific_payment_date_accepts_dd_mm_yyyy(self):
        user = self.create_user("requester@example.com")
        payment_date = finance_next_payment_run_date(date.today())
        response = self.client_for(user).post(
            "/finance-requests/payment-requests",
            data={
                "description": "Payment with date",
                "concept_id": str(self.concept.id),
                "currency": "ARS",
                "amount": "2500",
                "payment_method": "Cash",
                "payment_date_mode": "specific",
                "scheduled_payment_date": payment_date.strftime("%d/%m/%Y"),
            },
            follow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)
        payment = PaymentRequest.query.one()
        self.assertEqual(payment.scheduled_payment_date, payment_date)

    def test_specific_payment_date_rejects_past_date(self):
        user = self.create_user("requester@example.com")
        past_date = date.today() - timedelta(days=1)
        response = self.client_for(user).post(
            "/finance-requests/payment-requests",
            data={
                "description": "Payment with old date",
                "concept_id": str(self.concept.id),
                "currency": "ARS",
                "amount": "2500",
                "payment_method": "Cash",
                "payment_date_mode": "specific",
                "scheduled_payment_date": past_date.strftime("%d/%m/%Y"),
            },
            follow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(PaymentRequest.query.count(), 0)
        self.assertIn("Payment date cannot be in the past.", response.get_data(as_text=True))

    def test_specific_payment_date_rejects_weekends_and_public_holidays(self):
        user = self.create_user("requester@example.com")
        for blocked_date in (date(2026, 8, 22), date(2026, 8, 23), date(2026, 12, 25)):
            with self.subTest(blocked_date=blocked_date):
                db.session.query(PaymentRequest).delete()
                db.session.commit()
                response = self.client_for(user).post(
                    "/finance-requests/payment-requests",
                    data={
                        "description": "Payment with blocked date",
                        "concept_id": str(self.concept.id),
                        "currency": "ARS",
                        "amount": "2500",
                        "payment_method": "Cash",
                        "payment_date_mode": "specific",
                        "scheduled_payment_date": blocked_date.strftime("%d/%m/%Y"),
                    },
                    follow_redirects=True,
                )

                self.assertEqual(response.status_code, 200)
                self.assertEqual(PaymentRequest.query.count(), 0)
                self.assertIn(
                    "Payments cannot be processed on Saturdays, Sundays or public holidays.",
                    response.get_data(as_text=True),
                )

    def test_card_already_paid_ignores_payment_date(self):
        user = self.create_user("requester@example.com")
        response = self.client_for(user).post(
            "/finance-requests/payment-requests",
            data={
                "description": "Already paid card payment",
                "concept_id": str(self.concept.id),
                "currency": "ARS",
                "amount": "2500",
                "payment_method": "Card",
                "card_payment_status": "Already paid",
                "payment_date_mode": "specific",
                "scheduled_payment_date": "20/08/2026",
            },
            follow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)
        payment = PaymentRequest.query.one()
        self.assertIsNone(payment.scheduled_payment_date)

    def test_billing_request_card_renders_only_summary_fields(self):
        user = self.create_user("requester@example.com")
        response = self.client_for(user).post(
            "/finance-requests/billing-requests",
            data={
                "concept_id": str(self.concept.id),
                "client_name": "Client SA",
                "currency": "USD",
                "amount": "75",
                "client_tax_id": "30-12345678-9",
                "vat_status_invoice_type": "Responsable Inscripto (factura A)",
                "client_full_address": "123 Client Street",
                "visibility_mode": "Standard",
            },
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)
        billing = BillingRequest.query.one()
        self.assertEqual(billing.description, self.concept.name)
        self.assertTrue(billing.request_number.startswith("INVOICE-"))
        self.assertEqual(billing.client_tax_id, "30-12345678-9")
        self.assertEqual(billing.vat_status_invoice_type, "Responsable Inscripto (factura A)")
        self.assertEqual(billing.client_full_address, "123 Client Street")

        page = self.client_for(user).get("/finance-requests?tab=billing_requests").get_data(as_text=True)
        self.assertIn("Tax ID / CUIL / CUIT", page)
        self.assertIn("VAT status / Invoice type", page)
        self.assertIn("Responsable Inscripto (factura A)", page)
        self.assertIn("Monotributista (factura A)", page)
        self.assertIn("Consumidor Final (factura B)", page)
        self.assertIn("IVA Sujeto Exento (factura B)", page)
        self.assertIn("International clients (factura E)", page)
        self.assertIn("Full address", page)
        self.assertIn("data-finance-full-address-field hidden", page)
        self.assertIn("data-finance-vat-status", page)
        self.assertLess(page.index("Tax ID / CUIL / CUIT"), page.index("VAT status / Invoice type"))
        self.assertLess(page.index("VAT status / Invoice type"), page.index("Supporting documentation link"))
        self.assertLess(page.index("Full address"), page.index("Supporting documentation link"))
        self.assertNotIn("Requested invoice issue date", page)
        self.assertNotIn("<label>Description <textarea name=\"description\"", page)
        self.assertIn(billing.request_number, page)
        self.assertIn('<span class="finance-status-chip status-requested">Requested</span>', page)
        self.assertIn("finance-invoice-request-list", page)
        self.assertIn("<h3>Client: Client SA</h3>", page)
        self.assertIn('<span class="finance-payment-number-status">\n            <strong>', page)
        self.assertIn(f"USD {billing.amount} · {self.concept.name}", page)
        self.assertIn("<summary>Invoice details</summary>", page)
        details_panel = page[page.index("<summary>Invoice details</summary>") : page.index("<summary>Status track</summary>")]
        self.assertNotIn("<strong>Concept:</strong>", details_panel)
        self.assertIn("<strong>Tax ID / CUIL / CUIT:</strong> 30-12345678-9", details_panel)
        self.assertIn("<strong>VAT status / Invoice type:</strong> Responsable Inscripto (factura A)", details_panel)
        self.assertIn("<strong>Full address:</strong> 123 Client Street", details_panel)
        self.assertNotIn("<strong>Supporting documentation:</strong>", details_panel)
        self.assertLess(page.index(f"USD {billing.amount} · {self.concept.name}"), page.index("<summary>Invoice details</summary>"))
        self.assertLess(page.index(f"USD {billing.amount} · {self.concept.name}"), page.index("Requested:"))
        self.assertLess(page.index("Requested:"), page.index("<summary>Invoice details</summary>"))
        self.assertNotIn("<summary>Supporting documents</summary>", page)
        self.assertNotIn("<summary>Comments (", page)
        self.assertIn("<summary>Status track</summary>", page)
        self.assertIn("Requested:", page)
        self.assertIn(f"Requester: {user.full_name} · {user.department}", page)
        self.assertIn("Completed: not yet", page)
        self.assertIn("Invoice: not yet", page)
        self.assertIn('<span class="copy-icon copy-language-label">EN</span>', page)
        self.assertIn('<span class="copy-icon copy-language-label">SP</span>', page)
        self.assertIn("Invoice WhatsApp message copied.", page)
        self.assertIn("Mensaje de WhatsApp de la factura copiado.", page)
        self.assertNotIn(f"USD {billing.amount} · {self.concept.name} · Client SA", page)
        self.assertIn("*INVOICE-", page)
        self.assertIn("The invoice for *Client SA* was updated to *Requested*", page)
        self.assertIn("La factura para *Client SA* fue actualizada a *Solicitada*", page)
        self.assertNotIn("Invoice request: INVOICE-", page)
        self.assertNotIn("Solicitud de invoice: INVOICE-", page)
        self.assertNotIn("Invoice link</a>", page)
        self.assertNotIn('name="status"', page)
        self.assertNotIn('name="scheduled_invoice_issue_date"', page)
        self.assertNotIn('name="invoice_number"', page)
        self.assertNotIn('name="invoice_link"', page)

    def test_invoice_request_cards_have_consistent_base_height(self):
        with open("app/static/css/styles.css", encoding="utf-8") as css_file:
            css = css_file.read()

        selector = ".finance-invoice-request-list > .finance-request-card"
        block = css[css.index(selector) : css.index("}", css.index(selector))]
        self.assertIn("--finance-invoice-card-height: 106mm", css)
        self.assertIn("min-height: var(--finance-invoice-card-height);", block)

    def test_invoice_request_card_header_uses_full_width_for_status_alignment(self):
        with open("app/static/css/styles.css", encoding="utf-8") as css_file:
            css = css_file.read()

        selector = ".finance-invoice-card-main > div"
        block = css[css.index(selector) : css.index("}", css.index(selector))]
        self.assertIn("width: 100%;", block)

    def test_invoice_request_number_uses_invoice_prefix_and_legacy_bill_sequence(self):
        user = self.create_user("requester@example.com")
        year = date.today().year
        db.session.add(
            BillingRequest(
                request_number=f"BILL-{year}-0003",
                requester_user_id=user.id,
                requester_department=user.department,
                client_name_snapshot="Legacy Client",
                concept_id=self.concept.id,
                concept_name_snapshot=self.concept.name,
                description=self.concept.name,
                currency="ARS",
                amount=Decimal("10.00"),
                status="Requested",
            )
        )
        db.session.commit()

        response = self.client_for(user).post(
            "/finance-requests/billing-requests",
            data={
                "concept_id": str(self.concept.id),
                "client_name": "New Client",
                "currency": "ARS",
                "amount": "50",
                "client_tax_id": "30-44444444-4",
                "vat_status_invoice_type": "Consumidor Final (factura B)",
                "visibility_mode": "Standard",
            },
            follow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)
        billing = BillingRequest.query.filter_by(client_name_snapshot="New Client").one()
        self.assertEqual(billing.request_number, f"INVOICE-{year}-0004")

    def test_requested_invoice_request_card_shows_edit_modal(self):
        user = self.create_user("requester@example.com")
        billing = BillingRequest(
            request_number="BILL-2026-0001",
            requester_user_id=user.id,
            requester_department=user.department,
            client_name_snapshot="Client SA",
            concept_id=self.concept.id,
            concept_name_snapshot=self.concept.name,
            description=self.concept.name,
            currency="ARS",
            amount=Decimal("7609990.00"),
            client_tax_id="30-12345678-9",
            vat_status_invoice_type="Consumidor Final (factura B)",
            status="Requested",
        )
        db.session.add(billing)
        db.session.commit()

        page = self.client_for(user).get("/finance-requests?tab=billing_requests").get_data(as_text=True)

        self.assertIn(f'data-open-modal="edit-billing-request-{billing.id}"', page)
        self.assertIn(f'id="edit-billing-request-{billing.id}"', page)
        self.assertIn("Edit invoice request", page)
        self.assertIn('value="Client SA"', page)
        self.assertIn('value="30-12345678-9"', page)
        self.assertIn("Save and close", page)
        self.assertIn("Delete", page)
        self.assertIn("Are you sure you want to delete this invoice request?", page)
        self.assertIn(f"/finance-requests/billing-requests/{billing.id}/delete", page)

    def test_invoice_request_card_shows_documents_comments_and_status_track_blocks(self):
        user = self.create_user("requester@example.com")
        billing = BillingRequest(
            request_number="BILL-2026-0001",
            requester_user_id=user.id,
            requester_department=user.department,
            client_name_snapshot="Client SA",
            concept_id=self.concept.id,
            concept_name_snapshot=self.concept.name,
            description=self.concept.name,
            currency="ARS",
            amount=Decimal("7609990.00"),
            client_tax_id="30-12345678-9",
            vat_status_invoice_type="Consumidor Final (factura B)",
            status="Requested",
            supporting_documentation_url="https://example.com/docs",
            requester_comments="Requester note",
            finance_comments="Finance note",
        )
        db.session.add(billing)
        db.session.flush()
        db.session.add(
            BillingRequestEvent(
                billing_request_id=billing.id,
                event_type="Requested",
                new_status="Requested",
                comment="Created",
                created_by_user_id=user.id,
                created_by_department=user.department,
            )
        )
        db.session.commit()

        page = self.client_for(user).get("/finance-requests?tab=billing_requests").get_data(as_text=True)

        self.assertIn("<summary>Supporting documents</summary>", page)
        self.assertIn('<a href="https://example.com/docs" target="_blank" rel="noopener">View documents here</a>', page)
        self.assertIn("<summary>Comments (2)</summary>", page)
        comments_panel = page[page.index("<summary>Comments (2)</summary>") : page.index("<summary>Status track</summary>")]
        self.assertIn("<strong>Requester:</strong> Requester note", comments_panel)
        self.assertIn("<strong>Finance:</strong> Finance note", comments_panel)
        self.assertIn("<summary>Status track</summary>", page)
        self.assertIn("<strong>Requested</strong>", page)
        self.assertIn("Created", page)

    def test_non_requested_invoice_request_card_does_not_show_edit_button(self):
        user = self.create_user("requester@example.com")
        billing = BillingRequest(
            request_number="BILL-2026-0001",
            requester_user_id=user.id,
            requester_department=user.department,
            client_name_snapshot="Client SA",
            concept_id=self.concept.id,
            concept_name_snapshot=self.concept.name,
            description=self.concept.name,
            currency="ARS",
            amount=Decimal("7609990.00"),
            client_tax_id="30-12345678-9",
            vat_status_invoice_type="Consumidor Final (factura B)",
            status="Invoice scheduled",
        )
        db.session.add(billing)
        db.session.commit()

        page = self.client_for(user).get("/finance-requests?tab=billing_requests").get_data(as_text=True)

        self.assertNotIn(f'data-open-modal="edit-billing-request-{billing.id}"', page)

    def test_requested_invoice_request_can_be_edited(self):
        user = self.create_user("requester@example.com")
        billing = BillingRequest(
            request_number="BILL-2026-0001",
            requester_user_id=user.id,
            requester_department=user.department,
            client_name_snapshot="Client SA",
            concept_id=self.concept.id,
            concept_name_snapshot=self.concept.name,
            description=self.concept.name,
            currency="ARS",
            amount=Decimal("7609990.00"),
            client_tax_id="30-12345678-9",
            vat_status_invoice_type="Consumidor Final (factura B)",
            status="Requested",
        )
        db.session.add(billing)
        db.session.commit()

        response = self.client_for(user).post(
            f"/finance-requests/billing-requests/{billing.id}/edit",
            data={
                "concept_id": str(self.concept.id),
                "client_name": "Edited Client",
                "currency": "USD",
                "amount": "123.45",
                "client_tax_id": "30-99999999-9",
                "vat_status_invoice_type": "Responsable Inscripto (factura A)",
                "client_full_address": "Edited address",
                "supporting_documentation_url": "https://example.com/docs",
                "requester_comments": "Updated comment",
            },
            follow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)
        db.session.refresh(billing)
        self.assertEqual(billing.status, "Requested")
        self.assertEqual(billing.client_name_snapshot, "Edited Client")
        self.assertEqual(billing.currency, "USD")
        self.assertEqual(billing.amount, Decimal("123.45"))
        self.assertEqual(billing.client_tax_id, "30-99999999-9")
        self.assertEqual(billing.client_full_address, "Edited address")
        self.assertEqual(billing.supporting_documentation_url, "https://example.com/docs")
        self.assertEqual(billing.requester_comments, "Updated comment")

    def test_requested_invoice_request_can_be_deleted(self):
        user = self.create_user("requester@example.com")
        billing = BillingRequest(
            request_number="BILL-2026-0001",
            requester_user_id=user.id,
            requester_department=user.department,
            client_name_snapshot="Client SA",
            concept_id=self.concept.id,
            concept_name_snapshot=self.concept.name,
            description=self.concept.name,
            currency="ARS",
            amount=Decimal("7609990.00"),
            client_tax_id="30-12345678-9",
            vat_status_invoice_type="Consumidor Final (factura B)",
            status="Requested",
        )
        db.session.add(billing)
        db.session.commit()

        response = self.client_for(user).post(
            f"/finance-requests/billing-requests/{billing.id}/delete",
            follow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(BillingRequest.query.get(billing.id))

    def test_non_requested_invoice_request_cannot_be_deleted(self):
        user = self.create_user("requester@example.com")
        billing = BillingRequest(
            request_number="BILL-2026-0001",
            requester_user_id=user.id,
            requester_department=user.department,
            client_name_snapshot="Client SA",
            concept_id=self.concept.id,
            concept_name_snapshot=self.concept.name,
            description=self.concept.name,
            currency="ARS",
            amount=Decimal("7609990.00"),
            client_tax_id="30-12345678-9",
            vat_status_invoice_type="Consumidor Final (factura B)",
            status="Invoice scheduled",
        )
        db.session.add(billing)
        db.session.commit()

        response = self.client_for(user).post(f"/finance-requests/billing-requests/{billing.id}/delete")

        self.assertEqual(response.status_code, 403)
        self.assertIsNotNone(BillingRequest.query.get(billing.id))

    def test_invoice_request_card_shows_completed_metadata_and_invoice_link(self):
        user = self.create_user("finance@example.com", department="Finance")
        billing = BillingRequest(
            request_number="BILL-2026-0001",
            requester_user_id=user.id,
            requester_department=user.department,
            client_name_snapshot="Client SA",
            concept_id=self.concept.id,
            concept_name_snapshot=self.concept.name,
            description=self.concept.name,
            currency="ARS",
            amount=Decimal("7609990.00"),
            client_tax_id="30-12345678-9",
            vat_status_invoice_type="Consumidor Final (factura B)",
            status="Invoice issued",
            invoice_link="https://example.com/invoice",
        )
        db.session.add(billing)
        db.session.flush()
        db.session.add(
            BillingRequestEvent(
                billing_request_id=billing.id,
                event_type="Invoice issued",
                new_status="Invoice issued",
                created_by_user_id=user.id,
                created_by_department=user.department,
                created_on=datetime(2026, 10, 20, 14, 50, tzinfo=timezone.utc),
            )
        )
        db.session.commit()

        page = self.client_for(user).get("/finance-requests?tab=billing_requests").get_data(as_text=True)

        self.assertIn("Requested:", page)
        self.assertIn(f"Requester: {user.full_name} · {user.department}", page)
        self.assertIn("Completed:", page)
        self.assertIn('Invoice: <a href="https://example.com/invoice" target="_blank" rel="noopener">click here</a>', page)
        self.assertIn("*BILL-2026-0001*", page)
        self.assertIn("The invoice for *Client SA* was updated to *Invoice issued* on *20/10/2026 at 11:50h.*", page)
        self.assertIn("*View the invoice here:* https://example.com/invoice", page)
        self.assertIn("La factura para *Client SA* fue actualizada a *Factura emitida* el *20/10/2026 a las 11:50 h.*", page)
        self.assertIn("*Ver la factura aquí:* https://example.com/invoice", page)
        self.assertIn("*Path International Examinations*", page)

    def test_invoice_requests_can_archive_issued_or_cancelled_invoices(self):
        user = self.create_user("finance@example.com", department="Finance")
        issued = BillingRequest(
            request_number="INVOICE-2026-0001",
            requester_user_id=user.id,
            requester_department=user.department,
            client_name_snapshot="Issued Client",
            concept_id=self.concept.id,
            concept_name_snapshot=self.concept.name,
            description=self.concept.name,
            currency="ARS",
            amount=Decimal("100.00"),
            client_tax_id="30-12345678-9",
            vat_status_invoice_type="Consumidor Final (factura B)",
            status="Invoice issued",
            invoice_link="https://example.com/invoice",
        )
        requested = BillingRequest(
            request_number="INVOICE-2026-0002",
            requester_user_id=user.id,
            requester_department=user.department,
            client_name_snapshot="Requested Client",
            concept_id=self.concept.id,
            concept_name_snapshot=self.concept.name,
            description=self.concept.name,
            currency="ARS",
            amount=Decimal("200.00"),
            client_tax_id="30-87654321-9",
            vat_status_invoice_type="Consumidor Final (factura B)",
            status="Requested",
        )
        db.session.add_all([issued, requested])
        db.session.commit()

        page = self.client_for(user).get("/finance-requests?tab=billing_requests").get_data(as_text=True)

        issued_card = self.card_for(page, "Issued Client")
        requested_card = self.card_for(page, "Requested Client")
        self.assertIn("Show archived invoices", page)
        self.assertIn(f'action="/finance-requests/billing-requests/{issued.id}/archive"', issued_card)
        self.assertIn(">Archive</button>", issued_card)
        self.assertIn("Are you sure you want to archive this invoice request?", issued_card)
        self.assertNotIn(">Archive</button>", requested_card)

        response = self.client_for(user).post(
            f"/finance-requests/billing-requests/{issued.id}/archive",
            data={"tab": "billing_requests"},
            follow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)
        db.session.refresh(issued)
        self.assertTrue(issued.is_archived)
        self.assertIsNotNone(issued.archived_at)
        self.assertEqual(issued.archived_by_user_id, user.id)
        body = response.get_data(as_text=True)
        self.assertIn("Archived invoice requests", body)
        self.assertNotIn("New invoice request", body)
        self.assertNotIn('action="/finance-requests/billing-requests"', body)
        self.assertIn(issued.request_number, body)
        self.assertIn("Issued Client", body)
        self.assertIn("Invoice proof", body)
        self.assertIn("Full info", body)

        active_page = self.client_for(user).get("/finance-requests?tab=billing_requests").get_data(as_text=True)
        self.assertNotIn(issued.request_number, active_page)
        self.assertIn(requested.request_number, active_page)

    def test_invoice_requests_cannot_archive_requested_invoice(self):
        user = self.create_user("finance@example.com", department="Finance")
        billing = BillingRequest(
            request_number="INVOICE-2026-0001",
            requester_user_id=user.id,
            requester_department=user.department,
            client_name_snapshot="Requested Client",
            concept_id=self.concept.id,
            concept_name_snapshot=self.concept.name,
            description=self.concept.name,
            currency="ARS",
            amount=Decimal("100.00"),
            client_tax_id="30-12345678-9",
            vat_status_invoice_type="Consumidor Final (factura B)",
            status="Requested",
        )
        db.session.add(billing)
        db.session.commit()

        response = self.client_for(user).post(f"/finance-requests/billing-requests/{billing.id}/archive")

        self.assertEqual(response.status_code, 403)
        db.session.refresh(billing)
        self.assertFalse(billing.is_archived)

    def test_invoice_client_full_address_is_cleared_when_vat_status_does_not_require_it(self):
        user = self.create_user("requester@example.com")
        response = self.client_for(user).post(
            "/finance-requests/billing-requests",
            data={
                "concept_id": str(self.concept.id),
                "client_name": "Final Consumer",
                "currency": "ARS",
                "amount": "100",
                "client_tax_id": "20-11111111-1",
                "vat_status_invoice_type": "Consumidor Final (factura B)",
                "client_full_address": "Hidden Address",
                "visibility_mode": "Standard",
            },
            follow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)
        billing = BillingRequest.query.one()
        self.assertEqual(billing.vat_status_invoice_type, "Consumidor Final (factura B)")
        self.assertEqual(billing.client_full_address, "")

    def test_invoice_request_requires_all_fields_except_supporting_docs_and_comments(self):
        user = self.create_user("requester@example.com")
        response = self.client_for(user).post(
            "/finance-requests/billing-requests",
            data={
                "concept_id": str(self.concept.id),
                "client_name": "Missing details client",
                "currency": "ARS",
                "amount": "100",
                "vat_status_invoice_type": "Responsable Inscripto (factura A)",
            },
            follow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(BillingRequest.query.count(), 0)
        body = response.get_data(as_text=True)
        self.assertIn("Tax ID / CUIL / CUIT is required.", body)
        self.assertIn("Full address is required.", body)

        form_body = self.client_for(user).get("/finance-requests?tab=billing_requests").get_data(as_text=True)
        self.assertIn('name="client_name" value="" autocomplete="off" data-finance-payee-input required', form_body)
        self.assertIn('name="client_tax_id" value="" required', form_body)
        self.assertIn('name="vat_status_invoice_type" data-finance-vat-status required', form_body)
        self.assertIn('name="supporting_documentation_url"', form_body)
        self.assertNotIn('name="supporting_documentation_url" required', form_body)
        self.assertIn('name="requester_comments"', form_body)
        self.assertNotIn('name="requester_comments" rows="3" required', form_body)

    def test_invoice_contact_client_uses_separate_autocomplete_list(self):
        user = self.create_user("requester@example.com")
        payee = FinanceContact(display_name="Payment Provider", is_active=True)
        client = FinanceClientContact(
            display_name="Invoice Client",
            default_concept_id=self.concept.id,
            default_currency="USD",
            client_tax_id="30-11111111-1",
            vat_status_invoice_type="Responsable Inscripto (factura A)",
            client_full_address="Av. Siempre Viva 742",
            is_active=True,
        )
        db.session.add_all([payee, client])
        db.session.commit()

        body = self.client_for(user).get("/finance-requests?tab=billing_requests").get_data(as_text=True)

        self.assertIn("Contact / Client", body)
        self.assertLess(body.index("Contact / Client"), body.index(">Concept"))
        self.assertIn("data-finance-contact-kind=\"client\"", body)
        self.assertIn("data-contact-kind=\"client\"", body)
        self.assertIn("Invoice Client", body)
        self.assertIn("data-currency=\"USD\"", body)
        self.assertIn("data-tax-id=\"30-11111111-1\"", body)
        self.assertIn("data-vat-status=\"Responsable Inscripto (factura A)\"", body)
        self.assertIn("data-full-address=\"Av. Siempre Viva 742\"", body)
        self.assertIn("data-finance-payee-forget", body)
        self.assertIn(f"/finance-requests/client-contacts/{client.id}/forget", body)
        self.assertNotIn("Payment Provider", body)
        self.assertNotIn(">Client contact", body)
        self.assertNotIn(">Client name", body)

    def test_new_invoice_client_is_saved_separately_from_payment_payees(self):
        user = self.create_user("requester@example.com")
        response = self.client_for(user).post(
            "/finance-requests/billing-requests",
            data={
                "concept_id": str(self.concept.id),
                "client_name": "New Invoice Client",
                "currency": "USD",
                "amount": "75",
                "client_tax_id": "30-22222222-2",
                "vat_status_invoice_type": "Consumidor Final (factura B)",
                "visibility_mode": "Standard",
            },
            follow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)
        billing = BillingRequest.query.one()
        client = FinanceClientContact.query.filter_by(display_name="New Invoice Client").one()
        self.assertEqual(billing.client_contact_id, client.id)
        self.assertEqual(billing.client_name_snapshot, "New Invoice Client")
        self.assertEqual(client.default_concept_id, self.concept.id)
        self.assertEqual(client.default_currency, "USD")
        self.assertEqual(client.client_tax_id, "30-22222222-2")
        self.assertEqual(client.vat_status_invoice_type, "Consumidor Final (factura B)")
        self.assertEqual(client.client_full_address, "")
        self.assertEqual(FinanceContact.query.filter_by(display_name="New Invoice Client").count(), 0)

    def test_invoice_client_contact_defaults_are_overwritten_by_latest_invoice(self):
        user = self.create_user("requester@example.com")
        client = FinanceClientContact(
            display_name="Repeat Client",
            default_concept_id=None,
            default_currency="ARS",
            client_tax_id="old-tax",
            vat_status_invoice_type="Consumidor Final (factura B)",
            client_full_address="",
            is_active=True,
        )
        db.session.add(client)
        db.session.commit()

        response = self.client_for(user).post(
            "/finance-requests/billing-requests",
            data={
                "concept_id": str(self.concept.id),
                "client_name": "Repeat Client",
                "currency": "USD",
                "amount": "1200",
                "client_tax_id": "30-33333333-3",
                "vat_status_invoice_type": "Responsable Inscripto (factura A)",
                "client_full_address": "Calle Nueva 123",
                "visibility_mode": "Standard",
            },
            follow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)
        db.session.refresh(client)
        billing = BillingRequest.query.one()
        self.assertEqual(billing.client_contact_id, client.id)
        self.assertEqual(client.default_concept_id, self.concept.id)
        self.assertEqual(client.default_currency, "USD")
        self.assertEqual(client.client_tax_id, "30-33333333-3")
        self.assertEqual(client.vat_status_invoice_type, "Responsable Inscripto (factura A)")
        self.assertEqual(client.client_full_address, "Calle Nueva 123")

    def test_client_contact_can_be_forgotten_without_affecting_payee_contacts(self):
        user = self.create_user("requester@example.com")
        payee = FinanceContact(display_name="Shared Name", is_active=True)
        client = FinanceClientContact(display_name="Shared Name", is_active=True)
        db.session.add_all([payee, client])
        db.session.commit()

        response = self.client_for(user).post(
            f"/finance-requests/client-contacts/{client.id}/forget",
            headers={"X-Requested-With": "XMLHttpRequest"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["ok"], True)
        db.session.refresh(client)
        db.session.refresh(payee)
        self.assertFalse(client.is_active)
        self.assertTrue(payee.is_active)

    def test_overdue_reconciliation_is_idempotent_and_keeps_operational_statuses(self):
        user = self.create_user("requester@example.com")
        overdue = self.payment(user, status="Payment scheduled", scheduled_payment_date=date.today() - timedelta(days=1))
        on_hold = self.payment(user, status="On hold", scheduled_payment_date=date.today() - timedelta(days=2))

        self.assertEqual(reconcile_overdue_payment_requests(today=date.today()), 0)
        self.assertEqual(reconcile_overdue_payment_requests(today=date.today()), 0)
        db.session.refresh(overdue)
        db.session.refresh(on_hold)

        self.assertEqual(overdue.status, "Payment scheduled")
        self.assertEqual(on_hold.status, "On hold")
        self.assertTrue(payment_is_delayed(overdue, today=date.today()))
        self.assertTrue(payment_is_delayed(on_hold, today=date.today()))
        self.assertEqual(PaymentRequestEvent.query.filter_by(payment_request_id=overdue.id).count(), 0)

    def test_payment_delayed_appears_in_today_even_with_old_scheduled_date(self):
        user = self.create_user("requester@example.com")
        delayed = self.payment(user, status="Payment delayed", scheduled_payment_date=date.today() - timedelta(days=7))
        scheduled = self.payment(user, status="Management approved", scheduled_payment_date=date.today() - timedelta(days=1))
        completed = self.payment(user, status="Payment completed", scheduled_payment_date=date.today())

        groups = payment_calendar_groups([delayed, scheduled, completed], today=date.today())

        self.assertIn(delayed, groups["today"])
        self.assertIn(scheduled, groups["today"])
        self.assertNotIn(delayed, groups["tomorrow"])
        self.assertNotIn(completed, groups["today"])

    def test_requester_can_hold_and_release_own_submitted_payment(self):
        user = self.create_user("requester@example.com")
        payment = self.payment(user, status="Submitted")
        client = self.client_for(user)

        response = client.post(f"/finance-requests/payment-requests/{payment.id}/hold", data={"tab": "payment_requests"})
        self.assertEqual(response.status_code, 302)
        db.session.refresh(payment)
        self.assertEqual(payment.status, "On hold")
        self.assertEqual(payment.previous_status_before_hold, "Submitted")

        response = client.post(f"/finance-requests/payment-requests/{payment.id}/release-hold", data={"tab": "payment_requests"})
        self.assertEqual(response.status_code, 302)
        db.session.refresh(payment)
        self.assertEqual(payment.status, "Submitted")

    def test_on_hold_payment_card_shows_release_and_cancel_buttons(self):
        user = self.create_user("finance@example.com", department="Finance")
        payment = self.payment(user, status="On hold", scheduled_payment_date=date.today())
        payment.previous_status_before_hold = "Management approved"
        db.session.commit()

        body = self.client_for(user).get("/finance-requests?tab=payment_requests").get_data(as_text=True)

        self.assertIn(payment.request_number, body)
        self.assertIn(">Release</button>", body)
        self.assertIn(">Cancel</button>", body)
        self.assertIn("Are you sure you want to release this payment that is currently on hold?", body)
        self.assertIn("Are you sure you want to delete this payment that is currently on hold?", body)

    def test_releasing_on_hold_scheduled_payment_restores_scheduled_status_and_date(self):
        user = self.create_user("finance@example.com", department="Finance")
        scheduled_date = date.today() + timedelta(days=7)
        payment = self.payment(user, status="On hold", scheduled_payment_date=scheduled_date)
        payment.previous_status_before_hold = "Management approved"
        db.session.commit()

        response = self.client_for(user).post(
            f"/finance-requests/payment-requests/{payment.id}/release-hold",
            data={"tab": "payment_requests"},
        )

        self.assertEqual(response.status_code, 302)
        db.session.refresh(payment)
        self.assertEqual(payment.status, "Management approved")
        self.assertEqual(payment.scheduled_payment_date, scheduled_date)

    def test_cancelling_on_hold_payment_changes_status_to_cancelled(self):
        user = self.create_user("finance@example.com", department="Finance")
        payment = self.payment(user, status="On hold", scheduled_payment_date=date.today())
        payment.previous_status_before_hold = "Management approved"
        db.session.commit()

        response = self.client_for(user).post(
            f"/finance-requests/payment-requests/{payment.id}/cancel-hold",
            data={"tab": "payment_requests"},
        )

        self.assertEqual(response.status_code, 302)
        db.session.refresh(payment)
        self.assertEqual(payment.status, "Payment cancelled")
        self.assertIsNone(payment.previous_status_before_hold)

    def test_rejected_completed_and_cancelled_cannot_be_placed_on_hold(self):
        user = self.create_user("requester@example.com")
        client = self.client_for(user)
        for status in ("Rejected", "Payment completed", "Payment cancelled"):
            with self.subTest(status=status):
                payment = self.payment(user, status=status)
                response = client.post(f"/finance-requests/payment-requests/{payment.id}/hold")
                self.assertEqual(response.status_code, 403)
                db.session.refresh(payment)
                self.assertEqual(payment.status, status)

    def test_completed_payment_can_be_archived_without_changing_status(self):
        user = self.create_user("requester@example.com")
        payment = self.payment(user, status="Payment completed")

        response = self.client_for(user).post(f"/finance-requests/payment-requests/{payment.id}/archive")

        self.assertEqual(response.status_code, 302)
        db.session.refresh(payment)
        self.assertTrue(payment.is_archived)
        self.assertEqual(payment.status, "Payment completed")

    def test_payment_requests_show_archive_button_for_terminal_statuses(self):
        user = self.create_user("requester@example.com")
        for status in ("Rejected", "Payment cancelled", "Payment completed"):
            payment = self.payment(user, status=status)
            payment.description = f"{status} payment"
        self.payment(user, status="Submitted").description = "Submitted payment"
        db.session.commit()

        body = self.client_for(user).get("/finance-requests?tab=payment_requests").get_data(as_text=True)

        self.assertEqual(body.count(">Archive</button>"), 3)
        self.assertIn("Are you sure you want to archive this payment request?", body)
        self.assertIn("Rejected payment", body)
        self.assertIn("Payment cancelled payment", body)
        self.assertIn("Payment completed payment", body)
        self.assertIn("Submitted payment", body)

    def test_archived_payment_moves_from_general_list_to_archived_list(self):
        user = self.create_user("requester@example.com")
        payment = self.payment(user, status="Rejected")

        response = self.client_for(user).post(
            f"/finance-requests/payment-requests/{payment.id}/archive",
            data={"tab": "payment_requests"},
            follow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)
        db.session.refresh(payment)
        self.assertTrue(payment.is_archived)
        general_body = response.get_data(as_text=True)
        self.assertNotIn(payment.request_number, general_body)

        archived_body = self.client_for(user).get(
            "/finance-requests?tab=payment_requests&show_archived=1"
        ).get_data(as_text=True)

        self.assertIn(payment.request_number, archived_body)
        self.assertIn("Archived", archived_body)

    def test_archived_payment_requests_render_as_read_only_table(self):
        user = self.create_user("requester@example.com")
        completed = self.payment(user, status="Payment completed", is_archived=True)
        completed.payee_name_snapshot = "Paid Vendor"
        completed.description = "Completed archived payment"
        completed.payment_proof_url = "https://example.com/payment-proof"
        completed.payment_completed_at = datetime(2026, 8, 15, 15, 30, tzinfo=timezone.utc)
        cancelled = self.payment(user, status="Payment cancelled", is_archived=True)
        cancelled.payee_name_snapshot = "Cancelled Vendor"
        cancelled.description = "Cancelled archived payment"
        db.session.add(
            PaymentRequestEvent(
                payment_request_id=cancelled.id,
                event_type="Payment cancelled",
                new_status="Payment cancelled",
                created_on=datetime(2026, 8, 16, 13, 0, tzinfo=timezone.utc),
            )
        )
        active = self.payment(user, status="Submitted")
        active.description = "Active payment"
        db.session.commit()

        body = self.client_for(user).get("/finance-requests?tab=payment_requests&show_archived=1").get_data(as_text=True)

        for heading in ("Payment no.", "Final date", "Status", "Payee", "Concept", "Description", "Payment proof", "Full info"):
            self.assertIn(heading, body)
        self.assertIn('class="table-sort ', body)
        self.assertIn("sort=payee", body)
        self.assertIn(completed.request_number, body)
        self.assertIn("15/08/2026", body)
        self.assertIn("Paid Vendor", body)
        self.assertIn("Completed archived payment", body)
        self.assertIn('href="https://example.com/payment-proof"', body)
        self.assertIn(">View proof</a>", body)
        self.assertIn(f'data-open-modal="archived-payment-request-{completed.id}"', body)
        self.assertIn(f'id="archived-payment-request-{completed.id}"', body)
        self.assertIn(cancelled.request_number, body)
        self.assertIn("16/08/2026", body)
        self.assertIn("Cancelled Vendor", body)
        self.assertNotIn(active.request_number, body)
        self.assertNotIn("Active payment", body)
        self.assertNotIn("Are you sure you want to archive this payment request?", body)

    def test_archived_payment_requests_can_be_sorted_by_payee(self):
        user = self.create_user("requester@example.com")
        zeta = self.payment(user, status="Rejected", is_archived=True)
        zeta.payee_name_snapshot = "Zeta Vendor"
        alpha = self.payment(user, status="Payment cancelled", is_archived=True)
        alpha.payee_name_snapshot = "Alpha Vendor"
        db.session.commit()

        body = self.client_for(user).get(
            "/finance-requests?tab=payment_requests&show_archived=1&sort=payee&dir=asc"
        ).get_data(as_text=True)

        self.assertLess(body.index(alpha.request_number), body.index(zeta.request_number))
        self.assertIn('class="table-sort is-active"', body)
        self.assertIn("dir=desc", body)

    def test_completed_or_cancelled_payments_move_to_top_of_payment_requests(self):
        user = self.create_user("requester@example.com")
        newer_submitted = self.payment(user, status="Submitted")
        newer_submitted.created_on = datetime(2026, 8, 16, 15, 0, tzinfo=timezone.utc)
        completed = self.payment(user, status="Payment completed")
        completed.created_on = datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)
        completed.payment_completed_at = datetime(2026, 8, 16, 16, 0, tzinfo=timezone.utc)
        cancelled = self.payment(user, status="Payment cancelled")
        cancelled.created_on = datetime(2026, 8, 2, 12, 0, tzinfo=timezone.utc)
        db.session.add(
            PaymentRequestEvent(
                payment_request_id=cancelled.id,
                event_type="Payment cancelled",
                new_status="Payment cancelled",
                created_on=datetime(2026, 8, 16, 17, 0, tzinfo=timezone.utc),
            )
        )
        db.session.commit()

        body = self.client_for(user).get("/finance-requests?tab=payment_requests").get_data(as_text=True)

        self.assertLess(body.index(cancelled.request_number), body.index(completed.request_number))
        self.assertLess(body.index(completed.request_number), body.index(newer_submitted.request_number))


if __name__ == "__main__":
    unittest.main()
