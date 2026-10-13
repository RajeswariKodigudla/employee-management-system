from datetime import date, timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Department, Employee, Holiday, LeaveRequest, Notification
from .roles import HR_GROUP

User = get_user_model()
PASSWORD = "Notify_test_password_74!"


class NotificationTests(TestCase):
    def setUp(self):
        self.today = date(2026, 10, 13)
        self.admin = User.objects.create_superuser(
            username="notice-admin",
            email="admin@example.com",
            password=PASSWORD,
        )
        self.hr = User.objects.create_user(
            username="notice-hr",
            email="hr@example.com",
            password=PASSWORD,
            is_staff=True,
        )
        self.hr.groups.add(Group.objects.get(name=HR_GROUP))
        self.employee_user = User.objects.create_user(
            username="notice-employee",
            email="employee@example.com",
            password=PASSWORD,
        )
        department = Department.objects.create(name="People Operations")
        self.employee = Employee.objects.create(
            employee_id="NOTICE001",
            full_name="Morgan Lee",
            email="morgan@example.com",
            designation="Coordinator",
            department=department,
        )
        self.pending_leave = LeaveRequest.objects.create(
            employee=self.employee,
            start_date=self.today + timedelta(days=4),
            end_date=self.today + timedelta(days=5),
            reason="Personal",
        )
        self.holiday = Holiday.objects.create(
            name="Company Day",
            date=self.today + timedelta(days=10),
            description="Annual company celebration",
            holiday_type="COMPANY",
        )
        self.localdate_patch = patch("django.utils.timezone.localdate", return_value=self.today)
        self.localdate_patch.start()
        self.addCleanup(self.localdate_patch.stop)

    def test_generates_pending_leave_and_upcoming_holiday_notifications(self):
        self.client.force_login(self.hr)

        response = self.client.get(reverse("notification_list"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            Notification.objects.filter(user=self.hr).count(),
            2,
        )
        self.assertContains(response, "Pending leave request")
        self.assertContains(response, "Morgan Lee")
        self.assertContains(response, "Upcoming holiday: Company Day")
        self.assertContains(response, "notification-bell-count")
        leave_notification = Notification.objects.get(user=self.hr, kind="LEAVE")
        holiday_notification = Notification.objects.get(user=self.hr, kind="HOLIDAY")
        self.assertIn("leave:{}".format(self.pending_leave.pk), leave_notification.event_key)
        self.assertIn("holiday:{}".format(self.holiday.pk), holiday_notification.event_key)
        self.assertFalse(leave_notification.is_read)
        self.assertFalse(holiday_notification.is_read)
        self.assertIsNotNone(leave_notification.created_at)

    def test_refresh_does_not_create_duplicate_notifications(self):
        self.client.force_login(self.hr)

        self.client.get(reverse("notification_list"))
        self.client.get(reverse("dashboard"))
        self.client.get(reverse("notification_list"))

        self.assertEqual(Notification.objects.filter(user=self.hr).count(), 2)
        self.assertEqual(
            Notification.objects.filter(user=self.hr).values("event_key").distinct().count(),
            2,
        )

    def test_regular_users_receive_holiday_but_not_leave_notifications(self):
        self.client.force_login(self.employee_user)

        response = self.client.get(reverse("notification_list"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            list(
                Notification.objects.filter(user=self.employee_user).values_list(
                    "kind", flat=True
                )
            ),
            ["HOLIDAY"],
        )
        self.assertNotContains(response, "Morgan Lee")
        self.assertContains(response, "Company Day")

    def test_notifications_are_private_and_authentication_is_required(self):
        self.client.force_login(self.hr)
        self.client.get(reverse("notification_list"))
        notification = Notification.objects.get(
            user=self.hr,
            event_key=f"leave:{self.pending_leave.pk}",
        )
        self.client.force_login(self.employee_user)

        response = self.client.get(reverse("notification_list"))
        mark_response = self.client.post(
            reverse("notification_mark_read", args=[notification.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Morgan Lee")
        self.assertEqual(mark_response.status_code, 404)
        notification.refresh_from_db()
        self.assertFalse(notification.is_read)

        self.client.logout()
        login_response = self.client.get(reverse("notification_list"))
        self.assertEqual(login_response.status_code, 302)
        self.assertIn(reverse("login"), login_response.url)

    def test_mark_one_read_updates_only_current_users_notification(self):
        self.client.force_login(self.hr)
        self.client.get(reverse("notification_list"))
        notification = Notification.objects.get(
            user=self.hr,
            event_key=f"leave:{self.pending_leave.pk}",
        )

        response = self.client.post(
            reverse("notification_mark_read", args=[notification.pk])
        )

        notification.refresh_from_db()
        self.assertRedirects(response, reverse("notification_list"))
        self.assertTrue(notification.is_read)
        self.assertEqual(
            Notification.objects.filter(user=self.hr, is_read=False).count(),
            1,
        )

    def test_mark_all_read_requires_post_and_marks_only_own_rows(self):
        self.client.force_login(self.hr)
        self.client.get(reverse("notification_list"))
        admin_notification = Notification.objects.create(
            user=self.admin,
            kind="HOLIDAY",
            event_key="holiday:admin-only",
            title="Admin only",
            message="Private to admin",
        )

        get_response = self.client.get(reverse("notification_mark_all_read"))
        post_response = self.client.post(reverse("notification_mark_all_read"))

        self.assertEqual(get_response.status_code, 405)
        self.assertRedirects(post_response, reverse("notification_list"))
        self.assertEqual(Notification.objects.filter(user=self.hr, is_read=False).count(), 0)
        admin_notification.refresh_from_db()
        self.assertFalse(admin_notification.is_read)

    def test_read_unread_and_all_filters(self):
        self.client.force_login(self.hr)
        self.client.get(reverse("notification_list"))
        unread_notification = Notification.objects.get(
            user=self.hr,
            event_key=f"leave:{self.pending_leave.pk}",
        )
        unread_notification.is_read = True
        unread_notification.save(update_fields=["is_read"])

        unread_response = self.client.get(
            reverse("notification_list"),
            {"status": "unread"},
        )
        read_response = self.client.get(
            reverse("notification_list"),
            {"status": "read"},
        )
        all_response = self.client.get(
            reverse("notification_list"),
            {"status": "all"},
        )

        self.assertEqual(unread_response.context["notifications"].paginator.count, 1)
        self.assertEqual(read_response.context["notifications"].paginator.count, 1)
        self.assertEqual(all_response.context["notifications"].paginator.count, 2)
        self.assertContains(unread_response, "Company Day")
        self.assertNotContains(unread_response, "Morgan Lee")
        self.assertContains(read_response, "Morgan Lee")

    def test_resolved_leave_request_removes_stale_pending_notification(self):
        self.client.force_login(self.hr)
        self.client.get(reverse("notification_list"))
        self.pending_leave.status = "APPROVED"
        self.pending_leave.save(update_fields=["status"])

        self.client.get(reverse("notification_list"))

        self.assertFalse(
            Notification.objects.filter(
                user=self.hr,
                event_key=f"leave:{self.pending_leave.pk}",
            ).exists()
        )
