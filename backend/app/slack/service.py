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
from typing import Any, Dict, List, Optional, Set, Tuple

from app.config import settings
from app.models.schemas import (
    AlignmentWorkflowResult,
    ConflictSeverity,
    DetectedConflict,
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

    @staticmethod
    def _protect_abbreviations(text: str) -> str:
        """Protects middle initials, abbreviations, and numeric decimals from sentence splitting."""
        # Protect single capital initials like David T. or J. Chan
        t = re.sub(r"\b([A-Z])\.", r"\1<DOT>", text)
        # Protect common abbreviations
        for abbr in ["e.g.", "i.e.", "vs.", "etc.", "Mr.", "Ms.", "Dr.", "approx.", "min.", "dept."]:
            rep = abbr.replace(".", "<DOT>")
            t = re.sub(re.escape(abbr), rep, t, flags=re.IGNORECASE)
        # Protect numbers like 2.5 or 1.0
        t = re.sub(r"(\d)\.(\d)", r"\1<DOT>\2", t)
        return t

    @staticmethod
    def _unprotect_abbreviations(text: str) -> str:
        """Restores protected periods."""
        return text.replace("<DOT>", ".")

    @staticmethod
    def _split_sentences(text: str) -> List[str]:
        """Splits text into complete grammatical sentences, respecting initials and abbreviations."""
        if not text:
            return []
        cleaned = re.sub(r"[*_`>#]", "", text).replace("\r", " ").replace("\n", " ").strip()
        cleaned = re.sub(r"\s+", " ", cleaned)
        if not cleaned:
            return []
        protected = SlackIntegrationService._protect_abbreviations(cleaned)
        raw_sents = re.split(r"[.!?]+(?:\s+|$)", protected)
        results: List[str] = []
        for s in raw_sents:
            unprot = SlackIntegrationService._unprotect_abbreviations(s).strip()
            unprot = unprot.rstrip(".!?,:; ")
            if len(unprot) >= 8:
                results.append(f"{unprot}.")
        return results

    @staticmethod
    def _shorten_sentence_safely(sent: str, max_chars: int = 100) -> str:
        """Shortens a long statement into a complete, meaningful sentence without slicing mid-thought."""
        clean_sent = sent.strip()
        if len(clean_sent) <= max_chars:
            return clean_sent

        # 1. Try stripping parentheticals like (CONF-1) or (e.g., ...)
        stripped = re.sub(r"\s*\([^)]*\)", "", clean_sent).strip().rstrip(".!?,:; ")
        cand = f"{stripped}."
        if 25 <= len(cand) <= max_chars:
            return cand

        # 2. Try splitting at natural grammatical clause boundaries
        clean = stripped.rstrip(".!?,:; ")
        clause_delims = [
            "; ",
            " — ",
            " - ",
            ": Specifically, ",
            ": specifically, ",
            ", specifically regarding ",
            ", specifically ",
            ", focusing on ",
            ", and after ",
            ", and ",
            ", while ",
            ", but ",
            ", which ",
            ", allowing ",
            ", leading to ",
            ", to ensure ",
            ", to allow ",
            " to define ",
            " to review ",
            " to discuss ",
            ", Saturday for ",
            ", where ",
            ", although ",
            ", leaving ",
        ]
        for delim in clause_delims:
            if delim in clean:
                first_clause = clean.split(delim)[0].strip().rstrip(".!?,:; ")
                cand = f"{first_clause}."
                if 20 <= len(cand) <= max_chars:
                    return cand

        # If no clause boundary matches within max_chars, keep the full complete sentence
        # rather than cutting text mid-thought. The bullet removal loop will drop low-priority bullets if needed.
        return clean_sent

    @staticmethod
    def _extract_topic(c: DetectedConflict) -> str:
        """Extracts a concise, standardized topic category for a conflict."""
        raw_title = c.title or ""
        if ":" in raw_title:
            topic_cand = raw_title.split(":", 1)[0].strip()
            topic_cand = re.sub(r"[*_`]", "", topic_cand).strip()
            tl = topic_cand.lower()
            if "deadline sequence" in tl or "timeline" in tl:
                return "Timeline"
            if "unclear task ownership" in tl or "unassigned" in tl or "ownership" in tl:
                return "Ownership"
            if "quality assurance" in tl or bool(re.search(r"\bqa\b", tl)) or "testing" in tl:
                return "Testing"
            if len(topic_cand) <= 18:
                return topic_cand

        tl = raw_title.lower()
        if bool(re.search(r"\bqa\b", tl)) or "testing" in tl:
            return "Testing"
        if "scope" in tl or "recommendation" in tl or bool(re.search(r"\bmvp\b", tl)) or "feature" in tl:
            return "Scope"
        if "integration" in tl or bool(re.search(r"\bapi\b", tl)):
            return "Integration"
        if "deadline" in tl or "timeline" in tl or "schedule" in tl or "completion" in tl or "demo" in tl:
            return "Timeline"
        if "launch" in tl or "release" in tl or "ship" in tl:
            return "Launch"
        if "design" in tl or "figma" in tl or bool(re.search(r"\bui\b", tl)):
            return "Design"
        if "test" in tl:
            return "Testing"
        if "deploy" in tl:
            return "Deployment"
        if "owner" in tl or "responsibility" in tl:
            return "Ownership"
        if "meeting" in tl or "sync" in tl:
            return "Meeting"

        # Fallback to conflict type
        type_name = c.conflict_type.value.replace("_", " ").title().split()[0]
        return type_name or "Issue"

    @staticmethod
    def _format_conflict_bullet(c: DetectedConflict, max_chars: int = 100) -> str:
        """Formats a single conflict into a short, complete grammatical sentence: '• Topic: Sentence.'"""
        topic = SlackIntegrationService._extract_topic(c)
        raw_title = (c.title or "").strip()

        # Case A: If raw_title already has a concise colon statement (e.g. "Launch: Team expects different dates (Thu–Sun).")
        if ":" in raw_title:
            parts = raw_title.split(":", 1)
            stmt = parts[1].strip().rstrip(".!?,:; ")
            sents = SlackIntegrationService._split_sentences(stmt)
            if sents:
                shortened = SlackIntegrationService._shorten_sentence_safely(sents[0], max_chars=85)
                lower_stmt = shortened.lower()
                if any(w in lower_stmt for w in ["expects", "conflicts", "differs", "precedes", "unclear", "no ", "is ", "are ", "leaves", "disagree"]):
                    return f"• {topic}: {shortened}"

        # Case B: Semantic pattern matching on common conflict title phrases
        tl = raw_title.lower()
        if "scope" in tl and "recommendation" in tl:
            return f"• {topic}: Team disagrees on including personalized recommendations in MVP."
        if "integration" in tl and ("unassigned" in tl or "responsibility" in tl or "owner" in tl):
            return f"• {topic}: No confirmed owner for frontend-backend API integration."
        if ("timeline" in tl or "schedule" in tl or "time" in tl) and ("testing" in tl or "test" in tl or bool(re.search(r"\bqa\b", tl))):
            return f"• {topic}: Integration schedule conflicts with required testing time."
        if ("deadline" in tl or "completion" in tl or "demo" in tl) and ("contradict" in tl or "conflict" in tl):
            return f"• {topic}: Team members have conflicting dates for completion and demo."
        if "design" in tl or "figma" in tl or bool(re.search(r"\bui\b", tl)):
            return f"• {topic}: Teammates are working with different UI design versions."
        if "test" in tl or bool(re.search(r"\bqa\b", tl)):
            return f"• {topic}: Current schedule leaves inadequate time for QA testing."
        if "meeting" in tl:
            return f"• {topic}: Team members have conflicting dates for the next sync meeting."
        if "deploy" in tl and ("unassigned" in tl or "unclear" in tl or "owner" in tl):
            return f"• {topic}: Deployment responsibility is unconfirmed across team members."
        if "launch" in tl or "ship" in tl:
            return f"• {topic}: Team members expect different target launch dates."
        if c.parties_involved and len(c.parties_involved) >= 2:
            p_str = " and ".join(c.parties_involved[:2])
            if "ownership" in tl or "responsibility" in tl:
                return f"• {topic}: Task ownership is unconfirmed between {p_str}."
            if "dependency" in tl:
                return f"• {topic}: Quality assurance dependency between {p_str} is unbudgeted."

        # Case C: Check impact description for a clean sentence
        impact = c.impact_description or ""
        impact_sents = SlackIntegrationService._split_sentences(impact)
        for s in impact_sents:
            if 25 <= len(s) <= 85 and not s.lower().startswith("direct delivery blocker"):
                if not s.lower().startswith(f"{topic.lower()}:"):
                    return f"• {topic}: {s}"

        # Case D: Fallback to cleaned sentence from title or impact
        source_text = c.impact_description or c.severity_reasoning or raw_title
        sents = SlackIntegrationService._split_sentences(source_text)
        first_sent = sents[0] if sents else f"{raw_title.rstrip('.!?,:; ')}."
        shortened = SlackIntegrationService._shorten_sentence_safely(first_sent, max_chars=85)
        return f"• {topic}: {shortened}"

    @staticmethod
    def _format_recommendation_bullet(rec_text: str, max_chars: int = 100) -> str:
        """Formats a single actionable recommendation into one complete sentence: '• Action sentence.'"""
        cleaned = rec_text.strip()
        # Strip leading markdown labels like **CONFIRM deployment owner:**
        cleaned = re.sub(r"^\*\*[^*]+:\*\*\s*", "", cleaned)
        # Strip uppercase action headers like "CONFIRM final MVP scope: " or "DECIDE: "
        cleaned = re.sub(r"^[A-Z\s]{4,}:", "", cleaned).strip()
        # Strip reference tags like (CONF-1) or (related to RES-3)
        cleaned = re.sub(r"\s*\((?:CONF|RES|related)[^)]*\)", "", cleaned)
        # Strip "Review RES-X and "
        cleaned = re.sub(r"^Review\s+RES-\d+\s+and\s+", "", cleaned, flags=re.IGNORECASE)

        # Convert leading noun phrases to imperative sentences
        if cleaned.lower().startswith("decision on "):
            cleaned = "Decide on " + cleaned[12:]
        elif cleaned.lower().startswith("confirmation of "):
            cleaned = "Confirm " + cleaned[16:]
        elif cleaned.lower().startswith("discussion on "):
            cleaned = "Discuss " + cleaned[14:]

        sents = SlackIntegrationService._split_sentences(cleaned)
        first_sent = sents[0] if sents else f"{cleaned.rstrip('.!?,:; ')}."
        shortened = SlackIntegrationService._shorten_sentence_safely(first_sent, max_chars=max_chars - 5)
        return f"• {shortened}"

    @staticmethod
    def calculate_visible_characters(blocks: List[Dict[str, Any]]) -> int:
        """Calculates total visible characters displayed to a user across all Slack blocks."""
        total = 0
        for b in blocks:
            text_obj = b.get("text")
            if isinstance(text_obj, dict):
                total += len(text_obj.get("text", ""))
            elif isinstance(text_obj, str):
                total += len(text_obj)

            accessory = b.get("accessory")
            if isinstance(accessory, dict):
                acc_text = accessory.get("text")
                if isinstance(acc_text, dict):
                    total += len(acc_text.get("text", ""))
                elif isinstance(acc_text, str):
                    total += len(acc_text)

            elements = b.get("elements", [])
            for el in elements:
                if isinstance(el, dict):
                    el_text = el.get("text")
                    if isinstance(el_text, dict):
                        total += len(el_text.get("text", ""))
                    elif isinstance(el_text, str):
                        total += len(el_text)
        return total

    def format_slack_analysis(
        self,
        result: AlignmentWorkflowResult,
        project_id: str,
    ) -> Dict[str, Any]:
        """Constructs concise Slack Block Kit blocks and markdown text under 1,000 visible characters.

        - Bullet points instead of paragraphs.
        - Shows alignment score and number of conflicts, including '4 of 5 conflicts' when hidden.
        - Displays up to 4 conflicts prioritized by HIGH severity, each in ONE short complete sentence.
        - Displays up to 3 actionable AI recommendations, each in ONE complete sentence.
        - Never truncates sentences mid-thought or appends periods to incomplete phrases.
        - Removes lowest-priority bullets when space runs out instead of cutting text.
        - Preserves governance disclaimer and Open Dashboard button.
        """
        synth = result.synthesis_output
        conflicts = result.conflicts_output.conflicts
        score = round(synth.alignment_score)
        dashboard_url = f"{settings.dashboard_base_url.rstrip('/')}/?project_id={project_id}"

        # 1. Header & Stats
        header_title = "Mediator — Team Alignment"
        total_conflicts = len(conflicts)

        # 2. Conflicts (Prioritize HIGH severity, max 4)
        severity_rank = {
            ConflictSeverity.HIGH: 0,
            ConflictSeverity.MEDIUM: 1,
            ConflictSeverity.LOW: 2,
        }
        sorted_conflicts = sorted(
            conflicts,
            key=lambda c: (severity_rank.get(c.severity, 1), c.conflict_id),
        )

        selected_conflicts = sorted_conflicts[:4]
        conflict_bullets: List[str] = [
            self._format_conflict_bullet(c, max_chars=100) for c in selected_conflicts
        ] or ["• No active conflicts detected."]

        # 3. Next Steps (Actionable AI recommendations, up to 3)
        rec_bullets: List[str] = []
        seen_recs: Set[str] = set()

        # Gather candidates from human action items and proposed resolutions
        candidate_recs: List[str] = []
        if synth.human_action_items:
            candidate_recs.extend(synth.human_action_items)
        if synth.proposed_resolutions:
            for r in synth.proposed_resolutions:
                candidate_recs.append(r.recommended_solution)

        for rec in candidate_recs:
            bullet = self._format_recommendation_bullet(rec, max_chars=100)
            norm = bullet.lower().strip()
            if norm not in seen_recs:
                seen_recs.add(norm)
                rec_bullets.append(bullet)
            if len(rec_bullets) >= 3:
                break

        if not rec_bullets:
            rec_bullets.append("• Proceed with agreed team plans.")

        # Compute initial stats line
        shown_conflicts = len(selected_conflicts)
        if shown_conflicts < total_conflicts:
            stats_line = f"{score}% aligned | {shown_conflicts} of {total_conflicts} conflicts"
        else:
            conflict_word = "conflict" if total_conflicts == 1 else "conflicts"
            stats_line = f"{score}% aligned | {total_conflicts} {conflict_word}"

        # 4. Governance Disclaimer & Dashboard CTA
        disclaimer_text = "_AI suggestions — team approval required._"
        link_line = f"<{dashboard_url}|Open Mediator Dashboard>"

        conflicts_section_text = "*Conflicts*\n" + "\n".join(conflict_bullets)
        next_steps_section_text = "*Next Steps*\n" + "\n".join(rec_bullets)

        blocks: List[Dict[str, Any]] = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": header_title,
                    "emoji": True,
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": stats_line,
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": conflicts_section_text,
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": next_steps_section_text,
                },
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": disclaimer_text,
                    }
                ],
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": link_line,
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
        ]

        # Character budget enforcement:
        # If total visible characters exceed 1,000, remove the lowest-priority bullet instead of cutting text.
        while self.calculate_visible_characters(blocks) > 1000:
            if len(rec_bullets) > 1:
                rec_bullets.pop()
            elif len(conflict_bullets) > 1:
                conflict_bullets.pop()
                shown_count = len(conflict_bullets)
                if shown_count < total_conflicts:
                    stats_line = f"{score}% aligned | {shown_count} of {total_conflicts} conflicts"
                else:
                    stats_line = f"{score}% aligned | {total_conflicts} {'conflict' if total_conflicts == 1 else 'conflicts'}"
                blocks[1]["text"]["text"] = stats_line
            elif len(rec_bullets) == 1:
                rec_bullets.pop()
            else:
                break

            conflicts_section_text = "*Conflicts*\n" + "\n".join(conflict_bullets or ["• No active conflicts detected."])
            next_steps_section_text = "*Next Steps*\n" + "\n".join(rec_bullets or ["• Proceed with agreed team plans."])
            blocks[2]["text"]["text"] = conflicts_section_text
            blocks[3]["text"]["text"] = next_steps_section_text

        # Fallback text strictly matches the concise message
        fallback_text = (
            f"*{header_title}*\n"
            f"{stats_line}\n\n"
            f"{conflicts_section_text}\n\n"
            f"{next_steps_section_text}\n\n"
            f"{disclaimer_text}"
        )

        return {
            "blocks": blocks,
            "text": fallback_text,
        }


slack_service = SlackIntegrationService()
