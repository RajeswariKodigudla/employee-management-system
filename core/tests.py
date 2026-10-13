from datetime import date
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse
from .models import Department,Employee
class EMSTests(TestCase):
 def setUp(self):
  self.admin=get_user_model().objects.create_user(username="hr",password="StrongPass!123",is_staff=True)
  self.dep=Department.objects.create(name="Engineering")
  Employee.objects.create(employee_id="EMP001",full_name="Priya Sharma",email="priya@example.com",designation="Python Developer",department=self.dep,joining_date=date(2025,1,10))
 def test_dashboard_requires_login(self): self.assertEqual(self.client.get(reverse("dashboard")).status_code,302)
 def test_dashboard_for_logged_in_user(self):
  self.client.login(username="hr",password="StrongPass!123"); self.assertEqual(self.client.get(reverse("dashboard")).status_code,200)
 def test_search(self):
  self.client.login(username="hr",password="StrongPass!123"); self.assertContains(self.client.get(reverse("employee_list"),{"q":"Priya"}),"Priya Sharma")
 def test_department_with_employees_cannot_be_deleted(self):
  self.client.login(username="hr",password="StrongPass!123"); self.client.post(reverse("department_delete",args=[self.dep.pk])); self.assertTrue(Department.objects.filter(pk=self.dep.pk).exists())
