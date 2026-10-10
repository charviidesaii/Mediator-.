"""Perspective Analysis Agent.

Agent 1 in the multi-agent alignment workflow.
Uses Google ADK to extract structured goals, priorities, responsibilities,
deadlines, and missing details from unstructured teammate statements.
Preserves original quotes and attributes every finding to its author.
Supports arbitrary team members and arbitrary statements.
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
1. Process independently submitted teammate responses with complete neutrality for any participant.
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

        # If mock mode is active or no Gemini API key is configured, run generalized deterministic analysis
        if not settings.is_live_gemini_available:
            logger.info("Perspective Analysis running in deterministic mode (no live Gemini key or mock enabled)")
            return self._mock_analyze(responses)

        # Live Google ADK / Gemini execution
        try:
            logger.info(f"Invoking Google ADK Perspective Agent with model: {settings.gemini_model}")
            if settings.use_adk_runner:
                # Genuine Google ADK execution via Runner and SessionService
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
                    return PerspectiveAnalysisOutput.model_validate(data)

            # Direct fallback if ADK runner stream is empty
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
            logger.error("Error executing Google ADK / Gemini for Perspective Analysis: %s", e)
            if settings.app_env == "development" or settings.mock_llm:
                logger.warning("Falling back to deterministic perspective extraction after error.")
                return self._mock_analyze(responses)
            raise

    def _mock_analyze(self, responses: List[MemberResponse]) -> PerspectiveAnalysisOutput:
        """Generalized deterministic perspective extraction for arbitrary participants."""
        perspectives: List[ExtractedPerspective] = []
        days_regex = re.compile(r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", re.IGNORECASE)

        for resp in responses:
            name = resp.member_name.strip()
            text = resp.raw_text.strip()
            text_lower = text.lower()

            goals: List[GoalItem] = []
            priorities: List[PriorityItem] = []
            responsibilities: List[ResponsibilityItem] = []
            deadlines: List[DeadlineItem] = []
            ambiguities: List[str] = []

            # 1. Dynamic Deadline Extraction for any day mentioned
            matched_days = days_regex.findall(text)
            if matched_days:
                for day in matched_days:
                    cap_day = day.capitalize()
                    milestone = "Target Milestone"
                    if "frontend" in text_lower or "ui" in text_lower:
                        milestone = "Frontend Completion"
                    elif "backend" in text_lower or "api" in text_lower:
                        milestone = "Backend / API Completion"
                    elif "launch" in text_lower or "release" in text_lower:
                        milestone = "Full Application Launch"
                    elif "test" in text_lower or "qa" in text_lower:
                        milestone = "Testing Completion"

                    deadlines.append(
                        DeadlineItem(
                            milestone=milestone,
                            expected_deadline=cap_day,
                            is_tentative="thought" in text_lower or "think" in text_lower or "maybe" in text_lower,
                            source_quote=text,
                        )
                    )

            # 2. Dynamic Priority Extraction
            if any(w in text_lower for w in ["priority", "first", "urgent", "critical", "must"]):
                priorities.append(
                    PriorityItem(
                        priority_item=text,
                        urgency_level="CRITICAL",
                        source_quote=text,
                    )
                )
            elif any(w in text_lower for w in ["before", "prerequisite", "require", "need to"]):
                priorities.append(
                    PriorityItem(
                        priority_item=f"Prerequisite requirement: {text}",
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

            # 3. Dynamic Goals & Responsibilities
            if "frontend" in text_lower or "ui" in text_lower:
                goals.append(
                    GoalItem(
                        statement="Complete frontend user interface",
                        source_quote=text,
                        clarity="CLEAR",
                    )
                )
                responsibilities.append(
                    ResponsibilityItem(
                        responsibility="Frontend delivery",
                        assigned_to=name,
                        source_quote=text,
                    )
                )
            if "backend" in text_lower or "api" in text_lower:
                goals.append(
                    GoalItem(
                        statement="Complete backend service and database APIs",
                        source_quote=text,
                        clarity="CLEAR",
                    )
                )
                responsibilities.append(
                    ResponsibilityItem(
                        responsibility="Backend engineering",
                        assigned_to=name,
                        source_quote=text,
                    )
                )
            if "launch" in text_lower or "release" in text_lower:
                goals.append(
                    GoalItem(
                        statement="Launch the application to users",
                        source_quote=text,
                        clarity="CLEAR",
                    )
                )
                responsibilities.append(
                    ResponsibilityItem(
                        responsibility="Release coordination",
                        assigned_to="Team",
                        source_quote=text,
                    )
                )
            if "test" in text_lower or "qa" in text_lower:
                goals.append(
                    GoalItem(
                        statement="Complete quality assurance and testing prior to release",
                        source_quote=text,
                        clarity="CLEAR",
                    )
                )
                responsibilities.append(
                    ResponsibilityItem(
                        responsibility="Quality Assurance",
                        assigned_to=name,
                        source_quote=text,
                    )
                )

            # Fallback goal if none of standard keywords matched
            if not goals:
                goals.append(
                    GoalItem(
                        statement=f"Deliver milestone stated by {name}",
                        source_quote=text,
                        clarity="INFERRED",
                    )
                )

            # 4. Dynamic Ambiguity & Missing Information Detection
            if ("test" in text_lower or "qa" in text_lower) and not matched_days:
                ambiguities.append(f"Testing duration and completion schedule not specified by {name}.")
            if ("launch" in text_lower) and not any(k in text_lower for k in ["test", "qa", "freeze"]):
                ambiguities.append(f"Release timeline stated by {name} does not explicitly allocate buffer for QA.")
            if not matched_days:
                ambiguities.append(f"No explicit calendar deadline provided in statement: '{text}'.")

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
        has_qa_schedule = any(
            d.milestone == "Testing Completion" for p in perspectives for d in p.deadlines
        )
        cross_cutting_gaps = []
        if not has_qa_schedule and any("test" in p.member_name.lower() or any("test" in g.statement.lower() for g in p.goals) for p in perspectives):
            cross_cutting_gaps.append(
                "Testing was raised as a requirement, but no calendar start date or duration was scheduled."
            )
        elif not any(p.deadlines for p in perspectives):
            cross_cutting_gaps.append("No explicit milestone deadlines were stated across submitted team viewpoints.")

        return PerspectiveAnalysisOutput(
            perspectives=perspectives,
            total_members_analyzed=len(perspectives),
            overall_summary=(
                f"Analyzed {len(perspectives)} teammate perspective(s) across participants: "
                f"{', '.join(p.member_name for p in perspectives)}. Extracted distinct milestone targets, "
                "individual priorities, and unaddressed dependency gaps."
            ),
            identified_gaps=cross_cutting_gaps,
        )
