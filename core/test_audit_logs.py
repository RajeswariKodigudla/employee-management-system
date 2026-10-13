from datetime import date
from uuid import UUID

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from .audit import record_audit_event
from .models import (
    AuditLog,
    Department,
    Employee,
    Holiday,
    LeaveRequest,
    PayrollRecord,
    PerformanceReview,
)

User = get_user_model()


class AuditLogTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(
            username="audit-admin",
            email="audit-admin@example.com",
            password="SafePassword123!",
        )
        self.hr = User.objects.create_user(
            username="audit-hr",
            email="audit-hr@example.com",
            password="SafePassword123!",
        )
        self.hr.groups.add(Group.objects.get(name="HR"))
        self.employee_user = User.objects.create_user(
            username="audit-employee",
            email="audit-employee@example.com",
            password="SafePassword123!",
        )
        self.department = Department.objects.create(name="Audit Department")
        self.employee = Employee.objects.create(
            employee_id="AUD001",
            full_name="Casey Jordan",
            email="casey@example.com",
            designation="Analyst",
            department=self.department,
        )

    def test_admin_only_read_only_audit_log_access(self):
        url = reverse("audit_log_list")
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertEqual(self.client.post(url).status_code, 405)

        for user in (self.hr, self.employee_user):
            self.client.force_login(user)
            with self.subTest(user=user.username):
                self.assertEqual(self.client.get(url).status_code, 403)

        self.assertFalse(
            AuditLog._meta.permissions,
            "Audit logs should not expose mutable custom model permissions.",
        )
        self.assertEqual(AuditLog._meta.default_permissions, ("view",))

    def test_employee_department_and_leave_actions_are_logged(self):
        self.client.force_login(self.hr)

        create_employee_response = self.client.post(
            reverse("employee_create"),
            {
                "employee_id": "AUD002",
                "full_name": "Taylor Quinn",
                "email": "taylor@example.com",
                "phone": "555-0134",
                "designation": "Designer",
                "department": self.department.pk,
                "joining_date": "2026-01-15",
                "status": "ACTIVE",
                "address": "Not recorded in audit logs",
            },
        )
        self.assertEqual(create_employee_response.status_code, 302)
        created_employee = Employee.objects.get(employee_id="AUD002")
        create_log = AuditLog.objects.get(object_id=str(created_employee.pk))
        self.assertEqual(create_log.action, "CREATE")
        self.assertNotIn("email", create_log.changes)
        self.assertNotIn("address", create_log.changes)

        update_employee_response = self.client.post(
            reverse("employee_update", args=[created_employee.pk]),
            {
                "employee_id": "AUD002",
                "full_name": "Taylor Quinn",
                "email": "taylor@example.com",
                "phone": "555-0134",
                "designation": "Senior Designer",
                "department": self.department.pk,
                "joining_date": "2026-01-15",
                "status": "ON_LEAVE",
                "address": "Still excluded",
            },
        )
        self.assertEqual(update_employee_response.status_code, 302)
        update_log = AuditLog.objects.get(
            object_type="Employee",
            object_id=str(created_employee.pk),
            action="UPDATE",
        )
        created_employee.refresh_from_db()
        self.assertEqual(created_employee.designation, "Senior Designer")
        self.assertEqual(
            update_log.changes,
            {
                "designation": {"before": "Designer", "after": "Senior Designer"},
                "status": {"before": "Active", "after": "On Leave"},
            },
        )

        department_response = self.client.post(
            reverse("department_create"),
            {"name": "Research", "description": "Department details"},
        )
        self.assertEqual(department_response.status_code, 302)
        new_department = Department.objects.get(name="Research")
        self.assertTrue(AuditLog.objects.filter(
            object_type="Department",
            object_id=str(new_department.pk),
            action="CREATE",
        ).exists())
        department_update_response = self.client.post(
            reverse("department_update", args=[new_department.pk]),
            {"name": "Research & Development", "description": "Updated description"},
        )
        self.assertEqual(department_update_response.status_code, 302)
        self.assertTrue(AuditLog.objects.filter(
            object_type="Department",
            object_id=str(new_department.pk),
            action="UPDATE",
        ).exists())
        department_delete_response = self.client.post(
            reverse("department_delete", args=[new_department.pk])
        )
        self.assertEqual(department_delete_response.status_code, 302)
        self.assertFalse(Department.objects.filter(pk=new_department.pk).exists())
        self.assertTrue(AuditLog.objects.filter(
            object_type="Department",
            object_id=str(new_department.pk),
            action="DELETE",
        ).exists())

        leave_request = LeaveRequest.objects.create(
            employee=self.employee,
            start_date=date(2026, 10, 13),
            end_date=date(2026, 10, 14),
            reason="Personal leave",
        )
        approve_response = self.client.post(
            reverse("leave_review", args=[leave_request.pk, "approve"])
        )
        reject_leave = LeaveRequest.objects.create(
            employee=created_employee,
            start_date=date(2026, 11, 1),
            end_date=date(2026, 11, 2),
            reason="Another request",
        )
        reject_response = self.client.post(
            reverse("leave_review", args=[reject_leave.pk, "reject"])
        )
        self.assertEqual(approve_response.status_code, 302)
        self.assertEqual(reject_response.status_code, 302)
        leave_logs = list(
            AuditLog.objects.filter(object_type="Leave Request")
            .order_by("action")
            .values_list("action", "changes")
        )
        self.assertEqual(len(leave_logs), 2)
        self.assertEqual({action for action, _ in leave_logs}, {"APPROVE", "REJECT"})
        self.assertEqual(leave_logs[0][1]["status"]["before"], "Pending")

    def test_holiday_payroll_and_performance_changes_are_logged_safely(self):
        self.client.force_login(self.hr)

        holiday_response = self.client.post(
            reverse("holiday_create"),
            {
                "name": "Audit Holiday",
                "date": "2027-01-01",
                "description": "Holiday description excluded",
                "holiday_type": "COMPANY",
            },
        )
        self.assertEqual(holiday_response.status_code, 302)
        holiday = Holiday.objects.get(name="Audit Holiday")
        holiday_log = AuditLog.objects.get(
            object_type="Holiday",
            object_id=str(holiday.pk),
        )
        self.assertNotIn("description", holiday_log.changes)
        holiday_update_response = self.client.post(
            reverse("holiday_update", args=[holiday.pk]),
            {
                "name": "Updated Audit Holiday",
                "date": "2027-01-02",
                "description": "Changed description",
                "holiday_type": "PUBLIC",
            },
        )
        self.assertEqual(holiday_update_response.status_code, 302)
        self.assertTrue(AuditLog.objects.filter(
            object_type="Holiday",
            object_id=str(holiday.pk),
            action="UPDATE",
        ).exists())
        holiday_delete_response = self.client.post(
            reverse("holiday_delete", args=[holiday.pk])
        )
        self.assertEqual(holiday_delete_response.status_code, 302)
        self.assertTrue(AuditLog.objects.filter(
            object_type="Holiday",
            object_id=str(holiday.pk),
            action="DELETE",
        ).exists())

        payroll = PayrollRecord.objects.create(
            employee=self.employee,
            pay_month=date(2026, 9, 1),
            basic_salary="5000.00",
            allowances="300.00",
            deductions="100.00",
            payment_status="PENDING",
        )
        payroll_response = self.client.post(
            reverse("payroll_update", args=[payroll.pk]),
            {
                "employee": self.employee.pk,
                "pay_month": "2026-09",
                "basic_salary": "5000.00",
                "allowances": "300.00",
                "deductions": "100.00",
                "payment_date": "2026-09-30",
                "payment_status": "PAID",
            },
        )
        self.assertEqual(payroll_response.status_code, 302)
        payroll_log = AuditLog.objects.get(
            object_type="Payroll Record",
            object_id=str(payroll.pk),
            action="UPDATE",
        )
        payroll.refresh_from_db()
        self.assertEqual(payroll.payment_status, "PAID")
        self.assertEqual(
            payroll_log.changes,
            {
                "payment_status": {"before": "Pending", "after": "Paid"},
                "payment_date": {"before": None, "after": "2026-09-30"},
            },
        )
        self.assertNotIn("basic_salary", payroll_log.changes)
        self.assertNotIn("allowances", payroll_log.changes)
        self.assertNotIn("deductions", payroll_log.changes)
        payroll_delete_response = self.client.post(
            reverse("payroll_delete", args=[payroll.pk])
        )
        self.assertEqual(payroll_delete_response.status_code, 302)
        self.assertFalse(PayrollRecord.objects.filter(pk=payroll.pk).exists())
        self.assertTrue(AuditLog.objects.filter(
            object_type="Payroll Record",
            object_id=str(payroll.pk),
            action="DELETE",
        ).exists())

        review = PerformanceReview.objects.create(
            employee=self.employee,
            reviewer=self.hr,
            review_period_start=date(2026, 1, 1),
            review_period_end=date(2026, 6, 30),
            rating=3,
            goals="Confidential goal",
            achievements="Confidential achievement",
            strengths="Confidential strengths",
            improvement_areas="Confidential improvement notes",
            feedback="Confidential feedback",
        )
        performance_response = self.client.post(
            reverse("performance_update", args=[review.pk]),
            {
                "employee": self.employee.pk,
                "review_period_start": "2026-01-01",
                "review_period_end": "2026-06-30",
                "rating": "4",
                "goals": "Updated confidential goal",
                "achievements": "Updated confidential achievement",
                "strengths": "Updated confidential strengths",
                "improvement_areas": "Updated confidential improvement notes",
                "feedback": "Updated confidential feedback",
            },
        )
        self.assertEqual(performance_response.status_code, 302)
        performance_log = AuditLog.objects.get(
            object_type="Performance Review",
            object_id=str(review.pk),
            action="UPDATE",
        )
        self.assertEqual(
            performance_log.changes["rating"],
            {"before": 3, "after": 4},
        )
        for sensitive_field in (
            "goals",
            "achievements",
            "strengths",
            "improvement_areas",
            "feedback",
        ):
            self.assertNotIn(sensitive_field, performance_log.changes)
        performance_delete_response = self.client.post(
            reverse("performance_delete", args=[review.pk])
        )
        self.assertEqual(performance_delete_response.status_code, 302)
        self.assertFalse(PerformanceReview.objects.filter(pk=review.pk).exists())
        self.assertTrue(AuditLog.objects.filter(
            object_type="Performance Review",
            object_id=str(review.pk),
            action="DELETE",
        ).exists())

    def test_successful_deletions_are_logged_and_failed_deletes_are_not(self):
        self.client.force_login(self.hr)
        deletable_employee = Employee.objects.create(
            employee_id="AUD003",
            full_name="Delete Target",
            email="delete-target@example.com",
            designation="Temporary",
            department=self.department,
        )
        delete_response = self.client.post(
            reverse("employee_delete", args=[deletable_employee.pk])
        )
        self.assertEqual(delete_response.status_code, 302)
        self.assertFalse(Employee.objects.filter(pk=deletable_employee.pk).exists())
        delete_log = AuditLog.objects.get(
            object_type="Employee",
            object_id=str(deletable_employee.pk),
            action="DELETE",
        )
        self.assertEqual(delete_log.actor, self.hr)

        protected_delete_response = self.client.post(
            reverse("department_delete", args=[self.department.pk])
        )
        self.assertEqual(protected_delete_response.status_code, 302)
        self.assertTrue(Department.objects.filter(pk=self.department.pk).exists())
        self.assertFalse(AuditLog.objects.filter(
            object_type="Department",
            object_id=str(self.department.pk),
            action="DELETE",
        ).exists())

    def test_audit_action_key_prevents_duplicate_entries(self):
        action_key = UUID("42d5a12e-33d6-4f2b-9ad2-ff2cf1a3ac01")
        record_audit_event(
            actor=self.admin,
            action="CREATE",
            instance=self.department,
            description="Department created.",
            after={"name": self.department.name},
            action_key=action_key,
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                record_audit_event(
                    actor=self.admin,
                    action="CREATE",
                    instance=self.department,
                    description="Duplicate department creation event.",
                    after={"name": self.department.name},
                    action_key=action_key,
                )
        self.assertEqual(AuditLog.objects.filter(action_key=action_key).count(), 1)

    def test_audit_search_user_action_and_dates_and_pagination(self):
        self.client.force_login(self.hr)
        for day in range(1, 28):
            department = Department.objects.create(name=f"Department {day:02}")
            record_audit_event(
                actor=self.hr,
                action="CREATE",
                instance=department,
                description="Department created.",
                after={"name": department.name},
            )
        self.client.force_login(self.admin)

        filtered_response = self.client.get(reverse("audit_log_list"), {
            "user": self.hr.pk,
            "action": "CREATE",
            "start_date": "2000-01-01",
            "end_date": "2099-12-31",
        })
        self.assertEqual(filtered_response.status_code, 200)
        self.assertEqual(filtered_response.context["logs"].paginator.count, 27)
        self.assertEqual(filtered_response.context["logs"].paginator.num_pages, 2)
        search_response = self.client.get(reverse("audit_log_list"), {
            "q": "Department 05",
            "user": self.hr.pk,
            "action": "CREATE",
            "start_date": "2000-01-01",
            "end_date": "2099-12-31",
        })
        self.assertEqual(search_response.context["logs"].paginator.count, 1)
