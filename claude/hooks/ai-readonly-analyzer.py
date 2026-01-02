#!/usr/bin/env python3
import json
import sys
import os

def analyze_command(command):
    """Use Claude API to analyze if command is read-only"""

    try:
        from anthropic import Anthropic
    except ImportError:
        print("⚠️  anthropic package not installed. Run: pip install anthropic", file=sys.stderr)
        return {"isReadOnly": False, "confidence": 0, "reason": "anthropic package not installed"}

    api_key = os.getenv('ANTHROPIC_API_KEY')
    if not api_key:
        print("⚠️  ANTHROPIC_API_KEY not set", file=sys.stderr)
        return {"isReadOnly": False, "confidence": 0, "reason": "No API key"}

    client = Anthropic(api_key=api_key)

    prompt = f"""Analyze this bash command and determine if it's read-only (no modifications to filesystem, system, processes, databases, or remote resources).

Command: {command}

Consider these frameworks and their patterns:

**Python/Django:**
- Read-only: pytest, mypy, show_urls, showmigrations, check, coverage report
- NOT read-only: migrate, makemigrations, pip install, black (without --check)

**Node.js/React/Next.js:**
- Read-only: npm test, jest, eslint, next lint, npm outdated
- NOT read-only: npm install, next build, prettier --write

**Ruby/Rails:**
- Read-only: rspec, rails routes, rubocop, rails db:migrate:status
- NOT read-only: rails db:migrate, gem install, rails generate

**PHP/Laravel:**
- Read-only: phpunit, phpcs, php artisan route:list, php artisan test
- NOT read-only: php artisan migrate, composer install

**Go/Rust:**
- Read-only: go test, cargo check, cargo test, go vet
- NOT read-only: go install, cargo build, cargo publish

**General:**
- Commands with pipes (|), grep, head, tail are usually safe if the base command is safe
- "python -c" with only print/imports is safe, but with open/os/subprocess is dangerous

Respond ONLY with valid JSON (no markdown, no code fences):
{{
  "isReadOnly": boolean,
  "isDangerous": boolean,
  "confidence": 0.0-1.0,
  "reason": "brief explanation"
}}"""

    try:
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=300,
            temperature=0,
            messages=[{"role": "user", "content": prompt}]
        )

        text = message.content[0].text.strip()
        # Remove markdown code fences if present
        text = text.replace('```json', '').replace('```', '').strip()

        result = json.loads(text)
        return result
    except json.JSONDecodeError as e:
        print(f"⚠️  Failed to parse AI response: {e}", file=sys.stderr)
        print(f"Response was: {text[:200]}", file=sys.stderr)
        return {"isReadOnly": False, "confidence": 0, "reason": "JSON parse error"}
    except Exception as e:
        print(f"⚠️  AI analysis error: {e}", file=sys.stderr)
        return {"isReadOnly": False, "confidence": 0, "reason": str(e)}

def main():
    try:
        input_data = json.load(sys.stdin)
    except json.JSONDecodeError:
        print("⚠️  Invalid JSON input", file=sys.stderr)
        sys.exit(0)

    command = input_data.get('tool_input', {}).get('command', '')

    if not command:
        sys.exit(0)

    analysis = analyze_command(command)

    # Lower threshold to 0.80 to catch more edge cases
    if analysis['isReadOnly'] and analysis['confidence'] > 0.80:
        print(f"🤖 AI Auto-approved: {command}", file=sys.stderr)
        print(f"   Reason: {analysis['reason']}", file=sys.stderr)
        print(f"   Confidence: {analysis['confidence']:.0%}", file=sys.stderr)

        output = {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "allow",
                "permissionDecisionReason": f"AI: {analysis['reason']}"
            }
        }
        print(json.dumps(output))
        sys.exit(0)

    elif analysis['isDangerous'] and analysis['confidence'] > 0.85:
        print(f"🚫 AI Blocked: {command}", file=sys.stderr)
        print(f"   Reason: {analysis['reason']}", file=sys.stderr)
        sys.exit(2)  # Exit code 2 blocks the command

    # Default: ask user (uncertain)
    print(f"❓ AI uncertain (confidence: {analysis['confidence']:.0%}), asking user", file=sys.stderr)
    sys.exit(0)

if __name__ == '__main__':
    main()
