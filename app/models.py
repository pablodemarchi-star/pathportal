import json
from datetime import datetime, timezone

from app import db


class AcademicStaff(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    status = db.Column(db.String(30), nullable=False, index=True)
    title = db.Column(db.String(120), nullable=True)
    full_name = db.Column(db.String(160), nullable=False, index=True)
    seniority = db.Column(db.Boolean, nullable=False, default=False)
    fut_checked = db.Column(db.Boolean, nullable=False, default=False)
    meeting_fut_checked = db.Column(db.Boolean, nullable=False, default=False)
    roles = db.Column(db.String(200), nullable=False, default="")
    phone = db.Column(db.String(80), nullable=True)
    email = db.Column(db.String(160), nullable=True, index=True)
    has_car = db.Column(db.String(10), nullable=True, index=True)
    started_in = db.Column(db.String(4), nullable=True)
    full_address_google_maps = db.Column(db.String(500), nullable=True)
    street_name = db.Column(db.String(160), nullable=True)
    street_number = db.Column(db.String(40), nullable=True)
    city = db.Column(db.String(120), nullable=True, index=True)
    postcode = db.Column(db.String(40), nullable=True)
    province = db.Column(db.String(120), nullable=True, index=True)
    location_point = db.Column(db.String(500), nullable=True)
    country = db.Column(db.String(120), nullable=True, index=True)
    cv = db.Column(db.String(500), nullable=True)
    interview = db.Column(db.Text, nullable=True)
    account_id = db.Column(db.String(120), nullable=True, index=True)
    account_owner = db.Column(db.String(160), nullable=True, index=True)
    profile_picture = db.Column(db.String(500), nullable=True)
    created_on = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_on = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    def roles_list(self):
        return [role.strip() for role in self.roles.split(",") if role.strip()]


class Role(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False, unique=True, index=True)
    created_on = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_on = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class Fee(db.Model):
    __table_args__ = (
        db.UniqueConstraint("fee_description", "currency", "unit_of_measure", "role_id", name="uq_fee_description_currency_unit_role"),
    )

    id = db.Column(db.Integer, primary_key=True)
    fee_description = db.Column(db.String(180), nullable=False, index=True)
    currency = db.Column(db.String(3), nullable=False, index=True)
    fee_value = db.Column(db.String(40), nullable=False)
    unit_of_measure = db.Column(db.String(30), nullable=False, index=True)
    role_id = db.Column(db.Integer, db.ForeignKey("role.id"), nullable=True, index=True)
    valid_through = db.Column(db.Text, nullable=False, default="[]")
    created_on = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_on = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    role = db.relationship("Role", backref=db.backref("fees", lazy=True))

    def valid_through_list(self):
        try:
            values = json.loads(self.valid_through or "[]")
        except (TypeError, json.JSONDecodeError):
            return []
        if not isinstance(values, list):
            return []
        return [value for value in values if isinstance(value, str)]


class ProviderType(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False, unique=True, index=True)
    is_system = db.Column(db.Boolean, nullable=False, default=False, index=True)
    color_key = db.Column(db.String(40), nullable=False, default="provider-type-0")
    created_on = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_on = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class Provider(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    provider_type_id = db.Column(db.Integer, db.ForeignKey("provider_type.id"), nullable=False, index=True)
    name = db.Column(db.String(180), nullable=False, index=True)
    full_address = db.Column(db.String(500), nullable=False)
    experience_rating = db.Column(db.Integer, nullable=False, default=0)
    available_in_logistics = db.Column(db.Boolean, nullable=False, default=False, index=True)
    created_on = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_on = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    provider_type = db.relationship("ProviderType", backref=db.backref("providers", lazy=True))

    @property
    def display_label(self):
        provider_type_name = self.provider_type.name if self.provider_type else "Provider"
        return f"{self.name} — {provider_type_name}"


class ProviderHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    provider_id = db.Column(db.Integer, db.ForeignKey("provider.id"), nullable=False, index=True)
    comment = db.Column(db.Text, nullable=False)
    created_by = db.Column(db.String(120), nullable=True)
    created_on = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    provider = db.relationship("Provider", backref=db.backref("history_entries", lazy=True, cascade="all, delete-orphan"))


class AnnualCertificationRecord(db.Model):
    __table_args__ = (
        db.UniqueConstraint("member_id", "certification_type", "year", name="uq_member_certification_year"),
    )

    id = db.Column(db.Integer, primary_key=True)
    member_id = db.Column(db.Integer, db.ForeignKey("academic_staff.id"), nullable=False, index=True)
    certification_type = db.Column(db.String(80), nullable=False, index=True)
    year = db.Column(db.Integer, nullable=False, index=True)
    created_by = db.Column(db.String(120), nullable=True)
    updated_by = db.Column(db.String(120), nullable=True)
    created_on = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_on = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    member = db.relationship("AcademicStaff", backref=db.backref("annual_certifications", lazy=True))


class AnnualMeetingRecord(db.Model):
    __table_args__ = (
        db.UniqueConstraint("member_id", "meeting_type", "year", name="uq_member_meeting_year"),
    )

    id = db.Column(db.Integer, primary_key=True)
    member_id = db.Column(db.Integer, db.ForeignKey("academic_staff.id"), nullable=False, index=True)
    meeting_type = db.Column(db.String(80), nullable=False, index=True)
    year = db.Column(db.Integer, nullable=False, index=True)
    created_by = db.Column(db.String(120), nullable=True)
    updated_by = db.Column(db.String(120), nullable=True)
    created_on = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_on = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    member = db.relationship("AcademicStaff", backref=db.backref("annual_meetings", lazy=True))


class StaffCertificationFutSelection(db.Model):
    __table_args__ = (
        db.UniqueConstraint("member_id", "option_name", name="uq_member_staff_fut_option"),
    )

    id = db.Column(db.Integer, primary_key=True)
    member_id = db.Column(db.Integer, db.ForeignKey("academic_staff.id"), nullable=False, index=True)
    option_name = db.Column(db.String(120), nullable=False, index=True)
    status = db.Column(db.String(20), nullable=False, default="pending", index=True)
    created_on = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_on = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    member = db.relationship("AcademicStaff", backref=db.backref("staff_fut_selections", lazy=True))


class StaffCertificationFut2Selection(db.Model):
    __table_args__ = (
        db.UniqueConstraint("member_id", "option_name", name="uq_member_staff_fut2_option"),
    )

    id = db.Column(db.Integer, primary_key=True)
    member_id = db.Column(db.Integer, db.ForeignKey("academic_staff.id"), nullable=False, index=True)
    option_name = db.Column(db.String(120), nullable=False, index=True)
    status = db.Column(db.String(20), nullable=False, default="pending", index=True)
    created_on = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_on = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    member = db.relationship("AcademicStaff", backref=db.backref("staff_fut2_selections", lazy=True))


class ExaminerCertificationYear(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    year = db.Column(db.Integer, nullable=False, unique=True, index=True)
    is_archived = db.Column(db.Boolean, nullable=False, default=False, index=True)
    created_on = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_on = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class CertificationYearConfiguration(db.Model):
    __table_args__ = (
        db.UniqueConstraint("module_key", "year", name="uq_certification_year_configuration_module_year"),
    )

    id = db.Column(db.Integer, primary_key=True)
    module_key = db.Column(db.String(40), nullable=False, index=True)
    year = db.Column(db.Integer, nullable=False, index=True)
    annual_meeting_date = db.Column(db.Date)
    annual_meeting_time = db.Column(db.Time)
    remote_training_start_date = db.Column(db.Date)
    remote_training_end_date = db.Column(db.Date)
    created_on = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_on = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class ExaminerCertificationFut1Selection(db.Model):
    __table_args__ = (
        db.UniqueConstraint("member_id", "option_name", "year", name="uq_member_examiner_fut1_option_year"),
    )

    id = db.Column(db.Integer, primary_key=True)
    member_id = db.Column(db.Integer, db.ForeignKey("academic_staff.id"), nullable=False, index=True)
    option_name = db.Column(db.String(120), nullable=False, index=True)
    status = db.Column(db.String(20), nullable=False, default="pending", index=True)
    year = db.Column(db.Integer, nullable=False, default=2026, index=True)
    created_on = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_on = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    member = db.relationship("AcademicStaff", backref=db.backref("examiner_fut1_selections", lazy=True))


class ExaminerCertificationFut2Selection(db.Model):
    __table_args__ = (
        db.UniqueConstraint("member_id", "option_name", "year", name="uq_member_examiner_fut2_option_year"),
    )

    id = db.Column(db.Integer, primary_key=True)
    member_id = db.Column(db.Integer, db.ForeignKey("academic_staff.id"), nullable=False, index=True)
    option_name = db.Column(db.String(120), nullable=False, index=True)
    status = db.Column(db.String(20), nullable=False, default="pending", index=True)
    year = db.Column(db.Integer, nullable=False, default=2026, index=True)
    created_on = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_on = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    member = db.relationship("AcademicStaff", backref=db.backref("examiner_fut2_selections", lazy=True))


class ExaminerCertificationRemoteTrainingSelection(db.Model):
    __table_args__ = (
        db.UniqueConstraint("member_id", "year", name="uq_member_examiner_remote_training_year"),
    )

    id = db.Column(db.Integer, primary_key=True)
    member_id = db.Column(db.Integer, db.ForeignKey("academic_staff.id"), nullable=False, index=True)
    status = db.Column(db.String(40), nullable=False, index=True)
    year = db.Column(db.Integer, nullable=False, default=2026, index=True)
    created_on = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_on = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    member = db.relationship("AcademicStaff", backref=db.backref("examiner_remote_training_selections", lazy=True))


class ExaminerCertificationAnnualMeetingSelection(db.Model):
    __table_args__ = (
        db.UniqueConstraint("member_id", "year", name="uq_member_examiner_annual_meeting_year"),
    )

    id = db.Column(db.Integer, primary_key=True)
    member_id = db.Column(db.Integer, db.ForeignKey("academic_staff.id"), nullable=False, index=True)
    status = db.Column(db.String(40), nullable=False, index=True)
    year = db.Column(db.Integer, nullable=False, default=2026, index=True)
    created_on = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_on = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    member = db.relationship("AcademicStaff", backref=db.backref("examiner_annual_meeting_selections", lazy=True))


class SupervisorCertificationYear(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    year = db.Column(db.Integer, nullable=False, unique=True, index=True)
    is_archived = db.Column(db.Boolean, nullable=False, default=False, index=True)
    created_on = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_on = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class SupervisorCertificationFutSelection(db.Model):
    __table_args__ = (
        db.UniqueConstraint("member_id", "option_name", "year", name="uq_member_supervisor_fut_option_year"),
    )

    id = db.Column(db.Integer, primary_key=True)
    member_id = db.Column(db.Integer, db.ForeignKey("academic_staff.id"), nullable=False, index=True)
    option_name = db.Column(db.String(120), nullable=False, index=True)
    status = db.Column(db.String(20), nullable=False, default="pending", index=True)
    year = db.Column(db.Integer, nullable=False, default=2026, index=True)
    created_on = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_on = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    member = db.relationship("AcademicStaff", backref=db.backref("supervisor_fut_selections", lazy=True))


class SupervisorCertificationRemoteTrainingSelection(db.Model):
    __table_args__ = (
        db.UniqueConstraint("member_id", "year", name="uq_member_supervisor_remote_training_year"),
    )

    id = db.Column(db.Integer, primary_key=True)
    member_id = db.Column(db.Integer, db.ForeignKey("academic_staff.id"), nullable=False, index=True)
    status = db.Column(db.String(40), nullable=False, index=True)
    year = db.Column(db.Integer, nullable=False, default=2026, index=True)
    created_on = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_on = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    member = db.relationship("AcademicStaff", backref=db.backref("supervisor_remote_training_selections", lazy=True))


class SupervisorCertificationAnnualMeetingSelection(db.Model):
    __table_args__ = (
        db.UniqueConstraint("member_id", "year", name="uq_member_supervisor_annual_meeting_year"),
    )

    id = db.Column(db.Integer, primary_key=True)
    member_id = db.Column(db.Integer, db.ForeignKey("academic_staff.id"), nullable=False, index=True)
    status = db.Column(db.String(40), nullable=False, index=True)
    year = db.Column(db.Integer, nullable=False, default=2026, index=True)
    created_on = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_on = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    member = db.relationship("AcademicStaff", backref=db.backref("supervisor_annual_meeting_selections", lazy=True))


class InternStageYear(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    year = db.Column(db.Integer, nullable=False, unique=True, index=True)
    is_archived = db.Column(db.Boolean, nullable=False, default=False, index=True)
    created_on = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_on = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class InternStageFutSelection(db.Model):
    __table_args__ = (
        db.UniqueConstraint("member_id", "option_name", "year", name="uq_member_intern_stage_fut_option_year"),
    )

    id = db.Column(db.Integer, primary_key=True)
    member_id = db.Column(db.Integer, db.ForeignKey("academic_staff.id"), nullable=False, index=True)
    option_name = db.Column(db.String(120), nullable=False, index=True)
    status = db.Column(db.String(20), nullable=False, default="pending", index=True)
    year = db.Column(db.Integer, nullable=False, default=2026, index=True)
    created_on = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_on = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    member = db.relationship("AcademicStaff", backref=db.backref("intern_stage_fut_selections", lazy=True))


class InternStageRemoteTrainingSelection(db.Model):
    __table_args__ = (
        db.UniqueConstraint("member_id", "year", name="uq_member_intern_stage_remote_training_year"),
    )

    id = db.Column(db.Integer, primary_key=True)
    member_id = db.Column(db.Integer, db.ForeignKey("academic_staff.id"), nullable=False, index=True)
    status = db.Column(db.String(40), nullable=False, index=True)
    year = db.Column(db.Integer, nullable=False, default=2026, index=True)
    created_on = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_on = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    member = db.relationship("AcademicStaff", backref=db.backref("intern_stage_remote_training_selections", lazy=True))


class InternStage2Selection(db.Model):
    __table_args__ = (
        db.UniqueConstraint("member_id", "year", name="uq_member_intern_stage_2_year"),
    )

    id = db.Column(db.Integer, primary_key=True)
    member_id = db.Column(db.Integer, db.ForeignKey("academic_staff.id"), nullable=False, index=True)
    status = db.Column(db.String(40), nullable=False, index=True)
    year = db.Column(db.Integer, nullable=False, default=2026, index=True)
    created_on = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_on = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    member = db.relationship("AcademicStaff", backref=db.backref("intern_stage_2_selections", lazy=True))


class InternStage3Selection(db.Model):
    __table_args__ = (
        db.UniqueConstraint("member_id", "year", name="uq_member_intern_stage_3_year"),
    )

    id = db.Column(db.Integer, primary_key=True)
    member_id = db.Column(db.Integer, db.ForeignKey("academic_staff.id"), nullable=False, index=True)
    status = db.Column(db.String(40), nullable=False, index=True)
    year = db.Column(db.Integer, nullable=False, default=2026, index=True)
    created_on = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_on = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    member = db.relationship("AcademicStaff", backref=db.backref("intern_stage_3_selections", lazy=True))


class InternStageAnnualMeetingSelection(db.Model):
    __table_args__ = (
        db.UniqueConstraint("member_id", "year", name="uq_member_intern_stage_annual_meeting_year"),
    )

    id = db.Column(db.Integer, primary_key=True)
    member_id = db.Column(db.Integer, db.ForeignKey("academic_staff.id"), nullable=False, index=True)
    status = db.Column(db.String(40), nullable=False, index=True)
    year = db.Column(db.Integer, nullable=False, default=2026, index=True)
    created_on = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_on = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    member = db.relationship("AcademicStaff", backref=db.backref("intern_stage_annual_meeting_selections", lazy=True))


class ExamSession(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    exam_session_name = db.Column(db.String(160), nullable=False, default="", index=True)
    category = db.Column(db.String(80), nullable=False, default="", index=True)
    rsg_enabled = db.Column(db.Boolean, nullable=False, default=False)
    pen_enabled = db.Column(db.Boolean, nullable=False, default=False)
    pst_enabled = db.Column(db.Boolean, nullable=False, default=False)
    status = db.Column(db.String(20), nullable=False, index=True)
    session_date = db.Column(db.Date, nullable=False, index=True)
    shifts = db.Column(db.String(80), nullable=False, default="")
    modules = db.Column(db.String(120), nullable=False, default="")
    full_address_google_maps = db.Column(db.String(500), nullable=True)
    city = db.Column(db.String(120), nullable=True, index=True)
    province = db.Column(db.String(120), nullable=True, index=True)
    format = db.Column(db.String(20), nullable=False, index=True)
    location_url = db.Column(db.String(500), nullable=True)
    details_url = db.Column(db.String(500), nullable=True)
    created_on = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_on = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    def modules_list(self):
        return [module.strip() for module in self.modules.split(",") if module.strip()]

    def shifts_list(self):
        return [shift.strip() for shift in self.shifts.split(",") if shift.strip()]


class ExamSessionJourneyShare(db.Model):
    __table_args__ = (
        db.UniqueConstraint("token", name="uq_exam_session_journey_share_token"),
        db.UniqueConstraint("exam_session_id", "audience", name="uq_exam_session_journey_share_audience"),
        db.CheckConstraint("audience IN ('institution', 'public')", name="ck_exam_session_journey_share_audience"),
    )

    id = db.Column(db.Integer, primary_key=True)
    exam_session_id = db.Column(db.Integer, db.ForeignKey("exam_session.id"), nullable=False, index=True)
    audience = db.Column(db.String(20), nullable=False, default="institution", index=True)
    token = db.Column(db.String(96), nullable=False, unique=True, index=True)
    is_enabled = db.Column(db.Boolean, nullable=False, default=True, index=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    created_by = db.Column(db.String(120), nullable=True)
    last_copied_at = db.Column(db.DateTime(timezone=True), nullable=True)
    revoked_at = db.Column(db.DateTime(timezone=True), nullable=True)
    revoked_by = db.Column(db.String(120), nullable=True)
    regenerated_at = db.Column(db.DateTime(timezone=True), nullable=True)
    regenerated_by = db.Column(db.String(120), nullable=True)

    exam_session = db.relationship("ExamSession", backref=db.backref("journey_shares", lazy=True, cascade="all, delete-orphan"))


class ExamSessionYear(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    year = db.Column(db.Integer, nullable=False, unique=True, index=True)
    is_archived = db.Column(db.Boolean, nullable=False, default=False, index=True)
    created_on = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_on = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class ExamSessionScheduleWorkflow(db.Model):
    __table_args__ = (
        db.UniqueConstraint("exam_session_id", name="uq_exam_session_schedule_workflow"),
    )

    id = db.Column(db.Integer, primary_key=True)
    exam_session_id = db.Column(db.Integer, db.ForeignKey("exam_session.id"), nullable=False, index=True)
    status = db.Column(db.String(40), nullable=False, default="Not started", index=True)
    next_action_due_at = db.Column(db.Date, nullable=True, index=True)
    review_round = db.Column(db.Integer, nullable=False, default=0)
    last_sent_at = db.Column(db.DateTime(timezone=True), nullable=True)
    changes_requested_at = db.Column(db.DateTime(timezone=True), nullable=True)
    approved_at = db.Column(db.DateTime(timezone=True), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    exam_session = db.relationship("ExamSession", backref=db.backref("schedule_workflow", uselist=False))


class ExamSessionStaffingControl(db.Model):
    __table_args__ = (
        db.UniqueConstraint("exam_session_id", name="uq_exam_session_staffing_control"),
    )

    id = db.Column(db.Integer, primary_key=True)
    exam_session_id = db.Column(db.Integer, db.ForeignKey("exam_session.id"), nullable=False, index=True)
    staffing_due_at = db.Column(db.Date, nullable=True, index=True)
    note = db.Column(db.Text, nullable=True)
    updated_by = db.Column(db.String(120), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    exam_session = db.relationship("ExamSession", backref=db.backref("staffing_control", uselist=False))


class ExamSessionLogisticsControl(db.Model):
    __table_args__ = (
        db.UniqueConstraint("exam_session_id", name="uq_exam_session_logistics_control"),
    )

    id = db.Column(db.Integer, primary_key=True)
    exam_session_id = db.Column(db.Integer, db.ForeignKey("exam_session.id"), nullable=False, index=True)
    logistics_due_at = db.Column(db.Date, nullable=True, index=True)
    note = db.Column(db.Text, nullable=True)
    updated_by = db.Column(db.String(120), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    exam_session = db.relationship("ExamSession", backref=db.backref("logistics_control", uselist=False))


class ExamSessionFinanceControl(db.Model):
    __table_args__ = (
        db.UniqueConstraint("exam_session_id", name="uq_exam_session_finance_control"),
    )

    id = db.Column(db.Integer, primary_key=True)
    exam_session_id = db.Column(db.Integer, db.ForeignKey("exam_session.id"), nullable=False, index=True)
    status = db.Column(db.String(40), nullable=False, default="Not reviewed", index=True)
    finance_due_at = db.Column(db.Date, nullable=True, index=True)
    evidence_url = db.Column(db.String(500), nullable=True)
    note = db.Column(db.Text, nullable=True)
    responsible_department = db.Column(db.String(40), nullable=False, default="FINANCE", index=True)
    reviewed_at = db.Column(db.DateTime(timezone=True), nullable=True)
    cleared_at = db.Column(db.DateTime(timezone=True), nullable=True)
    hold_at = db.Column(db.DateTime(timezone=True), nullable=True)
    exception_approved_at = db.Column(db.DateTime(timezone=True), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    updated_by = db.Column(db.String(120), nullable=True)

    exam_session = db.relationship("ExamSession", backref=db.backref("finance_control", uselist=False))


class ExamSessionFinanceEvent(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    finance_control_id = db.Column(db.Integer, db.ForeignKey("exam_session_finance_control.id"), nullable=False, index=True)
    event_type = db.Column(db.String(60), nullable=False, default="updated", index=True)
    previous_status = db.Column(db.String(40), nullable=True)
    new_status = db.Column(db.String(40), nullable=False)
    previous_finance_due_at = db.Column(db.Date, nullable=True)
    new_finance_due_at = db.Column(db.Date, nullable=True)
    note = db.Column(db.Text, nullable=True)
    evidence_url = db.Column(db.String(500), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    created_by = db.Column(db.String(120), nullable=True)

    finance_control = db.relationship("ExamSessionFinanceControl", backref=db.backref("events", lazy=True, cascade="all, delete-orphan"))


class ExamSessionSinapsisControl(db.Model):
    __table_args__ = (
        db.UniqueConstraint("exam_session_id", name="uq_exam_session_sinapsis_control"),
    )

    id = db.Column(db.Integer, primary_key=True)
    exam_session_id = db.Column(db.Integer, db.ForeignKey("exam_session.id"), nullable=False, index=True)
    status = db.Column(db.String(40), nullable=False, default="Not reviewed", index=True)
    sinapsis_due_at = db.Column(db.Date, nullable=True, index=True)
    evidence_url = db.Column(db.String(500), nullable=True)
    note = db.Column(db.Text, nullable=True)
    responsible_department = db.Column(db.String(40), nullable=False, default="ADMIN", index=True)
    reviewed_at = db.Column(db.DateTime(timezone=True), nullable=True)
    ready_at = db.Column(db.DateTime(timezone=True), nullable=True)
    needs_correction_at = db.Column(db.DateTime(timezone=True), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    updated_by = db.Column(db.String(120), nullable=True)

    exam_session = db.relationship("ExamSession", backref=db.backref("sinapsis_control", uselist=False))


class ExamSessionSinapsisChecklistItem(db.Model):
    __table_args__ = (
        db.UniqueConstraint("sinapsis_control_id", "item_key", name="uq_sinapsis_control_item"),
    )

    id = db.Column(db.Integer, primary_key=True)
    sinapsis_control_id = db.Column(db.Integer, db.ForeignKey("exam_session_sinapsis_control.id"), nullable=False, index=True)
    item_key = db.Column(db.String(80), nullable=False, index=True)
    label = db.Column(db.String(240), nullable=False)
    description = db.Column(db.Text, nullable=True)
    is_required = db.Column(db.Boolean, nullable=False, default=True)
    is_checked = db.Column(db.Boolean, nullable=False, default=False)
    checked_at = db.Column(db.DateTime(timezone=True), nullable=True)
    checked_by = db.Column(db.String(120), nullable=True)
    note = db.Column(db.Text, nullable=True)
    display_order = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    sinapsis_control = db.relationship("ExamSessionSinapsisControl", backref=db.backref("checklist_items", lazy=True, cascade="all, delete-orphan"))


class ExamSessionSinapsisEvent(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sinapsis_control_id = db.Column(db.Integer, db.ForeignKey("exam_session_sinapsis_control.id"), nullable=False, index=True)
    event_type = db.Column(db.String(60), nullable=False, default="updated", index=True)
    previous_status = db.Column(db.String(40), nullable=True)
    new_status = db.Column(db.String(40), nullable=False)
    note = db.Column(db.Text, nullable=True)
    evidence_url = db.Column(db.String(500), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    created_by = db.Column(db.String(120), nullable=True)

    sinapsis_control = db.relationship("ExamSessionSinapsisControl", backref=db.backref("events", lazy=True, cascade="all, delete-orphan"))


class ExamSessionCommunicationsControl(db.Model):
    __table_args__ = (
        db.UniqueConstraint("exam_session_id", name="uq_exam_session_communications_control"),
    )

    id = db.Column(db.Integer, primary_key=True)
    exam_session_id = db.Column(db.Integer, db.ForeignKey("exam_session.id"), nullable=False, index=True)
    status = db.Column(db.String(40), nullable=False, default="Not started", index=True)
    communications_due_at = db.Column(db.Date, nullable=True, index=True)
    evidence_url = db.Column(db.String(500), nullable=True)
    note = db.Column(db.Text, nullable=True)
    responsible_department = db.Column(db.String(40), nullable=False, default="ADMIN", index=True)
    started_at = db.Column(db.DateTime(timezone=True), nullable=True)
    needs_follow_up_at = db.Column(db.DateTime(timezone=True), nullable=True)
    completed_at = db.Column(db.DateTime(timezone=True), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    updated_by = db.Column(db.String(120), nullable=True)

    exam_session = db.relationship("ExamSession", backref=db.backref("communications_control", uselist=False))


class ExamSessionCommunicationsChecklistItem(db.Model):
    __table_args__ = (
        db.UniqueConstraint("communications_control_id", "group_key", "item_key", name="uq_communications_control_group_item"),
    )

    id = db.Column(db.Integer, primary_key=True)
    communications_control_id = db.Column(db.Integer, db.ForeignKey("exam_session_communications_control.id"), nullable=False, index=True)
    group_key = db.Column(db.String(40), nullable=False, index=True)
    item_key = db.Column(db.String(80), nullable=False, index=True)
    label = db.Column(db.String(240), nullable=False)
    description = db.Column(db.Text, nullable=True)
    is_required = db.Column(db.Boolean, nullable=False, default=True)
    is_checked = db.Column(db.Boolean, nullable=False, default=False)
    checked_at = db.Column(db.DateTime(timezone=True), nullable=True)
    checked_by = db.Column(db.String(120), nullable=True)
    note = db.Column(db.Text, nullable=True)
    display_order = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    communications_control = db.relationship("ExamSessionCommunicationsControl", backref=db.backref("checklist_items", lazy=True, cascade="all, delete-orphan"))


class ExamSessionCommunicationsEvent(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    communications_control_id = db.Column(db.Integer, db.ForeignKey("exam_session_communications_control.id"), nullable=False, index=True)
    event_type = db.Column(db.String(60), nullable=False, default="updated", index=True)
    previous_status = db.Column(db.String(40), nullable=True)
    new_status = db.Column(db.String(40), nullable=False)
    note = db.Column(db.Text, nullable=True)
    evidence_url = db.Column(db.String(500), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    created_by = db.Column(db.String(120), nullable=True)

    communications_control = db.relationship("ExamSessionCommunicationsControl", backref=db.backref("events", lazy=True, cascade="all, delete-orphan"))


class ExamSessionIncident(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    exam_session_id = db.Column(db.Integer, db.ForeignKey("exam_session.id"), nullable=False, index=True)
    incident_type = db.Column(db.String(80), nullable=False, index=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    severity = db.Column(db.String(20), nullable=False, default="Medium", index=True)
    status = db.Column(db.String(30), nullable=False, default="Open", index=True)
    responsible_department = db.Column(db.String(40), nullable=False, default="ADMIN", index=True)
    due_at = db.Column(db.Date, nullable=True, index=True)
    evidence_url = db.Column(db.String(500), nullable=True)
    resolution_note = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    created_by = db.Column(db.String(120), nullable=True)
    updated_by = db.Column(db.String(120), nullable=True)
    resolved_at = db.Column(db.DateTime(timezone=True), nullable=True)
    cancelled_at = db.Column(db.DateTime(timezone=True), nullable=True)

    exam_session = db.relationship("ExamSession", backref=db.backref("incidents", lazy=True, cascade="all, delete-orphan"))


class ExamSessionIncidentChecklistItem(db.Model):
    __table_args__ = (
        db.UniqueConstraint("incident_id", "item_key", name="uq_incident_item"),
    )

    id = db.Column(db.Integer, primary_key=True)
    incident_id = db.Column(db.Integer, db.ForeignKey("exam_session_incident.id"), nullable=False, index=True)
    item_key = db.Column(db.String(80), nullable=False, index=True)
    label = db.Column(db.String(260), nullable=False)
    description = db.Column(db.Text, nullable=True)
    is_required = db.Column(db.Boolean, nullable=False, default=True)
    is_checked = db.Column(db.Boolean, nullable=False, default=False)
    checked_at = db.Column(db.DateTime(timezone=True), nullable=True)
    checked_by = db.Column(db.String(120), nullable=True)
    note = db.Column(db.Text, nullable=True)
    display_order = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    incident = db.relationship("ExamSessionIncident", backref=db.backref("checklist_items", lazy=True, cascade="all, delete-orphan"))


class ExamSessionIncidentEvent(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    incident_id = db.Column(db.Integer, db.ForeignKey("exam_session_incident.id"), nullable=False, index=True)
    event_type = db.Column(db.String(60), nullable=False, default="updated", index=True)
    previous_status = db.Column(db.String(30), nullable=True)
    new_status = db.Column(db.String(30), nullable=True)
    previous_severity = db.Column(db.String(20), nullable=True)
    new_severity = db.Column(db.String(20), nullable=True)
    note = db.Column(db.Text, nullable=True)
    evidence_url = db.Column(db.String(500), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    created_by = db.Column(db.String(120), nullable=True)

    incident = db.relationship("ExamSessionIncident", backref=db.backref("events", lazy=True, cascade="all, delete-orphan"))


class ExamSessionIncidentImpactReview(db.Model):
    __table_args__ = (
        db.UniqueConstraint("incident_id", "impact_key", name="uq_incident_impact_review"),
    )

    id = db.Column(db.Integer, primary_key=True)
    incident_id = db.Column(db.Integer, db.ForeignKey("exam_session_incident.id"), nullable=False, index=True)
    impact_key = db.Column(db.String(120), nullable=False, index=True)
    affected_area = db.Column(db.String(80), nullable=False, index=True)
    status = db.Column(db.String(30), nullable=False, default="Review suggested", index=True)
    note = db.Column(db.Text, nullable=True)
    reviewed_at = db.Column(db.DateTime(timezone=True), nullable=True)
    reviewed_by = db.Column(db.String(120), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    incident = db.relationship("ExamSessionIncident", backref=db.backref("impact_reviews", lazy=True, cascade="all, delete-orphan"))


class ExamSessionIncidentReviewFlag(db.Model):
    __table_args__ = (
        db.UniqueConstraint("incident_id", "impact_key", "affected_area", name="uq_incident_review_flag"),
    )

    id = db.Column(db.Integer, primary_key=True)
    exam_session_id = db.Column(db.Integer, db.ForeignKey("exam_session.id"), nullable=False, index=True)
    incident_id = db.Column(db.Integer, db.ForeignKey("exam_session_incident.id"), nullable=False, index=True)
    impact_review_id = db.Column(db.Integer, db.ForeignKey("exam_session_incident_impact_review.id"), nullable=True, index=True)
    impact_key = db.Column(db.String(120), nullable=False, index=True)
    affected_area = db.Column(db.String(80), nullable=False, index=True)
    status = db.Column(db.String(30), nullable=False, default="Needs review", index=True)
    reason = db.Column(db.Text, nullable=True)
    note = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    created_by = db.Column(db.String(120), nullable=True)
    reviewed_at = db.Column(db.DateTime(timezone=True), nullable=True)
    reviewed_by = db.Column(db.String(120), nullable=True)
    dismissed_at = db.Column(db.DateTime(timezone=True), nullable=True)
    dismissed_by = db.Column(db.String(120), nullable=True)

    exam_session = db.relationship("ExamSession", backref=db.backref("incident_review_flags", lazy=True, cascade="all, delete-orphan"))
    incident = db.relationship("ExamSessionIncident", backref=db.backref("review_flags", lazy=True, cascade="all, delete-orphan"))
    impact_review = db.relationship("ExamSessionIncidentImpactReview", backref=db.backref("review_flags", lazy=True))


class ExamSessionPackageUnit(db.Model):
    __table_args__ = (
        db.UniqueConstraint("exam_session_id", "room_name", "module_name", name="uq_exam_session_package_unit_room_module"),
    )

    id = db.Column(db.Integer, primary_key=True)
    exam_session_id = db.Column(db.Integer, db.ForeignKey("exam_session.id"), nullable=False, index=True)
    room_name = db.Column(db.String(160), nullable=False, index=True)
    module_name = db.Column(db.String(120), nullable=False, index=True)
    expected_candidate_count = db.Column(db.Integer, nullable=True)
    actual_label_count = db.Column(db.Integer, nullable=True)
    has_nep_candidates = db.Column(db.Boolean, nullable=False, default=False)
    status = db.Column(db.String(40), nullable=False, default="Not started", index=True)
    responsible_department = db.Column(db.String(40), nullable=False, default="LOGISTICS", index=True)
    package_deadline = db.Column(db.Date, nullable=True, index=True)
    note = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    exam_session = db.relationship("ExamSession", backref=db.backref("package_units", lazy=True))


class ExamSessionPackageChecklistItem(db.Model):
    __table_args__ = (
        db.UniqueConstraint("package_unit_id", "phase", "item_key", name="uq_package_unit_phase_item"),
        db.UniqueConstraint("exam_session_id", "phase", "item_key", name="uq_package_session_phase_item"),
    )

    id = db.Column(db.Integer, primary_key=True)
    package_unit_id = db.Column(db.Integer, db.ForeignKey("exam_session_package_unit.id"), nullable=True, index=True)
    exam_session_id = db.Column(db.Integer, db.ForeignKey("exam_session.id"), nullable=True, index=True)
    scope = db.Column(db.String(20), nullable=False, default="UNIT", index=True)
    phase = db.Column(db.String(30), nullable=False, index=True)
    item_key = db.Column(db.String(80), nullable=False, index=True)
    label = db.Column(db.String(240), nullable=False)
    description = db.Column(db.Text, nullable=True)
    is_required = db.Column(db.Boolean, nullable=False, default=True)
    is_checked = db.Column(db.Boolean, nullable=False, default=False)
    checked_at = db.Column(db.DateTime(timezone=True), nullable=True)
    checked_by = db.Column(db.String(120), nullable=True)
    note = db.Column(db.Text, nullable=True)
    display_order = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    package_unit = db.relationship("ExamSessionPackageUnit", backref=db.backref("checklist_items", lazy=True, cascade="all, delete-orphan"))
    exam_session = db.relationship("ExamSession", backref=db.backref("package_session_checklist_items", lazy=True))


class ExamSessionPackageEvent(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    package_unit_id = db.Column(db.Integer, db.ForeignKey("exam_session_package_unit.id"), nullable=False, index=True)
    event_type = db.Column(db.String(60), nullable=False, index=True)
    previous_status = db.Column(db.String(40), nullable=True)
    new_status = db.Column(db.String(40), nullable=True)
    note = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    created_by = db.Column(db.String(120), nullable=True)

    package_unit = db.relationship("ExamSessionPackageUnit", backref=db.backref("events", lazy=True, cascade="all, delete-orphan"))


class ExamSessionShipmentBundle(db.Model):
    __table_args__ = (
        db.UniqueConstraint("bundle_year", "bundle_sequence", name="uq_shipment_bundle_year_sequence"),
        db.UniqueConstraint("bundle_number", name="uq_shipment_bundle_number"),
    )

    id = db.Column(db.Integer, primary_key=True)
    bundle_number = db.Column(db.String(20), nullable=True, unique=True, index=True)
    bundle_sequence = db.Column(db.Integer, nullable=True, index=True)
    bundle_year = db.Column(db.Integer, nullable=True, index=True)
    auto_managed = db.Column(db.Boolean, nullable=False, default=False, index=True)
    supervisor_staff_id = db.Column(db.Integer, db.ForeignKey("academic_staff.id"), nullable=False, index=True)
    delivery_address = db.Column(db.String(500), nullable=False)
    delivery_city = db.Column(db.String(120), nullable=True, index=True)
    delivery_province = db.Column(db.String(120), nullable=True, index=True)
    courier = db.Column(db.String(120), nullable=False, default="Correo Argentino", index=True)
    tracking_number = db.Column(db.String(160), nullable=True, index=True)
    status = db.Column(db.String(60), nullable=False, default="Preparing bundle", index=True)
    dispatch_due_at = db.Column(db.Date, nullable=True, index=True)
    dispatched_at = db.Column(db.DateTime(timezone=True), nullable=True)
    delivered_at = db.Column(db.DateTime(timezone=True), nullable=True)
    recipient_reviewed_at = db.Column(db.DateTime(timezone=True), nullable=True)
    split_from_bundle_id = db.Column(db.Integer, db.ForeignKey("exam_session_shipment_bundle.id"), nullable=True, index=True)
    auto_split_at = db.Column(db.DateTime(timezone=True), nullable=True)
    responsible_department = db.Column(db.String(40), nullable=False, default="LOGISTICS", index=True)
    note = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    created_by = db.Column(db.String(120), nullable=True)
    updated_by = db.Column(db.String(120), nullable=True)

    supervisor = db.relationship("AcademicStaff", backref=db.backref("shipment_bundles", lazy=True))
    split_from_bundle = db.relationship("ExamSessionShipmentBundle", remote_side=[id])


class ExamSessionShipmentBundleSession(db.Model):
    __table_args__ = (
        db.UniqueConstraint("bundle_id", "exam_session_id", name="uq_shipment_bundle_session"),
        db.UniqueConstraint("exam_session_id", name="uq_shipment_session_active_bundle"),
    )

    id = db.Column(db.Integer, primary_key=True)
    bundle_id = db.Column(db.Integer, db.ForeignKey("exam_session_shipment_bundle.id"), nullable=False, index=True)
    exam_session_id = db.Column(db.Integer, db.ForeignKey("exam_session.id"), nullable=False, index=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    bundle = db.relationship("ExamSessionShipmentBundle", backref=db.backref("session_links", lazy=True, cascade="all, delete-orphan"))
    exam_session = db.relationship("ExamSession", backref=db.backref("shipment_bundle_links", lazy=True))


class ExamSessionShipmentChecklistItem(db.Model):
    __table_args__ = (
        db.UniqueConstraint("bundle_id", "item_key", name="uq_shipment_bundle_item"),
    )

    id = db.Column(db.Integer, primary_key=True)
    bundle_id = db.Column(db.Integer, db.ForeignKey("exam_session_shipment_bundle.id"), nullable=False, index=True)
    item_key = db.Column(db.String(80), nullable=False, index=True)
    label = db.Column(db.String(240), nullable=False)
    description = db.Column(db.Text, nullable=True)
    is_required = db.Column(db.Boolean, nullable=False, default=True)
    is_checked = db.Column(db.Boolean, nullable=False, default=False)
    checked_at = db.Column(db.DateTime(timezone=True), nullable=True)
    checked_by = db.Column(db.String(120), nullable=True)
    note = db.Column(db.Text, nullable=True)
    display_order = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    bundle = db.relationship("ExamSessionShipmentBundle", backref=db.backref("checklist_items", lazy=True, cascade="all, delete-orphan"))


class ExamSessionShipmentEvent(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    bundle_id = db.Column(db.Integer, db.ForeignKey("exam_session_shipment_bundle.id"), nullable=False, index=True)
    event_type = db.Column(db.String(80), nullable=False, index=True)
    previous_status = db.Column(db.String(60), nullable=True)
    new_status = db.Column(db.String(60), nullable=True)
    note = db.Column(db.Text, nullable=True)
    tracking_number = db.Column(db.String(160), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    created_by = db.Column(db.String(120), nullable=True)

    bundle = db.relationship("ExamSessionShipmentBundle", backref=db.backref("events", lazy=True, cascade="all, delete-orphan"))


class ExamSessionScheduleEvent(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    workflow_id = db.Column(db.Integer, db.ForeignKey("exam_session_schedule_workflow.id"), nullable=False, index=True)
    previous_status = db.Column(db.String(40), nullable=False)
    new_status = db.Column(db.String(40), nullable=False)
    note = db.Column(db.Text, nullable=True)
    due_at = db.Column(db.Date, nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    created_by = db.Column(db.String(120), nullable=True)

    workflow = db.relationship("ExamSessionScheduleWorkflow", backref=db.backref("events", lazy=True, cascade="all, delete-orphan"))


class StaffPayment(db.Model):
    __table_args__ = (
        db.UniqueConstraint("member_id", "year", name="uq_staff_payment_member_year"),
    )

    id = db.Column(db.Integer, primary_key=True)
    member_id = db.Column(db.Integer, db.ForeignKey("academic_staff.id"), nullable=False, index=True)
    year = db.Column(db.Integer, nullable=False, index=True)
    invoice_verified = db.Column(db.Boolean, nullable=False, default=False)
    payment_completed = db.Column(db.Boolean, nullable=False, default=False)
    status = db.Column(db.String(20), nullable=False, default="Pending", index=True)
    created_on = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_on = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    member = db.relationship("AcademicStaff", backref=db.backref("staff_payments", lazy=True))


class ExamSessionSupervisorAssignment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    exam_session_id = db.Column(db.Integer, db.ForeignKey("exam_session.id"), nullable=False, index=True)
    non_available_member_ids = db.Column(db.Text, nullable=False, default="[]")
    team_member_id = db.Column(db.Integer, db.ForeignKey("academic_staff.id"), nullable=True, index=True)
    participation_status = db.Column(db.String(40), nullable=False, default="Pending", index=True)
    logistics_enabled = db.Column(db.Boolean, nullable=False, default=False)
    logistics_type = db.Column(db.String(40), nullable=False, default="Does not apply", index=True)
    manual_fee_override = db.Column(db.Boolean, nullable=False, default=False)
    km = db.Column(db.Integer, nullable=True)
    start_time = db.Column(db.String(5), nullable=True)
    end_time = db.Column(db.String(5), nullable=True)
    time_ranges = db.Column(db.Text, nullable=True)
    role_fee = db.Column(db.String(80), nullable=True)
    role_fee_currency = db.Column(db.String(3), nullable=True)
    role_fee_base_value = db.Column(db.String(40), nullable=True)
    role_fee_unit = db.Column(db.String(30), nullable=True)
    role_fee_last_calculated_on = db.Column(db.DateTime(timezone=True), nullable=True)
    role_fee_last_recalculated_on = db.Column(db.DateTime(timezone=True), nullable=True)
    device_dep = db.Column(db.String(80), nullable=True)
    device_dep_currency = db.Column(db.String(3), nullable=True)
    device_dep_base_value = db.Column(db.String(40), nullable=True)
    device_dep_unit = db.Column(db.String(30), nullable=True)
    device_dep_last_calculated_on = db.Column(db.DateTime(timezone=True), nullable=True)
    device_dep_last_recalculated_on = db.Column(db.DateTime(timezone=True), nullable=True)
    commuting = db.Column(db.String(80), nullable=True)
    commuting_currency = db.Column(db.String(3), nullable=True)
    commuting_base_value = db.Column(db.String(40), nullable=True)
    commuting_unit = db.Column(db.String(30), nullable=True)
    commuting_last_calculated_on = db.Column(db.DateTime(timezone=True), nullable=True)
    commuting_last_recalculated_on = db.Column(db.DateTime(timezone=True), nullable=True)
    fuel = db.Column(db.String(80), nullable=True)
    fuel_enabled = db.Column(db.Boolean, nullable=False, default=False)
    fuel_currency = db.Column(db.String(3), nullable=True)
    fuel_base_value = db.Column(db.String(40), nullable=True)
    fuel_unit = db.Column(db.String(30), nullable=True)
    fuel_last_calculated_on = db.Column(db.DateTime(timezone=True), nullable=True)
    fuel_last_recalculated_on = db.Column(db.DateTime(timezone=True), nullable=True)
    vehicle_dep = db.Column(db.String(80), nullable=True)
    vehicle_dep_currency = db.Column(db.String(3), nullable=True)
    vehicle_dep_base_value = db.Column(db.String(40), nullable=True)
    vehicle_dep_unit = db.Column(db.String(30), nullable=True)
    vehicle_dep_last_calculated_on = db.Column(db.DateTime(timezone=True), nullable=True)
    vehicle_dep_last_recalculated_on = db.Column(db.DateTime(timezone=True), nullable=True)
    seniority_fee = db.Column(db.String(80), nullable=True)
    seniority_applied = db.Column(db.Boolean, nullable=False, default=False)
    seniority_percentage = db.Column(db.String(10), nullable=True)
    seniority_currency = db.Column(db.String(3), nullable=True)
    seniority_last_calculated_on = db.Column(db.DateTime(timezone=True), nullable=True)
    seniority_last_recalculated_on = db.Column(db.DateTime(timezone=True), nullable=True)
    fee_frozen_on = db.Column(db.DateTime(timezone=True), nullable=True)
    fee_frozen_status = db.Column(db.String(40), nullable=True)
    created_on = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_on = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    exam_session = db.relationship("ExamSession", backref=db.backref("supervisor_assignments", lazy=True))
    team_member = db.relationship("AcademicStaff", foreign_keys=[team_member_id])

    def non_available_ids(self):
        try:
            return [int(value) for value in json.loads(self.non_available_member_ids or "[]")]
        except (TypeError, ValueError, json.JSONDecodeError):
            return []

    def time_ranges_list(self):
        try:
            ranges = json.loads(self.time_ranges or "[]")
        except (TypeError, ValueError, json.JSONDecodeError):
            ranges = []
        clean_ranges = [
            {
                "start": (item.get("start") or "").strip(),
                "end": (item.get("end") or "").strip(),
            }
            for item in ranges
            if isinstance(item, dict)
        ]
        if clean_ranges:
            return clean_ranges
        if self.start_time or self.end_time:
            return [{"start": self.start_time or "", "end": self.end_time or ""}]
        return [{"start": "", "end": ""}]


class ExamSessionExaminerAssignment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    exam_session_id = db.Column(db.Integer, db.ForeignKey("exam_session.id"), nullable=False, index=True)
    non_available_member_ids = db.Column(db.Text, nullable=False, default="[]")
    team_member_id = db.Column(db.Integer, db.ForeignKey("academic_staff.id"), nullable=True, index=True)
    participation_status = db.Column(db.String(40), nullable=False, default="Pending", index=True)
    logistics_enabled = db.Column(db.Boolean, nullable=False, default=False)
    logistics_type = db.Column(db.String(40), nullable=False, default="Does not apply", index=True)
    manual_fee_override = db.Column(db.Boolean, nullable=False, default=False)
    km = db.Column(db.Integer, nullable=True)
    start_time = db.Column(db.String(5), nullable=True)
    end_time = db.Column(db.String(5), nullable=True)
    time_ranges = db.Column(db.Text, nullable=True)
    role_fee = db.Column(db.String(80), nullable=True)
    role_fee_currency = db.Column(db.String(3), nullable=True)
    role_fee_base_value = db.Column(db.String(40), nullable=True)
    role_fee_unit = db.Column(db.String(30), nullable=True)
    role_fee_last_calculated_on = db.Column(db.DateTime(timezone=True), nullable=True)
    role_fee_last_recalculated_on = db.Column(db.DateTime(timezone=True), nullable=True)
    device_dep = db.Column(db.String(80), nullable=True)
    device_dep_currency = db.Column(db.String(3), nullable=True)
    device_dep_base_value = db.Column(db.String(40), nullable=True)
    device_dep_unit = db.Column(db.String(30), nullable=True)
    device_dep_last_calculated_on = db.Column(db.DateTime(timezone=True), nullable=True)
    device_dep_last_recalculated_on = db.Column(db.DateTime(timezone=True), nullable=True)
    commuting = db.Column(db.String(80), nullable=True)
    commuting_currency = db.Column(db.String(3), nullable=True)
    commuting_base_value = db.Column(db.String(40), nullable=True)
    commuting_unit = db.Column(db.String(30), nullable=True)
    commuting_last_calculated_on = db.Column(db.DateTime(timezone=True), nullable=True)
    commuting_last_recalculated_on = db.Column(db.DateTime(timezone=True), nullable=True)
    fuel = db.Column(db.String(80), nullable=True)
    fuel_enabled = db.Column(db.Boolean, nullable=False, default=False)
    fuel_currency = db.Column(db.String(3), nullable=True)
    fuel_base_value = db.Column(db.String(40), nullable=True)
    fuel_unit = db.Column(db.String(30), nullable=True)
    fuel_last_calculated_on = db.Column(db.DateTime(timezone=True), nullable=True)
    fuel_last_recalculated_on = db.Column(db.DateTime(timezone=True), nullable=True)
    vehicle_dep = db.Column(db.String(80), nullable=True)
    vehicle_dep_currency = db.Column(db.String(3), nullable=True)
    vehicle_dep_base_value = db.Column(db.String(40), nullable=True)
    vehicle_dep_unit = db.Column(db.String(30), nullable=True)
    vehicle_dep_last_calculated_on = db.Column(db.DateTime(timezone=True), nullable=True)
    vehicle_dep_last_recalculated_on = db.Column(db.DateTime(timezone=True), nullable=True)
    seniority_fee = db.Column(db.String(80), nullable=True)
    seniority_applied = db.Column(db.Boolean, nullable=False, default=False)
    seniority_percentage = db.Column(db.String(10), nullable=True)
    seniority_currency = db.Column(db.String(3), nullable=True)
    seniority_last_calculated_on = db.Column(db.DateTime(timezone=True), nullable=True)
    seniority_last_recalculated_on = db.Column(db.DateTime(timezone=True), nullable=True)
    fee_frozen_on = db.Column(db.DateTime(timezone=True), nullable=True)
    fee_frozen_status = db.Column(db.String(40), nullable=True)
    created_on = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_on = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    exam_session = db.relationship("ExamSession", backref=db.backref("examiner_assignments", lazy=True))
    team_member = db.relationship("AcademicStaff", foreign_keys=[team_member_id])

    def non_available_ids(self):
        try:
            return [int(value) for value in json.loads(self.non_available_member_ids or "[]")]
        except (TypeError, ValueError, json.JSONDecodeError):
            return []

    def time_ranges_list(self):
        try:
            ranges = json.loads(self.time_ranges or "[]")
        except (TypeError, ValueError, json.JSONDecodeError):
            ranges = []
        clean_ranges = [
            {
                "start": (item.get("start") or "").strip(),
                "end": (item.get("end") or "").strip(),
            }
            for item in ranges
            if isinstance(item, dict)
        ]
        if clean_ranges:
            return clean_ranges
        if self.start_time or self.end_time:
            return [{"start": self.start_time or "", "end": self.end_time or ""}]
        return [{"start": "", "end": ""}]


class ExamSessionInternAssignment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    exam_session_id = db.Column(db.Integer, db.ForeignKey("exam_session.id"), nullable=False, index=True)
    non_available_member_ids = db.Column(db.Text, nullable=False, default="[]")
    team_member_id = db.Column(db.Integer, db.ForeignKey("academic_staff.id"), nullable=True, index=True)
    participation_status = db.Column(db.String(40), nullable=False, default="Pending", index=True)
    logistics_enabled = db.Column(db.Boolean, nullable=False, default=False)
    logistics_type = db.Column(db.String(40), nullable=False, default="Does not apply", index=True)
    manual_fee_override = db.Column(db.Boolean, nullable=False, default=False)
    km = db.Column(db.Integer, nullable=True)
    start_time = db.Column(db.String(5), nullable=True)
    end_time = db.Column(db.String(5), nullable=True)
    time_ranges = db.Column(db.Text, nullable=True)
    role_fee = db.Column(db.String(80), nullable=True)
    role_fee_currency = db.Column(db.String(3), nullable=True)
    role_fee_base_value = db.Column(db.String(40), nullable=True)
    role_fee_unit = db.Column(db.String(30), nullable=True)
    role_fee_last_calculated_on = db.Column(db.DateTime(timezone=True), nullable=True)
    role_fee_last_recalculated_on = db.Column(db.DateTime(timezone=True), nullable=True)
    device_dep = db.Column(db.String(80), nullable=True)
    device_dep_currency = db.Column(db.String(3), nullable=True)
    device_dep_base_value = db.Column(db.String(40), nullable=True)
    device_dep_unit = db.Column(db.String(30), nullable=True)
    device_dep_last_calculated_on = db.Column(db.DateTime(timezone=True), nullable=True)
    device_dep_last_recalculated_on = db.Column(db.DateTime(timezone=True), nullable=True)
    commuting = db.Column(db.String(80), nullable=True)
    commuting_currency = db.Column(db.String(3), nullable=True)
    commuting_base_value = db.Column(db.String(40), nullable=True)
    commuting_unit = db.Column(db.String(30), nullable=True)
    commuting_last_calculated_on = db.Column(db.DateTime(timezone=True), nullable=True)
    commuting_last_recalculated_on = db.Column(db.DateTime(timezone=True), nullable=True)
    fuel = db.Column(db.String(80), nullable=True)
    fuel_enabled = db.Column(db.Boolean, nullable=False, default=False)
    fuel_currency = db.Column(db.String(3), nullable=True)
    fuel_base_value = db.Column(db.String(40), nullable=True)
    fuel_unit = db.Column(db.String(30), nullable=True)
    fuel_last_calculated_on = db.Column(db.DateTime(timezone=True), nullable=True)
    fuel_last_recalculated_on = db.Column(db.DateTime(timezone=True), nullable=True)
    vehicle_dep = db.Column(db.String(80), nullable=True)
    vehicle_dep_currency = db.Column(db.String(3), nullable=True)
    vehicle_dep_base_value = db.Column(db.String(40), nullable=True)
    vehicle_dep_unit = db.Column(db.String(30), nullable=True)
    vehicle_dep_last_calculated_on = db.Column(db.DateTime(timezone=True), nullable=True)
    vehicle_dep_last_recalculated_on = db.Column(db.DateTime(timezone=True), nullable=True)
    seniority_fee = db.Column(db.String(80), nullable=True)
    seniority_applied = db.Column(db.Boolean, nullable=False, default=False)
    seniority_percentage = db.Column(db.String(10), nullable=True)
    seniority_currency = db.Column(db.String(3), nullable=True)
    seniority_last_calculated_on = db.Column(db.DateTime(timezone=True), nullable=True)
    seniority_last_recalculated_on = db.Column(db.DateTime(timezone=True), nullable=True)
    fee_frozen_on = db.Column(db.DateTime(timezone=True), nullable=True)
    fee_frozen_status = db.Column(db.String(40), nullable=True)
    created_on = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_on = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    exam_session = db.relationship("ExamSession", backref=db.backref("intern_assignments", lazy=True))
    team_member = db.relationship("AcademicStaff", foreign_keys=[team_member_id])

    def non_available_ids(self):
        try:
            return [int(value) for value in json.loads(self.non_available_member_ids or "[]")]
        except (TypeError, ValueError, json.JSONDecodeError):
            return []

    def time_ranges_list(self):
        try:
            ranges = json.loads(self.time_ranges or "[]")
        except (TypeError, ValueError, json.JSONDecodeError):
            ranges = []
        clean_ranges = [
            {
                "start": (item.get("start") or "").strip(),
                "end": (item.get("end") or "").strip(),
            }
            for item in ranges
            if isinstance(item, dict)
        ]
        if clean_ranges:
            return clean_ranges
        if self.start_time or self.end_time:
            return [{"start": self.start_time or "", "end": self.end_time or ""}]
        return [{"start": "", "end": ""}]


class ExamSessionMonthlyRegistration(db.Model):
    __table_args__ = (
        db.UniqueConstraint("exam_session_id", "month", "module", name="uq_exam_session_month_module"),
    )

    id = db.Column(db.Integer, primary_key=True)
    exam_session_id = db.Column(db.Integer, db.ForeignKey("exam_session.id"), nullable=False, index=True)
    month = db.Column(db.Integer, nullable=False, index=True)
    module = db.Column(db.String(80), nullable=False, index=True)
    registration_number = db.Column(db.Integer, nullable=False, default=0)
    created_on = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_on = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    exam_session = db.relationship("ExamSession", backref=db.backref("monthly_registrations", lazy=True))


class ExamSessionMonthlyCandidateTotal(db.Model):
    __table_args__ = (
        db.UniqueConstraint("exam_session_id", "month", name="uq_exam_session_month_candidate_total"),
    )

    id = db.Column(db.Integer, primary_key=True)
    exam_session_id = db.Column(db.Integer, db.ForeignKey("exam_session.id"), nullable=False, index=True)
    month = db.Column(db.Integer, nullable=False, index=True)
    total_candidates = db.Column(db.Integer, nullable=False, default=0)
    created_on = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_on = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    exam_session = db.relationship("ExamSession", backref=db.backref("monthly_candidate_totals", lazy=True))


class ExamSessionLogistics(db.Model):
    __table_args__ = (
        db.UniqueConstraint("exam_session_id", name="uq_exam_session_logistics"),
    )

    id = db.Column(db.Integer, primary_key=True)
    exam_session_id = db.Column(db.Integer, db.ForeignKey("exam_session.id"), nullable=False, index=True)
    logistics_files_url = db.Column(db.String(500), nullable=True)
    created_on = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_on = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    exam_session = db.relationship("ExamSession", backref=db.backref("logistics_config", uselist=False))


class ExamSessionLogisticsConcept(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    exam_session_id = db.Column(db.Integer, db.ForeignKey("exam_session.id"), nullable=False, index=True)
    status = db.Column(db.String(30), nullable=False, default="Pending", index=True)
    provider_id = db.Column(db.Integer, db.ForeignKey("provider.id"), nullable=True, index=True)
    provider = db.Column(db.String(160), nullable=False, default="", index=True)
    currency = db.Column(db.String(3), nullable=False, default="ARS", index=True)
    fee = db.Column(db.Integer, nullable=True)
    created_on = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_on = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    exam_session = db.relationship("ExamSession", backref=db.backref("logistics_concepts", lazy=True))
    provider_record = db.relationship("Provider", foreign_keys=[provider_id])


class ExamSessionLogisticsConceptNote(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    logistics_concept_id = db.Column(db.Integer, db.ForeignKey("exam_session_logistics_concept.id"), nullable=False, index=True)
    comment = db.Column(db.Text, nullable=False)
    created_by = db.Column(db.String(120), nullable=True)
    created_on = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    logistics_concept = db.relationship("ExamSessionLogisticsConcept", backref=db.backref("notes", lazy=True))


class PotentialEntry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    status = db.Column(db.String(40), nullable=False, index=True)
    full_name = db.Column(db.String(160), nullable=False, index=True)
    phone = db.Column(db.String(80), nullable=True)
    email = db.Column(db.String(160), nullable=True, index=True)
    city = db.Column(db.String(120), nullable=True, index=True)
    province = db.Column(db.String(120), nullable=True, index=True)
    cv = db.Column(db.String(500), nullable=True)
    interview_date = db.Column(db.String(10), nullable=True)
    interview_time = db.Column(db.String(8), nullable=True)
    platform = db.Column(db.String(20), nullable=True)
    interviewer = db.Column(db.String(220), nullable=True)
    interview = db.Column(db.Text, nullable=True)
    is_rejected = db.Column(db.Boolean, nullable=False, default=False, index=True)
    rejected_on = db.Column(db.DateTime(timezone=True), nullable=True)
    created_on = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_on = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    def roles_list(self):
        return []
