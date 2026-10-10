"""Conflict Detection Agent.

Agent 2 in the multi-agent alignment workflow.
Compares individual perspectives produced by Agent 1 to detect:
- Contradictory deadlines
- Incompatible goals
- Priority mismatches
- Missing information & dependencies

Distinguishes genuine disagreements from compatible differences and assigns
severity using strictly documented criteria across arbitrary participants.
"""

import json
import logging
from typing import Any, Dict, List, Optional
from google.adk.agents import Agent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import Client, types

from app.config import settings
from app.models.schemas import (
    ConflictCategory,
    ConflictDetectionOutput,
    ConflictSeverity,
    ConflictType,
    DetectedConflict,
    EvidenceItem,
    PerspectiveAnalysisOutput,
)

logger = logging.getLogger(__name__)

CONFLICT_AGENT_INSTRUCTION = """
You are the Conflict Detection Agent on an AI Team Alignment Platform.
Your mission is to objectively compare structured team member perspectives and systematically identify misalignments, contradictions, and information gaps.

Core Responsibilities:
1. Systematically compare all team members' goals, priorities, responsibilities, and deadlines across all participants.
2. Detect specific misalignments:
   - Contradictory Deadlines: When one milestone is scheduled before its required dependency (e.g. Launching before feature completion).
   - Incompatible Goals: Objectives that cannot simultaneously succeed given current resource/time boundaries.
   - Priority Mismatches: Conflicting urgency or order of operations.
   - Information Gaps: Crucial unstated dependencies (e.g. testing schedule unspecified).
3. DISTINGUISH DISAGREEMENTS FROM COMPATIBLE DIFFERENCES:
   - DIRECT_DISAGREEMENT: Mutually exclusive constraints that cannot coexist without compromise.
   - COMPATIBLE_DIFFERENCE: Non-conflicting variations in focus or responsibility that complement each other.
   - Document compatible differences in `compatible_differences`.
4. EVIDENCE & ATTRIBUTION:
   - Every detected conflict MUST cite the exact statements/quotes from the team members in the `evidence` field.
   - Explicitly list all `parties_involved`.
5. SEVERITY CRITERIA:
   - HIGH: Blocking contradiction; physically or logically impossible to achieve without failure (e.g., launching an unbuilt or untested product).
   - MEDIUM: Significant friction; timeline compression or unclarified dependencies that jeopardize project quality or team morale.
   - LOW: Minor difference in preference, terminology, or non-critical sequencing.
   - You MUST explain the rationale in `severity_reasoning`.

You must respond ONLY with structured JSON matching the ConflictDetectionOutput schema.
""".strip()


def create_conflict_adk_agent() -> Agent:
    """Creates the Google ADK Agent instance for Conflict Detection."""
    return Agent(
        name="conflict_detection_agent",
        description="Compares structured team perspectives to detect contradictions, mismatches, and gaps.",
        model=settings.gemini_model,
        instruction=CONFLICT_AGENT_INSTRUCTION,
        output_schema=ConflictDetectionOutput,
        output_key="conflicts",
    )


class ConflictDetectionService:
    """Service to execute Conflict Detection using Google ADK and Gemini API."""

    def __init__(self, client: Optional[Client] = None):
        self.adk_agent = create_conflict_adk_agent()
        self.client = client
        if self.client is None and settings.active_api_key:
            self.client = Client(api_key=settings.active_api_key)

    async def detect_conflicts(
        self, perspective_data: PerspectiveAnalysisOutput
    ) -> ConflictDetectionOutput:
        """Analyzes structured perspective output and detects conflicts."""
        if not perspective_data.perspectives or len(perspective_data.perspectives) < 2:
            return ConflictDetectionOutput(
                conflicts=[],
                compatible_differences=["Single team member response or no perspectives provided."],
                critical_information_gaps=perspective_data.identified_gaps,
                synthesis_summary="Insufficient perspectives to compare for team alignment (at least 2 teammates required).",
            )

        prompt = (
            f"Analyze the following structured perspectives extracted from team members:\n"
            f"```json\n{perspective_data.model_dump_json(indent=2)}\n```\n\n"
            f"Identify all contradictions, incompatible deadlines, priority mismatches, and information gaps."
        )

        # If mock mode is active or no Gemini API key is configured, run generalized deterministic detection
        if not settings.is_live_gemini_available:
            logger.info("Conflict Detection running in deterministic mode (no live Gemini key or mock enabled)")
            return self._mock_detect(perspective_data)

        # Live Google ADK / Gemini execution
        try:
            logger.info(f"Invoking Google ADK Conflict Detection Agent with model: {settings.gemini_model}")
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
                    return ConflictDetectionOutput.model_validate(data)

            # Direct fallback if ADK runner stream is empty
            config = types.GenerateContentConfig(
                system_instruction=CONFLICT_AGENT_INSTRUCTION,
                response_mime_type="application/json",
                response_schema=ConflictDetectionOutput,
                temperature=settings.agent_temperature,
            )
            response = self.client.models.generate_content(
                model=settings.gemini_model,
                contents=prompt,
                config=config,
            )
            if response.text:
                data = json.loads(response.text)
                return ConflictDetectionOutput.model_validate(data)
            else:
                raise ValueError("Empty response received from Gemini model.")
        except Exception as e:
            logger.error("Error executing Google ADK / Gemini for Conflict Detection: %s", e)
            if settings.app_env == "development" or settings.mock_llm:
                logger.warning("Falling back to deterministic conflict detection after error.")
                return self._mock_detect(perspective_data)
            raise

    def _mock_detect(
        self, perspective_data: PerspectiveAnalysisOutput
    ) -> ConflictDetectionOutput:
        """Generalized deterministic conflict detection for arbitrary participants."""
        conflicts: List[DetectedConflict] = []
        compatible_diffs: List[str] = []
        gaps: List[str] = list(perspective_data.identified_gaps)

        perspectives = perspective_data.perspectives
        day_rank = {
            "monday": 1,
            "tuesday": 2,
            "wednesday": 3,
            "thursday": 4,
            "friday": 5,
            "saturday": 6,
            "sunday": 7,
        }

        # 1. Dynamic Deadline Collision Search across ALL member pairs
        conflict_counter = 1
        for i in range(len(perspectives)):
            for j in range(i + 1, len(perspectives)):
                p1 = perspectives[i]
                p2 = perspectives[j]

                # Check deadline pairs
                for d1 in p1.deadlines:
                    for d2 in p2.deadlines:
                        d1_day = d1.expected_deadline.lower()
                        d2_day = d2.expected_deadline.lower()

                        if d1_day in day_rank and d2_day in day_rank:
                            rank1 = day_rank[d1_day]
                            rank2 = day_rank[d2_day]

                            # Determine if one milestone is launch and the other is development/frontend/testing
                            is_p1_launch = "launch" in d1.milestone.lower() or "release" in d1.milestone.lower()
                            is_p2_launch = "launch" in d2.milestone.lower() or "release" in d2.milestone.lower()

                            # Case A: p1 expects launch before p2 finishes development
                            if is_p1_launch and not is_p2_launch and rank1 < rank2:
                                conflicts.append(
                                    DetectedConflict(
                                        conflict_id=f"CONF-{conflict_counter:02d}",
                                        title=f"Deadline Sequence Inversion: {p1.member_name} Launch Precedes {p2.member_name} Completion",
                                        conflict_type=ConflictType.DEADLINE_CONTRADICTION,
                                        category=ConflictCategory.DIRECT_DISAGREEMENT,
                                        severity=ConflictSeverity.HIGH,
                                        severity_reasoning=(
                                            f"Logical impossibility: {p1.member_name} expects to launch on {d1.expected_deadline}, "
                                            f"while {p2.member_name} has scheduled {d2.milestone} for {d2.expected_deadline}. "
                                            "The deliverable cannot be released before its prerequisite work is completed."
                                        ),
                                        parties_involved=[p1.member_name, p2.member_name],
                                        evidence=[
                                            EvidenceItem(
                                                member_name=p1.member_name,
                                                quote=d1.source_quote,
                                                interpretation=f"Believes launch/release is scheduled for {d1.expected_deadline}.",
                                            ),
                                            EvidenceItem(
                                                member_name=p2.member_name,
                                                quote=d2.source_quote,
                                                interpretation=f"Targeting {d2.milestone} on {d2.expected_deadline}.",
                                            ),
                                        ],
                                        impact_description=(
                                            f"Direct delivery blocker. Releasing on {d1.expected_deadline} risks shipping incomplete "
                                            f"functionality or missing the target launch date."
                                        ),
                                    )
                                )
                                conflict_counter += 1

                            # Case B: p2 expects launch before p1 finishes development
                            elif is_p2_launch and not is_p1_launch and rank2 < rank1:
                                conflicts.append(
                                    DetectedConflict(
                                        conflict_id=f"CONF-{conflict_counter:02d}",
                                        title=f"Deadline Sequence Inversion: {p2.member_name} Launch Precedes {p1.member_name} Completion",
                                        conflict_type=ConflictType.DEADLINE_CONTRADICTION,
                                        category=ConflictCategory.DIRECT_DISAGREEMENT,
                                        severity=ConflictSeverity.HIGH,
                                        severity_reasoning=(
                                            f"Logical impossibility: {p2.member_name} expects to launch on {d2.expected_deadline}, "
                                            f"while {p1.member_name} has scheduled {d1.milestone} for {d1.expected_deadline}. "
                                            "The deliverable cannot be released before its prerequisite work is completed."
                                        ),
                                        parties_involved=[p1.member_name, p2.member_name],
                                        evidence=[
                                            EvidenceItem(
                                                member_name=p1.member_name,
                                                quote=d1.source_quote,
                                                interpretation=f"Targeting {d1.milestone} on {d1.expected_deadline}.",
                                            ),
                                            EvidenceItem(
                                                member_name=p2.member_name,
                                                quote=d2.source_quote,
                                                interpretation=f"Believes launch/release is scheduled for {d2.expected_deadline}.",
                                            ),
                                        ],
                                        impact_description=(
                                            f"Direct delivery blocker. Releasing on {d2.expected_deadline} risks shipping incomplete "
                                            f"functionality or missing the target launch date."
                                        ),
                                    )
                                )
                                conflict_counter += 1

        # 2. Dynamic Testing / QA Unbudgeted Dependency Detection
        testers = [p for p in perspectives if any("test" in g.statement.lower() or "qa" in g.statement.lower() for g in p.goals)]
        launchers = [p for p in perspectives if any("launch" in g.statement.lower() or "release" in g.statement.lower() for g in p.goals)]

        for tester in testers:
            for launcher in launchers:
                if tester.member_name != launcher.member_name:
                    tester_quote = tester.key_quotes[0] if tester.key_quotes else "Complete testing before launch"
                    launcher_quote = launcher.key_quotes[0] if launcher.key_quotes else "Targeting launch date"

                    # Check if there is already a QA dependency conflict recorded
                    already_recorded = any(
                        c.conflict_type == ConflictType.INFORMATION_GAP and tester.member_name in c.parties_involved and launcher.member_name in c.parties_involved
                        for c in conflicts
                    )
                    if not already_recorded:
                        conflicts.append(
                            DetectedConflict(
                                conflict_id=f"CONF-{conflict_counter:02d}",
                                title=f"Unbudgeted Quality Assurance Dependency Between {tester.member_name} and {launcher.member_name}",
                                conflict_type=ConflictType.INFORMATION_GAP,
                                category=ConflictCategory.UNRESOLVED_DEPENDENCY,
                                severity=ConflictSeverity.MEDIUM,
                                severity_reasoning=(
                                    f"{tester.member_name} requires testing to finish before release, but no testing timeframe "
                                    f"or buffer is explicitly allocated in {launcher.member_name}'s launch expectations."
                                ),
                                parties_involved=[tester.member_name, launcher.member_name],
                                evidence=[
                                    EvidenceItem(
                                        member_name=tester.member_name,
                                        quote=tester_quote,
                                        interpretation="States that complete testing is a mandatory prerequisite prior to release.",
                                    ),
                                    EvidenceItem(
                                        member_name=launcher.member_name,
                                        quote=launcher_quote,
                                        interpretation="Expects application launch without explicit testing window allocation.",
                                    ),
                                ],
                                impact_description="High risk of launching untested features or missing the target launch window when defects arise.",
                            )
                        )
                        conflict_counter += 1

        # 3. Dynamic Compatible Differences
        if len(perspectives) >= 2:
            roles = [p.member_name for p in perspectives]
            compatible_diffs.append(
                f"Teammates ({', '.join(roles)}) share a common commitment to project success; individual differences "
                "in functional focus (e.g. implementation vs quality assurance vs scheduling) are complementary when aligned into a staged delivery workflow."
            )

        # 4. Critical Information Gaps
        if not any(d for p in perspectives for d in p.deadlines if "test" in d.milestone.lower()):
            gaps.append("Calendar duration and specific dates for testing/QA sign-off remain undefined.")
        if not any(d for p in perspectives for d in p.deadlines if "backend" in d.milestone.lower()):
            gaps.append("Backend integration and deployment milestones were not explicitly specified in member statements.")

        synthesis_summary = (
            f"Detected {len(conflicts)} alignment issue(s) across {len(perspectives)} participants. "
            + (f"Identified {len([c for c in conflicts if c.severity == ConflictSeverity.HIGH])} blocking deadline contradiction(s)." if conflicts else "No severe contradictions detected.")
        )

        return ConflictDetectionOutput(
            conflicts=conflicts,
            compatible_differences=compatible_diffs,
            critical_information_gaps=gaps,
            synthesis_summary=synthesis_summary,
        )
