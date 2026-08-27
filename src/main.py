import subprocess
import traceback
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Header, Footer, ListView, ListItem, Label, Static
from textual.binding import Binding
from rich.text import Text
from screens import NewSessionScreen

class TmuxManager(App):
    """A Textual application to manage tmux sessions."""
    def __init__(self) -> None:
        super().__init__()
        self.current_session: str | None = None
        self.preview_timer = None

    # Point to the external stylesheet
    CSS_PATH = "styles.tcss"

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("x", "new_session", "New Session"), 
        Binding("delete", "kill_session", "Kill Session"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal():
            with Vertical(id="left-pane"):
                yield Static("Sessions", classes="pane-title")
                yield ListView(id="session-list")
            with Vertical(id="right-pane"):
                yield Static("Live Stream Preview", classes="pane-title")
                yield Static("Select a session to preview...", id="preview-window")
        yield Footer()

    def on_mount(self) -> None:
        self.refresh_sessions()
        # Start a background timer that triggers every 1.0 seconds
        self.preview_timer = self.set_interval(1.0, self.tick_preview)
    
    def tick_preview(self) -> None:
        """The function called by the timer to update the preview."""
        if self.current_session:
            self.update_preview(self.current_session)

    def refresh_sessions(self) -> None:
        list_view = self.query_one("#session-list", ListView)
        list_view.clear()
        
        try:
            result = subprocess.check_output(
                ["tmux", "list-sessions", "-F", "#{session_name}"], 
                text=True
            )
            sessions = result.strip().split("\n")
            
            for session in sessions:
                if session:
                    list_view.append(ListItem(Label(session), name=session))
        except subprocess.CalledProcessError:
            self.current_session = None # Stop the timer from looking for ghosts
            self.query_one("#preview-window", Static).update(
                "No active tmux sessions found.\n\nPress 'X' to create a new session!"
            )

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        if not event.item or not event.item.name:
            self.current_session = None
            return
        
        # Track the newly highlighted session and instantly preview it
        self.current_session = event.item.name
        self.update_preview(self.current_session)

    def update_preview(self, session_name: str) -> None:
        preview_window = self.query_one("#preview-window", Static)
        try:
            result = subprocess.check_output(
                ["tmux", "capture-pane", "-ep", "-t", session_name]
            )
            ansi_text = Text.from_ansi(result.decode('utf-8'))
            preview_window.update(ansi_text)
        except Exception as e:
            preview_window.update(f"Could not load preview for {session_name}.")

    def action_new_session(self) -> None:
        """Fires when 'X' is pressed. Shows the modal and handles the result."""
        def check_result(session_name: str | None) -> None:
            if session_name:
                subprocess.run(["tmux", "new-session", "-d", "-s", session_name])
                self.refresh_sessions()

        # Push the popup screen we imported from screens.py
        self.push_screen(NewSessionScreen(), check_result)

    async def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Fires when you press Enter. Suspends TUI and attaches to native tmux."""
        if not event.item or not event.item.name:
            return
            
        session_name = event.item.name
        
        # 1. Pause the background snapshot loop so it doesn't fight the terminal
        if self.preview_timer:
            self.preview_timer.pause()
            
        # 2. Seamlessly suspend the TUI and drop into native tmux
        with self.suspend():
            subprocess.run(["tmux", "attach-session", "-t", session_name])
            
        # 3. You detached! Resume the UI and background loop instantly
        self.refresh_sessions()
        if self.preview_timer:
            self.preview_timer.resume()
    
    def action_kill_session(self) -> None:
        """Fires when 'd' is pressed. Kills the highlighted tmux session."""
        list_view = self.query_one("#session-list", ListView)
        
        # Ensure a session is actually highlighted
        if list_view.highlighted_child is None:
            return
            
        # Safely extract the session name
        session_name = list_view.highlighted_child.name
        
        if session_name:
            # Tell tmux to kill it in the background
            subprocess.run(["tmux", "kill-session", "-t", session_name])
            
            # Instantly refresh the UI to remove it from the list
            self.refresh_sessions()

if __name__ == "__main__":
    app = TmuxManager()
    app.run()