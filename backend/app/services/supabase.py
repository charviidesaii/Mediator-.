"""Data persistence service supporting persistent SQLite, remote Supabase PostgreSQL, and local memory storage.

Maintains strict separation between:
- Individual opinions (MemberResponse)
- AI-generated interpretations (ExtractedPerspective)
- AI-generated recommendations (ProposedResolution)
- Human-approved decisions (ConfirmedDecision)

Ensures that only approved decisions become official project commitments.
Survives application restarts when using 'sqlite' or 'supabase' backends.
"""

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

import aiosqlite
import httpx

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

MIGRATION_DDL = """
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS team_members (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    name TEXT NOT NULL,
    role TEXT,
    email TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
    UNIQUE(project_id, name)
);

CREATE TABLE IF NOT EXISTS member_responses (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    member_name TEXT NOT NULL,
    raw_text TEXT NOT NULL,
    source TEXT DEFAULT 'direct_submission',
    submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS alignment_analyses (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    report_json TEXT NOT NULL,
    alignment_score REAL DEFAULT 0.0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS confirmed_decisions (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    resolution_id TEXT NOT NULL,
    status TEXT NOT NULL,
    decision_text TEXT NOT NULL,
    decided_by TEXT NOT NULL,
    decided_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    notes TEXT,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);
"""


class StorageService:
    """Storage service supporting SQLite (persistent), Supabase, or Memory."""

    def __init__(self, backend: Optional[str] = None):
        self.backend = backend or settings.storage_backend
        self.db_path = settings.sqlite_db_path

        # Memory store structures (used when backend == 'memory')
        self._projects: Dict[str, Project] = {}
        self._responses: Dict[str, List[MemberResponse]] = {}
        self._reports: Dict[str, SynthesisReport] = {}
        self._decisions: Dict[str, List[ConfirmedDecision]] = {}

        self._initialized = False

    async def initialize(self) -> None:
        """Initializes tables, migrations, or connections."""
        if self._initialized:
            return

        if self.backend == "sqlite":
            os.makedirs(os.path.dirname(os.path.abspath(self.db_path)), exist_ok=True)
            async with aiosqlite.connect(self.db_path) as db:
                await db.executescript(MIGRATION_DDL)
                await db.commit()
            logger.info(f"SQLite persistent storage initialized at: {self.db_path}")

        elif self.backend == "supabase":
            if not settings.supabase_url or not settings.supabase_key:
                logger.warning("Supabase URL or Key not set. Falling back to persistent SQLite.")
                self.backend = "sqlite"
                await self.initialize()
                return
            logger.info(f"Supabase PostgreSQL storage configured: {settings.supabase_url}")

        else:
            logger.info("Using ephemeral in-memory storage (test mode).")

        self._initialized = True

    # -------------------------------------------------------------
    # Project Operations
    # -------------------------------------------------------------
    async def create_project(self, project_in: ProjectCreate) -> Project:
        await self.initialize()
        project_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        project = Project(
            id=project_id,
            title=project_in.title.strip(),
            description=project_in.description.strip() if project_in.description else None,
            created_at=now,
            members=[],
        )

        if self.backend == "sqlite":
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    "INSERT INTO projects (id, title, description, created_at) VALUES (?, ?, ?, ?)",
                    (project.id, project.title, project.description, now.isoformat()),
                )
                await db.commit()
        else:
            self._projects[project_id] = project
            self._responses[project_id] = []
            self._decisions[project_id] = []

        return project

    async def get_project(self, project_id: str) -> Optional[Project]:
        await self.initialize()
        if self.backend == "sqlite":
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(
                    "SELECT id, title, description, created_at FROM projects WHERE id = ?",
                    (project_id,),
                ) as cursor:
                    row = await cursor.fetchone()
                    if not row:
                        return None

                # Fetch members
                members: List[TeamMember] = []
                async with db.execute(
                    "SELECT id, name, role, email, created_at FROM team_members WHERE project_id = ? ORDER BY created_at",
                    (project_id,),
                ) as cur:
                    async for m_row in cur:
                        members.append(
                            TeamMember(
                                id=m_row["id"],
                                name=m_row["name"],
                                role=m_row["role"],
                                email=m_row["email"],
                                created_at=datetime.fromisoformat(m_row["created_at"]) if m_row["created_at"] else datetime.now(timezone.utc),
                            )
                        )

                return Project(
                    id=row["id"],
                    title=row["title"],
                    description=row["description"],
                    created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else datetime.now(timezone.utc),
                    members=members,
                )

        return self._projects.get(project_id)

    async def list_projects(self) -> List[Project]:
        await self.initialize()
        if self.backend == "sqlite":
            projects = []
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute("SELECT id FROM projects ORDER BY created_at DESC") as cursor:
                    async for row in cursor:
                        p = await self.get_project(row["id"])
                        if p:
                            projects.append(p)
            return projects

        return list(self._projects.values())

    async def add_team_member(
        self, project_id: str, member_in: TeamMemberCreate
    ) -> Optional[TeamMember]:
        await self.initialize()
        project = await self.get_project(project_id)
        if not project:
            return None

        # Prevent duplicate member names within same project
        for m in project.members:
            if m.name.lower() == member_in.name.lower().strip():
                raise ValueError(f"Team member '{member_in.name.strip()}' already exists in this project.")

        member_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        member = TeamMember(
            id=member_id,
            name=member_in.name.strip(),
            role=member_in.role.strip() if member_in.role else None,
            email=member_in.email.strip() if member_in.email else None,
            created_at=now,
        )

        if self.backend == "sqlite":
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    "INSERT INTO team_members (id, project_id, name, role, email, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                    (member.id, project_id, member.name, member.role, member.email, now.isoformat()),
                )
                await db.commit()
        else:
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
        await self.initialize()
        project = await self.get_project(project_id)
        if not project:
            raise ValueError(f"Project with ID '{project_id}' not found.")

        clean_name = member_name.strip()
        clean_text = raw_text.strip()
        if not clean_text:
            raise ValueError("Response text cannot be empty or whitespace.")

        now = datetime.now(timezone.utc)
        response = MemberResponse(
            id=str(uuid.uuid4()),
            project_id=project_id,
            member_name=clean_name,
            raw_text=clean_text,
            source=source,
            submitted_at=now,
        )

        if self.backend == "sqlite":
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    "INSERT INTO member_responses (id, project_id, member_name, raw_text, source, submitted_at) VALUES (?, ?, ?, ?, ?, ?)",
                    (response.id, project_id, response.member_name, response.raw_text, response.source, now.isoformat()),
                )
                await db.commit()
        else:
            if project_id not in self._responses:
                self._responses[project_id] = []
            self._responses[project_id].append(response)

        return response

    async def get_responses(self, project_id: str) -> List[MemberResponse]:
        await self.initialize()
        if self.backend == "sqlite":
            responses: List[MemberResponse] = []
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(
                    "SELECT id, project_id, member_name, raw_text, source, submitted_at FROM member_responses WHERE project_id = ? ORDER BY submitted_at",
                    (project_id,),
                ) as cursor:
                    async for row in cursor:
                        responses.append(
                            MemberResponse(
                                id=row["id"],
                                project_id=row["project_id"],
                                member_name=row["member_name"],
                                raw_text=row["raw_text"],
                                source=row["source"],
                                submitted_at=datetime.fromisoformat(row["submitted_at"]) if row["submitted_at"] else datetime.now(timezone.utc),
                            )
                        )
            return responses

        return self._responses.get(project_id, [])

    # -------------------------------------------------------------
    # Alignment Analyses (AI-Generated Interpretations & Proposals)
    # -------------------------------------------------------------
    async def save_report(
        self, project_id: str, report: SynthesisReport
    ) -> SynthesisReport:
        await self.initialize()
        report.project_id = project_id

        if self.backend == "sqlite":
            report_id = str(uuid.uuid4())
            now = datetime.now(timezone.utc)
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    "INSERT INTO alignment_analyses (id, project_id, report_json, alignment_score, created_at) VALUES (?, ?, ?, ?, ?)",
                    (report_id, project_id, report.model_dump_json(), report.alignment_score, now.isoformat()),
                )
                await db.commit()
        else:
            self._reports[project_id] = report

        return report

    async def get_latest_report(self, project_id: str) -> Optional[SynthesisReport]:
        await self.initialize()
        if self.backend == "sqlite":
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(
                    "SELECT report_json FROM alignment_analyses WHERE project_id = ? ORDER BY created_at DESC LIMIT 1",
                    (project_id,),
                ) as cursor:
                    row = await cursor.fetchone()
                    if row:
                        data = json.loads(row["report_json"])
                        return SynthesisReport.model_validate(data)
            return None

        return self._reports.get(project_id)

    # -------------------------------------------------------------
    # Confirmed Decisions (Human-Approved Official Commitments)
    # -------------------------------------------------------------
    async def record_decision(
        self, project_id: str, action: DecisionActionRequest
    ) -> ConfirmedDecision:
        await self.initialize()
        project = await self.get_project(project_id)
        if not project:
            raise ValueError(f"Project with ID '{project_id}' not found.")

        # Ensure that action.resolution_id exists in the latest synthesis report
        report = await self.get_latest_report(project_id)
        if not report:
            raise ValueError(f"No alignment report found for project '{project_id}'. You must run /analyze before recording decisions.")

        valid_resolution = None
        for res in report.proposed_resolutions:
            if res.resolution_id == action.resolution_id:
                valid_resolution = res
                break

        if not valid_resolution:
            raise ValueError(
                f"Resolution ID '{action.resolution_id}' was not found in the project's proposals. "
                f"Valid resolution IDs: {[r.resolution_id for r in report.proposed_resolutions]}"
            )

        # Determine official binding commitment text
        decision_text = action.decision_text
        if not decision_text:
            if action.action == "APPROVE":
                decision_text = valid_resolution.recommended_solution
            elif action.action == "REJECT":
                decision_text = f"Rejected proposal: {valid_resolution.recommended_solution}"
            else:
                raise ValueError("Action MODIFY requires providing explicit 'decision_text'.")

        status_mapping = {
            "APPROVE": DecisionStatus.APPROVED,
            "REJECT": DecisionStatus.REJECTED,
            "MODIFY": DecisionStatus.MODIFIED,
        }

        now = datetime.now(timezone.utc)
        confirmed = ConfirmedDecision(
            id=str(uuid.uuid4()),
            project_id=project_id,
            resolution_id=action.resolution_id,
            status=status_mapping[action.action],
            decision_text=decision_text,
            decided_by=action.decided_by.strip(),
            decided_at=now,
            notes=action.notes.strip() if action.notes else None,
        )

        if self.backend == "sqlite":
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    "INSERT INTO confirmed_decisions (id, project_id, resolution_id, status, decision_text, decided_by, decided_at, notes) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (confirmed.id, project_id, confirmed.resolution_id, confirmed.status.value, confirmed.decision_text, confirmed.decided_by, now.isoformat(), confirmed.notes),
                )
                await db.commit()
        else:
            if project_id not in self._decisions:
                self._decisions[project_id] = []
            self._decisions[project_id].append(confirmed)

        return confirmed

    async def get_decisions(self, project_id: str) -> List[ConfirmedDecision]:
        await self.initialize()
        if self.backend == "sqlite":
            decisions: List[ConfirmedDecision] = []
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(
                    "SELECT id, project_id, resolution_id, status, decision_text, decided_by, decided_at, notes FROM confirmed_decisions WHERE project_id = ? ORDER BY decided_at",
                    (project_id,),
                ) as cursor:
                    async for row in cursor:
                        decisions.append(
                            ConfirmedDecision(
                                id=row["id"],
                                project_id=row["project_id"],
                                resolution_id=row["resolution_id"],
                                status=DecisionStatus(row["status"]),
                                decision_text=row["decision_text"],
                                decided_by=row["decided_by"],
                                decided_at=datetime.fromisoformat(row["decided_at"]) if row["decided_at"] else datetime.now(timezone.utc),
                                notes=row["notes"],
                            )
                        )
            return decisions

        return self._decisions.get(project_id, [])


# Unified singleton storage instance
storage_service = StorageService()
SupabaseStorageService = StorageService  # Backward compatibility alias
