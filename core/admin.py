from django.contrib import admin
from .models import Check, HourlyRollup, Incident, Monitor, StatusPage

for model in (Monitor, Check, Incident, HourlyRollup, StatusPage):
    admin.site.register(model)