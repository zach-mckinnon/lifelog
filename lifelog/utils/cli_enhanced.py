# lifelog/utils/cli_enhanced.py
"""
Modern CLI components with loading states, progress indicators, and user feedback.
"""
import time
import threading
from contextlib import contextmanager
from typing import Any, Callable, Optional, List, Dict, Union
from datetime import datetime
from enum import Enum

from rich.console import Console
from rich.progress import (
    Progress, SpinnerColumn, TextColumn, BarColumn, 
    TaskProgressColumn, TimeElapsedColumn, MofNCompleteColumn
)
from rich.panel import Panel
from rich.table import Table
from rich.layout import Layout
from rich.live import Live
from rich.text import Text
from rich.prompt import Prompt, Confirm
from rich.align import Align
from rich.rule import Rule
from rich.status import Status
from rich.spinner import Spinner

class OperationStatus(Enum):
    """Status types for operations."""
    PENDING = "pending"
    RUNNING = "running"  
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"
    CANCELLED = "cancelled"

class EnhancedCLI:
    """CLI with modern interface patterns, loading states, and progress indicators."""
    
    def __init__(self, console: Optional[Console] = None):
        self.console = console or Console()
        self._operation_count = 0
        
    def status_symbol(self, status: OperationStatus) -> str:
        """Get status symbol for different operation states."""
        symbols = {
            OperationStatus.PENDING: "⏳",
            OperationStatus.RUNNING: "🔄", 
            OperationStatus.SUCCESS: "✅",
            OperationStatus.WARNING: "⚠️",
            OperationStatus.ERROR: "❌",
            OperationStatus.CANCELLED: "🚫"
        }
        return symbols.get(status, "•")
    
    def status_color(self, status: OperationStatus) -> str:
        """Get color for different operation states."""
        colors = {
            OperationStatus.PENDING: "yellow",
            OperationStatus.RUNNING: "blue",
            OperationStatus.SUCCESS: "green", 
            OperationStatus.WARNING: "orange3",
            OperationStatus.ERROR: "red",
            OperationStatus.CANCELLED: "dim"
        }
        return colors.get(status, "white")

    @contextmanager
    def loading_operation(
        self, 
        message: str, 
        success_message: Optional[str] = None,
        spinner: str = "dots"
    ):
        """Context manager for operations with loading spinner."""
        self._operation_count += 1
        op_id = self._operation_count
        
        with self.console.status(f"[blue]{message}[/blue]", spinner=spinner) as status:
            try:
                yield status
                # Success
                final_message = success_message or f"{message} ✓"
                self.success(final_message)
            except KeyboardInterrupt:
                self.warning(f"{message} cancelled by user")
                raise
            except Exception as e:
                self.error(f"{message} failed: {str(e)}")
                raise

    @contextmanager
    def progress_operation(
        self, 
        description: str,
        total: Optional[int] = None,
        show_percentage: bool = True
    ):
        """Context manager for operations with progress bar."""
        columns = [
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}"),
            BarColumn(bar_width=40),
        ]
        
        if total and show_percentage:
            columns.extend([
                TaskProgressColumn(),
                MofNCompleteColumn(),
                TimeElapsedColumn()
            ])
        
        with Progress(*columns, console=self.console) as progress:
            task = progress.add_task(description, total=total)
            yield progress, task

    def step_progress(self, message: str, step: int, total: int):
        """Show step-based progress indicator."""
        progress_bar = "█" * int(20 * step / total) + "░" * (20 - int(20 * step / total))
        percentage = int(100 * step / total)
        
        self.console.print(
            f"[dim]Step {step}/{total}[/dim] [blue]{progress_bar}[/blue] "
            f"[dim]{percentage}%[/dim] {message}"
        )

    def operation_header(self, title: str, subtitle: Optional[str] = None):
        """Display operation header with status."""
        header_text = Text(title, style="bold bright_blue")
        if subtitle:
            header_text.append(f"\n{subtitle}", style="dim")
        
        panel = Panel(
            Align.center(header_text),
            style="blue",
            padding=(1, 2)
        )
        self.console.print(panel)

    def section_divider(self, title: Optional[str] = None):
        """Add a section divider."""
        if title:
            self.console.print(Rule(f"[bold blue]{title}[/bold blue]", style="blue"))
        else:
            self.console.print(Rule(style="dim"))

    def info(self, message: str, icon: str = "ℹ️"):
        """Display info message."""
        self.console.print(f"{icon} [dim]{message}[/dim]")

    def success(self, message: str, icon: str = "✅"):
        """Display success message."""
        self.console.print(f"{icon} [green]{message}[/green]")

    def warning(self, message: str, icon: str = "⚠️"):
        """Display warning message."""
        self.console.print(f"{icon} [orange3]{message}[/orange3]")

    def error(self, message: str, icon: str = "❌"):
        """Display error message."""
        self.console.print(f"{icon} [red]{message}[/red]")

    def thinking(self, message: str = "Processing"):
        """Show processing indicator."""
        return self.console.status(f"[dim]{message}...[/dim]", spinner="dots2")

    def enhanced_table(
        self,
        title: str,
        columns: List[str],
        rows: List[List[str]],
        show_header: bool = True,
        show_lines: bool = True
    ) -> Table:
        """Create table with improved styling."""
        table = Table(
            title=title,
            show_header=show_header,
            show_lines=show_lines,
            header_style="bold blue",
            title_style="bold bright_blue",
            border_style="blue"
        )
        
        for col in columns:
            table.add_column(col)
        
        for row in rows:
            table.add_row(*row)
            
        return table

    def interactive_select(
        self,
        message: str,
        choices: List[str],
        default: Optional[str] = None
    ) -> str:
        """Interactive selection with better UX."""
        self.console.print(f"[bold]{message}[/bold]")
        
        for i, choice in enumerate(choices, 1):
            style = "green" if choice == default else "dim"
            marker = "→" if choice == default else " "
            self.console.print(f"  {marker} [dim]{i}.[/dim] [{style}]{choice}[/{style}]")
        
        while True:
            try:
                response = Prompt.ask(
                    "\nSelect option",
                    choices=[str(i) for i in range(1, len(choices) + 1)],
                    default="1" if default is None else str(choices.index(default) + 1)
                )
                return choices[int(response) - 1]
            except (ValueError, IndexError):
                self.error("Invalid selection. Please try again.")

    def enhanced_confirm(
        self,
        message: str,
        default: bool = True,
        show_default: bool = True
    ) -> bool:
        """Confirmation prompt with non-interactive fallback."""
        try:
            return Confirm.ask(message, default=default, show_default=show_default)
        except (EOFError, KeyboardInterrupt):
            # Non-interactive environment or user cancelled
            self.info(f"Using default: {default}")
            return default

    def multi_step_operation(self, steps: List[Dict[str, Any]]):
        """Execute multi-step operation with progress feedback."""
        total_steps = len(steps)
        
        self.operation_header("Multi-Step Operation", f"{total_steps} steps to complete")
        
        for i, step in enumerate(steps, 1):
            step_name = step.get("name", f"Step {i}")
            step_func = step.get("function")
            step_args = step.get("args", ())
            step_kwargs = step.get("kwargs", {})
            
            self.step_progress(step_name, i, total_steps)
            
            try:
                with self.thinking(f"Executing {step_name}"):
                    if callable(step_func):
                        result = step_func(*step_args, **step_kwargs)
                        step["result"] = result
                
                self.success(f"{step_name} completed")
                
            except Exception as e:
                self.error(f"{step_name} failed: {str(e)}")
                raise
        
        self.success("All steps completed successfully!")
        return steps

    def database_operation_wrapper(self, operation_name: str, operation_func: Callable):
        """Wrapper for database operations with loading states."""
        with self.loading_operation(
            f"🗄️  {operation_name}",
            f"🗄️  {operation_name} completed"
        ):
            return operation_func()

    def sync_operation_display(self, sync_type: str = "data"):
        """Display sync operation progress."""
        steps = [
            "Checking connection",
            "Authenticating",
            f"Syncing {sync_type}",
            "Verifying integrity",
            "Finalizing"
        ]
        
        with self.progress_operation("🔄 Synchronizing", len(steps)) as (progress, task):
            for i, step in enumerate(steps):
                time.sleep(0.5)  # Simulate work
                progress.update(task, advance=1, description=f"🔄 {step}")
        
        self.success("Synchronization completed")

    def format_duration(self, minutes: float) -> str:
        """Format duration in a human-readable way."""
        if minutes < 1:
            return f"{minutes * 60:.0f}s"
        elif minutes < 60:
            return f"{minutes:.1f}m"
        else:
            hours = int(minutes // 60)
            mins = int(minutes % 60)
            return f"{hours}h {mins}m" if mins > 0 else f"{hours}h"

    def format_relative_time(self, dt: datetime) -> str:
        """Format datetime relative to now."""
        from lifelog.utils.shared_utils import now_utc
        
        now = now_utc()
        if dt.tzinfo is None:
            from datetime import timezone
            dt = dt.replace(tzinfo=timezone.utc)
        
        diff = now - dt
        
        if diff.days > 0:
            return f"{diff.days} days ago"
        elif diff.seconds > 3600:
            hours = diff.seconds // 3600
            return f"{hours} hours ago"
        elif diff.seconds > 60:
            minutes = diff.seconds // 60
            return f"{minutes} minutes ago"
        else:
            return "just now"

    def display_summary_card(self, title: str, data: Dict[str, Any]):
        """Display a summary card with key-value pairs."""
        content = []
        for key, value in data.items():
            content.append(f"[bold blue]{key}:[/bold blue] {value}")
        
        panel = Panel(
            "\n".join(content),
            title=f"[bold]{title}[/bold]",
            border_style="blue",
            padding=(1, 2)
        )
        self.console.print(panel)

# Global CLI instance
cli = EnhancedCLI()

# Convenience functions for backward compatibility
def loading_operation(message: str, success_message: Optional[str] = None):
    return cli.loading_operation(message, success_message)

def progress_operation(description: str, total: Optional[int] = None):
    return cli.progress_operation(description, total)

def operation_header(title: str, subtitle: Optional[str] = None):
    cli.operation_header(title, subtitle)

def success(message: str):
    cli.success(message)

def error(message: str):
    cli.error(message)

def warning(message: str):
    cli.warning(message)