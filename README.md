# AI Team Alignment Platform — Backend & Multi-Agent System

An AI-powered team alignment platform built for hackathons and fast-moving teams. The platform functions as an **AI teammate** that identifies hidden disagreements, compares individual perspectives, detects contradictory expectations, and collaboratively facilitates consensus.

Focuses exclusively on backend architecture and multi-agent AI functionality using **Google Agent Development Kit (ADK)**, **Google Gemini**, and **FastAPI**.

For detailed setup, architecture, and API documentation, please refer to [backend/README.md](file:///Users/charvidesai/Mediator-./Mediator-./backend/README.md).

---

## 📚 Audit & Integration Deliverables

- **[BACKEND_AUDIT_REPORT.md](file:///Users/charvidesai/Mediator-./Mediator-./BACKEND_AUDIT_REPORT.md)**: Full audit of 8 defect areas (Google ADK runner execution, arbitrary participant generalization, persistent SQLite/Supabase storage, input sanitization, decision validation).
- **[BACKEND_FIXES.md](file:///Users/charvidesai/Mediator-./Mediator-./BACKEND_FIXES.md)**: Detailed changelog of all architectural and logic repairs.
- **[API_INTEGRATION_GUIDE.md](file:///Users/charvidesai/Mediator-./Mediator-./API_INTEGRATION_GUIDE.md)**: REST contracts, schemas, TypeScript client, and Figma Make connection guide.
- **[TEST_RESULTS.md](file:///Users/charvidesai/Mediator-./Mediator-./TEST_RESULTS.md)**: 24 automated pytest tests across 6 categories + live HTTP socket tests.
- **[openapi.json](file:///Users/charvidesai/Mediator-./Mediator-./openapi.json)**: Exported OpenAPI v3.1 specification for external tools.

---

## ⚡ Quick Start

```bash
# 1. Create and activate Python virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment
cp backend/.env.example .env
# Optional: add your GEMINI_API_KEY if available (fallback deterministic mock mode runs automatically)

# 4. Run the interactive demonstration scenario (Alex, Sam, Taylor)
python backend/run_scenario.py

# 5. Run test suite (24 automated tests across API, DB, AI, Security)
pytest backend/tests -v

# 6. Start FastAPI dev server
uvicorn backend.app.main:app --reload --port 8000
```

- **Interactive Swagger UI**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **Interactive Test UI Console**: [http://localhost:8000/test-ui](http://localhost:8000/test-ui)
- **Health Check**: [http://localhost:8000/health](http://localhost:8000/health)
