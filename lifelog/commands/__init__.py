# Add to commands/__init__.py
from rich.console import Console
import typer

import lifelog.app as app


sync_app = typer.Typer(help="Synchronization commands")
console = Console()


@sync_app.command("to-server")
def sync_to_server():
    """Push local data to server"""
    console.print("[green]Syncing data to server...[/green]")
    # Implementation would go here
    console.print("[green]✓ Sync complete![/green]")


@sync_app.command("from-server")
def sync_from_server():
    """Pull data from server"""
    console.print("[green]Fetching data from server...[/green]")
    # Implementation would go here
    console.print("[green]✓ Sync complete![/green]")


# Add to main app
app.add_typer(sync_app, name="sync", help="Data synchronization commands")
