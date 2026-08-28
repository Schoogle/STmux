import subprocess
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Header, Footer, OptionList, Static
from textual.widgets.option_list import Option
from textual.binding import Binding
from rich.text import Text
from stmux.screens import NewSessionScreen, RenameSessionScreen, ConfirmDeleteScreen
from textual.widgets import Header, Footer, OptionList, Static, Input
from textual.events import Key

class TmuxManager(App):
    """A Textual application to manage tmux sessions."""
    TITLE = "STmux Session Overview Tool"

    def __init__(self) -> None:
        super().__init__()
        self.current_session: str | None = None
        self.preview_timer = None
        self.search_query = ""

    # Point to external stylesheet
    CSS_PATH = "styles.tcss"

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("x", "new_session", "New Session"),
        Binding("r", "rename_session", "Rename"),
        Binding("delete", "kill_session", "Kill Session"),
        Binding("shift+delete", "force_kill_session", "Force Kill", show=True),
        Binding("f", "search", "Search"),
        Binding("escape", "clear_search", "Clear Search", show=False),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal():
            with Vertical(id="left-pane"):
                yield Input(placeholder="Search sessions...", id="search-input", classes="hidden")
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
        
        self.query_one("#session-list").focus()
    
    def tick_preview(self) -> None:
        """The function called by the timer to update the preview."""
        if self.current_session:
            self.update_preview(self.current_session)

    def refresh_sessions(self) -> None:
        list_view = self.query_one("#session-list", OptionList)
        
        # 1. Remember the session before refreshing
        previous_session = self.current_session
        
        list_view.clear_options()
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
                
            if self.search_query:
                filtered_sessions = [s for s in valid_sessions if self.search_query in s.lower()]
            else:
                filtered_sessions = valid_sessions
            
            target_index = 0
            for i, session in enumerate(filtered_sessions):
                if len(session) > 20:
                    display_name = session[:17] + "..."
                else:
                    display_name = session
                
                list_view.add_option(Option(display_name, id=session))
                
                if session == previous_session:
                    target_index = i
                
            if filtered_sessions:
                list_view.highlighted = target_index
                self.current_session = filtered_sessions[target_index]
                self.update_preview(self.current_session)
            else:
                self.current_session = None
                self.query_one("#preview-window", Static).update(
                    "No sessions match your search."
                )
                
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

    def action_rename_session(self) -> None:
        """Fires when 'r' is pressed. Shows the rename modal."""
        if not self.current_session:
            return

        old_name = self.current_session

        def check_result(new_name: str | None) -> None:
            if new_name and new_name != old_name:
                # Tell tmux rename the session
                subprocess.run(["tmux", "rename-session", "-t", old_name, new_name])

                # Update tracker so refresh_sessions snaps the cursor to the newly named session
                self.current_session = new_name
                self.refresh_sessions()

        # Push the popup screen and pass in the current name
        self.push_screen(RenameSessionScreen(current_name=old_name), check_result)

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
        """Fires when 'delete' is pressed. Shows confirmation modal."""
        if not self.current_session:
            return
            
        session_name = self.current_session
        
        def check_result(confirmed: bool | None) -> None:
            if confirmed:
                # Tell tmux to kill it in the background
                subprocess.run(["tmux", "kill-session", "-t", session_name])
                
                # Clear tracker immediately after killing
                self.current_session = None
                
                # Refresh the UI to remove it from the list
                self.refresh_sessions()

        # Push the confirmation screen
        self.push_screen(ConfirmDeleteScreen(session_name=session_name), check_result)

    def action_force_kill_session(self) -> None:
        """Fires when 'shift+delete' is pressed. Instantly nukes the session."""
        if not self.current_session:
            return
            
        session_name = self.current_session
        
        # Clear tracker immediately
        self.current_session = None
        
        # Instantly kill it in the background without asking
        subprocess.run(["tmux", "kill-session", "-t", session_name])
        
        # Refresh the UI
        self.refresh_sessions()

    def action_search(self) -> None:
        """Fires when 'f' is pressed."""
        search_input = self.query_one("#search-input", Input)
        search_input.remove_class("hidden")
        search_input.focus()

    def action_clear_search(self) -> None:
        """Clears and hides the search input, returning focus to the session list."""
        search_input = self.query_one("#search-input", Input)
        
        if not search_input.has_class("hidden"):
            # Preserve the active session state before clearing the input
            preserved_session = self.current_session
            
            # Suppress Input.Changed to prevent asynchronous cursor resets
            with search_input.prevent(Input.Changed):
                search_input.value = ""
                
            search_input.add_class("hidden")
            self.search_query = ""
            
            # Restore state and apply UI updates
            self.current_session = preserved_session
            self.refresh_sessions()
            self.query_one("#session-list").focus()

    def on_input_changed(self, event: Input.Changed) -> None:
        """Fires every time a letter is typed in an Input."""
        if event.input.id == "search-input":
            self.search_query = event.value.lower()
            self.current_session = None
            self.refresh_sessions()

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        """Attaches to the currently highlighted session upon form submission."""
        if event.input.id == "search-input":
            if self.current_session:
                if self.preview_timer:
                    self.preview_timer.pause()
                    
                with self.suspend():
                    print("\033[2J\033[H", end="", flush=True)
                    subprocess.run(["tmux", "attach-session", "-t", self.current_session])
                    
                self.action_clear_search()
                
                if self.preview_timer:
                    self.preview_timer.resume()

    async def on_key(self, event: Key) -> None:
        """Intercepts raw key presses globally."""
        search_input = self.query_one("#search-input", Input)
        
        # If the search bar is open and active, we hijack the arrow keys.
        # Focus NEVER leaves the text box, but the list moves in the background!
        if search_input.has_focus:
            list_view = self.query_one("#session-list", OptionList)
            
            if event.key == "down":
                event.prevent_default()
                list_view.action_cursor_down()
                
            elif event.key == "up":
                event.prevent_default()
                list_view.action_cursor_up()

def main() -> None:
    """Entry point for the Smux command-line application."""
    app = TmuxManager()
    app.run()

if __name__ == "__main__":
    main()