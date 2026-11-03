import pytest
from django.core.cache import cache
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from core.models import Monitor

User = get_user_model()


@pytest.fixture(autouse=True)
def clear_throttle_cache():
    cache.clear()


@pytest.fixture
def user(db):
    return User.objects.create_user(username="alice", email="alice@test.com", password="Pass12345!")


@pytest.fixture
def client(user):
    c = APIClient()
    c.force_authenticate(user=user)
    return c


def test_health():
    res = APIClient().get("/api/health/")
    assert res.status_code == 200


def test_monitors_require_login(db):
    res = APIClient().get("/api/monitors/")
    assert res.status_code == 401


def test_create_monitor(client):
    res = client.post("/api/monitors/", {"name": "Site", "url": "https://example.com"}, format="json")
    assert res.status_code == 201
    assert res.data["name"] == "Site"


def test_duplicate_url_rejected(client):
    body = {"name": "Site", "url": "https://example.com"}
    client.post("/api/monitors/", body, format="json")
    res = client.post("/api/monitors/", body, format="json")
    assert res.status_code == 400


def test_private_url_blocked(client):
    res = client.post("/api/monitors/", {"name": "Local", "url": "http://127.0.0.1:8000"}, format="json")
    assert res.status_code == 400


def test_user_cannot_see_other_users_monitor(client, db):
    bob = User.objects.create_user(username="bob", email="bob@test.com", password="Pass12345!")
    other = Monitor.objects.create(owner=bob, name="Secret", url="https://example.org")
    res = client.get(f"/api/monitors/{other.id}/")
    assert res.status_code == 404