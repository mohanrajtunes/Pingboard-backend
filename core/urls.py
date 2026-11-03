from rest_framework.routers import DefaultRouter
from django.urls import path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from . import views
from .views import health, RegisterView, MeView, MonitorViewSet, StatusPageView, PublicStatusView, LoginView
router = DefaultRouter()
router.register("monitors", views.MonitorViewSet, basename="monitor")

urlpatterns = [
    path("health/", views.health),
    path("internal/tick/", views.TickView.as_view()),
    path("auth/register/", views.RegisterView.as_view()),
    path("auth/token/", views.LoginView.as_view()),
    path("auth/token/refresh/", TokenRefreshView.as_view()),
    path("auth/me/", views.MeView.as_view()),
    path("status-page/", StatusPageView.as_view()),
    path("public/status/<slug:slug>/", PublicStatusView.as_view()),

] + router.urls