from django.db import migrations


def add_payroll_permissions_to_roles(apps, schema_editor):
    db_alias = schema_editor.connection.alias
    ContentType = apps.get_model("contenttypes", "ContentType")
    Permission = apps.get_model("auth", "Permission")
    Group = apps.get_model("auth", "Group")

    content_type, _ = ContentType.objects.using(db_alias).get_or_create(
        app_label="core",
        model="payrollrecord",
    )
    permissions = []
    for action in ("add", "change", "delete", "view"):
        permission, _ = Permission.objects.using(db_alias).get_or_create(
            content_type=content_type,
            codename=f"{action}_payrollrecord",
            defaults={"name": f"Can {action} payroll record"},
        )
        permissions.append(permission)

    for group_name in ("Admin", "HR"):
        group = Group.objects.using(db_alias).get(name=group_name)
        group.permissions.add(*permissions)


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0007_payrollrecord_payroll_deductions_within_gross_and_more"),
        ("auth", "0012_alter_user_first_name_max_length"),
        ("contenttypes", "0002_remove_content_type_name"),
    ]

    operations = [
        migrations.RunPython(add_payroll_permissions_to_roles, migrations.RunPython.noop),
    ]
