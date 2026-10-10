"""Interactive runner demonstrating the Multi-Agent Alignment Workflow on the sample team scenario.

Scenario:
- Alex: "Our priority is completing the frontend by Friday."
- Sam: "I thought we agreed to launch the entire application on Thursday."
- Taylor: "I think we should complete testing before launching anything."

Executes:
1. Perspective Agent -> Extracts priorities, deadlines, and identifies missing info.
2. Conflict Agent -> Detects Thursday/Friday contradiction and QA gaps.
3. Resolution Agent -> Proposes compromise schedules and highlights unresolved questions.
4. Decision Demonstration -> Explicitly distinguishes proposed resolutions from human-approved decisions.
"""

import asyncio
import json
import os
import sys
from datetime import datetime

# Ensure backend directory is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__))))

from app.models.schemas import (
    DecisionActionRequest,
    MemberResponse,
    ProjectCreate,
)
from app.services.supabase import storage_service
from app.workflows.alignment import AlignmentWorkflow


# Terminal styling helpers
BOLD = "\033[1m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
CYAN = "\033[36m"
RED = "\033[31m"
MAGENTA = "\033[35m"
RESET = "\033[0m"


async def main():
    print(f"\n{BOLD}{CYAN}======================================================================{RESET}")
    print(f"{BOLD}{CYAN}       AI TEAM ALIGNMENT PLATFORM — MULTI-AGENT WORKFLOW RUNNER       {RESET}")
    print(f"{BOLD}{CYAN}======================================================================{RESET}\n")

    # Step 1: Initialize Project & Teammate Submissions
    print(f"{BOLD}[1] Initializing Project & Submitting Teammate Perspectives...{RESET}")
    project = await storage_service.create_project(
        ProjectCreate(
            title="Q4 MVP Product Release",
            description="Collaborative sprint launch for hackathon deliverable",
        )
    )
    print(f"Created Project: {BOLD}{project.title}{RESET} (ID: {project.id})\n")

    sample_inputs = [
        ("Alex", "The project deadline is Saturday and I believe Taylor owns deployment."),
        ("Sam", "The project deadline is Sunday and we need full feature completion before launch."),
        ("Taylor", "I believe Alex owns deployment, and we must complete thorough testing before launching anything."),
    ]

    submitted_responses = []
    for member_name, statement in sample_inputs:
        resp = await storage_service.add_response(
            project_id=project.id,
            member_name=member_name,
            raw_text=statement,
            source="slack_standup",
        )
        submitted_responses.append(resp)
        print(f"  {YELLOW}• {member_name}:{RESET} \"{statement}\"")

    print("\n" + "-" * 70)

    # Step 2: Execute Sequential Multi-Agent Workflow
    print(f"\n{BOLD}[2] Triggering Multi-Agent Workflow (Google ADK Sequential Pipeline)...{RESET}")
    print("   Pipeline: Perspective Agent -> Conflict Agent -> Resolution Agent\n")

    workflow = AlignmentWorkflow()
    result = await workflow.run(project_id=project.id, responses=submitted_responses)

    # Save to storage
    await storage_service.save_report(project.id, result.synthesis_output)

    print(f"{GREEN}✓ Workflow execution completed successfully in {result.execution_metadata['duration_seconds']}s!{RESET}\n")
    print("-" * 70)

    # Step 3: Display Agent 1 (Perspective Analysis) Results
    p_out = result.perspectives_output
    print(f"\n{BOLD}{MAGENTA}[AGENT 1: PERSPECTIVE ANALYSIS AGENT OUTPUT]{RESET}")
    print(f"Overall Summary: {p_out.overall_summary}\n")
    for p in p_out.perspectives:
        print(f"  {BOLD}Teammate: {p.member_name}{RESET}")
        for g in p.goals:
            print(f"    - Goal: {g.statement} (Quote: \"{g.source_quote}\")")
        for prio in p.priorities:
            print(f"    - Priority: {prio.priority_item} [Urgency: {prio.urgency_level}]")
        for d in p.deadlines:
            print(f"    - Deadline: {d.expected_deadline} for {d.milestone} (Tentative: {d.is_tentative})")
        for amb in p.ambiguities_or_missing_details:
            print(f"    - {YELLOW}Identified Missing Detail:{RESET} {amb}")
        print()

    if p_out.identified_gaps:
        print(f"  {YELLOW}Cross-Cutting Information Gaps:{RESET}")
        for gap in p_out.identified_gaps:
            print(f"    * {gap}")

    print("\n" + "-" * 70)

    # Step 4: Display Agent 2 (Conflict Detection) Results
    c_out = result.conflicts_output
    print(f"\n{BOLD}{RED}[AGENT 2: CONFLICT DETECTION AGENT OUTPUT]{RESET}")
    print(f"Synthesis Summary: {c_out.synthesis_summary}\n")
    for c in c_out.conflicts:
        print(f"  {BOLD}Conflict [{c.conflict_id}]: {c.title}{RESET}")
        print(f"    - Type: {c.conflict_type.value} | Category: {c.category.value} | Severity: {BOLD}{c.severity.value}{RESET}")
        print(f"    - Severity Reasoning: {c.severity_reasoning}")
        print(f"    - Parties Involved: {', '.join(c.parties_involved)}")
        print(f"    - Evidence Citations:")
        for ev in c.evidence:
            print(f"        * {ev.member_name}: \"{ev.quote}\" -> {ev.interpretation}")
        print(f"    - Impact: {c.impact_description}\n")

    if c_out.compatible_differences:
        print(f"  {CYAN}Compatible Non-Conflicting Differences:{RESET}")
        for cd in c_out.compatible_differences:
            print(f"    * {cd}")

    print("\n" + "-" * 70)

    # Step 5: Display Agent 3 (Resolution & Synthesis) Results
    s_out = result.synthesis_output
    print(f"\n{BOLD}{GREEN}[AGENT 3: RESOLUTION & SYNTHESIS AGENT OUTPUT]{RESET}")
    print(f"Alignment Score: {BOLD}{s_out.alignment_score}/100.0{RESET}")
    print(f"Executive Summary: {s_out.executive_summary}\n")

    for res in s_out.proposed_resolutions:
        print(f"  {BOLD}Resolution Proposal [{res.resolution_id}] for {res.conflict_title}:{RESET}")
        print(f"    - Recommended Compromise: {res.recommended_solution}")
        print(f"    - Rationale: {res.reasoning}")
        print(f"    - Status: {YELLOW}{BOLD}{res.status}{RESET} (Requires explicit human approval)")
        print(f"    - Alternative Options:")
        for opt in res.alternative_options:
            print(f"        * [{opt.option_id}] {opt.title}: {opt.description}")
        print(f"    - Unresolved Questions Requiring Human Consensus:")
        for q in res.unresolved_questions_for_team:
            print(f"        ? {q}")
        print()

    print(f"  {BOLD}Human Action Items:{RESET}")
    for act in s_out.human_action_items:
        print(f"    [ ] {act}")

    print(f"\n  {YELLOW}{BOLD}Governance Notice:{RESET} {s_out.disclaimer}")

    print("\n" + "-" * 70)

    # Step 6: Decision Demonstration (Human in the loop approval)
    print(f"\n{BOLD}[3] Human Decision Step: Simulating Teammate Approval of Proposal...{RESET}")
    decision_action = DecisionActionRequest(
        resolution_id="RES-01",
        action="APPROVE",
        decision_text="Official Team Commitment: Frontend completed Friday morning; dedicated testing Friday afternoon; public launch Monday 9am.",
        decided_by="Sam (Lead Organizer)",
        notes="Unanimously approved during team standup after reviewing AI compromise options.",
    )
    confirmed = await storage_service.record_decision(project.id, decision_action)
    print(f"Decision Recorded: ID {confirmed.id}")
    print(f"Status: {GREEN}{BOLD}{confirmed.status.value}{RESET}")
    print(f"Binding Commitment: \"{confirmed.decision_text}\"")
    print(f"Signed Off By: {confirmed.decided_by} at {confirmed.decided_at.isoformat()}")

    print(f"\n{BOLD}{CYAN}======================================================================{RESET}")
    print(f"{BOLD}{GREEN}✓ End-to-End Scenario Successfully Demonstrated!{RESET}")
    print(f"{BOLD}{CYAN}======================================================================{RESET}\n")


if __name__ == "__main__":
    asyncio.run(main())
