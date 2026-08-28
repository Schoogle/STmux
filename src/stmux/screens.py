from textual.app import ComposeResult
from textual.containers import Vertical, Center, Middle
from textual.widgets import Label, Input
from textual.screen import ModalScreen

class NewSessionScreen(ModalScreen[str]):
    """A popup screen to enter a new tmux session name."""

    def compose(self) -> ComposeResult:
        with Center():
            with Middle():
                with Vertical(id="dialog"):
                    yield Label("Enter new session name:")
                    yield Input(placeholder="e.g., Web_Frontend", id="session-input")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """When the user hits Enter in the input box, return the value."""
        self.dismiss(event.value)