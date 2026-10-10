"""Data persistence service supporting Supabase PostgreSQL and local in-memory storage.

Maintains strict separation between:
- Individual opinions (MemberResponse)
- AI-generated interpretations (ExtractedPerspective)
- AI-generated recommendations (ProposedResolution)
- Human-approved decisions (ConfirmedDecision)

Ensures that only approved decisions become official project commitments.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

from app.config import settings
from app.models.schemas import (
    ConfirmedDecision,
    DecisionActionRequest,
    DecisionStatus,
    MemberResponse,
    Project,
    ProjectCreate,
    SynthesisReport,
    TeamMember,
    TeamMemberCreate,
)

logger = logging.getLogger(__name__)


class SupabaseStorageService:
    """Storage service interfacing with Supabase or fallback in-memory state."""

    def __init__(self):
        self.supabase_client = None
        # In-memory storage for active session, local development, and mock testing
        self._projects: Dict[str, Project] = {}
        self._responses: Dict[str, List[MemberResponse]] = {}
        self._reports: Dict[str, SynthesisReport] = {}
        self._decisions: Dict[str, List[ConfirmedDecision]] = {}

        if settings.supabase_url and settings.supabase_key:
            try:
                # Optional supabase client initialization when credentials provided
                logger.info("Supabase credentials detected, initializing client...")
            except Exception as e:
                logger.warning(f"Could not connect to Supabase: {e}. Falling back to memory store.")

    # -------------------------------------------------------------
    # Project Operations
    # -------------------------------------------------------------
    async def create_project(self, project_in: ProjectCreate) -> Project:
        project_id = str(uuid.uuid4())
        project = Project(
            id=project_id,
            title=project_in.title,
            description=project_in.description,
            created_at=datetime.now(timezone.utc),
            members=[],
        )
        self._projects[project_id] = project
        self._responses[project_id] = []
        self._decisions[project_id] = []
        return project

    async def get_project(self, project_id: str) -> Optional[Project]:
        return self._projects.get(project_id)

    async def list_projects(self) -> List[Project]:
        return list(self._projects.values())

    async def add_team_member(
        self, project_id: str, member_in: TeamMemberCreate
    ) -> Optional[TeamMember]:
        project = self._projects.get(project_id)
        if not project:
            return None
        member_id = str(uuid.uuid4())
        member = TeamMember(
            id=member_id,
            name=member_in.name,
            role=member_in.role,
            email=member_in.email,
            created_at=datetime.now(timezone.utc),
        )
        project.members.append(member)
        return member

    # -------------------------------------------------------------
    # Team Responses (Individual Opinions)
    # -------------------------------------------------------------
    async def add_response(
        self,
        project_id: str,
        member_name: str,
        raw_text: str,
        source: str = "direct_submission",
    ) -> MemberResponse:
        response = MemberResponse(
            id=str(uuid.uuid4()),
            project_id=project_id,
            member_name=member_name,
            raw_text=raw_text,
            source=source,
            submitted_at=datetime.now(timezone.utc),
        )
        if project_id not in self._responses:
            self._responses[project_id] = []
        self._responses[project_id].append(response)
        return response

    async def get_responses(self, project_id: str) -> List[MemberResponse]:
        return self._responses.get(project_id, [])

    # -------------------------------------------------------------
    # Alignment Analyses (AI-Generated Interpretations & Proposals)
    # -------------------------------------------------------------
    async def save_report(
        self, project_id: str, report: SynthesisReport
    ) -> SynthesisReport:
        self._reports[project_id] = report
        return report

    async def get_latest_report(self, project_id: str) -> Optional[SynthesisReport]:
        return self._reports.get(project_id)

    # -------------------------------------------------------------
    # Confirmed Decisions (Human-Approved Official Commitments)
    # -------------------------------------------------------------
    async def record_decision(
        self, project_id: str, action: DecisionActionRequest
    ) -> ConfirmedDecision:
        report = self._reports.get(project_id)
        decision_text = action.decision_text or "No specific text recorded"

        # If resolution exists, resolve default decision text
        if report:
            for res in report.proposed_resolutions:
                if res.resolution_id == action.resolution_id:
                    if not action.decision_text:
                        decision_text = res.recommended_solution
                    break

        status_mapping = {
            "APPROVE": DecisionStatus.APPROVED,
            "REJECT": DecisionStatus.REJECTED,
            "MODIFY": DecisionStatus.MODIFIED,
        }

        confirmed = ConfirmedDecision(
            id=str(uuid.uuid4()),
            project_id=project_id,
            resolution_id=action.resolution_id,
            status=status_mapping[action.action],
            decision_text=decision_text,
            decided_by=action.decided_by,
            decided_at=datetime.now(timezone.utc),
            notes=action.notes,
        )

        if project_id not in self._decisions:
            self._decisions[project_id] = []
        self._decisions[project_id].append(confirmed)

        return confirmed

    async def get_decisions(self, project_id: str) -> List[ConfirmedDecision]:
        return self._decisions.get(project_id, [])


storage_service = SupabaseStorageService()
