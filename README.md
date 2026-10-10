# AI Team Alignment Platform — Backend & Multi-Agent System

An AI-powered team alignment platform built for hackathons and fast-moving teams. The platform functions as an **AI teammate** that identifies hidden disagreements, compares individual perspectives, detects contradictory expectations, and collaboratively facilitates consensus.

Focuses exclusively on backend architecture and multi-agent AI functionality using **Google Agent Development Kit (ADK)**, **Google Gemini**, and **FastAPI**.

For detailed setup, architecture, and API documentation, please refer to [backend/README.md](file:///Users/charvidesai/Mediator-./Mediator-./backend/README.md).

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
# Add your GEMINI_API_KEY if available (optional: fallback mock mode runs automatically)

# 4. Run the interactive demonstration scenario (Alex, Sam, Taylor)
python backend/run_scenario.py

# 5. Run test suite
pytest backend/tests -v

# 6. Start FastAPI dev server
uvicorn backend.app.main:app --reload --port 8000
```

Open interactive Swagger UI at: [http://localhost:8000/docs](http://localhost:8000/docs)
