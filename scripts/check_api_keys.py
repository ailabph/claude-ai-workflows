#!/usr/bin/env python3
"""Check API key validity for planner-auto (Claude + OpenAI).

Usage:
  python scripts/check_api_keys.py
"""

import getpass
import sys
import time


def check_anthropic(api_key: str) -> bool:
    """Test Anthropic API key with a minimal call."""
    try:
        import anthropic
    except ImportError:
        print("  anthropic package not installed. Run: pip install anthropic")
        return False

    try:
        client = anthropic.Anthropic(api_key=api_key)
        start = time.time()
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=10,
            messages=[{"role": "user", "content": "Say OK"}],
        )
        elapsed = time.time() - start
        text = response.content[0].text if response.content else ""
        tokens = response.usage.input_tokens + response.usage.output_tokens
        print(f"  Valid. Response: \"{text}\" ({elapsed:.1f}s, {tokens} tokens)")
        return True
    except anthropic.AuthenticationError:
        print("  INVALID — authentication failed. Check your key.")
        return False
    except anthropic.RateLimitError:
        print("  Key is valid but RATE LIMITED. Try again in a minute.")
        return True  # key is valid, just throttled
    except Exception as e:
        print(f"  ERROR: {type(e).__name__}: {e}")
        return False


def check_openai(api_key: str) -> bool:
    """Test OpenAI API key with a minimal call."""
    try:
        from openai import OpenAI
    except ImportError:
        print("  openai package not installed. Run: pip install openai")
        return False

    try:
        client = OpenAI(api_key=api_key)
        start = time.time()
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=10,
            messages=[{"role": "user", "content": "Say OK"}],
        )
        elapsed = time.time() - start
        text = response.choices[0].message.content or ""
        tokens = response.usage.total_tokens if response.usage else 0
        print(f"  Valid. Response: \"{text}\" ({elapsed:.1f}s, {tokens} tokens)")
        return True
    except Exception as e:
        name = type(e).__name__
        if "AuthenticationError" in name or "401" in str(e):
            print("  INVALID — authentication failed. Check your key.")
            return False
        elif "RateLimitError" in name or "429" in str(e):
            print("  Key is valid but RATE LIMITED. Try again in a minute.")
            return True
        else:
            print(f"  ERROR: {name}: {e}")
            return False


def main():
    print("=== planner-auto API Key Checker ===\n")

    # Anthropic
    print("Anthropic API Key (for Claude planner):")
    anthropic_key = getpass.getpass("  Paste key (hidden): ").strip()
    if not anthropic_key:
        print("  Skipped.\n")
        anthropic_ok = False
    else:
        print(f"  Key format: {anthropic_key[:10]}...{anthropic_key[-4:]} ({len(anthropic_key)} chars)")
        anthropic_ok = check_anthropic(anthropic_key)
    print()

    # OpenAI
    print("OpenAI API Key (for GPT reviewer):")
    openai_key = getpass.getpass("  Paste key (hidden): ").strip()
    if not openai_key:
        print("  Skipped.\n")
        openai_ok = False
    else:
        print(f"  Key format: {openai_key[:10]}...{openai_key[-4:]} ({len(openai_key)} chars)")
        openai_ok = check_openai(openai_key)
    print()

    # Summary
    print("=== Summary ===")
    print(f"  Anthropic: {'PASS' if anthropic_ok else 'FAIL'}")
    print(f"  OpenAI:    {'PASS' if openai_ok else 'FAIL'}")

    if anthropic_ok and openai_ok:
        print("\n  Both keys valid. planner-auto is ready to use.")
        print("  Make sure these are set in your environment:")
        print("    export ANTHROPIC_API_KEY=\"...\"")
        print("    export OPENAI_API_KEY=\"...\"")
    elif anthropic_ok:
        print("\n  Claude works. OpenAI key needed for the review command.")
    elif openai_ok:
        print("\n  OpenAI works. Anthropic key needed for discuss/generate commands.")
    else:
        print("\n  Neither key is working. Check your keys and try again.")

    sys.exit(0 if (anthropic_ok and openai_ok) else 1)


if __name__ == "__main__":
    main()
