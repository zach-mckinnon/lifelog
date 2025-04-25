# lifelog/commands/report.py 
from typing import Optional
import typer
import json
from rich import print
from rich.console import Console
from rich.table import Table
from rich.text import Text
from rich.progress import Progress
from datetime import datetime, timedelta
from collections import defaultdict
import statistics
import termplotlib as tpl
from lifelog.config.config_manager import get_habit_file, get_log_file, get_time_file
from lifelog.commands.utils.insight_engine import generate_insights
from utils.report_utils import render_line_chart, render_scatter_plot, correlation_score, render_calendar_heatmap


app = typer.Typer(help="Generate reports and visual summaries of logged data.")
console = Console()

LOG_FILE = get_log_file() 
TIME_FILE = get_time_file()
HABIT_FILE = get_habit_file()

def load_entries():
    if LOG_FILE.exists():
        with open(LOG_FILE, "r") as f:
            return json.load(f)
    return []

def load_time_log():
    if TIME_FILE.exists():
        with open(TIME_FILE, "r") as f:
            return json.load(f).get("history", [])
    return []

def load_habit_log():
    if HABIT_FILE.exists():
        with open(HABIT_FILE, "r") as f:
            return json.load(f).get("log", [])
    return []

def render_trend_chart(metric_name, entries):
    daily_values = defaultdict(list)
    for entry in entries:
        if entry.get("metric") == metric_name:
            ts = datetime.fromisoformat(entry["timestamp"])
            day = ts.strftime("%Y-%m-%d")
            try:
                daily_values[day].append(float(entry["value"]))
            except:
                continue

    dates = sorted(daily_values.keys())
    avg_values = [round(statistics.mean(daily_values[day]), 2) for day in dates]

    fig = tpl.figure()
    fig.plot(list(range(len(avg_values))), avg_values,
             xlabel=Text("Day", style="italic"),
             ylabel=Text(metric_name, style="italic"),
             xticks=[(i, Text(d[-5:], style="bold")) for i, d in enumerate(dates)])
    console.print(fig.get_string())

@app.command("help")
def report_help():
    """
    [bold blue]📊 Available Report Types:[/bold blue]
    """
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Command", style="dim")
    table.add_column("Description")

    table.add_row("trend <metric> [period]", "Line chart of metric over time (day, week, month)")
    table.add_row("compare <metric1> --metric2 <metric2>", "Scatter plot + correlation")
    table.add_row("correlations", "Show top correlations across metrics")
    table.add_row("heatmap <metric|time|habit>", "Calendar-style day-of-week chart")
    table.add_row("outliers <metric>", "Detect highs/lows")
    table.add_row("streaks [--habit]", "Habit streak analysis")
    table.add_row("totals [time|habit|metric]", "Weekly/monthly category totals")
    table.add_row("wellness", "Radar summary of health metrics")
    table.add_row("balance", "Pie chart of life balance")
    table.add_row("insights [--export <FILE>]", "Smart pattern analysis")
    table.add_row("missed-data", "Detect incomplete logs")

    console.print(table)


@app.command()
def time(period: str = typer.Option("week", help="Time range: day, week, month")):
    """
   Show [bold yellow]time tracking totals[/bold yellow] by category.
    """
    entries = load_time_log()
    now = datetime.now()

    if period == "day":
        since = now - timedelta(days=1)
    elif period == "week":
        since = now - timedelta(days=7)
    elif period == "month":
        since = now - timedelta(days=30)
    else:
        console.print("[bold red]Invalid period.[/bold red] Choose from: day, week, month")
        raise typer.Exit()

    totals = defaultdict(float)
    for entry in entries:
        ts = datetime.fromisoformat(entry["start"])
        if ts > since:
            totals[entry["category"]] += entry["duration_minutes"]
    
    console.print(f"\n[bold yellow]🕒 Time Tracking Totals (Last {period}):[/bold yellow]")
    table = Table(show_header=True, header_style="bold yellow")
    table.add_column("Category")
    table.add_column("Total Minutes", justify="right")

    for cat, total in totals.items():
        table.add_row(cat, f"[green]{round(total, 2)}[/green]")

    console.print(table)


@app.command("habits")
def report_habits(period: str = typer.Option("week", help="Time range: day, week, month")):
    """
    Show [bold green]number of completions[/bold green] per habit.
    """
    logs = load_habit_log()
    now = datetime.now()

    if period == "day":
        since = now - timedelta(days=1)
    elif period == "week":
        since = now - timedelta(days=7)
    elif period == "month":
        since = now - timedelta(days=30)
    else:
        console.print("[bold red]Invalid period.[/bold red] Choose from: day, week, month")
        raise typer.Exit()

    counts = defaultdict(int)
    for entry in logs:
        ts = datetime.fromisoformat(entry["timestamp"])
        if ts > since:
            counts[entry["name"]] += 1
    
    console.print(f"\n[bold green]✅ Habit Completion Counts (Last {period}):[/bold green]")
    table = Table(show_header=True, header_style="bold green")
    table.add_column("Habit")
    table.add_column("Completions", justify="right")

    for name, count in counts.items():
        table.add_row(name, f"[cyan]{count}[/cyan]")
    
    console.print(table)

@app.command()
def daily():
    """
    Show a summary report of [bold blue]today's[/bold blue] metric, time tracking, and habit completions.
    """
    now = datetime.now()
    since = now.replace(hour=0, minute=0, second=0, microsecond=0)

    # metric
    entries = [e for e in load_entries() if datetime.fromisoformat(e["timestamp"]) >= since]
    metric_data = defaultdict(list)
    for e in entries:
        try:
            metric_data[e["metric"]].append(float(e["value"]))
        except:
            continue

    console.print(f"\n[bold blue]📊 Metric Summary (Today):[/bold blue]")
    if metric_data:
        for name, values in metric_data.items():
            avg = round(statistics.mean(values), 2)
            console.print(f"- [bold cyan]{name}:[/bold cyan] [green]{avg}[/green]")
    else:
        console.print("[italic]No metric data logged today.[/italic]")

    # Time
    time_entries = [e for e in load_time_log() if datetime.fromisoformat(e["start"]) >= since]
    time_totals = defaultdict(float)
    for e in time_entries:
        time_totals[e["category"]] += e["duration_minutes"]

    console.print(f"\n[bold yellow]🕒 Time Tracking Summary (Today):[/bold yellow]")
    if time_totals:
        for cat, total in time_totals.items():
            console.print(f"- [bold magenta]{cat}:[/bold magenta] [green]{round(total, 2)} minutes[/green]")
    else:
        console.print("[italic]No time tracked today.[/italic]")

    # Habits
    habits = [h for h in load_habit_log() if datetime.fromisoformat(h["timestamp"]) >= since]
    habit_counts = defaultdict(int)
    for h in habits:
        habit_counts[h["name"]] += 1

    console.print(f"\n[bold green]✅ Habits Completed (Today):[/bold green]")
    if habit_counts:
        for name, count in habit_counts.items():
            console.print(f"- [bold blue]{name}:[/bold blue] [cyan]{count} times[/cyan]")
    else:
        console.print("[italic]No habits completed today.[/italic]")

@app.command("trend")
def report_trend(metric: str, period: str = "week"):
    """
    Show a [bold blue]trend chart[/bold blue] for [bold cyan]{metric}[/bold cyan].
    """
    entries = load_entries()
    now = datetime.now()
    since = now - {"day": timedelta(days=1), "week": timedelta(days=7), "month": timedelta(days=30)}.get(period, timedelta(days=7))
    filtered = [e for e in entries if e.get("metric") == metric and datetime.fromisoformat(e["timestamp"]) > since]

    if not filtered:
        console.print(f"[italic]No data found for [bold blue]{metric}[/bold blue] in the last [bold green]{period}[/bold green].[/italic]")
        return

    by_day = defaultdict(list)
    for entry in filtered:
        day = datetime.fromisoformat(entry["timestamp"]).strftime("%Y-%m-%d")
        try:
            by_day[day].append(float(entry["value"]))
        except:
            continue

    dates = sorted(by_day)
    values = [round(statistics.mean(by_day[d]), 2) for d in dates]

    console.print(f"\n[bold blue]📈 Trend of '{metric}' over the last {period}:[/bold blue]")
    render_line_chart(dates, values, label=metric)

@app.command("compare")
def report_compare(
    metric1: str = typer.Argument(..., help="The primary metric."),
    metric2: str = typer.Option(..., "--metric2", help="Metric to compare against.")
):
    """
    Compare [bold cyan]{metric1}[/bold cyan] against [bold magenta]{metric2}[/bold magenta] with a scatter plot.
    """
    entries = load_entries()
    data = defaultdict(dict)

    for e in entries:
        day = datetime.fromisoformat(e["timestamp"]).strftime("%Y-%m-%d")
        try:
            if e["metric"] == metric1:
                data[day]["x"] = float(e["value"])
            elif e["metric"] == metric2:
                data[day]["y"] = float(e["value"])
        except:
            continue

    valid = [d for d in data.values() if "x" in d and "y" in d]
    x_vals = [d["x"] for d in valid]
    y_vals = [d["y"] for d in valid]

    if not valid:
        console.print(f"[italic]No overlapping data found for [bold cyan]{metric1}[/bold cyan] and [bold magenta]{metric2}[/bold magenta].[/italic]")
        return

    console.print(f"\n[bold blue]📊 Comparison of '{metric1}' vs '{metric2}':[/bold blue]")
    render_scatter_plot(x_vals, y_vals, xlabel=metric1, ylabel=metric2)
    correlation = correlation_score(x_vals, y_vals)
    color = "green" if abs(correlation) < 0.3 else ("yellow" if abs(correlation) < 0.7 else "red")
    console.print(f"\n📈 Correlation Score: [{color}]{correlation:.2f}[/{color}]")

@app.command("heatmap")
def report_heatmap(kind: str):
    """
    Show a [bold purple]heatmap[/bold purple] for [bold blue]{kind}[/bold blue] (metric, time, or habit).
    """
    if kind == "time":
        entries = load_time_log()
        date_map = defaultdict(float)
        for e in entries:
            day = e["start"].split("T")[0]
            date_map[day] += e["duration_minutes"]
        title = "[bold purple]Time Tracking Heatmap[/bold purple]"
    elif kind == "habit":
        logs = load_habit_log()
        date_map = defaultdict(int)
        for e in logs:
            day = e["timestamp"].split("T")[0]
            date_map[day] += 1
        title = "[bold purple]Habit Completion Heatmap[/bold purple]"
    else:  # assume it's a metric name
        entries = load_entries()
        date_map = defaultdict(float)
        for e in entries:
            if e["metric"] == kind:
                day = e["timestamp"].split("T")[0]
                try:
                    date_map[day] += float(e["value"])
                except:
                    continue
        title = f"[bold purple]{kind.capitalize()} Heatmap[/bold purple]"

    console.print(f"\n{title}:")
    render_calendar_heatmap(date_map)


@app.command("insights")
def report_insights(export: Optional[str] = typer.Option(None, help="Export insights to JSON file")):
    """
    Run automated analysis to discover [bold gold]hidden correlations[/bold gold] in your life metrics.
    """

    console.print("[bold blue]🔍 Scanning your life data for hidden patterns...[/bold blue]")

    with Progress(transient=True) as progress:
        task = progress.add_task("[cyan]Crunching numbers...", total=100)
        for _ in range(100):
            import time
            time.sleep(0.01)
            progress.advance(task)

    insights = generate_insights()

    console.print("\n[bold gold]✨ Top Insights:[/bold gold]")
    if insights:
        table = Table(show_header=True, header_style="bold gold")
        table.add_column("#")
        table.add_column("Insight")
        table.add_column("Pearson", justify="right")
        table.add_column("Spearman", justify="right")

        for i, insight in enumerate(insights, 1):
            pearson = f"[green]{insight['correlation']['pearson']:.2f}[/green]" if insight['correlation']['pearson'] > 0 else f"[red]{insight['correlation']['pearson']:.2f}[/red]"
            spearman = f"[green]{insight['correlation']['spearman']:.2f}[/green]" if insight['correlation']['spearman'] > 0 else f"[red]{insight['correlation']['spearman']:.2f}[/red]"
            table.add_row(str(i), insight['note'], pearson, spearman)
        console.print(table)
    else:
        console.print("[italic]No significant insights found.[/italic]")

    if export:
        with open(export, "w") as f:
            json.dump(insights, f, indent=2)
        console.print(f"\n[green]📁 Insights saved to:[/green] [bold]{export}[/bold]")

# Placeholder implementations for the remaining commands
@app.command("correlations")
def report_correlations():
    console.print("[italic]🔬 Correlation analysis not yet implemented. Placeholder command active.[/italic]")

@app.command("outliers")
def report_outliers(metric: str):
    console.print(f"[italic]📍 Outlier detection for [bold]{metric}[/bold] is not implemented yet.[/italic]")

@app.command("streaks")
def report_streaks(habit: Optional[str] = typer.Option(None, help="Specific habit name")):
    console.print("[italic]🔥 Habit streak analysis coming soon.[/italic]")

@app.command("totals")
def report_totals(kind: str = typer.Argument(..., help="Type: time, habit, or metric")):
    console.print(f"[italic]📊 Totals report for [bold]{kind}[/bold] is not implemented yet.[/italic]")

@app.command("wellness")
def report_wellness():
    console.print("[italic]⚕️ Wellness radar chart is a placeholder implementation.[/italic]")

@app.command("balance")
def report_balance():
    console.print("[italic]⚖️ Life balance pie chart not yet implemented.[/italic]")

    
def load_data():
    metrics = []
    time_logs = []
    habit_logs = []

    log_file = get_log_file()
    time_file = get_time_file()
    habit_file = get_habit_file()

    if log_file.exists():
        with open(log_file, "r") as f:
            metrics = json.load(f)

    if time_file.exists():
        with open(time_file, "r") as f:
            time_logs = json.load(f).get("history", [])

    if habit_file.exists():
        with open(habit_file, "r") as f:
            habit_logs = json.load(f).get("log", [])

    return metrics, time_logs, habit_logs


def get_date_set(entries, date_key="timestamp"):
    return {datetime.fromisoformat(entry[date_key]).date() for entry in entries}


def detect_missed_data(days=7):
    today = datetime.now().date()
    recent_days = [(today - timedelta(days=i)) for i in range(days)]

    metrics, time_logs, habit_logs = load_data()

    metric_days = get_date_set(metrics)
    time_days = get_date_set(time_logs, "start")
    habit_days = get_date_set(habit_logs)

    summary = {
        "expected_days": days,
        "metric": [],
        "time": [],
        "habit": [],
    }

    for day in recent_days:
        if day not in metric_days:
            summary["metric"].append(str(day))
        if day not in time_days:
            summary["time"].append(str(day))
        if day not in habit_days:
            summary["habit"].append(str(day))

    return summary


def print_missed_data_report(summary):
    
    total_days = summary["expected_days"]

    def confidence(missed):
        return f"{round((total_days - len(missed)) / total_days * 100, 1)}%"

    console.print("\n[bold red]📉 Missed Data Report[/bold red]", style="bold underline")

    for category in ["metric", "time", "habit"]:
        missed = summary[category]
        logged_days = total_days - len(missed)
        conf = confidence(missed)

        table = Table(title=f"{category.capitalize()} Logs")
        table.add_column("Status", justify="center", style="bold")
        table.add_column("Details", style="dim")

        table.add_row("Logged", f"{logged_days} / {total_days} days")
        table.add_row("Confidence", conf)

        if missed:
            missed_days = ", ".join(missed)
            table.add_row("Missed On", missed_days)
        else:
            table.add_row("Missed On", "[green]No missed days![/green]")

        console.print(table)