"""Pytest fixtures for testing agents, workflows, and API endpoints."""

from datetime import datetime, timezone
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.models.schemas import MemberResponse
from app.workflows.alignment import AlignmentWorkflow


@pytest.fixture
def sample_responses() -> list[MemberResponse]:
    """Sample teammate responses from the core test scenario."""
    now = datetime.now(timezone.utc)
    return [
        MemberResponse(
            id="resp-1",
            project_id="test-proj-1",
            member_name="Alex",
            raw_text="Our priority is completing the frontend by Friday.",
            source="slack",
            submitted_at=now,
        ),
        MemberResponse(
            id="resp-2",
            project_id="test-proj-1",
            member_name="Sam",
            raw_text="I thought we agreed to launch the entire application on Thursday.",
            source="slack",
            submitted_at=now,
        ),
        MemberResponse(
            id="resp-3",
            project_id="test-proj-1",
            member_name="Taylor",
            raw_text="I think we should complete testing before launching anything.",
            source="slack",
            submitted_at=now,
        ),
    ]


@pytest.fixture
def workflow() -> AlignmentWorkflow:
    """Fixture providing the multi-agent alignment workflow."""
    return AlignmentWorkflow()


@pytest_asyncio.fixture(loop_scope="function")
async def async_client():
    """Async HTTP client for testing FastAPI REST endpoints."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client
