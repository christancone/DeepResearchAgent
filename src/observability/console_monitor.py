"""
Console Monitor

Real-time console display of agent activity.
Provides both rich live display and simple line-by-line logging.
"""

from collections import deque
from datetime import datetime
from typing import Optional, Dict, Any, List

from src.observability.events import AgentEvent, EventType, EVENT_ICONS
from src.observability.emitter import EventEmitter


class ConsoleLiveMonitor:
    """
    Real-time console display of agent activity using Rich library.
    
    Shows:
    - Current agent and what it's doing
    - Recent events stream
    - Active plan and progress
    - Tool calls with timing
    - Token/context usage
    """
    
    def __init__(self, max_events: int = 20):
        """
        Initialize the live monitor.
        
        Args:
            max_events: Maximum recent events to display
        """
        self.max_events = max_events
        self.recent_events: deque = deque(maxlen=max_events)
        self.current_agent: str = ""
        self.current_action: str = ""
        self.active_plan: Optional[Dict[str, Any]] = None
        self.token_usage: Dict[str, int] = {"input": 0, "output": 0}
        self.context_usage_percent: float = 0.0
        self.start_time: Optional[datetime] = None
        self._live = None
        self._console = None
        self._unsubscribe = None
    
    def start(self):
        """Start the live monitor."""
        try:
            from rich.console import Console
            from rich.live import Live
            
            self._console = Console()
            self.start_time = datetime.utcnow()
            
            # Subscribe to all events
            emitter = EventEmitter.get_instance()
            self._unsubscribe = emitter.subscribe(None, self._handle_event)
            
            # Start live display
            self._live = Live(
                self._build_display(),
                console=self._console,
                refresh_per_second=4
            )
            self._live.start()
            
        except ImportError:
            print("Rich library not available. Using SimpleConsoleLogger instead.")
            logger = SimpleConsoleLogger(verbose=True)
            logger.attach()
    
    def stop(self):
        """Stop the live monitor."""
        if self._live:
            self._live.stop()
            self._live = None
        
        if self._unsubscribe:
            self._unsubscribe()
            self._unsubscribe = None
    
    def _handle_event(self, event: AgentEvent):
        """Handle incoming events."""
        self.recent_events.append(event)
        
        # Update state based on event type
        if event.event_type == EventType.AGENT_STARTED:
            self.current_agent = event.agent_name
            task = event.data.get('task', '')
            self.current_action = f"Starting: {task[:50]}..."
        
        elif event.event_type == EventType.AGENT_THINKING:
            self.current_agent = event.agent_name
            thought = event.data.get('thought', '')
            self.current_action = f"Thinking: {thought[:50]}..."
        
        elif event.event_type == EventType.TOOL_CALLED:
            self.current_action = f"Calling: {event.data.get('tool_name', 'unknown')}"
        
        elif event.event_type == EventType.PLAN_CREATED:
            self.active_plan = event.data
        
        elif event.event_type == EventType.PLAN_UPDATED:
            if self.active_plan:
                self.active_plan.update(event.data)
        
        elif event.event_type == EventType.CONTEXT_BUDGET_WARNING:
            self.context_usage_percent = event.data.get('usage_percent', 0)
        
        # Update token usage
        if event.token_count:
            self.token_usage["input"] += event.token_count
        
        # Refresh display
        if self._live:
            try:
                self._live.update(self._build_display())
            except Exception:
                pass  # Ignore display errors
    
    def _build_display(self):
        """Build the live display layout."""
        try:
            from rich.layout import Layout
            from rich.panel import Panel
            from rich.table import Table
            from rich.text import Text
            
            layout = Layout()
            
            layout.split_column(
                Layout(name="header", size=3),
                Layout(name="main"),
                Layout(name="footer", size=3)
            )
            
            layout["main"].split_row(
                Layout(name="events", ratio=2),
                Layout(name="status", ratio=1)
            )
            
            # Header
            elapsed = ""
            if self.start_time:
                elapsed_secs = (datetime.utcnow() - self.start_time).total_seconds()
                elapsed = f" | Elapsed: {int(elapsed_secs)}s"
            
            layout["header"].update(
                Panel(
                    f"[bold blue]🤖 Asset Research Agent[/bold blue]{elapsed}",
                    style="blue"
                )
            )
            
            # Events stream
            events_table = Table(show_header=False, box=None, padding=(0, 1))
            events_table.add_column("Time", style="dim", width=8)
            events_table.add_column("Event", overflow="fold")
            
            for event in list(self.recent_events)[-15:]:
                time_str = event.timestamp.strftime("%H:%M:%S")
                events_table.add_row(time_str, event.to_human_readable())
            
            layout["events"].update(
                Panel(events_table, title="[bold]Event Stream[/bold]", border_style="green")
            )
            
            # Status panel
            status_content = self._build_status_panel()
            layout["status"].update(
                Panel(status_content, title="[bold]Status[/bold]", border_style="yellow")
            )
            
            # Footer
            tokens = f"Tokens: {self.token_usage['input']:,} in / {self.token_usage['output']:,} out"
            context = f"Context: {self.context_usage_percent:.1f}%"
            layout["footer"].update(
                Panel(f"{tokens} | {context}", style="dim")
            )
            
            return layout
            
        except ImportError:
            return "Rich library not available"
    
    def _build_status_panel(self):
        """Build the status panel content."""
        try:
            from rich.text import Text
            
            text = Text()
            
            # Current agent
            text.append("Agent: ", style="bold")
            text.append(f"{self.current_agent}\n", style="cyan")
            
            # Current action
            text.append("Action: ", style="bold")
            text.append(f"{self.current_action}\n\n", style="white")
            
            # Active plan
            if self.active_plan:
                text.append("Plan:\n", style="bold")
                steps = self.active_plan.get('steps', [])
                for i, step in enumerate(steps[:5]):
                    if isinstance(step, dict):
                        status = step.get('status', 'pending')
                        description = step.get('description', f'Step {i+1}')
                    else:
                        status = 'pending'
                        description = str(step)[:50]
                    
                    icon = "✓" if status == 'completed' else "▶" if status == 'in_progress' else "○"
                    style = "green" if status == 'completed' else "yellow" if status == 'in_progress' else "dim"
                    text.append(f"  {icon} {description}\n", style=style)
            
            return text
            
        except ImportError:
            return "Status unavailable"


class SimpleConsoleLogger:
    """
    Simple line-by-line console logger for agent events.
    
    Less fancy than ConsoleLiveMonitor but works in all environments.
    """
    
    def __init__(self, verbose: bool = True, use_colors: bool = True):
        """
        Initialize the console logger.
        
        Args:
            verbose: Show all events vs just major ones
            use_colors: Use ANSI color codes
        """
        self.verbose = verbose
        self.use_colors = use_colors
        self.indent_level = 0
        self._unsubscribe = None
        self._console = None
        
        # Try to use Rich console if available
        if use_colors:
            try:
                from rich.console import Console
                self._console = Console()
            except ImportError:
                self._console = None
    
    def attach(self):
        """Attach to event emitter."""
        emitter = EventEmitter.get_instance()
        self._unsubscribe = emitter.subscribe(None, self._handle_event)
    
    def detach(self):
        """Detach from event emitter."""
        if self._unsubscribe:
            self._unsubscribe()
            self._unsubscribe = None
    
    def _handle_event(self, event: AgentEvent):
        """Handle and print event."""
        # Adjust indent for hierarchical display
        if event.event_type == EventType.MANAGED_AGENT_DELEGATED:
            self.indent_level += 1
        elif event.event_type == EventType.MANAGED_AGENT_RESPONSE:
            self.indent_level = max(0, self.indent_level - 1)
        
        indent = "  " * self.indent_level
        
        # Format based on verbosity
        if self.verbose:
            self._print(f"{indent}{event.to_human_readable()}")
        else:
            # Only show major events
            if event.event_type in [
                EventType.AGENT_STARTED,
                EventType.AGENT_COMPLETED,
                EventType.AGENT_ERROR,
                EventType.TOOL_COMPLETED,
                EventType.PLAN_CREATED,
                EventType.MANAGED_AGENT_DELEGATED,
                EventType.MANAGED_AGENT_RESPONSE,
                EventType.FINAL_ANSWER_GENERATED
            ]:
                self._print(f"{indent}{event.to_human_readable()}")
    
    def _print(self, message: str):
        """Print message, using Rich console if available."""
        if self._console:
            self._console.print(message)
        else:
            # Strip emoji if terminal doesn't support it
            try:
                print(message)
            except UnicodeEncodeError:
                # Remove emoji and try again
                import re
                clean_message = re.sub(r'[^\x00-\x7F]+', '', message)
                print(clean_message)


def print_execution_summary(events: List[AgentEvent]):
    """
    Print a summary of execution from event history.
    
    Args:
        events: List of events from the execution
    """
    if not events:
        print("No events to summarize.")
        return
    
    try:
        from rich.console import Console
        from rich.table import Table
        
        console = Console()
        
        # Build summary table
        table = Table(title="Execution Summary")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")
        
        # Calculate statistics
        total_events = len(events)
        agents_used = set(e.agent_name for e in events if e.agent_name)
        tools_called = [e for e in events if e.event_type == EventType.TOOL_CALLED]
        errors = [e for e in events if e.event_type in [EventType.AGENT_ERROR, EventType.TOOL_ERROR]]
        
        start_time = events[0].timestamp
        end_time = events[-1].timestamp
        duration = (end_time - start_time).total_seconds()
        
        total_tokens = sum(e.token_count or 0 for e in events)
        total_tool_duration = sum(e.duration_ms or 0 for e in events if e.event_type == EventType.TOOL_COMPLETED)
        
        table.add_row("Total Events", str(total_events))
        table.add_row("Agents Used", ", ".join(agents_used))
        table.add_row("Tools Called", str(len(tools_called)))
        table.add_row("Errors", str(len(errors)))
        table.add_row("Duration", f"{duration:.1f}s")
        table.add_row("Total Tokens", f"{total_tokens:,}")
        table.add_row("Tool Time", f"{total_tool_duration}ms")
        
        console.print(table)
        
        # Print errors if any
        if errors:
            console.print("\n[bold red]Errors:[/bold red]")
            for error in errors:
                console.print(f"  - {error.agent_name}: {error.data.get('error', 'Unknown')}")
    
    except ImportError:
        # Fallback to simple print
        print("\n=== Execution Summary ===")
        print(f"Total Events: {len(events)}")
        print(f"Agents Used: {set(e.agent_name for e in events if e.agent_name)}")
        print(f"Duration: {(events[-1].timestamp - events[0].timestamp).total_seconds():.1f}s")
