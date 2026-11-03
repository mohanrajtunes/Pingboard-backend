from django.conf import settings
from django.core.mail import send_mail
from .models import Incident
from celery import shared_task
from .checker import claim_due_monitors, process_monitor

@shared_task
def dispatch_due_checks():
    """Runs every minute. Finds due monitors and queues one job for each."""
    ids = claim_due_monitors()
    for monitor_id in ids:
        run_monitor_check.delay(monitor_id)
    return len(ids)


@shared_task
def run_monitor_check(monitor_id):
    events = process_monitor(monitor_id)
    for incident_id, kind in events:
        send_alert_email.delay(incident_id, kind)

@shared_task
def send_alert_email(incident_id, kind):
    incident = Incident.objects.select_related("monitor__owner").filter(pk=incident_id).first()
    if incident is None:
        return
    monitor = incident.monitor
    to = monitor.owner.email
    if not to:
        return
    if kind == "down":
        subject = f"[DOWN] {monitor.name} is not responding"
        body = f"{monitor.name} ({monitor.url}) failed {settings.FAILURES_BEFORE_DOWN} checks in a row."
    else:
        subject = f"[UP] {monitor.name} is back online"
        body = f"{monitor.name} ({monitor.url}) has recovered."
    body += f"\n\nOpen dashboard: {settings.FRONTEND_URL}/monitors/{monitor.id}"
    send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [to])