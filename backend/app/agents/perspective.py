"""Perspective Analysis Agent.

Agent 1 in the multi-agent alignment workflow.
Uses Google ADK to extract structured goals, priorities, responsibilities,
deadlines, and missing details from unstructured teammate statements.
Preserves original quotes and attributes every finding to its author.
"""

import json
import logging
from typing import Any, Dict, List, Optional
from google.adk.agents import Agent
from google.genai import Client, types

from app.config import settings
from app.models.schemas import (
    DeadlineItem,
    ExtractedPerspective,
    GoalItem,
    MemberResponse,
    PerspectiveAnalysisOutput,
    PriorityItem,
    ResponsibilityItem,
)

logger = logging.getLogger(__name__)

PERSPECTIVE_AGENT_INSTRUCTION = """
You are the Perspective Analysis Agent on an AI Team Alignment Platform.
Your purpose is to deeply and objectively understand individual teammates' perspectives from their submitted statements.

Core Responsibilities:
1. Process independently submitted teammate responses with complete neutrality.
2. Extract the following structured elements for each teammate:
   - Goals: What does this person want to accomplish?
   - Priorities: What tasks or outcomes do they consider most urgent or important?
   - Responsibilities: Who do they believe is responsible for what work?
   - Deadlines & Timelines: What specific days, dates, or sequences do they expect?
3. PRESERVE ORIGINAL MEANING & EVIDENCE:
   - For every extracted item, include the exact verbatim quote from the member's statement in `source_quote`.
   - Never twist, exaggerate, or omit nuance from teammate words.
4. ATTRIBUTE TO SOURCE:
   - Explicitly associate all goals, priorities, and deadlines with the specific team member who stated them.
5. IDENTIFY AMBIGUITIES & MISSING DETAILS:
   - If a member does not specify a deadline, testing plan, owner, or deliverable scope, explicitly record it in `ambiguities_or_missing_details`.
   - NEVER invent or hallucinate information that was not stated.
6. Provide an objective `overall_summary` and list cross-cutting `identified_gaps`.

You must respond ONLY with structured JSON matching the PerspectiveAnalysisOutput schema.
""".strip()


def create_perspective_adk_agent() -> Agent:
    """Creates the Google ADK Agent instance for Perspective Analysis."""
    return Agent(
        name="perspective_analysis_agent",
        description="Analyzes individual teammate responses to extract structured goals, priorities, deadlines, and gaps.",
        model=settings.gemini_model,
        instruction=PERSPECTIVE_AGENT_INSTRUCTION,
        output_schema=PerspectiveAnalysisOutput,
        output_key="perspectives",
    )


class PerspectiveAnalysisService:
    """Service to execute Perspective Analysis using Google ADK and Gemini API."""

    def __init__(self, client: Optional[Client] = None):
        self.adk_agent = create_perspective_adk_agent()
        self.client = client
        if self.client is None and settings.active_api_key:
            self.client = Client(api_key=settings.active_api_key)

    async def analyze(
        self, responses: List[MemberResponse]
    ) -> PerspectiveAnalysisOutput:
        """Processes submitted teammate responses and extracts structured perspectives."""
        if not responses:
            return PerspectiveAnalysisOutput(
                perspectives=[],
                total_members_analyzed=0,
                overall_summary="No responses were provided for analysis.",
                identified_gaps=["No team input data available."],
            )

        # Prepare formatted prompt payload
        inputs_payload = [
            {
                "member_name": r.member_name,
                "raw_text": r.raw_text,
                "source": r.source,
                "submitted_at": r.submitted_at.isoformat() if hasattr(r.submitted_at, "isoformat") else str(r.submitted_at),
            }
            for r in responses
        ]
        prompt = (
            f"Please analyze the following team members' independently submitted statements:\n"
            f"```json\n{json.dumps(inputs_payload, indent=2)}\n```\n\n"
            f"Extract each member's goals, priorities, responsibilities, deadlines, and missing details."
        )

        # If mock mode is forced or no Gemini API key is available, execute deterministic extraction
        if settings.mock_llm or not self.client:
            logger.info("Using deterministic Perspective Analysis logic (mock mode / no API key)")
            return self._mock_analyze(responses)

        # Live Gemini execution via google-genai / ADK schema
        try:
            config = types.GenerateContentConfig(
                system_instruction=PERSPECTIVE_AGENT_INSTRUCTION,
                response_mime_type="application/json",
                response_schema=PerspectiveAnalysisOutput,
                temperature=settings.agent_temperature,
            )
            response = self.client.models.generate_content(
                model=settings.gemini_model,
                contents=prompt,
                config=config,
            )
            if response.text:
                data = json.loads(response.text)
                return PerspectiveAnalysisOutput.model_validate(data)
            else:
                raise ValueError("Empty response received from Gemini model.")
        except Exception as e:
            logger.error("Error calling Gemini API for Perspective Analysis: %s", e)
            if settings.app_env == "development" or settings.mock_llm:
                logger.warning("Falling back to deterministic perspective extraction after error.")
                return self._mock_analyze(responses)
            raise

    def _mock_analyze(self, responses: List[MemberResponse]) -> PerspectiveAnalysisOutput:
        """Deterministic perspective extraction for test scenarios and offline development."""
        perspectives: List[ExtractedPerspective] = []

        for resp in responses:
            name = resp.member_name
            text = resp.raw_text.strip()
            text_lower = text.lower()

            goals: List[GoalItem] = []
            priorities: List[PriorityItem] = []
            responsibilities: List[ResponsibilityItem] = []
            deadlines: List[DeadlineItem] = []
            ambiguities: List[str] = []

            # 1. Deadline extraction
            for day in ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]:
                if day in text_lower:
                    cap_day = day.capitalize()
                    milestone = "Milestone / Deliverable"
                    if "frontend" in text_lower:
                        milestone = "Frontend Completion"
                    elif "launch" in text_lower:
                        milestone = "Full Application Launch"
                    elif "test" in text_lower:
                        milestone = "Testing Completion"

                    deadlines.append(
                        DeadlineItem(
                            milestone=milestone,
                            expected_deadline=cap_day,
                            is_tentative="thought" in text_lower or "think" in text_lower,
                            source_quote=text,
                        )
                    )

            # 2. Priority extraction
            if "priority" in text_lower or "focus" in text_lower or "first" in text_lower:
                priorities.append(
                    PriorityItem(
                        priority_item=text,
                        urgency_level="CRITICAL",
                        source_quote=text,
                    )
                )
            elif "before" in text_lower or "prerequisite" in text_lower:
                priorities.append(
                    PriorityItem(
                        priority_item=f"Prerequisite sequence: {text}",
                        urgency_level="HIGH",
                        source_quote=text,
                    )
                )
            else:
                priorities.append(
                    PriorityItem(
                        priority_item=text,
                        urgency_level="NORMAL",
                        source_quote=text,
                    )
                )

            # 3. Goals & Responsibilities
            if "frontend" in text_lower:
                goals.append(
                    GoalItem(
                        statement="Complete frontend interface",
                        source_quote=text,
                        clarity="CLEAR",
                    )
                )
                responsibilities.append(
                    ResponsibilityItem(
                        responsibility="Frontend development",
                        assigned_to=name,
                        source_quote=text,
                    )
                )
            if "launch" in text_lower:
                goals.append(
                    GoalItem(
                        statement="Launch the entire application",
                        source_quote=text,
                        clarity="CLEAR",
                    )
                )
                responsibilities.append(
                    ResponsibilityItem(
                        responsibility="Application deployment and launch",
                        assigned_to="Team",
                        source_quote=text,
                    )
                )
            if "test" in text_lower or "testing" in text_lower:
                goals.append(
                    GoalItem(
                        statement="Complete comprehensive testing before any launch",
                        source_quote=text,
                        clarity="CLEAR",
                    )
                )
                responsibilities.append(
                    ResponsibilityItem(
                        responsibility="Quality Assurance / Testing",
                        assigned_to=name if "i" in text_lower else "QA / Team",
                        source_quote=text,
                    )
                )

            # 4. Ambiguities & Missing Details (not invented, strictly noted)
            if "test" in text_lower and not any(day in text_lower for day in ["monday", "tuesday", "wednesday", "thursday", "friday"]):
                ambiguities.append("Testing duration and specific completion date are not specified.")
            if "launch" in text_lower and "frontend" not in text_lower and "test" not in text_lower:
                ambiguities.append("Launch scope does not explicitly mention prerequisite completion or testing window.")
            if "frontend" in text_lower and "backend" not in text_lower and "launch" not in text_lower:
                ambiguities.append("Frontend timeline does not mention integration with backend or final release date.")

            perspectives.append(
                ExtractedPerspective(
                    member_name=name,
                    goals=goals,
                    priorities=priorities,
                    responsibilities=responsibilities,
                    deadlines=deadlines,
                    ambiguities_or_missing_details=ambiguities,
                    key_quotes=[text],
                )
            )

        # Cross-cutting gaps
        has_testing_schedule = any(
            d.milestone == "Testing Completion" for p in perspectives for d in p.deadlines
        )
        cross_cutting_gaps = []
        if not has_testing_schedule:
            cross_cutting_gaps.append(
                "No explicit start date or duration was provided for application testing."
            )

        return PerspectiveAnalysisOutput(
            perspectives=perspectives,
            total_members_analyzed=len(perspectives),
            overall_summary=(
                f"Analyzed {len(perspectives)} teammate perspective(s). Identified core goals "
                "surrounding frontend completion, application launch timing, and pre-launch testing requirements."
            ),
            identified_gaps=cross_cutting_gaps,
        )
