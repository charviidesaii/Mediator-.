"""Conflict Detection Agent.

Agent 2 in the multi-agent alignment workflow.
Compares individual perspectives produced by Agent 1 to detect:
- Contradictory deadlines
- Incompatible goals
- Priority mismatches
- Missing information & dependencies

Distinguishes genuine disagreements from compatible differences and assigns
severity using strictly documented criteria.
"""

import json
import logging
from typing import Any, Dict, List, Optional
from google.adk.agents import Agent
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
1. Systematically compare all team members' goals, priorities, responsibilities, and deadlines.
2. Detect specific misalignments:
   - Contradictory Deadlines: When one milestone is scheduled before its required dependency (e.g., Launching Thursday while Frontend finishes Friday).
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
                synthesis_summary="Insufficient perspectives to compare for team alignment.",
            )

        prompt = (
            f"Analyze the following structured perspectives extracted from team members:\n"
            f"```json\n{perspective_data.model_dump_json(indent=2)}\n```\n\n"
            f"Identify all contradictions, incompatible deadlines, priority mismatches, and information gaps."
        )

        # If mock mode is forced or no Gemini API key is available, execute deterministic detection
        if settings.mock_llm or not self.client:
            logger.info("Using deterministic Conflict Detection logic (mock mode / no API key)")
            return self._mock_detect(perspective_data)

        # Live Gemini execution via google-genai / ADK schema
        try:
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
            logger.error("Error calling Gemini API for Conflict Detection: %s", e)
            if settings.app_env == "development" or settings.mock_llm:
                logger.warning("Falling back to deterministic conflict detection after error.")
                return self._mock_detect(perspective_data)
            raise

    def _mock_detect(
        self, perspective_data: PerspectiveAnalysisOutput
    ) -> ConflictDetectionOutput:
        """Deterministic conflict detection for test scenarios and offline development."""
        conflicts: List[DetectedConflict] = []
        compatible_diffs: List[str] = []
        gaps: List[str] = list(perspective_data.identified_gaps)

        # Collect members and their deadlines/priorities
        perspectives = perspective_data.perspectives
        member_map = {p.member_name: p for p in perspectives}

        # Check for Thursday vs Friday deadline contradiction (e.g. Sam vs Alex)
        alex = member_map.get("Alex")
        sam = member_map.get("Sam")
        taylor = member_map.get("Taylor")

        # 1. Timeline Contradiction: Alex (Friday Frontend) vs Sam (Thursday Full Launch)
        if alex and sam:
            alex_quote = alex.key_quotes[0] if alex.key_quotes else "Frontend by Friday"
            sam_quote = sam.key_quotes[0] if sam.key_quotes else "Launch on Thursday"

            conflicts.append(
                DetectedConflict(
                    conflict_id="CONF-01",
                    title="Deadline Sequence Inversion: Full Launch Precedes Frontend Completion",
                    conflict_type=ConflictType.DEADLINE_CONTRADICTION,
                    category=ConflictCategory.DIRECT_DISAGREEMENT,
                    severity=ConflictSeverity.HIGH,
                    severity_reasoning=(
                        "Logically and physically impossible: Sam expects the entire application "
                        "to launch on Thursday, but Alex has scheduled frontend completion for Friday. "
                        "The application cannot launch before its core user interface is ready."
                    ),
                    parties_involved=["Alex", "Sam"],
                    evidence=[
                        EvidenceItem(
                            member_name="Alex",
                            quote=alex_quote,
                            interpretation="States frontend will be completed by Friday.",
                        ),
                        EvidenceItem(
                            member_name="Sam",
                            quote=sam_quote,
                            interpretation="Believes the entire application was agreed to launch on Thursday.",
                        ),
                    ],
                    impact_description=(
                        "Immediate delivery blocker. Launching on Thursday would mean releasing without "
                        "a completed frontend, or failing to meet Sam's expected launch date."
                    ),
                )
            )

        # 2. Dependency Gap: Taylor (Testing before launch) vs Sam (Thursday launch without test buffer)
        if taylor and sam:
            taylor_quote = taylor.key_quotes[0] if taylor.key_quotes else "Complete testing before launching anything"
            sam_quote = sam.key_quotes[0] if sam.key_quotes else "Launch the entire application on Thursday"

            conflicts.append(
                DetectedConflict(
                    conflict_id="CONF-02",
                    title="Unscheduled Quality Assurance Dependency Prior to Launch",
                    conflict_type=ConflictType.INFORMATION_GAP,
                    category=ConflictCategory.UNRESOLVED_DEPENDENCY,
                    severity=ConflictSeverity.MEDIUM,
                    severity_reasoning=(
                        "Taylor requires testing to finish before any release, but no testing timeframe, "
                        "duration, or resource allocation is accounted for in Sam's launch plan."
                    ),
                    parties_involved=["Taylor", "Sam"],
                    evidence=[
                        EvidenceItem(
                            member_name="Taylor",
                            quote=taylor_quote,
                            interpretation="Requires complete testing as a hard prerequisite before launching anything.",
                        ),
                        EvidenceItem(
                            member_name="Sam",
                            quote=sam_quote,
                            interpretation="Plans full application launch for Thursday without explicit testing buffer.",
                        ),
                    ],
                    impact_description=(
                        "High risk of launching untested features or missing the Thursday launch window "
                        "once QA begins."
                    ),
                )
            )

        # 3. Compatible Differences
        if alex and taylor:
            compatible_diffs.append(
                "Alex's focus on frontend delivery and Taylor's focus on comprehensive testing are compatible, "
                "provided frontend deliverables are handed off to Taylor in a staged testing pipeline."
            )

        # 4. Critical Information Gaps
        gaps.append("Duration and scope of testing (smoke tests vs full regression) are undefined.")
        gaps.append("Backend completion status and integration milestones were not mentioned by any teammate.")

        return ConflictDetectionOutput(
            conflicts=conflicts,
            compatible_differences=compatible_diffs,
            critical_information_gaps=gaps,
            synthesis_summary=(
                f"Detected {len(conflicts)} core misalignment(s): a critical deadline clash "
                "between Alex and Sam (Friday frontend vs Thursday launch), and an unaddressed "
                "testing dependency raised by Taylor."
            ),
        )
