from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.conf import settings

class Monitor(models.Model):
    UNKNOWN, UP, DOWN = "unknown", "up", "down"
    STATUS_CHOICES = [
        (UNKNOWN, "Unknown"),
        (UP, "Up"),
        (DOWN, "Down")
    ]

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="monitors")
    name = models.CharField(max_length=100)
    url = models.URLField(max_length=500)
    interval_minutes = models.PositiveSmallIntegerField(default=5)
    expected_status = models.PositiveSmallIntegerField(default=200)
    alerts_enabled = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=UNKNOWN)
    consecutive_failures = models.PositiveSmallIntegerField(default=0)
    last_checked_at = models.DateTimeField(null=True, blank=True)
    next_check_at = models.DateTimeField(default=timezone.now, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name", "id"]
        constraints = [
            models.UniqueConstraint(fields=["owner", "url"], name="unique_url_per_owner"),
        ]

    def __str__(self):
        return f"{self.name} ({self.url})"

class Check(models.Model):
    monitor = models.ForeignKey(Monitor, on_delete=models.CASCADE, related_name="checks")
    checked_at = models.DateTimeField(default=timezone.now)
    status_code = models.PositiveSmallIntegerField(null=True, blank=True)
    response_ms = models.PositiveIntegerField(null=True, blank=True)
    ok = models.BooleanField()
    error = models.CharField(max_length=300, blank=True) 

    class Meta:
        ordering = ["-checked_at"]
        indexes = [models.Index(fields=["monitor", "-checked_at"], name="check_monitor_time_idx")]

class Incident(models.Model):
    monitor = models.ForeignKey(Monitor, on_delete=models.CASCADE, related_name="incidents")
    started_at = models.DateTimeField()
    resolved_at = models.DateTimeField(null=True, blank=True)
    cause = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["-started_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["monitor"],
                condition=Q(resolved_at__isnull=True),
                name="one_open_incident_per_monitor",
            ),
        ]

    @property
    def duration_seconds(self):
        end = self.resolved_at or timezone.now()
        return int((end - self.started_at).total_seconds())


class HourlyRollup(models.Model):
    monitor = models.ForeignKey(Monitor, on_delete=models.CASCADE, related_name="rollups")
    hour = models.DateTimeField()
    checks = models.PositiveIntegerField()
    failures = models.PositiveIntegerField()
    timed = models.PositiveIntegerField()
    avg_ms = models.FloatField(null=True, blank=True)
    max_ms = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        ordering = ["hour"]
        constraints = [
            models.UniqueConstraint(fields=["monitor", "hour"], name="unique_rollup_per_hour"),
        ]


class StatusPage(models.Model):
    owner = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="status_page")
    slug = models.SlugField(max_length=50, unique=True)
    title = models.CharField(max_length=100)
    monitors = models.ManyToManyField(Monitor, blank=True, related_name="status_pages")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.slug