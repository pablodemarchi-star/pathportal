import os
import unittest
from io import BytesIO

os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from openpyxl import load_workbook

from app import create_app, db
from app.models import AcademicStaff
from app.routes import apply_import_row, build_academic_staff_export, parse_import_workbook


class StaffExportTest(unittest.TestCase):
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

    def test_academic_staff_export_excludes_removed_columns(self):
        member = AcademicStaff(
            id=7,
            status="Active",
            full_name="Jane Staff",
            roles="Examiner",
            email="jane@example.com",
            has_car="Yes",
            full_address_google_maps="742 Evergreen Terrace",
            street_name="Old Street",
            street_number="123",
            city="Springfield",
            postcode="ABC123",
            province="Buenos Aires",
            country="Argentina",
            started_in="2024",
            location_point="https://maps.example.com/location-point",
            cv="https://example.com/cv.pdf",
            profile_picture="https://example.com/profile.jpg",
        )

        workbook_bytes = build_academic_staff_export([member], session_counts={member.id: 3})
        workbook = load_workbook(BytesIO(workbook_bytes))
        sheet = workbook.active

        headers = [cell.value for cell in sheet[3]]
        first_data_row = [cell.value for cell in sheet[4]]

        self.assertNotIn("Location point", headers)
        self.assertNotIn("Updated on", headers)
        self.assertNotIn("Street name", headers)
        self.assertNotIn("Street number", headers)
        self.assertNotIn("Postcode", headers)
        self.assertEqual(headers.index("Full address"), headers.index("Has a car") + 1)
        self.assertEqual(headers.index("Sessions"), headers.index("Started in") + 1)
        self.assertEqual(first_data_row[headers.index("Full address")], member.full_address_google_maps)
        self.assertEqual(first_data_row[headers.index("Sessions")], 3)
        self.assertNotIn("https://maps.example.com/location-point", first_data_row)
        self.assertNotIn("Old Street", first_data_row)
        self.assertNotIn("123", first_data_row)
        self.assertNotIn("ABC123", first_data_row)
        self.assertEqual(sheet.cell(row=4, column=headers.index("CV") + 1).hyperlink.target, member.cv)
        self.assertEqual(
            sheet.cell(row=4, column=headers.index("Profile picture") + 1).hyperlink.target,
            member.profile_picture,
        )

    def test_exported_full_address_is_imported(self):
        source_member = AcademicStaff(
            id=8,
            status="Active",
            full_name="John Staff",
            roles="Supervisor",
            email="john@example.com",
            has_car="No",
            full_address_google_maps="Av. Siempre Viva 123",
            city="CABA",
            province="Buenos Aires",
            country="Argentina",
            started_in="2025",
        )
        workbook_bytes = build_academic_staff_export([source_member], session_counts={source_member.id: 2})

        payload = parse_import_workbook(BytesIO(workbook_bytes), update_empty_fields=False)
        self.assertEqual(payload["unknown_headers"], [])
        self.assertEqual(payload["summary"]["ready"], 1)

        row_data = payload["rows"][0]["data"]
        self.assertEqual(row_data["Full address"], source_member.full_address_google_maps)

        imported_member = AcademicStaff()
        apply_import_row(imported_member, row_data, update_empty_fields=True)
        self.assertEqual(imported_member.full_address_google_maps, source_member.full_address_google_maps)


if __name__ == "__main__":
    unittest.main()
