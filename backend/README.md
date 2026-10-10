# AI Team Alignment Platform — Backend & Multi-Agent System

An AI-powered team alignment backend built for hackathons and collaborative development. The platform acts as an **AI teammate** that surfaces hidden misalignments, compares teammate perspectives, identifies deadline contradictions, detects unbudgeted dependencies, and synthesizes pragmatic compromises — **while strictly preserving human authority over decisions**.

> **Note**: This repository focuses exclusively on the backend and multi-agent AI functionality. The frontend will be built separately (e.g. using Figma Make) and connected via the REST API.

---

## 🛠 Technology Stack

- **Backend Framework**: Python 3.11+ / FastAPI
- **Multi-Agent Framework**: Google Agent Development Kit (ADK)
- **AI Model**: Google Gemini API (`gemini-2.5-flash` / `gemini-2.0-flash`)
- **Data Validation & Typing**: Pydantic v2 & Pydantic-Settings
- **Testing**: pytest & pytest-asyncio
- **Database / Persistence**: Supabase PostgreSQL schema with local memory storage adapter
- **Future Integrations**: Slack Bolt for Python, n8n webhook events

---

## 🤖 Multi-Agent Architecture (Google ADK)

The system orchestrates a sequential multi-agent pipeline using Google ADK:

```
[ Teammate Responses ]
         │
         ▼
┌─────────────────────────────────┐
│   Agent 1: Perspective Agent    │  Extracts goals, priorities, responsibilities,
│  (google.adk.agents.Agent)      │  deadlines, and missing details per teammate.
└────────────────┬────────────────┘
                 │ ExtractedPerspective & PerspectiveAnalysisOutput
                 ▼
┌─────────────────────────────────┐
│   Agent 2: Conflict Agent       │  Identifies contradictory deadlines, incompatible
│  (google.adk.agents.Agent)      │  goals, and testing gaps. Distinguishes direct
└────────────────┬────────────────┘  disagreements from compatible differences.
                 │ DetectedConflict & ConflictDetectionOutput
                 ▼
┌─────────────────────────────────┐
│   Agent 3: Resolution Agent     │  Synthesizes realistic compromises and alternative
│  (google.adk.agents.Agent)      │  options. Explicitly leaves status="PROPOSED".
└────────────────┬────────────────┘
                 │ SynthesisReport
                 ▼
┌─────────────────────────────────┐
│     Human Decision Gate         │  Teammates vote/sign-off on proposals.
│  (Confirmed Project Commitment) │  Only human-approved actions become commitments!
└─────────────────────────────────┘
```

### 1. Perspective Analysis Agent (`app/agents/perspective.py`)
- Processes independently submitted teammate statements.
- Extracts project goals, priorities, responsibilities, and timeline expectations.
- Preserves original meaning by quoting members verbatim in evidence fields.
- Explicitly flags missing details or ambiguities rather than hallucinating facts.

### 2. Conflict Detection Agent (`app/agents/conflict.py`)
- Compares individual perspectives across all teammates.
- Detects contradictory deadlines (e.g., Friday frontend completion vs Thursday full launch).
- Identifies unbudgeted dependencies (e.g., testing requirements raised without a scheduled testing window).
- Distinguishes direct disagreements from compatible differences.
- Assigns severity (`HIGH`, `MEDIUM`, `LOW`) using documented criteria with evidence citations.

### 3. Resolution & Synthesis Agent (`app/agents/resolution.py`)
- Considers every teammate's perspective and constraints equitably.
- Proposes realistic compromise schedules (e.g., phased launch, scope trimming, dedicated QA gates).
- Formulates unresolved questions requiring team discussion.
- **Strict Governance Rule**: All proposed resolutions have `status="PROPOSED"`. AI never auto-approves decisions.

---

## 📁 Repository Structure

```
backend/
├── app/
│   ├── main.py                  # FastAPI application entrypoint & middleware
│   ├── config.py                # Environment configuration (pydantic-settings)
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── perspective.py       # Agent 1: Perspective Analysis Agent
│   │   ├── conflict.py          # Agent 2: Conflict Detection Agent
│   │   └── resolution.py        # Agent 3: Resolution & Synthesis Agent
│   ├── workflows/
│   │   ├── __init__.py
│   │   └── alignment.py         # Multi-Agent Workflow Orchestrator (Google ADK)
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── projects.py          # /api/projects endpoints
│   │   ├── responses.py         # /api/projects/{id}/responses endpoints
│   │   ├── analysis.py          # /api/projects/{id}/analyze & /alignment
│   │   └── decisions.py         # /api/projects/{id}/decisions (Human sign-off)
│   ├── models/
│   │   ├── __init__.py
│   │   ├── schemas.py           # Pydantic schemas for agents, inputs, & outputs
│   │   └── database.py          # Supabase PostgreSQL schema and DDL
│   └── services/
│       ├── __init__.py
│       ├── supabase.py          # Persistence service & storage adapter
│       └── analysis.py          # Analysis trigger and persistence coordinator
├── tests/
│   ├── __init__.py
│   ├── conftest.py              # Test fixtures and async client
│   ├── test_perspective_agent.py
│   ├── test_conflict_agent.py
│   ├── test_resolution_agent.py
│   ├── test_alignment_workflow.py
│   └── test_api_endpoints.py    # End-to-end integration test
├── run_scenario.py              # Interactive test scenario demonstration script
├── .env.example                 # Configuration template
├── requirements.txt             # Backend dependencies
└── README.md                    # Project documentation
```

---

## 🚀 Getting Started

### 1. Prerequisites
- Python 3.11+
- (Optional) Google Gemini API Key from [Google AI Studio](https://aistudio.google.com/)

### 2. Environment Setup

```bash
# Clone the repository and navigate to backend
cd backend

# Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Configure Environment Variables

Copy `.env.example` to `.env`:

```bash
cp .env.example .env
```

Edit `.env` to supply your `GEMINI_API_KEY`:

```env
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-2.5-flash
APP_ENV=development
```

> **Note**: If `GEMINI_API_KEY` is not provided or `MOCK_LLM=true`, the system automatically runs with a deterministic mock runner, allowing all offline development, demonstrations, and test suites to execute reliably!

---

## 🧪 Running the Sample Scenario & Tests

### Run the Interactive Scenario Demonstration
Demonstrates the Alex, Sam, and Taylor scenario from end to end:

```bash
python run_scenario.py
```

### Run Unit and Integration Tests

```bash
pytest tests -v
```

All 14 tests run and validate:
- Perspective extraction and evidence preservation
- Conflict detection (Friday vs Thursday deadline clash)
- Severity criteria and compatible differences
- Resolution proposal generation with human action items
- Governance safety invariant: AI proposals are never auto-approved
- End-to-end FastAPI REST API lifecycle

---

## 🌐 Running the FastAPI Server

Start the local server with hot-reloading:

```bash
uvicorn app.main:app --reload --port 8000
```

Once running:
- **Interactive OpenAPI Documentation (Swagger UI)**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc Documentation**: [http://localhost:8000/redoc](http://localhost:8000/redoc)
- **Health Check**: [http://localhost:8000/health](http://localhost:8000/health)

---

## 📡 REST API Reference

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/projects` | Create a new project workspace |
| `GET` | `/api/projects` | List all projects |
| `GET` | `/api/projects/{id}` | Retrieve project details |
| `POST` | `/api/projects/{id}/members` | Add a team member |
| `POST` | `/api/projects/{id}/responses` | Submit an individual teammate's viewpoint |
| `GET` | `/api/projects/{id}/responses` | Retrieve all submitted responses |
| `POST` | `/api/projects/{id}/analyze` | Trigger the multi-agent alignment workflow |
| `GET` | `/api/projects/{id}/alignment` | Retrieve the latest synthesis report & proposals |
| `POST` | `/api/projects/{id}/decisions` | Approve, reject, or modify proposed resolutions |
| `GET` | `/api/projects/{id}/decisions` | Retrieve confirmed binding decisions |

---

## 🔗 Future Integration Readiness

### 1. Figma Make / Frontend Integration
- All endpoints accept and return strict, validated JSON.
- CORS is preconfigured in `app/main.py` (customizable via `CORS_ORIGINS`).
- The frontend only needs to call `/api/projects/{id}/analyze` and render the structured `SynthesisReport`.

### 2. Slack Bolt Integration
- Teammate responses can be piped in from Slack channel messages via `POST /api/projects/{id}/responses`.
- Slack interactive messages or modals can present `proposed_resolutions` with Approve / Reject buttons hitting `POST /api/projects/{id}/decisions`.

### 3. n8n Automation
- Webhooks can be triggered upon completion of `/analyze` or `/decisions` to notify team channels or update Jira/Linear tickets.

### 4. Agent Extensibility
- `AlignmentWorkflow.register_extension_agent(...)` allows easily appending future agents (e.g. `CommitmentTrackingAgent`, `OrchestratorAgent`) without modifying existing route handlers.
