from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

from .admin import ProtectedUserChangeForm
from .roles import ADMIN_GROUP, HR_GROUP
from .roles import role_for_user

User = get_user_model()
TEST_PASSWORD = "G7!hr_secure_Test_passphrase"


class UserManagementTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(
            username="site-admin",
            email="admin@example.com",
            password=TEST_PASSWORD,
        )
        self.hr = User.objects.create_user(
            username="hr-manager",
            email="hr@example.com",
            password=TEST_PASSWORD,
            is_staff=True,
        )
        self.hr.groups.add(Group.objects.get(name=HR_GROUP))
        self.regular_user = User.objects.create_user(
            username="employee-user",
            email="employee@example.com",
            password=TEST_PASSWORD,
        )

    def test_admin_can_view_paginated_users(self):
        User.objects.bulk_create(
            [
                User(username=f"staff-{index}", password="!", is_active=index != 0)
                for index in range(27)
            ]
        )
        self.client.force_login(self.admin)

        response = self.client.get(reverse("user_list"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["users"].object_list), 25)
        self.assertContains(response, "User &amp; Role Management")
        self.assertContains(response, "site-admin")
        self.assertContains(response, "Admin")
        self.assertContains(response, "Inactive")

        next_page = self.client.get(reverse("user_list"), {"page": 2})
        self.assertEqual(len(next_page.context["users"].object_list), 5)

    def test_admin_creates_user_with_hashed_password_and_assigned_role(self):
        self.client.force_login(self.admin)

        response = self.client.post(
            reverse("user_create"),
            {
                "username": "new-hr",
                "first_name": "New",
                "last_name": "Manager",
                "email": "new-hr@example.com",
                "role": "hr",
                "password1": TEST_PASSWORD,
                "password2": TEST_PASSWORD,
            },
        )

        created_user = User.objects.get(username="new-hr")
        self.assertRedirects(response, reverse("user_list"))
        self.assertTrue(created_user.check_password(TEST_PASSWORD))
        self.assertNotEqual(created_user.password, TEST_PASSWORD)
        self.assertTrue(created_user.is_staff)
        self.assertTrue(created_user.groups.filter(name=HR_GROUP).exists())
        self.assertFalse(created_user.groups.filter(name=ADMIN_GROUP).exists())

    def test_admin_can_edit_user_details_role_and_active_status(self):
        self.client.force_login(self.admin)

        response = self.client.post(
            reverse("user_update", args=[self.regular_user.pk]),
            {
                "username": self.regular_user.username,
                "first_name": "Updated",
                "last_name": "Employee",
                "email": "updated@example.com",
                "role": "hr",
                "is_active": "False",
            },
        )

        self.regular_user.refresh_from_db()
        self.assertRedirects(response, reverse("user_list"))
        self.assertEqual(self.regular_user.first_name, "Updated")
        self.assertFalse(self.regular_user.is_active)
        self.assertTrue(self.regular_user.groups.filter(name=HR_GROUP).exists())
        self.assertTrue(self.regular_user.check_password(TEST_PASSWORD))

    def test_hr_cannot_view_or_manage_users_or_change_own_role(self):
        self.client.force_login(self.hr)

        list_response = self.client.get(reverse("user_list"))
        edit_response = self.client.post(
            reverse("user_update", args=[self.hr.pk]),
            {
                "username": self.hr.username,
                "first_name": "",
                "last_name": "",
                "email": self.hr.email,
                "role": "admin",
                "is_active": "True",
            },
        )
        create_response = self.client.get(reverse("user_create"))

        self.assertEqual(list_response.status_code, 403)
        self.assertEqual(edit_response.status_code, 403)
        self.assertEqual(create_response.status_code, 403)
        self.hr.refresh_from_db()
        self.assertFalse(self.hr.groups.filter(name=ADMIN_GROUP).exists())
        self.assertFalse(self.hr.has_perm("auth.view_user"))

    def test_regular_user_cannot_reach_user_management_or_hr_operations(self):
        self.client.force_login(self.regular_user)

        self.assertEqual(self.client.get(reverse("user_list")).status_code, 403)
        self.assertEqual(self.client.get(reverse("employee_create")).status_code, 403)
        self.assertEqual(self.client.get(reverse("attendance_list")).status_code, 403)

    def test_hr_can_use_assigned_people_operations_and_reports(self):
        self.client.force_login(self.hr)

        for url_name in (
            "employee_create",
            "department_create",
            "attendance_list",
            "attendance_create",
            "leave_list",
            "leave_create",
            "reports",
        ):
            with self.subTest(url_name=url_name):
                self.assertEqual(self.client.get(reverse(url_name)).status_code, 200)

    def test_admin_cannot_remove_own_admin_role(self):
        self.client.force_login(self.admin)

        response = self.client.post(
            reverse("user_update", args=[self.admin.pk]),
            {
                "username": self.admin.username,
                "first_name": "",
                "last_name": "",
                "email": self.admin.email,
                "role": "hr",
                "is_active": "True",
            },
        )

        self.admin.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "You cannot change your own role.")
        self.assertTrue(self.admin.is_superuser)
        self.assertEqual(role_for_user(self.admin), "admin")

    def test_last_active_admin_cannot_be_deactivated_or_demoted(self):
        second_admin = User.objects.create_user(
            username="only-admin",
            email="only-admin@example.com",
            password=TEST_PASSWORD,
            is_staff=True,
        )
        second_admin.groups.add(Group.objects.get(name=ADMIN_GROUP))
        self.admin.is_active = False
        self.admin.save(update_fields=["is_active"])
        self.client.force_login(second_admin)

        response = self.client.post(
            reverse("user_update", args=[second_admin.pk]),
            {
                "username": second_admin.username,
                "first_name": "",
                "last_name": "",
                "email": second_admin.email,
                "role": "admin",
                "is_active": "False",
            },
        )

        second_admin.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "last active administrator")
        self.assertTrue(second_admin.is_active)

    def test_admin_role_receives_full_core_permissions(self):
        group_admin = User.objects.create_user(
            username="group-admin",
            email="group-admin@example.com",
            password=TEST_PASSWORD,
            is_staff=True,
        )
        group_admin.groups.add(Group.objects.get(name=ADMIN_GROUP))
        self.assertTrue(group_admin.has_perm("auth.view_user"))
        for permission in (
            "core.add_employee",
            "core.change_department",
            "core.delete_attendance",
            "core.view_leaverequest",
        ):
            with self.subTest(permission=permission):
                self.assertTrue(group_admin.has_perm(permission))
        for permission in (
            "core.add_employee",
            "core.change_department",
            "core.delete_attendance",
            "core.view_leaverequest",
        ):
            with self.subTest(permission=permission):
                self.assertTrue(self.hr.has_perm(permission))

    def test_user_deletion_is_disabled_in_django_admin(self):
        self.client.force_login(self.admin)

        response = self.client.get(
            f"/django-admin/auth/user/{self.hr.pk}/delete/"
        )

        self.assertEqual(response.status_code, 403)

    def test_django_admin_form_cannot_remove_last_active_admin(self):
        form = ProtectedUserChangeForm(
            data={
                "username": self.admin.username,
                "first_name": "",
                "last_name": "",
                "email": self.admin.email,
                "is_active": "",
                "is_superuser": "",
                "groups": [],
                "user_permissions": [],
            },
            instance=self.admin,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("last active administrator", str(form.errors))
