from datetime import date

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from .models import Holiday
from .roles import HR_GROUP

User = get_user_model()
PASSWORD = "Holiday_test_password_69!"


class HolidayCalendarTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(
            username="holiday-admin",
            email="admin@example.com",
            password=PASSWORD,
        )
        self.hr = User.objects.create_user(
            username="holiday-hr",
            email="hr@example.com",
            password=PASSWORD,
            is_staff=True,
        )
        self.hr.groups.add(Group.objects.get(name=HR_GROUP))
        self.employee = User.objects.create_user(
            username="holiday-employee",
            email="employee@example.com",
            password=PASSWORD,
        )

    def test_admin_can_create_edit_and_delete_holidays(self):
        self.client.force_login(self.admin)
        create_response = self.client.post(
            reverse("holiday_create"),
            {
                "name": "Founders Day",
                "date": "2027-04-12",
                "description": "Company anniversary",
                "holiday_type": "COMPANY",
            },
        )
        holiday = Holiday.objects.get(name="Founders Day")
        self.assertRedirects(create_response, reverse("holiday_calendar"))
        self.assertEqual(holiday.date, date(2027, 4, 12))

        edit_page = self.client.get(reverse("holiday_update", args=[holiday.pk]))
        self.assertEqual(edit_page.status_code, 200)
        edit_response = self.client.post(
            reverse("holiday_update", args=[holiday.pk]),
            {
                "name": "Founders Celebration",
                "date": "2027-04-13",
                "description": "Updated company anniversary",
                "holiday_type": "COMPANY",
            },
        )
        holiday.refresh_from_db()
        self.assertRedirects(edit_response, reverse("holiday_calendar"))
        self.assertEqual(holiday.name, "Founders Celebration")
        self.assertEqual(holiday.date, date(2027, 4, 13))

        delete_response = self.client.post(reverse("holiday_delete", args=[holiday.pk]))
        self.assertRedirects(delete_response, reverse("holiday_calendar"))
        self.assertFalse(Holiday.objects.filter(pk=holiday.pk).exists())

    def test_hr_can_create_holidays_with_assigned_permissions(self):
        self.client.force_login(self.hr)

        response = self.client.post(
            reverse("holiday_create"),
            {
                "name": "HR Holiday",
                "date": "2027-05-10",
                "description": "Created by HR",
                "holiday_type": "",
            },
        )

        self.assertRedirects(response, reverse("holiday_calendar"))
        holiday = Holiday.objects.get(name="HR Holiday")
        self.assertEqual(
            self.client.get(reverse("holiday_update", args=[holiday.pk])).status_code,
            200,
        )
        edit_response = self.client.post(
            reverse("holiday_update", args=[holiday.pk]),
            {
                "name": "HR Updated Holiday",
                "date": "2027-05-11",
                "description": "Updated by HR",
                "holiday_type": "OPTIONAL",
            },
        )
        self.assertRedirects(edit_response, reverse("holiday_calendar"))
        self.assertTrue(Holiday.objects.filter(name="HR Updated Holiday").exists())
        delete_response = self.client.post(reverse("holiday_delete", args=[holiday.pk]))
        self.assertRedirects(delete_response, reverse("holiday_calendar"))
        self.assertFalse(Holiday.objects.filter(pk=holiday.pk).exists())

    def test_duplicate_name_and_date_is_rejected_in_form(self):
        Holiday.objects.create(
            name="Company Day",
            date=date(2027, 1, 1),
            description="First entry",
        )
        self.client.force_login(self.admin)

        response = self.client.post(
            reverse("holiday_create"),
            {
                "name": "company day",
                "date": "2027-01-01",
                "description": "Duplicate entry",
                "holiday_type": "",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "already exists on this date")
        self.assertEqual(Holiday.objects.filter(date=date(2027, 1, 1)).count(), 1)

    def test_database_constraint_prevents_duplicate_exact_name_and_date(self):
        Holiday.objects.create(
            name="National Day",
            date=date(2027, 8, 15),
            description="First entry",
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Holiday.objects.create(
                    name="National Day",
                    date=date(2027, 8, 15),
                    description="Duplicate entry",
                )

    def test_calendar_search_year_month_and_upcoming_holidays(self):
        target = Holiday.objects.create(
            name="Matching Holiday",
            date=date(2027, 3, 8),
            description="Searchable company event",
            holiday_type="COMPANY",
        )
        Holiday.objects.create(
            name="Other Holiday",
            date=date(2027, 3, 19),
            description="Different event",
        )
        self.client.force_login(self.hr)

        response = self.client.get(
            reverse("holiday_calendar"),
            {"q": "searchable", "year": "2027", "month": "3"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["calendar_year"], 2027)
        self.assertEqual(response.context["calendar_month"], 3)
        self.assertEqual(list(response.context["calendar_holidays"]), [target])
        self.assertEqual(list(response.context["upcoming_holidays"]), [target])
        self.assertContains(response, "Matching Holiday")
        self.assertNotContains(response, "Other Holiday")

    def test_calendar_includes_upcoming_and_month_grid_for_admin(self):
        holiday = Holiday.objects.create(
            name="Upcoming Event",
            date=date(2027, 7, 4),
            description="Future company event",
        )
        self.client.force_login(self.admin)

        response = self.client.get(
            reverse("holiday_calendar"),
            {"year": "2027", "month": "7"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Upcoming Event")
        self.assertIn(holiday, response.context["calendar_holidays"])
        self.assertEqual(len(response.context["weeks"]), 5)

    def test_unauthorized_user_cannot_view_create_edit_or_delete_holidays(self):
        holiday = Holiday.objects.create(
            name="Protected Holiday",
            date=date(2027, 9, 1),
            description="Protected record",
        )
        self.client.force_login(self.employee)

        responses = (
            self.client.get(reverse("holiday_calendar")),
            self.client.get(reverse("holiday_create")),
            self.client.post(
                reverse("holiday_create"),
                {
                    "name": "Unauthorized",
                    "date": "2027-09-02",
                    "description": "Should not save",
                    "holiday_type": "",
                },
            ),
            self.client.post(
                reverse("holiday_update", args=[holiday.pk]),
                {
                    "name": "Changed",
                    "date": "2027-09-03",
                    "description": "Should not update",
                    "holiday_type": "",
                },
            ),
            self.client.post(reverse("holiday_delete", args=[holiday.pk])),
        )

        self.assertEqual([response.status_code for response in responses], [403] * 5)
        holiday.refresh_from_db()
        self.assertEqual(holiday.name, "Protected Holiday")
        self.assertEqual(Holiday.objects.count(), 1)

    def test_invalid_year_shows_validation_message_without_server_error(self):
        self.client.force_login(self.admin)

        response = self.client.get(
            reverse("holiday_calendar"),
            {"year": "1200", "month": "13"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ensure this value is greater than or equal to 1900.")
        self.assertContains(response, "Select a valid choice")
