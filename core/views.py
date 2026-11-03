from datetime import timedelta
from django.db.models import Avg, Count, Q
from django.db.models.functions import TruncDay, TruncHour
from django.utils import timezone
from rest_framework import serializers, viewsets
from django.conf import settings
from .models import Monitor, Check, StatusPage
from .serializers import MonitorSerializer, StatusPageSerializer
from rest_framework.decorators import action
from rest_framework.response import Response
from .checker import process_monitor
from .serializers import CheckSerializer, IncidentSerializer
from rest_framework import generics
from .serializers import RegisterSerializer, UserSerializer
from django.shortcuts import render, get_object_or_404
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView
from rest_framework.throttling import ScopedRateThrottle
from rest_framework_simplejwt.views import TokenObtainPairView

@api_view(["GET"])
@permission_classes({AllowAny})
def health(request):
    return Response({"status": "ok"})


class RegisterView(generics.CreateAPIView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"
    serializer_class = RegisterSerializer
    permission_classes = [AllowAny]


class MeView(generics.RetrieveAPIView):
    serializer_class = UserSerializer

    def get_object(self):
        return self.request.user
STAT_RANGES = {
    "24h": (timedelta(hours=24), TruncHour),
    "7d": (timedelta(days=7), TruncDay),
    "30d": (timedelta(days=30), TruncDay),
}

class MonitorViewSet(viewsets.ModelViewSet):
    serializer_class = MonitorSerializer

    def get_queryset(self):
        return Monitor.objects.filter(owner=self.request.user)

    def perform_create(self, serializer):
        user = self.request.user
        if Monitor.objects.filter(owner=user).count() >= settings.MAX_MONITORS_PER_USER:
            raise serializers.ValidationError(
                f"You can have up to {settings.MAX_MONITORS_PER_USER} monitors."
            )
        if Monitor.objects.filter(owner=user, url=serializer.validated_data["url"]).exists():
            raise serializers.ValidationError({"url": ["You are already monitoring this URL."]})
        serializer.save(owner=user)

    @action(detail=True, methods=["post"], url_path="check-now")
    def check_now(self, request, pk=None):
        monitor = self.get_object()
        process_monitor(monitor.id)
        monitor.refresh_from_db()
        return Response(MonitorSerializer(monitor).data)

    @action(detail=True, methods=["get"])
    def checks(self, request, pk=None):
        monitor = self.get_object()
        return Response(CheckSerializer(monitor.checks.all()[:50], many=True).data)
    
    @action(detail=True, methods=["get"])
    def stats(self, request, pk=None):
        monitor = self.get_object()
        key = request.query_params.get("range", "24h")
        if key not in STAT_RANGES:
            return Response({"range": ["Use 24h, 7d or 30d."]}, status=400)
        delta, trunc = STAT_RANGES[key]
        qs = Check.objects.filter(monitor=monitor, checked_at__gte=timezone.now() - delta)

        totals = qs.aggregate(
            total=Count("id"),
            up=Count("id", filter=Q(ok=True)),
            avg=Avg("response_ms"),
        )
        rows = (
            qs.annotate(t=trunc("checked_at"))
            .values("t")
            .annotate(total=Count("id"), up=Count("id", filter=Q(ok=True)), avg=Avg("response_ms"))
            .order_by("t")
        )
        total = totals["total"]
        return Response({
            "range": key,
            "checks": total,
            "uptime_percent": round(totals["up"] * 100 / total, 2) if total else None,
            "avg_response_ms": round(totals["avg"]) if totals["avg"] else None,
            "buckets": [
                {
                    "time": r["t"],
                    "uptime_percent": round(r["up"] * 100 / r["total"], 2),
                    "avg_response_ms": round(r["avg"]) if r["avg"] else None,
                }
                for r in rows
            ],
        })

    @action(detail=True, methods=["get"])
    def incidents(self, request, pk=None):
        monitor = self.get_object()
        return Response(IncidentSerializer(monitor.incidents.all()[:50], many=True).data)

class StatusPageView(APIView):
    def get(self, request):
        page = StatusPage.objects.filter(owner=request.user).first()
        if page is None:
            return Response({"detail": "No status page yet."}, status=404)
        return Response(StatusPageSerializer(page, context={"request": request}).data)

    def put(self, request):
        page = StatusPage.objects.filter(owner=request.user).first()
        ser = StatusPageSerializer(
            page, data=request.data, context={"request": request}, partial=page is not None
        )
        ser.is_valid(raise_exception=True)
        ser.save(owner=request.user)
        return Response(ser.data)


class PublicStatusView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request, slug):
        page = get_object_or_404(StatusPage, slug=slug)
        since = timezone.now() - timedelta(hours=24)
        items = []
        for m in page.monitors.filter(is_active=True):
            t = Check.objects.filter(monitor=m, checked_at__gte=since).aggregate(
                total=Count("id"), up=Count("id", filter=Q(ok=True))
            )
            items.append({
                "name": m.name,
                "status": m.status,
                "uptime_24h": round(t["up"] * 100 / t["total"], 2) if t["total"] else None,
            })
        statuses = [i["status"] for i in items]
        if "down" in statuses:
            overall = "outage"
        elif items and all(s == "up" for s in statuses):
            overall = "operational"
        else:
            overall = "unknown"
        return Response({"title": page.title, "overall": overall, "monitors": items})

    
class LoginView(TokenObtainPairView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"