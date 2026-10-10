"""Team perspective response routes."""

from fastapi import APIRouter, HTTPException, status
from typing import List

from app.models.schemas import MemberResponse, MemberResponseSubmit
from app.services.supabase import storage_service

router = APIRouter(prefix="/projects", tags=["Responses"])


@router.post(
    "/{project_id}/responses",
    response_model=MemberResponse,
    status_code=status.HTTP_201_CREATED,
)
async def submit_response(project_id: str, response_in: MemberResponseSubmit):
    """Submit an individual teammate's perspectives, priorities, or expectations."""
    project = await storage_service.get_project(project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project with ID '{project_id}' not found.",
        )

    response = await storage_service.add_response(
        project_id=project_id,
        member_name=response_in.member_name,
        raw_text=response_in.raw_text,
        source=response_in.source,
    )
    return response


@router.get(
    "/{project_id}/responses",
    response_model=List[MemberResponse],
)
async def list_responses(project_id: str):
    """Retrieve all submitted responses for a project."""
    project = await storage_service.get_project(project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project with ID '{project_id}' not found.",
        )
    return await storage_service.get_responses(project_id)
