from datetime import date
import re

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm
from django.core.exceptions import ValidationError
from django.db.models import Q
from .roles import ADMIN_GROUP, HR_GROUP, role_for_user
from .models import Employee,Department,LeaveRequest,Attendance,Holiday,PayrollRecord,PerformanceReview,AuditLog
class StyledForm(forms.ModelForm):
 def __init__(self,*a,**kw):
  super().__init__(*a,**kw)
  for f in self.fields.values(): f.widget.attrs["class"]=(f.widget.attrs.get("class","")+" form-control").strip(); f.widget.attrs["class"] += " form-select" if isinstance(f.widget,forms.Select) else ""
class EmployeeForm(StyledForm):
 class Meta:
  model=Employee; fields=["employee_id","full_name","email","phone","designation","department","joining_date","status","address"]; widgets={"joining_date":forms.DateInput(attrs={"type":"date"}),"address":forms.Textarea(attrs={"rows":3})}
class DepartmentForm(StyledForm):
 class Meta: model=Department; fields=["name","description"]; widgets={"description":forms.Textarea(attrs={"rows":3})}
class LeaveForm(StyledForm):
 class Meta: model=LeaveRequest; fields=["employee","start_date","end_date","reason"]; widgets={"start_date":forms.DateInput(attrs={"type":"date"}),"end_date":forms.DateInput(attrs={"type":"date"}),"reason":forms.Textarea(attrs={"rows":3})}
 def clean(self):
  d=super().clean()
  if d.get("start_date") and d.get("end_date") and d["end_date"]<d["start_date"]: raise ValidationError("End date cannot be before start date.")
  return d
class AttendanceForm(StyledForm):
 class Meta: model=Attendance; fields=["employee","attendance_date","check_in","check_out","note"]; widgets={"attendance_date":forms.DateInput(attrs={"type":"date"}),"check_in":forms.TimeInput(attrs={"type":"time"}),"check_out":forms.TimeInput(attrs={"type":"time"})}
 def clean(self):
  d=super().clean()
  if d.get("check_in") and d.get("check_out") and d["check_out"]<=d["check_in"]: raise ValidationError("Check-out must be later than check-in.")
  return d

class HolidayForm(StyledForm):
 class Meta:
  model=Holiday
  fields=["name","date","description","holiday_type"]
  widgets={"date":forms.DateInput(attrs={"type":"date"}),"description":forms.Textarea(attrs={"rows":3})}

 def clean_name(self):
  name=self.cleaned_data["name"].strip()
  if not name:
   raise ValidationError("Holiday name cannot be blank.")
  return name

 def clean(self):
  cleaned_data=super().clean()
  name=cleaned_data.get("name")
  holiday_date=cleaned_data.get("date")
  if name and holiday_date:
   duplicates=Holiday.objects.filter(date=holiday_date,name__iexact=name)
   if self.instance.pk:
    duplicates=duplicates.exclude(pk=self.instance.pk)
   if duplicates.exists():
    self.add_error("name","A holiday with this name already exists on this date.")
  return cleaned_data

class HolidayCalendarFilterForm(forms.Form):
 q=forms.CharField(required=False,label="Search holidays",widget=forms.TextInput(attrs={"class":"form-control","placeholder":"Search holidays..."}))
 year=forms.IntegerField(required=False,min_value=1900,max_value=9999,widget=forms.NumberInput(attrs={"class":"form-control"}))
 month=forms.ChoiceField(
  required=False,
  choices=[("", "All months")]+[(str(month),date(2000,month,1).strftime("%B")) for month in range(1,13)],
  widget=forms.Select(attrs={"class":"form-select"}),
 )

class PayrollRecordForm(StyledForm):
 class MonthDateField(forms.DateField):
  def to_python(self,value):
   if value and re.fullmatch(r"\d{4}-\d{2}",str(value)):
    value=f"{value}-01"
   return super().to_python(value)

 pay_month=MonthDateField(
  input_formats=["%Y-%m-%d"],
  widget=forms.DateInput(format="%Y-%m",attrs={"type":"month"}),
  help_text="Select the month for this payroll record.",
 )
 basic_salary=forms.DecimalField(
  max_digits=12,
  decimal_places=2,
  min_value=0,
  widget=forms.NumberInput(attrs={"min":"0","step":"0.01"}),
 )
 allowances=forms.DecimalField(
  max_digits=12,
  decimal_places=2,
  min_value=0,
  widget=forms.NumberInput(attrs={"min":"0","step":"0.01"}),
 )
 deductions=forms.DecimalField(
  max_digits=12,
  decimal_places=2,
  min_value=0,
  widget=forms.NumberInput(attrs={"min":"0","step":"0.01"}),
 )

 class Meta:
  model=PayrollRecord
  fields=[
   "employee",
   "pay_month",
   "basic_salary",
   "allowances",
   "deductions",
   "payment_date",
   "payment_status",
  ]
  widgets={
   "payment_date":forms.DateInput(attrs={"type":"date"}),
   "basic_salary":forms.NumberInput(attrs={"min":"0","step":"0.01"}),
   "allowances":forms.NumberInput(attrs={"min":"0","step":"0.01"}),
   "deductions":forms.NumberInput(attrs={"min":"0","step":"0.01"}),
  }

 def clean_pay_month(self):
  pay_month=self.cleaned_data["pay_month"]
  return pay_month.replace(day=1)

 def clean(self):
  cleaned_data=super().clean()
  payment_date=cleaned_data.get("payment_date")
  pay_month=cleaned_data.get("pay_month")
  if payment_date and pay_month and payment_date<pay_month:
   self.add_error("payment_date","Payment date cannot be before the pay month.")
  basic_salary=cleaned_data.get("basic_salary")
  allowances=cleaned_data.get("allowances")
  deductions=cleaned_data.get("deductions")
  if basic_salary is not None and allowances is not None and deductions is not None:
   if deductions>basic_salary+allowances:
    self.add_error("deductions","Deductions cannot exceed gross salary.")
  return cleaned_data

class PayrollFilterForm(forms.Form):
  q=forms.CharField(required=False,label="Search employee",widget=forms.TextInput(attrs={"class":"form-control","placeholder":"Search employee..."}))
  year=forms.IntegerField(required=False,min_value=1900,max_value=9999,widget=forms.NumberInput(attrs={"class":"form-control"}))
  month=forms.ChoiceField(
   required=False,
   choices=[("", "All months")]+[(str(month),date(2000,month,1).strftime("%B")) for month in range(1,13)],
   widget=forms.Select(attrs={"class":"form-select"}),
  )

class PerformanceReviewForm(StyledForm):
  class Meta:
   model=PerformanceReview
   fields=[
    "employee",
    "review_period_start",
    "review_period_end",
    "rating",
    "goals",
    "achievements",
    "strengths",
    "improvement_areas",
    "feedback",
   ]
   widgets={
    "review_period_start":forms.DateInput(attrs={"type":"date"}),
    "review_period_end":forms.DateInput(attrs={"type":"date"}),
    "goals":forms.Textarea(attrs={"rows":4}),
    "achievements":forms.Textarea(attrs={"rows":4}),
    "strengths":forms.Textarea(attrs={"rows":3}),
    "improvement_areas":forms.Textarea(attrs={"rows":3}),
    "feedback":forms.Textarea(attrs={"rows":4}),
   }

  def clean(self):
   cleaned_data=super().clean()
   period_start=cleaned_data.get("review_period_start")
   period_end=cleaned_data.get("review_period_end")
   if period_start and period_end and period_end<period_start:
    self.add_error("review_period_end","Review period end date cannot be before its start date.")
   for field_name in ("goals","achievements","strengths","improvement_areas","feedback"):
    value=cleaned_data.get(field_name)
    if value is not None and not value.strip():
     self.add_error(field_name,"This field is required.")
   return cleaned_data

class PerformanceReviewFilterForm(forms.Form):
  q=forms.CharField(required=False,label="Search employee",widget=forms.TextInput(attrs={"class":"form-control","placeholder":"Employee name or ID"}))
  department=forms.ModelChoiceField(
   required=False,
   queryset=Department.objects.all(),
   empty_label="All departments",
   widget=forms.Select(attrs={"class":"form-select"}),
  )
  period_year=forms.IntegerField(
   required=False,
   min_value=1900,
   max_value=9999,
   widget=forms.NumberInput(attrs={"class":"form-control","placeholder":"Review year"}),
  )
  rating=forms.ChoiceField(
   required=False,
   choices=[("", "All ratings")]+[
    (str(value), label) for value,label in PerformanceReview.RATING_CHOICES
   ],
   widget=forms.Select(attrs={"class":"form-select"}),
  )

class AuditLogFilterForm(forms.Form):
  q=forms.CharField(
   required=False,
   label="Search logs",
   widget=forms.TextInput(attrs={"class":"form-control","placeholder":"Search records or descriptions"}),
  )
  user=forms.ModelChoiceField(
   required=False,
   queryset=get_user_model().objects.none(),
   empty_label="All users",
   widget=forms.Select(attrs={"class":"form-select"}),
  )
  action=forms.ChoiceField(
   required=False,
   choices=[("", "All actions")]+AuditLog.ACTION_CHOICES,
   widget=forms.Select(attrs={"class":"form-select"}),
  )
  start_date=forms.DateField(
   required=False,
   widget=forms.DateInput(attrs={"type":"date","class":"form-control"}),
  )
  end_date=forms.DateField(
   required=False,
   widget=forms.DateInput(attrs={"type":"date","class":"form-control"}),
  )

  def __init__(self,*args,**kwargs):
   super().__init__(*args,**kwargs)
   self.fields["user"].queryset=get_user_model().objects.order_by("username")

  def clean(self):
   cleaned_data=super().clean()
   start_date=cleaned_data.get("start_date")
   end_date=cleaned_data.get("end_date")
   if start_date and end_date and end_date<start_date:
    self.add_error("end_date","End date cannot be before start date.")
   return cleaned_data
  period_year=forms.IntegerField(
   required=False,
   min_value=1900,
   max_value=9999,
   label="Review year",
   widget=forms.NumberInput(attrs={"class":"form-control","placeholder":"Year"}),
  )
  rating=forms.ChoiceField(
   required=False,
   choices=[("", "All ratings")]+[(str(value),label) for value,label in PerformanceReview.RATING_CHOICES],
   widget=forms.Select(attrs={"class":"form-select"}),
  )

class ReportDateRangeForm(forms.Form):
 start_date=forms.DateField(required=False,widget=forms.DateInput(attrs={"type":"date","class":"form-control"}))
 end_date=forms.DateField(required=False,widget=forms.DateInput(attrs={"type":"date","class":"form-control"}))
 def clean(self):
  cleaned_data=super().clean()
  start_date=cleaned_data.get("start_date")
  end_date=cleaned_data.get("end_date")
  if start_date and end_date and end_date<start_date:
   raise ValidationError("End date cannot be before start date.")
  return cleaned_data

ROLE_CHOICES = (
 ("employee","Employee"),
 ("hr","HR"),
 ("admin","Admin"),
)

class ManagedUserCreationForm(UserCreationForm):
 email=forms.EmailField(widget=forms.EmailInput(attrs={"class":"form-control"}))
 first_name=forms.CharField(max_length=150,required=False,widget=forms.TextInput(attrs={"class":"form-control"}))
 last_name=forms.CharField(max_length=150,required=False,widget=forms.TextInput(attrs={"class":"form-control"}))
 role=forms.ChoiceField(choices=ROLE_CHOICES,widget=forms.Select(attrs={"class":"form-select"}))

 class Meta(UserCreationForm.Meta):
  model=get_user_model()
  fields=("username","first_name","last_name","email")

class ManagedUserChangeForm(forms.ModelForm):
 role=forms.ChoiceField(choices=ROLE_CHOICES,widget=forms.Select(attrs={"class":"form-select"}))

 class Meta:
  model=get_user_model()
  fields=("username","first_name","last_name","email","is_active")
  widgets={"is_active":forms.Select(choices=((True,"Active"),(False,"Inactive")),attrs={"class":"form-select"})}

 def __init__(self,*args,**kwargs):
  actor=kwargs.pop("actor",None)
  super().__init__(*args,**kwargs)
  self.actor_id=getattr(actor,"pk",None)
  if self.instance.pk:
   self.fields["role"].initial=role_for_user(self.instance)

 def clean(self):
  cleaned_data=super().clean()
  if not self.instance.pk:
   return cleaned_data

  requested_role=cleaned_data.get("role")
  requested_active=cleaned_data.get("is_active")
  if self.instance.is_superuser and requested_role!="admin":
   self.add_error("role","A superuser account must retain the Admin role.")
  if self.instance.pk == getattr(self,"actor_id",None) and requested_role!="admin":
   self.add_error("role","You cannot change your own role.")
  is_admin_account=self.instance.is_superuser or self.instance.groups.filter(name=ADMIN_GROUP).exists()
  if is_admin_account and self.instance.is_active and (
   not requested_active or requested_role!="admin"
  ):
   User=get_user_model()
   remaining_admins=User.objects.filter(is_active=True).filter(
    Q(is_superuser=True)|Q(groups__name=ADMIN_GROUP)
   ).exclude(pk=self.instance.pk).distinct().exists()
   if not remaining_admins:
    self.add_error(None,"The last active administrator cannot be deactivated or demoted.")
  return cleaned_data
