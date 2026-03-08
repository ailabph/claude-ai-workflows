"""
Tests for the chat-mode TUI app (Milestones 2, 3, 4, and 5).
"""

import pytest

pytest.importorskip("textual")

from unittest.mock import patch, MagicMock

from textual.widgets import Markdown

from orchestrator_auto.tui.chat_app import ChatTUIApp, HelpModal, ConfirmModal
from orchestrator_auto.tui.widgets.chat_input_bar import ChatInputBar
from orchestrator_auto.tui.widgets.chat_message_view import ChatMessageView
from orchestrator_auto.tui.widgets.verbose_panel import VerbosePanel
from orchestrator_auto.tui.messages import (
    ChatChunkReceived,
    ChatResponseComplete,
    ChatNotification,
    ChatToolEvent,
    ChatSendFailed,
)


@pytest.mark.asyncio
async def test_layout_renders():
    """Test that the app layout renders with all expected widgets."""
    app = ChatTUIApp(model="opus", verbose=False, system_prompt=None, tools_enabled=True)
    async with app.run_test() as pilot:
        # Verify core widgets are mounted
        assert app.query_one("#chat-view", ChatMessageView)
        assert app.query_one("#input-bar", ChatInputBar)
        assert app.query_one("#chat-input")
        assert app.query_one("#send-btn")


@pytest.mark.asyncio
async def test_empty_input_does_not_send():
    """Test that empty input does not post a SendMessage."""
    app = ChatTUIApp(model="opus", verbose=False, system_prompt=None, tools_enabled=True)
    async with app.run_test() as pilot:
        # Leave textarea empty, click Send
        btn = app.query_one("#send-btn")
        await pilot.click(btn)
        await pilot.pause()

        # No bubbles should be created
        view = app.query_one("#chat-view", ChatMessageView)
        children = list(view.children)
        assert len(children) == 0, f"Expected 0 bubbles, got {len(children)}"


@pytest.mark.asyncio
async def test_clear_chat_removes_bubbles():
    """Test that action_clear_chat removes all bubbles."""
    app = ChatTUIApp(model="opus", verbose=False, system_prompt=None, tools_enabled=True)
    async with app.run_test() as pilot:
        view = app.query_one("#chat-view", ChatMessageView)

        # Add a message
        view.append_user_message("test message")
        bubble_id = view.begin_assistant_message()
        view.append_chunk(bubble_id, "response")
        view.finalize_assistant_message(bubble_id)
        await pilot.pause()

        assert len(list(view.children)) >= 2

        # Clear chat
        app.action_clear_chat()
        await pilot.pause()

        assert len(list(view.children)) == 0


@pytest.mark.asyncio
async def test_chat_message_view_streaming():
    """Test the streaming bubble lifecycle: begin, append chunks, finalize."""
    app = ChatTUIApp(model="opus", verbose=False, system_prompt=None, tools_enabled=True)
    async with app.run_test() as pilot:
        view = app.query_one("#chat-view", ChatMessageView)

        # Begin assistant message
        bubble_id = view.begin_assistant_message()
        await pilot.pause()
        assert bubble_id.startswith("bubble-")

        # Append chunks
        view.append_chunk(bubble_id, "Hello ")
        view.append_chunk(bubble_id, "world")
        await pilot.pause()

        # The bubble should have streaming cursor
        bubble = view._bubbles[bubble_id]
        assert bubble.text == "Hello world"

        # Finalize
        view.finalize_assistant_message(bubble_id)
        await pilot.pause()

        # After finalization, streaming flag should be off and text clean
        assert not bubble._streaming
        assert bubble.text == "Hello world"


# --- M3: Streaming integration tests ---


@pytest.mark.asyncio
async def test_handle_user_message_locks_input():
    """Test that _handle_user_message disables the input bar."""
    app = ChatTUIApp(model="opus", verbose=False, system_prompt=None, tools_enabled=True)

    def mock_send(content, on_chunk=None):
        return "response"

    async with app.run_test() as pilot:
        # Mock the backend
        mock_backend = MagicMock()
        mock_backend.send.side_effect = mock_send
        app._backend = mock_backend

        # Directly call _handle_user_message
        app._handle_user_message("Hello")
        await pilot.pause()

        input_bar = app.query_one("#input-bar", ChatInputBar)
        assert input_bar.disabled is True


@pytest.mark.asyncio
async def test_chunk_received_updates_bubble():
    """Test that on_chat_chunk_received appends chunk to the bubble."""
    app = ChatTUIApp(model="opus", verbose=False, system_prompt=None, tools_enabled=True)
    async with app.run_test() as pilot:
        view = app.query_one("#chat-view", ChatMessageView)
        bubble_id = view.begin_assistant_message()
        await pilot.pause()

        # Post chunk message
        app.post_message(ChatChunkReceived(chunk="Hello ", bubble_id=bubble_id))
        await pilot.pause()
        app.post_message(ChatChunkReceived(chunk="world", bubble_id=bubble_id))
        await pilot.pause()

        bubble = view._bubbles[bubble_id]
        assert bubble.text == "Hello world"


@pytest.mark.asyncio
async def test_response_complete_finalizes_and_reenables():
    """Test that on_chat_response_complete finalizes bubble and re-enables input."""
    app = ChatTUIApp(model="opus", verbose=False, system_prompt=None, tools_enabled=True)
    async with app.run_test() as pilot:
        view = app.query_one("#chat-view", ChatMessageView)
        input_bar = app.query_one("#input-bar", ChatInputBar)

        # Start a bubble and disable input (simulating streaming)
        bubble_id = view.begin_assistant_message()
        app._current_bubble_id = bubble_id
        input_bar.disabled = True
        await pilot.pause()

        # Post response complete
        usage = {"input_tokens": 100, "output_tokens": 50, "cost_usd": 0.005}
        app.post_message(
            ChatResponseComplete(bubble_id=bubble_id, full_text="Hello world", usage=usage)
        )
        await pilot.pause()

        # Bubble should be finalized
        bubble = view._bubbles[bubble_id]
        assert not bubble._streaming

        # Input should be re-enabled
        assert input_bar.disabled is False

        # Current bubble should be cleared
        assert app._current_bubble_id is None


@pytest.mark.asyncio
async def test_subtitle_updates_with_token_count():
    """Test that subtitle updates with cumulative token count and cost."""
    app = ChatTUIApp(model="opus", verbose=False, system_prompt=None, tools_enabled=True)
    async with app.run_test() as pilot:
        view = app.query_one("#chat-view", ChatMessageView)

        # First response
        bubble_id1 = view.begin_assistant_message()
        usage1 = {"input_tokens": 100, "output_tokens": 50, "cost_usd": 0.005}
        app.post_message(
            ChatResponseComplete(bubble_id=bubble_id1, full_text="hi", usage=usage1)
        )
        await pilot.pause()

        assert "150" in app.sub_title
        assert "$0.0050" in app.sub_title

        # Second response accumulates
        bubble_id2 = view.begin_assistant_message()
        usage2 = {"input_tokens": 200, "output_tokens": 100, "cost_usd": 0.010}
        app.post_message(
            ChatResponseComplete(bubble_id=bubble_id2, full_text="bye", usage=usage2)
        )
        await pilot.pause()

        assert "450" in app.sub_title
        assert "$0.0150" in app.sub_title


@pytest.mark.asyncio
async def test_response_complete_with_empty_usage():
    """Test that response complete handles missing/empty usage gracefully."""
    app = ChatTUIApp(model="opus", verbose=False, system_prompt=None, tools_enabled=True)
    async with app.run_test() as pilot:
        view = app.query_one("#chat-view", ChatMessageView)
        bubble_id = view.begin_assistant_message()

        app.post_message(
            ChatResponseComplete(bubble_id=bubble_id, full_text="hi", usage={})
        )
        await pilot.pause()

        assert app._total_input_tokens == 0
        assert app._total_output_tokens == 0
        assert app._total_cost == 0.0


@pytest.mark.asyncio
async def test_notification_handler_is_noop():
    """Test that on_chat_notification doesn't crash (no-op for M3)."""
    app = ChatTUIApp(model="opus", verbose=False, system_prompt=None, tools_enabled=True)
    async with app.run_test() as pilot:
        app.post_message(ChatNotification(notification={"message": "test"}))
        await pilot.pause()
        # Should not raise


@pytest.mark.asyncio
async def test_backend_created_on_mount():
    """Test that the ChatBackend is created during on_mount."""
    with patch("orchestrator_auto.chat_backend.ChatBackend") as MockBackend:
        app = ChatTUIApp(model="sonnet", verbose=False, system_prompt="custom", tools_enabled=False)
        async with app.run_test() as pilot:
            MockBackend.assert_called_once_with(
                model="sonnet",
                system_prompt="custom",
                tools_enabled=False,
            )
            assert app._backend is not None


# --- M4: Verbose panel tests ---


@pytest.mark.asyncio
async def test_verbose_panel_mounted_when_verbose_true():
    """Test that VerbosePanel is present in the DOM when verbose=True."""
    app = ChatTUIApp(model="opus", verbose=True, system_prompt=None, tools_enabled=True)
    async with app.run_test() as pilot:
        panel = app.query_one("#verbose-panel", VerbosePanel)
        assert panel is not None
        # Main area should be a Horizontal container
        main_area = app.query_one("#main-area")
        assert main_area is not None


@pytest.mark.asyncio
async def test_verbose_panel_not_mounted_when_verbose_false():
    """Test that VerbosePanel is absent when verbose=False."""
    app = ChatTUIApp(model="opus", verbose=False, system_prompt=None, tools_enabled=True)
    async with app.run_test() as pilot:
        panels = app.query("#verbose-panel")
        assert len(panels) == 0
        # No #main-area wrapper either
        main_areas = app.query("#main-area")
        assert len(main_areas) == 0


@pytest.mark.asyncio
async def test_notification_appears_in_verbose_panel():
    """Test that posting ChatNotification populates the verbose panel."""
    app = ChatTUIApp(model="opus", verbose=True, system_prompt=None, tools_enabled=True)
    async with app.run_test() as pilot:
        app.post_message(
            ChatNotification(notification={"message": "Reading file...", "type": "info"})
        )
        await pilot.pause()

        panel = app.query_one("#verbose-panel", VerbosePanel)
        # Panel should have entries beyond the header
        entries = [c for c in panel.children if "verbose-header" not in c.classes]
        assert len(entries) == 1


@pytest.mark.asyncio
async def test_tool_event_appears_in_verbose_panel():
    """Test that posting ChatToolEvent populates the verbose panel."""
    app = ChatTUIApp(model="opus", verbose=True, system_prompt=None, tools_enabled=True)
    async with app.run_test() as pilot:
        app.post_message(
            ChatToolEvent(
                tool_name="Glob",
                tool_input={"pattern": "**/*.py"},
                tool_response="12 results",
            )
        )
        await pilot.pause()

        panel = app.query_one("#verbose-panel", VerbosePanel)
        entries = [c for c in panel.children if "verbose-header" not in c.classes]
        assert len(entries) == 1


@pytest.mark.asyncio
async def test_f2_toggles_verbose_panel():
    """Test that F2 keypress toggles the verbose panel display."""
    app = ChatTUIApp(model="opus", verbose=True, system_prompt=None, tools_enabled=True)
    async with app.run_test() as pilot:
        panel = app.query_one("#verbose-panel", VerbosePanel)
        assert panel.display is True

        await pilot.press("f2")
        await pilot.pause()
        assert panel.display is False

        await pilot.press("f2")
        await pilot.pause()
        assert panel.display is True


@pytest.mark.asyncio
async def test_f2_noop_when_no_verbose_panel():
    """Test that F2 does nothing when verbose panel is not mounted."""
    app = ChatTUIApp(model="opus", verbose=False, system_prompt=None, tools_enabled=True)
    async with app.run_test() as pilot:
        # Should not raise
        await pilot.press("f2")
        await pilot.pause()


@pytest.mark.asyncio
async def test_clear_chat_also_clears_verbose_panel():
    """Test that action_clear_chat clears the verbose panel entries."""
    app = ChatTUIApp(model="opus", verbose=True, system_prompt=None, tools_enabled=True)
    async with app.run_test() as pilot:
        # Add a notification
        app.post_message(
            ChatNotification(notification={"message": "test", "type": "info"})
        )
        await pilot.pause()

        panel = app.query_one("#verbose-panel", VerbosePanel)
        entries = [c for c in panel.children if "verbose-header" not in c.classes]
        assert len(entries) == 1

        # Clear chat
        app.action_clear_chat()
        await pilot.pause()

        entries = [c for c in panel.children if "verbose-header" not in c.classes]
        assert len(entries) == 0


# --- VerbosePanel unit tests ---


@pytest.mark.asyncio
async def test_verbose_panel_add_notification():
    """Test VerbosePanel.add_notification() directly."""
    app = ChatTUIApp(model="opus", verbose=True, system_prompt=None, tools_enabled=True)
    async with app.run_test() as pilot:
        panel = app.query_one("#verbose-panel", VerbosePanel)
        panel.add_notification("Running glob search", "info")
        await pilot.pause()

        entries = [c for c in panel.children if "notif-entry" in c.classes]
        assert len(entries) == 1


@pytest.mark.asyncio
async def test_verbose_panel_add_tool_event():
    """Test VerbosePanel.add_tool_event() directly."""
    app = ChatTUIApp(model="opus", verbose=True, system_prompt=None, tools_enabled=True)
    async with app.run_test() as pilot:
        panel = app.query_one("#verbose-panel", VerbosePanel)
        panel.add_tool_event("Read", {"file_path": "/test.py"}, "file contents")
        await pilot.pause()

        entries = [c for c in panel.children if "tool-entry" in c.classes]
        assert len(entries) == 1


@pytest.mark.asyncio
async def test_verbose_panel_clear_events():
    """Test VerbosePanel.clear_events() removes entries but keeps header."""
    app = ChatTUIApp(model="opus", verbose=True, system_prompt=None, tools_enabled=True)
    async with app.run_test() as pilot:
        panel = app.query_one("#verbose-panel", VerbosePanel)
        panel.add_notification("test1", "info")
        panel.add_tool_event("Glob", {"pattern": "*.py"}, "5 results")
        await pilot.pause()

        panel.clear_events()
        await pilot.pause()

        # Only the header should remain
        entries = [c for c in panel.children if "verbose-header" not in c.classes]
        assert len(entries) == 0
        # Header should still be there
        headers = [c for c in panel.children if "verbose-header" in c.classes]
        assert len(headers) == 1


# --- M5: Polish, shortcuts, help, Markdown tests ---


@pytest.mark.asyncio
async def test_clear_command_does_not_call_backend():
    """Test that /clear input clears chat without calling backend."""
    app = ChatTUIApp(model="opus", verbose=False, system_prompt=None, tools_enabled=True)
    async with app.run_test() as pilot:
        mock_backend = MagicMock()
        app._backend = mock_backend

        view = app.query_one("#chat-view", ChatMessageView)
        # Add some messages first
        view.append_user_message("hello")
        bubble_id = view.begin_assistant_message()
        view.append_chunk(bubble_id, "hi")
        view.finalize_assistant_message(bubble_id)
        await pilot.pause()
        assert len(list(view.children)) >= 2

        # Send /clear
        app._handle_user_message("/clear")
        await pilot.pause()

        # Chat should be cleared
        assert len(list(view.children)) == 0
        # Backend should NOT have been called
        mock_backend.send.assert_not_called()


@pytest.mark.asyncio
async def test_help_modal_opens_on_f1():
    """Test that F1 opens the HelpModal."""
    app = ChatTUIApp(model="opus", verbose=False, system_prompt=None, tools_enabled=True)
    async with app.run_test() as pilot:
        await pilot.press("f1")
        await pilot.pause()

        # HelpModal should be on the screen stack
        assert len(app.screen_stack) > 1
        assert isinstance(app.screen_stack[-1], HelpModal)


@pytest.mark.asyncio
async def test_help_modal_dismisses_on_escape():
    """Test that HelpModal dismisses with Escape."""
    app = ChatTUIApp(model="opus", verbose=False, system_prompt=None, tools_enabled=True)
    async with app.run_test() as pilot:
        await pilot.press("f1")
        await pilot.pause()
        assert isinstance(app.screen_stack[-1], HelpModal)

        await pilot.press("escape")
        await pilot.pause()
        # Should be back to main screen
        assert len(app.screen_stack) == 1


@pytest.mark.asyncio
async def test_quit_triggers_confirmation_modal():
    """Test that quit action shows ConfirmModal."""
    app = ChatTUIApp(model="opus", verbose=False, system_prompt=None, tools_enabled=True)
    async with app.run_test() as pilot:
        app.action_quit()
        await pilot.pause()

        assert len(app.screen_stack) > 1
        assert isinstance(app.screen_stack[-1], ConfirmModal)


@pytest.mark.asyncio
async def test_confirm_modal_no_does_not_exit():
    """Test that clicking No in ConfirmModal does not exit."""
    app = ChatTUIApp(model="opus", verbose=False, system_prompt=None, tools_enabled=True)
    async with app.run_test() as pilot:
        app.action_quit()
        await pilot.pause()

        # Click "No" button
        modal = app.screen_stack[-1]
        no_btn = modal.query_one("#confirm-no")
        await pilot.click(no_btn)
        await pilot.pause()

        # Should be back to main screen, app still running
        assert len(app.screen_stack) == 1


@pytest.mark.asyncio
async def test_markdown_widget_used_in_assistant_bubbles():
    """Test that assistant bubbles use Markdown widget for content."""
    app = ChatTUIApp(model="opus", verbose=False, system_prompt=None, tools_enabled=True)
    async with app.run_test() as pilot:
        view = app.query_one("#chat-view", ChatMessageView)
        bubble_id = view.begin_assistant_message()
        view.append_chunk(bubble_id, "# Hello\n\nSome **bold** text")
        view.finalize_assistant_message(bubble_id)
        await pilot.pause()

        bubble = view._bubbles[bubble_id]
        # The content widget should be a Markdown instance
        md_widgets = bubble.query(Markdown)
        assert len(md_widgets) > 0


# --- Bug fix tests: /clear resets backend, worker error recovery, quit cleanup ---


@pytest.mark.asyncio
async def test_clear_resets_backend_context():
    """Test that action_clear_chat calls backend.reset() to clear conversation history."""
    app = ChatTUIApp(model="opus", verbose=False, system_prompt=None, tools_enabled=True)
    async with app.run_test() as pilot:
        mock_backend = MagicMock()
        app._backend = mock_backend

        app.action_clear_chat()
        await pilot.pause()

        mock_backend.reset.assert_called_once()


@pytest.mark.asyncio
async def test_clear_reenables_input_bar():
    """Test that action_clear_chat re-enables the input bar (handles clearing mid-stream)."""
    app = ChatTUIApp(model="opus", verbose=False, system_prompt=None, tools_enabled=True)
    async with app.run_test() as pilot:
        mock_backend = MagicMock()
        app._backend = mock_backend

        # Simulate mid-stream: disable input
        input_bar = app.query_one("#input-bar", ChatInputBar)
        input_bar.disabled = True

        app.action_clear_chat()
        await pilot.pause()

        assert input_bar.disabled is False


@pytest.mark.asyncio
async def test_worker_failure_reenables_input():
    """Test that a backend.send() failure re-enables input and shows error."""
    app = ChatTUIApp(model="opus", verbose=False, system_prompt=None, tools_enabled=True)
    async with app.run_test() as pilot:
        view = app.query_one("#chat-view", ChatMessageView)
        input_bar = app.query_one("#input-bar", ChatInputBar)

        # Start a bubble and disable input (simulating streaming start)
        bubble_id = view.begin_assistant_message()
        app._current_bubble_id = bubble_id
        input_bar.disabled = True
        await pilot.pause()

        # Post a ChatSendFailed message (simulating what the worker would do)
        app.post_message(ChatSendFailed(bubble_id=bubble_id, error="Connection timeout"))
        await pilot.pause()

        # Input should be re-enabled
        assert input_bar.disabled is False
        # Current bubble should be cleared
        assert app._current_bubble_id is None
        # Bubble should be finalized (no streaming cursor)
        bubble = view._bubbles[bubble_id]
        assert not bubble._streaming


@pytest.mark.asyncio
async def test_quit_calls_backend_reset():
    """Test that confirming quit calls backend.reset() before exiting."""
    app = ChatTUIApp(model="opus", verbose=False, system_prompt=None, tools_enabled=True)
    async with app.run_test() as pilot:
        mock_backend = MagicMock()
        app._backend = mock_backend

        app.action_quit()
        await pilot.pause()

        # Confirm quit
        modal = app.screen_stack[-1]
        yes_btn = modal.query_one("#confirm-yes")
        await pilot.click(yes_btn)
        await pilot.pause()

        mock_backend.reset.assert_called_once()
