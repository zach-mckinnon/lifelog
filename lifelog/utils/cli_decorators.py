# lifelog/utils/cli_decorators.py
"""
Decorators and utilities for enhanced CLI commands with loading states and progress.
"""
import functools
import time
import asyncio
from typing import Callable, Any, Optional, List, Dict
from contextlib import contextmanager

from lifelog.utils.cli_enhanced import cli
from lifelog.utils.pi_optimizer import pi_optimizer
from lifelog.utils.error_handler import handle_db_errors

def with_loading(
    message: str, 
    success_message: Optional[str] = None,
    show_duration: bool = True
):
    """Decorator to add loading state to command functions."""
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()
            
            with cli.loading_operation(message, success_message) as status:
                result = func(*args, **kwargs)
                
                if show_duration:
                    duration = time.time() - start_time
                    if duration > 0.5:  # Only show duration for operations > 0.5s
                        cli.info(f"Completed in {duration:.1f}s")
                
                return result
        return wrapper
    return decorator

def with_progress(description: str, total: Optional[int] = None):
    """Decorator to add progress bar to command functions."""
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            with cli.progress_operation(description, total) as (progress, task):
                # Pass progress objects to the function
                if 'progress_callback' in func.__code__.co_varnames:
                    kwargs['progress_callback'] = lambda advance=1: progress.update(task, advance=advance)
                
                return func(*args, **kwargs)
        return wrapper
    return decorator

def with_operation_header(title: str, subtitle: Optional[str] = None):
    """Decorator to add operation header to commands."""
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            cli.operation_header(title, subtitle)
            return func(*args, **kwargs)
        return wrapper
    return decorator

def with_performance_monitoring(operation_name: str):
    """Decorator to monitor command performance with Pi-specific optimizations."""
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()
            
            # Pre-operation cleanup on Pi
            if pi_optimizer.is_raspberry_pi:
                with cli.thinking("Optimizing for Pi"):
                    pi_optimizer.periodic_cleanup()
            
            try:
                result = func(*args, **kwargs)
                
                # Performance summary
                duration = time.time() - start_time
                if duration > 1.0:  # Show performance info for longer operations
                    settings = pi_optimizer.get_optimized_settings()
                    memory_mb = pi_optimizer.memory_mb
                    
                    perf_data = {
                        "Duration": f"{duration:.2f}s",
                        "System Memory": f"{memory_mb:.0f}MB",
                        "Database Cache": f"{settings['database']['cache_size']} pages"
                    }
                    
                    if pi_optimizer.is_raspberry_pi:
                        perf_data["Platform"] = "Raspberry Pi (Optimized)"
                    
                    cli.display_summary_card(f"{operation_name} Performance", perf_data)
                
                return result
                
            except Exception as e:
                cli.error(f"{operation_name} failed: {str(e)}")
                raise
                
        return wrapper
    return decorator

def interactive_command(
    confirm_message: Optional[str] = None,
    dangerous: bool = False
):
    """Decorator for interactive commands with confirmation."""
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            if confirm_message:
                style = "red" if dangerous else "yellow"
                if not cli.enhanced_confirm(f"[{style}]{confirm_message}[/{style}]"):
                    cli.info("Operation cancelled")
                    return
            
            return func(*args, **kwargs)
        return wrapper
    return decorator

def multi_step_command(steps: List[str]):
    """Decorator for multi-step operations."""
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            total_steps = len(steps)
            cli.operation_header("Multi-Step Operation", f"{total_steps} steps")
            
            # Create a step tracker that the function can use
            step_tracker = {"current": 0, "total": total_steps}
            
            def next_step(message: Optional[str] = None):
                step_tracker["current"] += 1
                step_name = message or steps[step_tracker["current"] - 1]
                cli.step_progress(
                    step_name, 
                    step_tracker["current"], 
                    step_tracker["total"]
                )
            
            # Pass step tracker to function if it accepts it
            if 'step_callback' in func.__code__.co_varnames:
                kwargs['step_callback'] = next_step
            
            return func(*args, **kwargs)
        return wrapper
    return decorator

class CommandContext:
    """Context object for command execution."""
    
    def __init__(self):
        self.cli = cli
        self.start_time = time.time()
        self.operation_count = 0
    
    def elapsed_time(self) -> float:
        return time.time() - self.start_time
    
    def log_operation(self, name: str):
        self.operation_count += 1
        cli.info(f"Operation {self.operation_count}: {name}")

def with_context(func: Callable) -> Callable:
    """Decorator to provide command context."""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        context = CommandContext()
        kwargs['ctx'] = context
        return func(*args, **kwargs)
    return wrapper

def database_operation(operation_name: str, show_performance: bool = True):
    """Decorator specifically for database operations."""
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        @handle_db_errors(operation_name)
        def wrapper(*args, **kwargs):
            start_time = time.time()
            
            with cli.loading_operation(f"🗄️ {operation_name}"):
                result = func(*args, **kwargs)
            
            if show_performance:
                duration = time.time() - start_time
                if duration > 0.1:  # Show timing for operations > 100ms
                    cli.info(f"Database operation completed in {duration*1000:.0f}ms")
            
            return result
        return wrapper
    return decorator

@contextmanager
def command_section(title: str):
    """Context manager for command sections."""
    cli.section_divider(title)
    try:
        yield
    finally:
        cli.section_divider()

def batch_operation(items: List[Any], operation_name: str):
    """Decorator for batch operations with progress tracking."""
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            total_items = len(items)
            
            if total_items == 0:
                cli.warning(f"No items to process for {operation_name}")
                return []
            
            cli.operation_header(f"Batch {operation_name}", f"Processing {total_items} items")
            
            results = []
            with cli.progress_operation(operation_name, total_items) as (progress, task):
                for i, item in enumerate(items):
                    try:
                        result = func(item, *args, **kwargs)
                        results.append(result)
                        progress.update(task, advance=1)
                        
                        # Brief pause for visual feedback on fast operations
                        if total_items > 5:
                            time.sleep(0.05)
                            
                    except Exception as e:
                        cli.warning(f"Failed to process item {i+1}: {e}")
                        results.append(None)
                        progress.update(task, advance=1)
            
            successful = len([r for r in results if r is not None])
            cli.success(f"Batch operation completed: {successful}/{total_items} successful")
            
            return results
        return wrapper
    return decorator