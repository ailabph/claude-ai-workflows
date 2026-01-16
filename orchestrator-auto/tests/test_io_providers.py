"""
Tests for I/O provider abstractions.

Tests the InputProvider interface and implementations.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from orchestrator_auto.io import InputProvider, CLIInputProvider
from orchestrator_auto.io.events import (
    ChunkEvent,
    StateChangeEvent,
    OutputEvent,
    InputRequestedEvent,
)


class TestCLIInputProvider:
    """Tests for CLI input provider."""

    def test_prompt_returns_tuple(self):
        """Ensure prompt returns (display, content) tuple."""
        # Mock the underlying function at the correct location
        mock_prompt = Mock(return_value=("display_text", "full_content"))

        with patch('orchestrator_auto.input_handler.prompt_with_paste_support', mock_prompt):
            provider = CLIInputProvider()
            display, content = provider.prompt("Test: ")

        # Verify the mock was called correctly
        mock_prompt.assert_called_once_with("Test: ", False)
        assert display == "display_text"
        assert content == "full_content"

    def test_prompt_with_eof_handling(self):
        """Test EOF handling with return_none_on_eof=True."""
        mock_prompt = Mock(return_value=(None, None))

        with patch('orchestrator_auto.input_handler.prompt_with_paste_support', mock_prompt):
            provider = CLIInputProvider()
            display, content = provider.prompt("Test: ", return_none_on_eof=True)

        mock_prompt.assert_called_once_with("Test: ", True)
        assert display is None
        assert content is None

    def test_is_input_provider_subclass(self):
        """Ensure CLIInputProvider is a subclass of InputProvider."""
        assert issubclass(CLIInputProvider, InputProvider)


class TestInputProviderInterface:
    """Tests for InputProvider ABC."""

    def test_cannot_instantiate_abstract_class(self):
        """Cannot instantiate InputProvider directly."""
        with pytest.raises(TypeError):
            InputProvider()

    def test_concrete_implementation_required(self):
        """Concrete implementations must implement all abstract methods."""

        class IncompleteProvider(InputProvider):
            pass

        with pytest.raises(TypeError):
            IncompleteProvider()

    def test_minimal_implementation(self):
        """A minimal implementation should work."""

        class MinimalProvider(InputProvider):
            def prompt(self, prompt_text, return_none_on_eof=False):
                return ("test", "test")

            def prompt_choice(self, prompt_text, choices, default=None):
                return choices[0] if choices else ""

        provider = MinimalProvider()
        display, content = provider.prompt("Test: ")
        assert display == "test"
        assert content == "test"

    def test_prompt_confirm_default_implementation(self):
        """Test the default prompt_confirm implementation."""

        class TestProvider(InputProvider):
            def prompt(self, prompt_text, return_none_on_eof=False):
                return ("y", "y")

            def prompt_choice(self, prompt_text, choices, default=None):
                return "y"

        provider = TestProvider()
        result = provider.prompt_confirm("Confirm?")
        assert result is True

    def test_prompt_confirm_returns_false_for_n(self):
        """Test prompt_confirm returns False for 'n'."""

        class TestProvider(InputProvider):
            def prompt(self, prompt_text, return_none_on_eof=False):
                return ("n", "n")

            def prompt_choice(self, prompt_text, choices, default=None):
                return "n"

        provider = TestProvider()
        result = provider.prompt_confirm("Confirm?")
        assert result is False


class TestEventDataclasses:
    """Tests for event dataclasses."""

    def test_chunk_event(self):
        """Test ChunkEvent creation and attributes."""
        event = ChunkEvent(chunk="Hello", agent="executor")
        assert event.chunk == "Hello"
        assert event.agent == "executor"

    def test_state_change_event(self):
        """Test StateChangeEvent creation."""
        mock_state = Mock()
        mock_state.phase = "execution"
        mock_state.status = "active"

        event = StateChangeEvent(
            state=mock_state,
            previous_phase="planning",
            event_type="plan_approved"
        )
        assert event.state.phase == "execution"
        assert event.previous_phase == "planning"
        assert event.event_type == "plan_approved"

    def test_state_change_event_defaults(self):
        """Test StateChangeEvent default values."""
        mock_state = Mock()
        event = StateChangeEvent(state=mock_state)
        assert event.previous_phase is None
        assert event.event_type is None

    def test_output_event(self):
        """Test OutputEvent creation and defaults."""
        event = OutputEvent(message="Hello world")
        assert event.message == "Hello world"
        assert event.level == "info"

        event_error = OutputEvent(message="Error!", level="error")
        assert event_error.level == "error"

    def test_input_requested_event(self):
        """Test InputRequestedEvent creation."""
        event = InputRequestedEvent(prompt_text="Enter value: ")
        assert event.prompt_text == "Enter value: "
        assert event.context == "input"

        event_blocker = InputRequestedEvent(
            prompt_text="Blocked!",
            context="blocker"
        )
        assert event_blocker.context == "blocker"


class TestEngineIntegration:
    """Tests for engine integration with InputProvider."""

    def test_engine_accepts_input_provider(self, tmp_path):
        """Ensure engine accepts injected input provider."""

        class MockProvider(InputProvider):
            def prompt(self, prompt_text, return_none_on_eof=False):
                return ("mock_display", "mock_input")

            def prompt_choice(self, prompt_text, choices, default=None):
                return choices[0] if choices else ""

        provider = MockProvider()

        # Import here to avoid circular import issues
        from orchestrator_auto.engine import Orchestrator

        # Create orchestrator with mock provider
        db_path = str(tmp_path / "test.db")
        orch = Orchestrator(
            feature_description="Test feature",
            db_path=db_path,
            input_provider=provider,
        )

        # Verify provider was set
        assert orch.input_provider is provider
        assert isinstance(orch.input_provider, InputProvider)

    def test_engine_defaults_to_cli_provider(self, tmp_path):
        """Ensure engine defaults to CLIInputProvider when not specified."""
        from orchestrator_auto.engine import Orchestrator

        db_path = str(tmp_path / "test.db")
        orch = Orchestrator(
            feature_description="Test feature",
            db_path=db_path,
        )

        assert isinstance(orch.input_provider, CLIInputProvider)

    def test_engine_accepts_callbacks(self, tmp_path):
        """Ensure engine accepts on_chunk and on_state_change callbacks."""
        from orchestrator_auto.engine import Orchestrator

        chunks = []
        states = []

        def on_chunk(chunk, agent):
            chunks.append((chunk, agent))

        def on_state_change(state):
            states.append(state)

        db_path = str(tmp_path / "test.db")
        orch = Orchestrator(
            feature_description="Test feature",
            db_path=db_path,
            on_chunk=on_chunk,
            on_state_change=on_state_change,
        )

        assert orch.on_chunk is on_chunk
        assert orch.on_state_change is on_state_change

    def test_engine_notify_state_change_calls_callback(self, tmp_path):
        """Ensure _notify_state_change calls the callback."""
        from orchestrator_auto.engine import Orchestrator

        states = []

        def on_state_change(state):
            states.append(state)

        db_path = str(tmp_path / "test.db")
        orch = Orchestrator(
            feature_description="Test feature",
            db_path=db_path,
            on_state_change=on_state_change,
        )

        # Manually call _notify_state_change
        orch._notify_state_change()

        # Verify callback was called with the state
        assert len(states) == 1
        assert states[0] == orch.state

    def test_engine_notify_state_change_noop_without_callback(self, tmp_path):
        """Ensure _notify_state_change is a no-op without callback."""
        from orchestrator_auto.engine import Orchestrator

        db_path = str(tmp_path / "test.db")
        orch = Orchestrator(
            feature_description="Test feature",
            db_path=db_path,
            on_state_change=None,
        )

        # Should not raise
        orch._notify_state_change()
