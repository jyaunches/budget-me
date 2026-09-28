"""Tests for Link server module."""

from fastapi.testclient import TestClient


class TestLinkServer:
    """Tests for the Link server endpoints."""

    def test_link_server_serves_html(self, monkeypatch, mocker):
        """GET / returns HTML response with Plaid Link script."""
        monkeypatch.setenv("DATABASE_URL_DEV", "postgresql+asyncpg://localhost/db")
        monkeypatch.setenv("DATABASE_URL_PROD", "postgresql+asyncpg://localhost/db")
        monkeypatch.setenv("APP_TOKEN_ENC_KEY", "test-key")
        monkeypatch.setenv("PLAID_CLIENT_ID", "test-client-id")
        monkeypatch.setenv("PLAID_SECRET", "test-secret")
        monkeypatch.setenv("PLAID_ENV", "sandbox")

        from budget_me.config import get_settings
        from budget_me.server.link_server import app

        get_settings.cache_clear()

        client = TestClient(app)
        response = client.get("/")

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "plaid" in response.text.lower()
        assert "link" in response.text.lower()

    def test_link_server_creates_token(self, monkeypatch, mocker):
        """POST /api/link-token returns JSON with link_token."""
        monkeypatch.setenv("DATABASE_URL_DEV", "postgresql+asyncpg://localhost/db")
        monkeypatch.setenv("DATABASE_URL_PROD", "postgresql+asyncpg://localhost/db")
        monkeypatch.setenv("APP_TOKEN_ENC_KEY", "test-key")
        monkeypatch.setenv("PLAID_CLIENT_ID", "test-client-id")
        monkeypatch.setenv("PLAID_SECRET", "test-secret")
        monkeypatch.setenv("PLAID_ENV", "sandbox")

        from budget_me.config import get_settings
        from budget_me.server.link_server import app

        get_settings.cache_clear()

        # Mock create_link_token function
        mocker.patch(
            "budget_me.server.link_server.create_link_token",
            return_value="link-sandbox-test-token",
        )

        client = TestClient(app)
        response = client.post("/api/link-token")

        assert response.status_code == 200
        assert "link_token" in response.json()
        assert response.json()["link_token"] == "link-sandbox-test-token"

    def test_link_server_exchanges_token(self, monkeypatch, mocker):
        """POST /api/exchange with public_token returns success with item_id."""
        monkeypatch.setenv("DATABASE_URL_DEV", "postgresql+asyncpg://localhost/db")
        monkeypatch.setenv("DATABASE_URL_PROD", "postgresql+asyncpg://localhost/db")
        monkeypatch.setenv("APP_TOKEN_ENC_KEY", "test-key")
        monkeypatch.setenv("PLAID_CLIENT_ID", "test-client-id")
        monkeypatch.setenv("PLAID_SECRET", "test-secret")
        monkeypatch.setenv("PLAID_ENV", "sandbox")

        from budget_me.config import get_settings
        from budget_me.server.link_server import app

        get_settings.cache_clear()

        # Mock exchange_public_token function
        test_item_id = "test-item-id-123"
        mocker.patch(
            "budget_me.server.link_server.exchange_public_token",
            return_value={"access_token": "access-test", "item_id": test_item_id},
        )

        client = TestClient(app)
        response = client.post(
            "/api/exchange", json={"public_token": "public-sandbox-test-token"}
        )

        assert response.status_code == 200
        assert response.json()["success"] is True
        assert response.json()["item_id"] == test_item_id

    def test_link_server_handles_exchange_error(self, monkeypatch, mocker):
        """POST /api/exchange with invalid token returns error details with 400 status."""
        monkeypatch.setenv("DATABASE_URL_DEV", "postgresql+asyncpg://localhost/db")
        monkeypatch.setenv("DATABASE_URL_PROD", "postgresql+asyncpg://localhost/db")
        monkeypatch.setenv("APP_TOKEN_ENC_KEY", "test-key")
        monkeypatch.setenv("PLAID_CLIENT_ID", "test-client-id")
        monkeypatch.setenv("PLAID_SECRET", "test-secret")
        monkeypatch.setenv("PLAID_ENV", "sandbox")

        from budget_me.config import get_settings
        from budget_me.server.link_server import app

        get_settings.cache_clear()

        # Mock exchange_public_token to raise an error
        mocker.patch(
            "budget_me.server.link_server.exchange_public_token",
            side_effect=Exception("Invalid public token"),
        )

        client = TestClient(app)
        response = client.post("/api/exchange", json={"public_token": "invalid-token"})

        assert response.status_code == 400
        json_response = response.json()
        assert "detail" in json_response
        assert "error" in json_response["detail"]
