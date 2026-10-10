"""Database representations and SQL table definitions for Supabase PostgreSQL.

Defines the database schema and table structures supporting:
- Projects
- Team members
- Team responses (with source attribution and timestamp)
- Alignment analyses (with intermediate and final reports)
- Detected conflicts
- Proposed resolutions (clearly marked PROPOSED)
- Confirmed decisions (human-approved official commitments)
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


# SQL DDL Script for Supabase PostgreSQL initialization (Phase 3 reference)
SUPABASE_SCHEMA_SQL = """
-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Projects table
CREATE TABLE IF NOT EXISTS projects (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    title TEXT NOT NULL,
    description TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Team members table
CREATE TABLE IF NOT EXISTS team_members (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    project_id UUID REFERENCES projects(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    role TEXT,
    email TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Team responses table (Individual Opinions)
CREATE TABLE IF NOT EXISTS member_responses (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    project_id UUID REFERENCES projects(id) ON DELETE CASCADE,
    member_name TEXT NOT NULL,
    raw_text TEXT NOT NULL,
    source TEXT DEFAULT 'direct_submission',
    submitted_at TIMESTAMPTZ DEFAULT NOW()
);

-- Alignment analyses table (AI-Generated Intermediate & Final Reports)
CREATE TABLE IF NOT EXISTS alignment_analyses (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    project_id UUID REFERENCES projects(id) ON DELETE CASCADE,
    perspectives_data JSONB NOT NULL,
    conflicts_data JSONB NOT NULL,
    synthesis_report JSONB NOT NULL,
    intermediate_debug JSONB,
    alignment_score NUMERIC(5,2),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Detected conflicts table
CREATE TABLE IF NOT EXISTS detected_conflicts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    analysis_id UUID REFERENCES alignment_analyses(id) ON DELETE CASCADE,
    conflict_code TEXT NOT NULL,
    title TEXT NOT NULL,
    conflict_type TEXT NOT NULL,
    severity TEXT NOT NULL,
    severity_reasoning TEXT NOT NULL,
    parties_involved TEXT[] NOT NULL,
    evidence JSONB NOT NULL,
    impact_description TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Proposed resolutions table (AI-Generated Proposals - NOT DECISIONS)
CREATE TABLE IF NOT EXISTS proposed_resolutions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    analysis_id UUID REFERENCES alignment_analyses(id) ON DELETE CASCADE,
    conflict_code TEXT NOT NULL,
    conflict_title TEXT NOT NULL,
    recommended_solution TEXT NOT NULL,
    reasoning TEXT NOT NULL,
    alternative_options JSONB NOT NULL,
    impacted_members TEXT[] NOT NULL,
    unresolved_questions TEXT[] NOT NULL,
    status TEXT NOT NULL DEFAULT 'PROPOSED', -- ALWAYS PROPOSED by default
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Confirmed decisions table (Human-Approved Project Commitments)
CREATE TABLE IF NOT EXISTS confirmed_decisions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    project_id UUID REFERENCES projects(id) ON DELETE CASCADE,
    resolution_id UUID REFERENCES proposed_resolutions(id) ON DELETE SET NULL,
    status TEXT NOT NULL CHECK (status IN ('APPROVED', 'REJECTED', 'MODIFIED')),
    decision_text TEXT NOT NULL,
    decided_by TEXT NOT NULL,
    decided_at TIMESTAMPTZ DEFAULT NOW(),
    notes TEXT
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_members_project ON team_members(project_id);
CREATE INDEX IF NOT EXISTS idx_responses_project ON member_responses(project_id);
CREATE INDEX IF NOT EXISTS idx_analyses_project ON alignment_analyses(project_id);
CREATE INDEX IF NOT EXISTS idx_decisions_project ON confirmed_decisions(project_id);
"""


class DBProjectRecord(BaseModel):
    id: str
    title: str
    description: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class DBResponseRecord(BaseModel):
    id: str
    project_id: str
    member_name: str
    raw_text: str
    source: str
    submitted_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class DBAnalysisRecord(BaseModel):
    id: str
    project_id: str
    perspectives_data: Dict[str, Any]
    conflicts_data: Dict[str, Any]
    synthesis_report: Dict[str, Any]
    intermediate_debug: Optional[Dict[str, Any]] = None
    alignment_score: float
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class DBDecisionRecord(BaseModel):
    id: str
    project_id: str
    resolution_id: str
    status: str
    decision_text: str
    decided_by: str
    decided_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    notes: Optional[str] = None
