from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from .forms import PayrollRecordForm
from .models import Department, Employee, PayrollRecord

User = get_user_model()


class PayrollTests(TestCase):
    def setUp(self):
        self.department = Department.objects.create(name="Payroll Department")
        self.employee = Employee.objects.create(
            employee_id="PAY001",
            full_name="Jordan Smith",
            email="jordan@example.com",
            designation="Analyst",
            department=self.department,
        )
        self.hr = User.objects.create_user(username="payroll-hr", password="SafePassword123!")
        self.hr.groups.add(Group.objects.get(name="HR"))
        self.admin = User.objects.create_user(
            username="payroll-admin",
            password="SafePassword123!",
            is_superuser=True,
            is_staff=True,
        )
        self.ordinary_user = User.objects.create_user(
            username="payroll-employee",
            password="SafePassword123!",
        )

    def create_record(self, **overrides):
        values = {
            "employee": self.employee,
            "pay_month": date(2026, 5, 1),
            "basic_salary": Decimal("5000.00"),
            "allowances": Decimal("750.00"),
            "deductions": Decimal("250.00"),
            "payment_status": "PAID",
            "payment_date": date(2026, 5, 28),
        }
        values.update(overrides)
        return PayrollRecord.objects.create(**values)

    def test_gross_and_net_salary_calculations(self):
        record = self.create_record()
        self.assertEqual(record.gross_salary, Decimal("5750.00"))
        self.assertEqual(record.net_salary, Decimal("5500.00"))

    def test_form_accepts_month_input_and_saves_first_day(self):
        form = PayrollRecordForm(data={
            "employee": self.employee.pk,
            "pay_month": "2026-05",
            "basic_salary": "5000.00",
            "allowances": "750.00",
            "deductions": "250.00",
            "payment_date": "2026-05-28",
            "payment_status": "PAID",
        })
        self.assertTrue(form.is_valid(), form.errors)
        record = form.save()
        self.assertEqual(record.pay_month, date(2026, 5, 1))

    def test_form_rejects_negative_amounts_and_excess_deductions(self):
        negative_amount_form = PayrollRecordForm(data={
            "employee": self.employee.pk,
            "pay_month": "2026-05",
            "basic_salary": "-1.00",
            "allowances": "0.00",
            "deductions": "0.00",
            "payment_date": "",
            "payment_status": "PENDING",
        })
        self.assertFalse(negative_amount_form.is_valid())
        self.assertIn("basic_salary", negative_amount_form.errors)

        excess_deduction_form = PayrollRecordForm(data={
            "employee": self.employee.pk,
            "pay_month": "2026-05",
            "basic_salary": "100.00",
            "allowances": "20.00",
            "deductions": "121.00",
            "payment_date": "",
            "payment_status": "PENDING",
        })
        self.assertFalse(excess_deduction_form.is_valid())
        self.assertIn("deductions", excess_deduction_form.errors)

    def test_database_constraints_reject_negative_amounts(self):
        record = PayrollRecord(
            employee=self.employee,
            pay_month=date(2026, 6, 1),
            basic_salary=Decimal("-1.00"),
            allowances=Decimal("0.00"),
            deductions=Decimal("0.00"),
        )
        with self.assertRaises(ValidationError):
            record.full_clean()

    def test_form_prevents_duplicate_employee_month(self):
        self.create_record()
        duplicate_form = PayrollRecordForm(data={
            "employee": self.employee.pk,
            "pay_month": "2026-05",
            "basic_salary": "5000.00",
            "allowances": "0.00",
            "deductions": "0.00",
            "payment_date": "",
            "payment_status": "PENDING",
        })
        self.assertFalse(duplicate_form.is_valid())
        self.assertIn("__all__", duplicate_form.errors)

    def test_payroll_permissions_are_granted_to_admin_and_hr_groups(self):
        for group_name in ("Admin", "HR"):
            group = Group.objects.get(name=group_name)
            for action in ("add", "change", "delete", "view"):
                with self.subTest(group=group_name, action=action):
                    self.assertTrue(group.permissions.filter(
                        content_type__app_label="core",
                        content_type__model="payrollrecord",
                        codename=f"{action}_payrollrecord",
                    ).exists())

    def test_payroll_views_require_authorized_role(self):
        self.assertEqual(self.client.get(reverse("payroll_list")).status_code, 403)
        self.client.force_login(self.ordinary_user)
        for url_name in ("payroll_list", "payroll_create", "payroll_export_csv"):
            with self.subTest(url=url_name):
                self.assertEqual(self.client.get(reverse(url_name)).status_code, 403)
        self.assertEqual(
            self.client.get(reverse("payroll_history", args=[self.employee.pk])).status_code,
            403,
        )

    def test_hr_can_create_view_and_export_payroll(self):
        self.client.force_login(self.hr)
        self.assertEqual(self.client.get(reverse("payroll_list")).status_code, 200)
        self.assertEqual(self.client.get(reverse("payroll_create")).status_code, 200)
        response = self.client.post(reverse("payroll_create"), data={
            "employee": self.employee.pk,
            "pay_month": "2026-05",
            "basic_salary": "5000.00",
            "allowances": "750.00",
            "deductions": "250.00",
            "payment_date": "2026-05-28",
            "payment_status": "PAID",
        })
        self.assertRedirects(response, reverse("payroll_history", args=[self.employee.pk]))
        self.assertTrue(PayrollRecord.objects.filter(employee=self.employee).exists())
        export = self.client.get(reverse("payroll_export_csv"))
        self.assertEqual(export.status_code, 200)
        self.assertIn("5500.00", export.content.decode())

    def test_monthly_summary_filters_and_employee_history(self):
        self.create_record()
        self.create_record(
            employee=Employee.objects.create(
                employee_id="PAY002",
                full_name="Taylor Lee",
                email="taylor@example.com",
                designation="Coordinator",
                department=self.department,
            ),
            pay_month=date(2026, 6, 1),
            payment_date=date(2026, 6, 28),
        )
        self.client.force_login(self.hr)
        response = self.client.get(reverse("payroll_list"), {"year": "2026", "month": "5"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["record_count"], 1)
        self.assertEqual(response.context["totals"]["net_total"], Decimal("5500.00"))
        self.assertEqual(len(response.context["monthly_summaries"]), 1)
        self.assertEqual(
            response.context["monthly_summaries"][0]["gross_total"],
            Decimal("5750.00"),
        )

        history = self.client.get(reverse("payroll_history", args=[self.employee.pk]))
        self.assertEqual(history.status_code, 200)
        self.assertEqual(history.context["records"].count(), 1)
