from uuid import UUID, uuid4

from .models import AuditLog


def record_audit_event(
    *,
    actor,
    action,
    instance,
    description,
    before=None,
    after=None,
    action_key: UUID | None = None,
):
    before = before or {}
    after = after or {}
    changes = {
        field_name: {
            "before": before.get(field_name),
            "after": after.get(field_name),
        }
        for field_name in before.keys() | after.keys()
        if before.get(field_name) != after.get(field_name)
    }
    return AuditLog.objects.create(
        action_key=action_key or uuid4(),
        actor=actor,
        acting_username=actor.get_username(),
        action=action,
        object_type=instance._meta.verbose_name.title(),
        object_id=str(instance.pk),
        affected_record=str(instance)[:255],
        description=description[:255],
        changes=changes,
    )
