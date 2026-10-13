from datetime import date

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

from .forms import PerformanceReviewForm
from .models import Department, Employee, PerformanceReview

User = get_user_model()


class PerformanceReviewTests(TestCase):
    def setUp(self):
        self.department = Department.objects.create(name="Product")
        self.other_department = Department.objects.create(name="Operations")
        self.employee = Employee.objects.create(
            employee_id="REV001",
            full_name="Morgan Chen",
            email="morgan@example.com",
            designation="Product Manager",
            department=self.department,
        )
        self.other_employee = Employee.objects.create(
            employee_id="REV002",
            full_name="Sam Rivera",
            email="sam@example.com",
            designation="Operations Lead",
            department=self.other_department,
        )
        self.hr = User.objects.create_user(
            username="review-hr",
            password="SafePassword123!",
        )
        self.hr.groups.add(Group.objects.get(name="HR"))
        self.admin = User.objects.create_user(
            username="review-admin",
            password="SafePassword123!",
            is_superuser=True,
            is_staff=True,
        )
        self.ordinary_user = User.objects.create_user(
            username="review-employee",
            password="SafePassword123!",
        )

    def review_data(self, **overrides):
        data = {
            "employee": self.employee.pk,
            "review_period_start": "2026-01-01",
            "review_period_end": "2026-06-30",
            "rating": "4",
            "goals": "Deliver product roadmap",
            "achievements": "Launched the new portal",
            "strengths": "Clear communication and ownership",
            "improvement_areas": "Delegate recurring work",
            "feedback": "Strong impact across the team",
        }
        data.update(overrides)
        return data

    def create_review(self, employee=None, rating=4, start="2026-01-01", end="2026-06-30"):
        return PerformanceReview.objects.create(
            employee=employee or self.employee,
            reviewer=self.hr,
            review_period_start=date.fromisoformat(start),
            review_period_end=date.fromisoformat(end),
            rating=rating,
            goals="Deliver product roadmap",
            achievements="Launched the new portal",
            strengths="Clear communication and ownership",
            improvement_areas="Delegate recurring work",
            feedback="Strong impact across the team",
        )

    def test_form_requires_content_and_rating_in_range(self):
        form = PerformanceReviewForm(data=self.review_data(goals="   "))
        self.assertFalse(form.is_valid())
        self.assertIn("goals", form.errors)

        invalid_rating_form = PerformanceReviewForm(
            data=self.review_data(rating="6")
        )
        self.assertFalse(invalid_rating_form.is_valid())
        self.assertIn("rating", invalid_rating_form.errors)

    def test_form_rejects_end_before_start(self):
        form = PerformanceReviewForm(data=self.review_data(
            review_period_start="2026-07-01",
            review_period_end="2026-06-30",
        ))
        self.assertFalse(form.is_valid())
        self.assertIn("review_period_end", form.errors)

    def test_admin_hr_permissions_are_configured(self):
        for group_name in ("Admin", "HR"):
            group = Group.objects.get(name=group_name)
            for action in ("add", "change", "delete", "view"):
                with self.subTest(group=group_name, action=action):
                    self.assertTrue(group.permissions.filter(
                        content_type__app_label="core",
                        content_type__model="performancereview",
                        codename=f"{action}_performancereview",
                    ).exists())

    def test_review_list_and_history_require_authorized_access(self):
        self.create_review()
        urls = [
            reverse("performance_list"),
            reverse("performance_history", args=[self.employee.pk]),
        ]
        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 403)
        self.client.force_login(self.ordinary_user)
        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 403)
        self.assertEqual(
            self.client.get(reverse("performance_export_csv")).status_code,
            403,
        )

    def test_hr_can_create_review_and_reviewer_is_authenticated_actor(self):
        self.client.force_login(self.hr)
        response = self.client.post(
            reverse("performance_create"),
            data=self.review_data(),
        )

        review = PerformanceReview.objects.get()
        self.assertRedirects(
            response,
            reverse("performance_history", args=[self.employee.pk]),
        )
        self.assertEqual(review.reviewer, self.hr)
        self.assertEqual(review.rating, 4)
        self.assertEqual(review.review_period_end, date(2026, 6, 30))

    def test_hr_can_edit_review_without_changing_original_reviewer(self):
        review = self.create_review()
        self.client.force_login(self.admin)
        changed_data = self.review_data(
            rating="5",
            achievements="Launched the portal and improved adoption",
        )
        response = self.client.post(
            reverse("performance_update", args=[review.pk]),
            data=changed_data,
        )

        review.refresh_from_db()
        self.assertRedirects(
            response,
            reverse("performance_history", args=[self.employee.pk]),
        )
        self.assertEqual(review.rating, 5)
        self.assertEqual(review.reviewer, self.hr)
        self.assertEqual(review.achievements, "Launched the portal and improved adoption")

    def test_non_admin_hr_cannot_create_or_edit_reviews(self):
        review = self.create_review()
        self.client.force_login(self.ordinary_user)
        self.assertEqual(
            self.client.get(reverse("performance_create")).status_code,
            403,
        )
        self.assertEqual(
            self.client.get(reverse("performance_update", args=[review.pk])).status_code,
            403,
        )

    def test_search_department_period_rating_filters_and_summaries(self):
        matching = self.create_review(rating=5, start="2026-01-01", end="2026-06-30")
        self.create_review(
            employee=self.other_employee,
            rating=2,
            start="2025-01-01",
            end="2025-12-31",
        )
        self.client.force_login(self.hr)
        response = self.client.get(reverse("performance_list"), {
            "q": "Morgan",
            "department": self.department.pk,
            "period_year": "2026",
            "rating": "5",
        })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["reviews"].paginator.count, 1)
        self.assertEqual(response.context["reviews"].object_list[0], matching)
        self.assertEqual(response.context["summary"]["review_count"], 1)
        self.assertEqual(float(response.context["summary"]["average_rating"]), 5.0)
        self.assertEqual(
            response.context["rating_summary"][0]["label"],
            "5 - Outstanding",
        )
        self.assertEqual(len(response.context["employee_summary"]), 1)

    def test_employee_history_and_csv_export(self):
        self.create_review(rating=3)
        self.client.force_login(self.hr)

        history = self.client.get(
            reverse("performance_history", args=[self.employee.pk])
        )
        self.assertEqual(history.status_code, 200)
        self.assertContains(history, "Strong impact across the team")
        self.assertEqual(history.context["summary"]["review_count"], 1)

        export = self.client.get(reverse("performance_export_csv"), {"rating": "3"})
        self.assertEqual(export.status_code, 200)
        self.assertIn("text/csv", export["Content-Type"])
        contents = export.content.decode()
        self.assertIn("Morgan Chen", contents)
        self.assertIn("Strong impact across the team", contents)
