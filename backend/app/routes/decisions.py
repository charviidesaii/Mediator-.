"""Human decisions and approval routes."""

from fastapi import APIRouter, BackgroundTasks, HTTPException, status
from typing import List

from app.models.schemas import APIErrorResponse, ConfirmedDecision, DecisionActionRequest
from app.services.n8n import trigger_n8n_decision_webhook
from app.services.supabase import storage_service

router = APIRouter(prefix="/projects", tags=["Decisions"])


@router.post(
    "/{project_id}/decisions",
    response_model=ConfirmedDecision,
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {"model": APIErrorResponse},
        404: {"model": APIErrorResponse},
    },
)
async def record_decision(
    project_id: str,
    action: DecisionActionRequest,
    background_tasks: BackgroundTasks,
):
    """Approve, reject, or modify an AI-proposed resolution into an official project commitment.

    Only human-approved actions transition an AI proposal into an official project commitment.
    Validates that the resolution_id exists in the project's latest analysis report.
    Dispatches outbound webhook to n8n upon successful human APPROVE or MODIFY.
    """
    project = await storage_service.get_project(project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project with ID '{project_id}' not found.",
        )

    try:
        confirmed = await storage_service.record_decision(project_id, action)
        if action.action in ["APPROVE", "MODIFY"]:
            background_tasks.add_task(
                trigger_n8n_decision_webhook,
                project_id=project_id,
                action=action,
                confirmed=confirmed,
            )
        return confirmed
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get(
    "/{project_id}/decisions",
    response_model=List[ConfirmedDecision],
    responses={404: {"model": APIErrorResponse}},
)
async def list_decisions(project_id: str):
    """Retrieve all confirmed human decisions and project commitments."""
    project = await storage_service.get_project(project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project with ID '{project_id}' not found.",
        )

    return await storage_service.get_decisions(project_id)
