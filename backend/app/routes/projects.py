"""Project routes."""

from fastapi import APIRouter, HTTPException, status
from typing import List

from app.models.schemas import APIErrorResponse, Project, ProjectCreate, TeamMember, TeamMemberCreate
from app.services.supabase import storage_service

router = APIRouter(prefix="/projects", tags=["Projects"])


@router.post(
    "",
    response_model=Project,
    status_code=status.HTTP_201_CREATED,
    responses={400: {"model": APIErrorResponse}},
)
async def create_project(project_in: ProjectCreate):
    """Create a new project workspace for team alignment."""
    try:
        project = await storage_service.create_project(project_in)
        return project
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get("", response_model=List[Project])
async def list_projects():
    """List all projects."""
    return await storage_service.list_projects()


@router.get(
    "/{project_id}",
    response_model=Project,
    responses={404: {"model": APIErrorResponse}},
)
async def get_project(project_id: str):
    """Retrieve details for a specific project by ID."""
    project = await storage_service.get_project(project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project with ID '{project_id}' not found.",
        )
    return project


@router.post(
    "/{project_id}/members",
    response_model=TeamMember,
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {"model": APIErrorResponse},
        404: {"model": APIErrorResponse},
        409: {"model": APIErrorResponse},
    },
)
async def add_team_member(project_id: str, member_in: TeamMemberCreate):
    """Add a new team member to an existing project."""
    project = await storage_service.get_project(project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project with ID '{project_id}' not found.",
        )
    try:
        member = await storage_service.add_team_member(project_id, member_in)
        return member
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )
