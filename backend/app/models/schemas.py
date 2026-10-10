from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field, field_validator


# ==========================================
# Core Domain Schemas
# ==========================================

class TeamMemberBase(BaseModel):
    name: str = Field(..., description="Full name or alias of the team member")
    role: Optional[str] = Field(default=None, description="Role in team (e.g. Frontend, Backend, PM, QA)")
    email: Optional[str] = Field(default=None, description="Optional email address")


class TeamMemberCreate(TeamMemberBase):
    pass


class TeamMember(TeamMemberBase):
    id: str = Field(..., description="Unique ID for team member")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ProjectBase(BaseModel):
    title: str = Field(..., description="Project name")
    description: Optional[str] = Field(default=None, description="Project goals and overview")


class ProjectCreate(ProjectBase):
    pass


class Project(ProjectBase):
    id: str = Field(..., description="Unique project ID")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    members: List[TeamMember] = Field(default_factory=list)


class MemberResponseSubmit(BaseModel):
    member_name: str = Field(..., description="Name of the team member submitting perspective")
    raw_text: str = Field(..., description="Unstructured response or viewpoint from the teammate")
    source: str = Field(default="direct_submission", description="Source of submission (e.g. form, slack, direct)")


class MemberResponse(BaseModel):
    id: str = Field(..., description="Unique response ID")
    project_id: str = Field(..., description="Associated project ID")
    member_name: str = Field(..., description="Name of the team member")
    raw_text: str = Field(..., description="Unstructured response or viewpoint")
    source: str = Field(default="direct_submission")
    submitted_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ==========================================
# Agent 1: Perspective Analysis Schemas
# ==========================================

class GoalItem(BaseModel):
    statement: str = Field(..., description="Project goal identified from the member's response")
    source_quote: str = Field(..., description="Exact quote from the member supporting this goal")
    clarity: Literal["CLEAR", "AMBIGUOUS", "INFERRED"] = Field(
        default="CLEAR", description="Clarity level of the stated goal"
    )


class PriorityItem(BaseModel):
    priority_item: str = Field(..., description="Priority or top concern expressed")
    urgency_level: Literal["CRITICAL", "HIGH", "NORMAL", "LOW"] = Field(
        default="HIGH", description="Expressed urgency"
    )
    source_quote: str = Field(..., description="Verbatim statement showing priority")


class ResponsibilityItem(BaseModel):
    responsibility: str = Field(..., description="Responsibility or task mentioned")
    assigned_to: str = Field(..., description="Who the member believes is responsible")
    source_quote: str = Field(..., description="Verbatim statement from the member")


class DeadlineItem(BaseModel):
    milestone: str = Field(..., description="Milestone or task deadline refers to")
    expected_deadline: str = Field(..., description="Deadline date/timeframe mentioned (e.g. 'Thursday', 'Friday')")
    is_tentative: bool = Field(default=False, description="Whether the member phrased this as an assumption or tentative")
    source_quote: str = Field(..., description="Verbatim statement containing the deadline")


class ExtractedPerspective(BaseModel):
    member_name: str = Field(..., description="Name of the team member")
    goals: List[GoalItem] = Field(default_factory=list, description="Extracted project goals")
    priorities: List[PriorityItem] = Field(default_factory=list, description="Extracted priorities")
    responsibilities: List[ResponsibilityItem] = Field(default_factory=list, description="Identified responsibilities")
    deadlines: List[DeadlineItem] = Field(default_factory=list, description="Expected deadlines or timelines")
    ambiguities_or_missing_details: List[str] = Field(
        default_factory=list,
        description="Missing details, unstated dependencies, or ambiguous points that are NOT invented",
    )
    key_quotes: List[str] = Field(default_factory=list, description="Key verbatim quotes from the member")


class PerspectiveAnalysisOutput(BaseModel):
    perspectives: List[ExtractedPerspective] = Field(
        ..., description="List of structured perspectives for each team member"
    )
    total_members_analyzed: int = Field(default=0, description="Count of members analyzed")
    overall_summary: str = Field(..., description="Concise objective summary of all individual inputs")
    identified_gaps: List[str] = Field(
        default_factory=list,
        description="Cross-cutting areas where information was completely missing from all members",
    )

    @field_validator("total_members_analyzed", mode="before")
    def set_total(cls, v, values):
        if not v and "perspectives" in values.data:
            return len(values.data["perspectives"])
        return v


# ==========================================
# Agent 2: Conflict Detection Schemas
# ==========================================

class ConflictType(str, Enum):
    DEADLINE_CONTRADICTION = "DEADLINE_CONTRADICTION"
    GOAL_INCOMPATIBILITY = "GOAL_INCOMPATIBILITY"
    PRIORITY_MISMATCH = "PRIORITY_MISMATCH"
    RESPONSIBILITY_OVERLAP_OR_GAP = "RESPONSIBILITY_OVERLAP_OR_GAP"
    INFORMATION_GAP = "INFORMATION_GAP"
    PROCESS_MISALIGNMENT = "PROCESS_MISALIGNMENT"


class ConflictSeverity(str, Enum):
    HIGH = "HIGH"        # Impossible to satisfy simultaneously, blocking launch/milestone
    MEDIUM = "MEDIUM"    # Significant friction, potential quality or timeline slip
    LOW = "LOW"          # Preference difference or minor nuance that can easily coexist


class ConflictCategory(str, Enum):
    DIRECT_DISAGREEMENT = "DIRECT_DISAGREEMENT"        # Mutually exclusive positions
    COMPATIBLE_DIFFERENCE = "COMPATIBLE_DIFFERENCE"    # Divergent focus that can be synthesized
    UNRESOLVED_DEPENDENCY = "UNRESOLVED_DEPENDENCY"    # Critical missing sequence or dependency


class EvidenceItem(BaseModel):
    member_name: str = Field(..., description="Team member who made the statement")
    quote: str = Field(..., description="Exact verbatim quote from the member's input")
    interpretation: str = Field(..., description="Factual interpretation of what the quote asserts")


class DetectedConflict(BaseModel):
    conflict_id: str = Field(..., description="Unique identifier for the conflict (e.g. 'CONF-1')")
    title: str = Field(..., description="Short descriptive title of the conflict")
    conflict_type: ConflictType = Field(..., description="Categorization of the conflict type")
    category: ConflictCategory = Field(..., description="Whether this is a direct disagreement or compatible difference")
    severity: ConflictSeverity = Field(..., description="Assigned severity rating")
    severity_reasoning: str = Field(
        ..., description="Documented rationale explaining why this severity was assigned"
    )
    parties_involved: List[str] = Field(..., description="List of member names whose statements are in conflict")
    evidence: List[EvidenceItem] = Field(..., description="Citations and original quotes supporting this finding")
    impact_description: str = Field(..., description="Potential impact on the project if left unresolved")


class ConflictDetectionOutput(BaseModel):
    conflicts: List[DetectedConflict] = Field(..., description="List of detected conflicts and misalignments")
    compatible_differences: List[str] = Field(
        default_factory=list,
        description="Differences in focus or emphasis that are compatible and not in conflict",
    )
    critical_information_gaps: List[str] = Field(
        default_factory=list,
        description="Missing facts or prerequisites that prevent clear decision-making (e.g. testing duration)",
    )
    synthesis_summary: str = Field(..., description="High-level summary of the team's alignment status")


# ==========================================
# Agent 3: Resolution & Synthesis Schemas
# ==========================================

class ResolutionOption(BaseModel):
    option_id: str = Field(..., description="Identifier for option (e.g. 'OPT-A')")
    title: str = Field(..., description="Short title of the proposed approach")
    description: str = Field(..., description="Detailed description of this solution")
    pros: List[str] = Field(..., description="Advantages of this option")
    cons: List[str] = Field(..., description="Disadvantages or trade-offs")
    compromise_notes: str = Field(..., description="How this accommodates different members' perspectives")


class ProposedResolution(BaseModel):
    resolution_id: str = Field(..., description="Unique ID for this resolution (e.g. 'RES-1')")
    conflict_id: str = Field(..., description="Reference to the conflict being addressed")
    conflict_title: str = Field(..., description="Title of the corresponding conflict")
    recommended_solution: str = Field(..., description="Primary recommended compromise or solution")
    reasoning: str = Field(..., description="Clear explanation of the reasoning behind this recommendation")
    alternative_options: List[ResolutionOption] = Field(
        default_factory=list, description="Alternative options for the team to consider"
    )
    impacted_members: List[str] = Field(..., description="Members who must agree or be consulted")
    unresolved_questions_for_team: List[str] = Field(
        ..., description="Specific questions the team must answer to finalize a decision"
    )
    # CRITICAL: AI recommendations are ALWAYS proposals, NEVER auto-approved
    status: Literal["PROPOSED"] = Field(
        default="PROPOSED",
        description="Status is strictly PROPOSED until approved by human team members",
    )


class SynthesisReport(BaseModel):
    report_id: str = Field(..., description="Unique synthesis report ID")
    project_id: str = Field(default="", description="Associated project ID")
    executive_summary: str = Field(..., description="Executive summary of the alignment situation")
    alignment_score: float = Field(
        ..., ge=0.0, le=100.0, description="Estimated alignment index (0-100, where 100 is perfectly aligned)"
    )
    key_findings: List[str] = Field(..., description="Key findings from the multi-agent analysis")
    proposed_resolutions: List[ProposedResolution] = Field(
        ..., description="Proposed solutions for team discussion"
    )
    human_action_items: List[str] = Field(
        ..., description="Explicit actions and decisions required from human teammates"
    )
    disclaimer: str = Field(
        default="All resolutions are AI-generated proposals and require explicit human team approval before becoming commitments.",
        description="Governance notice stating proposals are not final decisions",
    )
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ==========================================
# Full Multi-Agent Workflow Result
# ==========================================

class AlignmentWorkflowResult(BaseModel):
    workflow_id: str = Field(..., description="Unique execution ID")
    project_id: str = Field(..., description="Project ID")
    perspectives_output: PerspectiveAnalysisOutput = Field(..., description="Output from Agent 1 (Perspective)")
    conflicts_output: ConflictDetectionOutput = Field(..., description="Output from Agent 2 (Conflict)")
    synthesis_output: SynthesisReport = Field(..., description="Output from Agent 3 (Resolution)")
    intermediate_results: Dict[str, Any] = Field(
        default_factory=dict, description="Raw intermediate results for debugging and traceability"
    )
    execution_metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Execution timing, model used, and trace metadata"
    )


# ==========================================
# Human Decisions & Approvals Schemas
# ==========================================

class DecisionStatus(str, Enum):
    PROPOSED = "PROPOSED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    MODIFIED = "MODIFIED"


class DecisionActionRequest(BaseModel):
    resolution_id: str = Field(..., description="ID of the resolution to act upon")
    action: Literal["APPROVE", "REJECT", "MODIFY"] = Field(..., description="Action to take")
    decision_text: Optional[str] = Field(
        default=None, description="Official agreed commitment text (required if MODIFY or if customized)"
    )
    decided_by: str = Field(..., description="Name or ID of team member approving/rejecting")
    notes: Optional[str] = Field(default=None, description="Notes on why the decision was taken")


class ConfirmedDecision(BaseModel):
    id: str = Field(..., description="Unique decision ID")
    project_id: str = Field(..., description="Project ID")
    resolution_id: str = Field(..., description="Resolution ID that this decision was based on")
    status: DecisionStatus = Field(..., description="Final status (APPROVED, REJECTED, MODIFIED)")
    decision_text: str = Field(..., description="Official binding team commitment text")
    decided_by: str = Field(..., description="Team member who recorded the decision")
    decided_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    notes: Optional[str] = Field(default=None)
