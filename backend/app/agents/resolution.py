"""Resolution & Synthesis Agent.

Agent 3 in the multi-agent alignment workflow.
Synthesizes detected conflicts and individual perspectives to recommend
realistic compromises and actionable solutions.

CRITICAL GOVERNANCE CONSTRAINT:
Never automatically finalizes team decisions.
All proposed resolutions are marked with status="PROPOSED".
Explicitly identifies unresolved questions requiring human judgment.
"""

import json
import logging
from typing import Any, Dict, List, Optional
from google.adk.agents import Agent
from google.genai import Client, types

from app.config import settings
from app.models.schemas import (
    ConflictDetectionOutput,
    PerspectiveAnalysisOutput,
    ProposedResolution,
    ResolutionOption,
    SynthesisReport,
)

logger = logging.getLogger(__name__)

RESOLUTION_AGENT_INSTRUCTION = """
You are the Resolution & Synthesis Agent on an AI Team Alignment Platform.
Your purpose is to facilitate collaborative team consensus by analyzing conflicts and synthesizing pragmatic compromise proposals.

CRITICAL GOVERNANCE PRINCIPLES:
1. NEVER AUTOMATICALLY FINALIZE DECISIONS:
   - Your outputs are strictly RECOMMENDATIONS and PROPOSALS.
   - You must never mark a decision as "APPROVED" or "FINAL".
   - The status of every proposed resolution MUST be "PROPOSED".
2. EQUITABLE PERSPECTIVE SYNTHESIS:
   - Carefully consider every teammate's perspective and constraints.
   - Do not dismiss any member's valid concern (e.g. testing requirements or hard deadlines).
3. PRAGMATIC COMPROMISES & OPTIONS:
   - For every detected conflict, formulate a primary `recommended_solution` with clear reasoning.
   - Provide concrete alternative options (`alternative_options`) showing pros, cons, and trade-offs.
   - For deadline clashes, propose realistic sequenced schedules (e.g. accommodating frontend finish, QA window, and launch).
4. UNRESOLVED QUESTIONS:
   - Explicitly list specific questions that require human consensus and cannot be decided by AI.
5. ESTIMATE ALIGNMENT SCORE:
   - Provide an alignment score from 0.0 to 100.0 based on the proportion and severity of resolved vs blocking conflicts.

You must respond ONLY with structured JSON matching the SynthesisReport schema.
""".strip()


def create_resolution_adk_agent() -> Agent:
    """Creates the Google ADK Agent instance for Resolution & Synthesis."""
    return Agent(
        name="resolution_synthesis_agent",
        description="Synthesizes team perspectives and conflicts to generate non-binding compromise proposals.",
        model=settings.gemini_model,
        instruction=RESOLUTION_AGENT_INSTRUCTION,
        output_schema=SynthesisReport,
        output_key="synthesis",
    )


class ResolutionSynthesisService:
    """Service to execute Resolution & Synthesis using Google ADK and Gemini API."""

    def __init__(self, client: Optional[Client] = None):
        self.adk_agent = create_resolution_adk_agent()
        self.client = client
        if self.client is None and settings.active_api_key:
            self.client = Client(api_key=settings.active_api_key)

    async def synthesize(
        self,
        project_id: str,
        perspectives: PerspectiveAnalysisOutput,
        conflicts: ConflictDetectionOutput,
    ) -> SynthesisReport:
        """Generates synthesis report and proposed resolutions for human approval."""
        prompt = (
            f"Given the following team perspectives and detected conflicts:\n\n"
            f"PERSPECTIVES:\n```json\n{perspectives.model_dump_json(indent=2)}\n```\n\n"
            f"CONFLICTS:\n```json\n{conflicts.model_dump_json(indent=2)}\n```\n\n"
            f"Generate a comprehensive SynthesisReport with realistic proposed compromises, "
            f"clearly marked as PROPOSED, and highlight human action items."
        )

        # If mock mode is forced or no Gemini API key is available, execute deterministic synthesis
        if settings.mock_llm or not self.client:
            logger.info("Using deterministic Resolution & Synthesis logic (mock mode / no API key)")
            return self._mock_synthesize(project_id, perspectives, conflicts)

        # Live Gemini execution via google-genai / ADK schema
        try:
            config = types.GenerateContentConfig(
                system_instruction=RESOLUTION_AGENT_INSTRUCTION,
                response_mime_type="application/json",
                response_schema=SynthesisReport,
                temperature=settings.agent_temperature,
            )
            response = self.client.models.generate_content(
                model=settings.gemini_model,
                contents=prompt,
                config=config,
            )
            if response.text:
                data = json.loads(response.text)
                report = SynthesisReport.model_validate(data)
                report.project_id = project_id
                # Enforce safety invariant: status must always be PROPOSED
                for res in report.proposed_resolutions:
                    res.status = "PROPOSED"
                return report
            else:
                raise ValueError("Empty response received from Gemini model.")
        except Exception as e:
            logger.error("Error calling Gemini API for Resolution & Synthesis: %s", e)
            if settings.app_env == "development" or settings.mock_llm:
                logger.warning("Falling back to deterministic synthesis after error.")
                return self._mock_synthesize(project_id, perspectives, conflicts)
            raise

    def _mock_synthesize(
        self,
        project_id: str,
        perspectives: PerspectiveAnalysisOutput,
        conflicts: ConflictDetectionOutput,
    ) -> SynthesisReport:
        """Deterministic resolution synthesis for test scenarios and offline development."""
        proposed_resolutions: List[ProposedResolution] = []

        # Find deadline contradiction conflict
        for conflict in conflicts.conflicts:
            if conflict.conflict_type.value == "DEADLINE_CONTRADICTION":
                proposed_resolutions.append(
                    ProposedResolution(
                        resolution_id="RES-01",
                        conflict_id=conflict.conflict_id,
                        conflict_title=conflict.title,
                        recommended_solution=(
                            "Adopt a realistic phased schedule: Accelerate frontend MVP by Thursday afternoon "
                            "or adjust official launch to Monday morning, reserving Friday for dedicated testing. "
                            "Alternatively, if a Thursday soft launch is mandatory, launch with backend core APIs "
                            "and release the full frontend on Friday."
                        ),
                        reasoning=(
                            "Alex needs until Friday for frontend delivery, while Sam intended a Thursday launch. "
                            "Launching on Thursday is physically impossible if the frontend is incomplete. "
                            "Rescheduling public launch to Monday allows frontend completion by Friday and "
                            "gives Taylor the weekend/Friday afternoon to test thoroughly without emergency hotfixes."
                        ),
                        alternative_options=[
                            ResolutionOption(
                                option_id="OPT-A",
                                title="Adjust Public Launch to Friday Afternoon or Monday",
                                description=(
                                    "Move Sam's full launch date from Thursday to Friday afternoon (soft launch) "
                                    "or Monday morning, enabling Alex to complete the frontend on Friday morning."
                                ),
                                pros=["Preserves full frontend scope", "Avoids high-stress crunch"],
                                cons=["Delays Sam's target Thursday release by 1 to 3 days"],
                                compromise_notes="Satisfies Alex's completion timeline and accommodates quality review.",
                            ),
                            ResolutionOption(
                                option_id="OPT-B",
                                title="Scope Trimming for Thursday Partial Launch",
                                description=(
                                    "Alex ships an essential 'P0-only' frontend subset by Wednesday evening, "
                                    "allowing testing on Thursday morning and a limited Thursday soft launch."
                                ),
                                pros=["Maintains Sam's Thursday launch target"],
                                cons=["Frontend will have reduced polish and missing secondary features"],
                                compromise_notes="Compromises on feature scope to preserve target date.",
                            ),
                        ],
                        impacted_members=conflict.parties_involved,
                        unresolved_questions_for_team=[
                            "Is Sam's Thursday deadline driven by an external stakeholder or internal preference?",
                            "Can Alex scope down the frontend to a P0 MVP deliverable by Wednesday evening?",
                            "Would Sam accept a Monday launch if it guarantees full testing and polish?",
                        ],
                        status="PROPOSED",
                    )
                )

            elif conflict.conflict_type.value == "INFORMATION_GAP":
                proposed_resolutions.append(
                    ProposedResolution(
                        resolution_id="RES-02",
                        conflict_id=conflict.conflict_id,
                        conflict_title=conflict.title,
                        recommended_solution=(
                            "Establish an explicit QA Testing window: Taylor leads a 24-hour testing cycle "
                            "commencing immediately upon frontend and backend feature freeze."
                        ),
                        reasoning=(
                            "Taylor rightly highlighted that launching without testing invites critical failures. "
                            "By budgeting an explicit QA window into the project timeline, the team protects "
                            "product stability while acknowledging Alex and Sam's delivery goals."
                        ),
                        alternative_options=[
                            ResolutionOption(
                                option_id="OPT-QA-1",
                                title="Dedicated Testing Gate",
                                description="Freeze all development 24 hours prior to public release for regression testing.",
                                pros=["High stability", "Reduced launch bugs"],
                                cons=["Requires early code freeze"],
                                compromise_notes="Protects Taylor's quality standard without indefinite delays.",
                            ),
                            ResolutionOption(
                                option_id="OPT-QA-2",
                                title="Concurrent Feature Smoke Testing",
                                description="Taylor conducts ongoing component testing as Alex finishes individual screens.",
                                pros=["Shortens testing turnaround after final merge"],
                                cons=["Higher coordination overhead between Alex and Taylor"],
                                compromise_notes="Allows faster path to launch while testing iteratively.",
                            ),
                        ],
                        impacted_members=conflict.parties_involved,
                        unresolved_questions_for_team=[
                            "How many hours of testing are required before Taylor feels confident signing off?",
                            "Can Taylor begin testing API endpoints and mock components before the full UI is merged?",
                        ],
                        status="PROPOSED",
                    )
                )

        key_findings = [
            "Severe schedule contradiction between Friday frontend completion and Thursday application launch.",
            "Testing requirements raised by Taylor were previously unbudgeted in the launch timeline.",
            "The team shares a common goal of a successful launch, but lacks a synchronized milestone roadmap.",
        ]

        human_action_items = [
            "Team discussion needed: Vote on whether to reschedule launch to Monday or reduce frontend scope for Thursday.",
            "Alex and Taylor to agree on code freeze deadline for QA handoff.",
            "Confirm test plan requirements and minimum criteria for release sign-off.",
        ]

        # Calculate alignment index (e.g. 55% given high severity conflict)
        alignment_score = 55.0 if any(c.severity.value == "HIGH" for c in conflicts.conflicts) else 75.0

        return SynthesisReport(
            report_id="SYNTH-01",
            project_id=project_id,
            executive_summary=(
                "The team is aligned on the objective to launch, but has conflicting timeline assumptions. "
                "Alex has targeted frontend delivery for Friday, which directly clashes with Sam's expected "
                "Thursday launch. Taylor has also introduced a crucial prerequisite for comprehensive testing. "
                "Two realistic compromise paths (Schedule Extension vs Scope Reduction) are proposed for team review."
            ),
            alignment_score=alignment_score,
            key_findings=key_findings,
            proposed_resolutions=proposed_resolutions,
            human_action_items=human_action_items,
            disclaimer=(
                "All resolutions are AI-generated proposals and require explicit human team approval "
                "before becoming commitments. No decisions have been finalized."
            ),
        )
