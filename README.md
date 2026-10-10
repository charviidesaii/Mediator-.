# 🤝 Mediator — AI Team Alignment Platform & Slack Teammate

[![Tests](https://img.shields.io/badge/pytest-30%20passed-success)](backend/tests)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115%2B-009688)](https://fastapi.tiangolo.com/)
[![Google ADK](https://img.shields.io/badge/Google%20ADK-2.11%2B-4285F4)](https://github.com/google/agent-development-kit)
[![Slack Bolt](https://img.shields.io/badge/Slack%20Bolt-Socket%20Mode-4A154B)](https://slack.dev/bolt-python/)

**Mediator** is an AI teammate that surfaces hidden disagreements, compares individual team member perspectives, identifies contradictory deadlines, flags unassigned or conflicting responsibilities, and synthesizes actionable compromise resolutions — **while strictly preserving human authority over decisions**.

Built for hackathons and high-velocity engineering teams using **Google Agent Development Kit (ADK)**, **Google Gemini**, **FastAPI**, **Slack Bolt (Socket Mode)**, and persistent local storage.

---

## 📑 Table of Contents

- [Core Features](#-core-features)
- [Architecture & Multi-Agent Pipeline](#-architecture--multi-agent-pipeline)
- [Quick Start](#-quick-start)
- [Environment Variables](#-environment-variables)
- [Running the Services](#-running-the-services)
  - [1. FastAPI Backend & Web Dashboard](#1-fastapi-backend--web-dashboard)
  - [2. Slack Bot (Socket Mode)](#2-slack-bot-socket-mode)
- [Slack App Setup & OAuth Configuration](#-slack-app-setup--oauth-configuration)
- [End-to-End Demo Scenario](#-end-to-end-demo-scenario)
- [Automated Test Suite](#-automated-test-suite)
- [API Reference](#-api-reference)
- [Known Limitations & Roadmap](#-known-limitations--roadmap)
- [Repository Deliverables](#-repository-deliverables)

---

## 🌟 Core Features

1. **Independent Perspective Submission**: Team members independently submit their project goals, deadlines, and responsibilities without being biased by others' inputs.
2. **Multi-Agent Conflict Detection**: Powered by Google ADK & Gemini to detect direct deadline clashes, sequencing inversions, and ownership ambiguities.
3. **Verbatim Evidence Citations**: Every detected conflict quotes the exact words submitted by teammates to maintain complete context and trust.
4. **Pragmatic Resolution Synthesis**: Generates compromise schedules, role clarifications, and open consensus questions with status strictly set to `PROPOSED`.
5. **Human Decision Gate**: AI never automatically overrides or commits decisions. Teammates must explicitly `APPROVE`, `MODIFY`, or `REJECT` proposed resolutions.
6. **Slack Teammate Integration**: Mention `@Mediator` in any project channel to pull recent discussion context, identify misaligned expectations, and post an alignment report directly into the thread with a link to the web dashboard.
7. **Transparent Execution Modes**: Clearly labels whether the analysis ran via `LIVE_GEMINI` or deterministic `MOCK_FALLBACK` (no silent mock masking).

---

## 🤖 Architecture & Multi-Agent Pipeline

```
                                 [ Team Perspectives ]
                          (Web Dashboard or Slack Channel)
                                         │
                                         ▼
                 ┌─────────────────────────────────────────────────┐
                 │       Agent 1: Perspective Analysis Agent       │
                 │            (Google ADK / Gemini)                │
                 │ Extracts individual goals, priorities, dates,   │
                 │ and task ownership with verbatim citations.     │
                 └───────────────────────┬─────────────────────────┘
                                         │
                                         ▼
                 ┌─────────────────────────────────────────────────┐
                 │         Agent 2: Conflict Detection Agent       │
                 │            (Google ADK / Gemini)                │
                 │ Compares viewpoints to find deadline clashes,   │
                 │ sequencing errors, and ownership overlaps/gaps. │
                 └───────────────────────┬─────────────────────────┘
                                         │
                                         ▼
                 ┌─────────────────────────────────────────────────┐
                 │        Agent 3: Resolution & Synthesis Agent    │
                 │            (Google ADK / Gemini)                │
                 │ Synthesizes compromises & discussion questions. │
                 │ All suggestions marked status="PROPOSED".       │
                 └───────────────────────┬─────────────────────────┘
                                         │
                                         ▼
                 ┌─────────────────────────────────────────────────┐
                 │              Human Decision Gate                │
                 │   Teammates sign off on resolutions via UI/API  │
                 │  Only human-approved items become commitments!  │
                 └─────────────────────────────────────────────────┘
```

---

## ⚡ Quick Start

### 1. Clone & Set Up Virtual Environment

```bash
git clone https://github.com/tsunderii/mediator-jc.git
cd mediator-jc

# Create and activate Python virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies (FastAPI, Google ADK, Google GenAI, Slack Bolt, SQLite)
pip install -r requirements.txt
```

### 2. Configure Environment

Copy `.env.example` to `.env`:

```bash
cp .env.example .env
```

Edit `.env` with your settings:

```env
# Optional for live AI (defaults to offline deterministic mock if omitted)
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-2.5-flash

# Optional for Slack Bot integration
SLACK_BOT_TOKEN=xoxb-your-bot-token
SLACK_APP_TOKEN=xapp-your-app-token
SLACK_SIGNING_SECRET=your-signing-secret
DASHBOARD_BASE_URL=http://localhost:8000
```

---

## ⚙️ Environment Variables

| Variable | Description | Required? | Default |
|---|---|---|---|
| `GEMINI_API_KEY` | Google AI Studio API key | Optional | Offline deterministic mock if absent |
| `GEMINI_MODEL` | Gemini model name | No | `gemini-2.5-flash` |
| `MOCK_LLM` | Force offline deterministic mock runner | No | `false` |
| `SLACK_BOT_TOKEN` | Slack Bot User OAuth Token (`xoxb-...`) | For Slack Bot | None |
| `SLACK_APP_TOKEN` | Slack App-Level Token (`xapp-...`) | For Slack Bot | None |
| `SLACK_SIGNING_SECRET`| Slack Signing Secret | For Slack Bot | None |
| `DASHBOARD_BASE_URL` | Base URL included in Slack thread links | No | `http://localhost:8000` |
| `SQLITE_DB_PATH` | Persistent SQLite database location | No | `data/mediator.db` |
| `PORT` | FastAPI server listening port | No | `8000` |

---

## 🚀 Running the Services

### 1. FastAPI Backend & Web Dashboard

Start the backend server:

```bash
# From workspace root
uvicorn backend.app.main:app --reload --port 8000
```

Once running:
- **Interactive Web Dashboard**: Open [http://localhost:8000/dashboard](http://localhost:8000/dashboard) or [http://localhost:8000/](http://localhost:8000/) in your browser.
  - Create projects, manage team members, submit responses.
  - Run multi-agent alignment with a single click.
  - View agreement scores, conflicts with verbatim evidence, and resolution options.
  - Sign off on resolutions (`Approve`, `Modify`, `Reject`) to generate binding commitments.
- **Interactive Swagger API Documentation**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **Health Check**: [http://localhost:8000/health](http://localhost:8000/health)

### 2. Slack Bot (Socket Mode)

To run Mediator inside your Slack workspace:

```bash
# Ensure SLACK_BOT_TOKEN and SLACK_APP_TOKEN are set in .env
python backend/run_slack_bot.py
```

Because Mediator uses **Slack Socket Mode**, no public tunnels (ngrok) or webhooks are needed. The bot connects securely via WebSocket.

---

## 💬 Slack App Setup & OAuth Configuration

Follow these steps to configure your Slack app:

1. Go to [api.slack.com/apps](https://api.slack.com/apps) and click **Create New App** > **From scratch**.
2. Name the app **Mediator** and select your workspace.
3. **Enable Socket Mode**:
   - Go to **Socket Mode** in the sidebar and toggle **Enable Socket Mode** to `On`.
   - When prompted, create an **App-Level Token** with the `connections:write` scope. Name it `socket-mode`.
   - Copy this token (`xapp-...`) and set it as `SLACK_APP_TOKEN` in your `.env`.
4. **Configure Bot Token Scopes**:
   - Go to **OAuth & Permissions** in the sidebar.
   - Under **Bot Token Scopes**, add the following OAuth scopes:
     - `app_mentions:read` (detects `@Mediator` mentions in channels)
     - `channels:history` (reads messages in public channels the bot is added to)
     - `groups:history` (reads messages in private channels the bot is added to)
     - `chat:write` (replies in message threads)
     - `users:read` (resolves Slack user IDs to teammate real names)
     - `im:history` (optional, for direct messages)
5. **Enable Event Subscriptions**:
   - Go to **Event Subscriptions** in the sidebar and toggle **Enable Events** to `On`.
   - Under **Subscribe to bot events**, add:
     - `app_mention`
   - Save changes.
6. **Install App to Workspace**:
   - Go to **Install App** in the sidebar and click **Install to Workspace**.
   - Copy the **Bot User OAuth Token** (`xoxb-...`) and set it as `SLACK_BOT_TOKEN` in `.env`.
   - Under **Basic Information**, copy the **Signing Secret** and set it as `SLACK_SIGNING_SECRET` in `.env`.
7. **Using the Bot in Slack**:
   - In any channel, invite the bot: `/invite @Mediator`
   - Discuss your project plans (e.g., Alex notes Saturday deployment, Taylor notes QA needs).
   - Trigger analysis by mentioning: `@Mediator what are our current misalignments?`
   - The bot responds in the thread with detected conflicts, evidence quotes, and a direct link to the dashboard.

---

## 🎭 End-to-End Demo Scenario

A pre-built demonstration scenario featuring three fictional teammates with conflicting plans:
- **Alex (Frontend Lead)**: Believes the launch deadline is Saturday; believes Taylor owns deployment.
- **Sam (Backend Lead)**: Believes the launch deadline is Sunday.
- **Taylor (DevOps/QA Lead)**: Believes Alex owns deployment; insists on a mandatory 24-hour QA window before release.

### Run the CLI Demo

```bash
python backend/run_scenario.py
```

### What the Demo Validates:
1. **Perspective Extraction**: Alex, Sam, and Taylor's independent inputs are processed and milestones extracted.
2. **Conflict Detection**:
   - Direct deadline clash detected: Saturday launch vs Sunday target (`HIGH` severity).
   - Responsibility gap detected: Both Alex and Taylor believe the other owns deployment (`HIGH` severity).
   - Unbudgeted testing window detected: Taylor's QA prerequisite vs immediate launch (`MEDIUM` severity).
3. **Resolution Synthesis**:
   - Recommends a compromise schedule (e.g. Code freeze Saturday 18:00, QA window Sunday morning, launch Sunday 16:00).
   - Proposes explicit deployment ownership division (Taylor owns deployment pipeline, Alex owns deployment smoke testing).
4. **Human Decision Gate**:
   - Teammates review the proposal.
   - One resolution is approved and one modified to demonstrate consensus tracking.
   - Confirmed decisions are stored as binding commitments.
5. **Persistence Across Restarts**:
   - All projects, responses, and confirmed decisions persist in SQLite (`data/mediator.db`).

---

## 🧪 Automated Test Suite

Run the full pytest suite (30 passing tests):

```bash
pytest backend/tests -v
```

### Test Coverage Highlights:
- `test_perspective_agent.py`: Goal and deadline extraction, evidence preservation, ambiguity handling.
- `test_conflict_agent.py`: Deadline contradictions, testing dependency gaps, severity scoring.
- `test_resolution_agent.py`: Compromise synthesis, governance safety invariant (`status="PROPOSED"`).
- `test_alignment_workflow.py`: End-to-end multi-agent pipeline orchestration and output aggregation.
- `test_api_endpoints.py`: REST routes for projects, responses, analysis, and human decision sign-offs.
- `test_demo_scenario.py`: Full Alex/Sam/Taylor lifecycle test including decision modification and database reload.
- `test_slack_bot.py`: Context cleaning, mention stripping, chronological message ordering, channel-to-project mapping, Block Kit formatting, and event deduplication.

---

## 📡 REST API Reference

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/projects` | Create a new project workspace |
| `GET` | `/api/projects` | List all projects |
| `GET` | `/api/projects/{id}` | Retrieve project details & member roster |
| `POST` | `/api/projects/{id}/members` | Add a team member to a project |
| `POST` | `/api/projects/{id}/responses` | Submit an individual teammate's perspective |
| `GET` | `/api/projects/{id}/responses` | List all submitted perspectives |
| `POST` | `/api/projects/{id}/analyze` | Trigger the multi-agent alignment workflow |
| `GET` | `/api/projects/{id}/alignment` | Retrieve the latest synthesis report & resolutions |
| `POST` | `/api/projects/{id}/decisions` | Approve, reject, or modify proposed resolutions |
| `GET` | `/api/projects/{id}/decisions` | Retrieve confirmed binding project decisions |
| `GET` | `/dashboard` or `/` | Access the browser-based interactive web dashboard |
| `GET` | `/health` | Service health status check |

For complete schemas and OpenAPI specification, see [openapi.json](openapi.json) or visit `/docs` when the backend is running.

---

## ⚠️ Known Limitations & Roadmap

- **Mention-Triggered Workflow**: The Slack bot currently operates via explicit `@Mediator` mentions. Continuous passive channel scanning is deliberately omitted to prevent excessive API costs and respect team privacy.
- **Human Invariant**: In accordance with the governance charter, neither the backend nor the Slack bot can automatically finalize or sign off on decisions. Human interaction via the Web Dashboard or API is required.
- **LLM Rate Limits & Fallback**: If a live Gemini API key encounters quota limits, the system transparently indicates `MOCK_FALLBACK: <reason>` in the synthesis report so teams always know the provenance of the analysis.
- **Slack Block Kit Action Handlers**: Direct in-Slack button approval (`block_actions`) is designed and can be enabled with interactive webhook endpoints; in Socket Mode, teammates use the dashboard link for full auditability.

---

## 📚 Repository Deliverables

- [API_INTEGRATION_GUIDE.md](API_INTEGRATION_GUIDE.md): REST contracts and frontend connection guide.
- [BACKEND_AUDIT_REPORT.md](BACKEND_AUDIT_REPORT.md): Initial architectural audit report.
- [BACKEND_FIXES.md](BACKEND_FIXES.md): Changelog of bug fixes and enhancements.
- [TEST_RESULTS.md](TEST_RESULTS.md): Test verification matrix and scenario results.
- [openapi.json](openapi.json): Exported OpenAPI v3.1 specification.
