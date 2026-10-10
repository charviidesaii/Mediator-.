"""Analysis service orchestrating the multi-agent workflow execution and storage."""

import logging
from typing import Optional

from app.models.schemas import AlignmentWorkflowResult, SynthesisReport
from app.services.supabase import storage_service
from app.workflows.alignment import AlignmentWorkflow

logger = logging.getLogger(__name__)


class AnalysisService:
    """Coordinates multi-agent analysis triggering, result persistence, and report delivery."""

    def __init__(self, workflow: Optional[AlignmentWorkflow] = None):
        self.workflow = workflow or AlignmentWorkflow()

    async def trigger_analysis(self, project_id: str) -> AlignmentWorkflowResult:
        """Triggers the full Perspective -> Conflict -> Resolution multi-agent workflow for a project."""
        project = await storage_service.get_project(project_id)
        if not project:
            raise ValueError(f"Project with ID '{project_id}' not found.")

        responses = await storage_service.get_responses(project_id)
        if not responses:
            raise ValueError(f"No team member responses found for project '{project_id}'.")

        logger.info(f"Running multi-agent analysis for project {project_id} with {len(responses)} response(s).")
        result: AlignmentWorkflowResult = await self.workflow.run(
            project_id=project_id, responses=responses
        )

        # Store the synthesis report into storage
        await storage_service.save_report(project_id, result.synthesis_output)

        return result

    async def get_latest_report(self, project_id: str) -> Optional[SynthesisReport]:
        """Retrieves the latest alignment report for a project."""
        project = await storage_service.get_project(project_id)
        if not project:
            raise ValueError(f"Project with ID '{project_id}' not found.")
        return await storage_service.get_latest_report(project_id)


analysis_service = AnalysisService()
