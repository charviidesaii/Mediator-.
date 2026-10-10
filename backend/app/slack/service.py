"""Slack Integration Service for Mediator.

Provides:
- Channel to project workspace mapping
- Slack message history extraction and conversation cleaning
- Ingestion of teammate messages into structured perspectives
- Rich Slack thread formatting for alignment reports and compromise proposals
- Strict governance: AI proposals are NEVER auto-approved without human sign-off
"""

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from app.config import settings
from app.models.schemas import (
    AlignmentWorkflowResult,
    ConflictSeverity,
    MemberResponseSubmit,
    Project,
    TeamMemberCreate,
)
from app.services.analysis import analysis_service
from app.services.supabase import storage_service

logger = logging.getLogger(__name__)


class SlackIntegrationService:
    """Service handling Slack conversation parsing, project binding, and report rendering."""

    def __init__(self):
        self._user_cache: Dict[str, str] = {}

    async def get_or_create_project_for_channel(
        self, channel_id: str, channel_name: Optional[str] = None
    ) -> Project:
        """Retrieves or auto-creates a Mediator project workspace mapped to a Slack channel."""
        return await storage_service.get_or_create_project_for_channel(
            channel_id=channel_id, channel_name=channel_name
        )

    async def resolve_user_name(self, client: Any, user_id: str) -> str:
        """Resolves a Slack user ID to a human-friendly display name with caching."""
        if user_id in self._user_cache:
            return self._user_cache[user_id]

        if not client:
            return f"User_{user_id[:6]}"

        try:
            res = client.users_info(user=user_id)
            if res.get("ok"):
                profile = res.get("user", {}).get("profile", {})
                display_name = (
                    profile.get("display_name")
                    or profile.get("real_name")
                    or res.get("user", {}).get("name")
                    or user_id
                )
                self._user_cache[user_id] = display_name.strip()
                return self._user_cache[user_id]
        except Exception as e:
            logger.warning(f"Failed to resolve Slack user ID {user_id}: {e}")

        fallback = f"User_{user_id[:6]}"
        self._user_cache[user_id] = fallback
        return fallback

    def clean_slack_text(self, text: str) -> str:
        """Removes Slack user mention tags (e.g. <@U12345>) and extra whitespace."""
        # Remove user mentions <@U...>
        cleaned = re.sub(r"<@[A-Z0-9]+>", "", text)
        # Convert channel links <#C123|general> to #general
        cleaned = re.sub(r"<#[A-Z0-9]+\|([^>]+)>", r"#\1", cleaned)
        # Convert URLs <https://...|label> to label
        cleaned = re.sub(r"<(https?://[^|>]+)\|([^>]+)>", r"\2", cleaned)
        # Remove standalone URLs brackets
        cleaned = re.sub(r"<(https?://[^>]+)>", r"\1", cleaned)
        return cleaned.strip()

    async def extract_channel_context(
        self,
        client: Any,
        channel_id: str,
        thread_ts: Optional[str] = None,
        limit: int = 25,
        bot_user_id: Optional[str] = None,
    ) -> List[Tuple[str, str]]:
        """Extracts substantive human messages from a channel or thread.

        Returns a list of tuples: (member_name, cleaned_statement)
        """
        extracted: List[Tuple[str, str]] = []

        try:
            if thread_ts:
                # Fetch replies within the active thread
                resp = client.conversations_replies(
                    channel=channel_id,
                    ts=thread_ts,
                    limit=limit,
                )
            else:
                # Fetch recent channel messages
                resp = client.conversations_history(
                    channel=channel_id,
                    limit=limit,
                )

            messages = resp.get("messages", [])
            # Guarantee chronological ordering by timestamp
            messages = sorted(messages, key=lambda m: float(m.get("ts", 0)))

            for msg in messages:
                user = msg.get("user")
                text = msg.get("text", "")
                subtype = msg.get("subtype")
                is_bot = bool(msg.get("bot_id")) or (bot_user_id and user == bot_user_id)

                # Skip bot messages, channel join/leave notifications, or empty messages
                if is_bot or subtype or not user or not text:
                    continue

                cleaned = self.clean_slack_text(text)
                # Ignore very short greetings or bot triggering command lines
                if len(cleaned) < 5 or cleaned.lower() in ["help", "status", "ping", "analyze"]:
                    continue

                user_name = await self.resolve_user_name(client, user)
                extracted.append((user_name, cleaned))

        except Exception as e:
            logger.error(f"Error fetching Slack messages from channel {channel_id}: {e}")
            raise

        return extracted

    async def ingest_messages_into_project(
        self,
        project_id: str,
        messages: List[Tuple[str, str]],
        source: str = "slack",
    ) -> int:
        """Ingests extracted statements into the project workspace, ensuring members exist."""
        project = await storage_service.get_project(project_id)
        if not project:
            raise ValueError(f"Project with ID '{project_id}' not found.")

        existing_members = {m.name.lower(): m for m in project.members}
        added_count = 0

        for user_name, text in messages:
            # Register member if not already registered
            if user_name.lower() not in existing_members:
                try:
                    new_member = await storage_service.add_team_member(
                        project_id=project_id,
                        member_in=TeamMemberCreate(name=user_name, role="Slack Participant"),
                    )
                    if new_member:
                        existing_members[user_name.lower()] = new_member
                except Exception as mem_err:
                    logger.debug(f"Member {user_name} already registered or conflict: {mem_err}")

            # Store the perspective response
            try:
                await storage_service.add_response(
                    project_id=project_id,
                    member_name=user_name,
                    raw_text=text,
                    source=source,
                )
                added_count += 1
            except Exception as resp_err:
                logger.warning(f"Error storing response from {user_name}: {resp_err}")

        return added_count

    async def run_analysis_for_channel(
        self,
        channel_id: str,
        channel_name: Optional[str] = None,
        client: Optional[Any] = None,
        thread_ts: Optional[str] = None,
        bot_user_id: Optional[str] = None,
    ) -> AlignmentWorkflowResult:
        """Complete workflow: extract Slack context -> ingest -> run multi-agent analysis."""
        project = await self.get_or_create_project_for_channel(channel_id, channel_name)

        # If client is provided, harvest recent messages
        if client:
            messages = await self.extract_channel_context(
                client=client,
                channel_id=channel_id,
                thread_ts=thread_ts,
                bot_user_id=bot_user_id,
            )
            if messages:
                await self.ingest_messages_into_project(project.id, messages, source="slack")

        # Run multi-agent pipeline
        return await analysis_service.trigger_analysis(project.id)

    def format_slack_analysis(
        self,
        result: AlignmentWorkflowResult,
        project_id: str,
    ) -> Dict[str, Any]:
        """Constructs Slack Block Kit blocks and markdown text for the alignment summary."""
        synth = result.synthesis_output
        conflicts = result.conflicts_output.conflicts
        score = synth.alignment_score
        dashboard_url = f"{settings.dashboard_base_url.rstrip('/')}/?project_id={project_id}"

        # Status emoji based on alignment score
        if score >= 80:
            status_emoji = "🟢 *High Alignment*"
        elif score >= 50:
            status_emoji = "🟡 *Partial Misalignment Detected*"
        else:
            status_emoji = "🔴 *Critical Misalignments Detected*"

        blocks: List[Dict[str, Any]] = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "🤖 Mediator — Team Alignment Analysis",
                    "emoji": True,
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"{status_emoji} — *Score: {score:.1f}/100*\n"
                        f"{synth.executive_summary}\n\n"
                        f"📊 *Mode*: `{result.execution_mode}` | *Duration*: `{result.execution_metadata.get('duration_seconds', 0)}s`"
                    ),
                },
            },
            {"type": "divider"},
        ]

        # 1. Detected Conflicts Section
        if conflicts:
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"⚠️ *Detected Misalignments & Conflicts ({len(conflicts)})*:",
                },
            })

            for c in conflicts[:4]:  # Show up to 4 top conflicts to avoid block size overflow
                sev_icon = "🔴" if c.severity == ConflictSeverity.HIGH else "🟡"
                evidence_lines = []
                for ev in c.evidence:
                    evidence_lines.append(f"> • *{ev.member_name}*: \"{ev.quote}\" — _{ev.interpretation}_")
                evidence_text = "\n".join(evidence_lines)

                blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": (
                            f"{sev_icon} *[{c.conflict_id}] {c.title}*\n"
                            f"*Parties*: {', '.join(c.parties_involved)} | *Severity*: `{c.severity.value}`\n"
                            f"{c.severity_reasoning}\n\n"
                            f"*Evidence*:\n{evidence_text}"
                        ),
                    },
                })
        else:
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "✅ *No direct blocking contradictions were detected across submitted statements!*",
                },
            })

        blocks.append({"type": "divider"})

        # 2. AI-Proposed Compromises Section
        if synth.proposed_resolutions:
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"💡 *AI-Proposed Compromises ({len(synth.proposed_resolutions)})*:",
                },
            })

            for r in synth.proposed_resolutions[:3]:
                questions_lines = "\n".join([f"> ? {q}" for q in r.unresolved_questions_for_team[:2]])
                blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": (
                            f"📌 *[{r.resolution_id}] For {r.conflict_title}*:\n"
                            f"*{r.recommended_solution}*\n\n"
                            f"_Rationale_: {r.reasoning}\n"
                            f"*Open Questions for Consensus*:\n{questions_lines}"
                        ),
                    },
                })

        # 3. Governance Notice & Dashboard CTA Link
        blocks.extend([
            {"type": "divider"},
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": (
                            "🔒 *Governance Guardrail*: Resolutions are strictly AI proposals and are *never* "
                            "automatically approved or enforced without explicit human confirmation."
                        ),
                    }
                ],
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"👉 *<https://localhost:8000/?project_id={project_id}|Open Mediator Dashboard>*\n_Review full evidence citations, compare alternative options, and record team decisions._",
                },
                "accessory": {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "Open Dashboard",
                        "emoji": True,
                    },
                    "url": dashboard_url,
                    "action_id": "open_dashboard_button",
                },
            },
        ])

        # Fallback markdown text
        fallback_text = (
            f"🤖 *Mediator Analysis Complete* (Alignment Score: {score:.1f}/100)\n"
            f"{synth.executive_summary}\n"
            f"Review conflicts and approve compromises at: {dashboard_url}"
        )

        return {
            "blocks": blocks,
            "text": fallback_text,
        }


slack_service = SlackIntegrationService()
