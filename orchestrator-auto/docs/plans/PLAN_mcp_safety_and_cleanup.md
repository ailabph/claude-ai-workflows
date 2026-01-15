# Implementation Plan: MCP Safety & Cleanup

## Overview

This plan implements safeguards against MCP-related crashes and provides recovery tools. Split into two phases:

- **Phase 1** (Quick Wins): Prompt safety rules + CLI cleanup + health check (~2 hours)
- **Phase 2** (Robust Prevention): MCP wrapper proxy for response size guard (~6-8 hours)

---

## ⚠️ Important Architecture Notes

### Proxy Integration Reality

The Claude Agent SDK spawns MCP processes internally from the `mcp_servers` config. The SDK's message reader has a hardcoded 1MB buffer limit. When an MCP response exceeds this limit, the crash happens **inside the SDK** before any Python code can intercept.

**This means:**
- We **cannot** intercept responses in Python after the SDK reads them (too late)
- The only viable approach is a **wrapper executable** that sits between SDK and MCP server
- The wrapper intercepts responses **before** they reach the SDK

```
❌ Wrong (Python interception - too late):
┌─────────┐     ┌─────────┐     ┌─────────────┐
│   SDK   │────▶│ Python  │────▶│ MCP Server  │
│ (crash) │◀────│  Proxy  │◀────│             │
└─────────┘     └─────────┘     └─────────────┘
       ↑
SDK crashes here before Python sees response

✅ Correct (Wrapper executable):
┌─────────┐     ┌──────────────────┐     ┌─────────────┐
│   SDK   │────▶│ Wrapper Script   │────▶│ MCP Server  │
│         │◀────│ (spawns real MCP)│◀────│  (real)     │
└─────────┘     └──────────────────┘     └─────────────┘
                        ↑
        Intercepts BEFORE SDK sees response
        Returns truncated/error if too large
```

### Cleanup Scope Warning

The `pgrep`/`pkill` pattern matching approach can be **over-broad**:

- `pkill -f ms-playwright` kills ALL Playwright browsers on the system
- This includes: developer running `npx playwright test`, Claude Code with Playwright MCP, etc.
- **Not orchestrator-specific** - no way to distinguish "our" processes from others

**Mitigations in Phase 1:**
- `--dry-run` flag to preview before killing
- Confirmation prompt by default
- `--pattern` flag for user-specified narrower patterns
- Clear documentation of the risk

**Future improvement (not in this plan):**
- Session-scoped cleanup via PID tracking or env var markers
- Inject `ORCH_SESSION_ID=<id>` into MCP server env, kill only matching processes

---

## Phase 1: Quick Wins

### Milestone 1: Executor Prompt Safety Rules

**Goal**: Reduce `browser_snapshot` crashes through LLM guidance.

**File**: `orchestrator_auto/prompts.py`

**Changes**: Add MCP Playwright safety section to `EXECUTOR_SYSTEM_PROMPT`.

**Deliverables**:

```python
# Add to EXECUTOR_SYSTEM_PROMPT in prompts.py, after the existing guidelines

MCP_PLAYWRIGHT_SAFETY = """
## MCP Playwright Safety Rules

CRITICAL: The `browser_snapshot` tool can crash the session on complex pages due to response size limits.

### Rules:

1. **NEVER use `browser_snapshot` on**:
   - Dashboards with charts/graphs/widgets
   - Tables with more than 20 rows
   - Admin panels with many form controls
   - Pages with infinite scroll or lazy-loaded content
   - Any page that looks "busy" or data-heavy

2. **ALWAYS prefer `browser_take_screenshot`** for visual verification - it's safer and usually sufficient.

3. **For element inspection**, use targeted snapshots with the `ref` parameter on specific elements, not full-page snapshots.

4. **If you need page structure**, describe what you see in the screenshot rather than requesting a snapshot.

### Safe Pattern:
```
# Instead of this (DANGEROUS on complex pages):
browser_snapshot()

# Do this (SAFE):
browser_take_screenshot()
# Then describe what you observe in the screenshot
```

### If `browser_snapshot` fails:
If you encounter an error mentioning "buffer size" or "response too large", immediately switch to `browser_take_screenshot` and continue your task.
"""
```

**Integration**:
```python
# In prompts.py, update EXECUTOR_SYSTEM_PROMPT
EXECUTOR_SYSTEM_PROMPT = f"""
{EXISTING_EXECUTOR_PROMPT}

{MCP_PLAYWRIGHT_SAFETY}
"""
```

**Testing**:
- Manual: Start session with Playwright MCP, verify prompt includes safety rules
- Unit: Assert `MCP_PLAYWRIGHT_SAFETY` in `EXECUTOR_SYSTEM_PROMPT`

**Limitations**: Relies on LLM following instructions. Not guaranteed to prevent all crashes.

---

### Milestone 2: CLI Cleanup Command

**Goal**: Provide manual recovery for orphaned MCP processes.

**File**: `orchestrator_auto/cli.py`

**New Command**: `orchestrator cleanup`

**⚠️ Warning**: This command uses pattern matching that may kill unrelated Playwright processes. Always use `--dry-run` first in shared environments.

**Deliverables**:

```python
# cli.py - Add new command

# Default patterns - intentionally conservative
DEFAULT_MCP_PATTERNS = [
    ("Playwright MCP Server", "mcp-server-playwright"),
    ("MCP NPX Process", "npx.*@playwright/mcp"),
]

# Extended patterns - more aggressive, higher risk of false positives
EXTENDED_MCP_PATTERNS = [
    ("Playwright Chrome", "ms-playwright/mcp-chrome"),
    ("Playwright Chromium", "ms-playwright/chromium"),
]


@cli.command()
@click.option('--dry-run', is_flag=True, help='Show what would be killed without actually killing')
@click.option('--force', '-f', is_flag=True, help='Skip confirmation prompt')
@click.option('--all', 'kill_all', is_flag=True, help='Include browser processes (may affect other Playwright users)')
@click.option('--pattern', '-p', multiple=True, help='Custom pattern(s) to match (can be specified multiple times)')
def cleanup(dry_run: bool, force: bool, kill_all: bool, pattern: tuple):
    """Kill orphaned MCP processes (Playwright MCP servers).

    By default, only kills MCP server processes. Use --all to also kill
    Playwright browser processes (WARNING: may affect other Playwright users).

    \b
    ⚠️  WARNING: Pattern matching may kill unrelated processes.
    Always use --dry-run first to preview what will be killed.

    Examples:

    \b
        orchestrator cleanup              # Kill MCP servers only (safe)
        orchestrator cleanup --dry-run    # Preview what would be killed
        orchestrator cleanup --all        # Also kill browser processes
        orchestrator cleanup -p "my-mcp"  # Custom pattern
    """
    import subprocess
    import platform

    if platform.system() == "Windows":
        click.secho("⚠ Windows cleanup not yet supported. Please use Task Manager.", fg="yellow")
        click.echo("Look for: node.exe (mcp-server), chrome.exe (playwright)")
        sys.exit(1)

    # Build pattern list
    if pattern:
        # User-specified patterns
        patterns = [("Custom", p) for p in pattern]
    else:
        patterns = list(DEFAULT_MCP_PATTERNS)
        if kill_all:
            patterns.extend(EXTENDED_MCP_PATTERNS)

    click.secho("🔍 Scanning for MCP processes...\n", fg="cyan")

    if not kill_all and not pattern:
        click.secho("ℹ  Using conservative patterns (MCP servers only).", fg="blue")
        click.secho("   Use --all to include browser processes (may affect other users).\n", fg="blue")

    found_processes = []

    for name, pat in patterns:
        try:
            result = subprocess.run(
                ["pgrep", "-f", pat],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                pids = result.stdout.strip().split('\n')
                for pid in pids:
                    if pid:
                        found_processes.append((name, pat, pid))
        except Exception:
            pass

    if not found_processes:
        click.secho("✓ No matching MCP processes found.", fg="green")
        return

    # Display found processes
    click.secho(f"Found {len(found_processes)} process(es):\n", fg="yellow")
    for name, pat, pid in found_processes:
        # Try to get process command for clarity
        try:
            cmd_result = subprocess.run(
                ["ps", "-p", pid, "-o", "command="],
                capture_output=True,
                text=True,
                timeout=2
            )
            cmd = cmd_result.stdout.strip()[:60] + "..." if len(cmd_result.stdout.strip()) > 60 else cmd_result.stdout.strip()
        except Exception:
            cmd = f"(pattern: {pat})"
        click.echo(f"  • PID {pid}: {cmd}")
    click.echo()

    # Warning for --all mode
    if kill_all:
        click.secho("⚠  WARNING: --all mode may kill Playwright processes from other applications!", fg="yellow", bold=True)
        click.echo()

    if dry_run:
        click.secho("Dry run - no processes killed.", fg="cyan")
        return

    # Confirm unless forced
    if not force:
        if not click.confirm("Kill these processes?"):
            click.echo("Aborted.")
            return

    # Kill processes
    killed = 0
    for name, pat, pid in found_processes:
        try:
            subprocess.run(["kill", "-9", pid], capture_output=True, timeout=5)
            click.secho(f"  ✓ Killed PID {pid}", fg="green")
            killed += 1
        except Exception as e:
            click.secho(f"  ✗ Failed to kill PID {pid}: {e}", fg="red")

    click.echo()
    click.secho(f"Cleanup complete. Killed {killed}/{len(found_processes)} processes.",
                fg="green" if killed == len(found_processes) else "yellow")
```

**Testing**:
```python
# tests/test_cli.py

class TestCleanupCommand:
    """Test orchestrator cleanup command."""

    def test_cleanup_no_processes(self, cli_runner):
        """Test cleanup when no orphaned processes exist."""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = Mock(returncode=1, stdout='')
            result = cli_runner.invoke(cli, ['cleanup'])
            assert 'No matching MCP processes found' in result.output

    def test_cleanup_dry_run(self, cli_runner):
        """Test cleanup dry run shows but doesn't kill."""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = Mock(returncode=0, stdout='12345\n')
            result = cli_runner.invoke(cli, ['cleanup', '--dry-run'])
            assert 'Dry run' in result.output
            assert 'PID 12345' in result.output

    def test_cleanup_conservative_by_default(self, cli_runner):
        """Test that cleanup uses conservative patterns by default."""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = Mock(returncode=1, stdout='')
            result = cli_runner.invoke(cli, ['cleanup'])
            assert 'conservative patterns' in result.output.lower()

    def test_cleanup_all_flag_warning(self, cli_runner):
        """Test that --all flag shows warning."""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = Mock(returncode=0, stdout='12345\n')
            result = cli_runner.invoke(cli, ['cleanup', '--all', '--dry-run'])
            assert 'WARNING' in result.output
            assert 'other applications' in result.output

    def test_cleanup_custom_pattern(self, cli_runner):
        """Test cleanup with custom pattern."""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = Mock(returncode=0, stdout='99999\n')
            result = cli_runner.invoke(cli, ['cleanup', '-p', 'my-custom-mcp', '--dry-run'])
            assert 'PID 99999' in result.output
```

---

### Milestone 3: Health Check Enhancement

**Goal**: Detect potential orphaned processes in `orchestrator check`.

**File**: `orchestrator_auto/cli.py`

**Changes**: Enhance existing `check` command with orphan detection.

**Note**: Detection uses same pattern matching as cleanup - may show false positives from other Playwright users.

**Deliverables**:

```python
# cli.py - Add helper function

def _detect_mcp_processes() -> List[Tuple[str, str, str]]:
    """Detect running MCP-related processes.

    Returns:
        List of (process_name, pattern, pid) tuples

    Note: May include processes from other applications using Playwright.
    """
    import subprocess
    import platform

    if platform.system() == "Windows":
        return []  # Not supported on Windows yet

    # Only check for MCP servers (conservative)
    MCP_PATTERNS = [
        ("Playwright MCP Server", "mcp-server-playwright"),
    ]

    found = []
    for name, pattern in MCP_PATTERNS:
        try:
            result = subprocess.run(
                ["pgrep", "-f", pattern],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                for pid in result.stdout.strip().split('\n'):
                    if pid:
                        found.append((name, pattern, pid))
        except Exception:
            pass

    return found


# Update the existing check command to include MCP process detection
# Add after API connectivity check:

    # Check for MCP processes (potential orphans)
    mcp_processes = _detect_mcp_processes()
    if mcp_processes:
        click.secho(f"⚠ MCP processes detected: {len(mcp_processes)} running", fg="yellow")
        for name, _, pid in mcp_processes[:3]:
            click.echo(f"    • {name} (PID: {pid})")
        if len(mcp_processes) > 3:
            click.echo(f"    ... and {len(mcp_processes) - 3} more")
        click.echo(f"    These may be orphaned. Run: orchestrator cleanup --dry-run")
        # Note: Don't fail check for this, just warn
    else:
        click.secho("✓ No MCP server processes detected", fg="green")
```

**Expected Output**:
```bash
$ orchestrator check
✓ Authentication: API key (sk-ant-...XXXX)
✓ Claude Agent SDK: 0.1.16
✓ API connectivity: OK
⚠ MCP processes detected: 2 running
    • Playwright MCP Server (PID: 12345)
    • Playwright MCP Server (PID: 12346)
    These may be orphaned. Run: orchestrator cleanup --dry-run

All critical checks passed. Review warnings above.
```

---

### Milestone 4: Documentation & Testing

**Deliverables**:

1. **README.md** - Add to Troubleshooting section:
```markdown
### MCP Process Cleanup

If a session crashes while using Playwright MCP, browser/server processes may be left running.

**Detect potential orphans:**
```bash
orchestrator check
```

**Clean up MCP server processes:**
```bash
orchestrator cleanup --dry-run   # Preview first!
orchestrator cleanup             # Interactive cleanup
orchestrator cleanup -f          # Force without confirmation
```

**Include browser processes (use with caution):**
```bash
orchestrator cleanup --all --dry-run  # Preview
orchestrator cleanup --all            # Kill servers + browsers
```

> ⚠️ **Warning**: The `--all` flag may kill Playwright processes from other applications
> (e.g., if you're running `npx playwright test` in another terminal). Always preview
> with `--dry-run` first.

**Common crash cause:** Using `browser_snapshot` on complex pages (dashboards, large tables)
can exceed the 1MB response buffer limit. The executor is instructed to prefer
`browser_take_screenshot` for safety.
```

2. **Unit tests** - See test code in milestones above

---

## Phase 2: MCP Wrapper Proxy

### ⚠️ Architecture Requirement

The proxy **must** be implemented as a wrapper executable, not Python-level interception.

**Why**: The Claude Agent SDK spawns MCP processes and reads their stdout directly. The 1MB buffer crash occurs inside the SDK's message reader. By the time Python code could intercept, the SDK has already crashed.

**Solution**: Replace the MCP command in config with our wrapper script. The wrapper:
1. Spawns the real MCP server as a subprocess
2. Reads responses from the real server
3. Checks response size before forwarding to SDK
4. Returns graceful error if response exceeds limit

### Milestone 5: MCP Wrapper Script

**Goal**: Create standalone wrapper that intercepts MCP responses.

**New File**: `orchestrator_auto/scripts/mcp_size_guard.py`

**Architecture**:
```
SDK spawns this:
┌─────────────────────────────────────────────────────────────┐
│  mcp-size-guard npx @playwright/mcp@latest                  │
│  ├── Spawns real MCP: npx @playwright/mcp@latest            │
│  ├── Parses stdin to track request IDs (for error responses)│
│  ├── Reads response from real MCP stdout                    │
│  ├── If response > 900KB: return error JSON with request ID │
│  ├── If partial > 900KB: emit error, drain until newline    │
│  └── Else: forward response to own stdout (SDK reads this)  │
└─────────────────────────────────────────────────────────────┘
```

**Deliverables**:

```python
#!/usr/bin/env python3
"""
MCP Size Guard - Wrapper to prevent oversized MCP responses from crashing the SDK.

Usage:
    mcp-size-guard <original-command> [args...]

Example:
    mcp-size-guard npx @playwright/mcp@latest

The wrapper spawns the real MCP server and proxies stdin/stdout, checking response
sizes before forwarding. If a response exceeds the limit, it returns a graceful
JSON-RPC error instead of the oversized response.

Key features:
- Tracks request IDs from stdin for proper error correlation
- Drains oversized partial messages to resync stream
- Thread-safe request tracking between stdin/stdout handlers
"""

import sys
import os
import subprocess
import json
import threading
import select
from typing import Optional, Tuple
from dataclasses import dataclass, field

MAX_RESPONSE_SIZE = 900_000  # 900KB, below SDK's 1MB limit
BUFFER_SIZE = 65536  # Read in 64KB chunks


@dataclass
class RequestInfo:
    """Thread-safe container for current request info."""
    id: Optional[int] = None
    method: Optional[str] = None
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def update(self, request_id: Optional[int], method: Optional[str]):
        with self._lock:
            self.id = request_id
            self.method = method

    def get(self) -> Tuple[Optional[int], Optional[str]]:
        with self._lock:
            return self.id, self.method


def create_error_response(request_id: Optional[int], method: Optional[str], message: str, size: int) -> bytes:
    """Create a JSON-RPC error response with proper request correlation."""
    response = {
        "jsonrpc": "2.0",
        "id": request_id,  # Correlate with the request that caused this
        "error": {
            "code": -32000,
            "message": message,
            "data": {
                "size_bytes": size,
                "limit_bytes": MAX_RESPONSE_SIZE,
                "method": method,
                "suggestion": "Use browser_take_screenshot instead of browser_snapshot for complex pages."
            }
        }
    }
    return json.dumps(response).encode() + b'\n'


def parse_request(data: bytes) -> Tuple[Optional[int], Optional[str]]:
    """Extract request ID and method from JSON-RPC request."""
    try:
        obj = json.loads(data.decode())
        return obj.get("id"), obj.get("method")
    except Exception:
        return None, None


def proxy_stdin(proc: subprocess.Popen, request_info: RequestInfo):
    """Forward stdin to MCP process, tracking request IDs for error correlation."""
    stdin_buffer = b''

    try:
        while True:
            # Use select for non-blocking read on stdin
            if select.select([sys.stdin.buffer], [], [], 0.1)[0]:
                data = sys.stdin.buffer.read1(BUFFER_SIZE)
                if not data:
                    break

                stdin_buffer += data

                # Parse complete JSON-RPC requests (newline-delimited)
                while b'\n' in stdin_buffer:
                    line, stdin_buffer = stdin_buffer.split(b'\n', 1)

                    # Extract and store request info for error responses
                    req_id, method = parse_request(line)
                    if req_id is not None:
                        request_info.update(req_id, method)

                    # Forward to MCP server
                    proc.stdin.write(line + b'\n')
                    proc.stdin.flush()

            # Check if process is still alive
            if proc.poll() is not None:
                break
    except Exception as e:
        print(f"[mcp-size-guard] stdin proxy error: {e}", file=sys.stderr)


def drain_until_newline(proc: subprocess.Popen, response_buffer: bytes) -> bytes:
    """Drain oversized response until newline to resync stream.

    When we detect an oversized partial message, the MCP server is still
    outputting the rest of that line. We must discard until we hit the
    newline to re-align with JSON-RPC message boundaries.

    Without this, the next read would get the MIDDLE of the oversized JSON,
    causing parse errors and stream desynchronization.

    Returns:
        The remainder of the buffer after the newline (start of next message)
    """
    drain_size = len(response_buffer)

    while b'\n' not in response_buffer:
        try:
            if select.select([proc.stdout], [], [], 1.0)[0]:
                chunk = proc.stdout.read1(BUFFER_SIZE) if hasattr(proc.stdout, 'read1') else proc.stdout.read(BUFFER_SIZE)
                if not chunk:
                    print(f"[mcp-size-guard] EOF while draining (discarded {drain_size:,} bytes)", file=sys.stderr)
                    return b''  # EOF
                response_buffer += chunk
                drain_size += len(chunk)
            else:
                # Timeout waiting for newline - process may have died
                print(f"[mcp-size-guard] Timeout while draining (discarded {drain_size:,} bytes)", file=sys.stderr)
                return b''
        except Exception as e:
            print(f"[mcp-size-guard] Error while draining: {e}", file=sys.stderr)
            return b''

    # Discard everything up to and including the newline
    _, remainder = response_buffer.split(b'\n', 1)
    print(f"[mcp-size-guard] Drained oversized message ({drain_size:,} bytes total)", file=sys.stderr)
    return remainder


def main():
    if len(sys.argv) < 2:
        print("Usage: mcp-size-guard <command> [args...]", file=sys.stderr)
        print("Example: mcp-size-guard npx @playwright/mcp@latest", file=sys.stderr)
        sys.exit(1)

    # Command to wrap
    command = sys.argv[1:]

    # Start the real MCP server
    try:
        proc = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0
        )
    except Exception as e:
        print(f"[mcp-size-guard] Failed to start MCP server: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"[mcp-size-guard] Started MCP server: {' '.join(command)}", file=sys.stderr)

    # Thread-safe request tracking for error correlation
    request_info = RequestInfo()

    # Start stdin forwarding thread (parses requests for ID tracking)
    stdin_thread = threading.Thread(target=proxy_stdin, args=(proc, request_info), daemon=True)
    stdin_thread.start()

    response_buffer = b''

    try:
        while True:
            # Check if process ended
            if proc.poll() is not None:
                break

            # Read from MCP stdout
            if select.select([proc.stdout], [], [], 0.1)[0]:
                chunk = proc.stdout.read1(BUFFER_SIZE) if hasattr(proc.stdout, 'read1') else proc.stdout.read(BUFFER_SIZE)
                if not chunk:
                    break

                response_buffer += chunk

                # Process complete JSON-RPC messages (newline-delimited)
                while b'\n' in response_buffer:
                    line, response_buffer = response_buffer.split(b'\n', 1)

                    if len(line) > MAX_RESPONSE_SIZE:
                        # Response too large - send error instead
                        req_id, method = request_info.get()
                        error_response = create_error_response(
                            req_id,
                            method,
                            f"MCP response too large ({len(line):,} bytes > {MAX_RESPONSE_SIZE:,} limit). "
                            f"The page is too complex for this operation.",
                            len(line)
                        )
                        sys.stdout.buffer.write(error_response)
                        sys.stdout.buffer.flush()

                        print(f"[mcp-size-guard] Blocked oversized response: {len(line):,} bytes "
                              f"(id={req_id}, method={method})", file=sys.stderr)
                    else:
                        # Forward normal response
                        sys.stdout.buffer.write(line + b'\n')
                        sys.stdout.buffer.flush()

                # Check if buffer is getting too large (incomplete oversized message)
                if len(response_buffer) > MAX_RESPONSE_SIZE:
                    req_id, method = request_info.get()
                    error_response = create_error_response(
                        req_id,
                        method,
                        f"MCP response too large (>{MAX_RESPONSE_SIZE:,} bytes). "
                        f"The page is too complex for this operation.",
                        len(response_buffer)
                    )
                    sys.stdout.buffer.write(error_response)
                    sys.stdout.buffer.flush()

                    print(f"[mcp-size-guard] Blocked oversized partial response: {len(response_buffer):,} bytes "
                          f"(id={req_id}, method={method})", file=sys.stderr)

                    # CRITICAL: Drain until newline to resync with message boundaries
                    # Otherwise the next read gets the middle of this oversized line
                    response_buffer = drain_until_newline(proc, response_buffer)

    except KeyboardInterrupt:
        print("[mcp-size-guard] Interrupted", file=sys.stderr)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        print("[mcp-size-guard] MCP server terminated", file=sys.stderr)


if __name__ == "__main__":
    main()
```

**Installation**:
```toml
# pyproject.toml entry point
[project.scripts]
mcp-size-guard = "orchestrator_auto.scripts.mcp_size_guard:main"
```

---

### Milestone 6: Config Injection

**Goal**: Automatically wrap Playwright MCP with size guard.

**File**: `orchestrator_auto/config.py`

**Key design decisions**:
1. Default `type` to `"stdio"` if not specified (most configs omit it)
2. Use boolean flag for module execution, not string inspection
3. Build command/args separately, never as a combined string

**Deliverables**:

```python
# config.py

import shutil
import sys
from pathlib import Path
from typing import Dict, Any, Optional, List
import copy


def inject_mcp_size_guard(
    mcp_servers: Optional[Dict[str, Any]],
    guard_patterns: Optional[List[str]] = None
) -> Optional[Dict[str, Any]]:
    """
    Wrap MCP servers with size guard for crash prevention.

    Args:
        mcp_servers: MCP server configuration dict
        guard_patterns: Server name patterns to wrap (default: ["playwright"])

    Returns:
        Modified MCP config with size guard wrapper

    Notes:
        - Defaults type to "stdio" if not specified (common in .mcp.json)
        - Only wraps stdio-type servers (not SSE or other transports)
    """
    if not mcp_servers:
        return mcp_servers

    guard_patterns = guard_patterns or ["playwright"]

    # Check if wrapper is installed as a script
    wrapper_path = shutil.which("mcp-size-guard")
    use_module_execution = wrapper_path is None

    modified = copy.deepcopy(mcp_servers)

    for name, config in modified.items():
        # Check if this server should be wrapped
        should_wrap = any(p.lower() in name.lower() for p in guard_patterns)
        if not should_wrap:
            continue

        # Default type to stdio if not specified (most .mcp.json configs omit it)
        config_type = config.get("type", "stdio")
        if config_type != "stdio":
            continue  # Only wrap stdio servers

        original_command = config.get("command", "")
        original_args = config.get("args", [])

        if not original_command:
            continue  # No command to wrap

        # Wrap with size guard
        if use_module_execution:
            # Use Python module execution
            config["command"] = sys.executable
            config["args"] = [
                "-m", "orchestrator_auto.scripts.mcp_size_guard",
                original_command
            ] + original_args
        else:
            # Use installed script
            config["command"] = wrapper_path
            config["args"] = [original_command] + original_args

        # Mark as wrapped (for debugging/logging)
        config["_size_guard"] = True
        config["_original_command"] = original_command

    return modified
```

**Integration in engine.py**:
```python
# In _apply_mcp_config or agent creation

def _apply_mcp_config(self):
    if self._mcp_config:
        # Apply headless mode if requested
        if self._headless:
            self._mcp_config = inject_headless_mode(self._mcp_config)

        # Apply size guard wrapper
        self._mcp_config = inject_mcp_size_guard(self._mcp_config)
```

**CLI flag** (optional):
```python
@click.option('--no-mcp-guard', is_flag=True, help='Disable MCP response size guard')
```

---

### Milestone 7: Testing & Validation

**Goal**: Verify wrapper works correctly.

**Tests**:

```python
# tests/test_mcp_size_guard.py

import pytest
import subprocess
import json
from unittest.mock import Mock, patch, MagicMock
from dataclasses import dataclass

class TestRequestInfo:
    """Test thread-safe request tracking."""

    def test_request_info_thread_safe(self):
        from orchestrator_auto.scripts.mcp_size_guard import RequestInfo

        info = RequestInfo()
        info.update(123, "browser_snapshot")

        req_id, method = info.get()
        assert req_id == 123
        assert method == "browser_snapshot"

    def test_request_info_updates(self):
        from orchestrator_auto.scripts.mcp_size_guard import RequestInfo

        info = RequestInfo()
        info.update(1, "method_a")
        info.update(2, "method_b")

        req_id, method = info.get()
        assert req_id == 2
        assert method == "method_b"


class TestErrorResponse:
    """Test error response generation."""

    def test_error_response_format(self):
        from orchestrator_auto.scripts.mcp_size_guard import create_error_response

        error = create_error_response(123, "browser_snapshot", "Test error", 2000000)
        parsed = json.loads(error.decode())

        assert parsed["jsonrpc"] == "2.0"
        assert parsed["id"] == 123
        assert "error" in parsed
        assert parsed["error"]["code"] == -32000
        assert parsed["error"]["data"]["method"] == "browser_snapshot"
        assert parsed["error"]["data"]["size_bytes"] == 2000000

    def test_error_response_with_none_id(self):
        from orchestrator_auto.scripts.mcp_size_guard import create_error_response

        error = create_error_response(None, None, "Test error", 1000000)
        parsed = json.loads(error.decode())

        assert parsed["id"] is None  # Should handle None gracefully


class TestParseRequest:
    """Test request parsing."""

    def test_parse_valid_request(self):
        from orchestrator_auto.scripts.mcp_size_guard import parse_request

        data = b'{"jsonrpc": "2.0", "id": 42, "method": "browser_snapshot"}'
        req_id, method = parse_request(data)

        assert req_id == 42
        assert method == "browser_snapshot"

    def test_parse_invalid_json(self):
        from orchestrator_auto.scripts.mcp_size_guard import parse_request

        data = b'not valid json'
        req_id, method = parse_request(data)

        assert req_id is None
        assert method is None


class TestConfigInjection:
    """Test MCP config modification."""

    def test_inject_wraps_playwright(self):
        from orchestrator_auto.config import inject_mcp_size_guard

        config = {
            "playwright": {
                "command": "npx",
                "args": ["@playwright/mcp@latest"]
            }
        }

        with patch('shutil.which', return_value=None):  # Force module execution
            result = inject_mcp_size_guard(config)

        assert result["playwright"]["_size_guard"] is True
        assert result["playwright"]["_original_command"] == "npx"
        assert "mcp_size_guard" in str(result["playwright"]["args"])

    def test_inject_handles_missing_type(self):
        """Config without type field should default to stdio and be wrapped."""
        from orchestrator_auto.config import inject_mcp_size_guard

        config = {
            "playwright": {
                "command": "npx",
                "args": ["@playwright/mcp@latest"]
                # Note: no "type" field
            }
        }

        with patch('shutil.which', return_value=None):
            result = inject_mcp_size_guard(config)

        assert result["playwright"]["_size_guard"] is True

    def test_inject_skips_non_stdio(self):
        """SSE and other transport types should not be wrapped."""
        from orchestrator_auto.config import inject_mcp_size_guard

        config = {
            "playwright": {
                "type": "sse",
                "url": "http://localhost:3000"
            }
        }

        result = inject_mcp_size_guard(config)

        assert "_size_guard" not in result["playwright"]

    def test_inject_skips_non_playwright(self):
        from orchestrator_auto.config import inject_mcp_size_guard

        config = {
            "other-mcp": {
                "type": "stdio",
                "command": "other-command",
                "args": []
            }
        }

        result = inject_mcp_size_guard(config)

        assert "_size_guard" not in result["other-mcp"]

    def test_inject_uses_installed_script(self):
        """When mcp-size-guard is installed, use it directly."""
        from orchestrator_auto.config import inject_mcp_size_guard

        config = {
            "playwright": {
                "command": "npx",
                "args": ["@playwright/mcp@latest"]
            }
        }

        with patch('shutil.which', return_value="/usr/local/bin/mcp-size-guard"):
            result = inject_mcp_size_guard(config)

        assert result["playwright"]["command"] == "/usr/local/bin/mcp-size-guard"
        assert result["playwright"]["args"][0] == "npx"
```

**Manual testing**:
```bash
# 1. Test wrapper directly
echo '{"jsonrpc":"2.0","id":1,"method":"test"}' | python -m orchestrator_auto.scripts.mcp_size_guard npx @playwright/mcp@latest

# 2. Test with orchestrator
orchestrator start -f "Test Playwright" --mcp-config .mcp.json

# 3. Deliberately trigger large response
# Navigate to complex dashboard, call browser_snapshot
# Should get graceful error instead of crash
```

---

## Implementation Checklist

### Phase 1 (v0.11.3) - ~2 hours

- [ ] **Milestone 1**: Executor prompt safety rules
  - [ ] Add `MCP_PLAYWRIGHT_SAFETY` to `prompts.py`
  - [ ] Update `EXECUTOR_SYSTEM_PROMPT`
  - [ ] Add unit test

- [ ] **Milestone 2**: CLI cleanup command
  - [ ] Add `cleanup` command to `cli.py`
  - [ ] Implement conservative default patterns
  - [ ] Add `--dry-run`, `--force`, `--all`, `--pattern` options
  - [ ] Add warnings about over-broad matching
  - [ ] Add unit tests

- [ ] **Milestone 3**: Health check enhancement
  - [ ] Add `_detect_mcp_processes()` helper
  - [ ] Integrate into `check` command (warning only, not failure)
  - [ ] Add unit tests

- [ ] **Milestone 4**: Documentation
  - [ ] Update README troubleshooting section with warnings
  - [ ] Update changelog

### Phase 2 (v0.12.0) - ~6-8 hours

- [ ] **Milestone 5**: MCP wrapper script
  - [ ] Create `orchestrator_auto/scripts/mcp_size_guard.py`
  - [ ] Implement stdin parsing for request ID tracking (thread-safe)
  - [ ] Implement response size checking
  - [ ] Implement drain/resync for oversized partial messages
  - [ ] Add entry point to pyproject.toml
  - [ ] Test standalone execution

- [ ] **Milestone 6**: Config injection
  - [ ] Add `inject_mcp_size_guard()` to `config.py`
  - [ ] Default `type` to `"stdio"` when missing
  - [ ] Use boolean flag for module execution (not string inspection)
  - [ ] Integrate into engine.py
  - [ ] Add `--no-mcp-guard` CLI flag (optional)
  - [ ] Test with real Playwright MCP

- [ ] **Milestone 7**: Testing & validation
  - [ ] Unit tests for RequestInfo thread safety
  - [ ] Unit tests for error response with request ID
  - [ ] Unit tests for config injection (including missing type)
  - [ ] Manual end-to-end testing
  - [ ] Documentation

---

## Future Improvements (Not in This Plan)

### Session-Scoped Cleanup

Current cleanup uses broad pattern matching. Future improvement:

1. **Env var marker**: Inject `ORCH_SESSION_ID=<id>` into MCP server env
2. **PID tracking**: Record spawned PIDs in `~/.claude_orchestrator/pids/<session_id>`
3. **Targeted cleanup**: Only kill processes with matching session ID

### Upstream Fixes

- File issue with Claude Agent SDK for configurable buffer size
- File issue with Playwright MCP for chunked/limited snapshot responses

---

## Success Metrics

| Metric | Phase 1 Target | Phase 2 Target |
|--------|----------------|----------------|
| Buffer overflow crashes | Reduced ~50% (prompt guidance) | Eliminated (hard guard) |
| Orphaned process cleanup | Manual recovery available | Automatic on completion |
| False positive kills | Minimized via conservative defaults | N/A |
| User awareness | High (check + warnings) | N/A |

---

## Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| LLM ignores prompt safety rules | Medium | Medium | Phase 2 provides hard guard |
| Cleanup kills unrelated processes | Medium | High | Conservative defaults, --dry-run, warnings |
| Wrapper adds latency | Low | Low | Only wraps known-problematic tools |
| SDK changes break wrapper | Low | High | Version-pin SDK, monitor releases |
| Wrapper has bugs | Medium | Medium | Extensive testing, fallback to no-guard mode |
| Stream desync after oversized msg | Medium | High | Drain until newline before resuming |

---

## References

- Proposal: `docs/proposals/PROPOSAL_mcp_crash_cleanup.md`
- Session example: `75561c07`
- Claude Agent SDK: https://github.com/anthropics/claude-agent-sdk
- MCP Specification: https://modelcontextprotocol.io/
