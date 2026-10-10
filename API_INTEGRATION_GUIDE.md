# Mediator — API Integration Guide (for Figma Make & External Frontends)

This guide provides the complete API specification, request/response formats, and sequence diagrams required to connect a decoupled frontend (such as Figma Make wireframes, React/Vite, or Next.js) to the Mediator AI Team Alignment Platform.

---

## 1. Overview & Connection Architecture

The Mediator platform is an **AI-powered team alignment backend**. It exposes a pure REST JSON API.

```
┌──────────────────────────────┐                ┌──────────────────────────────┐
│  External Frontend (Figma)   │                │   Mediator FastAPI Backend   │
│  - Project Workspace UI      │  HTTP/REST     │   - Project Management       │
│  - Response Collection Form  │ ─────────────> │   - Google ADK Multi-Agent   │
│  - Conflict & Proposal Cards │  JSON Payloads │   - Persistent SQLite / DB   │
│  - Human Decision Controls   │                │   - OpenAPI Specification    │
└──────────────────────────────┘                └──────────────────────────────┘
```

- **Default Local Base URL**: `http://localhost:8000`
- **Interactive OpenAPI Documentation (Swagger UI)**: `http://localhost:8000/docs`
- **Machine-Readable OpenAPI Specification**: `http://localhost:8000/openapi.json`
- **Built-in HTML Test Console**: `http://localhost:8000/test-ui`

---

## 2. Environment & CORS Setup

The backend comes preconfigured with CORS middleware allowing browser preflight (`OPTIONS`) requests.

In your external frontend or Figma Make environment, configure your API base URL:
```javascript
const API_BASE_URL = process.env.VITE_API_BASE_URL || "http://localhost:8000";
```

Allowed CORS Origins can be configured in `.env`:
```env
CORS_ORIGINS=["http://localhost:3000","http://localhost:5173","http://localhost:8000","*"]
```

---

## 3. End-to-End API Usage Sequence

```
1. POST /api/projects                  -> Create project workspace
2. POST /api/projects/{id}/members     -> Add team members
3. POST /api/projects/{id}/responses   -> Submit teammate perspectives
4. POST /api/projects/{id}/analyze     -> Trigger Google ADK multi-agent analysis
5. GET  /api/projects/{id}/alignment   -> Retrieve synthesis report & proposed resolutions
6. POST /api/projects/{id}/decisions   -> Human team approves/rejects/modifies proposals
7. GET  /api/projects/{id}/decisions   -> Retrieve confirmed binding commitments
```

---

## 4. Complete API Endpoint Reference

### 4.1 Create a Project
- **Method**: `POST`
- **Path**: `/api/projects`
- **Description**: Initializes a new project workspace.

#### Request Body
```json
{
  "title": "Mobile App Launch 2026",
  "description": "Collaborative sprint for Q4 release"
}
```

#### Response (`201 Created`)
```json
{
  "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "title": "Mobile App Launch 2026",
  "description": "Collaborative sprint for Q4 release",
  "created_at": "2026-10-10T19:30:00Z",
  "members": []
}
```

---

### 4.2 Add Team Member
- **Method**: `POST`
- **Path**: `/api/projects/{project_id}/members`
- **Description**: Registers a team member in the project workspace. Duplicate names are rejected.

#### Request Body
```json
{
  "name": "Alex",
  "role": "Frontend Lead",
  "email": "alex@team.com"
}
```

#### Response (`201 Created`)
```json
{
  "id": "e4b529a6-89d4-48f8-b391-9e7ecdc17192",
  "name": "Alex",
  "role": "Frontend Lead",
  "email": "alex@team.com",
  "created_at": "2026-10-10T19:31:00Z"
}
```

#### Error Response (`409 Conflict`)
```json
{
  "detail": "Team member 'Alex' already exists in this project."
}
```

---

### 4.3 Submit Member Perspective
- **Method**: `POST`
- **Path**: `/api/projects/{project_id}/responses`
- **Description**: Submits an individual teammate's raw priorities, expectations, or concerns.

#### Request Body
```json
{
  "member_name": "Alex",
  "raw_text": "Our priority is completing the frontend by Friday.",
  "source": "figma_form"
}
```

#### Response (`201 Created`)
```json
{
  "id": "b18a4a2c-7b0a-4a25-9c98-10928374a2b1",
  "project_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "member_name": "Alex",
  "raw_text": "Our priority is completing the frontend by Friday.",
  "source": "figma_form",
  "submitted_at": "2026-10-10T19:32:00Z"
}
```

---

### 4.4 List Submitted Perspectives
- **Method**: `GET`
- **Path**: `/api/projects/{project_id}/responses`
- **Description**: Retrieves all submitted responses for a project.

#### Response (`200 OK`)
```json
[
  {
    "id": "b18a4a2c-7b0a-4a25-9c98-10928374a2b1",
    "project_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "member_name": "Alex",
    "raw_text": "Our priority is completing the frontend by Friday.",
    "source": "figma_form",
    "submitted_at": "2026-10-10T19:32:00Z"
  }
]
```

---

### 4.5 Trigger Multi-Agent Analysis
- **Method**: `POST`
- **Path**: `/api/projects/{project_id}/analyze`
- **Description**: Runs the sequential Google ADK multi-agent workflow:
  1. **Perspective Agent**: Extracts goals, priorities, responsibilities, and deadlines.
  2. **Conflict Agent**: Identifies contradictory dates, priority mismatches, and QA gaps.
  3. **Resolution Agent**: Proposes compromises, leaving decisions strictly as `PROPOSED`.

#### Response (`200 OK`)
```json
{
  "workflow_id": "wf-a1b2c3d4e5",
  "project_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "execution_mode": "MOCK_DETERMINISTIC",
  "perspectives_output": {
    "total_members_analyzed": 3,
    "overall_summary": "Analyzed 3 teammate perspectives...",
    "perspectives": [
      {
        "member_name": "Alex",
        "goals": [{ "statement": "Complete frontend user interface", "source_quote": "...", "clarity": "CLEAR" }],
        "priorities": [{ "priority_item": "...", "urgency_level": "CRITICAL", "source_quote": "..." }],
        "deadlines": [{ "milestone": "Frontend Completion", "expected_deadline": "Friday", "is_tentative": false, "source_quote": "..." }],
        "ambiguities_or_missing_details": ["No explicit calendar deadline for testing..."],
        "key_quotes": ["Our priority is completing the frontend by Friday."]
      }
    ],
    "identified_gaps": ["Calendar duration for QA remains undefined."]
  },
  "conflicts_output": {
    "conflicts": [
      {
        "conflict_id": "CONF-01",
        "title": "Deadline Sequence Inversion: Sam Launch Precedes Alex Completion",
        "conflict_type": "DEADLINE_CONTRADICTION",
        "category": "DIRECT_DISAGREEMENT",
        "severity": "HIGH",
        "severity_reasoning": "Logical impossibility: Sam expects to launch on Thursday, while Alex completes frontend on Friday.",
        "parties_involved": ["Sam", "Alex"],
        "evidence": [
          { "member_name": "Sam", "quote": "...", "interpretation": "Launch on Thursday" },
          { "member_name": "Alex", "quote": "...", "interpretation": "Finish Friday" }
        ],
        "impact_description": "Direct blocker."
      }
    ],
    "compatible_differences": ["Functional focus differences are complementary."],
    "critical_information_gaps": ["Duration for QA sign-off remains undefined."],
    "synthesis_summary": "Detected 1 blocking contradiction."
  },
  "synthesis_output": {
    "report_id": "SYNTH-3fa85f64",
    "project_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "alignment_score": 55.0,
    "executive_summary": "The multi-agent workflow identified conflicting timeline assumptions...",
    "proposed_resolutions": [
      {
        "resolution_id": "RES-01",
        "conflict_id": "CONF-01",
        "conflict_title": "Deadline Sequence Inversion",
        "recommended_solution": "Adopt a synchronized schedule: Reschedule full public launch to Monday...",
        "reasoning": "A product cannot launch before prerequisite components are complete...",
        "alternative_options": [
          {
            "option_id": "OPT-1A",
            "title": "Adjust Public Launch Date to Monday",
            "description": "Shift launch to Monday morning after Friday QA.",
            "pros": ["Full scope", "Less crunch"],
            "cons": ["Delayed release"],
            "compromise_notes": "Accommodates all deadlines."
          }
        ],
        "impacted_members": ["Sam", "Alex"],
        "unresolved_questions_for_team": ["Is Thursday deadline a hard external commitment?"],
        "status": "PROPOSED"
      }
    ],
    "human_action_items": [
      "Vote on whether to reschedule launch to Monday or reduce scope for Thursday."
    ],
    "disclaimer": "All resolutions are AI-generated proposals and require explicit human team approval before becoming commitments."
  },
  "execution_metadata": {
    "duration_seconds": 0.05,
    "model": "gemini-2.5-flash",
    "framework": "Google Agent Development Kit (ADK) v2.11.0",
    "adk_workflow_graph": "team_alignment_workflow"
  }
}
```

---

### 4.6 Retrieve Alignment Report
- **Method**: `GET`
- **Path**: `/api/projects/{project_id}/alignment`
- **Description**: Returns the latest synthesis report and active proposals.

---

### 4.7 Record Human Decision (Approve / Reject / Modify)
- **Method**: `POST`
- **Path**: `/api/projects/{project_id}/decisions`
- **Description**: Transitions an AI proposal into an official binding project commitment. Only human-approved actions become commitments.

#### Request Body (Approval)
```json
{
  "resolution_id": "RES-01",
  "action": "APPROVE",
  "decided_by": "Sam (Product Lead)",
  "notes": "Approved unanimously during sprint sync."
}
```

#### Request Body (Modification)
```json
{
  "resolution_id": "RES-01",
  "action": "MODIFY",
  "decision_text": "Agreed commitment: Frontend delivers Thursday 5pm, testing Friday morning, launch Friday 3pm.",
  "decided_by": "Sam (Product Lead)",
  "notes": "Custom compromise negotiated between Alex and Taylor."
}
```

#### Response (`201 Created`)
```json
{
  "id": "7fa94e12-32a1-432a-bc91-239485710293",
  "project_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "resolution_id": "RES-01",
  "status": "APPROVED",
  "decision_text": "Adopt a synchronized schedule: Reschedule full public launch to Monday...",
  "decided_by": "Sam (Product Lead)",
  "decided_at": "2026-10-10T19:35:00Z",
  "notes": "Approved unanimously during sprint sync."
}
```

#### Error Response (`400 Bad Request` if bogus resolution ID is provided)
```json
{
  "detail": "Resolution ID 'RES-BOGUS-999' was not found in the project's proposals. Valid resolution IDs: ['RES-01']"
}
```

---

### 4.8 Retrieve Confirmed Decisions
- **Method**: `GET`
- **Path**: `/api/projects/{project_id}/decisions`
- **Description**: Returns all historical and active binding decisions for the project.

---

## 5. Figma Make Frontend Integration Code Snippet

```typescript
// Example TypeScript client helper for Figma Make wireframes
export class MediatorClient {
  constructor(private baseUrl: string = "http://localhost:8000") {}

  async createProject(title: string, description?: string) {
    const res = await fetch(`${this.baseUrl}/api/projects`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title, description }),
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  }

  async submitPerspective(projectId: string, memberName: string, text: string) {
    const res = await fetch(`${this.baseUrl}/api/projects/${projectId}/responses`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ member_name: memberName, raw_text: text }),
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  }

  async runAnalysis(projectId: string) {
    const res = await fetch(`${this.baseUrl}/api/projects/${projectId}/analyze`, {
      method: "POST",
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  }

  async approveDecision(projectId: string, resolutionId: string, decidedBy: string) {
    const res = await fetch(`${this.baseUrl}/api/projects/${projectId}/decisions`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        resolution_id: resolutionId,
        action: "APPROVE",
        decided_by: decidedBy,
      }),
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  }
}
```
