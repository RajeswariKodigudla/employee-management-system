from django.conf import settings
from django.db import models
from django.utils import timezone
import uuid
class Department(models.Model):
 name=models.CharField(max_length=100,unique=True); description=models.TextField(blank=True); created_at=models.DateTimeField(auto_now_add=True)
 class Meta: ordering=["name"]
 def __str__(self): return self.name
class Employee(models.Model):
 STATUS=[("ACTIVE","Active"),("INACTIVE","Inactive"),("ON_LEAVE","On Leave")]
 employee_id=models.CharField(max_length=20,unique=True); full_name=models.CharField(max_length=150); email=models.EmailField(unique=True); phone=models.CharField(max_length=25,blank=True); designation=models.CharField(max_length=100); department=models.ForeignKey(Department,on_delete=models.PROTECT,related_name="employees"); joining_date=models.DateField(default=timezone.localdate); status=models.CharField(max_length=12,choices=STATUS,default="ACTIVE"); address=models.TextField(blank=True); created_at=models.DateTimeField(auto_now_add=True); updated_at=models.DateTimeField(auto_now=True)
 class Meta: ordering=["full_name"]
 def __str__(self): return f"{self.employee_id} - {self.full_name}"
class LeaveRequest(models.Model):
 STATUS=[("PENDING","Pending"),("APPROVED","Approved"),("REJECTED","Rejected")]
 employee=models.ForeignKey(Employee,on_delete=models.CASCADE,related_name="leave_requests"); start_date=models.DateField(); end_date=models.DateField(); reason=models.TextField(); status=models.CharField(max_length=10,choices=STATUS,default="PENDING"); reviewed_by=models.ForeignKey(settings.AUTH_USER_MODEL,null=True,blank=True,on_delete=models.SET_NULL); created_at=models.DateTimeField(auto_now_add=True)
 class Meta: ordering=["-created_at"]
 @property
 def days_requested(self): return (self.end_date-self.start_date).days+1
class Attendance(models.Model):
 employee=models.ForeignKey(Employee,on_delete=models.CASCADE,related_name="attendance_records"); attendance_date=models.DateField(default=timezone.localdate); check_in=models.TimeField(null=True,blank=True); check_out=models.TimeField(null=True,blank=True); note=models.CharField(max_length=250,blank=True)
 class Meta:
  ordering=["-attendance_date"]; constraints=[models.UniqueConstraint(fields=["employee","attendance_date"],name="unique_employee_attendance_day")]

class Holiday(models.Model):
 TYPE_CHOICES=[
  ("PUBLIC","Public"),
  ("COMPANY","Company"),
  ("OPTIONAL","Optional"),
  ("OTHER","Other"),
 ]
 name=models.CharField(max_length=150)
 date=models.DateField()
 description=models.TextField()
 holiday_type=models.CharField(max_length=12,choices=TYPE_CHOICES,blank=True)

 class Meta:
  ordering=["date","name"]
  constraints=[
   models.UniqueConstraint(fields=["date","name"],name="unique_holiday_date_name")
  ]

 def __str__(self):
  return f"{self.name} ({self.date})"

class Notification(models.Model):
 KIND_CHOICES=[
  ("LEAVE","Pending leave request"),
  ("HOLIDAY","Upcoming company holiday"),
 ]
 user=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.CASCADE,related_name="notifications")
 kind=models.CharField(max_length=12,choices=KIND_CHOICES)
 event_key=models.CharField(max_length=100)
 title=models.CharField(max_length=200)
 message=models.TextField()
 created_at=models.DateTimeField(auto_now_add=True)
 is_read=models.BooleanField(default=False)

 class Meta:
  ordering=["-created_at","-pk"]
  constraints=[
   models.UniqueConstraint(fields=["user","event_key"],name="unique_user_notification_event")
  ]

 def __str__(self):
  return f"{self.title} — {self.user}"

class PayrollRecord(models.Model):
 PAYMENT_STATUS_CHOICES=[
  ("PENDING","Pending"),
  ("PAID","Paid"),
  ("ON_HOLD","On hold"),
 ]
 employee=models.ForeignKey(Employee,on_delete=models.PROTECT,related_name="payroll_records")
 pay_month=models.DateField(help_text="Use the first day of the payroll month.")
 basic_salary=models.DecimalField(max_digits=12,decimal_places=2)
 allowances=models.DecimalField(max_digits=12,decimal_places=2,default=0)
 deductions=models.DecimalField(max_digits=12,decimal_places=2,default=0)
 payment_date=models.DateField(null=True,blank=True)
 payment_status=models.CharField(max_length=10,choices=PAYMENT_STATUS_CHOICES,default="PENDING")
 created_at=models.DateTimeField(auto_now_add=True)
 updated_at=models.DateTimeField(auto_now=True)

 class Meta:
  ordering=["-pay_month","employee__full_name"]
  constraints=[
   models.UniqueConstraint(fields=["employee","pay_month"],name="unique_employee_payroll_month"),
   models.CheckConstraint(check=models.Q(basic_salary__gte=0),name="payroll_basic_nonnegative"),
   models.CheckConstraint(check=models.Q(allowances__gte=0),name="payroll_allowances_nonnegative"),
   models.CheckConstraint(check=models.Q(deductions__gte=0),name="payroll_deductions_nonnegative"),
   models.CheckConstraint(check=models.Q(deductions__lte=models.F("basic_salary")+models.F("allowances")),name="payroll_deductions_within_gross"),
   models.CheckConstraint(check=models.Q(pay_month__day=1),name="payroll_month_first_day"),
   models.CheckConstraint(check=models.Q(payment_status__in=["PENDING","PAID","ON_HOLD"]),name="payroll_payment_status_valid"),
  ]

 @property
 def gross_salary(self):
  return self.basic_salary+self.allowances

 @property
 def net_salary(self):
  return self.gross_salary-self.deductions

 def __str__(self):
  return f"{self.employee.full_name} — {self.pay_month:%B %Y}"

class PerformanceReview(models.Model):
 RATING_CHOICES=[
  (1,"1 - Needs improvement"),
  (2,"2 - Developing"),
  (3,"3 - Meets expectations"),
  (4,"4 - Exceeds expectations"),
  (5,"5 - Outstanding"),
 ]
 employee=models.ForeignKey(Employee,on_delete=models.PROTECT,related_name="performance_reviews")
 reviewer=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT,related_name="submitted_performance_reviews")
 review_period_start=models.DateField()
 review_period_end=models.DateField()
 rating=models.PositiveSmallIntegerField(choices=RATING_CHOICES)
 goals=models.TextField()
 achievements=models.TextField()
 strengths=models.TextField()
 improvement_areas=models.TextField()
 feedback=models.TextField()
 created_at=models.DateTimeField(auto_now_add=True)
 updated_at=models.DateTimeField(auto_now=True)

 class Meta:
  ordering=["-review_period_end","employee__full_name"]
  constraints=[
   models.CheckConstraint(check=models.Q(rating__gte=1,rating__lte=5),name="performance_rating_between_1_5"),
   models.CheckConstraint(check=models.Q(review_period_end__gte=models.F("review_period_start")),name="performance_period_end_after_start"),
  ]

 def __str__(self):
  return f"{self.employee.full_name} — {self.review_period_start:%d %b %Y} to {self.review_period_end:%d %b %Y}"

class AuditLog(models.Model):
 ACTION_CHOICES=[
  ("CREATE","Create"),
  ("UPDATE","Update"),
  ("DELETE","Delete"),
  ("APPROVE","Approve"),
  ("REJECT","Reject"),
 ]
 action_key=models.UUIDField(default=uuid.uuid4,unique=True,editable=False)
 actor=models.ForeignKey(
  settings.AUTH_USER_MODEL,
  null=True,
  blank=True,
  on_delete=models.SET_NULL,
  related_name="audit_logs",
 )
 acting_username=models.CharField(max_length=150)
 action=models.CharField(max_length=10,choices=ACTION_CHOICES)
 object_type=models.CharField(max_length=80)
 object_id=models.CharField(max_length=64)
 affected_record=models.CharField(max_length=255)
 description=models.CharField(max_length=255)
 changes=models.JSONField(default=dict,blank=True)
 timestamp=models.DateTimeField(auto_now_add=True)

 class Meta:
  ordering=["-timestamp","-pk"]
  default_permissions=("view",)
  constraints=[
   models.CheckConstraint(check=models.Q(action__in=["CREATE","UPDATE","DELETE","APPROVE","REJECT"]),name="audit_log_action_valid"),
  ]

 def __str__(self):
  return f"{self.get_action_display()} {self.affected_record} by {self.acting_username}"
