"""
Orchestrator engine for managing two-agent workflow.

Coordinates Planner and Executor agents through discovery, planning,
and execution phases with automatic milestone approval and blocker handling.
"""

from typing import Optional, Dict, Any, Callable

from . import db
from .agents import create_planner_agent, create_executor_agent, PlannerAgent, ExecutorAgent
from .state import StateMachine, WorkflowState, TransitionEvent
from .parser import (
    parse_planner_response,
    parse_executor_response,
    PLANNER_APPROVED,
    PLANNER_CHANGES_REQUESTED,
    PLANNER_BLOCKED,
    PLANNER_PLAN_READY,
    EXECUTOR_REPORT,
    EXECUTOR_CLARIFICATION,
    EXECUTOR_BLOCKED,
)
from .prompts import (
    MILESTONE_PROMPT_TEMPLATE,
    APPROVAL_CONTINUATION_TEMPLATE,
    CHANGES_REQUESTED_TEMPLATE,
)
from .recovery import register_recovery_hook


class Orchestrator:
    """
    Orchestrates two-agent workflow through discovery, planning, and execution phases.

    Manages state transitions, message routing, and automatic milestone approval.
    """

    def __init__(
        self,
        feature_description: Optional[str] = None,
        session_id: Optional[str] = None,
        db_path: Optional[str] = None,
        plan_path: Optional[str] = None,
        on_output: Optional[Callable[[str], None]] = None,
    ):
        """
        Initialize orchestrator.

        Args:
            feature_description: Description for new session
            session_id: ID of existing session to resume
            db_path: Optional database path
            plan_path: Optional path to existing plan file (skips discovery/planning)
            on_output: Optional callback for output messages
        """
        self.db_path = db_path
        self.on_output = on_output or print
        self.state_machine = StateMachine(db_path=db_path)

        # Initialize database
        db.init_db(db_path)

        # Create or resume session
        if session_id:
            # Resume existing session
            self.session_id = session_id
            state = self.state_machine.get_state(session_id)
            if not state:
                raise ValueError(f"Session {session_id} not found")
            self.state = state
        elif feature_description:
            if plan_path:
                # Start with existing plan (skip discovery/planning)
                self._start_with_plan(feature_description, plan_path)
            else:
                # Create new session with discovery
                self.session_id = db.create_session(
                    feature_description=feature_description,
                    db_path=db_path
                )
                self.state = self.state_machine.get_state(self.session_id)
        else:
            raise ValueError("Must provide either feature_description or session_id")

        # Agents (created on demand)
        self.planner: Optional[PlannerAgent] = None
        self.executor: Optional[ExecutorAgent] = None

        # Track current blocker
        self.current_blocker_id: Optional[int] = None

    def _start_with_plan(self, feature_description: str, plan_path: str) -> None:
        """
        Start a new session with an existing plan file.

        Skips discovery and planning phases, goes directly to execution.

        Args:
            feature_description: Feature being implemented
            plan_path: Path to existing plan file
        """
        from .parser import parse_plan_file

        # Validate plan file
        plan_info = parse_plan_file(plan_path)
        if not plan_info["valid"]:
            raise ValueError(f"Invalid plan file: {plan_info['error']}")

        self._output(f"\n→ Using existing plan: {plan_path}")
        self._output(f"\n  Milestones: {plan_info['milestones']}")
        self._output(f"\n  Names: {', '.join(plan_info['milestone_names'])}\n")

        # Create session
        self.session_id = db.create_session(
            feature_description=feature_description,
            db_path=self.db_path
        )

        # Update to execution phase with plan info
        db.update_session(
            self.session_id,
            {
                "phase": "execution",
                "plan_path": plan_path,
                "current_milestone": 1,
                "total_milestones": plan_info["milestones"],
            },
            self.db_path
        )

        # Load state
        self.state = self.state_machine.get_state(self.session_id)

        self._output(f"\n✓ Session created: {self.session_id[:8]}")
        self._output(f"\n  Phase: EXECUTION (skipped discovery/planning)\n")

    def _log_message(
        self,
        agent: str,
        role: str,
        content: str,
        token_count: Optional[int] = None
    ) -> None:
        """Log message to database."""
        db.log_message(
            session_id=self.session_id,
            phase=self.state.phase,
            agent=agent,
            role=role,
            content=content,
            token_count=token_count,
            db_path=self.db_path
        )

    def _create_planner(self) -> PlannerAgent:
        """Create or return existing planner agent."""
        if self.planner is None:
            planner_session_id = f"{self.session_id}-planner"
            self.planner = create_planner_agent(session_id=planner_session_id)
            # Register recovery hook
            register_recovery_hook(
                self.planner,
                session_id=self.session_id,
                agent_role="PLANNER",
                db_path=self.db_path
            )
        return self.planner

    def _create_executor(self) -> ExecutorAgent:
        """Create or return existing executor agent."""
        if self.executor is None:
            executor_session_id = f"{self.session_id}-executor"
            self.executor = create_executor_agent(session_id=executor_session_id)
            # Register recovery hook
            register_recovery_hook(
                self.executor,
                session_id=self.session_id,
                agent_role="EXECUTOR",
                db_path=self.db_path
            )
        return self.executor

    def start(self) -> None:
        """
        Start the orchestration workflow.

        Runs through discovery, planning, and execution phases.
        """
        self._output(f"\n=== Orchestrator Auto: {self.state.feature_description} ===\n")
        self._output(f"Session ID: {self.session_id}\n")

        try:
            # Run appropriate phase based on current state
            if self.state.phase == "discovery":
                self._run_discovery_loop()

            if self.state.phase == "planning":
                self._run_planning()

            if self.state.phase == "execution":
                self._run_execution_loop()

            if self.state.phase == "completed":
                self._output("\n=== Workflow Complete ===\n")

        finally:
            # Cleanup
            self._cleanup()

    def resume(self, answer: Optional[str] = None) -> None:
        """
        Resume a paused session.

        Args:
            answer: Optional answer to current blocker
        """
        if self.state.phase != "paused":
            raise ValueError("Session is not paused")

        # Get unresolved blockers
        blockers = db.get_unresolved_blockers(self.session_id, self.db_path)
        if not blockers:
            # No blockers, just resume
            success, self.state, error = self.state_machine.transition(
                self.session_id,
                TransitionEvent.HUMAN_RESPONDED.value
            )
            if not success:
                raise RuntimeError(f"Failed to resume: {error}")
        else:
            # Resolve blocker with answer
            blocker = blockers[0]
            if answer:
                db.resolve_blocker(blocker["id"], answer, self.db_path)
                self._log_message("human", "user", answer)

                # Resume to previous phase
                success, self.state, error = self.state_machine.transition(
                    self.session_id,
                    TransitionEvent.HUMAN_RESPONDED.value
                )
                if not success:
                    raise RuntimeError(f"Failed to resume: {error}")
            else:
                raise ValueError("Answer required to resolve blocker")

        # Continue workflow
        self.start()

    def respond(self, answer: str) -> None:
        """Respond to a blocker. Alias for resume()."""
        self.resume(answer)

    def _output(self, message: str) -> None:
        """Output a message via callback."""
        if self.on_output:
            self.on_output(message)

    def _run_discovery_loop(self) -> None:
        """
        Run discovery phase conversation.

        Human ↔ Planner until user types /ready.
        """
        self._output("\n=== Phase 1: Discovery ===\n")
        self._output("Discuss your feature requirements with the Planner.")
        self._output("Type '/ready' when you're ready to proceed to planning.\n")

        planner = self._create_planner()

        # Start conversation
        user_input = self.state.feature_description
        self._log_message("human", "user", user_input)
        self._output(f"You: {user_input}\n")

        while True:
            # Send to planner
            response = planner.send_message(user_input)

            # Log response
            self._log_message("planner", "assistant", response)

            # Output response
            self._output(f"Planner: {response}\n")

            # Check for blockers
            response_type, data = parse_planner_response(response)
            if response_type == PLANNER_BLOCKED:
                self._handle_blocker("planner", data["question"])
                return

            # Get user input
            user_input = input("You: ").strip()
            self._log_message("human", "user", user_input)

            # Check for /ready command
            if user_input.lower() == "/ready":
                self._output("\n✓ Proceeding to planning phase...\n")
                success, self.state, error = self.state_machine.transition(
                    self.session_id,
                    TransitionEvent.READY.value
                )
                if not success:
                    raise RuntimeError(f"Failed to transition to planning: {error}")
                return

    def _run_planning(self) -> None:
        """
        Run planning phase.

        Planner creates implementation plan with milestones.
        """
        self._output("\n=== Phase 2: Planning ===\n")
        self._output("Planner is creating the implementation plan...\n")

        planner = self._create_planner()

        # Prompt planner to create plan with inline content
        default_plan_path = f"docs/{self.session_id}/DOC_{self.session_id}_plan.md"
        plan_prompt = f"""
Create an implementation plan for: {self.state.feature_description}

1. Research the codebase to understand existing patterns
2. Define 3-5 milestones with clear deliverables
3. Output the plan using this EXACT format:

[PLAN_READY]
Path: {default_plan_path}
Milestones: N total

[PLAN_CONTENT]
# Implementation Plan: [Feature Name]

## Overview
[Brief description]

## Milestones

### Milestone 1: [Name]
**Deliverables:**
- [deliverable 1]
- [deliverable 2]

### Milestone 2: [Name]
...

[/PLAN_CONTENT]

Summary: [brief summary of the approach]

IMPORTANT: Include the FULL plan content between [PLAN_CONTENT] and [/PLAN_CONTENT] tags.
The orchestrator will save the file for you.
"""

        response = planner.send_message(plan_prompt)

        # Log response
        self._log_message("planner", "assistant", response)

        # Output response
        self._output(f"Planner: {response}\n")

        # Parse response
        response_type, data = parse_planner_response(response)

        if response_type == PLANNER_PLAN_READY:
            plan_path = data.get("path") or default_plan_path
            total_milestones = data.get("milestones", 0)
            plan_content = data.get("content")

            # If plan content was provided, save it
            from pathlib import Path
            if plan_content:
                self._output(f"\n→ Saving plan to: {plan_path}")
                plan_file = Path(plan_path)
                plan_file.parent.mkdir(parents=True, exist_ok=True)
                plan_file.write_text(plan_content)
                self._output(" ✓\n")

            # Verify plan file exists
            if not Path(plan_path).exists():
                self._output(f"\n⚠ Plan file not found at: {plan_path}")
                self._output("Planner did not provide plan content in [PLAN_CONTENT] tags.\n")
                self._handle_blocker(
                    "planner",
                    f"Plan file missing at {plan_path}. Please provide the plan content between [PLAN_CONTENT] and [/PLAN_CONTENT] tags."
                )
                return

            self._output(f"\n✓ Plan created at: {plan_path}")
            self._output(f"✓ Total milestones: {total_milestones}\n")

            # Transition to execution
            success, self.state, error = self.state_machine.transition(
                self.session_id,
                TransitionEvent.PLAN_APPROVED.value,
                plan_path=plan_path,
                total_milestones=total_milestones
            )
            if not success:
                raise RuntimeError(f"Failed to transition to execution: {error}")

        elif response_type == PLANNER_BLOCKED:
            self._handle_blocker("planner", data["question"])

        else:
            self._output("\n⚠ Planner did not use [PLAN_READY] tag. Pausing for review.\n")
            self._handle_blocker("planner", "Plan creation did not complete as expected")

    def _run_execution_loop(self) -> None:
        """
        Run execution phase loop.

        Execute milestones with automatic approval.
        """
        self._output("\n=== Phase 3: Execution ===\n")

        planner = self._create_planner()
        executor = self._create_executor()

        current_milestone = self.state.current_milestone or 1
        total_milestones = self.state.total_milestones

        while current_milestone <= total_milestones:
            self._output(f"\n--- Milestone {current_milestone}/{total_milestones} ---\n")

            # Generate milestone prompt
            milestone_prompt = MILESTONE_PROMPT_TEMPLATE.format(
                feature_description=self.state.feature_description,
                total_milestones=total_milestones,
                plan_path=self.state.plan_path or "docs/plan.md",
                milestone_number=current_milestone,
                milestone_name=f"Milestone {current_milestone}",
                milestone_tasks=f"Execute Milestone {current_milestone} from the plan",
                next_milestone_number=current_milestone + 1
            )

            # Send to executor
            self._output("→ Sending milestone to Executor...\n")
            executor_response = executor.send_message(milestone_prompt)

            # Log response
            self._log_message("executor", "assistant", executor_response)

            # Parse executor response
            response_type, data = parse_executor_response(executor_response)

            if response_type == EXECUTOR_REPORT:
                report_content = data["content"]
                self._output(f"\n✓ Executor completed milestone {current_milestone}\n")

                # Route to planner for validation
                validation = self._route_to_planner(report_content)

                if validation == "approved":
                    # Auto-continue to next milestone
                    current_milestone += 1
                    success, self.state, error = self.state_machine.transition(
                        self.session_id,
                        TransitionEvent.MILESTONE_APPROVED.value,
                        current_milestone=current_milestone - 1
                    )
                    if not success:
                        raise RuntimeError(f"Failed to approve milestone: {error}")

                elif validation == "changes_requested":
                    # Executor needs to fix issues
                    # Loop will re-execute this milestone
                    pass

                elif validation == "blocked":
                    # Paused for human input
                    return

            elif response_type == EXECUTOR_CLARIFICATION:
                self._output(f"\n→ Executor needs clarification from Planner\n")
                # Route question to planner
                clarification_response = planner.send_message(data["question"])
                # Send response back to executor
                self._route_to_executor(clarification_response)

            elif response_type == EXECUTOR_BLOCKED:
                self._handle_blocker("executor", data["reason"])
                return

            else:
                self._output("\n⚠ Executor response not recognized. Pausing.\n")
                self._handle_blocker("executor", "Unexpected response format")
                return

        # All milestones complete
        self._output("\n✓ All milestones complete!\n")
        success, self.state, error = self.state_machine.transition(
            self.session_id,
            TransitionEvent.ALL_MILESTONES_DONE.value
        )
        if not success:
            raise RuntimeError(f"Failed to complete workflow: {error}")

    def _route_to_planner(self, report: str) -> str:
        """
        Route progress report to planner for validation.

        Args:
            report: Executor's progress report

        Returns:
            "approved", "changes_requested", or "blocked"
        """
        planner = self._create_planner()

        validation_prompt = f"""
        Review this milestone progress report from the Executor:

        {report}

        Validate:
        1. Are all deliverables completed?
        2. Do tests pass?
        3. Does code follow project conventions?

        Respond with [MILESTONE_APPROVED], [CHANGES_REQUESTED], or [HUMAN_INPUT_NEEDED].
        """

        response = planner.send_message(validation_prompt)

        # Log response
        self._log_message("planner", "assistant", response)

        # Parse response
        response_type, data = parse_planner_response(response)

        if response_type == PLANNER_APPROVED:
            milestone_num = data.get("milestone", self.state.current_milestone)
            self._output(f"\n✓ Planner approved Milestone {milestone_num}\n")
            return "approved"

        elif response_type == PLANNER_CHANGES_REQUESTED:
            issues = data.get("issues", [])
            self._output(f"\n⚠ Planner requested changes:\n")
            for issue in issues:
                self._output(f"  - {issue}\n")

            # Send feedback to executor
            feedback = CHANGES_REQUESTED_TEMPLATE.format(
                milestone_number=self.state.current_milestone,
                issues="\n".join([f"- {issue}" for issue in issues])
            )
            self._route_to_executor(feedback)
            return "changes_requested"

        elif response_type == PLANNER_BLOCKED:
            question = data.get("question", "Unknown question")
            self._handle_blocker("planner", question)
            return "blocked"

        else:
            self._output("\n⚠ Planner response not recognized\n")
            return "blocked"

    def _route_to_executor(self, feedback: str) -> None:
        """
        Route feedback to executor.

        Args:
            feedback: Planner's feedback or instructions
        """
        executor = self._create_executor()

        response = executor.send_message(feedback)

        # Log
        self._log_message("executor", "assistant", response)

        self._output(f"\n→ Executor response: {response[:200]}...\n")

    def _handle_blocker(self, agent: str, question: str) -> None:
        """
        Handle a blocker by pausing the workflow.

        Args:
            agent: Agent that raised the blocker
            question: Question or issue
        """
        self._output(f"\n⏸ Workflow paused - {agent} needs input:\n")
        self._output(f"  {question}\n")
        self._output(f"\nUse orchestrator.respond('your answer') to continue.\n")

        # Create blocker record
        blocker_id = db.create_blocker(
            session_id=self.session_id,
            agent=agent,
            question=question,
            db_path=self.db_path
        )
        self.current_blocker_id = blocker_id

        # Transition to paused
        success, self.state, error = self.state_machine.transition(
            self.session_id,
            TransitionEvent.HUMAN_INPUT_NEEDED.value
        )
        if not success:
            raise RuntimeError(f"Failed to pause: {error}")

    def _cleanup(self) -> None:
        """Cleanup resources."""
        if self.planner:
            self.planner.close()
        if self.executor:
            self.executor.close()

    def get_status(self) -> Dict[str, Any]:
        """
        Get current workflow status.

        Returns:
            Dictionary with session status
        """
        return {
            "session_id": self.session_id,
            "phase": self.state.phase,
            "status": self.state.status,
            "current_milestone": self.state.current_milestone,
            "total_milestones": self.state.total_milestones,
            "plan_path": self.state.plan_path,
        }
