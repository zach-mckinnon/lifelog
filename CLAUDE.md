# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Command Line Interface

**Main entry point:** `llog` (entry point in `lifelog/llog.py`)

### Essential Commands
```bash
# Initial setup (required first)
llog setup

# Core functionality
llog task add "Task description"      # Add tasks
llog time start "Work"                # Start time tracking  
llog track add "Mood"                 # Add custom trackers
llog report summary                   # Daily summary reports

# Multi-device sync
llog api-start --host 0.0.0.0 --port 5000  # Start API server
llog sync                            # Manual sync (client mode)

# Configuration
llog config-edit                     # Interactive config editor
llog backup [output_path]           # Create database backup
```

### Development Commands
```bash
pip install -e .        # Install in development mode
llog setup             # Initialize config and database
llog ui               # Test curses interface (currently disabled)
```

## Architecture Overview

**Lifelog** is a privacy-first CLI productivity tracker built with:
- **CLI Framework:** Typer with Rich for terminal UI
- **Database:** SQLite with repository pattern
- **Sync:** Flask REST API for multi-device sync
- **Config:** TOML-based configuration in `~/.lifelog/`

### Core Directory Structure

- `lifelog/llog.py` - Main CLI entry point with Typer app
- `lifelog/commands/` - Command modules (task, time, track, report, etc.)
- `lifelog/utils/db/` - Database layer with repository pattern
- `lifelog/api/` - Flask REST API for device sync
- `lifelog/config/` - Configuration management (TOML)
- `lifelog/ui_views/` - Terminal UI components (curses-based)

### Data Architecture

**Repository Pattern:** All data access through `*_repository.py` files in `lifelog/utils/db/`:
- `task_repository.py` - Task management
- `time_repository.py` - Time tracking
- `track_repository.py` - Custom tracker metrics
- `report_repository.py` - Analytics and reporting

**Database Schema:** Defined in `lifelog/utils/db/database_manager.py:initialize_schema()`
- All tables include sync fields: `uid` (UUID), `updated_at`, `deleted`
- Repository functions: `get_all_*`, `get_*_by_id`, `add_*`, `update_*`, `delete_*`
- Dataclass models in `lifelog/utils/db/models.py` with exact field matching to DB schema

### Configuration System

**Location:** `~/.lifelog/` directory containing:
- `config.toml` - User settings and preferences
- `lifelog.db` - Main SQLite database  
- `sync_queue.db` - Pending sync operations for client mode
- `hooks/` - Custom automation scripts

**Key config sections:**
- `[categories]` - Task/time categories with descriptions
- `[category_importance]` - Weighting values for priority calculations
- `[api]` - Device pairing and sync credentials

### Multi-Device Sync

**Architecture:** Server/client model using Flask REST API
- **Host device:** Runs `llog api-start` to serve data
- **Client devices:** Queue operations locally, sync when connected
- **Data flow:** All entities have UUID, updated_at timestamps for conflict resolution
- **Security:** Basic device token authentication (not for public internet use)

## Development Patterns

### Adding New Commands
```python
# In lifelog/commands/new_module.py
app = typer.Typer(help="Module description")

@app.command()
def action(arg: str = typer.Argument(..., help="Description")):
    try:
        result = repository.action(data)
        console.print(f"[green]✅ Success[/green]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)

# Register in lifelog/llog.py
app.add_typer(new_module.app, name="new", help="Description")
```

### Database Changes
1. Update schema in `database_manager.py:initialize_schema()`
2. Add dataclass in `models.py` with exact field matching
3. Create/update repository with `*_from_row()` conversion functions
4. Ensure `get_*_fields()` returns all DB columns except 'id'

### Repository Pattern Requirements
- Use `normalize_for_db()` to convert dataclass datetime/enum fields
- Handle sync operations with `queue_sync_operation()` for client mode
- All repositories must implement standard CRUD operations
- Convert DB rows to dataclasses using `*_from_row()` functions

## Testing & Debugging

**No formal test suite present** - manual testing through:
```bash
llog setup                    # Test initialization
llog task add "Test task"     # Test basic functionality
llog api-start --debug       # Debug API server
llog report summary          # Test data aggregation
```

**Common issues:**
- Dataclass field mismatches with DB schema
- Datetime string conversions in `*_from_row()` functions  
- Rich console markup: use `[red]`, `[green]`, `[yellow]` styles
- Sync conflicts: check `should_sync()` before operations

## Security Considerations

**Local-only design:** Not intended for public deployment
- Basic device token auth (not cryptographically secure)
- SQLite database unencrypted
- Designed for single-user, trusted device environments

**Multi-device setup requires:** SSH tunnels, VPN, or private networks for secure remote access.