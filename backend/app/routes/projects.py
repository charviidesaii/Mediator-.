"""Project routes."""

from fastapi import APIRouter, HTTPException, status
from typing import List

from app.models.schemas import Project, ProjectCreate, TeamMember, TeamMemberCreate
from app.services.supabase import storage_service

router = APIRouter(prefix="/projects", tags=["Projects"])


@router.post("", response_model=Project, status_code=status.HTTP_201_CREATED)
async def create_project(project_in: ProjectCreate):
    """Create a new project workspace for team alignment."""
    project = await storage_service.create_project(project_in)
    return project


@router.get("", response_model=List[Project])
async def list_projects():
    """List all projects."""
    return await storage_service.list_projects()


@router.get("/{project_id}", response_model=Project)
async def get_project(project_id: str):
    """Retrieve details for a specific project by ID."""
    project = await storage_service.get_project(project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project with ID '{project_id}' not found.",
        )
    return project


@router.post("/{project_id}/members", response_model=TeamMember, status_code=status.HTTP_201_CREATED)
async def add_team_member(project_id: str, member_in: TeamMemberCreate):
    """Add a new team member to an existing project."""
    member = await storage_service.add_team_member(project_id, member_in)
    if not member:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project with ID '{project_id}' not found.",
        )
    return member
