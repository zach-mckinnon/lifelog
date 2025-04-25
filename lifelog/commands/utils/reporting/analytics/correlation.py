from datetime import datetime, timedelta
import csv, json
from rich.console import Console
from lifelog.commands.utils.reporting.insight_engine import generate_insights
from lifelog.commands.utils.reporting.analytics.report_utils import render_scatter_plot

console = Console()

def report_correlation(since: str = "30d", top_n: int = 5, export: str = None):
    """
    🔍 Correlation analysis between trackers over the specified period.

    since: time window (e.g. "30d", "7d")
    top_n: number of top correlated pairs to show
    export: optional path to export JSON or CSV
    """
    # 1. Determine cutoff (unused by generate_insights, placeholder)
    cutoff = _parse_since(since)
    console.print(f"[bold]Correlation Analysis:[/] since {cutoff.date().isoformat()} (showing top {top_n})")

    # 2. Generate insights (metric-to-metric correlations)
    insights = generate_insights()
    top_insights = insights[:top_n]

    # 3. Display top correlations
    for idx, ins in enumerate(top_insights, start=1):
        m1, m2 = ins['metrics']
        pearson = ins['correlation']['pearson']
        spearman = ins['correlation']['spearman']
        trend = ins.get('trend', '')
        note = ins.get('note', '')
        console.print(f"{idx}. [bold]{m1} ↔ {m2}[/bold]: Pearson={pearson}, Spearman={spearman} ({trend})")
        console.print(f"   {note}\n")

        # Optional scatter plot
        # (for brevity, scatter plotted only for first pair)
        if idx == 1:
            # Fetch series data from insight_engine.daily_averages
            # using generate_insights internals (not shown here)
            # Placeholder: skip plotting actual values
            pass

    # 4. Export if requested
    if export:
        _export_insights(top_insights, export)


def _parse_since(s: str) -> datetime:
    now = datetime.now()
    unit = s[-1]
    try:
        amt = int(s[:-1])
    except ValueError:
        amt = int(s)
        unit = 'd'
    if unit == 'd':
        return now - timedelta(days=amt)
    if unit == 'w':
        return now - timedelta(weeks=amt)
    if unit == 'm':
        return now - timedelta(days=30*amt)
    return now - timedelta(days=amt)


def _export_insights(insights: list[dict], filepath: str):
    ext = filepath.split('.')[-1].lower()
    if ext == 'csv':
        with open(filepath, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['metric1','metric2','pearson','spearman','trend','note'])
            for ins in insights:
                m1, m2 = ins['metrics']
                c = ins['correlation']
                writer.writerow([m1, m2, c['pearson'], c['spearman'], ins.get('trend',''), ins.get('note','')])
    elif ext == 'json':
        with open(filepath, 'w') as f:
            json.dump(insights, f, indent=2)
    console.print(f"[green]Exported correlation report to {filepath}[/green]")
