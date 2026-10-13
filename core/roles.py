from django.contrib.auth.models import Group

ADMIN_GROUP = "Admin"
HR_GROUP = "HR"


def role_for_user(user):
    group_names = {group.name for group in user.groups.all()}
    if user.is_superuser or ADMIN_GROUP in group_names:
        return "admin"
    if HR_GROUP in group_names:
        return "hr"
    return "employee"


def assign_role(user, role):
    admin_group = Group.objects.get(name=ADMIN_GROUP)
    hr_group = Group.objects.get(name=HR_GROUP)
    user.groups.remove(admin_group, hr_group)
    if role == "admin":
        user.groups.add(admin_group)
    elif role == "hr":
        user.groups.add(hr_group)
    elif role != "employee":
        raise ValueError(f"Unsupported user role: {role}")
    user.is_staff = role in ("admin", "hr")
    user.save(update_fields=["is_staff"])
