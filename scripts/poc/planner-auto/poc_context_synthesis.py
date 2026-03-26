#!/usr/bin/env python3
"""POC 4b: On-Demand Context Synthesis

Validate on-demand context synthesis from DB for plan generation.

Steps:
  1. Create and populate test DB (reuse POC 3a schema):
     - 5-8 context_entries (files with summaries)
     - 10-15 messages (simulated user/planner conversation with
       requirements, decisions, clarification loops, greetings)
  2. Query all context_entries and messages for session
  3. Build synthesis prompt for Claude:
     - "Given this conversation history and loaded files, produce
       a structured context summary covering: files and their purpose,
       key entities, user requirements, decisions made, open questions"
  4. Invoke Claude (headless, cheap model like haiku)
  5. Capture synthesized output
  6. Validate:
     a. Under 2000 tokens
     b. Contains references to loaded files
     c. Captures key decisions from conversation
     d. Omits noise (greetings, repetitive clarifications)
  7. Print: synthesized context, token count, latency

Usage:
  export ANTHROPIC_API_KEY="your-key"
  python scripts/poc/planner-auto/poc_context_synthesis.py
"""

# TODO: implement
