import subprocess
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Header, Footer, OptionList, Static
from textual.widgets.option_list import Option
from textual.binding import Binding
from rich.text import Text
from screens import NewSessionScreen

class TmuxManager(App):
    """A Textual application to manage tmux sessions."""
    TITLE = "Smux Session Overview Tool"

    def __init__(self) -> None:
        super().__init__()
        self.current_session: str | None = None
        self.preview_timer = None

    # Point to external stylesheet
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
                yield OptionList(id="session-list")
            with Vertical(id="right-pane"):
                yield Static("Select a session to preview...", id="preview-window")
        yield Footer()

    def on_mount(self) -> None:
        # Set border titles
        self.query_one("#left-pane").border_title = "Sessions"
        self.query_one("#right-pane").border_title = "Live Preview"
        
        self.refresh_sessions()
        self.preview_timer = self.set_interval(1.0, self.tick_preview)
    
    def tick_preview(self) -> None:
        """The function called by the timer to update the preview."""
        if self.current_session:
            self.update_preview(self.current_session)

    def refresh_sessions(self) -> None:
        list_view = self.query_one("#session-list", OptionList)
        list_view.clear_options()
        
        # Clear the current session to prevent ghost polling
        self.current_session = None
        
        try:
            result = subprocess.check_output(
                ["tmux", "list-sessions", "-F", "#{session_name}"], 
                text=True
            )
            sessions = result.strip().split("\n")
            
            valid_sessions = [s for s in sessions if s]
            if not valid_sessions:
                raise subprocess.CalledProcessError(1, "tmux")
                
            for session in valid_sessions:
                # Truncate display name if it exceeds 20 characters
                if len(session) > 20:
                    display_name = session[:17] + "..."
                else:
                    display_name = session
                
                # Display the truncated name, but keep the full session in the id
                list_view.add_option(Option(display_name, id=session))
                
            # If options were added and nothing is highlighted, highlight the first one
            if valid_sessions and list_view.highlighted is None:
                list_view.highlighted = 0
                
        except subprocess.CalledProcessError:
            self.current_session = None
            self.query_one("#preview-window", Static).update(
                "No active tmux sessions found.\n\nPress 'X' to create a new session!"
            )

    def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        if not event.option or not event.option.id:
            self.current_session = None
            return
        
        self.current_session = event.option.id
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

        # Push the popup screen
        self.push_screen(NewSessionScreen(), check_result)

    async def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if not event.option or not event.option.id:
            return
            
        session_name = event.option.id
        
        if self.preview_timer:
            self.preview_timer.pause()
            
        with self.suspend():
            # Clear screen buffer instantly to prevent the text flash artifact
            print("\033[2J\033[H", end="", flush=True)
            subprocess.run(["tmux", "attach-session", "-t", session_name])
            
        self.refresh_sessions()
        if self.preview_timer:
            self.preview_timer.resume()
    
    def action_kill_session(self) -> None:
        """Fires when 'delete' is pressed. Kills the highlighted tmux session."""
        if not self.current_session:
            return
            
        session_name = self.current_session
        
        # Clear tracker immediately before killing
        self.current_session = None
        
        # Tell tmux to kill it in the background
        subprocess.run(["tmux", "kill-session", "-t", session_name])
        
        # Refresh the UI to remove it from the list
        self.refresh_sessions()

def main() -> None:
    """Entry point for the Smux command-line application."""
    app = TmuxManager()
    app.run()

if __name__ == "__main__":
    main()