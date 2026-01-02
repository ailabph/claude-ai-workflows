#!/usr/bin/env python3
"""
Manual test script to verify send_ping() and wait_for_pong() methods.
This doesn't actually send messages, just checks the methods exist and have correct signatures.
"""

import sys
import inspect
from orchestrator_auto.telegram import TelegramNotifier, TelegramListener

def test_send_ping_exists():
    """Check that send_ping method exists on TelegramNotifier."""
    assert hasattr(TelegramNotifier, 'send_ping'), "send_ping method not found on TelegramNotifier"

    # Check signature
    sig = inspect.signature(TelegramNotifier.send_ping)
    params = list(sig.parameters.keys())
    assert params == ['self'], f"Expected ['self'], got {params}"

    # Check return annotation
    assert sig.return_annotation is not None, "send_ping should have return type annotation"
    print("✓ TelegramNotifier.send_ping() exists with correct signature")


def test_wait_for_pong_exists():
    """Check that wait_for_pong method exists on TelegramListener."""
    assert hasattr(TelegramListener, 'wait_for_pong'), "wait_for_pong method not found on TelegramListener"

    # Check signature
    sig = inspect.signature(TelegramListener.wait_for_pong)
    params = list(sig.parameters.keys())
    assert 'ping_message_id' in params, "wait_for_pong should have ping_message_id parameter"
    assert 'timeout' in params, "wait_for_pong should have timeout parameter"

    # Check defaults
    assert sig.parameters['timeout'].default == 60, "timeout should default to 60"

    print("✓ TelegramListener.wait_for_pong() exists with correct signature")


def test_docstrings():
    """Check that methods have docstrings."""
    assert TelegramNotifier.send_ping.__doc__ is not None, "send_ping should have docstring"
    assert TelegramListener.wait_for_pong.__doc__ is not None, "wait_for_pong should have docstring"
    print("✓ Both methods have docstrings")


if __name__ == '__main__':
    try:
        test_send_ping_exists()
        test_wait_for_pong_exists()
        test_docstrings()
        print("\n✅ All manual tests passed!")
        sys.exit(0)
    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)
