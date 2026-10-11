"""Security, input validation, and test harness endpoint tests."""

import pytest


@pytest.mark.asyncio
async def test_input_validation_empty_project_title(async_client):
    """Verify that empty or whitespace-only project titles are rejected with 422."""
    res = await async_client.post("/api/projects", json={"title": "   ", "description": "Blank title"})
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_input_validation_empty_member_name(async_client):
    """Verify that empty member name is rejected with 422."""
    proj_res = await async_client.post("/api/projects", json={"title": "Valid Project"})
    proj_id = proj_res.json()["id"]

    res = await async_client.post(f"/api/projects/{proj_id}/members", json={"name": "  "})
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_input_validation_empty_response_text(async_client):
    """Verify that submitting empty response text is rejected with 422."""
    proj_res = await async_client.post("/api/projects", json={"title": "Valid Project 2"})
    proj_id = proj_res.json()["id"]

    res = await async_client.post(
        f"/api/projects/{proj_id}/responses",
        json={"member_name": "Jordan", "raw_text": "   "},
    )
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_dummy_frontend_endpoint(async_client):
    """Verify that the dummy frontend test harness is accessible at /test-ui."""
    res = await async_client.get("/test-ui")
    assert res.status_code == 200
    assert "text/html" in res.headers.get("content-type", "")
    assert "Mediator — Backend Test Console" in res.text
    assert "Create Project" in res.text


@pytest.mark.asyncio
async def test_api_key_authentication_enforcement(async_client):
    """Verify that when AUTH_ENABLED is True, protected API endpoints require valid API key."""
    from unittest.mock import patch
    from app.config import settings

    with patch.object(settings, "auth_enabled", True), \
         patch.object(settings, "api_secret_key", "secret-test-key-456"):

        # 1. Unauthenticated request to /api/projects is rejected with 401
        res_no_auth = await async_client.get("/api/projects")
        assert res_no_auth.status_code == 401
        assert "Unauthorized" in res_no_auth.json().get("detail", "")

        # 2. Request with invalid key is rejected with 401
        res_bad_key = await async_client.get("/api/projects", headers={"X-API-Key": "wrong-key"})
        assert res_bad_key.status_code == 401

        # 3. Request with valid X-API-Key header succeeds
        res_good_header = await async_client.get("/api/projects", headers={"X-API-Key": "secret-test-key-456"})
        assert res_good_header.status_code == 200

        # 4. Request with valid Bearer token succeeds
        res_good_bearer = await async_client.get(
            "/api/projects", headers={"Authorization": "Bearer secret-test-key-456"}
        )
        assert res_good_bearer.status_code == 200

        # 5. Non-API endpoints (/health, /test-ui) remain publicly accessible
        health_res = await async_client.get("/health")
        assert health_res.status_code == 200

