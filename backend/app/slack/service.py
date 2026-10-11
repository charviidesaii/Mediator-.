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
    ) -> List[Tuple[str, str, str]]:
        """Extracts substantive human messages from a channel or thread.

        Returns a list of tuples: (member_name, cleaned_statement, message_ts)
        """
        extracted: List[Tuple[str, str, str]] = []

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
                ts = str(msg.get("ts", ""))
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
                extracted.append((user_name, cleaned, ts))

        except Exception as e:
            logger.error(f"Error fetching Slack messages from channel {channel_id}: {e}")
            raise

        return extracted

    async def ingest_messages_into_project(
        self,
        project_id: str,
        messages: List[Any],
        source: str = "slack",
        channel_id: Optional[str] = None,
        storage: Optional[Any] = None,
    ) -> int:
        """Ingests extracted statements into the project workspace with deduplication and edit preservation."""
        store = storage or storage_service
        project = await store.get_project(project_id)
        if not project:
            raise ValueError(f"Project with ID '{project_id}' not found.")

        if not channel_id:
            mapping = await store.get_channel_mapping_for_project(project_id)
            if mapping:
                channel_id = mapping.get("channel_id")

        existing_responses = await store.get_responses(project_id)
        # Stable source identifier map: source -> MemberResponse
        existing_by_source: Dict[str, Any] = {
            r.source: r for r in existing_responses if r.source and r.source.startswith("slack:")
        }
        # Content deduplication set: (member_name.lower(), raw_text)
        existing_by_content: Set[Tuple[str, str]] = {
            (r.member_name.lower().strip(), r.raw_text.strip()) for r in existing_responses
        }

        existing_members = {m.name.lower(): m for m in project.members}
        added_count = 0

        for item in messages:
            if isinstance(item, (list, tuple)) and len(item) >= 3:
                user_name, text, msg_ts = item[0], item[1], str(item[2])
            elif isinstance(item, (list, tuple)) and len(item) == 2:
                user_name, text, msg_ts = item[0], item[1], None
            else:
                continue

            clean_user = user_name.strip()
            clean_text = text.strip()
            if not clean_text:
                continue

            # Stable identifier for Slack messages: slack:channel_id:msg_ts
            if msg_ts:
                stable_source = f"slack:{channel_id}:{msg_ts}" if channel_id else f"slack:{msg_ts}"
                if stable_source in existing_by_source:
                    existing_resp = existing_by_source[stable_source]
                    if existing_resp.raw_text.strip() == clean_text:
                        # Identical message already saved — skip duplicate
                        continue
                    else:
                        # Message was edited in Slack — update existing response
                        await store.update_response_text(existing_resp.id, clean_text)
                        existing_by_content.discard(
                            (existing_resp.member_name.lower().strip(), existing_resp.raw_text.strip())
                        )
                        existing_by_content.add((clean_user.lower(), clean_text))
                        existing_resp.raw_text = clean_text
                        continue
            else:
                stable_source = source

            # Content deduplication: skip if user already said this exact text
            if (clean_user.lower(), clean_text) in existing_by_content:
                continue

            # Register member if not already registered
            if clean_user.lower() not in existing_members:
                try:
                    new_member = await store.add_team_member(
                        project_id=project_id,
                        member_in=TeamMemberCreate(name=clean_user, role="Slack Participant"),
                    )
                    if new_member:
                        existing_members[clean_user.lower()] = new_member
                except Exception as mem_err:
                    logger.debug(f"Member {clean_user} already registered or conflict: {mem_err}")

            # Store the perspective response
            try:
                new_resp = await store.add_response(
                    project_id=project_id,
                    member_name=clean_user,
                    raw_text=clean_text,
                    source=stable_source,
                )
                added_count += 1
                existing_by_content.add((clean_user.lower(), clean_text))
                if msg_ts:
                    existing_by_source[stable_source] = new_resp
            except Exception as resp_err:
                logger.warning(f"Error storing response from {clean_user}: {resp_err}")

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
                await self.ingest_messages_into_project(
                    project.id, messages, source="slack", channel_id=channel_id
                )

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
            ": ",
            "; ",
            " — ",
            " - ",
            ": Specifically, ",
            ": specifically, ",
            ", specifically regarding ",
            ", specifically ",
            ", focusing on ",
            ", or ",
            ", and after ",
            ", and ",
            ", while ",
            ", but ",
            ", which ",
            ", allowing ",
            ", leading to ",
            " to establish ",
            " during the next sync ",
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
    def remove_technical_jargon(text: str) -> str:
        """Translates technical/engineering jargon into friendly, conversational teammate phrasing."""
        if not text:
            return ""
        t = text

        # Replace QA and testing jargon
        t = re.sub(r"\bQA\s+gate\b", "testing buffer", t, flags=re.IGNORECASE)
        t = re.sub(r"\bQA\s+testing\b", "testing", t, flags=re.IGNORECASE)
        t = re.sub(r"\bQA\s+dependency\b", "testing schedule", t, flags=re.IGNORECASE)
        t = re.sub(r"\bQA\s+engineers?\b", "testers", t, flags=re.IGNORECASE)
        t = re.sub(r"\bQA\b", "testing", t)
        t = re.sub(r"\bQuality\s+Assurance\b", "Testing", t, flags=re.IGNORECASE)
        t = re.sub(r"\bregression\s+(?:analysis|testing)\b", "testing", t, flags=re.IGNORECASE)

        # Replace dependency, architectural, and workflow jargon
        t = re.sub(r"\bdeadline\s+sequence\s+inversion\b", "misaligned order of tasks", t, flags=re.IGNORECASE)
        t = re.sub(r"\bdependency\s+inversion\b", "schedule conflict", t, flags=re.IGNORECASE)
        t = re.sub(r"\bprecedes\b", "comes before", t, flags=re.IGNORECASE)
        t = re.sub(r"\bunbudgeted\b", "unplanned", t, flags=re.IGNORECASE)
        t = re.sub(r"\blogistical\s+bottlenecks\b", "delays", t, flags=re.IGNORECASE)
        t = re.sub(r"\bsingle-owner\s+accountability\b", "clear ownership", t, flags=re.IGNORECASE)
        t = re.sub(r"\bsynchronized\s+milestone\s+schedule\b", "coordinated schedule", t, flags=re.IGNORECASE)
        t = re.sub(r"\bdeliverables\b", "tasks", t, flags=re.IGNORECASE)
        t = re.sub(r"\bdeliverable\b", "task", t, flags=re.IGNORECASE)

        # Clean multiple spaces
        t = re.sub(r"\s+", " ", t).strip()
        return t

    @staticmethod
    def _get_topic_and_icon(c: DetectedConflict) -> Tuple[str, str]:
        """Returns (emoji, conversational_topic_label) for a conflict."""
        raw_title = (c.title or "").strip()
        tl = raw_title.lower()
        impact = (c.impact_description or "").lower()
        full = f"{tl} {impact}"

        # 1. Project scope
        if any(w in full for w in ["scope", "recommendation", "mvp", "feature", "in-scope", "out-of-scope"]):
            return "🎯", "Project scope"

        # 2. Responsibilities / Ownership
        if any(w in full for w in ["owner", "ownership", "responsibility", "responsibilities", "unassigned", "accountability", "role"]):
            return "👥", "Responsibilities"

        # 3. Deadlines / Timeline
        if any(w in full for w in ["deadline", "timeline", "schedule", "completion date", "timeframe", "dates"]):
            # If testing or launch is explicit, prioritize those
            if not any(w in full for w in ["qa", "testing", "launch", "ship"]):
                return "📅", "Deadlines"

        # 4. Testing
        if any(w in full for w in ["test", "testing", "qa", "quality assurance", "regression"]):
            return "🧪", "Testing"

        # 5. Launch
        if any(w in full for w in ["launch", "release", "ship", "deploy", "deployment"]):
            return "🚀", "Launch"

        # 6. Deadlines fallback if had dates or demo
        if any(w in full for w in ["deadline", "timeline", "schedule", "demo"]):
            return "📅", "Deadlines"

        # 7. Design
        if any(w in full for w in ["design", "figma", "ui", "ux"]):
            return "🎨", "Design"

        # 8. Meeting
        if any(w in full for w in ["meeting", "sync", "standup", "huddle"]):
            return "💬", "Meeting"

        # 9. Priorities
        if any(w in full for w in ["priorit", "urgency", "tradeoff"]):
            return "⚡", "Priorities"

        # Default fallback
        extracted = SlackIntegrationService._extract_topic(c)
        return "⚠️", extracted or "Workflow"

    @staticmethod
    def _extract_topic(c: DetectedConflict) -> str:
        """Extracts a concise, standardized topic category for a conflict."""
        raw_title = c.title or ""
        if ":" in raw_title:
            topic_cand = raw_title.split(":", 1)[0].strip()
            topic_cand = re.sub(r"[*_`]", "", topic_cand).strip()
            tl = topic_cand.lower()
            if "deadline sequence" in tl or "timeline" in tl or "deadline" in tl:
                return "Deadlines"
            if "unclear task ownership" in tl or "unassigned" in tl or "ownership" in tl or "responsibility" in tl:
                return "Responsibilities"
            if "quality assurance" in tl or bool(re.search(r"\bqa\b", tl)) or "testing" in tl:
                return "Testing"
            if "scope" in tl:
                return "Project scope"
            if len(topic_cand) <= 18:
                return topic_cand

        tl = raw_title.lower()
        if bool(re.search(r"\bqa\b", tl)) or "testing" in tl:
            return "Testing"
        if "scope" in tl or "recommendation" in tl or bool(re.search(r"\bmvp\b", tl)) or "feature" in tl:
            return "Project scope"
        if "integration" in tl or bool(re.search(r"\bapi\b", tl)):
            return "Responsibilities"
        if "deadline" in tl or "timeline" in tl or "schedule" in tl or "completion" in tl or "demo" in tl:
            return "Deadlines"
        if "launch" in tl or "release" in tl or "ship" in tl:
            return "Launch"
        if "design" in tl or "figma" in tl or bool(re.search(r"\bui\b", tl)):
            return "Design"
        if "owner" in tl or "responsibility" in tl:
            return "Responsibilities"
        if "meeting" in tl or "sync" in tl:
            return "Meeting"

        type_name = c.conflict_type.value.replace("_", " ").title().split()[0]
        return type_name or "Workflow"

    @staticmethod
    def _format_conflict_bullet(c: DetectedConflict, max_chars: int = 85) -> str:
        """Formats a single conflict into a short, complete sentence: '- {icon} *{Topic}:* {Sentence}.'"""
        icon, topic_label = SlackIntegrationService._get_topic_and_icon(c)
        raw_title = (c.title or "").strip()
        tl = raw_title.lower()

        # Check for colon in raw_title
        stmt = ""
        if ":" in raw_title:
            parts = raw_title.split(":", 1)
            candidate = parts[1].strip()
            cand_lower = candidate.lower()
            # If candidate is a bare noun phrase like "Frontend delivery", expand to a complete sentence
            if any(cand_lower.startswith(w) for w in ["frontend", "backend", "deployment", "integration", "quality assurance", "testing", "design", "ui"]) and not any(v in cand_lower for v in ["is", "are", "expects", "conflicts", "unclear", "unconfirmed", "no confirmed", "needs", "disagree"]):
                stmt = f"{candidate} ownership is unclear."
            elif len(candidate) >= 15:
                stmt = candidate

        # Semantic pattern mapping for natural conversational sentences if no colon statement
        if not stmt:
            if "scope" in tl or "recommendation" in tl or "mvp" in tl or "feature" in tl:
                stmt = "Teammates disagree on demo features."
            elif any(w in tl for w in ["deadline", "timeline", "schedule", "completion", "target deadline"]):
                stmt = "Teammates expect different completion dates."
            elif any(w in tl for w in ["unbudgeted", "buffer", "inadequate", "short"]) and any(w in tl for w in ["test", "qa"]):
                stmt = "Not enough time may be reserved for testing."
            elif "ownership" in tl or "responsibility" in tl:
                task_cand = ""
                if ":" in raw_title:
                    task_cand = raw_title.split(":", 1)[1].strip()
                    task_cand = re.sub(r"\s+Between\s+.*$", "", task_cand, flags=re.IGNORECASE).strip()
                if task_cand and len(task_cand) <= 30:
                    stmt = f"{task_cand} ownership is unclear."
                else:
                    stmt = "Task ownership is unclear."
            elif "test" in tl or "qa" in tl:
                stmt = "Not enough time may be reserved for testing."
            elif "design" in tl or "figma" in tl or "ui" in tl:
                stmt = "Teammates are working with different UI design versions."
            elif "launch" in tl or "ship" in tl:
                stmt = "Team members expect different target launch dates."
            elif "meeting" in tl or "sync" in tl:
                stmt = "Team members have conflicting dates for the next sync meeting."
            elif c.impact_description and len(c.impact_description) >= 15:
                stmt = c.impact_description
            else:
                stmt = raw_title

        # Clean jargon and conversationalize raw patterns
        clean_stmt = SlackIntegrationService.remove_technical_jargon(stmt)
        # Strip trailing ': Team needs alignment.'
        clean_stmt = re.sub(r":\s*team needs alignment\.?$", ".", clean_stmt, flags=re.IGNORECASE)
        cl_low = clean_stmt.lower()
        if " vs " in cl_low and ("(" in clean_stmt or "saturday" in cl_low or "sunday" in cl_low):
            clean_stmt = re.sub(r"\(([^)]+)\)", r"expects \1", clean_stmt)
            clean_stmt = re.sub(r"\s+vs\s+", ", while ", clean_stmt)
        elif cl_low.startswith("deployment between "):
            clean_stmt = "Deployment ownership is unconfirmed between " + clean_stmt[19:]
        elif "unplanned testing dependency between " in cl_low:
            clean_stmt = re.sub(
                r"unplanned testing dependency between ([^.]+)",
                r"Testing schedule between \1 is unplanned",
                clean_stmt,
                flags=re.IGNORECASE,
            )

        sents = SlackIntegrationService._split_sentences(clean_stmt)
        first_sent = sents[0] if sents else f"{clean_stmt.rstrip('.!?,:; ')}."
        shortened = SlackIntegrationService._shorten_sentence_safely(first_sent, max_chars=max_chars)

        clean_end = shortened.rstrip(".!?,:; ")
        for dangle in [" and", " the", " on", " to", " with", " or", " but", " for"]:
            if clean_end.endswith(dangle):
                clean_end = clean_end[: -len(dangle)].rstrip(".!?,:; ")
        shortened = f"{clean_end}."

        if len(shortened) > 1:
            shortened = shortened[0].upper() + shortened[1:]

        return f"- *{topic_label}:* {shortened}"

    @staticmethod
    def _format_recommendation_bullet(rec_text: str, max_chars: int = 90) -> str:
        """Formats a single recommendation into a conversational teammate sentence: '- Action sentence.'"""
        cleaned = rec_text.strip()
        # Strip leading markdown labels like **CONFIRM deployment owner:**
        cleaned = re.sub(r"^\*\*[^*]+:\*\*\s*", "", cleaned)
        # Strip uppercase action headers like "CONFIRM final MVP scope: " or "DECIDE: "
        cleaned = re.sub(r"^[A-Z\s]{4,}:", "", cleaned).strip()
        # Strip reference tags like (CONF-1) or (related to RES-3)
        cleaned = re.sub(r"\s*\((?:CONF|RES|related)[^)]*\)", "", cleaned)
        # Strip "Review RES-X and "
        cleaned = re.sub(r"^Review\s+RES-\d+\s+and\s+", "", cleaned, flags=re.IGNORECASE)

        # Remove technical jargon first
        cleaned = SlackIntegrationService.remove_technical_jargon(cleaned)

        # If colon present with a high-level action prefix, pick the concise action statement
        if ":" in cleaned:
            parts = cleaned.split(":", 1)
            first_p = parts[0].strip()
            second_p = parts[1].strip()
            if 20 <= len(first_p) <= 85 and any(w in first_p.lower() for w in ["schedule", "deadline", "ownership", "confirm", "agree", "testing", "scope", "gate"]):
                cleaned = first_p
            elif 20 <= len(second_p) <= 85:
                cleaned = second_p

        # Shorten long lists of 3+ names to 'across teammates'
        cleaned = re.sub(
            r"(?:between|accommodating|across)\s+[A-Za-z\s]+,\s+[A-Za-z\s]+,\s+.*?(?=\s+(?:during|to|while|\.|$))",
            "across teammates",
            cleaned,
            flags=re.IGNORECASE,
        )

        # Soften tone to helpful teammate recommendations
        cl = cleaned.lower()
        if cl.startswith("adopt a "):
            cleaned = "Consider adopting a " + cleaned[8:]
        elif cl.startswith("confirm which team member owns "):
            cleaned = "Confirm who owns " + cleaned[31:]
        elif cl.startswith("formally designate "):
            cleaned = "Clarify whether to designate " + cleaned[19:]
        elif cl.startswith("establish an explicit "):
            cleaned = "Agree on an explicit " + cleaned[22:]
        elif cl.startswith("establish "):
            cleaned = "Agree on " + cleaned[10:]
        elif cl.startswith("decision on "):
            cleaned = "Decide on " + cleaned[12:]
        elif cl.startswith("confirmation of "):
            cleaned = "Confirm " + cleaned[16:]
        elif cl.startswith("discussion on "):
            cleaned = "Discuss " + cleaned[14:]

        sents = SlackIntegrationService._split_sentences(cleaned)
        first_sent = sents[0] if sents else f"{cleaned.rstrip('.!?,:; ')}."
        shortened = SlackIntegrationService._shorten_sentence_safely(first_sent, max_chars=max_chars)

        clean_end = shortened.rstrip(".!?,:; ")
        for dangle in [" and", " the", " on", " to", " with", " or", " but", " for", " during"]:
            if clean_end.endswith(dangle):
                clean_end = clean_end[: -len(dangle)].rstrip(".!?,:; ")
        shortened = f"{clean_end}."

        if len(shortened) > 1:
            shortened = shortened[0].upper() + shortened[1:]

        return f"- {shortened}"

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

        Teammate Check-In structure:
        - 🤖 Mediator | Team Check-In
        - Circle indicator: 🟢 (>=75%), 🟠 (30-74%), 🔴 (<30%)
        - Up to 4 highest-priority conflicts sorted by HIGH severity, using emojis and complete sentences.
        - Up to 3 AI-suggested next steps matched directly to proposed_resolutions.
        - Governance disclaimer: '🔒 Suggestions only — your team makes the final call.'
        - CTA deep-linking directly to the project's Decisions tab.
        - Budgeting: Visible characters <= 1,000; drops lowest-priority bullet if space runs out.
        """
        synth = result.synthesis_output
        conflicts = result.conflicts_output.conflicts
        score = round(synth.alignment_score)
        total_conflicts = len(conflicts)
        header_title = "Mediator | Team Check-In"
        decisions_url = f"{settings.dashboard_base_url.rstrip('/')}/?project_id={project_id}&tab=Decisions"

        # 1. Conflicts (Prioritize HIGH severity, max 4)
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
            self._format_conflict_bullet(c, max_chars=85) for c in selected_conflicts
        ]
        if not conflict_bullets:
            conflict_bullets = ["- *Everything aligned:* No active conflicts detected."]

        # 2. Next Steps (Actionable AI recommendations, up to 3)
        # Requirement: Every suggested action comes directly from an actual proposed_resolutions record
        # matched to the selected conflicts.
        rec_bullets: List[str] = []
        seen_recs: Set[str] = set()

        res_by_conflict: Dict[str, Any] = {}
        for r in synth.proposed_resolutions:
            if r.conflict_id and r.conflict_id not in res_by_conflict:
                res_by_conflict[r.conflict_id] = r

        # Match to selected conflicts
        for c in selected_conflicts:
            if c.conflict_id in res_by_conflict:
                r = res_by_conflict[c.conflict_id]
                bullet = self._format_recommendation_bullet(r.recommended_solution)
                norm = bullet.lower().strip()
                if norm not in seen_recs:
                    seen_recs.add(norm)
                    rec_bullets.append(bullet)
                if len(rec_bullets) >= 3:
                    break

        # Additional proposed resolutions from the report if space permits
        if len(rec_bullets) < 3:
            for r in synth.proposed_resolutions:
                bullet = self._format_recommendation_bullet(r.recommended_solution)
                norm = bullet.lower().strip()
                if norm not in seen_recs:
                    seen_recs.add(norm)
                    rec_bullets.append(bullet)
                if len(rec_bullets) >= 3:
                    break

        # Fallback to human action items if no proposed resolutions exist
        if not rec_bullets and synth.human_action_items:
            for item in synth.human_action_items:
                bullet = self._format_recommendation_bullet(item)
                norm = bullet.lower().strip()
                if norm not in seen_recs:
                    seen_recs.add(norm)
                    rec_bullets.append(bullet)
                if len(rec_bullets) >= 3:
                    break

        if not rec_bullets:
            rec_bullets.append("- Proceed with agreed team plans.")

        # 3. Score Line (Minimal, no emoji)
        shown_conflicts = len(selected_conflicts) if conflicts else 0
        if shown_conflicts < total_conflicts:
            count_text = f"{shown_conflicts} of {total_conflicts} conflicts"
        else:
            conflict_word = "potential conflict" if total_conflicts == 1 else "potential conflicts"
            count_text = f"{total_conflicts} {conflict_word}"

        stats_line = f"{score}% aligned · {count_text}"

        # 4. Section Headings, Disclaimer, and CTA Link
        disclaimer_text = "AI suggestions only · Team approval required"
        link_line = f"<{decisions_url}|Review in Mediator →>"

        conflicts_section_text = "*⚠️ What's not lining up*\n" + "\n".join(conflict_bullets)
        next_steps_section_text = "*💡 Suggested next steps*\n" + "\n".join(rec_bullets)

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
                        "text": "Review in Mediator →",
                        "emoji": True,
                    },
                    "url": decisions_url,
                    "action_id": "open_dashboard_button",
                },
            },
        ]

        # 5. Character Budgeting: Strictly <= 1,000 visible characters
        # If over 1,000 visible characters, remove lowest-priority bullet instead of truncating text
        while self.calculate_visible_characters(blocks) > 1000:
            if len(rec_bullets) > 1:
                rec_bullets.pop()
            elif len(conflict_bullets) > 1:
                conflict_bullets.pop()
                shown_count = len(conflict_bullets)
                if shown_count < total_conflicts:
                    count_text = f"{shown_count} of {total_conflicts} conflicts"
                else:
                    count_text = f"{total_conflicts} {'potential conflict' if total_conflicts == 1 else 'potential conflicts'}"
                stats_line = f"{score}% aligned · {count_text}"
                blocks[1]["text"]["text"] = stats_line
            elif len(rec_bullets) == 1:
                rec_bullets.pop()
            else:
                break

            conflicts_section_text = "*⚠️ What's not lining up*\n" + "\n".join(
                conflict_bullets or ["- *Everything aligned:* No active conflicts detected."]
            )
            next_steps_section_text = "*💡 Suggested next steps*\n" + "\n".join(
                rec_bullets or ["- Proceed with agreed team plans."]
            )
            blocks[2]["text"]["text"] = conflicts_section_text
            blocks[3]["text"]["text"] = next_steps_section_text

        # Fallback markdown text strictly matches the conversational structure and remains <= 1000 chars
        fallback_text = (
            f"*{header_title}*\n\n"
            f"{stats_line}\n\n"
            f"{conflicts_section_text}\n\n"
            f"{next_steps_section_text}\n\n"
            f"{disclaimer_text}\n\n"
            f"{link_line}"
        )

        return {
            "blocks": blocks,
            "text": fallback_text,
        }


slack_service = SlackIntegrationService()
