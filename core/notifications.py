from datetime import timedelta

from django.utils import timezone

from .models import Holiday, LeaveRequest, Notification

UPCOMING_HOLIDAY_DAYS = 30


def sync_user_notifications(user):
    today = timezone.localdate()

    if user.has_perm("core.view_leaverequest"):
        pending_requests = LeaveRequest.objects.filter(status="PENDING").select_related(
            "employee"
        )
        active_leave_keys = set()
        for leave in pending_requests:
            event_key = f"leave:{leave.pk}"
            active_leave_keys.add(event_key)
            Notification.objects.get_or_create(
                user=user,
                event_key=event_key,
                defaults={
                    "kind": "LEAVE",
                    "title": "Pending leave request",
                    "message": (
                        f"{leave.employee.full_name} requested leave from "
                        f"{leave.start_date:%d %b %Y} to {leave.end_date:%d %b %Y}."
                    ),
                },
            )
        stale_leave_notifications = Notification.objects.filter(
            user=user,
            kind="LEAVE",
        )
        if active_leave_keys:
            stale_leave_notifications = stale_leave_notifications.exclude(
                event_key__in=active_leave_keys
            )
        stale_leave_notifications.delete()
    else:
        Notification.objects.filter(user=user, kind="LEAVE").delete()

    upcoming_holidays = Holiday.objects.filter(
        date__gte=today,
        date__lte=today + timedelta(days=UPCOMING_HOLIDAY_DAYS),
    )
    for holiday in upcoming_holidays:
        event_key = f"holiday:{holiday.pk}"
        Notification.objects.get_or_create(
            user=user,
            event_key=event_key,
            defaults={
                "kind": "HOLIDAY",
                "title": f"Upcoming holiday: {holiday.name}",
                "message": (
                    f"{holiday.name} is on {holiday.date:%A, %d %b %Y}."
                    + (f" {holiday.description}" if holiday.description else "")
                ),
            },
        )

    return Notification.objects.filter(user=user)


def notification_summary(request):
    if not request.user.is_authenticated:
        return {"unread_notification_count": 0}
    notifications = sync_user_notifications(request.user)
    return {
        "unread_notification_count": notifications.filter(is_read=False).count()
    }
