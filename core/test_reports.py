import csv
from datetime import date
from io import StringIO

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

from .models import Attendance, Department, Employee, LeaveRequest


class ReportsTests(TestCase):
    def setUp(self):
        self.staff = get_user_model().objects.create_user(
            username="report-staff",
            password="test-password",
            is_staff=True,
        )
        self.staff.groups.add(Group.objects.get(name="HR"))
        self.department = Department.objects.create(name="Engineering")
        self.other_department = Department.objects.create(name="Operations")
        self.employee = Employee.objects.create(
            employee_id="RPT001",
            full_name="Asha Rao",
            email="asha@example.com",
            designation="Engineer",
            department=self.department,
            joining_date=date(2025, 1, 10),
        )
        self.outside_employee = Employee.objects.create(
            employee_id="RPT002",
            full_name="Dev Patel",
            email="dev@example.com",
            designation="Analyst",
            department=self.department,
            joining_date=date(2025, 3, 10),
        )
        Attendance.objects.create(
            employee=self.employee,
            attendance_date=date(2025, 1, 20),
        )
        Attendance.objects.create(
            employee=self.employee,
            attendance_date=date(2025, 2, 20),
        )
        for status in ("PENDING", "APPROVED", "REJECTED"):
            LeaveRequest.objects.create(
                employee=self.employee,
                start_date=date(2025, 1, 15),
                end_date=date(2025, 1, 16),
                reason="Personal leave",
                status=status,
            )
        LeaveRequest.objects.create(
            employee=self.employee,
            start_date=date(2025, 3, 15),
            end_date=date(2025, 3, 16),
            reason="Outside selected range",
            status="PENDING",
        )
        self.client.force_login(self.staff)

    def test_reports_use_database_values_with_date_range(self):
        response = self.client.get(
            reverse("reports"),
            {"start_date": "2025-01-01", "end_date": "2025-01-31"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Reports &amp; Analytics")
        self.assertContains(response, "chart.umd.min.js")
        self.assertContains(response, 'id="department-chart"')
        self.assertEqual(response.context["total_employees"], 1)
        self.assertEqual(
            response.context["department_rows"],
            [
                {"name": "Engineering", "count": 1},
                {"name": "Operations", "count": 0},
            ],
        )
        self.assertEqual(
            response.context["attendance_rows"],
            [{"month": "Jan 2025", "count": 1}],
        )
        self.assertEqual(
            [row["count"] for row in response.context["leave_counts"]],
            [1, 1, 1],
        )

    def test_reports_include_real_data_and_zero_statuses_without_filters(self):
        response = self.client.get(reverse("reports"))

        self.assertEqual(response.context["total_employees"], 2)
        self.assertEqual(
            [row["count"] for row in response.context["attendance_rows"]],
            [1, 1],
        )
        self.assertEqual(
            [row["count"] for row in response.context["leave_counts"]],
            [2, 1, 1],
        )

    def test_reports_require_staff_permission(self):
        self.client.force_login(
            get_user_model().objects.create_user(
                username="regular-user",
                password="test-password",
            )
        )
        response = self.client.get(reverse("reports"))

        self.assertEqual(response.status_code, 403)

    def test_reports_export_csv_uses_filters_and_real_data(self):
        response = self.client.get(
            reverse("reports_export_csv"),
            {"start_date": "2025-01-01", "end_date": "2025-01-31"},
        )

        self.assertEqual(response.status_code, 200)
        rows = list(csv.reader(StringIO(response.content.decode("utf-8"))))
        self.assertIn(["Employees", "2025-01-01", "2025-01-31", "Total employees", "1"], rows)
        self.assertIn(["Monthly attendance records", "2025-01-01", "2025-01-31", "Jan 2025", "1"], rows)
        self.assertIn(["Leave requests", "2025-01-01", "2025-01-31", "Pending", "1"], rows)

    def test_invalid_date_range_is_reported_and_rejected_for_csv(self):
        response = self.client.get(
            reverse("reports"),
            {"start_date": "2025-02-01", "end_date": "2025-01-01"},
        )
        csv_response = self.client.get(
            reverse("reports_export_csv"),
            {"start_date": "2025-02-01", "end_date": "2025-01-01"},
        )

        self.assertContains(response, "End date cannot be before start date.")
        self.assertEqual(response.context["total_employees"], 0)
        self.assertEqual(csv_response.status_code, 400)

    def test_empty_database_reports_render_without_errors(self):
        Attendance.objects.all().delete()
        LeaveRequest.objects.all().delete()
        Employee.objects.all().delete()
        Department.objects.all().delete()

        response = self.client.get(reverse("reports"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["total_employees"], 0)
        self.assertEqual(response.context["department_rows"], [])
        self.assertEqual(response.context["attendance_rows"], [])
        self.assertEqual(response.context["leave_counts"], [
            {"status": "PENDING", "label": "Pending", "count": 0},
            {"status": "APPROVED", "label": "Approved", "count": 0},
            {"status": "REJECTED", "label": "Rejected", "count": 0},
        ])
