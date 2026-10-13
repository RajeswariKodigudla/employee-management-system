from django.conf import settings
from django.db import migrations


ADMIN_GROUP = "Admin"
HR_GROUP = "HR"


def create_roles_and_migrate_staff(apps, schema_editor):
    db_alias = schema_editor.connection.alias
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    ContentType = apps.get_model("contenttypes", "ContentType")
    User = apps.get_model(*settings.AUTH_USER_MODEL.split("."))

    admin_group, _ = Group.objects.using(db_alias).get_or_create(name=ADMIN_GROUP)
    hr_group, _ = Group.objects.using(db_alias).get_or_create(name=HR_GROUP)
    model_labels = (
        ("core", "employee", "employee"),
        ("core", "department", "department"),
        ("core", "attendance", "attendance"),
        ("core", "leaverequest", "leave request"),
    )
    permissions = {}
    for app_label, model_name, human_name in model_labels:
        content_type, _ = ContentType.objects.using(db_alias).get_or_create(
            app_label=app_label,
            model=model_name,
        )
        for action in ("add", "change", "delete", "view"):
            permission, _ = Permission.objects.using(db_alias).get_or_create(
                content_type=content_type,
                codename=f"{action}_{model_name}",
                defaults={"name": f"Can {action} {human_name}"},
            )
            permissions[f"{app_label}.{permission.codename}"] = permission

    auth_user_content_type, _ = ContentType.objects.using(db_alias).get_or_create(
        app_label="auth",
        model=User._meta.model_name,
    )
    view_user_permission, _ = Permission.objects.using(db_alias).get_or_create(
        content_type=auth_user_content_type,
        codename="view_user",
        defaults={"name": "Can view user"},
    )
    admin_group.permissions.add(*permissions.values(), view_user_permission)
    hr_group.permissions.add(*permissions.values())

    for user in User.objects.using(db_alias).filter(is_superuser=True).iterator():
        user.groups.add(admin_group)
    for user in User.objects.using(db_alias).filter(is_staff=True, is_superuser=False).iterator():
        user.groups.add(hr_group)


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0001_initial"),
        ("auth", "0012_alter_user_first_name_max_length"),
        ("contenttypes", "0002_remove_content_type_name"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RunPython(create_roles_and_migrate_staff, migrations.RunPython.noop),
    ]
