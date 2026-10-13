from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

from .models import Department, Employee, PayrollRecord
from .payslips import payslip_values

User = get_user_model()


class PayslipTests(TestCase):
    def setUp(self):
        self.department = Department.objects.create(name="Finance")
        self.employee = Employee.objects.create(
            employee_id="SLIP007",
            full_name="Asha Patel",
            email="asha@example.com",
            designation="Payroll Analyst",
            department=self.department,
        )
        self.record = PayrollRecord.objects.create(
            employee=self.employee,
            pay_month=date(2026, 9, 1),
            basic_salary=Decimal("65000.00"),
            allowances=Decimal("8500.50"),
            deductions=Decimal("2500.25"),
            payment_status="ON_HOLD",
            payment_date=None,
        )
        self.hr = User.objects.create_user(
            username="payslip-hr",
            password="SafePassword123!",
        )
        self.hr.groups.add(Group.objects.get(name="HR"))
        self.regular_user = User.objects.create_user(
            username="asha-account",
            email=self.employee.email,
            password="SafePassword123!",
        )

    def test_payslip_data_uses_stored_payroll_values_and_currency_format(self):
        values = payslip_values(self.record)

        self.assertEqual(values["company_name"], "Employee Management System")
        self.assertEqual(values["employee_name"], "Asha Patel")
        self.assertEqual(values["employee_id"], "SLIP007")
        self.assertEqual(values["department"], "Finance")
        self.assertEqual(values["designation"], "Payroll Analyst")
        self.assertEqual(values["pay_month"], "September 2026")
        self.assertEqual(values["payment_status"], "ON HOLD")
        self.assertEqual(values["payment_date"], "Not recorded")
        self.assertEqual(values["basic_salary"], "₹65,000.00")
        self.assertEqual(values["allowances"], "₹8,500.50")
        self.assertEqual(values["gross_salary"], "₹73,500.50")
        self.assertEqual(values["deductions"], "₹2,500.25")
        self.assertEqual(values["net_salary"], "₹71,000.25")

    def test_authorized_user_downloads_valid_pdf_without_changing_payment_status(self):
        self.client.force_login(self.hr)

        response = self.client.get(
            reverse("payroll_payslip", args=[self.record.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertIn("attachment;", response["Content-Disposition"])
        self.assertIn("payslip-SLIP007-2026-09.pdf", response["Content-Disposition"])
        self.assertTrue(response.content.startswith(b"%PDF-"))
        self.assertIn(b"%%EOF", response.content)
        self.record.refresh_from_db()
        self.assertEqual(self.record.payment_status, "ON_HOLD")

    def test_payroll_list_and_employee_history_link_to_payslip(self):
        self.client.force_login(self.hr)
        list_response = self.client.get(reverse("payroll_list"))
        history_response = self.client.get(
            reverse("payroll_history", args=[self.employee.pk])
        )
        payslip_url = reverse("payroll_payslip", args=[self.record.pk])

        self.assertContains(list_response, payslip_url)
        self.assertContains(history_response, payslip_url)

    def test_payslip_requires_authentication_and_payroll_permission(self):
        url = reverse("payroll_payslip", args=[self.record.pk])
        anonymous_response = self.client.get(url)
        self.assertRedirects(anonymous_response, f"/login/?next={url}")

        self.client.force_login(self.regular_user)
        self.assertEqual(self.client.get(url).status_code, 403)

    def test_missing_payroll_record_returns_not_found_to_authorized_user(self):
        self.client.force_login(self.hr)
        response = self.client.get(
            reverse("payroll_payslip", args=[self.record.pk + 1000])
        )
        self.assertEqual(response.status_code, 404)

    def test_paid_status_is_reported_only_when_payroll_record_is_paid(self):
        self.record.payment_status = "PAID"
        self.record.payment_date = date(2026, 10, 5)
        self.record.save(update_fields=["payment_status", "payment_date"])

        values = payslip_values(self.record)

        self.assertEqual(values["payment_status"], "PAID")
        self.assertEqual(values["payment_date"], "05 October 2026")
        self.record.refresh_from_db()
        self.assertEqual(self.record.payment_status, "PAID")
