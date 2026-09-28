"""Tests for health check endpoint."""


def test_health_check_returns_healthy(client):
    """Health endpoint should return healthy status."""
    response = client.get("/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "budget_me"
