#!/usr/bin/env python3
"""
Visual QA Workflow Setup Script (macOS)

Checks, installs, and configures dependencies for the Visual QA workflow.

Usage:
    python CLAUDE_visual_qa_workflow_setup.py          # Run all checks
    python CLAUDE_visual_qa_workflow_setup.py --check  # Check only, no installs
    python CLAUDE_visual_qa_workflow_setup.py --install # Install missing dependencies
    python CLAUDE_visual_qa_workflow_setup.py --configure # Configure Claude Code MCP
"""

import os
import sys
import json
import shutil
import subprocess
import argparse
from pathlib import Path
from typing import Optional, Tuple

# ANSI colors for terminal output
class Colors:
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BLUE = '\033[94m'
    BOLD = '\033[1m'
    END = '\033[0m'

def print_header(text: str):
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'='*60}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.BLUE}{text}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.BLUE}{'='*60}{Colors.END}\n")

def print_success(text: str):
    print(f"{Colors.GREEN}✓{Colors.END} {text}")

def print_warning(text: str):
    print(f"{Colors.YELLOW}⚠{Colors.END} {text}")

def print_error(text: str):
    print(f"{Colors.RED}✗{Colors.END} {text}")

def print_info(text: str):
    print(f"{Colors.BLUE}ℹ{Colors.END} {text}")

def run_command(cmd: list, capture: bool = True) -> Tuple[int, str, str]:
    """Run a shell command and return exit code, stdout, stderr."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=capture,
            text=True,
            timeout=60
        )
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except FileNotFoundError:
        return 1, "", f"Command not found: {cmd[0]}"
    except subprocess.TimeoutExpired:
        return 1, "", "Command timed out"
    except Exception as e:
        return 1, "", str(e)

def check_command_exists(cmd: str) -> bool:
    """Check if a command exists in PATH."""
    return shutil.which(cmd) is not None

def get_version(cmd: list) -> Optional[str]:
    """Get version string from a command."""
    code, stdout, _ = run_command(cmd)
    if code == 0:
        return stdout.split('\n')[0]
    return None

# =============================================================================
# Dependency Checks
# =============================================================================

def check_node() -> Tuple[bool, str]:
    """Check if Node.js is installed."""
    if not check_command_exists('node'):
        return False, "Node.js not found"

    version = get_version(['node', '--version'])
    if version:
        # Check minimum version (v16+)
        try:
            major = int(version.lstrip('v').split('.')[0])
            if major >= 16:
                return True, f"Node.js {version}"
            else:
                return False, f"Node.js {version} (need v16+)"
        except:
            return True, f"Node.js {version}"
    return False, "Could not determine Node.js version"

def check_npm() -> Tuple[bool, str]:
    """Check if npm is installed."""
    if not check_command_exists('npm'):
        return False, "npm not found"

    version = get_version(['npm', '--version'])
    if version:
        return True, f"npm {version}"
    return False, "Could not determine npm version"

def check_npx() -> Tuple[bool, str]:
    """Check if npx is available."""
    if not check_command_exists('npx'):
        return False, "npx not found"
    return True, "npx available"

def check_playwright_mcp() -> Tuple[bool, str]:
    """Check if Playwright MCP server is installed."""
    # Check if globally installed
    code, stdout, _ = run_command(['npm', 'list', '-g', '@anthropic/mcp-server-playwright'])
    if code == 0 and '@anthropic/mcp-server-playwright' in stdout:
        return True, "Playwright MCP installed globally"

    # Check if it can be run via npx (will download if needed)
    code, _, _ = run_command(['npx', '--yes', '@anthropic/mcp-server-playwright', '--version'])
    if code == 0:
        return True, "Playwright MCP available via npx"

    return False, "Playwright MCP not installed"

def check_playwright_browsers() -> Tuple[bool, str]:
    """Check if Playwright browsers are installed."""
    code, stdout, stderr = run_command(['npx', 'playwright', 'install', '--dry-run'])

    # Check if chromium is available
    playwright_cache = Path.home() / 'Library' / 'Caches' / 'ms-playwright'
    if playwright_cache.exists():
        chromium_dirs = list(playwright_cache.glob('chromium-*'))
        if chromium_dirs:
            return True, f"Playwright browsers found in {playwright_cache}"

    return False, "Playwright browsers not installed"

def check_claude_code() -> Tuple[bool, str]:
    """Check if Claude Code CLI is available."""
    if check_command_exists('claude'):
        version = get_version(['claude', '--version'])
        if version:
            return True, f"Claude Code {version}"
        return True, "Claude Code installed"
    return False, "Claude Code CLI not found"

# =============================================================================
# Configuration Checks
# =============================================================================

def get_mcp_config_path() -> Path:
    """Get the MCP config file path."""
    # Check project-level first
    project_config = Path.cwd() / '.mcp.json'
    if project_config.exists():
        return project_config

    # Then user-level
    home_config = Path.home() / '.claude.json'
    return home_config

def check_mcp_config() -> Tuple[bool, str, Optional[dict]]:
    """Check if MCP config exists and has playwright configured."""
    config_path = get_mcp_config_path()

    if not config_path.exists():
        return False, f"MCP config not found at {config_path}", None

    try:
        with open(config_path) as f:
            config = json.load(f)

        mcp_servers = config.get('mcpServers', {})
        if 'playwright' in mcp_servers:
            return True, f"Playwright MCP configured in {config_path}", config
        else:
            return False, f"Playwright not in MCP config ({config_path})", config
    except json.JSONDecodeError:
        return False, f"Invalid JSON in {config_path}", None
    except Exception as e:
        return False, f"Error reading config: {e}", None

def check_permissions_config() -> Tuple[bool, str]:
    """Check if Claude Code permissions are configured."""
    settings_path = Path.cwd() / '.claude' / 'settings.json'

    if not settings_path.exists():
        return False, "Permissions not configured (.claude/settings.json)"

    try:
        with open(settings_path) as f:
            settings = json.load(f)

        permissions = settings.get('permissions', {})
        allow = permissions.get('allow', [])

        # Check for MCP permissions
        has_mcp_perms = any('mcp__playwright' in p or 'mcp__' in p for p in allow)

        if has_mcp_perms:
            return True, "MCP permissions configured"
        else:
            return False, "MCP permissions not in allow list"
    except:
        return False, "Error reading permissions config"

# =============================================================================
# Installation Functions
# =============================================================================

def install_homebrew() -> bool:
    """Install Homebrew if not present."""
    if check_command_exists('brew'):
        print_success("Homebrew already installed")
        return True

    print_info("Installing Homebrew...")
    code, _, _ = run_command([
        '/bin/bash', '-c',
        '$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)'
    ], capture=False)
    return code == 0

def install_node() -> bool:
    """Install Node.js via Homebrew."""
    print_info("Installing Node.js via Homebrew...")
    code, _, _ = run_command(['brew', 'install', 'node'], capture=False)
    return code == 0

def install_playwright_mcp() -> bool:
    """Install Playwright MCP server globally."""
    print_info("Installing Playwright MCP server...")
    code, _, _ = run_command([
        'npm', 'install', '-g', '@anthropic/mcp-server-playwright'
    ], capture=False)
    return code == 0

def install_playwright_browsers() -> bool:
    """Install Playwright browsers."""
    print_info("Installing Playwright browsers (Chromium)...")
    code, _, _ = run_command([
        'npx', 'playwright', 'install', 'chromium'
    ], capture=False)
    return code == 0

# =============================================================================
# Configuration Functions
# =============================================================================

def configure_mcp() -> bool:
    """Configure MCP for Claude Code."""
    config_path = Path.cwd() / '.mcp.json'

    # Default config
    mcp_config = {
        "mcpServers": {
            "playwright": {
                "command": "npx",
                "args": ["@anthropic/mcp-server-playwright"]
            }
        }
    }

    # If config exists, merge with existing
    if config_path.exists():
        try:
            with open(config_path) as f:
                existing = json.load(f)
            existing.setdefault('mcpServers', {})
            existing['mcpServers']['playwright'] = mcp_config['mcpServers']['playwright']
            mcp_config = existing
        except:
            pass

    try:
        with open(config_path, 'w') as f:
            json.dump(mcp_config, f, indent=2)
        print_success(f"Created MCP config at {config_path}")
        return True
    except Exception as e:
        print_error(f"Failed to create MCP config: {e}")
        return False

def configure_permissions() -> bool:
    """Configure Claude Code permissions."""
    settings_dir = Path.cwd() / '.claude'
    settings_path = settings_dir / 'settings.json'

    # Default permissions
    permissions_config = {
        "permissions": {
            "allow": [
                "mcp__playwright__*",
                "Bash(npm run dev)",
                "Bash(npm run build)",
                "Bash(npm run start)",
                "Bash(git status)",
                "Bash(git diff:*)",
                "Bash(git log:*)",
                "Bash(git add:*)",
                "Bash(git commit:*)",
                "Read",
                "Write",
                "Edit",
                "Glob",
                "Grep"
            ],
            "deny": [
                "Bash(rm -rf:*)",
                "Bash(git push:*)",
                "Bash(git reset --hard:*)"
            ]
        }
    }

    # Merge with existing if present
    if settings_path.exists():
        try:
            with open(settings_path) as f:
                existing = json.load(f)
            # Merge allow lists
            existing_allow = existing.get('permissions', {}).get('allow', [])
            new_allow = permissions_config['permissions']['allow']
            merged_allow = list(set(existing_allow + new_allow))
            existing.setdefault('permissions', {})
            existing['permissions']['allow'] = merged_allow
            existing['permissions'].setdefault('deny', permissions_config['permissions']['deny'])
            permissions_config = existing
        except:
            pass

    try:
        settings_dir.mkdir(parents=True, exist_ok=True)
        with open(settings_path, 'w') as f:
            json.dump(permissions_config, f, indent=2)
        print_success(f"Created permissions config at {settings_path}")
        return True
    except Exception as e:
        print_error(f"Failed to create permissions config: {e}")
        return False

# =============================================================================
# Main Functions
# =============================================================================

def run_checks() -> dict:
    """Run all dependency and configuration checks."""
    print_header("Visual QA Workflow - Dependency Check")

    results = {}

    # Core dependencies
    print(f"{Colors.BOLD}Core Dependencies:{Colors.END}")

    ok, msg = check_node()
    results['node'] = ok
    (print_success if ok else print_error)(msg)

    ok, msg = check_npm()
    results['npm'] = ok
    (print_success if ok else print_error)(msg)

    ok, msg = check_npx()
    results['npx'] = ok
    (print_success if ok else print_error)(msg)

    # MCP dependencies
    print(f"\n{Colors.BOLD}MCP Dependencies:{Colors.END}")

    ok, msg = check_playwright_mcp()
    results['playwright_mcp'] = ok
    (print_success if ok else print_warning)(msg)

    ok, msg = check_playwright_browsers()
    results['playwright_browsers'] = ok
    (print_success if ok else print_warning)(msg)

    # Claude Code
    print(f"\n{Colors.BOLD}Claude Code:{Colors.END}")

    ok, msg = check_claude_code()
    results['claude_code'] = ok
    (print_success if ok else print_warning)(msg)

    # Configuration
    print(f"\n{Colors.BOLD}Configuration:{Colors.END}")

    ok, msg, _ = check_mcp_config()
    results['mcp_config'] = ok
    (print_success if ok else print_warning)(msg)

    ok, msg = check_permissions_config()
    results['permissions'] = ok
    (print_success if ok else print_warning)(msg)

    return results

def run_install():
    """Install missing dependencies."""
    print_header("Visual QA Workflow - Install Dependencies")

    # Check and install Node.js
    ok, _ = check_node()
    if not ok:
        if check_command_exists('brew'):
            if install_node():
                print_success("Node.js installed")
            else:
                print_error("Failed to install Node.js")
                return False
        else:
            print_error("Please install Node.js manually: https://nodejs.org/")
            print_info("Or install Homebrew first: /bin/bash -c \"$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\"")
            return False

    # Install Playwright MCP
    ok, _ = check_playwright_mcp()
    if not ok:
        if install_playwright_mcp():
            print_success("Playwright MCP installed")
        else:
            print_error("Failed to install Playwright MCP")
            return False

    # Install Playwright browsers
    ok, _ = check_playwright_browsers()
    if not ok:
        if install_playwright_browsers():
            print_success("Playwright browsers installed")
        else:
            print_warning("Failed to install Playwright browsers (may install on first use)")

    print_success("All dependencies installed!")
    return True

def run_configure():
    """Configure MCP and permissions."""
    print_header("Visual QA Workflow - Configure")

    # Configure MCP
    ok, _, _ = check_mcp_config()
    if not ok:
        configure_mcp()
    else:
        print_success("MCP already configured")

    # Configure permissions
    ok, _ = check_permissions_config()
    if not ok:
        configure_permissions()
    else:
        print_success("Permissions already configured")

    print_success("Configuration complete!")
    return True

def print_summary(results: dict):
    """Print summary and next steps."""
    print_header("Summary")

    all_ok = all(results.values())
    core_ok = results.get('node') and results.get('npm')
    mcp_ok = results.get('playwright_mcp') and results.get('mcp_config')

    if all_ok:
        print_success("All checks passed! Ready to use Visual QA workflow.")
        print(f"\n{Colors.BOLD}Quick Start:{Colors.END}")
        print("  1. Start your dev server: npm run dev")
        print("  2. In Claude Code, run:")
        print(f"     {Colors.BLUE}Read CLAUDE_visual_qa_workflow.md{Colors.END}")
        print("  3. Provide a task with design reference and route")
    else:
        print_warning("Some checks failed. See above for details.")
        print(f"\n{Colors.BOLD}Next Steps:{Colors.END}")

        if not core_ok:
            print("  1. Install Node.js: brew install node")
            print("     Or download from: https://nodejs.org/")

        if not results.get('playwright_mcp'):
            print("  2. Install Playwright MCP:")
            print("     npm install -g @anthropic/mcp-server-playwright")

        if not results.get('mcp_config'):
            print("  3. Configure MCP:")
            print(f"     python {sys.argv[0]} --configure")

        if not results.get('permissions'):
            print("  4. Configure permissions:")
            print(f"     python {sys.argv[0]} --configure")

        print(f"\n{Colors.BOLD}Or run automatic setup:{Colors.END}")
        print(f"  python {sys.argv[0]} --install --configure")

def main():
    parser = argparse.ArgumentParser(
        description="Visual QA Workflow Setup Script",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python CLAUDE_visual_qa_workflow_setup.py              # Check all dependencies
  python CLAUDE_visual_qa_workflow_setup.py --install    # Install missing deps
  python CLAUDE_visual_qa_workflow_setup.py --configure  # Configure MCP & permissions
  python CLAUDE_visual_qa_workflow_setup.py --install --configure  # Full setup
        """
    )

    parser.add_argument(
        '--check',
        action='store_true',
        help='Run checks only (default behavior)'
    )
    parser.add_argument(
        '--install',
        action='store_true',
        help='Install missing dependencies'
    )
    parser.add_argument(
        '--configure',
        action='store_true',
        help='Configure MCP and permissions'
    )

    args = parser.parse_args()

    # Default to check if no args
    if not args.install and not args.configure:
        args.check = True

    # Run install if requested
    if args.install:
        if not run_install():
            sys.exit(1)

    # Run configure if requested
    if args.configure:
        if not run_configure():
            sys.exit(1)

    # Always run checks at the end
    results = run_checks()
    print_summary(results)

    # Exit with error if core deps missing
    if not (results.get('node') and results.get('npm')):
        sys.exit(1)

if __name__ == "__main__":
    main()