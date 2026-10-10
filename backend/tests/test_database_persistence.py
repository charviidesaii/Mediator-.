"""Database persistence and data isolation tests."""

import os
import tempfile
import pytest
from app.models.schemas import MemberResponseSubmit, ProjectCreate, TeamMemberCreate
from app.services.supabase import StorageService


@pytest.mark.asyncio
async def test_sqlite_persistence_survives_restart():
    """Verify that records saved to SQLite survive when a new StorageService instance connects."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    try:
        # Instance 1: Create project and responses
        service_1 = StorageService(backend="sqlite")
        service_1.db_path = db_path
        await service_1.initialize()

        proj = await service_1.create_project(
            ProjectCreate(title="Persistent Sprint", description="Testing restarts")
        )
        await service_1.add_team_member(proj.id, TeamMemberCreate(name="Elena", role="Backend"))
        await service_1.add_response(proj.id, "Elena", "Completing APIs by Wednesday")

        # Simulate Application Restart (dispose service_1, create service_2)
        del service_1

        service_2 = StorageService(backend="sqlite")
        service_2.db_path = db_path
        await service_2.initialize()

        # Verify project and data survived restart
        reloaded_proj = await service_2.get_project(proj.id)
        assert reloaded_proj is not None
        assert reloaded_proj.title == "Persistent Sprint"
        assert len(reloaded_proj.members) == 1
        assert reloaded_proj.members[0].name == "Elena"

        reloaded_responses = await service_2.get_responses(proj.id)
        assert len(reloaded_responses) == 1
        assert reloaded_responses[0].member_name == "Elena"
        assert reloaded_responses[0].raw_text == "Completing APIs by Wednesday"

    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


@pytest.mark.asyncio
async def test_duplicate_member_prevention():
    """Verify that adding duplicate member names to the same project is prevented."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    try:
        service = StorageService(backend="sqlite")
        service.db_path = db_path
        await service.initialize()

        proj = await service.create_project(ProjectCreate(title="Unique Members Project"))
        await service.add_team_member(proj.id, TeamMemberCreate(name="Jordan", role="QA"))

        # Second attempt with same name should raise ValueError
        with pytest.raises(ValueError, match="already exists"):
            await service.add_team_member(proj.id, TeamMemberCreate(name="Jordan", role="Lead QA"))
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


@pytest.mark.asyncio
async def test_cross_project_isolation():
    """Verify that project responses and data are strictly isolated between projects."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    try:
        service = StorageService(backend="sqlite")
        service.db_path = db_path
        await service.initialize()

        proj_a = await service.create_project(ProjectCreate(title="Project Alpha"))
        proj_b = await service.create_project(ProjectCreate(title="Project Beta"))

        await service.add_response(proj_a.id, "UserA", "Secret roadmap for Alpha")
        await service.add_response(proj_b.id, "UserB", "Roadmap for Beta")

        responses_a = await service.get_responses(proj_a.id)
        responses_b = await service.get_responses(proj_b.id)

        assert len(responses_a) == 1
        assert responses_a[0].member_name == "UserA"
        assert "Alpha" in responses_a[0].raw_text

        assert len(responses_b) == 1
        assert responses_b[0].member_name == "UserB"
        assert "Beta" in responses_b[0].raw_text
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)
