"""
Context recovery and PreCompact hook for long-running agent sessions.

Provides functionality to preserve agent state before context compaction
and restore it with a recovery prompt.
"""

from typing import Optional, Dict, Any, List
from .db import (
    get_session,
    get_messages,
    get_milestones,
    get_unresolved_blockers,
)
from .prompts import RECOVERY_PROMPT_TEMPLATE


def generate_recovery_prompt(
    session_id: str,
    agent_role: str,
    db_path: Optional[str] = None,
    recent_message_count: int = 5
) -> str:
    """
    Generate a recovery prompt from database state.

    Queries the database for session information, milestone progress,
    and recent messages, then formats them into a recovery prompt.

    Args:
        session_id: Workflow session ID
        agent_role: "PLANNER" or "EXECUTOR"
        db_path: Optional database path
        recent_message_count: Number of recent messages to include

    Returns:
        Formatted recovery prompt with session state
    """
    # Get session information
    session = get_session(session_id, db_path)
    if not session:
        return f"[Error: Session {session_id} not found]"

    # Get milestones
    milestones = get_milestones(session_id, db_path)
    approved_milestones = [m for m in milestones if m["status"] == "completed"]

    # Format approved milestones
    if approved_milestones:
        milestone_list = "\n".join([
            f"- Milestone {m['number']}: {m['name']} ✓"
            for m in approved_milestones
        ])
    else:
        milestone_list = "None yet"

    # Get recent messages
    messages = get_messages(session_id, db_path=db_path)
    recent_messages = messages[-recent_message_count:] if messages else []

    # Format recent messages
    if recent_messages:
        message_list = "\n".join([
            f"[{m['agent']}] ({m['role']}): {m['content'][:200]}..."
            if len(m['content']) > 200
            else f"[{m['agent']}] ({m['role']}): {m['content']}"
            for m in recent_messages
        ])
    else:
        message_list = "No recent messages"

    # Determine current task
    if session["phase"] == "discovery":
        current_task = "Continue discussing requirements with the user. When ready, they will say '/ready' to proceed to planning."
    elif session["phase"] == "planning":
        current_task = f"Continue creating the implementation plan at: {session.get('plan_path', 'docs/[feature]/DOC_[feature]_plan.md')}"
    elif session["phase"] == "execution":
        current_milestone = session.get("current_milestone", 0)
        total_milestones = session.get("total_milestones", 0)
        if agent_role == "PLANNER":
            current_task = f"You are reviewing Milestone {current_milestone} of {total_milestones}. Wait for the executor's progress report."
        else:
            current_task = f"You are working on Milestone {current_milestone} of {total_milestones}. Review the plan and continue implementation."
    else:
        current_task = "Continue with the workflow."

    # Check for unresolved blockers
    blockers = get_unresolved_blockers(session_id, db_path)
    if blockers:
        blocker_text = "\n\n### Unresolved Blockers\n" + "\n".join([
            f"- [{b['agent']}] {b['question']}"
            for b in blockers
        ])
        current_task += blocker_text

    # Format the recovery prompt
    recovery_prompt = RECOVERY_PROMPT_TEMPLATE.format(
        session_id=session_id,
        feature_description=session["feature_description"],
        phase=session["phase"],
        status=session["status"],
        current_milestone=session.get("current_milestone", 0),
        total_milestones=session.get("total_milestones", 0),
        plan_path=session.get("plan_path", "Not yet created"),
        approved_milestones=milestone_list,
        recent_messages=message_list,
        current_task=current_task,
        agent_role=agent_role,
    )

    return recovery_prompt


def create_compact_hook(
    session_id: str,
    agent_role: str,
    db_path: Optional[str] = None
):
    """
    Create a PreCompact hook callback for an agent.

    The hook is called before the SDK compacts the context window,
    allowing us to inject a recovery prompt with session state.

    Args:
        session_id: Workflow session ID
        agent_role: "PLANNER" or "EXECUTOR"
        db_path: Optional database path

    Returns:
        Hook callback function
    """
    def precompact_hook() -> str:
        """
        PreCompact hook callback.

        Called by the SDK before context compaction. Returns a recovery
        prompt with current session state to preserve context.
        """
        return generate_recovery_prompt(
            session_id=session_id,
            agent_role=agent_role,
            db_path=db_path
        )

    return precompact_hook


def register_recovery_hook(
    agent,
    session_id: str,
    agent_role: str,
    db_path: Optional[str] = None
) -> None:
    """
    Register a PreCompact recovery hook with an agent.

    With the query()-based SDK approach, we store the hook on the agent
    for potential manual injection if context recovery is needed.

    Args:
        agent: PlannerAgent or ExecutorAgent instance
        session_id: Workflow session ID
        agent_role: "PLANNER" or "EXECUTOR"
        db_path: Optional database path
    """
    hook = create_compact_hook(session_id, agent_role, db_path)

    # Store the hook on the agent for manual recovery if needed
    # The query() SDK approach handles context automatically, but we keep
    # this for potential manual recovery scenarios
    agent._recovery_hook = hook
    agent._session_id = session_id
    agent._agent_role = agent_role
    agent._db_path = db_path


def get_recovery_state(
    session_id: str,
    db_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Get the current recovery state for a session.

    Returns a dictionary with session state that can be used
    for manual recovery or debugging.

    Args:
        session_id: Workflow session ID
        db_path: Optional database path

    Returns:
        Dictionary with session state
    """
    session = get_session(session_id, db_path)
    if not session:
        return {"error": f"Session {session_id} not found"}

    milestones = get_milestones(session_id, db_path)
    messages = get_messages(session_id, db_path=db_path)
    blockers = get_unresolved_blockers(session_id, db_path)

    return {
        "session": session,
        "milestones": milestones,
        "approved_milestones": [m for m in milestones if m["status"] == "completed"],
        "pending_milestones": [m for m in milestones if m["status"] == "pending"],
        "in_progress_milestones": [m for m in milestones if m["status"] == "in_progress"],
        "message_count": len(messages),
        "recent_messages": messages[-5:] if messages else [],
        "unresolved_blockers": blockers,
    }
