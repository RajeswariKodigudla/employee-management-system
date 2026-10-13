from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.forms import UserChangeForm
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Q
from .roles import ADMIN_GROUP
from .models import Department,Employee,LeaveRequest,Attendance,Holiday

class ProtectedUserChangeForm(UserChangeForm):
 def clean(self):
  cleaned_data=super().clean()
  user=self.instance
  was_admin=user.is_superuser or user.groups.filter(name=ADMIN_GROUP).exists()
  groups=cleaned_data.get("groups")
  remains_admin=cleaned_data.get("is_superuser",user.is_superuser)
  if groups is None:
   remains_admin=remains_admin or user.groups.filter(name=ADMIN_GROUP).exists()
  else:
   remains_admin=remains_admin or groups.filter(name=ADMIN_GROUP).exists()
  if was_admin and user.is_active and (
   not cleaned_data.get("is_active",user.is_active) or not remains_admin
  ):
   User=get_user_model()
   other_active_admin=User.objects.filter(is_active=True).filter(
    Q(is_superuser=True)|Q(groups__name=ADMIN_GROUP)
   ).exclude(pk=user.pk).distinct().exists()
   if not other_active_admin:
    raise ValidationError("The last active administrator cannot be deactivated or demoted.")
  return cleaned_data

class ProtectedUserAdmin(UserAdmin):
 form=ProtectedUserChangeForm

 def has_delete_permission(self,request,obj=None):
  return False

 def delete_model(self,request,obj):
  raise PermissionDenied("User deletion is disabled; deactivate the account instead.")

 def delete_queryset(self,request,queryset):
  raise PermissionDenied("User deletion is disabled; deactivate the accounts instead.")

admin.site.unregister(get_user_model())
admin.site.register(get_user_model(),ProtectedUserAdmin)

admin.site.register(Department)
@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin): list_display=("employee_id","full_name","department","designation","status"); search_fields=("employee_id","full_name","email"); list_filter=("status","department")
admin.site.register(LeaveRequest); admin.site.register(Attendance)
admin.site.register(Holiday)
