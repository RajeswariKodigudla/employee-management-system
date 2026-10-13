import csv
import calendar
from datetime import date
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required,permission_required
from django.contrib.auth.forms import UserCreationForm
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Avg,Count,Q,Sum
from django.db.models.functions import TruncMonth
from django.http import HttpResponse
from django.shortcuts import render,redirect,get_object_or_404
from django.utils.http import content_disposition_header
from django.views.decorators.http import require_GET,require_POST
from django.utils import timezone
from .models import Employee,Department,LeaveRequest,Attendance,Holiday,Notification,PayrollRecord,PerformanceReview,AuditLog
from .forms import EmployeeForm,DepartmentForm,LeaveForm,AttendanceForm,ReportDateRangeForm,ManagedUserCreationForm,ManagedUserChangeForm,HolidayForm,HolidayCalendarFilterForm,PayrollRecordForm,PayrollFilterForm,PerformanceReviewForm,PerformanceReviewFilterForm,AuditLogFilterForm
from .roles import ADMIN_GROUP,assign_role,role_for_user
from .notifications import sync_user_notifications
from .payslips import generate_payslip_pdf
from .audit import record_audit_event

User=get_user_model()
def register(request):
 form=UserCreationForm(request.POST or None)
 if request.method=="POST" and form.is_valid(): form.save(); messages.success(request,"Account created. Sign in to continue."); return redirect("login")
 return render(request,"registration/register.html",{"form":form})
@login_required
def dashboard(request):
 total=Employee.objects.count()
 return render(request,"core/dashboard.html",{"total":total,"active":Employee.objects.filter(status="ACTIVE").count(),"inactive":Employee.objects.filter(status="INACTIVE").count(),"departments":Department.objects.count(),"pending":LeaveRequest.objects.filter(status="PENDING").count(),"recent":Employee.objects.select_related("department").order_by("-created_at")[:6],"dept_stats":Department.objects.annotate(n=Count("employees")).order_by("-n")[:6]})
@login_required
def employee_list(request):
 qs=Employee.objects.select_related("department"); q=request.GET.get("q","").strip(); dep=request.GET.get("department",""); status=request.GET.get("status","")
 if q: qs=qs.filter(Q(full_name__icontains=q)|Q(employee_id__icontains=q)|Q(email__icontains=q))
 if dep: qs=qs.filter(department_id=dep)
 if status: qs=qs.filter(status=status)
 return render(request,"core/employees.html",{"employees":qs,"departments":Department.objects.all(),"q":q,"dep":dep,"status":status})
@login_required
def employee_detail(request,pk): return render(request,"core/employee_detail.html",{"e":get_object_or_404(Employee.objects.select_related("department"),pk=pk)})
@permission_required("core.add_employee",raise_exception=True)
def employee_create(request):
 form=EmployeeForm(request.POST or None)
 if request.method=="POST" and form.is_valid():
  with transaction.atomic():
   employee=form.save()
   record_audit_event(
    actor=request.user,
    action="CREATE",
    instance=employee,
    description="Employee record created.",
    after={
     "employee_id":employee.employee_id,
     "name":employee.full_name,
     "department":employee.department.name,
     "designation":employee.designation,
     "status":employee.get_status_display(),
    },
   )
  messages.success(request,"Employee created successfully.")
  return redirect("employee_list")
 return render(request,"core/form.html",{"form":form,"title":"Add employee","back":"employee_list"})
@permission_required("core.change_employee",raise_exception=True)
def employee_update(request,pk):
 e=get_object_or_404(Employee,pk=pk); form=EmployeeForm(request.POST or None,instance=e)
 before={
  "name":e.full_name,
  "department":e.department.name,
  "designation":e.designation,
  "status":e.get_status_display(),
 }
 if request.method=="POST" and form.is_valid():
  with transaction.atomic():
   e=form.save()
   record_audit_event(
    actor=request.user,
    action="UPDATE",
    instance=e,
    description="Employee record updated.",
    before=before,
    after={
     "name":e.full_name,
     "department":e.department.name,
     "designation":e.designation,
     "status":e.get_status_display(),
    },
   )
  messages.success(request,"Employee updated successfully.")
  return redirect("employee_detail",pk=e.pk)
 return render(request,"core/form.html",{"form":form,"title":"Edit employee","back":"employee_list"})
@permission_required("core.delete_employee",raise_exception=True)
@require_POST
def employee_delete(request,pk):
 employee=get_object_or_404(Employee.objects.select_related("department"),pk=pk)
 with transaction.atomic():
  record_audit_event(
   actor=request.user,
   action="DELETE",
   instance=employee,
   description="Employee record deleted.",
   before={
    "employee_id":employee.employee_id,
    "name":employee.full_name,
    "department":employee.department.name,
   },
  )
  employee.delete()
 messages.success(request,"Employee deleted.")
 return redirect("employee_list")
@permission_required("core.delete_employee",raise_exception=True)
@require_POST
def bulk_delete(request):
 ids=request.POST.getlist("selected_ids")
 if ids:
  employees=list(Employee.objects.filter(pk__in=ids).select_related("department"))
  with transaction.atomic():
   for employee in employees:
    record_audit_event(
     actor=request.user,
     action="DELETE",
     instance=employee,
     description="Employee record deleted through bulk action.",
     before={
      "employee_id":employee.employee_id,
      "name":employee.full_name,
      "department":employee.department.name,
     },
    )
   Employee.objects.filter(pk__in=[employee.pk for employee in employees]).delete()
  messages.success(request,"Selected employee records deleted.")
 else: messages.error(request,"Select at least one employee.")
 return redirect("employee_list")
@permission_required("auth.view_user",raise_exception=True)
@require_POST
def delete_all(request):
 if request.user.has_perm("auth.view_user") and request.POST.get("confirm_text")=="DELETE ALL":
  employees=list(Employee.objects.select_related("department"))
  with transaction.atomic():
   for employee in employees:
    record_audit_event(
     actor=request.user,
     action="DELETE",
     instance=employee,
     description="Employee record deleted through delete-all action.",
     before={
      "employee_id":employee.employee_id,
      "name":employee.full_name,
      "department":employee.department.name,
     },
    )
   Employee.objects.all().delete()
  messages.warning(request,f"Deleted {len(employees)} employee records.")
 else: messages.error(request,'Only an administrator can do this. Type "DELETE ALL" to confirm.')
 return redirect("employee_list")
@login_required
def department_list(request):
 q=request.GET.get("q","").strip(); ds=Department.objects.annotate(n=Count("employees"))
 if q: ds=ds.filter(Q(name__icontains=q)|Q(description__icontains=q))
 return render(request,"core/departments.html",{"departments":ds,"q":q})
@permission_required("core.add_department",raise_exception=True)
def department_create(request):
 form=DepartmentForm(request.POST or None)
 if request.method=="POST" and form.is_valid():
  with transaction.atomic():
   department=form.save()
   record_audit_event(
    actor=request.user,
    action="CREATE",
    instance=department,
    description="Department created.",
    after={"name":department.name},
   )
  messages.success(request,"Department created.")
  return redirect("department_list")
 return render(request,"core/form.html",{"form":form,"title":"Add department","back":"department_list"})
@permission_required("core.change_department",raise_exception=True)
def department_update(request,pk):
 obj=get_object_or_404(Department,pk=pk); form=DepartmentForm(request.POST or None,instance=obj)
 before={"name":obj.name}
 if request.method=="POST" and form.is_valid():
  with transaction.atomic():
   obj=form.save()
   record_audit_event(
    actor=request.user,
    action="UPDATE",
    instance=obj,
    description="Department updated.",
    before=before,
    after={"name":obj.name},
   )
  messages.success(request,"Department updated.")
  return redirect("department_list")
 return render(request,"core/form.html",{"form":form,"title":"Edit department","back":"department_list"})
@permission_required("core.delete_department",raise_exception=True)
@require_POST
def department_delete(request,pk):
 obj=get_object_or_404(Department,pk=pk)
 if obj.employees.exists(): messages.error(request,"Reassign employees before deleting this department.")
 else:
  name=obj.name
  with transaction.atomic():
   record_audit_event(
    actor=request.user,
    action="DELETE",
    instance=obj,
    description="Department deleted.",
    before={"name":name},
   )
   obj.delete()
  messages.success(request,"Department deleted.")
 return redirect("department_list")
@permission_required("core.view_attendance",raise_exception=True)
def attendance_list(request): return render(request,"core/attendance.html",{"records":Attendance.objects.select_related("employee")})
@permission_required("core.add_attendance",raise_exception=True)
def attendance_create(request):
 form=AttendanceForm(request.POST or None)
 if request.method=="POST" and form.is_valid(): form.save(); messages.success(request,"Attendance saved."); return redirect("attendance_list")
 return render(request,"core/form.html",{"form":form,"title":"Record attendance","back":"attendance_list"})
@permission_required("core.view_leaverequest",raise_exception=True)
def leave_list(request): return render(request,"core/leaves.html",{"leaves":LeaveRequest.objects.select_related("employee")})
@permission_required("core.add_leaverequest",raise_exception=True)
def leave_create(request):
 form=LeaveForm(request.POST or None)
 if request.method=="POST" and form.is_valid(): form.save(); messages.success(request,"Leave request saved."); return redirect("leave_list")
 return render(request,"core/form.html",{"form":form,"title":"Create leave request","back":"leave_list"})
@permission_required("core.change_leaverequest",raise_exception=True)
@require_POST
def leave_review(request,pk,decision):
 obj=get_object_or_404(LeaveRequest,pk=pk)
 if decision in ["approve","reject"]:
  old_status=obj.get_status_display()
  obj.status="APPROVED" if decision=="approve" else "REJECTED"
  obj.reviewed_by=request.user
  with transaction.atomic():
   obj.save(update_fields=["status","reviewed_by"])
   record_audit_event(
    actor=request.user,
    action="APPROVE" if decision=="approve" else "REJECT",
    instance=obj,
    description=f"Leave request {obj.get_status_display().lower()}.",
    before={"status":old_status},
    after={"status":obj.get_status_display()},
   )
  messages.success(request,"Leave request updated.")
 return redirect("leave_list")
@permission_required("core.view_employee",raise_exception=True)
def export_csv(request):
 response=HttpResponse(content_type="text/csv"); response["Content-Disposition"]='attachment; filename="employees.csv"'; w=csv.writer(response); w.writerow(["ID","Name","Email","Department","Designation","Joining date","Status"])
 for e in Employee.objects.select_related("department"): w.writerow([e.employee_id,e.full_name,e.email,e.department.name,e.designation,e.joining_date,e.get_status_display()])
 return response

def _report_context(start_date=None,end_date=None):
 employee_filters={}
 attendance_filters={}
 leave_filters={}
 if start_date:
  employee_filters["joining_date__gte"]=start_date
  attendance_filters["attendance_date__gte"]=start_date
  leave_filters["start_date__gte"]=start_date
 if end_date:
  employee_filters["joining_date__lte"]=end_date
  attendance_filters["attendance_date__lte"]=end_date
  leave_filters["start_date__lte"]=end_date

 department_filter=Q()
 if start_date:
  department_filter &= Q(employees__joining_date__gte=start_date)
 if end_date:
  department_filter &= Q(employees__joining_date__lte=end_date)
 department_count=Count("employees",filter=department_filter) if start_date or end_date else Count("employees")
 departments=Department.objects.annotate(employee_count=department_count).order_by("name")
 attendance_months=list(
  Attendance.objects.filter(**attendance_filters)
  .annotate(month=TruncMonth("attendance_date"))
  .values("month")
  .annotate(total=Count("pk"))
  .order_by("month")
 )
 attendance_rows=[
  {"month":row["month"].strftime("%b %Y"),"count":row["total"]}
  for row in attendance_months
 ]
 leave_totals=dict(
  LeaveRequest.objects.filter(**leave_filters)
  .values_list("status")
  .annotate(total=Count("pk"))
 )
 leave_counts=[
  {"status":status,"label":label,"count":leave_totals.get(status,0)}
  for status,label in LeaveRequest.STATUS
 ]
 attendance_count=sum(row["total"] for row in attendance_months)
 leave_request_count=sum(row["count"] for row in leave_counts)
 department_rows=[
  {"name":department.name,"count":department.employee_count}
  for department in departments
 ]
 return {
  "total_employees":Employee.objects.filter(**employee_filters).count(),
  "attendance_count":attendance_count,
  "leave_request_count":leave_request_count,
  "has_leave_requests":leave_request_count > 0,
  "department_rows":department_rows,
  "attendance_rows":attendance_rows,
  "leave_counts":leave_counts,
  "start_date":start_date,
  "end_date":end_date,
 }

@permission_required("core.view_attendance",raise_exception=True)
def reports(request):
 form=ReportDateRangeForm(request.GET)
 context={"form":form,"report_valid":form.is_valid()}
 if form.is_valid():
  context.update(_report_context(**form.cleaned_data))
 else:
  context.update({"total_employees":0,"attendance_count":0,"leave_request_count":0,"has_leave_requests":False,"department_rows":[],"attendance_rows":[],"leave_counts":[],"start_date":None,"end_date":None})
 return render(request,"core/reports.html",context)

@permission_required("core.view_attendance",raise_exception=True)
def reports_export_csv(request):
 form=ReportDateRangeForm(request.GET)
 if not form.is_valid():
  return HttpResponse("Invalid date range.",status=400,content_type="text/plain")
 context=_report_context(**form.cleaned_data)
 response=HttpResponse(content_type="text/csv; charset=utf-8")
 response["Content-Disposition"]='attachment; filename="employee-reports.csv"'
 writer=csv.writer(response)
 writer.writerow(["Report","Period start","Period end","Category","Count"])
 start_date=context["start_date"].isoformat() if context["start_date"] else "All"
 end_date=context["end_date"].isoformat() if context["end_date"] else "All"
 writer.writerow(["Employees",start_date,end_date,"Total employees",context["total_employees"]])
 for row in context["department_rows"]:
  writer.writerow(["Employees by department",start_date,end_date,row["name"],row["count"]])
 for row in context["attendance_rows"]:
  writer.writerow(["Monthly attendance records",start_date,end_date,row["month"],row["count"]])
 for row in context["leave_counts"]:
  writer.writerow(["Leave requests",start_date,end_date,row["label"],row["count"]])
 return response

@permission_required("auth.view_user",raise_exception=True)
def user_list(request):
 users=User.objects.prefetch_related("groups").order_by("username")
 page=Paginator(users,25).get_page(request.GET.get("page"))
 for user in page.object_list:
  user.display_role=role_for_user(user)
 return render(request,"core/users.html",{"users":page})

@permission_required("auth.view_user",raise_exception=True)
def user_create(request):
 form=ManagedUserCreationForm(request.POST or None)
 if request.method=="POST" and form.is_valid():
  with transaction.atomic():
   user=form.save()
   assign_role(user,form.cleaned_data["role"])
  messages.success(request,"User created successfully.")
  return redirect("user_list")
 return render(request,"core/user_form.html",{"form":form,"title":"Create user"})

@permission_required("auth.view_user",raise_exception=True)
def user_update(request,pk):
 if request.method=="POST":
  with transaction.atomic():
   active_users=list(
    User.objects.select_for_update()
    .filter(is_active=True)
    .order_by("pk")
    .prefetch_related("groups")
   )
   user=next((active_user for active_user in active_users if active_user.pk==pk),None)
   if user is None:
    user=get_object_or_404(User.objects.select_for_update().prefetch_related("groups"),pk=pk)
   form=ManagedUserChangeForm(request.POST,instance=user,actor=request.user)
   if form.is_valid():
    requested_role=form.cleaned_data["role"]
    relinquishing_admin=user.is_superuser or user.groups.filter(name=ADMIN_GROUP).exists()
    losing_active_admin=relinquishing_admin and user.is_active and (
     not form.cleaned_data["is_active"] or requested_role!="admin"
    )
    active_admins=[
     active_user for active_user in active_users
     if active_user.is_superuser or active_user.groups.filter(name=ADMIN_GROUP).exists()
    ]
    if losing_active_admin and len(active_admins)<=1:
     form.add_error(None,"The last active administrator cannot be deactivated or demoted.")
    else:
     updated_user=form.save()
     assign_role(updated_user,requested_role)
     messages.success(request,"User details updated successfully.")
     return redirect("user_list")
 else:
  user=get_object_or_404(User.objects.prefetch_related("groups"),pk=pk)
  form=ManagedUserChangeForm(instance=user,actor=request.user)
 return render(request,"core/user_form.html",{"form":form,"title":"Edit user","target_user":user})

def _filtered_payroll(request):
 form=PayrollFilterForm(request.GET)
 records=PayrollRecord.objects.select_related("employee","employee__department")
 if not form.is_valid():
  return form,records.none()
 query=form.cleaned_data["q"].strip()
 if query:
  records=records.filter(
   Q(employee__full_name__icontains=query)
   |Q(employee__employee_id__icontains=query)
  )
 if form.cleaned_data["year"]:
  records=records.filter(pay_month__year=form.cleaned_data["year"])
 if form.cleaned_data["month"]:
  records=records.filter(pay_month__month=form.cleaned_data["month"])
 return form,records

@permission_required("core.view_payrollrecord",raise_exception=True)
def payroll_list(request):
 form,records=_filtered_payroll(request)
 totals=records.aggregate(
  basic_total=Sum("basic_salary"),
  allowances_total=Sum("allowances"),
  deductions_total=Sum("deductions"),
 )
 totals={key:value or 0 for key,value in totals.items()}
 totals["gross_total"]=totals["basic_total"]+totals["allowances_total"]
 totals["net_total"]=totals["gross_total"]-totals["deductions_total"]
 monthly_summaries=list(
  records.values("pay_month")
  .annotate(
   record_count=Count("pk"),
   basic_total=Sum("basic_salary"),
   allowances_total=Sum("allowances"),
   deductions_total=Sum("deductions"),
  )
  .order_by("-pay_month")
 )
 for summary in monthly_summaries:
  summary["gross_total"]=summary["basic_total"]+summary["allowances_total"]
  summary["net_total"]=summary["gross_total"]-summary["deductions_total"]
 return render(request,"core/payroll.html",{
  "form":form,
  "records":records,
  "totals":totals,
  "record_count":records.count(),
  "monthly_summaries":monthly_summaries,
 })

@permission_required("core.add_payrollrecord",raise_exception=True)
def payroll_create(request):
 form=PayrollRecordForm(request.POST or None)
 if request.method=="POST" and form.is_valid():
  with transaction.atomic():
   record=form.save()
   record_audit_event(
    actor=request.user,
    action="CREATE",
    instance=record,
    description="Payroll record created.",
    after={
     "employee_id":record.employee.employee_id,
     "pay_month":record.pay_month.isoformat(),
     "payment_status":record.get_payment_status_display(),
    },
   )
  messages.success(request,"Payroll record created successfully.")
  return redirect("payroll_history",employee_id=record.employee_id)
 return render(request,"core/payroll_form.html",{"form":form,"title":"Create payroll record"})

@permission_required("core.change_payrollrecord",raise_exception=True)
def payroll_update(request,pk):
 record=get_object_or_404(PayrollRecord.objects.select_related("employee"),pk=pk)
 form=PayrollRecordForm(request.POST or None,instance=record)
 before={
  "employee_id":record.employee.employee_id,
  "pay_month":record.pay_month.isoformat(),
  "payment_status":record.get_payment_status_display(),
  "payment_date":record.payment_date.isoformat() if record.payment_date else None,
 }
 if request.method=="POST" and form.is_valid():
  with transaction.atomic():
   record=form.save()
   record_audit_event(
    actor=request.user,
    action="UPDATE",
    instance=record,
    description="Payroll record updated; salary amounts excluded from audit details.",
    before=before,
    after={
     "employee_id":record.employee.employee_id,
     "pay_month":record.pay_month.isoformat(),
     "payment_status":record.get_payment_status_display(),
     "payment_date":record.payment_date.isoformat() if record.payment_date else None,
    },
   )
  messages.success(request,"Payroll record updated successfully.")
  return redirect("payroll_history",employee_id=record.employee_id)
 return render(request,"core/payroll_form.html",{"form":form,"title":"Edit payroll record","record":record})

@permission_required("core.delete_payrollrecord",raise_exception=True)
@require_POST
def payroll_delete(request,pk):
 record=get_object_or_404(PayrollRecord.objects.select_related("employee"),pk=pk)
 before={
  "employee_id":record.employee.employee_id,
  "pay_month":record.pay_month.isoformat(),
  "payment_status":record.get_payment_status_display(),
 }
 with transaction.atomic():
  record_audit_event(
   actor=request.user,
   action="DELETE",
   instance=record,
   description="Payroll record deleted; salary amounts excluded from audit details.",
   before=before,
  )
  record.delete()
 messages.success(request,"Payroll record deleted.")
 return redirect("payroll_list")

@permission_required("core.view_payrollrecord",raise_exception=True)
def payroll_history(request,employee_id):
 employee=get_object_or_404(Employee,pk=employee_id)
 records=PayrollRecord.objects.filter(employee=employee).order_by("-pay_month")
 totals=records.aggregate(
  basic_total=Sum("basic_salary"),
  allowances_total=Sum("allowances"),
  deductions_total=Sum("deductions"),
 )
 return render(request,"core/payroll_history.html",{
  "employee":employee,
  "records":records,
  "totals":{key:value or 0 for key,value in totals.items()},
 })

@permission_required("core.view_payrollrecord",raise_exception=True)
def payroll_export_csv(request):
 form,records=_filtered_payroll(request)
 if not form.is_valid():
  return HttpResponse("Invalid payroll filters.",status=400,content_type="text/plain")
 response=HttpResponse(content_type="text/csv; charset=utf-8")
 response["Content-Disposition"]='attachment; filename="payroll-report.csv"'
 writer=csv.writer(response)
 writer.writerow(["Employee ID","Employee","Department","Pay month","Basic salary","Allowances","Gross salary","Deductions","Net salary","Payment date","Payment status"])
 for record in records:
  writer.writerow([
   record.employee.employee_id,
   record.employee.full_name,
   record.employee.department.name,
   record.pay_month.isoformat(),
   record.basic_salary,
   record.allowances,
   record.gross_salary,
   record.deductions,
   record.net_salary,
   record.payment_date.isoformat() if record.payment_date else "",
   record.get_payment_status_display(),
  ])
 return response

@login_required
@permission_required("core.view_payrollrecord",raise_exception=True)
def payroll_payslip(request,pk):
  record=get_object_or_404(
   PayrollRecord.objects.select_related("employee","employee__department"),
   pk=pk,
  )
  pdf=generate_payslip_pdf(record)
  filename=(
   f"payslip-{record.employee.employee_id}-"
   f"{record.pay_month:%Y-%m}.pdf"
  )
  response=HttpResponse(pdf,content_type="application/pdf")
  response["Content-Disposition"]=content_disposition_header(
   as_attachment=True,
   filename=filename,
  )
  return response

def _filtered_performance_reviews(request):
  form=PerformanceReviewFilterForm(request.GET)
  reviews=PerformanceReview.objects.select_related(
   "employee","employee__department","reviewer",
  )
  if not form.is_valid():
   return form,reviews.none()
  query=form.cleaned_data["q"].strip()
  if query:
   reviews=reviews.filter(
    Q(employee__full_name__icontains=query)
    |Q(employee__employee_id__icontains=query)
   )
  department=form.cleaned_data["department"]
  if department:
   reviews=reviews.filter(employee__department=department)
  if form.cleaned_data["period_year"]:
   reviews=reviews.filter(review_period_start__year=form.cleaned_data["period_year"])
  if form.cleaned_data["rating"]:
   reviews=reviews.filter(rating=form.cleaned_data["rating"])
  return form,reviews

@permission_required("core.view_performancereview",raise_exception=True)
def performance_list(request):
  form,reviews=_filtered_performance_reviews(request)
  summary=reviews.aggregate(
   review_count=Count("pk"),
   average_rating=Avg("rating"),
  )
  rating_summary=list(
   reviews.values("rating")
   .annotate(count=Count("pk"))
   .order_by("rating")
  )
  rating_labels=dict(PerformanceReview.RATING_CHOICES)
  for row in rating_summary:
   row["label"]=rating_labels[row["rating"]]
  employee_summary=list(
   reviews.values(
    "employee_id",
    "employee__full_name",
    "employee__employee_id",
    "employee__department__name",
   )
   .annotate(review_count=Count("pk"),average_rating=Avg("rating"))
   .order_by("employee__full_name")
  )
  page=Paginator(reviews,25).get_page(request.GET.get("page"))
  return render(request,"core/performance.html",{
   "form":form,
   "reviews":page,
   "summary":summary,
   "rating_summary":rating_summary,
   "employee_summary":employee_summary,
  })

@permission_required("core.add_performancereview",raise_exception=True)
def performance_create(request):
  form=PerformanceReviewForm(request.POST or None)
  if request.method=="POST" and form.is_valid():
   review=form.save(commit=False)
   review.reviewer=request.user
   with transaction.atomic():
    review.save()
    record_audit_event(
     actor=request.user,
     action="CREATE",
     instance=review,
     description="Performance review created; appraisal text excluded from audit details.",
     after={
      "employee_id":review.employee.employee_id,
      "period_start":review.review_period_start.isoformat(),
      "period_end":review.review_period_end.isoformat(),
      "rating":review.rating,
     },
    )
   messages.success(request,"Performance review created successfully.")
   return redirect("performance_history",employee_id=review.employee_id)
  return render(request,"core/performance_form.html",{
   "form":form,
   "title":"Create performance review",
  })

@permission_required("core.change_performancereview",raise_exception=True)
def performance_update(request,pk):
  review=get_object_or_404(
   PerformanceReview.objects.select_related("employee","reviewer"),
   pk=pk,
  )
  form=PerformanceReviewForm(request.POST or None,instance=review)
  before={
   "employee_id":review.employee.employee_id,
   "period_start":review.review_period_start.isoformat(),
   "period_end":review.review_period_end.isoformat(),
   "rating":review.rating,
  }
  if request.method=="POST" and form.is_valid():
   updated_review=form.save(commit=False)
   updated_review.reviewer=review.reviewer
   with transaction.atomic():
    updated_review.save()
    record_audit_event(
     actor=request.user,
     action="UPDATE",
     instance=updated_review,
     description="Performance review updated; appraisal text excluded from audit details.",
     before=before,
     after={
      "employee_id":updated_review.employee.employee_id,
      "period_start":updated_review.review_period_start.isoformat(),
      "period_end":updated_review.review_period_end.isoformat(),
      "rating":updated_review.rating,
     },
    )
   messages.success(request,"Performance review updated successfully.")
   return redirect("performance_history",employee_id=updated_review.employee_id)
  return render(request,"core/performance_form.html",{
   "form":form,
   "title":"Edit performance review",
   "review":review,
  })

@permission_required("core.delete_performancereview",raise_exception=True)
@require_POST
def performance_delete(request,pk):
  review=get_object_or_404(
   PerformanceReview.objects.select_related("employee"),
   pk=pk,
  )
  employee_id=review.employee_id
  before={
   "employee_id":review.employee.employee_id,
   "period_start":review.review_period_start.isoformat(),
   "period_end":review.review_period_end.isoformat(),
   "rating":review.rating,
  }
  with transaction.atomic():
   record_audit_event(
    actor=request.user,
    action="DELETE",
    instance=review,
    description="Performance review deleted; appraisal text excluded from audit details.",
    before=before,
   )
   review.delete()
  messages.success(request,"Performance review deleted.")
  return redirect("performance_history",employee_id=employee_id)

@permission_required("core.view_performancereview",raise_exception=True)
def performance_history(request,employee_id):
  employee=get_object_or_404(
   Employee.objects.select_related("department"),
   pk=employee_id,
  )
  reviews=PerformanceReview.objects.filter(employee=employee).select_related("reviewer")
  summary=reviews.aggregate(
   review_count=Count("pk"),
   average_rating=Avg("rating"),
  )
  return render(request,"core/performance_history.html",{
   "employee":employee,
   "reviews":reviews,
   "summary":summary,
  })

@permission_required("core.view_performancereview",raise_exception=True)
def performance_export_csv(request):
  form,reviews=_filtered_performance_reviews(request)
  if not form.is_valid():
   return HttpResponse("Invalid performance review filters.",status=400,content_type="text/plain")
  response=HttpResponse(content_type="text/csv; charset=utf-8")
  response["Content-Disposition"]='attachment; filename="performance-reviews.csv"'
  writer=csv.writer(response)
  writer.writerow([
   "Employee ID","Employee","Department","Review period start","Review period end",
   "Reviewer","Rating","Goals","Achievements","Strengths","Improvement areas","Feedback",
  ])
  for review in reviews:
   writer.writerow([
    review.employee.employee_id,
    review.employee.full_name,
    review.employee.department.name,
    review.review_period_start.isoformat(),
    review.review_period_end.isoformat(),
    review.reviewer.get_full_name() or review.reviewer.username,
    review.get_rating_display(),
    review.goals,
    review.achievements,
    review.strengths,
    review.improvement_areas,
    review.feedback,
   ])
  return response

@permission_required("core.view_holiday",raise_exception=True)
def holiday_calendar(request):
 today=timezone.localdate()
 form=HolidayCalendarFilterForm(
  request.GET or {"year":today.year,"month":today.month}
 )
 if form.is_valid():
  year=form.cleaned_data["year"] or today.year
  month=int(form.cleaned_data["month"] or today.month)
  query=form.cleaned_data["q"]
 else:
  year=today.year
  month=today.month
  query=""

 base_holidays=Holiday.objects.all()
 if query:
  base_holidays=base_holidays.filter(Q(name__icontains=query)|Q(description__icontains=query))
 calendar_holidays=base_holidays.filter(date__year=year,date__month=month)
 holidays_by_date={}
 for holiday in calendar_holidays:
  holidays_by_date.setdefault(holiday.date,[]).append(holiday)

 calendar_builder=calendar.Calendar(firstweekday=calendar.MONDAY)
 weeks=[]
 for days in calendar_builder.monthdayscalendar(year,month):
  week=[]
  for day in days:
   current_date=date(year,month,day) if day else None
   week.append({
    "day":day,
    "date":current_date,
    "holidays":holidays_by_date.get(current_date,[]) if current_date else [],
   })
  weeks.append(week)
 previous_month=date(year if month>1 else year-1,month-1 if month>1 else 12,1)
 next_month=date(year if month<12 else year+1,month+1 if month<12 else 1,1)
 upcoming=base_holidays.filter(date__gte=today)
 if form.is_valid() and form.cleaned_data["year"]:
  upcoming=upcoming.filter(date__year=year)
 if form.is_valid() and form.cleaned_data["month"]:
  upcoming=upcoming.filter(date__month=month)
 context={
  "form":form,
  "calendar_year":year,
  "calendar_month":month,
  "month_name":date(year,month,1).strftime("%B"),
  "weeks":weeks,
  "calendar_holidays":calendar_holidays,
  "upcoming_holidays":upcoming.order_by("date","name")[:8],
  "holiday_count":calendar_holidays.count(),
  "query":query,
  "previous_month":previous_month,
  "next_month":next_month,
  "calendar_today":today,
 }
 return render(request,"core/holidays.html",context)

@permission_required("core.add_holiday",raise_exception=True)
def holiday_create(request):
 form=HolidayForm(request.POST or None)
 if request.method=="POST" and form.is_valid():
  with transaction.atomic():
   holiday=form.save()
   record_audit_event(
    actor=request.user,
    action="CREATE",
    instance=holiday,
    description="Company holiday created.",
    after={
     "name":holiday.name,
     "date":holiday.date.isoformat(),
     "type":holiday.get_holiday_type_display(),
    },
   )
  messages.success(request,f"{holiday.name} was added to the holiday calendar.")
  return redirect("holiday_calendar")
 return render(request,"core/holiday_form.html",{"form":form,"title":"Add holiday"})

@permission_required("core.change_holiday",raise_exception=True)
def holiday_update(request,pk):
 holiday=get_object_or_404(Holiday,pk=pk)
 form=HolidayForm(request.POST or None,instance=holiday)
 before={
  "name":holiday.name,
  "date":holiday.date.isoformat(),
  "type":holiday.get_holiday_type_display(),
 }
 if request.method=="POST" and form.is_valid():
  with transaction.atomic():
   holiday=form.save()
   record_audit_event(
    actor=request.user,
    action="UPDATE",
    instance=holiday,
    description="Company holiday updated.",
    before=before,
    after={
     "name":holiday.name,
     "date":holiday.date.isoformat(),
     "type":holiday.get_holiday_type_display(),
    },
   )
  messages.success(request,"Holiday updated successfully.")
  return redirect("holiday_calendar")
 return render(request,"core/holiday_form.html",{"form":form,"title":"Edit holiday","holiday":holiday})

@permission_required("core.delete_holiday",raise_exception=True)
@require_POST
def holiday_delete(request,pk):
 holiday=get_object_or_404(Holiday,pk=pk)
 name=holiday.name
 before={
  "name":holiday.name,
  "date":holiday.date.isoformat(),
  "type":holiday.get_holiday_type_display(),
 }
 with transaction.atomic():
  record_audit_event(
   actor=request.user,
   action="DELETE",
   instance=holiday,
   description="Company holiday deleted.",
   before=before,
  )
  holiday.delete()
 messages.success(request,f"{name} was removed from the holiday calendar.")
 return redirect("holiday_calendar")

@login_required
def notification_list(request):
 sync_user_notifications(request.user)
 status=request.GET.get("status","all")
 notifications=Notification.objects.filter(user=request.user)
 if status=="read":
  notifications=notifications.filter(is_read=True)
 elif status=="unread":
  notifications=notifications.filter(is_read=False)
 else:
  status="all"
 page=Paginator(notifications,20).get_page(request.GET.get("page"))
 return render(
  request,
  "core/notifications.html",
  {
   "notifications":page,
   "status":status,
   "unread_count":Notification.objects.filter(user=request.user,is_read=False).count(),
  },
 )

@login_required
@require_POST
def notification_mark_read(request,pk):
 notification=get_object_or_404(Notification,user=request.user,pk=pk)
 if not notification.is_read:
  notification.is_read=True
  notification.save(update_fields=["is_read"])
 return redirect("notification_list")

@login_required
@require_POST
def notification_mark_all_read(request):
 Notification.objects.filter(user=request.user,is_read=False).update(is_read=True)
 messages.success(request,"All notifications have been marked as read.")
 return redirect("notification_list")

@permission_required("core.view_auditlog",raise_exception=True)
@require_GET
def audit_log_list(request):
 form=AuditLogFilterForm(request.GET)
 logs=AuditLog.objects.select_related("actor")
 if form.is_valid():
  query=form.cleaned_data["q"].strip()
  if query:
   logs=logs.filter(
    Q(acting_username__icontains=query)
    |Q(object_type__icontains=query)
    |Q(affected_record__icontains=query)
    |Q(description__icontains=query)
   )
  if form.cleaned_data["user"]:
   logs=logs.filter(actor=form.cleaned_data["user"])
  if form.cleaned_data["action"]:
   logs=logs.filter(action=form.cleaned_data["action"])
  if form.cleaned_data["start_date"]:
   logs=logs.filter(timestamp__date__gte=form.cleaned_data["start_date"])
  if form.cleaned_data["end_date"]:
   logs=logs.filter(timestamp__date__lte=form.cleaned_data["end_date"])
 else:
  logs=logs.none()
 page=Paginator(logs,25).get_page(request.GET.get("page"))
 return render(request,"core/audit_logs.html",{
  "form":form,
  "logs":page,
 })
