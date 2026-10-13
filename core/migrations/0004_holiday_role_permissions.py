from django.db import migrations


def add_holiday_permissions_to_roles(apps, schema_editor):
    db_alias = schema_editor.connection.alias
    ContentType = apps.get_model("contenttypes", "ContentType")
    Permission = apps.get_model("auth", "Permission")
    Group = apps.get_model("auth", "Group")
    Holiday = apps.get_model("core", "Holiday")

    content_type, _ = ContentType.objects.using(db_alias).get_or_create(
        app_label="core",
        model="holiday",
    )
    permissions = []
    for action, verb in (
        ("add", "add"),
        ("change", "change"),
        ("delete", "delete"),
        ("view", "view"),
    ):
        permission, _ = Permission.objects.using(db_alias).get_or_create(
            content_type=content_type,
            codename=f"{action}_holiday",
            defaults={"name": f"Can {verb} holiday"},
        )
        permissions.append(permission)

    admin_group = Group.objects.using(db_alias).get(name="Admin")
    hr_group = Group.objects.using(db_alias).get(name="HR")
    admin_group.permissions.add(*permissions)
    hr_group.permissions.add(*permissions)


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0003_holiday"),
        ("auth", "0012_alter_user_first_name_max_length"),
        ("contenttypes", "0002_remove_content_type_name"),
    ]

    operations = [
        migrations.RunPython(add_holiday_permissions_to_roles, migrations.RunPython.noop),
    ]
