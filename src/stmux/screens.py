from textual.app import ComposeResult
from textual.containers import Center, Middle, Vertical, Horizontal
from textual.widgets import Label, Input, Button
from textual.screen import ModalScreen

class NewSessionScreen(ModalScreen[str]):
    """Screen with a dialog to create a new session."""
    def compose(self) -> ComposeResult:
        with Middle():
            with Center():
                yield Vertical(
                    Label("Enter new session name:"),
                    Input(placeholder="Session name...", id="session_name"),
                    id="dialog"
                )

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(event.value)


class RenameSessionScreen(ModalScreen[str]):
    """Screen with a dialog to rename an existing session."""
    def __init__(self, current_name: str, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.current_name = current_name

    def compose(self) -> ComposeResult:
        with Middle():
            with Center():
                yield Vertical(
                    Label("Rename session:"),
                    Input(value=self.current_name, id="rename_input"),
                    id="dialog"
                )

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(event.value)


class ConfirmDeleteScreen(ModalScreen[bool]):
    """Screen with a dialog to confirm session deletion."""
    
    BINDINGS = [
        ("delete", "confirm", "Confirm"),
        ("escape", "cancel", "Cancel"),
        # Map Left/Right arrows directly to Textual's built-in focus switcher!
        ("left", "app.focus_previous", "Focus Previous"),
        ("right", "app.focus_next", "Focus Next")
    ]

    def __init__(self, session_name: str, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.session_name = session_name

    def compose(self) -> ComposeResult:
        with Middle():
            with Center():
                yield Vertical(
                    Label(f"Are you sure you want to delete session: [bold red]{self.session_name}[/]?"),
                    Horizontal(
                        Button("Cancel", id="cancel"),
                        Button("OK", id="ok"),
                        id="dialog-buttons"
                    ),
                    id="dialog"
                )

    def on_mount(self) -> None:
        """Fires right when the screen opens. We force focus onto Cancel."""
        self.query_one("#cancel").focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Fires when a button is clicked or activated with Enter."""
        if event.button.id == "ok":
            self.dismiss(True)
        else:
            self.dismiss(False)

    def action_confirm(self) -> None:
        """Fires when the 'delete' key is pressed."""
        self.dismiss(True)

    def action_cancel(self) -> None:
        """Fires when 'escape' is pressed."""
        self.dismiss(False)