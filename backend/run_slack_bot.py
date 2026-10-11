#!/usr/bin/env python3
"""Standalone runner for the Mediator Slack Bot using Socket Mode.

Usage:
    export SLACK_BOT_TOKEN="xoxb-..."
    export SLACK_APP_TOKEN="xapp-..."
    export SLACK_SIGNING_SECRET="..."
    export GEMINI_API_KEY="..."
    python backend/run_slack_bot.py
"""

import asyncio
import logging
import os
import sys

# Ensure backend directory is in sys.path
backend_dir = os.path.dirname(os.path.abspath(__file__))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.config import settings
from app.services.supabase import storage_service
from app.slack.bot import create_slack_app, start_slack_socket_mode

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("mediator_slack_bot")


def main():
    print("=" * 65)
    print("        MEDIATOR — SLACK BOLT SOCKET MODE DAEMON")
    print("=" * 65)

    if not settings.slack_bot_token:
        print("\n❌ Error: SLACK_BOT_TOKEN environment variable is missing!")
        print("Set your tokens in .env or shell environment:")
        print("  export SLACK_BOT_TOKEN='xoxb-...'")
        print("  export SLACK_APP_TOKEN='xapp-...'")
        print("  export SLACK_SIGNING_SECRET='...'")
        print("  export GEMINI_API_KEY='...'")
        sys.exit(1)

    if not settings.slack_app_token:
        print("\n❌ Error: SLACK_APP_TOKEN environment variable is missing!")
        print("Socket Mode requires an App-Level token beginning with 'xapp-'.")
        sys.exit(1)

    # Initialize and connect to shared persistent storage matching FastAPI backend
    asyncio.run(storage_service.initialize())
    print(f"Persistent Storage: {storage_service.db_path} [{settings.storage_backend}]")

    print(f"Connecting to Slack Workspace with Bot Token: {settings.slack_bot_token[:12]}...")
    print(f"Active Gemini Model: {settings.gemini_model}")
    print(f"Dashboard Base URL: {settings.dashboard_base_url}")
    print(f"Execution Mode: {'LIVE_GEMINI' if settings.is_live_gemini_available else 'MOCK_DETERMINISTIC'}\n")
    print("⚡ Socket Mode Handler active. Waiting for @Mediator mentions in Slack channels...\n")

    app = create_slack_app()
    handler = start_slack_socket_mode(app)
    if handler:
        try:
            handler.start()
        except KeyboardInterrupt:
            print("\nShutting down Slack Bot daemon...")


if __name__ == "__main__":
    main()
