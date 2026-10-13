from django.db import migrations


def grant_audit_log_view_to_admin(apps, schema_editor):
    db_alias = schema_editor.connection.alias
    ContentType = apps.get_model("contenttypes", "ContentType")
    Permission = apps.get_model("auth", "Permission")
    Group = apps.get_model("auth", "Group")

    content_type, _ = ContentType.objects.using(db_alias).get_or_create(
        app_label="core",
        model="auditlog",
    )
    permission, _ = Permission.objects.using(db_alias).get_or_create(
        content_type=content_type,
        codename="view_auditlog",
        defaults={"name": "Can view audit log"},
    )
    Group.objects.using(db_alias).get(name="Admin").permissions.add(permission)


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0011_auditlog"),
        ("auth", "0012_alter_user_first_name_max_length"),
        ("contenttypes", "0002_remove_content_type_name"),
    ]

    operations = [
        migrations.RunPython(
            grant_audit_log_view_to_admin,
            migrations.RunPython.noop,
        ),
    ]
