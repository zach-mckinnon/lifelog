# Lifelog CLI Copilot Instructions

## Architecture Overview

Lifelog is a privacy-first CLI productivity tracker for neurodivergent users with multi-device sync capabilities. Built with Python/Typer for CLI, Rich for UI, SQLite for storage, and Flask for API sync.

### Core Components

- **CLI Entry Point**: `lifelog/llog.py` - Main Typer app with subcommands
- **Commands**: `lifelog/commands/` - Task, time, tracker, report, API modules
- **Database**: `lifelog/utils/db/` - Repository pattern with sync capabilities
- **UI**: `lifelog/ui.py` + `ui_views/` - Curses-based terminal interface
- **Config**: `lifelog/config/` - TOML-based configuration management
- **API**: `lifelog/api/` - Flask REST API for device pairing/sync

## Data Model Architecture

### Repository Pattern

All data access uses repositories (`*_repository.py`) with consistent patterns:

```python
# Create with dataclass -> repository handles DB conversion
tracker = Tracker(id=None, title="Mood", type="int", created=now())
new_tracker = track_repository.add_tracker(tracker)

# All repositories have: get_all_*, get_*_by_id, add_*, update_*, delete_*
```

### Sync-Aware Data Flow

- **Direct DB Mode**: Local-only operations
- **Client Mode**: Queue operations for server sync via `queue_sync_operation()`
- All entities have `uid` (UUID), `updated_at`, `deleted` fields for sync
- Use `normalize_for_db()` to convert dataclass datetime/enum fields to DB format

### Model Consistency Requirements

- Dataclass fields MUST match database schema exactly
- Use `*_from_row()` functions to convert DB rows to dataclasses
- `get_*_fields()` functions MUST return all DB columns except 'id'
- Handle Optional[datetime] vs string conversions carefully

## Key Development Patterns

### Command Structure

```python
# commands/module_name.py
app = typer.Typer(help="Module description")

@app.command()
def action(
    required_arg: str = typer.Argument(..., help="Description"),
    optional_flag: bool = typer.Option(False, help="Description")
):
    # Always include error handling with Rich console
    try:
        result = repository.action(data)
        console.print(f"[green]✅ Success message[/green]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(code=1)
```

### Database Schema Evolution

- Schema defined in `database_manager.py:initialize_schema()`
- Complex goal system: base `goals` table + type-specific tables (`goal_sum`, `goal_range`, etc.)
- Gamification tables: `user_profiles`, `badges`, `skills`, `shop_items`
- All tables include sync fields: `uid`, `updated_at`, `deleted`

## Critical Workflows

### Setup & First Run

```bash
llog setup  # Runs setup wizard, creates config, initializes DB
```

### Multi-Device Sync

```bash
# Host device
llog api-start --host 0.0.0.0 --port 5000

# Client device setup
llog setup  # Choose client mode, provide host URL
```

### Docker Deployment

```bash
llog docker up    # Uses generated docker-compose.yml
llog docker logs  # View container logs
```

## Configuration System

### Config Location: `~/.lifelog/`

- `config.toml` - User configuration
- `lifelog.db` - SQLite database
- `sync_queue.db` - Pending sync operations
- `hooks/` - Custom automation scripts

### Key Config Sections

```toml
[categories]  # Task/time categories with descriptions
[category_importance]  # Weighting for priority calculation
[api]  # Encrypted sync credentials
[cron.*]  # Scheduled operations
```

## Testing & Debugging

### Development Setup

```bash
pip install -e .  # Install in development mode
llog setup        # Initialize config and DB
```

### Common Issues

- **Field mismatches**: Ensure dataclass fields match DB schema in `get_*_fields()`
- **Datetime handling**: Use `datetime.fromisoformat()` in `*_from_row()` functions
- **Sync conflicts**: Check `should_sync()` before sync operations
- **Rich markup**: Use `[red]`, `[green]`, `[yellow]` not `[error]` styles

### Debug Commands

```bash
llog ui                    # Test curses interface
llog api-start --debug    # Debug mode API server
llog report summary       # Test data aggregation
```

## Extension Points

### Hooks System

Drop Python scripts in `~/.lifelog/hooks/` - called on events:

```python
# hooks/task_completed.py
def run(event_type, data):
    # Custom automation when tasks complete
```

### Goal Types

Add new goal types by:

1. Adding dataclass in `models.py`
2. Adding table in `database_manager.py`
3. Adding case in `goal_from_row()` function
4. Updating `create_goal_interactive()` in `goal_util.py`

### API Extensions

Add endpoints in `api/*_api.py` following existing patterns with `@require_device_token` and proper error handling.
