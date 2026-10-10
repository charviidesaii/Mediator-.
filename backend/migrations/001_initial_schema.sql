-- Mediator Database Schema
-- Version: 001
-- Description: Initial schema for projects, members, responses, analyses, conflicts, resolutions, and confirmed decisions.

-- Projects Table
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Team Members Table
CREATE TABLE IF NOT EXISTS team_members (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    name TEXT NOT NULL,
    role TEXT,
    email TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
    UNIQUE(project_id, name)
);

-- Member Responses (Individual Opinions) Table
CREATE TABLE IF NOT EXISTS member_responses (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    member_name TEXT NOT NULL,
    raw_text TEXT NOT NULL,
    source TEXT DEFAULT 'direct_submission',
    submitted_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);

-- Alignment Analyses (AI-Generated Reports & Intermediate Debug Data)
CREATE TABLE IF NOT EXISTS alignment_analyses (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    report_json TEXT NOT NULL,
    perspectives_json TEXT NOT NULL,
    conflicts_json TEXT NOT NULL,
    intermediate_debug_json TEXT,
    alignment_score REAL DEFAULT 0.0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);

-- Confirmed Decisions (Human-Approved Project Commitments)
CREATE TABLE IF NOT EXISTS confirmed_decisions (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    resolution_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('APPROVED', 'REJECTED', 'MODIFIED')),
    decision_text TEXT NOT NULL,
    decided_by TEXT NOT NULL,
    decided_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    notes TEXT,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);

-- Indexes for performance and isolation
CREATE INDEX IF NOT EXISTS idx_team_members_project ON team_members(project_id);
CREATE INDEX IF NOT EXISTS idx_member_responses_project ON member_responses(project_id);
CREATE INDEX IF NOT EXISTS idx_analyses_project ON alignment_analyses(project_id);
CREATE INDEX IF NOT EXISTS idx_decisions_project ON confirmed_decisions(project_id);
