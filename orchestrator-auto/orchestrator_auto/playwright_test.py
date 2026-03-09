"""
MCP Playwright verification tool.

Provides a CLI tool to verify that Planner and Executor agents can access
and successfully use Playwright MCP tools.
"""

import asyncio
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Literal

from .agents import (
    PlannerAgent,
    ExecutorAgent,
    build_allowed_tools,
)
from .config import (
    load_mcp_config,
    find_repo_root,
    resolve_model,
)


# MCP tools required for verification (explicit list to avoid tool-name drift)
PLAYWRIGHT_MCP_TOOLS = [
    "mcp__playwright__browser_navigate",
    "mcp__playwright__browser_snapshot",
    "mcp__playwright__browser_click",
    "mcp__playwright__browser_type",
    "mcp__playwright__browser_console_messages",
    "mcp__playwright__browser_network_requests",
    "mcp__playwright__browser_take_screenshot",
    "mcp__playwright__browser_close",
]

# Default output directory base
DEFAULT_ARTIFACT_DIR = Path(".orchestrator_artifacts/playwright-test")

# Default model for test agents
DEFAULT_TEST_MODEL = "claude-sonnet-4-6"


def _generate_verification_prompt(test_url: str, role: str) -> str:
    """Generate the verification prompt for the agent."""
    screenshot_name = f"{role}_test.png"

    return f"""You are testing MCP Playwright tool integration.

Your task is to verify that Playwright MCP tools work correctly by performing these steps IN ORDER:

1. Navigate to: {test_url}
2. Take a snapshot and briefly describe the visible top-level elements (h1, links, etc.)
3. Click the link with data-testid="nav-form" (the "Go to form" link)
4. Wait for the form page to load, then type "testuser" into the input with data-testid="username"
5. Collect console messages and report any [mcp-test] prefixed messages
6. Collect network requests and report any /api/ requests you see (ping, fail)
7. Take a screenshot and save it as: {screenshot_name}
8. Close the browser

IMPORTANT:
- Use the exact tool names provided (mcp__playwright__*)
- Report any errors you encounter
- At the end, confirm whether the screenshot was saved successfully

Execute each step and report your findings.
"""


def _find_screenshot_path(out_dir: Path, role: str) -> Optional[Path]:
    """Locate screenshot created by Playwright MCP.

    Playwright MCP commonly writes artifacts under a `.playwright-mcp/` sandbox
    directory. This helper accepts both direct output and sandboxed output.
    """
    filename = f"{role}_test.png"

    direct_path = out_dir / filename
    if direct_path.exists():
        return direct_path

    sandbox_dir = out_dir / ".playwright-mcp"
    preferred_sandbox_path = sandbox_dir / filename
    if preferred_sandbox_path.exists():
        return preferred_sandbox_path

    if sandbox_dir.exists():
        matches = sorted(sandbox_dir.rglob(filename))
        if matches:
            return matches[0]

    return None


def _create_output_dir(out_dir: Optional[Path] = None) -> Path:
    """
    Create and return the output directory for artifacts.

    If out_dir is None, creates a timestamped directory under the default location.
    """
    if out_dir is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_dir = DEFAULT_ARTIFACT_DIR / timestamp

    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir


def _load_mcp_servers(mcp_config_path: Optional[str] = None) -> dict:
    """
    Load MCP server configuration.

    Priority:
    1. Explicit path (--mcp-config)
    2. Project .mcp.json
    3. Global ~/.mcp.json
    """
    project_root = find_repo_root()
    mcp_servers, _, _ = load_mcp_config(mcp_config_path, project_root)

    if not mcp_servers:
        raise ValueError(
            "No MCP configuration found. Provide --mcp-config or create .mcp.json"
        )

    # Check for playwright server
    if "playwright" not in mcp_servers:
        available = list(mcp_servers.keys())
        raise ValueError(
            f"Playwright MCP server not found in config. "
            f"Available servers: {available}"
        )

    # Return only the playwright server
    return {"playwright": mcp_servers["playwright"]}


def run_playwright_test(
    role: Literal["planner", "executor"],
    test_url: str,
    mcp_config_path: Optional[str] = None,
    out_dir: Optional[Path] = None,
    timeout: int = 120,
    model: Optional[str] = None,
    verbose: bool = False,
) -> tuple[bool, str, Path]:
    """
    Run Playwright MCP verification for a single agent role.

    Args:
        role: Agent role to test ("planner" or "executor")
        test_url: URL to the test website
        mcp_config_path: Path to MCP config file (optional)
        out_dir: Output directory for artifacts (optional)
        timeout: Overall timeout in seconds
        model: Model override (optional)
        verbose: Print full agent response

    Returns:
        Tuple of (success, message, out_dir)
    """
    # Setup output directory
    actual_out_dir = _create_output_dir(out_dir)

    # Load MCP config
    try:
        mcp_servers = _load_mcp_servers(mcp_config_path)
    except (ValueError, FileNotFoundError) as e:
        return False, str(e), actual_out_dir

    # Build allowed tools
    allowed_tools = build_allowed_tools(mcp_tools=PLAYWRIGHT_MCP_TOOLS)

    # Resolve model
    resolved_model = resolve_model(model) or DEFAULT_TEST_MODEL

    # Create agent
    agent = None
    try:
        if role == "planner":
            agent = PlannerAgent(
                model=resolved_model,
                session_id=f"playwright-test-{role}",
                mcp_servers=mcp_servers,
                allowed_tools=allowed_tools,
                cwd=actual_out_dir,
            )
        else:
            agent = ExecutorAgent(
                model=resolved_model,
                session_id=f"playwright-test-{role}",
                mcp_servers=mcp_servers,
                allowed_tools=allowed_tools,
                cwd=actual_out_dir,
            )

        # Generate and send verification prompt with timeout
        prompt = _generate_verification_prompt(test_url, role)
        try:
            loop = agent._get_loop()
            response = loop.run_until_complete(
                asyncio.wait_for(
                    agent.send_message_async(prompt),
                    timeout=timeout,
                )
            )
        except asyncio.TimeoutError:
            return (
                False,
                f"Timeout after {timeout}s waiting for {role} agent",
                actual_out_dir,
            )

        if verbose:
            print("\n--- Agent Response ---")
            print(response)
            print("--- End Response ---\n")

        # Validate artifacts
        screenshot_path = _find_screenshot_path(actual_out_dir, role)
        if screenshot_path is None:
            expected = actual_out_dir / f"{role}_test.png"
            expected_sandbox = actual_out_dir / ".playwright-mcp" / f"{role}_test.png"
            return (
                False,
                "Screenshot not created. Looked for: "
                f"{expected} and {expected_sandbox}",
                actual_out_dir,
            )

        if screenshot_path.stat().st_size == 0:
            return (
                False,
                f"Screenshot is empty: {screenshot_path}",
                actual_out_dir,
            )

        return True, f"Verification passed for {role}", actual_out_dir

    except Exception as e:
        return False, f"Error during {role} test: {e}", actual_out_dir

    finally:
        if agent:
            try:
                agent.close()
            except Exception:
                pass


def run_playwright_test_both(
    test_url: str,
    mcp_config_path: Optional[str] = None,
    out_dir: Optional[Path] = None,
    timeout: int = 120,
    model: Optional[str] = None,
    verbose: bool = False,
) -> tuple[bool, dict, Path]:
    """
    Run Playwright MCP verification for both planner and executor.

    Runs planner first, then executor sequentially with a short sleep between.

    Args:
        test_url: URL to the test website
        mcp_config_path: Path to MCP config file (optional)
        out_dir: Output directory for artifacts (optional)
        timeout: Overall timeout in seconds per role
        model: Model override (optional)
        verbose: Print full agent responses

    Returns:
        Tuple of (all_passed, results_dict, out_dir)
        results_dict has format: {"planner": (success, msg), "executor": (success, msg)}
    """
    # Use shared output directory
    actual_out_dir = _create_output_dir(out_dir)

    results = {}

    # Run planner
    planner_success, planner_msg, _ = run_playwright_test(
        role="planner",
        test_url=test_url,
        mcp_config_path=mcp_config_path,
        out_dir=actual_out_dir,
        timeout=timeout,
        model=model,
        verbose=verbose,
    )
    results["planner"] = (planner_success, planner_msg)

    # Short sleep between runs to reduce MCP process contention
    time.sleep(2)

    # Run executor
    executor_success, executor_msg, _ = run_playwright_test(
        role="executor",
        test_url=test_url,
        mcp_config_path=mcp_config_path,
        out_dir=actual_out_dir,
        timeout=timeout,
        model=model,
        verbose=verbose,
    )
    results["executor"] = (executor_success, executor_msg)

    all_passed = planner_success and executor_success
    return all_passed, results, actual_out_dir
