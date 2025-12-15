# Feature: Activity Indicator with Streaming Snippets

## Status: IMPLEMENTED

## Overview

Add real-time feedback during agent processing to show the user that work is happening. Since the Claude SDK already streams responses, we can display message snippets at intervals.

## Current Behavior

- SDK streams via async generator: `async for message in query(...)`
- Current implementation accumulates all text before returning
- User sees no output until agent fully completes (can be minutes)

## Proposed Behavior

Show throttled snippets every 1-2 seconds:
```
⏳ [42 tokens] ...implementing the authentication module...
⏳ [89 tokens] ...def validate_user(username, password):...
⏳ [156 tokens] ...### Files Created/Modified:...
```

## Implementation Plan

### 1. Add streaming callback to BaseAgent

**File:** `orchestrator_auto/agents.py`

```python
async def send_message_async(
    self,
    content: str,
    on_chunk: Optional[Callable[[str], None]] = None
) -> str:
    """
    Send a message with optional streaming callback.

    Args:
        content: Message content
        on_chunk: Optional callback for each text chunk
    """
    options = self._get_options()
    response_text = ""

    async for message in query(prompt=content, options=options):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    response_text += block.text
                    if on_chunk:
                        on_chunk(block.text)
        elif isinstance(message, ResultMessage):
            pass

    return response_text
```

### 2. Create throttled output handler

**File:** `orchestrator_auto/output.py` (new file)

```python
import time
from typing import Optional

class StreamingIndicator:
    """Throttled streaming output for activity indication."""

    def __init__(
        self,
        interval: float = 1.0,
        snippet_length: int = 50,
        show_tokens: bool = True
    ):
        self.interval = interval
        self.snippet_length = snippet_length
        self.show_tokens = show_tokens
        self.last_output_time = 0
        self.buffer = ""
        self.token_count = 0

    def on_chunk(self, text: str) -> None:
        """Handle incoming text chunk."""
        self.buffer += text
        self.token_count += len(text.split())

        now = time.time()
        if now - self.last_output_time >= self.interval:
            self._display_snippet()
            self.last_output_time = now

    def _display_snippet(self) -> None:
        """Display current snippet."""
        snippet = self.buffer[-self.snippet_length:]
        snippet = snippet.replace('\n', ' ').strip()

        if self.show_tokens:
            print(f"\r⏳ [{self.token_count} tokens] ...{snippet}", end="", flush=True)
        else:
            print(f"\r⏳ ...{snippet}", end="", flush=True)

    def finish(self) -> None:
        """Clear the indicator line."""
        print("\r" + " " * 80 + "\r", end="", flush=True)
```

### 3. Integrate with engine

**File:** `orchestrator_auto/engine.py`

```python
from .output import StreamingIndicator

def _route_to_planner(self, report: str) -> str:
    indicator = StreamingIndicator(interval=1.5)

    response = self.planner.send_message(
        prompt,
        on_chunk=indicator.on_chunk
    )

    indicator.finish()
    return response
```

### 4. Add CLI flag (optional)

**File:** `orchestrator_auto/cli.py`

```python
@click.option(
    '--show-activity/--no-activity',
    default=True,
    help='Show streaming activity indicator'
)
```

## Complexity Estimate

- agents.py changes: ~15 min
- output.py new file: ~30 min
- engine.py integration: ~30 min
- Testing: ~30 min
- **Total: ~2 hours**

## Alternatives Considered

1. **Simple spinner** - Less informative, doesn't show real progress
2. **Full streaming output** - Too noisy, floods terminal
3. **Progress bar** - Hard to estimate completion percentage

## Dependencies

- None (uses existing SDK streaming)

## Testing Notes

- Test with slow responses (use lower-tier models)
- Test terminal width handling
- Test with long Unicode content
- Verify cleanup on interruption (Ctrl+C)
