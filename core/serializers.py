from django.conf import settings
from .models import Monitor, Check, Incident, StatusPage
from .validators import UnsafeURL, validate_public_url
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

User = get_user_model()


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ["id", "username", "email", "password"]
        extra_kwargs = {"email": {"required": True}}

    def validate_email(self, value):
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("An account with this email already exists.")
        return value

    def validate_password(self, value):
        validate_password(value)
        return value

    def create(self, validated_data):
        return User.objects.create_user(**validated_data)


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "username", "email"]



class MonitorSerializer(serializers.ModelSerializer):
    interval_minutes = serializers.ChoiceField(choices=settings.ALLOWED_INTERVALS, default=5)

    class Meta:
        model = Monitor
        fields = [
            "id", "name", "url", "interval_minutes", "expected_status",
            "alerts_enabled", "is_active", "status", "last_checked_at", "created_at",
        ]
        read_only_fields = ["status", "last_checked_at", "created_at"]
        extra_kwargs = {"expected_status": {"min_value": 100, "max_value": 599}}

    def validate_url(self, value):
        try:
            validate_public_url(value)
        except UnsafeURL as exc:
            raise serializers.ValidationError(str(exc))
        return value

class CheckSerializer(serializers.ModelSerializer):
    class Meta:
        model = Check
        fields = ["id", "checked_at", "status_code", "response_ms", "ok", "error"]


class IncidentSerializer(serializers.ModelSerializer):
    duration_seconds = serializers.ReadOnlyField()

    class Meta:
        model = Incident
        fields = ["id", "started_at", "resolved_at", "cause", "duration_seconds"]

class StatusPageSerializer(serializers.ModelSerializer):
    monitors = serializers.PrimaryKeyRelatedField(
        many=True, required=False, queryset=Monitor.objects.none()
    )

    class Meta:
        model = StatusPage
        fields = ["slug", "title", "monitors"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            self.fields["monitors"].child_relation.queryset = Monitor.objects.filter(
                owner=request.user
            )