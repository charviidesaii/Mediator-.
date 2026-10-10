# AI Team Alignment Platform — Backend, Multi-Agent System & Slack Bot

An AI-powered team alignment backend built for hackathons and collaborative development. The platform acts as an **AI teammate** that surfaces hidden misalignments, compares teammate perspectives, identifies deadline contradictions, detects unbudgeted dependencies, clarifies role ownership gaps, and synthesizes pragmatic compromises — **while strictly preserving human authority over decisions**.

---

## 🛠 Technology Stack

- **Backend Framework**: Python 3.11+ / FastAPI
- **Multi-Agent Framework**: Google Agent Development Kit (ADK)
- **AI Model**: Google Gemini API (`gemini-2.5-flash` / `gemini-2.0-flash`)
- **Data Validation & Typing**: Pydantic v2 & Pydantic-Settings
- **Testing**: pytest & pytest-asyncio (30 passing tests)
- **Database / Persistence**: Persistent SQLite (`data/mediator.db`) with async queries via `aiosqlite` and Supabase PostgreSQL DDL migrations
- **Slack Teammate Integration**: Slack Bolt for Python in Socket Mode (`slack-bolt`)
- **Web Dashboard**: Interactive dark-mode dashboard with real-time API binding, conflict inspection, evidence quotes, and decision sign-offs

---

## 🤖 Multi-Agent Architecture (Google ADK)

The system orchestrates a sequential multi-agent pipeline using Google ADK:

```
[ Teammate Responses ] (Web Dashboard or Slack Thread)
         │
         ▼
┌─────────────────────────────────┐
│   Agent 1: Perspective Agent    │  Extracts goals, priorities, responsibilities,
│  (google.adk.agents.Agent)      │  deadlines, and missing details per teammate.
└────────────────┬────────────────┘
                 │ ExtractedPerspective & PerspectiveAnalysisOutput
                 ▼
┌─────────────────────────────────┐
│   Agent 2: Conflict Agent       │  Identifies contradictory deadlines, sequence
│  (google.adk.agents.Agent)      │  inversions, and role ownership gaps/overlaps.
└────────────────┬────────────────┘  Distinguishes direct conflicts from compatible differences.
                 │ DetectedConflict & ConflictDetectionOutput
                 ▼
┌─────────────────────────────────┐
│   Agent 3: Resolution Agent     │  Synthesizes realistic compromises and alternative
│  (google.adk.agents.Agent)      │  options. Explicitly leaves status="PROPOSED".
└────────────────┬────────────────┘
                 │ SynthesisReport
                 ▼
┌─────────────────────────────────┐
│     Human Decision Gate         │  Teammates vote/sign-off on proposals via UI/API.
│  (Confirmed Project Commitment) │  Only human-approved actions become commitments!
└─────────────────────────────────┘
```

### 1. Perspective Analysis Agent (`app/agents/perspective.py`)
- Processes independently submitted teammate statements.
- Extracts project goals, priorities, responsibilities, and timeline expectations.
- Preserves original meaning by quoting members verbatim in evidence fields.
- Explicitly flags missing details or ambiguities rather than hallucinating facts.
- Tracks `last_execution_mode` (`LIVE_GEMINI` vs `MOCK_DETERMINISTIC`).

### 2. Conflict Detection Agent (`app/agents/conflict.py`)
- Compares individual perspectives across all teammates.
- Detects contradictory deadlines (e.g., Saturday launch vs Sunday target).
- Identifies unbudgeted dependencies (e.g., 24-hour QA testing window prerequisite).
- Identifies role & responsibility confusion (e.g., both Alex and Taylor thinking the other owns deployment).
- Distinguishes direct disagreements from compatible differences.
- Assigns severity (`HIGH`, `MEDIUM`, `LOW`) using documented criteria with evidence citations.

### 3. Resolution & Synthesis Agent (`app/agents/resolution.py`)
- Considers every teammate's perspective and constraints equitably.
- Proposes realistic compromise schedules (e.g., phased launch, scope trimming, dedicated QA gates).
- Proposes explicit role ownership splits (e.g., Taylor owns deployment pipeline, Alex owns smoke verification).
- Formulates unresolved questions requiring team discussion.
- **Strict Governance Rule**: All proposed resolutions have `status="PROPOSED"`. AI never auto-approves decisions.

---

## 📁 Repository Structure

```
backend/
├── app/
│   ├── main.py                  # FastAPI application entrypoint, CORS, & UI routes
│   ├── config.py                # Environment configuration & Slack settings
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── perspective.py       # Agent 1: Perspective Analysis Agent
│   │   ├── conflict.py          # Agent 2: Conflict Detection Agent
│   │   └── resolution.py        # Agent 3: Resolution & Synthesis Agent
│   ├── workflows/
│   │   ├── __init__.py
│   │   └── alignment.py         # Multi-Agent Workflow Orchestrator (Google ADK)
│   ├── slack/
│   │   ├── __init__.py
│   │   ├── service.py           # Context cleaning, user caching, & Block Kit generation
│   │   └── bot.py               # Slack Bolt Socket Mode app & event deduplication
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
│       ├── supabase.py          # SQLite persistence adapter & Slack channel mappings
│       └── analysis.py          # Analysis trigger and persistence coordinator
├── dummy_frontend/
│   └── index.html               # Interactive full-featured web dashboard
├── migrations/
│   └── 001_initial_schema.sql   # DDL migrations including slack_channel_mappings
├── tests/
│   ├── __init__.py
│   ├── conftest.py              # Test fixtures and async client
│   ├── test_perspective_agent.py
│   ├── test_conflict_agent.py
│   ├── test_resolution_agent.py
│   ├── test_alignment_workflow.py
│   ├── test_api_endpoints.py    # End-to-end integration test
│   ├── test_demo_scenario.py    # 3-teammate conflicting scenario lifecycle test
│   └── test_slack_bot.py        # Slack context cleaning & Block Kit test
├── run_scenario.py              # Interactive test scenario demonstration script
├── run_slack_bot.py             # Slack Bolt Socket Mode runner script
├── .env.example                 # Configuration template
├── requirements.txt             # Backend dependencies
└── README.md                    # Project documentation
```

---

## 🚀 Getting Started

### 1. Prerequisites
- Python 3.11+
- (Optional) Google Gemini API Key from [Google AI Studio](https://aistudio.google.com/)
- (Optional) Slack App Bot and App-Level Tokens for Slack integration

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

Edit `.env` to supply your configuration:

```env
# Gemini Configuration
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-2.5-flash
APP_ENV=development

# Slack Bolt Configuration (Optional)
SLACK_BOT_TOKEN=xoxb-your-bot-token
SLACK_APP_TOKEN=xapp-your-app-token
SLACK_SIGNING_SECRET=your-signing-secret
DASHBOARD_BASE_URL=http://localhost:8000
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

All 30 automated tests pass and validate:
- Perspective extraction and evidence preservation
- Conflict detection (Saturday vs Sunday launch deadline clash, ownership gaps)
- Severity criteria and compatible differences
- Resolution proposal generation with human action items
- Governance safety invariant: AI proposals are never auto-approved
- End-to-end FastAPI REST API lifecycle
- Slack text cleaning, mention stripping, Block Kit formatting, and event deduplication
- Database persistence across server reloads

---

## 🌐 Running the Services

### 1. FastAPI Server & Web Dashboard

Start the local server with hot-reloading:

```bash
uvicorn app.main:app --reload --port 8000
```

Once running:
- **Interactive Web Dashboard**: [http://localhost:8000/dashboard](http://localhost:8000/dashboard) or [http://localhost:8000/](http://localhost:8000/)
- **Interactive OpenAPI Documentation (Swagger UI)**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc Documentation**: [http://localhost:8000/redoc](http://localhost:8000/redoc)
- **Health Check**: [http://localhost:8000/health](http://localhost:8000/health)

### 2. Slack Bot (Socket Mode)

Start the Slack Bolt listener in Socket Mode:

```bash
python run_slack_bot.py
```

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
| `GET` | `/dashboard` or `/` | Interactive web dashboard |
| `GET` | `/health` | Service health check |
