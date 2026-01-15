"""
Orchestrator engine for managing two-agent workflow.

Coordinates Planner and Executor agents through discovery, planning,
and execution phases with automatic milestone approval and blocker handling.
"""

import traceback
from typing import Optional, Dict, Any, Callable, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from .telegram import TelegramNotifier

from . import db
from .exceptions import OrchestratorError, AgentError
from .logging_config import create_session_logger, teardown_session_logger, get_null_logger
from .auth import detect_auth
from .config import (
    get_project_identity,
    find_repo_root,
    load_mcp_config_raw,
    expand_env_vars,
    get_agent_mcp_config,
    inject_headless_mode,
)
from .agents import (
    create_planner_agent,
    create_executor_agent,
    PlannerAgent,
    ExecutorAgent,
    build_allowed_tools,
)
from .state import StateMachine, WorkflowState, TransitionEvent
from .parser import (
    parse_planner_response,
    parse_executor_response,
    is_response_truncated,
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
from .output import StreamingIndicator
from .input_handler import prompt_with_paste_support


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
        show_activity: bool = True,
        planner_model: Optional[str] = None,
        executor_model: Optional[str] = None,
        telegram_notifier: Optional["TelegramNotifier"] = None,
        debug: bool = False,
        mcp_config_path: Optional[str] = None,
        headless: bool = False,
    ):
        """
        Initialize orchestrator.

        Args:
            feature_description: Description for new session
            session_id: ID of existing session to resume
            db_path: Optional database path
            plan_path: Optional path to existing plan file (skips discovery/planning)
            on_output: Optional callback for output messages
            show_activity: Whether to show streaming activity indicator (default: True)
            planner_model: Model for planner agent (optional, uses default if not specified)
            executor_model: Model for executor agent (optional, uses default if not specified)
            telegram_notifier: Optional TelegramNotifier for sending notifications
            debug: If True, enable debug logging with console output
            mcp_config_path: Optional path to MCP configuration file (.mcp.json)
            headless: If True, run Playwright MCP browser in headless mode
        """
        self.db_path = db_path
        self.on_output = on_output or print
        self.show_activity = show_activity
        self.state_machine = StateMachine(db_path=db_path)
        self._debug = debug

        # Model configuration
        self.planner_model = planner_model
        self.executor_model = executor_model

        # Telegram notifications
        self.telegram_notifier = telegram_notifier

        # MCP configuration
        self.mcp_servers = None
        self.planner_mcp_config = None
        self.executor_mcp_config = None
        self._mcp_config_for_db = None  # Store raw config for DB persistence
        self._headless = headless  # Playwright headless mode

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

            # Load models from session if not provided
            session_data = db.get_session(session_id, db_path)
            if session_data:
                if not self.planner_model and session_data.get("planner_model"):
                    self.planner_model = session_data["planner_model"]
                if not self.executor_model and session_data.get("executor_model"):
                    self.executor_model = session_data["executor_model"]

            # Load MCP config from DB first (for resume)
            self._load_mcp_from_db(session_id)

            # If explicit MCP path provided, it overrides DB config
            if mcp_config_path:
                self._load_mcp_from_file(mcp_config_path)

        elif feature_description:
            # Load MCP config from file for new session
            if mcp_config_path or not session_id:
                self._load_mcp_from_file(mcp_config_path)

            if plan_path:
                # Start with existing plan (skip discovery/planning)
                self._start_with_plan(feature_description, plan_path)
            else:
                # Get project identity for session scoping
                project_id, project_remote = get_project_identity()

                # Detect auth source for tracking
                auth_info = detect_auth()

                # Create new session with discovery
                self.session_id = db.create_session(
                    feature_description=feature_description,
                    planner_model=planner_model,
                    executor_model=executor_model,
                    project_id=project_id,
                    project_remote=project_remote,
                    auth_info=auth_info.to_db_dict(),
                    mcp_config=self._mcp_config_for_db,
                    db_path=db_path
                )
                self.state = self.state_machine.get_state(self.session_id)
        else:
            raise ValueError("Must provide either feature_description or session_id")

        # Initialize session logger (after session_id is available)
        # Each session gets its own logger to support queue/watch mode
        try:
            self._logger, self._log_path = create_session_logger(
                self.session_id, debug=self._debug
            )
        except Exception:
            # Fallback to null logger if logging setup fails
            self._logger = get_null_logger()
            self._log_path = None

        # Agents (created on demand)
        self.planner: Optional[PlannerAgent] = None
        self.executor: Optional[ExecutorAgent] = None

        # Track current blocker
        self.current_blocker_id: Optional[int] = None

        # Pending human response to inject into agent conversation on resume
        # Format: {"agent": "planner"|"executor", "answer": str, "question": str}
        self._pending_response: Optional[Dict[str, str]] = None

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

        # Get project identity for session scoping
        project_id, project_remote = get_project_identity()

        # Detect auth source for tracking
        auth_info = detect_auth()

        # Create session with model configuration
        self.session_id = db.create_session(
            feature_description=feature_description,
            planner_model=self.planner_model,
            executor_model=self.executor_model,
            project_id=project_id,
            project_remote=project_remote,
            auth_info=auth_info.to_db_dict(),
            mcp_config=self._mcp_config_for_db,
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

    def _load_mcp_from_db(self, session_id: str) -> None:
        """Load MCP configuration from database session."""
        try:
            mcp_config = db.get_session_mcp_config(session_id, self.db_path)
            if mcp_config:
                # Expand env vars at runtime (raw config stored in DB)
                mcp_config = expand_env_vars(mcp_config)
                self._apply_mcp_config(mcp_config)
                if self._debug:
                    self._output(f"  (Loaded MCP config from session)\n")
        except Exception as e:
            if self._debug:
                self._output(f"  (Failed to load MCP from DB: {e})\n")

    def _load_mcp_from_file(self, mcp_config_path: Optional[str]) -> None:
        """Load MCP configuration from file."""
        try:
            project_root = find_repo_root()

            # Load RAW config (${VAR} unexpanded) for DB storage
            raw_servers, raw_planner_cfg, raw_executor_cfg = load_mcp_config_raw(
                mcp_config_path=mcp_config_path,
                project_root=project_root,
            )

            if raw_servers:
                # Store RAW config for DB persistence (security)
                self._mcp_config_for_db = {
                    "servers": raw_servers,
                    "planner": raw_planner_cfg,
                    "executor": raw_executor_cfg,
                }

                # Expand env vars for runtime use
                expanded_config = expand_env_vars(self._mcp_config_for_db)
                self._apply_mcp_config(expanded_config)

        except FileNotFoundError:
            raise  # Let explicit path errors bubble up
        except Exception as e:
            if self._debug:
                self._output(f"  (MCP config load failed: {e})\n")

    def _apply_mcp_config(self, mcp_config: Dict[str, Any]) -> None:
        """Apply loaded MCP configuration."""
        mcp_servers = mcp_config.get("servers", {})
        planner_cfg = mcp_config.get("planner", {})
        executor_cfg = mcp_config.get("executor", {})

        # Inject headless mode for Playwright MCP if enabled
        if self._headless and mcp_servers:
            mcp_servers = inject_headless_mode(mcp_servers)

        if mcp_servers:
            self.mcp_servers = mcp_servers

            # Get planner MCP config
            planner_servers, planner_tools = get_agent_mcp_config(
                mcp_servers, planner_cfg or {}
            )
            if planner_servers:
                self.planner_mcp_config = {
                    "servers": planner_servers,
                    "tools": planner_tools,
                }

            # Get executor MCP config
            executor_servers, executor_tools = get_agent_mcp_config(
                mcp_servers, executor_cfg or {}
            )
            if executor_servers:
                self.executor_mcp_config = {
                    "servers": executor_servers,
                    "tools": executor_tools,
                }

    def _create_planner(self) -> PlannerAgent:
        """Create or return existing planner agent."""
        if self.planner is None:
            planner_session_id = f"{self.session_id}-planner"
            kwargs = {"session_id": planner_session_id}
            if self.planner_model:
                kwargs["model"] = self.planner_model

            # Add MCP configuration if available
            if self.planner_mcp_config:
                kwargs["mcp_servers"] = self.planner_mcp_config["servers"]
                # Use helper to build tool list (avoids DEFAULT_TOOLS import)
                kwargs["allowed_tools"] = build_allowed_tools(
                    mcp_tools=self.planner_mcp_config["tools"]
                )

            self.planner = create_planner_agent(**kwargs)
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
            kwargs = {"session_id": executor_session_id}
            if self.executor_model:
                kwargs["model"] = self.executor_model

            # Add MCP configuration if available
            if self.executor_mcp_config:
                kwargs["mcp_servers"] = self.executor_mcp_config["servers"]
                # Use helper to build tool list (avoids DEFAULT_TOOLS import)
                kwargs["allowed_tools"] = build_allowed_tools(
                    mcp_tools=self.executor_mcp_config["tools"]
                )

            self.executor = create_executor_agent(**kwargs)
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

        # Send workflow started notification
        self._notify_telegram(
            "notify_workflow_started",
            session_id=self.session_id[:8],
            feature=self.state.feature_description,
            planner_model=self.planner_model,
            executor_model=self.executor_model,
        )

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

        except KeyboardInterrupt:
            # User cancelled - don't mark as failed or log to file, just re-raise
            raise
        except OrchestratorError:
            # Already a typed error (e.g., from _handle_fatal_error), re-raise
            raise
        except Exception as e:
            # Unexpected error - handle and wrap
            self._handle_fatal_error(e)
        finally:
            # Cleanup
            self._cleanup()

    def resume(self, answer: Optional[str] = None) -> None:
        """
        Resume a paused session.

        When resuming with an answer, the answer is stored as a pending response
        and injected into the appropriate agent's conversation when the phase
        continues. This ensures the agent actually receives the human's input.

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

                # Store pending response to inject into agent conversation
                # This ensures the agent actually receives the human's answer
                self._pending_response = {
                    "agent": blocker["agent"],  # "planner" or "executor"
                    "answer": answer,
                    "question": blocker["question"],
                }

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

    def _inject_pending_response(self, target_agent: str) -> Optional[str]:
        """
        Inject pending human response into the appropriate agent's conversation.

        This method checks if there's a pending response from a human (after
        resolving a blocker) and sends it to the agent that raised the blocker.
        This ensures continuity - the agent actually receives the human's answer.

        Args:
            target_agent: The agent type being used ("planner" or "executor")

        Returns:
            The agent's response to the injected message, or None if no pending response
        """
        if not self._pending_response:
            return None

        # Only inject if this is the agent that raised the blocker
        if self._pending_response["agent"] != target_agent:
            return None

        answer = self._pending_response["answer"]
        question = self._pending_response["question"]

        # Clear pending response before sending (prevent re-injection)
        self._pending_response = None

        self._output(f"\n→ Injecting human response to {target_agent}...\n")

        # Format the response with context about what was asked
        injection_prompt = f"""Human response to your previous question:

Question: {question}

Answer: {answer}

Please continue based on this information."""

        # Get the appropriate agent and send the response
        if target_agent == "planner":
            agent = self._create_planner()
        else:
            agent = self._create_executor()

        response = self._send_with_activity(
            agent, injection_prompt, f"{target_agent.capitalize()} processing response"
        )

        # Log the response
        self._log_message(target_agent, "assistant", response)

        return response

    def _output(self, message: str) -> None:
        """Output a message via callback."""
        if self.on_output:
            self.on_output(message)

    def _notify_telegram(self, method_name: str, **kwargs) -> Optional[int]:
        """
        Safely call a telegram notifier method.

        Catches exceptions so telegram errors don't crash the workflow.

        Args:
            method_name: Name of the TelegramNotifier method to call
            **kwargs: Arguments to pass to the method

        Returns:
            Message ID if successful, None otherwise
        """
        if not self.telegram_notifier:
            return None

        try:
            method = getattr(self.telegram_notifier, method_name, None)
            if method:
                return method(**kwargs)
        except Exception as e:
            # Log but don't crash workflow
            self._output(f"  (Telegram notification failed: {e})\n")
        return None

    def _create_activity_indicator(self) -> Optional[StreamingIndicator]:
        """Create an activity indicator if enabled."""
        if not self.show_activity:
            return None
        return StreamingIndicator(interval=1.5, show_tokens=True)

    def _touch_heartbeat(self) -> None:
        """Update session heartbeat to signal activity."""
        try:
            db.touch_session(self.session_id, self.db_path)
        except Exception:
            # Don't let heartbeat failures crash the workflow
            pass

    def _create_heartbeat_callback(
        self,
        original_callback: Optional[callable],
        interval_seconds: int = 60
    ) -> callable:
        """
        Create a callback that updates heartbeat during streaming.

        Wraps the original on_chunk callback and throttles heartbeat updates
        to at most once per interval_seconds.

        Args:
            original_callback: Original on_chunk callback (may be None)
            interval_seconds: Minimum seconds between heartbeat updates

        Returns:
            Wrapped callback function
        """
        import time
        last_heartbeat = [0]  # Use list for mutable closure

        def wrapped_callback(chunk):
            # Call original callback if provided
            if original_callback:
                original_callback(chunk)

            # Throttle heartbeat updates
            now = time.time()
            if now - last_heartbeat[0] >= interval_seconds:
                self._touch_heartbeat()
                last_heartbeat[0] = now

        return wrapped_callback

    def _send_with_activity(
        self,
        agent,
        message: str,
        activity_label: str = "Working"
    ) -> str:
        """
        Send message to agent with optional activity indicator.

        Args:
            agent: Agent to send message to
            message: Message content
            activity_label: Label to show before indicator

        Returns:
            Agent's response
        """
        indicator = self._create_activity_indicator()

        if indicator:
            self._output(f"  {activity_label}... ")

        # Touch heartbeat before sending
        self._touch_heartbeat()

        # Wrap callback to update heartbeat during streaming
        on_chunk = self._create_heartbeat_callback(
            indicator.on_chunk if indicator else None,
            interval_seconds=60
        )

        response = agent.send_message(
            message,
            on_chunk=on_chunk
        )

        # Touch heartbeat after response
        self._touch_heartbeat()

        if indicator:
            indicator.finish()

        return response

    def _run_discovery_loop(self) -> None:
        """
        Run discovery phase conversation.

        Human ↔ Planner until user types /ready.
        """
        self._output("\n=== Phase 1: Discovery ===\n")
        self._output(f"Feature: {self.state.feature_description}\n")
        self._output("\nDiscuss your feature requirements with the Planner.")
        self._output("\nType '/ready' when you're ready to proceed to planning.\n")

        planner = self._create_planner()

        # Wait for user's first message before starting (with paste support)
        display_text, user_input = prompt_with_paste_support("\nYou: ")
        if not user_input:
            # Use feature description as fallback if user just hits enter
            user_input = self.state.feature_description
            display_text = user_input
        # Show collapsed preview if paste was detected
        if display_text != user_input:
            self._output(f"  {display_text}\n")
        self._log_message("human", "user", user_input)

        # Check for /ready command before sending to planner
        if "/ready" in user_input.lower():
            self._output("\n✓ Proceeding to planning phase...\n")
            success, self.state, error = self.state_machine.transition(
                self.session_id,
                TransitionEvent.READY.value
            )
            if not success:
                raise RuntimeError(f"Failed to transition to planning: {error}")
            return

        while True:
            # Send to planner with activity indicator
            self._output("\n")  # Add spacing before activity indicator
            response = self._send_with_activity(planner, user_input, "→ Planner")

            # Log response
            self._log_message("planner", "assistant", response)

            # Output response
            self._output(f"\nPlanner: {response}\n")

            # Check for blockers
            response_type, data = parse_planner_response(response)
            if response_type == PLANNER_BLOCKED:
                self._handle_blocker("planner", data["question"])
                return

            # Get user input (with paste support)
            display_text, user_input = prompt_with_paste_support("\nYou: ")
            # Show collapsed preview if paste was detected
            if display_text != user_input:
                self._output(f"  {display_text}\n")
            self._log_message("human", "user", user_input)

            # Check for /ready command (flexible - can be anywhere in input)
            if "/ready" in user_input.lower():
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

        response = self._send_with_activity(planner, plan_prompt, "Planner creating plan")

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

        # FIX: Inject any pending human response before continuing
        # This ensures the agent receives the human's answer after a blocker is resolved
        executor_injection = self._inject_pending_response("executor")
        planner_injection = self._inject_pending_response("planner")

        # If we injected a response to executor, parse it to continue the flow
        if executor_injection:
            response_type, data = parse_executor_response(executor_injection)
            if response_type == EXECUTOR_REPORT:
                # Agent produced a report after receiving human input
                report_content = data["content"]
                self._output(f"\n✓ Executor produced report after human input\n")
                validation, _ = self._route_to_planner(report_content)
                if validation == "approved":
                    # Milestone was approved, increment counter
                    # FIX: Use explicit None check instead of falsy check
                    # to avoid treating milestone 0 as None (though milestones typically start at 1)
                    base_milestone = self.state.current_milestone if self.state.current_milestone is not None else 1
                    current_milestone = base_milestone + 1
                    success, self.state, error = self.state_machine.transition(
                        self.session_id,
                        TransitionEvent.MILESTONE_APPROVED.value,
                        current_milestone=base_milestone
                    )
                elif validation == "blocked":
                    return
                # For "changes_requested", continue to milestone loop below
            elif response_type == EXECUTOR_BLOCKED:
                self._handle_blocker("executor", data["reason"])
                return

        # FIX: Use explicit None check instead of falsy check
        current_milestone = self.state.current_milestone if self.state.current_milestone is not None else 1
        total_milestones = self.state.total_milestones

        # FIX: Track retry count per milestone to prevent infinite loops
        # when planner keeps requesting changes
        retry_count = 0

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

            # Send to executor with activity indicator
            self._output("→ Sending milestone to Executor...\n")
            executor_response = self._send_with_activity(
                executor, milestone_prompt, "Executor implementing"
            )

            # Log response
            self._log_message("executor", "assistant", executor_response)

            # Parse executor response
            response_type, data = parse_executor_response(executor_response)

            if response_type == EXECUTOR_REPORT:
                report_content = data["content"]
                self._output(f"\n✓ Executor completed milestone {current_milestone}\n")

                # Route to planner for validation
                # FIX: Handle tuple return (validation_result, executor_response)
                validation, executor_feedback_response = self._route_to_planner(report_content)

                if validation == "approved":
                    # Auto-continue to next milestone
                    completed_milestone = current_milestone
                    current_milestone += 1
                    retry_count = 0  # Reset retry count on success
                    success, self.state, error = self.state_machine.transition(
                        self.session_id,
                        TransitionEvent.MILESTONE_APPROVED.value,
                        current_milestone=completed_milestone
                    )
                    if not success:
                        raise RuntimeError(f"Failed to approve milestone: {error}")

                    # Send milestone completion notification
                    self._notify_telegram(
                        "notify_milestone_completed",
                        session_id=self.session_id[:8],
                        milestone_num=completed_milestone,
                        total_milestones=total_milestones,
                        milestone_name=f"Milestone {completed_milestone}",
                    )

                elif validation == "changes_requested":
                    # FIX: Track retry count to prevent infinite loops
                    # After MAX_CHANGES_RETRIES, pause for human intervention
                    retry_count += 1
                    MAX_CHANGES_RETRIES = 3

                    if retry_count >= MAX_CHANGES_RETRIES:
                        self._output(f"\n⚠ Maximum retries ({MAX_CHANGES_RETRIES}) reached for milestone {current_milestone}\n")
                        self._handle_blocker(
                            "executor",
                            f"Milestone {current_milestone} has been retried {retry_count} times without approval. "
                            f"Please review the executor's work and provide guidance."
                        )
                        return

                    # FIX: Parse executor's response to feedback instead of re-sending milestone prompt
                    # The executor already received feedback and responded - use that response
                    if executor_feedback_response:
                        executor_response = executor_feedback_response
                        # Continue the loop - we already have the executor's new response
                        # Parse it and continue without sending another milestone prompt
                        continue

                elif validation == "blocked":
                    # Paused for human input
                    return

            elif response_type == EXECUTOR_CLARIFICATION:
                self._output(f"\n→ Executor needs clarification from Planner\n")
                # Route question to planner with activity indicator
                clarification_response = self._send_with_activity(
                    planner, data["question"], "Planner clarifying"
                )
                # Send response back to executor
                self._route_to_executor(clarification_response)

            elif response_type == EXECUTOR_BLOCKED:
                self._handle_blocker("executor", data["reason"])
                return

            else:
                # FIX: Detect truncated responses and attempt auto-continuation
                # This handles cases where executor hits token limits mid-response
                if is_response_truncated(executor_response):
                    self._output("\n⚠ Executor response appears truncated. Requesting continuation...\n")

                    # Ask executor to continue and provide the required report
                    # Keep prompt concise to reduce risk of re-truncation
                    continuation_prompt = (
                        "Your previous response was cut off. "
                        "Please provide a brief [PROGRESS_REPORT]...[/PROGRESS_REPORT] summarizing "
                        "what was completed, or [BLOCKED] if you cannot proceed. "
                        "Keep your response concise."
                    )
                    continuation = self._send_with_activity(
                        executor, continuation_prompt, "Executor continuing"
                    )
                    self._log_message("executor", "assistant", continuation)

                    # Re-parse the continuation response
                    response_type, data = parse_executor_response(continuation)

                    if response_type == EXECUTOR_REPORT:
                        # Success - process the report normally
                        report_content = data["content"]
                        self._output(f"\n✓ Executor completed milestone {current_milestone} (after continuation)\n")
                        validation, executor_feedback_response = self._route_to_planner(report_content)

                        if validation == "approved":
                            success, self.state, error = self.state_machine.transition(
                                self.session_id,
                                TransitionEvent.MILESTONE_APPROVED.value
                            )
                            if not success:
                                raise RuntimeError(f"State transition failed: {error}")
                            current_milestone = self.state.current_milestone
                            continue
                        elif validation == "changes_requested":
                            if executor_feedback_response:
                                executor_response = executor_feedback_response
                                continue
                        elif validation == "blocked":
                            return

                    elif response_type == EXECUTOR_BLOCKED:
                        self._handle_blocker("executor", data["reason"])
                        return

                    elif response_type == EXECUTOR_CLARIFICATION:
                        # Route clarification to planner
                        self._output(f"\n→ Executor needs clarification from Planner\n")
                        clarification_response = self._send_with_activity(
                            planner, data["question"], "Planner clarifying"
                        )
                        self._route_to_executor(clarification_response)
                        continue

                    # Continuation didn't produce a valid response either
                    self._output("\n⚠ Continuation also unrecognized. Pausing for human review.\n")
                    self._handle_blocker(
                        "executor",
                        f"Executor response was truncated and continuation attempt also failed to produce "
                        f"expected tags. The executor may be stuck or hitting output limits. "
                        f"Please review the session logs and provide guidance."
                    )
                    return

                # Not truncated, just unrecognized format
                self._output("\n⚠ Executor response not recognized. Pausing.\n")
                self._handle_blocker(
                    "executor",
                    f"Executor response did not contain expected tags ([PROGRESS_REPORT], "
                    f"[CLARIFICATION_NEEDED], or [BLOCKED]). Please review and provide guidance."
                )
                return

        # All milestones complete
        self._output("\n✓ All milestones complete!\n")
        success, self.state, error = self.state_machine.transition(
            self.session_id,
            TransitionEvent.ALL_MILESTONES_DONE.value
        )
        if not success:
            raise RuntimeError(f"Failed to complete workflow: {error}")

        # Send workflow completion notification
        self._notify_telegram(
            "notify_workflow_completed",
            session_id=self.session_id[:8],
            feature=self.state.feature_description,
            total_milestones=total_milestones,
        )

    def _route_to_planner(self, report: str) -> Tuple[str, Optional[str]]:
        """
        Route progress report to planner for validation.

        Args:
            report: Executor's progress report

        Returns:
            Tuple of (validation_result, executor_response):
            - validation_result: "approved", "changes_requested", or "blocked"
            - executor_response: Executor's response to feedback (for changes_requested), None otherwise
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

        response = self._send_with_activity(planner, validation_prompt, "Planner reviewing")

        # Log response
        self._log_message("planner", "assistant", response)

        # Parse response
        response_type, data = parse_planner_response(response)

        if response_type == PLANNER_APPROVED:
            milestone_num = data.get("milestone", self.state.current_milestone)
            self._output(f"\n✓ Planner approved Milestone {milestone_num}\n")
            return ("approved", None)

        elif response_type == PLANNER_CHANGES_REQUESTED:
            issues = data.get("issues", [])
            self._output(f"\n⚠ Planner requested changes:\n")
            for issue in issues:
                self._output(f"  - {issue}\n")

            # Send feedback to executor and capture response
            # FIX: Return executor's response so main loop can parse it
            # instead of re-sending the milestone prompt (which caused duplicates)
            if issues:
                issues_text = "\n".join([f"- {issue}" for issue in issues])
            else:
                issues_text = "- No specific issues parsed. Please review the planner's feedback above and address any concerns mentioned."
            feedback = CHANGES_REQUESTED_TEMPLATE.format(
                milestone_number=self.state.current_milestone,
                issues=issues_text
            )
            executor_response = self._route_to_executor(feedback)
            return ("changes_requested", executor_response)

        elif response_type == PLANNER_BLOCKED:
            question = data.get("question", "Unknown question")
            self._handle_blocker("planner", question)
            return ("blocked", None)

        else:
            # FIX: Detect truncated responses and attempt auto-continuation
            # This handles cases where planner hits token limits mid-response
            if is_response_truncated(response):
                self._output("\n⚠ Planner response appears truncated. Requesting continuation...\n")

                # Ask planner to continue and provide the required tag
                # Keep prompt concise to reduce risk of re-truncation
                continuation_prompt = (
                    "Your previous response was cut off. "
                    "Please provide your verdict briefly: [MILESTONE_APPROVED], "
                    "[CHANGES_REQUESTED] with a short list of issues, or [HUMAN_INPUT_NEEDED]. "
                    "Keep your response concise (1-2 sentences max)."
                )
                continuation = self._send_with_activity(
                    planner, continuation_prompt, "Planner continuing"
                )
                self._log_message("planner", "assistant", continuation)

                # Re-parse the continuation response
                response_type, data = parse_planner_response(continuation)

                if response_type == PLANNER_APPROVED:
                    milestone_num = data.get("milestone", self.state.current_milestone)
                    self._output(f"\n✓ Planner approved Milestone {milestone_num} (after continuation)\n")
                    return ("approved", None)

                elif response_type == PLANNER_CHANGES_REQUESTED:
                    issues = data.get("issues", [])
                    self._output(f"\n⚠ Planner requested changes:\n")
                    for issue in issues:
                        self._output(f"  - {issue}\n")
                    if issues:
                        issues_text = "\n".join([f"- {issue}" for issue in issues])
                    else:
                        issues_text = "- No specific issues parsed. Please review the planner's feedback above and address any concerns mentioned."
                    feedback = CHANGES_REQUESTED_TEMPLATE.format(
                        milestone_number=self.state.current_milestone,
                        issues=issues_text
                    )
                    executor_response = self._route_to_executor(feedback)
                    return ("changes_requested", executor_response)

                elif response_type == PLANNER_BLOCKED:
                    question = data.get("question", "Unknown question")
                    self._handle_blocker("planner", question)
                    return ("blocked", None)

                # Continuation didn't produce a valid response either
                self._output("\n⚠ Continuation also unrecognized. Pausing for human review.\n")
                self._handle_blocker(
                    "planner",
                    f"Planner response was truncated and continuation attempt also failed to produce "
                    f"expected tags. The planner may be stuck or hitting output limits. "
                    f"Please review the session logs and provide guidance."
                )
                return ("blocked", None)

            # Not truncated, just unrecognized format
            self._output("\n⚠ Planner response not recognized. Creating blocker for review.\n")
            self._handle_blocker(
                "planner",
                f"Planner response did not contain expected tags ([MILESTONE_APPROVED], "
                f"[CHANGES_REQUESTED], or [HUMAN_INPUT_NEEDED]). Please review the response "
                f"and provide guidance on how to proceed."
            )
            return ("blocked", None)

    def _route_to_executor(self, feedback: str) -> str:
        """
        Route feedback to executor.

        Args:
            feedback: Planner's feedback or instructions

        Returns:
            Executor's response (for parsing in the main loop)
        """
        executor = self._create_executor()

        response = self._send_with_activity(executor, feedback, "Executor working")

        # Log
        self._log_message("executor", "assistant", response)

        self._output(f"\n→ Executor response: {response[:200]}...\n")

        # Check for truncated response and auto-continue if needed
        if is_response_truncated(response):
            self._output("\n⚠ Executor response appears truncated. Requesting continuation...\n")

            continuation_prompt = (
                "Your previous response was cut off. "
                "Please provide a brief [PROGRESS_REPORT]...[/PROGRESS_REPORT] summarizing "
                "what was completed, or [BLOCKED] if you cannot proceed. "
                "Keep your response concise."
            )
            continuation = self._send_with_activity(
                executor, continuation_prompt, "Executor continuing"
            )
            self._log_message("executor", "assistant", continuation)
            response = continuation

        return response

    def _handle_blocker(self, agent: str, question: str) -> None:
        """
        Handle a blocker by pausing the workflow.

        Args:
            agent: Agent that raised the blocker
            question: Question or issue
        """
        self._output(f"\n⏸ Workflow paused - {agent} needs input:\n")
        self._output(f"  {question}\n")
        # Show CLI command with session ID for easy copy-paste
        short_id = self.session_id[:8]
        self._output(f"\nTo continue, run:\n")
        self._output(f"  orchestrator respond {short_id} \"your answer here\"\n")

        # Create blocker record
        blocker_id = db.create_blocker(
            session_id=self.session_id,
            agent=agent,
            question=question,
            db_path=self.db_path
        )
        self.current_blocker_id = blocker_id

        # Send blocker notification and store message_id for reply tracking
        telegram_message_id = self._notify_telegram(
            "notify_blocker",
            session_id=self.session_id[:8],
            blocker_id=blocker_id,
            question=question,
            agent=agent.capitalize(),
        )

        # Store telegram message_id for reply-to-blocker routing (Phase 2)
        if telegram_message_id:
            try:
                db.set_blocker_telegram_message_id(
                    blocker_id=blocker_id,
                    telegram_message_id=telegram_message_id,
                    db_path=self.db_path
                )
            except Exception:
                pass  # Don't crash workflow on DB error

        # Transition to paused
        success, self.state, error = self.state_machine.transition(
            self.session_id,
            TransitionEvent.HUMAN_INPUT_NEEDED.value
        )
        if not success:
            raise RuntimeError(f"Failed to pause: {error}")

    def _handle_fatal_error(self, error: Exception) -> None:
        """
        Handle fatal error: mark session failed, log to DB and file.

        This ensures session row is marked failed even if queue mode
        only catches at CLI level. Without this, the session row would
        remain "active" causing misleading `orchestrator list` output
        and incorrect stuck session detection.

        Args:
            error: The exception that caused the failure

        Raises:
            AgentError: Always raises with session context for CLI boundary
        """
        # Log full stack trace to file
        self._logger.exception("Orchestration failed")

        # Get current state for context
        session = db.get_session(self.session_id, self.db_path)
        current_phase = session.get("phase") if session else "unknown"
        current_milestone = session.get("current_milestone") if session else None

        # Transition to FAILED state (sets phase=completed, status=failed)
        try:
            success, _, transition_error = self.state_machine.transition(
                self.session_id,
                TransitionEvent.FAILED.value
            )
            if not success:
                # Transition returned failure (e.g., invalid state) - fallback to direct DB update
                self._logger.warning(f"State transition to FAILED returned failure: {transition_error}")
                db.update_session(
                    self.session_id,
                    {"phase": "completed", "status": "failed"},
                    self.db_path
                )
        except Exception as transition_error:
            # Exception during transition - fallback to direct DB update
            self._logger.error(f"Failed to transition to FAILED state: {transition_error}")
            try:
                db.update_session(
                    self.session_id,
                    {"phase": "completed", "status": "failed"},
                    self.db_path
                )
            except Exception as db_update_error:
                self._logger.error(f"Fallback DB update also failed: {db_update_error}")

        # Persist error details to session_errors table
        stack_trace = "".join(traceback.format_exception(type(error), error, error.__traceback__))
        try:
            db.log_session_error(
                session_id=self.session_id,
                error_type=type(error).__name__,
                error_message=str(error),
                stack_trace=stack_trace,
                phase=current_phase,
                milestone_number=current_milestone,
                log_file_path=self._log_path,
                db_path=self.db_path
            )
        except Exception as db_error:
            # Log but don't mask the original error
            self._logger.error(f"Failed to persist error to database: {db_error}")

        # Wrap and re-raise as typed exception for CLI boundary
        raise AgentError(
            str(error),
            session_id=self.session_id,
            log_path=self._log_path
        ) from error

    def _cleanup(self) -> None:
        """Cleanup resources."""
        if self.planner:
            self.planner.close()
        if self.executor:
            self.executor.close()
        if self.telegram_notifier:
            self.telegram_notifier.close()
        # Teardown session logger (prevents handler accumulation in queue/watch mode)
        if hasattr(self, '_logger') and self._logger:
            teardown_session_logger(self._logger)

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
            "planner_model": self.planner_model,
            "executor_model": self.executor_model,
        }
