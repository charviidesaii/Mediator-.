# Mediator — Integration & E2E Testing Documentation

## Executive Summary
This document records all architectural improvements, bug fixes, integration setups, and testing results completed for the **Mediator AI Team Alignment Platform**.

---

## 1. Phase 1: API Configuration & Environment Modes

### Problems Addressed
* [client.ts](file:///Users/davidtakang/Mediator-./frontend/src/api/client.ts) previously hardcoded `https://mediator.free.beeceptor.com`, routing all requests to Beeceptor without environment fallback.
* No environment-specific files existed for distinguishing mock mode from live mode.
* When live API calls failed, errors could cause undefined state.

### Changes & Solutions
* **Environment Files**:
  * [frontend/.env.mock](file:///Users/davidtakang/Mediator-./frontend/.env.mock): Points to `https://mediator.free.beeceptor.com` with `VITE_APP_MODE=mock`.
  * [frontend/.env.live](file:///Users/davidtakang/Mediator-./frontend/.env.live): Points to `http://localhost:8000` with `VITE_APP_MODE=live`.
* **Dynamic API Client**:
  * [client.ts](file:///Users/davidtakang/Mediator-./frontend/src/api/client.ts) reads `VITE_API_BASE_URL` dynamically, allowing custom HTTPS deployment URLs.
  * Exports `appMode` (`"mock" | "live"`), `isMock`, and `isLive`.
  * Throws explicit `ApiError` when plain-text or unconfigured responses are returned.
* **UI Mode Badges**:
  * Header displays `[🟡 MOCK MODE (Beeceptor)]` when in mock mode.
  * Header displays `[🟢 LIVE MODE (FastAPI)]` when connected to local/deployed FastAPI.
  * Displays `[🔴 API Offline]` with an explicit connection error banner and **Retry** button when the backend is unreachable.
  * **Fail-Safe**: Never silently substitutes fake data when the live backend fails.
* **NPM Scripts**:
  * `npm run dev:mock` runs Vite with `--mode mock`.
  * `npm run dev:live` runs Vite with `--mode live`.

---

## 2. Phase 2: Beeceptor Mock Service Specification

Beeceptor functions as the decoupled mock testing service. The table below outlines all endpoints defined in [openapi.json](file:///Users/davidtakang/Mediator-./openapi.json):

| Method | Path | Status | Response Content-Type | Description |
| :--- | :--- | :--- | :--- | :--- |
| `GET` | `/health` | `200 OK` | `application/json` | System health & model status |
| `GET` | `/api/projects` | `200 OK` | `application/json` | List project workspaces |
| `POST` | `/api/projects` | `201 Created` | `application/json` | Create new project workspace |
| `GET` | `/api/projects/{id}` | `200 OK` | `application/json` | Retrieve single project workspace |
| `POST` | `/api/projects/{id}/members` | `201 Created` | `application/json` | Register teammate into workspace |
| `POST` | `/api/projects/{id}/responses` | `201 Created` | `application/json` | Submit perspective statement |
| `GET` | `/api/projects/{id}/responses` | `200 OK` | `application/json` | List all submitted perspectives |
| `POST` | `/api/projects/{id}/analyze` | `200 OK` | `application/json` | Trigger multi-agent AI analysis |
| `GET` | `/api/projects/{id}/alignment` | `200 OK` | `application/json` | Retrieve latest synthesis report |
| `POST` | `/api/projects/{id}/decisions` | `201 Created` | `application/json` | Human APPROVE/MODIFY/REJECT action |
| `GET` | `/api/projects/{id}/decisions` | `200 OK` | `application/json` | List confirmed human commitments |

> **Stateful vs. Stateless Note**: Beeceptor static mocks do not persist writes across requests. For end-to-end multi-agent alignment and SQLite data persistence, use Live Mode (`http://localhost:8000`).

---

## 3. Phase 3: Slack Bolt Integration Fix

### Bug Resolved
* **Unimported Service**: In [bot.py](file:///Users/davidtakang/Mediator-./backend/app/slack/bot.py), `handle_app_mention` invoked `analysis_service.trigger_analysis(...)` without importing `analysis_service`, causing a runtime `NameError`.
* **Fix**: Imported `from app.services.analysis import analysis_service`.
* **Eager Auth Avoidance**: Set `token_verification_enabled=False` on `App` initialization so local testing does not trigger synchronous network authentication errors.
* **Test Coverage**: Added `test_slack_handle_app_mention_executes_analysis_service` in [test_slack_bot.py](file:///Users/davidtakang/Mediator-./backend/tests/test_slack_bot.py).

---

## 4. Phase 4: n8n Post-Decision Automation

### Architecture & Behavior
1. **Configurable Endpoint**: `N8N_WEBHOOK_URL` in [config.py](file:///Users/davidtakang/Mediator-./backend/app/config.py) (configured to `https://dtakang.app.n8n.cloud/webhook/mediator-decision`).
2. **Outbound Dispatcher**: [n8n.py](file:///Users/davidtakang/Mediator-./backend/app/services/n8n.py) sends structured payloads:
   ```json
   {
     "event_id": "evt_xxxxxxxxxxxx",
     "event_type": "decision.approved",
     "project_id": "proj_42",
     "resolution_id": "res_7",
     "decision_text": "Ship v2 API on Friday",
     "decided_by": "david@mediator.app",
     "timestamp": "2026-10-10T17:55:00Z"
   }
   ```
3. **Governance Guardrails**:
   * Fires **only** on `APPROVE` (`decision.approved`) and `MODIFY` (`decision.modified`).
   * Never fires for `REJECT` or unapproved proposals.
4. **Fault Tolerance**:
   * Uses FastAPI `BackgroundTasks`.
   * Webhook delivery errors do not roll back or compromise the saved decision in SQLite.
5. **Importable Workflow**:
   * Workflow specification stored in [integrations/n8n/mediator_decision_workflow.json](file:///Users/davidtakang/Mediator-./integrations/n8n/mediator_decision_workflow.json).
   * Includes nodes for validation, deduplication, Beeceptor audit logging, and Slack announcements.

---

## 5. Verification & Test Suite

All 40 automated tests pass with 100% success rate:
```bash
./venv/bin/pytest backend/tests/ -v
# 40 passed in 2.44s
```

Test coverage includes:
- Agent pipelines: `PerspectiveAgent`, `ConflictAgent`, `ResolutionAgent`
- Decision governance and resolution validation
- Channel mapping and SQLite persistence across restarts
- Slack message parsing, loop prevention, and mention handling
- n8n webhook schema formatting, rejection filtering, and fault tolerance
- FastAPI dashboard serving and content negotiation
