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
