import subprocess
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical, ScrollableContainer
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
        self.upside_down_sessions: set[str] = set()

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
        Binding("u", "toggle_upside_down", "Upside Down", show=True, priority=True),
        Binding("f22", "dummy_back", "Back", key_display="◀", show=True),
        Binding("f23", "dummy_preview", "Preview", key_display="▶", show=True),
    ]

    def action_dummy_preview(self) -> None:
        """Dummy action for the Preview footer anchor."""
        pass

    def action_dummy_back(self) -> None:
        """Dummy action for the Back footer anchor."""
        pass

    def action_toggle_upside_down(self) -> None:
        """Toggles the upside-down (top-anchored) state for the active session."""
        list_view = self.query_one("#session-list", OptionList)
        session_to_toggle = self.current_session
        
        # Fallback to the highlighted index if current_session is unassigned
        if not session_to_toggle and list_view.highlighted is not None:
            option = list_view.get_option_at_index(list_view.highlighted)
            if option and option.id:
                session_to_toggle = option.id
                
        if not session_to_toggle:
            return
            
        if session_to_toggle in self.upside_down_sessions:
            self.upside_down_sessions.remove(session_to_toggle)
        else:
            self.upside_down_sessions.add(session_to_toggle)
            
        self.refresh_sessions()

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal():
            with Vertical(id="left-pane"):
                yield Input(placeholder="Search sessions...", id="search-input", classes="hidden")
                yield OptionList(id="session-list")
            with Vertical(id="right-pane"):
                with ScrollableContainer(id="preview-container"):  
                    yield Static("Select a session to preview...", id="preview-window")
        yield Footer()

    def on_mount(self) -> None:
        """Initializes the UI state and starts the background timers."""
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
            # Strip whitespace from each session line to prevent lookup mismatches
            sessions = [s.strip() for s in result.strip().split("\n") if s.strip()]
            
            if not sessions:
                raise subprocess.CalledProcessError(1, "tmux")
                
            reversed_sessions = list(reversed(sessions))
                
            if self.search_query:
                filtered_sessions = [s for s in reversed_sessions if self.search_query in s.lower()]
            else:
                filtered_sessions = reversed_sessions
            
            target_index = 0
            for i, session in enumerate(filtered_sessions):
                is_ud = session in self.upside_down_sessions
                suffix = " [U]" if is_ud else ""
                max_base_len = 20 - len(suffix)
                
                if len(session) > max_base_len:
                    base_display = session[:max_base_len - 3] + "..."
                else:
                    base_display = session
                
                display_str = base_display + suffix
                
                # Wrap in Text() to treat [U] as literal text instead of a Rich markup tag
                list_view.add_option(Option(Text(display_str), id=session))
                
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
        """Fetches terminal output and history from tmux to update the preview."""
        container = self.query_one("#preview-container", ScrollableContainer)
        preview_window = self.query_one("#preview-window", Static)
        
        # 1. Grab the current width and height of the Textual preview container
        width = container.size.width
        height = container.size.height

        # 2. Resize the underlying tmux window to match the pane dimensions
        if width > 0 and height > 0:
            try:
                subprocess.run(
                    ["tmux", "resize-window", "-t", session_name, "-x", str(width), "-y", str(height)],
                    check=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
            except Exception:
                pass

        try:
            result = subprocess.check_output(
                ["tmux", "capture-pane", "-ep", "-S", "-1000", "-t", session_name]
            )
            raw_text = result.decode('utf-8')
            
            # Natural top-to-bottom text order (no line reversal)
            ansi_text = Text.from_ansi(raw_text)
            
            # 1. Capture state from the container
            is_focused = container.has_focus
            current_x, current_y = container.scroll_offset
            
            # 2. Update the text
            preview_window.update(ansi_text)
            
            # 3. Restore scroll or pin to top/bottom based on session settings
            def restore_scroll():
                is_top_anchored = session_name in self.upside_down_sessions
                
                if is_focused:
                    container.scroll_to(current_x, current_y, animate=False)
                elif is_top_anchored:
                    container.scroll_to(0, 0, animate=False)
                else:
                    container.scroll_end(animate=False)
                    
            self.set_timer(0.05, restore_scroll)
                
        except Exception:
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
        """Intercepts raw key presses globally for custom pane navigation."""
        search_input = self.query_one("#search-input", Input)
        list_view = self.query_one("#session-list", OptionList)
        container = self.query_one("#preview-container", ScrollableContainer)
        
        # Scenario 1: User is actively typing in the search box.
        if search_input.has_focus:
            if event.key == "down":
                event.prevent_default()
                list_view.action_cursor_down()
            elif event.key == "up":
                event.prevent_default()
                list_view.action_cursor_up()
                
        # Scenario 2: User is navigating the session list.
        elif list_view.has_focus:
            if event.key == "right" and self.current_session:
                event.prevent_default()
                container.focus()
                
                # Respect top-anchor ([U]) vs live-tail when entering preview
                if self.current_session in self.upside_down_sessions:
                    container.scroll_to(0, 0, animate=False)
                else:
                    container.scroll_end(animate=False)
                
        # Scenario 3: User is scrolling the live preview.
        elif container.has_focus:
            if event.key == "left" or event.key == "escape":
                event.prevent_default()
                list_view.focus()

    def action_scroll_preview(self) -> None:
        """Fires when 'v' is pressed. Shifts focus to the preview pane for live scrolling."""
        if not self.current_session:
            return
            
        container = self.query_one("#preview-container", ScrollableContainer)
        container.focus()
        container.scroll_end(animate=False)

    def action_focus_preview(self) -> None:
        """Shifts focus to the preview pane, or moves text cursor if searching."""
        search_input = self.query_one("#search-input", Input)
        
        # 1. If typing in the search box, just move the cursor right
        if search_input.has_focus:
            search_input.action_cursor_right()
            return
            
        # 2. Otherwise, shift focus to the preview pane
        if self.query_one("#session-list").has_focus and self.current_session:
            container = self.query_one("#preview-container", ScrollableContainer)
            container.focus()
            
            # If the session is top-anchored ([U]), start at the top (0, 0). 
            # Otherwise, tail the bottom like normal sessions.
            if self.current_session in self.upside_down_sessions:
                container.scroll_to(0, 0, animate=False)
            else:
                container.scroll_end(animate=False)

    def action_focus_list(self) -> None:
        """Shifts focus back to the session list, or moves text cursor if searching."""
        search_input = self.query_one("#search-input", Input)
        
        # 1. If typing in the search box, just move the cursor left
        if search_input.has_focus:
            search_input.action_cursor_left()
            return
            
        # 2. Otherwise, shift focus back to the session list
        if self.query_one("#preview-container").has_focus:
            self.query_one("#session-list").focus()

def main() -> None:
    """Entry point for the Smux command-line application."""
    app = TmuxManager()
    app.run()

if __name__ == "__main__":
    main()