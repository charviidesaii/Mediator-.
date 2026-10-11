"""Resolution & Synthesis Agent.

Agent 3 in the multi-agent alignment workflow.
Synthesizes detected conflicts and individual perspectives to recommend
realistic compromises and actionable solutions across arbitrary participants.

CRITICAL GOVERNANCE CONSTRAINT:
Never automatically finalizes team decisions.
All proposed resolutions are marked with status="PROPOSED".
Explicitly identifies unresolved questions requiring human judgment.
"""

import json
import logging
import re
from typing import Any, Dict, List, Optional
from google.adk.agents import Agent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import Client, types

from app.config import settings
from app.models.schemas import (
    ConflictDetectionOutput,
    ConflictSeverity,
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
3. PRAGMATIC COMPROMISES & CONFIRMING OWNERSHIP:
   - For every detected conflict, formulate a primary `recommended_solution` in 1 to 2 concise sentences with clear reasoning.
   - If ownership of a task or milestone is unclear, suggest CONFIRMING an owner rather than inventing or arbitrarily assigning one.
   - Never invent or confirm assignments and deadlines on behalf of the team.
   - Provide concrete alternative options (`alternative_options`) showing pros, cons, and trade-offs.
   - For deadline clashes, propose realistic sequenced schedules accommodating prerequisite development, testing window, and presentation.
4. UNRESOLVED QUESTIONS:
   - Explicitly list specific questions that require human consensus and cannot be decided by AI.
5. ESTIMATE ALIGNMENT SCORE:
   - Provide an alignment score from 0.0 to 100.0 based on the proportion and severity of distinct resolved vs blocking conflicts.

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
        self.last_execution_mode: str = "MOCK_DETERMINISTIC"
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

        # If mock mode is active or no Gemini API key is configured, run generalized deterministic synthesis
        if not settings.is_live_gemini_available:
            self.last_execution_mode = "MOCK_DETERMINISTIC"
            logger.info("Resolution Synthesis running in deterministic mode (no live Gemini key or mock enabled)")
            return self._mock_synthesize(project_id, perspectives, conflicts)

        # Live Google ADK / Gemini execution
        try:
            logger.info(f"Invoking Google ADK Resolution Agent with model: {settings.gemini_model}")
            if settings.use_adk_runner:
                session_service = InMemorySessionService()
                session = await session_service.create_session(
                    app_name="mediator", user_id="system_coordinator"
                )
                runner = Runner(
                    agent=self.adk_agent,
                    app_name="mediator",
                    session_service=session_service,
                )
                user_content = types.Content(
                    role="user",
                    parts=[types.Part.from_text(text=prompt)],
                )

                final_text = ""
                async for event in runner.run_async(
                    user_id="system_coordinator",
                    session_id=session.id,
                    new_message=user_content,
                ):
                    if event.is_final_response() and event.content and event.content.parts:
                        for part in event.content.parts:
                            if part.text and not getattr(part, "thought", False):
                                final_text += part.text

                if final_text.strip():
                    data = json.loads(final_text)
                    report = SynthesisReport.model_validate(data)
                    report.project_id = project_id
                    for res in report.proposed_resolutions:
                        res.status = "PROPOSED"
                    if conflicts.conflicts:
                        high_c = len([c for c in conflicts.conflicts if c.severity == ConflictSeverity.HIGH])
                        med_c = len([c for c in conflicts.conflicts if c.severity == ConflictSeverity.MEDIUM])
                        expected_score = max(25.0, min(100.0, 100.0 - (high_c * 15.0) - (med_c * 10.0)))
                        if report.alignment_score < expected_score - 15:
                            report.alignment_score = expected_score
                    self.last_execution_mode = "LIVE_GEMINI"
                    return report

            # Direct fallback if ADK runner stream is empty
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
                if conflicts.conflicts:
                    high_c = len([c for c in conflicts.conflicts if c.severity == ConflictSeverity.HIGH])
                    med_c = len([c for c in conflicts.conflicts if c.severity == ConflictSeverity.MEDIUM])
                    expected_score = max(25.0, min(100.0, 100.0 - (high_c * 15.0) - (med_c * 10.0)))
                    if report.alignment_score < expected_score - 15:
                        report.alignment_score = expected_score
                self.last_execution_mode = "LIVE_GEMINI"
                return report
            else:
                raise ValueError("Empty response received from Gemini model.")
        except Exception as e:
            logger.error("Error executing Google ADK / Gemini for Resolution Synthesis: %s", e)
            if settings.app_env == "development" or settings.mock_llm:
                self.last_execution_mode = f"MOCK_FALLBACK ({type(e).__name__})"
                logger.warning(f"Falling back to deterministic synthesis after error: {e}")
                return self._mock_synthesize(project_id, perspectives, conflicts)
            raise

    def _mock_synthesize(
        self,
        project_id: str,
        perspectives: PerspectiveAnalysisOutput,
        conflicts: ConflictDetectionOutput,
    ) -> SynthesisReport:
        """Generalized deterministic resolution synthesis for arbitrary participants."""
        proposed_resolutions: List[ProposedResolution] = []
        res_counter = 1

        for conflict in conflicts.conflicts:
            parties = ", ".join(conflict.parties_involved)

            if conflict.conflict_type.value == "DEADLINE_CONTRADICTION":
                proposed_resolutions.append(
                    ProposedResolution(
                        resolution_id=f"RES-{res_counter:02d}",
                        conflict_id=conflict.conflict_id,
                        conflict_title=conflict.title,
                        recommended_solution=(
                            f"Adopt a synchronized milestone schedule accommodating {parties}: "
                            "Reschedule the full public launch to follow prerequisite completion, "
                            "or define a limited P0 MVP soft launch on the earlier target date while "
                            "final deliverables and thorough regression testing proceed."
                        ),
                        reasoning=(
                            f"Identified conflicting milestone sequencing between {parties}. "
                            "A software deliverable cannot physically launch before its core dependencies are complete. "
                            "Aligning the release schedule protects product quality while respecting individual delivery constraints."
                        ),
                        alternative_options=[
                            ResolutionOption(
                                option_id=f"OPT-{res_counter}A",
                                title="Adjust Public Launch Date",
                                description="Shift the target launch date by 1 to 3 days to allow all prerequisite development and testing gates to complete fully.",
                                pros=["Ensures full feature scope", "Avoids high-stress crunch"],
                                cons=["Extends initial launch milestone"],
                                compromise_notes=f"Directly accommodates delivery timelines stated by {parties}.",
                            ),
                            ResolutionOption(
                                option_id=f"OPT-{res_counter}B",
                                title="Scope Trimming for Early Soft Launch",
                                description="Trim non-essential feature scope to ship an MVP core on the earlier date, reserving complete features for a subsequent release.",
                                pros=["Preserves earlier launch timeline target"],
                                cons=["Requires cutting or deferring secondary features"],
                                compromise_notes="Compromises on feature scope in exchange for speed.",
                            ),
                        ],
                        impacted_members=conflict.parties_involved,
                        unresolved_questions_for_team=[
                            f"Is the earlier target launch date an unmovable external commitment or an internal goal?",
                            f"Can {parties} agree on a minimal subset of P0 features that would be acceptable for an earlier beta release?",
                            f"What is the latest acceptable date for full public release?",
                        ],
                        status="PROPOSED",
                    )
                )
                res_counter += 1

            elif conflict.conflict_type.value == "INFORMATION_GAP":
                proposed_resolutions.append(
                    ProposedResolution(
                        resolution_id=f"RES-{res_counter:02d}",
                        conflict_id=conflict.conflict_id,
                        conflict_title=conflict.title,
                        recommended_solution=(
                            f"Establish an explicit dedicated Quality Assurance gate between {parties}: "
                            "Budget a formal testing cycle of 24-48 hours immediately following feature code freeze."
                        ),
                        reasoning=(
                            "Releasing without a dedicated testing window creates substantial stability and reputation risk. "
                            "Formally scheduling a QA gate gives engineers predictable handoff times and protects product reliability."
                        ),
                        alternative_options=[
                            ResolutionOption(
                                option_id=f"OPT-{res_counter}A",
                                title="Formal Code Freeze and QA Window",
                                description="Freeze all incoming feature code 24 hours prior to release for smoke and regression testing.",
                                pros=["Maximizes release reliability and bug discovery"],
                                cons=["Prevents last-minute code additions"],
                                compromise_notes=f"Satisfies quality requirements raised by {parties}.",
                            ),
                            ResolutionOption(
                                option_id=f"OPT-{res_counter}B",
                                title="Continuous Component Smoke Testing",
                                description="Run incremental test suites against individual components as they are completed.",
                                pros=["Shortens testing turnaround after final merge"],
                                cons=["Requires higher coordination overhead during development"],
                                compromise_notes="Enables ongoing testing in parallel with development.",
                            ),
                        ],
                        impacted_members=conflict.parties_involved,
                        unresolved_questions_for_team=[
                            "What are the minimum acceptance test criteria required for release sign-off?",
                            "Who holds final decision authority to approve or block the release based on test outcomes?",
                        ],
                        status="PROPOSED",
                    )
                )
                res_counter += 1

            elif conflict.conflict_type.value == "RESPONSIBILITY_OVERLAP_OR_GAP":
                first_party = conflict.parties_involved[0] if conflict.parties_involved else "Lead"
                second_party = conflict.parties_involved[1] if len(conflict.parties_involved) > 1 else "Reviewer"
                # Extract clean task label from title
                task_label = conflict.title
                if ":" in task_label:
                    task_label = task_label.split(":", 1)[1].strip()
                task_label = re.sub(r"\s+Between\s+.*$", "", task_label, flags=re.IGNORECASE).strip()
                if not task_label:
                    task_label = "this deliverable"

                proposed_resolutions.append(
                    ProposedResolution(
                        resolution_id=f"RES-{res_counter:02d}",
                        conflict_id=conflict.conflict_id,
                        conflict_title=conflict.title,
                        recommended_solution=(
                            f"Confirm which team member owns {task_label.lower()} between {parties} during the next sync to establish clear accountability."
                        ),
                        reasoning=(
                            f"Identified unconfirmed ownership expectations across {parties}. "
                            "Having unconfirmed assumptions creates execution gaps where critical tasks are dropped. "
                            "Confirming an explicit owner with backup support ensures predictable delivery."
                        ),
                        alternative_options=[
                            ResolutionOption(
                                option_id=f"OPT-{res_counter}A",
                                title=f"Confirm {first_party} as Primary Owner with {second_party} as Reviewer",
                                description=f"{first_party} leads hands-on implementation while {second_party} conducts peer review.",
                                pros=["Clear single-threaded ownership", "Reduces ambiguity"],
                                cons=[f"Concentrates workload on {first_party}"],
                                compromise_notes=f"Maintains {second_party}'s visibility through peer review checkpoints.",
                            ),
                            ResolutionOption(
                                option_id=f"OPT-{res_counter}B",
                                title=f"Split Scope between {first_party} and {second_party}",
                                description="Divide responsibilities into configuration/CI setup vs deployment and validation.",
                                pros=["Shared engagement", "Prevents single-point dependency"],
                                cons=["Requires explicit handoff interface"],
                                compromise_notes=f"Allows both {first_party} and {second_party} to contribute distinct technical expertise.",
                            ),
                        ],
                        impacted_members=conflict.parties_involved,
                        unresolved_questions_for_team=[
                            f"Between {parties}, who has direct bandwidth to take primary accountability for {task_label.lower()}?",
                            "Can the team agree on a simple RACI handoff for release milestones?",
                        ],
                        status="PROPOSED",
                    )
                )
                res_counter += 1

            else:
                proposed_resolutions.append(
                    ProposedResolution(
                        resolution_id=f"RES-{res_counter:02d}",
                        conflict_id=conflict.conflict_id,
                        conflict_title=conflict.title,
                        recommended_solution=f"Schedule a 15-minute alignment sync between {parties} to agree on prioritized deliverables.",
                        reasoning="Direct dialogue with clear trade-offs will resolve non-blocking priority divergences.",
                        alternative_options=[
                            ResolutionOption(
                                option_id=f"OPT-{res_counter}A",
                                title="Consensus Alignment",
                                description="Agree on a single prioritized backlog.",
                                pros=["Full team alignment"],
                                cons=["Requires negotiation"],
                                compromise_notes="Balances individual concerns.",
                            )
                        ],
                        impacted_members=conflict.parties_involved,
                        unresolved_questions_for_team=["Which objective takes priority if time runs short?"],
                        status="PROPOSED",
                    )
                )
                res_counter += 1

        # Fallback resolution if 0 conflicts detected
        if not proposed_resolutions:
            proposed_resolutions.append(
                ProposedResolution(
                    resolution_id="RES-01",
                    conflict_id="ALIGN-01",
                    conflict_title="Team Timeline Synchronization",
                    recommended_solution="Confirm milestone targets and proceed with planned deliverables.",
                    reasoning="No direct contradictions were detected among submitted perspectives.",
                    alternative_options=[],
                    impacted_members=[p.member_name for p in perspectives.perspectives],
                    unresolved_questions_for_team=["Are there any external dependencies not captured in initial statements?"],
                    status="PROPOSED",
                )
            )

        key_findings = [
            f"Analyzed {len(perspectives.perspectives)} participant perspective(s) with {len(conflicts.conflicts)} detected misalignment(s).",
            f"Key focus areas identified: {', '.join(set(g.statement for p in perspectives.perspectives for g in p.goals)) if perspectives.perspectives else 'None'}.",
        ]
        if any(c.severity.value == "HIGH" for c in conflicts.conflicts):
            key_findings.append("A high-severity milestone contradiction requires team reconciliation before proceeding.")

        human_action_items = [
            "Team review required: Review proposed compromise options and vote on schedule realignment.",
            "Confirm handoff dates between implementation leads and QA.",
            "Record final approved commitments through the /decisions API.",
        ]
        # Calculate alignment index based on distinct grouped conflicts
        high_conflicts = len([c for c in conflicts.conflicts if c.severity.value == "HIGH"])
        med_conflicts = len([c for c in conflicts.conflicts if c.severity.value == "MEDIUM"])
        low_conflicts = len([c for c in conflicts.conflicts if c.severity.value == "LOW"])
        alignment_score = max(25.0, min(100.0, 100.0 - (high_conflicts * 15.0) - (med_conflicts * 10.0) - (low_conflicts * 5.0)))

        return SynthesisReport(
            report_id=f"SYNTH-{project_id[:8]}",
            project_id=project_id,
            executive_summary=(
                f"The multi-agent alignment workflow evaluated perspectives from {len(perspectives.perspectives)} teammate(s). "
                f"Generated {len(proposed_resolutions)} proposed resolution(s) addressing {len(conflicts.conflicts)} conflict(s). "
                "All proposals require human team sign-off."
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
