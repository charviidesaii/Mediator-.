# Mediator — Backend Audit Report

**Date**: 2026-10-10  
**Repository**: [charviidesaii/Mediator-.](https://github.com/charviidesaii/Mediator-.)  
**Audit Scope**: Phase 1 — Comprehensive Backend Architecture, Google ADK & Gemini, Persistence, APIs, and Security Inspection  
**Auditor**: Senior Backend Architect & Google ADK QA Specialist  

---

## 1. Executive Summary

A comprehensive architectural and code-level audit of the **Mediator** AI Team Alignment Platform backend was conducted. The project has an established modular foundation using FastAPI, Pydantic v2, Google ADK, and Google Gemini. 

However, the audit identified several **critical discrepancies, logic limitations, and architectural gaps** that must be resolved to achieve full production readiness, authentic Google ADK runtime execution, persistent data storage, and seamless integration with an external Figma Make frontend:

1. **Google ADK Execution Discrepancy**: While Google ADK `Agent` and `Workflow` objects are formally instantiated in `agents/perspective.py`, `agents/conflict.py`, `agents/resolution.py`, and `workflows/alignment.py`, runtime LLM calls bypassed the ADK runtime engine and invoked `self.client.models.generate_content(...)` directly on the `google.genai.Client`.
2. **Hardcoded Participant Logic in Mock/Fallback**: The offline/mock fallback analysis was hardcoded specifically for the demo participants (`Alex`, `Sam`, `Taylor`). Submitting viewpoints from arbitrary teammates (e.g., `Jordan`, `Elena`, `Marcus`) resulted in undetected conflicts and ignored perspectives.
3. **In-Memory Ephemeral Storage (No True Persistence)**: Despite containing Supabase configuration fields and SQL DDL scripts, `services/supabase.py` stored all projects, responses, and reports in volatile in-memory Python dictionaries (`self._projects = {}`). All state is completely lost upon application restarts.
4. **Missing Authentication & Project-Level Authorization**: All API routes are completely unauthenticated. Any client can create, modify, inspect, or sign off on decisions across any project without authorization, creating cross-tenant data exposure risks.
5. **Validation & Integrity Flaws**: Empty strings and whitespace-only inputs were accepted for project titles, member names, and statements. Furthermore, `POST /api/projects/{id}/decisions` allowed recording decisions for arbitrary, nonexistent `resolution_id` values.
6. **No Pre-built Testing Harness for Figma Make**: No minimal dummy frontend existed to visually test API endpoints before connecting the Figma Make wireframes.

---

## 2. Detailed Component Inspection

### 2.1 FastAPI Entry Point & Configuration (`app/main.py`, `app/config.py`)
- **Strengths**:
  - Clean separation into route modules (`projects`, `responses`, `analysis`, `decisions`).
  - OpenAPI Swagger and ReDoc interactive documentation available at `/docs` and `/redoc`.
  - CORS middleware configured via `settings.cors_origins`.
- **Defects & Vulnerabilities**:
  - Missing global unhandled exception handler: Unhandled exceptions bubble up as generic 500 errors without structured error envelopes (`{"error": ..., "detail": ..., "status_code": ...}`).
  - No explicit storage engine selector: `config.py` did not allow selecting between SQLite, Supabase, or in-memory persistence.
  - No security headers or API key validation dependency.

### 2.2 API Routes & HTTP Status Codes (`app/routes/`)
- **`projects.py`**:
  - `POST /api/projects`: Accepted empty string `""` or whitespace `"   "` titles.
  - `POST /api/projects/{id}/members`: Permitted adding duplicate team members with identical names to the same project.
- **`responses.py`**:
  - `POST /api/projects/{id}/responses`: Accepted empty `raw_text` and empty `member_name`.
  - Did not enforce or verify that the member is registered within the project.
- **`analysis.py`**:
  - `POST /api/projects/{id}/analyze`: Returned HTTP 400 when responses were empty, but did not clearly communicate execution mode (whether live Gemini or deterministic mock was executed).
  - Lacked pagination or history for past alignment analyses.
- **`decisions.py`**:
  - `POST /api/projects/{id}/decisions`: **Critical Logic Defect** — Accepted decision sign-offs for arbitrary string IDs that never existed in the AI synthesis report. 
  - Did not prevent multiple conflicting approvals for the same resolution without explicitly using `MODIFY`.

### 2.3 Pydantic Schemas & Data Validation (`app/models/schemas.py`)
- **Strengths**:
  - Robust Pydantic v2 domain schemas with clear field definitions (`GoalItem`, `PriorityItem`, `DeadlineItem`, `DetectedConflict`, `ProposedResolution`, `SynthesisReport`).
  - Strict governance invariant: `ProposedResolution.status` is restricted to `Literal["PROPOSED"]`.
- **Defects & Improvements**:
  - Missing input sanitizers (`str.strip()`) on strings.
  - Missing field-level validators checking minimum lengths on `ProjectCreate.title`, `TeamMemberCreate.name`, and `MemberResponseSubmit.raw_text`.
  - Inconsistent timestamp representation: UTC timezone awareness needed consistent enforcement across all models.

### 2.4 Google ADK and Gemini Integration (`app/agents/`, `app/workflows/`)
- **Critical Finding: Execution Path Bypass**:
  - Google ADK `Agent` instances are created with:
    ```python
    create_perspective_adk_agent() -> Agent(name="perspective_analysis_agent", ...)
    create_conflict_adk_agent() -> Agent(name="conflict_detection_agent", ...)
    create_resolution_adk_agent() -> Agent(name="resolution_synthesis_agent", ...)
    ```
  - And a Google ADK `Workflow` is created in `workflows/alignment.py`:
    ```python
    Workflow(edges=[(START, perspective_agent, conflict_agent, resolution_agent)])
    ```
  - **However**, when `PerspectiveAnalysisService.analyze()`, `ConflictDetectionService.detect_conflicts()`, and `ResolutionSynthesisService.synthesize()` executed, they made direct calls:
    ```python
    self.client.models.generate_content(...)
    ```
  - The Google ADK `Runner` (`from google.adk.runners import Runner`) and ADK session services (`InMemorySessionService`) were not actively executing the agent turns.
- **Remediation**:
  - Provide a genuine Google ADK runner pipeline using `google.adk.runners.Runner` and `google.adk.workflow.Workflow`, passing events through ADK session management while maintaining structured Pydantic input/output schemas.
  - Explicitly label and separate mock mode from live Gemini execution, logging execution mode transparently.

### 2.5 Dynamic Participant Analysis vs Hardcoded Demos
- **Critical Finding**:
  - The offline/mock analyzer contained hardcoded references:
    ```python
    alex = member_map.get("Alex")
    sam = member_map.get("Sam")
    taylor = member_map.get("Taylor")
    ```
  - When arbitrary team members (e.g. `Alice`, `Bob`, `Carlos`) submitted conflicting deadlines (e.g. Wednesday launch vs Thursday code freeze), the mock detection logic completely failed to identify the conflict because member names did not match the demo script.
- **Remediation**:
  - Implement a dynamic semantic rules engine in the deterministic analyzer that inspects timeline entities, goal verbs, dependency clauses, and priority keywords across arbitrary member counts and arbitrary participant names.

### 2.6 Supabase Database & Persistence (`app/services/supabase.py`)
- **Critical Finding**:
  - `services/supabase.py` contains:
    ```python
    self._projects: Dict[str, Project] = {}
    self._responses: Dict[str, List[MemberResponse]] = {}
    self._reports: Dict[str, SynthesisReport] = {}
    self._decisions: Dict[str, List[ConfirmedDecision]] = {}
    ```
  - While configuration fields for `SUPABASE_URL` and `SUPABASE_KEY` existed, no database connection was ever initiated, and no records were written to PostgreSQL.
  - Restarting the server destroys all projects, responses, reports, and approved decisions.
- **Remediation**:
  - Implement true persistent storage:
    1. **Persistent Local Database (SQLite via aiosqlite)**: Built-in, zero-credential local file persistence (`data/mediator.db`) that survives server restarts.
    2. **Remote Supabase PostgreSQL Engine**: Direct REST/HTTP or asyncpg integration when `SUPABASE_URL` and `SUPABASE_KEY` are provided.
    3. **Memory Engine**: Explicitly enabled only for automated test isolation (`STORAGE_BACKEND=memory`).
  - Provide SQL migration scripts (`migrations/001_initial_schema.sql`) with tables, foreign keys, indexes, and constraints.

### 2.7 Security, Authentication & Authorization
- **Critical Finding**:
  - No authentication headers (`X-API-Key` or `Authorization: Bearer <token>`) were enforced.
  - Any HTTP client could query or alter any project ID without authorization.
- **Remediation**:
  - Implement configurable authentication middleware/dependencies supporting:
    - Admin API Key (`X-API-Key` / `settings.api_secret_key`)
    - Project-scoped access tokens or open development mode (`AUTH_ENABLED=false` for local prototyping, `AUTH_ENABLED=true` for production).
  - Enforce project data isolation: ensure responses, analyses, and decisions cannot be accessed across different project IDs.

---

## 3. Prioritized Defect & Remediation Matrix

| ID | Component | Severity | Description | Remediation Plan |
|---|---|---|---|---|
| **DEF-01** | Google ADK | HIGH | ADK Agents defined but runtime calls direct Gemini API. | Integrate genuine ADK `Runner` and `Workflow` execution path with event-driven state updates. |
| **DEF-02** | Agent Logic | HIGH | Hardcoded to `Alex/Sam/Taylor` in deterministic/mock mode. | Implement generalized entity-relation parser for arbitrary participants and arbitrary timelines. |
| **DEF-03** | Storage | HIGH | Data held exclusively in memory; lost on restart. | Build SQLite persistent store + Supabase client adapter + migrations; environment-controlled backend. |
| **DEF-04** | API Security | MEDIUM | Endpoints completely unauthenticated and open. | Implement `X-API-Key` and project token auth dependencies with configurable dev/prod modes. |
| **DEF-05** | Decision Logic | HIGH | Decisions can be recorded for nonexistent resolution IDs. | Enforce report resolution lookup validation before allowing decision recording. |
| **DEF-06** | Input Validation | MEDIUM | Empty project titles and empty responses accepted. | Add Pydantic string validators, stripping whitespace and enforcing length bounds. |
| **DEF-07** | Frontend Test | MEDIUM | No UI test harness for verifying APIs before Figma Make. | Create minimal plain HTML/JS test console connecting directly to REST API. |
| **DEF-08** | Documentation | LOW | Missing OpenAPI JSON export and Figma Make guide. | Export `openapi.json` and author comprehensive `API_INTEGRATION_GUIDE.md`. |

---

## 4. Conclusion & Next Steps

The existing foundation is solid in concept and schema design, but requires the remediation of the 8 defects listed above to transition from an initial prototype to a robust, persistent, multi-agent backend ready for Figma Make integration.

Proceed to **Phase 2 — Fix Backend Functionality** to apply these repairs systematically.
