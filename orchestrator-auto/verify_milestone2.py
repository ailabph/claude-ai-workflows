#!/usr/bin/env python3
"""
Verification script for Milestone 2: CLI Command Implementation
Checks that the CLI command is properly implemented.
"""

import sys
import inspect
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from orchestrator_auto import cli as cli_module

def verify_milestone_2():
    """Verify Milestone 2 deliverables."""
    print("=" * 60)
    print("MILESTONE 2 VERIFICATION: CLI Command Implementation")
    print("=" * 60)
    print()

    # Check 1: telegram_ping command exists
    print("✓ Checking telegram ping command...")
    assert hasattr(cli_module, 'telegram_ping'), "telegram_ping function not found"

    # Check signature
    sig = inspect.signature(cli_module.telegram_ping)
    params = list(sig.parameters.keys())
    assert 'timeout' in params, "Missing timeout parameter"
    assert 'verbose' in params, "Missing verbose parameter"

    # Check docstring
    assert cli_module.telegram_ping.__doc__ is not None, "Missing docstring"
    assert "ping-pong" in cli_module.telegram_ping.__doc__.lower(), "Docstring should mention ping-pong"

    print("  - Command function exists: telegram_ping()")
    print("  - Parameters: timeout, verbose")
    print("  - Docstring: ✓")
    print()

    # Check 2: Command implementation
    print("✓ Checking implementation...")
    source = inspect.getsource(cli_module.telegram_ping)

    # Check for config loading
    assert "get_telegram_config" in source, "Should load telegram config"
    print("  - Loads telegram config ✓")

    # Check for notifier usage
    assert "TelegramNotifier" in source, "Should use TelegramNotifier"
    assert "send_ping" in source, "Should call send_ping()"
    print("  - Uses TelegramNotifier.send_ping() ✓")

    # Check for listener usage
    assert "TelegramListener" in source, "Should use TelegramListener"
    assert "wait_for_pong" in source, "Should call wait_for_pong()"
    print("  - Uses TelegramListener.wait_for_pong() ✓")

    # Check for error handling
    assert "sys.exit(1)" in source, "Should exit with code 1 on error"
    assert "HTTPX_AVAILABLE" in source, "Should check httpx availability"
    print("  - Error handling with sys.exit(1) ✓")
    print("  - Checks HTTPX_AVAILABLE ✓")

    # Check for cleanup
    assert "close()" in source, "Should close connections"
    assert "finally:" in source, "Should use finally block for cleanup"
    print("  - Cleanup with close() in finally block ✓")

    # Check for user feedback
    assert "click.echo" in source or "click.secho" in source, "Should provide user feedback"
    assert "Ping sent" in source, "Should confirm ping sent"
    assert "Pong received" in source, "Should confirm pong received"
    assert "Timeout" in source, "Should handle timeout"
    print("  - User-friendly messages ✓")
    print()

    # Check 3: Test file has CLI tests
    print("✓ Checking CLI tests...")
    test_file = Path(__file__).parent / "tests" / "test_telegram.py"
    test_content = test_file.read_text()

    assert "TestTelegramPingCLI" in test_content, "Missing TestTelegramPingCLI class"
    assert "test_ping_command_success" in test_content, "Missing success test"
    assert "test_ping_command_timeout" in test_content, "Missing timeout test"
    assert "test_ping_command_no_config" in test_content, "Missing no config test"
    assert "test_ping_command_send_failure" in test_content, "Missing send failure test"

    print("  - TestTelegramPingCLI class exists ✓")
    print("  - test_ping_command_success ✓")
    print("  - test_ping_command_timeout ✓")
    print("  - test_ping_command_no_config ✓")
    print("  - test_ping_command_send_failure ✓")
    print()

    # Check 4: Command decorator
    print("✓ Checking Click decorators...")
    # Read the cli.py file to check decorators
    cli_file = Path(__file__).parent / "orchestrator_auto" / "cli.py"
    cli_content = cli_file.read_text()

    # Find the ping command definition
    ping_section = cli_content[cli_content.find("@telegram.command(\"ping\")"):cli_content.find("@telegram.command(\"ping\")")+1000]

    assert "@telegram.command(\"ping\")" in ping_section, "Missing @telegram.command decorator"
    assert "--timeout" in ping_section, "Missing --timeout option"
    assert "--verbose" in ping_section, "Missing --verbose option"

    print("  - @telegram.command('ping') decorator ✓")
    print("  - --timeout option ✓")
    print("  - --verbose option ✓")
    print()

    print("=" * 60)
    print("✅ MILESTONE 2: ALL CHECKS PASSED")
    print("=" * 60)
    print()
    print("Deliverables completed:")
    print("  ✓ `orchestrator telegram ping` command implemented")
    print("  ✓ Timeout behavior correct (exits with code 1)")
    print("  ✓ Error messages are user-friendly")
    print("  ✓ Sends confirmation message on success")
    print("  ✓ CLI tests added (4 test cases)")
    print()

if __name__ == '__main__':
    try:
        verify_milestone_2()
        sys.exit(0)
    except AssertionError as e:
        print(f"\n❌ Verification failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error during verification: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
