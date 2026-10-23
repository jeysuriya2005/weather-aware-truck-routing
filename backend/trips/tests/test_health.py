from rest_framework.test import APIClient


def test_health_endpoint():
    response = APIClient().get("/api/health/")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "weather-aware-truck-routing"}


def test_health_rejects_non_get():
    assert APIClient().post("/api/health/", {}, format="json").status_code == 405
