import time
from dataclasses import dataclass
from datetime import timedelta
from urllib.parse import urljoin

import requests
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import Check, Incident, Monitor
from .validators import UnsafeURL, validate_public_url

REDIRECT_CODES = (301, 302, 303, 307, 308)
USER_AGENT = "PingBoard/1.0 (uptime monitor)"
RETRY_AFTER_FAILURE = timedelta(minutes=1)
CLAIM_WINDOW = timedelta(minutes=2)


@dataclass
class Result:
    ok: bool
    status_code: int | None = None
    response_ms: int | None = None
    error: str = ""


def perform_request(url, expected_status):
    """Request the URL. Redirects are followed by hand so every hop is safety-checked."""
    started = time.monotonic()
    status_code = None
    error = ""
    try:
        current = url
        hops = 0
        while True:
            validate_public_url(current)
            resp = requests.get(
                current,
                timeout=(5, settings.CHECK_TIMEOUT_SECONDS),
                allow_redirects=False,
                stream=True,  
                headers={"User-Agent": USER_AGENT},
            )
            try:
                status_code = resp.status_code
                location = resp.headers.get("Location")
            finally:
                resp.close()
            if status_code == expected_status:
                break
            if status_code in REDIRECT_CODES and location and hops < settings.MAX_REDIRECTS:
                current = urljoin(current, location)
                hops += 1
                continue
            break
    except UnsafeURL as exc:
        error = str(exc)
    except requests.Timeout:
        error = f"Timed out after {settings.CHECK_TIMEOUT_SECONDS} seconds"
    except requests.exceptions.SSLError:
        error = "SSL certificate error"
    except requests.exceptions.TooManyRedirects:
        error = "Too many redirects"
    except requests.ConnectionError:
        error = "Could not connect to the server"
    except requests.RequestException as exc:
        error = f"Request failed: {type(exc).__name__}"

    elapsed_ms = int((time.monotonic() - started) * 1000)
    if error:
        return Result(ok=False, status_code=status_code, response_ms=None, error=error)
    ok = status_code == expected_status
    if not ok:
        error = f"Expected status {expected_status} but got {status_code}"
    return Result(ok=ok, status_code=status_code, response_ms=elapsed_ms, error=error)


def record_result(monitor_id, result, started=None):
    events = []
    with transaction.atomic():
        monitor = Monitor.objects.select_for_update().filter(pk=monitor_id).first()
        if monitor is None or not monitor.is_active:
            return events
        now = timezone.now()
        base = started or now
        Check.objects.create(
            monitor=monitor,
            checked_at=now,
            status_code=result.status_code,
            response_ms=result.response_ms,
            ok=result.ok,
            error=result.error,
        )
        monitor.last_checked_at = now
        interval = timedelta(minutes=monitor.interval_minutes)

        if result.ok:
            monitor.consecutive_failures = 0
            monitor.status = Monitor.UP
            monitor.next_check_at = base + interval
            incident = monitor.incidents.filter(resolved_at__isnull=True).first()
            if incident:
                incident.resolved_at = now
                incident.save(update_fields=["resolved_at"])
                events.append((incident.id, "recovered"))
        else:
            monitor.consecutive_failures += 1
            if monitor.consecutive_failures >= settings.FAILURES_BEFORE_DOWN:
                monitor.status = Monitor.DOWN
                monitor.next_check_at = base + interval
                incident, created = Incident.objects.get_or_create(
                    monitor=monitor,
                    resolved_at=None,
                    defaults={"started_at": now, "cause": result.error},
                )
                if created:
                    events.append((incident.id, "down"))
            else:
                monitor.next_check_at = now + RETRY_AFTER_FAILURE
        monitor.save(update_fields=["last_checked_at", "consecutive_failures", "status", "next_check_at"])
    return events


def process_monitor(monitor_id):
    monitor = Monitor.objects.filter(pk=monitor_id, is_active=True).first()
    if monitor is None:
        return []
    started = timezone.now()
    result = perform_request(monitor.url, monitor.expected_status)
    return record_result(monitor_id, result, started)

def claim_due_monitors(limit=500):
    now = timezone.now()
    with transaction.atomic():
        ids = list(
            Monitor.objects.select_for_update(skip_locked=True)
            .filter(is_active=True, next_check_at__lte=now + timedelta(seconds=10))
            .order_by("next_check_at")
            .values_list("id", flat=True)[:limit]
        )
        if ids:
            Monitor.objects.filter(id__in=ids).update(next_check_at=now + CLAIM_WINDOW)
    return ids