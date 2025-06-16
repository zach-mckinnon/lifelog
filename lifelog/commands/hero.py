# lifelog/commands/hero.py

import typer
from rich.console import Console
from rich.table import Table

from lifelog.utils.db.gamify_repository import (
    _ensure_profile,
    get_unread_notifications,
    list_badges,
    list_skills,
    list_shop_items,
    buy_item,
    add_xp,
    mark_notifications_read,
)
from lifelog.utils.db import safe_query

console = Console()
app = typer.Typer(name="hero", help="🏰 Hero profile, badges, skills & shop")


@app.command("profile")
def profile_cli():
    """
    Show your hero’s level, XP, gold, and unlocked badges.
    """
    p = _ensure_profile()
    console.rule(f"[bold yellow]🛡️  Hero Profile[/bold yellow]")
    console.print(
        f"Level: [green]{p.level}[/green]   XP: [cyan]{p.xp}/100[/cyan]   Gold: [gold1]{p.gold}[/gold1]\n")

    console.print("[bold]Unlocked Badges[/bold]")
    table = Table("Name", "When")
    rows = safe_query(
        "SELECT b.name, pb.awarded_at FROM profile_badges pb "
        "JOIN badges b ON pb.badge_id = b.id WHERE pb.profile_id = ?",
        (p.id,)
    )
    if rows:
        for r in rows:
            table.add_row(r["name"], r["awarded_at"].split("T")[0])
        console.print(table)
    else:
        console.print("  (none yet)")


@app.command("badges")
def badges_cli():
    """
    List all possible badges and indicate which are unlocked.
    """
    p = _ensure_profile()
    console.rule("[bold magenta]🏅 All Badges[/bold magenta]")
    table = Table("Badge", "Description", "Status")
    for b in list_badges():
        unlocked = safe_query(
            "SELECT 1 FROM profile_badges WHERE profile_id=? AND badge_id=?",
            (p.id, b.id)
        )
        status = "[green]✔[/green]" if unlocked else "[dim]–[/dim]"
        table.add_row(b.name, b.description, status)
    console.print(table)


@app.command("skills")
def skills_cli():
    """
    Show all skills and your current level in each.
    """
    console.rule("[bold cyan]🛠️  Skills[/bold cyan]")
    table = Table("Skill", "Description", "Level")
    for sk in list_skills():
        level = safe_query(
            "SELECT level FROM profile_skills ps JOIN skills s ON ps.skill_id=s.id "
            "WHERE ps.profile_id=? AND s.uid=?",
            (_ensure_profile().id, sk.uid)
        )
        lvl = level[0]["level"] if level else 0
        table.add_row(sk.name, sk.description, str(lvl))
    console.print(table)


@app.command("shop")
def shop_cli():
    """
    Browse items you can buy with gold.
    """
    console.rule("[bold green]🏪 Shop[/bold green]")
    table = Table("UID", "Name", "Cost")
    for item in list_shop_items():
        table.add_row(item.uid, item.name, str(item.cost_gold))
    console.print(table)


@app.command("buy")
def buy_cli(uid: str):
    """
    Purchase one unit of <uid> from the shop.
    """
    try:
        inv = buy_item(uid)
    except Exception as e:
        console.print(f"[red]❌ {e}[/red]")
        raise typer.Exit(1)
    console.print(
        f"[green]✅ Bought {uid}! Now have {inv.quantity} in inventory.[/green]")

# Allow manual XP award (for testing/demo)


@app.command("add-xp")
def add_xp_cli(amount: int):
    """
    Add a chunk of XP to your profile (for testing).
    """
    p = add_xp(amount)
    console.print(f"[cyan]Your new XP is {p.xp}/100 at Level {p.level}[/cyan]")


@app.command("notify")
def show_notifications():
    """Show all unread notifications and mark them read."""
    profile = _ensure_profile()
    notes = get_unread_notifications(profile.id)
    if not notes:
        typer.echo("No new notifications.")
        return
    for n in notes:
        typer.echo(f"[{n['created_at']}] {n['message']}")
    mark_notifications_read([n["id"] for n in notes])
