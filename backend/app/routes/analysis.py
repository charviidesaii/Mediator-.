"""Multi-agent analysis routes."""

from fastapi import APIRouter, HTTPException, status

from app.models.schemas import APIErrorResponse, AlignmentWorkflowResult, SynthesisReport
from app.services.analysis import analysis_service

router = APIRouter(prefix="/projects", tags=["Analysis"])


@router.post(
    "/{project_id}/analyze",
    response_model=AlignmentWorkflowResult,
    status_code=status.HTTP_200_OK,
    responses={
        400: {"model": APIErrorResponse},
        404: {"model": APIErrorResponse},
        500: {"model": APIErrorResponse},
    },
)
async def trigger_analysis(project_id: str):
    """Trigger the multi-agent alignment workflow (Perspective -> Conflict -> Resolution).

    Coordinates:
    - Agent 1: Extracts structured goals, priorities, responsibilities, and deadlines.
    - Agent 2: Identifies contradictory dates, priority mismatches, and information gaps.
    - Agent 3: Proposes actionable compromises, leaving decisions strictly for human approval.
    """
    try:
        result = await analysis_service.trigger_analysis(project_id)
        return result
    except ValueError as e:
        err_msg = str(e)
        if "not found" in err_msg.lower():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=err_msg,
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=err_msg,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Analysis failed: {str(e)}",
        )


@router.get(
    "/{project_id}/alignment",
    response_model=SynthesisReport,
    status_code=status.HTTP_200_OK,
    responses={404: {"model": APIErrorResponse}},
)
async def get_alignment_report(project_id: str):
    """Retrieve the latest alignment synthesis report for a project."""
    try:
        report = await analysis_service.get_latest_report(project_id)
        if not report:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No alignment report found for project '{project_id}'. Trigger /analyze first.",
            )
        return report
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
