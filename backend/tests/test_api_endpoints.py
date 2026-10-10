"""Integration tests for FastAPI REST API endpoints."""

import pytest


@pytest.mark.asyncio
async def test_end_to_end_api_lifecycle(async_client):
    """Integration test testing the complete REST API lifecycle from project creation to decision approval."""

    # 1. Create a Project
    project_payload = {
        "title": "Mobile App Launch 2026",
        "description": "Cross-functional team sprint",
    }
    create_res = await async_client.post("/api/projects", json=project_payload)
    assert create_res.status_code == 201
    project_data = create_res.json()
    project_id = project_data["id"]
    assert project_data["title"] == "Mobile App Launch 2026"

    # 2. Add Team Members
    members = [
        {"name": "Alex", "role": "Frontend Lead"},
        {"name": "Sam", "role": "Product Manager"},
        {"name": "Taylor", "role": "QA Engineer"},
    ]
    for m in members:
        mem_res = await async_client.post(f"/api/projects/{project_id}/members", json=m)
        assert mem_res.status_code == 201

    # 3. Submit Perspectives (Alex, Sam, Taylor)
    responses = [
        {"member_name": "Alex", "raw_text": "Our priority is completing the frontend by Friday."},
        {"member_name": "Sam", "raw_text": "I thought we agreed to launch the entire application on Thursday."},
        {"member_name": "Taylor", "raw_text": "I think we should complete testing before launching anything."},
    ]
    for r in responses:
        resp_res = await async_client.post(f"/api/projects/{project_id}/responses", json=r)
        assert resp_res.status_code == 201

    # 4. Verify Responses Listed
    list_res = await async_client.get(f"/api/projects/{project_id}/responses")
    assert list_res.status_code == 200
    assert len(list_res.json()) == 3

    # 5. Integration Test: Trigger Multi-Agent Analysis Endpoint
    analyze_res = await async_client.post(f"/api/projects/{project_id}/analyze")
    assert analyze_res.status_code == 200
    analysis_data = analyze_res.json()

    assert "workflow_id" in analysis_data
    assert analysis_data["project_id"] == project_id
    assert analysis_data["perspectives_output"]["total_members_analyzed"] == 3
    assert len(analysis_data["conflicts_output"]["conflicts"]) >= 1
    assert len(analysis_data["synthesis_output"]["proposed_resolutions"]) >= 1

    # Verify status is strictly PROPOSED
    for res in analysis_data["synthesis_output"]["proposed_resolutions"]:
        assert res["status"] == "PROPOSED"

    # 6. Retrieve Alignment Report
    report_res = await async_client.get(f"/api/projects/{project_id}/alignment")
    assert report_res.status_code == 200
    report_data = report_res.json()
    assert report_data["alignment_score"] > 0
    assert len(report_data["proposed_resolutions"]) >= 1

    # 7. Record a Human Decision (Approve a resolution)
    first_res = report_data["proposed_resolutions"][0]
    decision_payload = {
        "resolution_id": first_res["resolution_id"],
        "action": "APPROVE",
        "decision_text": "Team agreed to soft launch on Thursday with full release on Monday following QA.",
        "decided_by": "Sam (PM)",
        "notes": "Consensus reached in sync.",
    }
    dec_res = await async_client.post(f"/api/projects/{project_id}/decisions", json=decision_payload)
    assert dec_res.status_code == 201
    decision_data = dec_res.json()
    assert decision_data["status"] == "APPROVED"
    assert decision_data["decided_by"] == "Sam (PM)"

    # 8. Verify Decisions List
    dec_list_res = await async_client.get(f"/api/projects/{project_id}/decisions")
    assert dec_list_res.status_code == 200
    assert len(dec_list_res.json()) == 1
    assert dec_list_res.json()[0]["status"] == "APPROVED"


@pytest.mark.asyncio
async def test_health_check(async_client):
    """Test health check and root endpoints."""
    res = await async_client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "healthy"

    root_res = await async_client.get("/")
    assert root_res.status_code == 200
    assert root_res.json()["docs_url"] == "/docs"
