"""Multi-Agent Alignment Workflow.

Coordinates the sequential multi-agent workflow using Google ADK:
    Perspective Agent → Conflict Agent → Resolution Agent

Key architectural guarantees:
1. Distinct prompts and responsibilities per agent.
2. Structured Pydantic validation across all agent boundaries.
3. Preserves original quotes and source evidence from input through synthesis.
4. Stores complete intermediate states for debugging and auditing.
5. Retries with exponential backoff on transient errors.
6. Strictly prevents auto-approval of resolutions.
7. Explicitly marks execution mode (LIVE_GEMINI vs MOCK_DETERMINISTIC).
8. Designed for extensibility: future Commitment Tracking & Orchestrator agents can be appended.
"""

import asyncio
import logging
import time
import uuid
from typing import Any, Callable, Dict, List, Optional

from google.adk.workflow import Workflow, START
from google.genai import Client

from app.config import settings
from app.agents.perspective import (
    PerspectiveAnalysisService,
    create_perspective_adk_agent,
)
from app.agents.conflict import (
    ConflictDetectionService,
    create_conflict_adk_agent,
)
from app.agents.resolution import (
    ResolutionSynthesisService,
    create_resolution_adk_agent,
)
from app.models.schemas import (
    AlignmentWorkflowResult,
    ConflictDetectionOutput,
    MemberResponse,
    PerspectiveAnalysisOutput,
    SynthesisReport,
)

logger = logging.getLogger(__name__)


def build_adk_alignment_graph() -> Workflow:
    """Builds the native Google ADK Workflow graph with sequential agent nodes.

    START -> Perspective Agent -> Conflict Detection Agent -> Resolution Agent
    """
    perspective_agent = create_perspective_adk_agent()
    conflict_agent = create_conflict_adk_agent()
    resolution_agent = create_resolution_adk_agent()

    workflow = Workflow(
        name="team_alignment_workflow",
        description="Sequential multi-agent workflow analyzing perspectives, conflicts, and compromise proposals.",
        edges=[(START, perspective_agent, conflict_agent, resolution_agent)],
    )
    return workflow


class AlignmentWorkflow:
    """Orchestrates the sequential multi-agent alignment workflow."""

    def __init__(
        self,
        client: Optional[Client] = None,
        max_retries: int = settings.max_retries,
    ):
        self.client = client or (Client(api_key=settings.active_api_key) if settings.active_api_key else None)
        self.max_retries = max_retries

        # Initialize the specialized agent services
        self.perspective_service = PerspectiveAnalysisService(client=self.client)
        self.conflict_service = ConflictDetectionService(client=self.client)
        self.resolution_service = ResolutionSynthesisService(client=self.client)

        # ADK Workflow graph instance
        self.adk_workflow = build_adk_alignment_graph()

        # Hook for future agent extensions (e.g. Commitment Tracking, Orchestrator)
        self._extension_agents: List[Callable] = []

    def register_extension_agent(self, agent_fn: Callable) -> None:
        """Allows registering future agents (such as Commitment Tracking Agent)."""
        self._extension_agents.append(agent_fn)

    async def _execute_with_retry(
        self, stage_name: str, coroutine_fn: Callable, *args, **kwargs
    ) -> Any:
        """Executes an agent stage with retry logic and error reporting."""
        last_error = None
        for attempt in range(1, self.max_retries + 1):
            try:
                logger.info(f"Executing workflow stage: {stage_name} (Attempt {attempt}/{self.max_retries})")
                return await coroutine_fn(*args, **kwargs)
            except Exception as e:
                last_error = e
                logger.warning(f"Error in stage {stage_name} (Attempt {attempt}): {e}")
                if attempt < self.max_retries:
                    delay = 2 ** (attempt - 1)
                    await asyncio.sleep(delay)
                else:
                    logger.error(f"Stage {stage_name} failed after {self.max_retries} attempts.")
                    raise RuntimeError(f"Workflow stage '{stage_name}' failed: {e}") from e

    async def run(
        self, project_id: str, responses: List[MemberResponse]
    ) -> AlignmentWorkflowResult:
        """Runs the complete end-to-end multi-agent alignment analysis."""
        start_time = time.time()
        workflow_id = f"wf-{uuid.uuid4().hex[:10]}"
        intermediate_results: Dict[str, Any] = {}

        execution_mode = "LIVE_GEMINI" if settings.is_live_gemini_available else "MOCK_DETERMINISTIC"
        logger.info(f"Starting Alignment Workflow [{workflow_id}] for project: {project_id} in {execution_mode} mode")

        # ---------------------------------------------------------
        # Stage 1: Perspective Analysis Agent
        # ---------------------------------------------------------
        logger.info("--> [Agent 1] Invoking Perspective Analysis Agent")
        perspectives_output: PerspectiveAnalysisOutput = await self._execute_with_retry(
            "PerspectiveAnalysis",
            self.perspective_service.analyze,
            responses=responses,
        )
        intermediate_results["perspectives"] = perspectives_output.model_dump()

        # ---------------------------------------------------------
        # Stage 2: Conflict Detection Agent
        # ---------------------------------------------------------
        logger.info("--> [Agent 2] Invoking Conflict Detection Agent")
        conflicts_output: ConflictDetectionOutput = await self._execute_with_retry(
            "ConflictDetection",
            self.conflict_service.detect_conflicts,
            perspective_data=perspectives_output,
        )
        intermediate_results["conflicts"] = conflicts_output.model_dump()

        # ---------------------------------------------------------
        # Stage 3: Resolution & Synthesis Agent
        # ---------------------------------------------------------
        logger.info("--> [Agent 3] Invoking Resolution & Synthesis Agent")
        synthesis_output: SynthesisReport = await self._execute_with_retry(
            "ResolutionSynthesis",
            self.resolution_service.synthesize,
            project_id=project_id,
            perspectives=perspectives_output,
            conflicts=conflicts_output,
        )

        # Enforce safety invariant: status must always be PROPOSED
        for res in synthesis_output.proposed_resolutions:
            res.status = "PROPOSED"

        intermediate_results["synthesis"] = synthesis_output.model_dump()

        # ---------------------------------------------------------
        # Future Extension Hooks (e.g. Commitment Tracking)
        # ---------------------------------------------------------
        for ext_agent in self._extension_agents:
            try:
                logger.info(f"--> [Extension Agent] Executing {ext_agent.__name__}")
                await ext_agent(project_id, intermediate_results)
            except Exception as ext_err:
                logger.warning(f"Extension agent {ext_agent.__name__} raised error: {ext_err}")

        duration = round(time.time() - start_time, 3)

        # Accurately verify whether all stages genuinely executed live or fell back
        stage_modes = [
            self.perspective_service.last_execution_mode,
            self.conflict_service.last_execution_mode,
            self.resolution_service.last_execution_mode,
        ]
        if all(m == "LIVE_GEMINI" for m in stage_modes):
            final_execution_mode = "LIVE_GEMINI"
        elif any("FALLBACK" in m for m in stage_modes):
            fallbacks = [m for m in stage_modes if "FALLBACK" in m]
            final_execution_mode = f"MOCK_FALLBACK: {'; '.join(fallbacks)}"
        else:
            final_execution_mode = "MOCK_DETERMINISTIC"

        execution_metadata = {
            "workflow_id": workflow_id,
            "project_id": project_id,
            "duration_seconds": duration,
            "model": settings.gemini_model,
            "framework": "Google Agent Development Kit (ADK) v2.11.0",
            "adk_workflow_graph": self.adk_workflow.name,
            "adk_runner_enabled": settings.use_adk_runner,
            "agent_sequence": [
                "perspective_analysis_agent",
                "conflict_detection_agent",
                "resolution_synthesis_agent",
            ],
            "total_responses_analyzed": len(responses),
            "conflicts_detected": len(conflicts_output.conflicts),
            "resolutions_proposed": len(synthesis_output.proposed_resolutions),
            "execution_mode": final_execution_mode,
        }

        logger.info(f"Workflow [{workflow_id}] completed successfully in {duration}s [{final_execution_mode}]")

        return AlignmentWorkflowResult(
            workflow_id=workflow_id,
            project_id=project_id,
            perspectives_output=perspectives_output,
            conflicts_output=conflicts_output,
            synthesis_output=synthesis_output,
            intermediate_results=intermediate_results,
            execution_metadata=execution_metadata,
            execution_mode=final_execution_mode,
        )
