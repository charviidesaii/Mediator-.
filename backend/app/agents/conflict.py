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
import re
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
    ExtractedPerspective,
    PerspectiveAnalysisOutput,
)

logger = logging.getLogger(__name__)

CONFLICT_AGENT_INSTRUCTION = """
You are the Conflict Detection Agent on an AI Team Alignment Platform.
Your mission is to objectively compare structured team member perspectives and systematically identify misalignments, contradictions, and information gaps.

Core Responsibilities:
1. Systematically compare all team members' goals, priorities, responsibilities, and deadlines across all participants.
2. Detect specific misalignments:
   - Contradictory Deadlines: When members expect different completion dates for the same project/milestone (e.g. Saturday vs Sunday), or when one milestone is scheduled before its required dependency (e.g. Launching on Thursday before Friday completion). Categorize as DEADLINE_CONTRADICTION.
   - Unclear or Overlapping Responsibilities: Contradictory assumptions of task ownership (e.g. Member A believes Member B owns deployment, while Member B believes Member A owns it; or unassigned critical responsibilities). Categorize as RESPONSIBILITY_OVERLAP_OR_GAP.
   - Incompatible Goals: Objectives that cannot simultaneously succeed given current resource/time boundaries. Categorize as GOAL_INCOMPATIBILITY.
   - Priority Mismatches: Conflicting urgency or order of operations. Categorize as PRIORITY_MISMATCH.
   - Information Gaps: Crucial unstated dependencies (e.g. testing schedule unspecified). Categorize as INFORMATION_GAP.
3. DISTINGUISH DISAGREEMENTS FROM COMPATIBLE DIFFERENCES:
   - DIRECT_DISAGREEMENT: Mutually exclusive constraints that cannot coexist without compromise.
   - COMPATIBLE_DIFFERENCE: Non-conflicting variations in focus or responsibility that complement each other.
   - Document compatible differences in `compatible_differences`.
4. EVIDENCE & ATTRIBUTION:
   - Every detected conflict MUST cite the exact statements/quotes from the team members in the `evidence` field.
   - Explicitly list all `parties_involved`.
5. SEVERITY CRITERIA:
   - HIGH: Blocking contradiction; physically or logically impossible to achieve without failure (e.g., launching an unbuilt or untested product, or unowned critical deployment).
   - MEDIUM: Significant friction; timeline compression or unclarified dependencies that jeopardize project quality or team morale.
   - LOW: Minor difference in preference, terminology, or non-critical sequencing.
   - You MUST explain the rationale in `severity_reasoning`.
6. GROUPING & GOVERNANCE:
   - Group duplicate findings about the same task, milestone, or deliverable into a single issue.
   - NEVER create self-conflicts where an individual is in conflict with themselves (e.g. "Charvi vs. Charvi"). Every conflict must involve at least 2 distinct team members.
   - Issue titles must be short, clear, and at most 60 characters.

You must respond ONLY with structured JSON matching the ConflictDetectionOutput schema.
""".strip()


def clean_issue_title(title: str, max_chars: int = 60) -> str:
    """Produces a concise, descriptive issue title under max_chars without technical jargon."""
    t = (title or "").strip()
    t = re.sub(r"\s*\((?:CONF|RES)[^)]*\)", "", t)
    # Strip trailing " Between X and Y" or " across X, Y"
    t = re.sub(r"\s+(?:Between|between)\s+[A-Za-z0-9\s.,]+(?:\s+and\s+[A-Za-z0-9\s.,]+)*$", "", t)
    t = re.sub(r"\s+across\s+[A-Za-z0-9\s.,]+$", "", t, flags=re.IGNORECASE)

    # Clean technical jargon from title
    t = re.sub(r"\bQuality\s+Assurance\b", "Testing", t, flags=re.IGNORECASE)
    t = re.sub(r"\bQA\b", "Testing", t)

    if ":" in t:
        parts = [p.strip() for p in t.split(":", 1)]
        prefix, suffix = parts[0], parts[1]
        # If suffix is "Person (Day) vs Person (Day)"
        if " vs " in suffix.lower() and ("(" in suffix or any(d in suffix.lower() for d in ["saturday", "sunday", "friday", "thursday", "wednesday", "tuesday", "monday"])):
            t = prefix
        else:
            suffix_clean = re.sub(r"\s+(?:Between|between)\s+.*$", "", suffix)
            candidate = f"{prefix}: {suffix_clean}".strip()
            if len(candidate) <= max_chars:
                t = candidate
            elif len(prefix) <= max_chars:
                t = prefix

    if len(t) > max_chars:
        t = t[:max_chars].rsplit(" ", 1)[0].rstrip(" -:,")
    return t


def clean_and_group_conflicts(conflicts: List[DetectedConflict]) -> List[DetectedConflict]:
    """Filters self-conflicts and groups duplicate findings about the same task into one distinct issue."""
    if not conflicts:
        return []

    # 1. Filter out self-conflicts (e.g. Charvi vs Charvi)
    valid_conflicts: List[DetectedConflict] = []
    for c in conflicts:
        unique_parties = set(p.strip().lower() for p in c.parties_involved if p.strip())
        if len(unique_parties) < 2:
            continue

        tl = (c.title or "").lower()
        if " vs " in tl:
            parts = [s.strip() for s in tl.split(" vs ", 1)]
            if len(parts) == 2 and parts[0] == parts[1]:
                continue
            first_name = parts[0].split("(")[0].strip()
            second_name = parts[1].split("(")[0].strip()
            if first_name and first_name == second_name:
                continue

        if "between " in tl and " and " in tl:
            after_between = tl.split("between ", 1)[1]
            between_parts = [s.strip() for s in after_between.split(" and ", 1)]
            if len(between_parts) == 2 and between_parts[0] == between_parts[1]:
                continue

        valid_conflicts.append(c)

    # 2. Group duplicate conflicts by normalized issue category and task domain
    grouped_buckets: Dict[str, List[DetectedConflict]] = {}
    for c in valid_conflicts:
        tl = (c.title or "").lower()
        c_type = c.conflict_type.value if hasattr(c.conflict_type, "value") else str(c.conflict_type)

        if c_type == "DEADLINE_CONTRADICTION" or "deadline" in tl or "completion" in tl or "schedule" in tl:
            if any(k in tl for k in ["launch", "release", "presentation", "demo", "target deadline", "readiness", "completion"]):
                group_key = "deadline:project_launch"
            else:
                group_key = "deadline:milestone_sequence"
        elif c_type == "RESPONSIBILITY_OVERLAP_OR_GAP" or "ownership" in tl or "responsibility" in tl:
            domain = "responsibility:task_ownership"
            for d in ["frontend", "backend", "integration", "deployment", "quality assurance", "testing", "design", "ui"]:
                if d in tl:
                    domain = f"responsibility:{d}"
                    break
            group_key = domain
        elif c_type == "INFORMATION_GAP" or "quality assurance" in tl or "testing" in tl:
            group_key = "gap:testing_buffer"
        elif "scope" in tl or "recommendation" in tl:
            group_key = "scope:feature_scope"
        else:
            cat_val = c.category.value if hasattr(c.category, "value") else str(c.category)
            group_key = f"other:{c_type}:{cat_val}"

        grouped_buckets.setdefault(group_key, []).append(c)

    distinct_conflicts: List[DetectedConflict] = []
    conflict_idx = 1
    severity_order = {ConflictSeverity.HIGH: 3, ConflictSeverity.MEDIUM: 2, ConflictSeverity.LOW: 1}

    for group_key, bucket in grouped_buckets.items():
        primary = bucket[0]
        # Union parties
        all_parties: List[str] = []
        for c in bucket:
            for p in c.parties_involved:
                if p not in all_parties:
                    all_parties.append(p)

        # Union evidence without duplicate quotes
        all_evidence: List[EvidenceItem] = []
        seen_quotes = set()
        for c in bucket:
            for ev in c.evidence:
                quote_key = (ev.member_name.lower().strip(), ev.quote.strip())
                if quote_key not in seen_quotes:
                    seen_quotes.add(quote_key)
                    all_evidence.append(ev)

        # Max severity among grouped items
        max_sev = max(bucket, key=lambda c: severity_order.get(c.severity, 1)).severity

        # Clean title <= 60 chars
        clean_title = clean_issue_title(primary.title)
        if len(clean_title) > 60:
            clean_title = clean_title[:60].rsplit(" ", 1)[0].rstrip(" -:,")

        parties_str = ", ".join(all_parties)
        if len(bucket) > 1:
            reasoning = f"Multiple teammates ({parties_str}) have misaligned expectations regarding {clean_title.lower()}."
            impact = f"Blocks coordinated delivery between {parties_str} without team alignment."
        else:
            reasoning = primary.severity_reasoning
            impact = primary.impact_description

        distinct_conflicts.append(
            DetectedConflict(
                conflict_id=f"CONF-{conflict_idx:02d}",
                title=clean_title,
                conflict_type=primary.conflict_type,
                category=primary.category,
                severity=max_sev,
                severity_reasoning=reasoning,
                parties_involved=all_parties,
                evidence=all_evidence,
                impact_description=impact,
            )
        )
        conflict_idx += 1

    return distinct_conflicts


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
        self.last_execution_mode: str = "MOCK_DETERMINISTIC"
        if self.client is None and settings.active_api_key:
            self.client = Client(api_key=settings.active_api_key)

    async def detect_conflicts(
        self, perspective_data: PerspectiveAnalysisOutput
    ) -> ConflictDetectionOutput:
        """Analyzes structured perspective output and detects conflicts."""
        if not perspective_data.perspectives or len(perspective_data.perspectives) < 2:
            self.last_execution_mode = "MOCK_DETERMINISTIC"
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
            self.last_execution_mode = "MOCK_DETERMINISTIC"
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
                    self.last_execution_mode = "LIVE_GEMINI"
                    out = ConflictDetectionOutput.model_validate(data)
                    out.conflicts = clean_and_group_conflicts(out.conflicts)
                    return out

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
                self.last_execution_mode = "LIVE_GEMINI"
                out = ConflictDetectionOutput.model_validate(data)
                out.conflicts = clean_and_group_conflicts(out.conflicts)
                return out
            else:
                raise ValueError("Empty response received from Gemini model.")
        except Exception as e:
            logger.error("Error executing Google ADK / Gemini for Conflict Detection: %s", e)
            if settings.app_env == "development" or settings.mock_llm:
                self.last_execution_mode = f"MOCK_FALLBACK ({type(e).__name__})"
                logger.warning(f"Falling back to deterministic conflict detection after error: {e}")
                return self._mock_detect(perspective_data)
            raise

    def _mock_detect(
        self, perspective_data: PerspectiveAnalysisOutput
    ) -> ConflictDetectionOutput:
        """Generalized deterministic conflict detection for arbitrary participants."""
        conflicts: List[DetectedConflict] = []
        compatible_diffs: List[str] = []
        gaps: List[str] = list(perspective_data.identified_gaps)

        # Consolidate perspectives by unique member name so multi-message users do not generate self-conflicts
        merged_perspectives: Dict[str, ExtractedPerspective] = {}
        for p in perspective_data.perspectives:
            key = p.member_name.strip().lower()
            if key not in merged_perspectives:
                merged_perspectives[key] = ExtractedPerspective(
                    member_name=p.member_name.strip(),
                    goals=list(p.goals),
                    priorities=list(p.priorities),
                    responsibilities=list(p.responsibilities),
                    deadlines=list(p.deadlines),
                    ambiguities_or_missing_details=list(p.ambiguities_or_missing_details),
                    key_quotes=list(p.key_quotes),
                )
            else:
                existing = merged_perspectives[key]
                existing.goals.extend(p.goals)
                existing.priorities.extend(p.priorities)
                existing.responsibilities.extend(p.responsibilities)
                existing.deadlines.extend(p.deadlines)
                existing.ambiguities_or_missing_details.extend(p.ambiguities_or_missing_details)
                for q in p.key_quotes:
                    if q not in existing.key_quotes:
                        existing.key_quotes.append(q)

        perspectives = list(merged_perspectives.values())
        if len(perspectives) < 2:
            return ConflictDetectionOutput(
                conflicts=[],
                compatible_differences=["Single team member response or no perspectives provided."],
                critical_information_gaps=perspective_data.identified_gaps,
                synthesis_summary="Insufficient distinct perspectives to compare for team alignment (at least 2 teammates required).",
            )

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

                            # Determine if one milestone is launch and the other is prerequisite development (frontend/backend/qa)
                            is_p1_launch = "launch" in d1.milestone.lower() or "release" in d1.milestone.lower()
                            is_p2_launch = "launch" in d2.milestone.lower() or "release" in d2.milestone.lower()
                            is_p1_prereq = any(k in d1.milestone.lower() for k in ["frontend", "backend", "test", "qa", "api"])
                            is_p2_prereq = any(k in d2.milestone.lower() for k in ["frontend", "backend", "test", "qa", "api"])

                            # Case A: p1 expects launch before p2 finishes prerequisite development
                            if is_p1_launch and is_p2_prereq and rank1 < rank2:
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

                            # Case B: p2 expects launch before p1 finishes prerequisite development
                            elif is_p2_launch and is_p1_prereq and rank2 < rank1:
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

                            # Case C: Direct Target Deadline Disagreement (differing milestone targets)
                            elif rank1 != rank2:
                                already_has_deadline_conflict = any(
                                    c.conflict_type == ConflictType.DEADLINE_CONTRADICTION
                                    and p1.member_name in c.parties_involved
                                    and p2.member_name in c.parties_involved
                                    for c in conflicts
                                )
                                if not already_has_deadline_conflict:
                                    conflicts.append(
                                        DetectedConflict(
                                            conflict_id=f"CONF-{conflict_counter:02d}",
                                            title=f"Conflicting Target Deadlines: {p1.member_name} ({d1.expected_deadline}) vs {p2.member_name} ({d2.expected_deadline})",
                                            conflict_type=ConflictType.DEADLINE_CONTRADICTION,
                                            category=ConflictCategory.DIRECT_DISAGREEMENT,
                                            severity=ConflictSeverity.HIGH,
                                            severity_reasoning=(
                                                f"Direct deadline disagreement: {p1.member_name} expects {d1.milestone} on {d1.expected_deadline}, "
                                                f"whereas {p2.member_name} expects {d2.milestone} on {d2.expected_deadline}. "
                                                "The team does not have a shared commitment for completion timing."
                                            ),
                                            parties_involved=[p1.member_name, p2.member_name],
                                            evidence=[
                                                EvidenceItem(
                                                    member_name=p1.member_name,
                                                    quote=d1.source_quote,
                                                    interpretation=f"Expects deadline on {d1.expected_deadline}.",
                                                ),
                                                EvidenceItem(
                                                    member_name=p2.member_name,
                                                    quote=d2.source_quote,
                                                    interpretation=f"Expects deadline on {d2.expected_deadline}.",
                                                ),
                                            ],
                                            impact_description=(
                                                f"Timeline friction and lack of synchronized delivery targets between "
                                                f"{p1.member_name} and {p2.member_name}."
                                            ),
                                        )
                                    )
                                    conflict_counter += 1

                # Dynamic Responsibility & Ownership Confusion Search between p1 and p2
                for r1 in p1.responsibilities:
                    for r2 in p2.responsibilities:
                        # Compare responsibilities of the same domain (e.g. deployment, testing, api)
                        if r1.responsibility.lower() == r2.responsibility.lower():
                            # If they assign to different people, or mutual finger-pointing
                            assigned1 = r1.assigned_to.strip().lower()
                            assigned2 = r2.assigned_to.strip().lower()
                            p1_name = p1.member_name.strip().lower()
                            p2_name = p2.member_name.strip().lower()

                            is_mismatch = (
                                assigned1 != assigned2
                                or (assigned1 == p2_name and assigned2 == p1_name)
                                or (assigned1 not in [p1_name, p2_name] and assigned2 not in [p1_name, p2_name] and assigned1 != assigned2)
                            )
                            if is_mismatch:
                                already_has_resp_conflict = any(
                                    c.conflict_type == ConflictType.RESPONSIBILITY_OVERLAP_OR_GAP
                                    and p1.member_name in c.parties_involved
                                    and p2.member_name in c.parties_involved
                                    and r1.responsibility.lower() in c.title.lower()
                                    for c in conflicts
                                )
                                if not already_has_resp_conflict:
                                    conflicts.append(
                                        DetectedConflict(
                                            conflict_id=f"CONF-{conflict_counter:02d}",
                                            title=f"Unclear Task Ownership: {r1.responsibility} Between {p1.member_name} and {p2.member_name}",
                                            conflict_type=ConflictType.RESPONSIBILITY_OVERLAP_OR_GAP,
                                            category=ConflictCategory.DIRECT_DISAGREEMENT,
                                            severity=ConflictSeverity.HIGH,
                                            severity_reasoning=(
                                                f"Ownership confusion: {p1.member_name} assumes {r1.assigned_to} is responsible for {r1.responsibility}, "
                                                f"while {p2.member_name} assumes {r2.assigned_to} is responsible for it. "
                                                f"Neither teammate has taken explicit verified accountability for {r1.responsibility}."
                                            ),
                                            parties_involved=[p1.member_name, p2.member_name],
                                            evidence=[
                                                EvidenceItem(
                                                    member_name=p1.member_name,
                                                    quote=r1.source_quote,
                                                    interpretation=f"Believes {r1.assigned_to} owns {r1.responsibility}.",
                                                ),
                                                EvidenceItem(
                                                    member_name=p2.member_name,
                                                    quote=r2.source_quote,
                                                    interpretation=f"Believes {r2.assigned_to} owns {r2.responsibility}.",
                                                ),
                                            ],
                                            impact_description=(
                                                f"Critical delivery blocker: without a designated single owner, "
                                                f"{r1.responsibility} may be completely dropped or delayed."
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

        # Clean self-conflicts and group duplicate findings
        cleaned_conflicts = clean_and_group_conflicts(conflicts)

        synthesis_summary = (
            f"Detected {len(cleaned_conflicts)} distinct alignment issue(s) across {len(perspectives)} participants. "
            + (f"Identified {len([c for c in cleaned_conflicts if c.severity == ConflictSeverity.HIGH])} blocking contradiction(s)." if cleaned_conflicts else "No severe contradictions detected.")
        )

        return ConflictDetectionOutput(
            conflicts=cleaned_conflicts,
            compatible_differences=compatible_diffs,
            critical_information_gaps=gaps,
            synthesis_summary=synthesis_summary,
        )
