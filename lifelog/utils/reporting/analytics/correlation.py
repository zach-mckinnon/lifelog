# lifelog.utils/reporting/analytics/correlation.py
'''
Lifelog CLI - Correlation Analysis Module
This module provides functionality to analyze correlations between different trackers over a specified period.
It includes functions to generate insights based on correlation scores, display the top correlated pairs of metrics, and export the results to CSV or JSON files.
It is designed to help users identify relationships between their tracked metrics, providing valuable feedback for self-improvement and habit tracking.
'''


from datetime import datetime, timedelta
import csv
import json
from rich.console import Console
# Insight engine functionality removed
from lifelog.utils.reporting.analytics.report_utils import render_scatter_plot
from lifelog.utils.shared_utils import now_utc

console = Console()


def report_correlation(since: str = "30d", top_n: int = 5, export: str = None):
    """
    🔍 Correlation analysis between trackers over the specified period.

    since: time window (e.g. "30d", "7d")
    top_n: number of top correlated pairs to show
    export: optional path to export JSON or CSV
    """
    # 1. Parse the "since" argument and set the cutoff date
    # 2. Generate insights using the insight_engine
    cutoff = _parse_since(since)
    console.print(
        f"[bold]Correlation Analysis:[/] since {cutoff.date().isoformat()} (showing top {top_n})")

    # Insight functionality removed - return empty list
    insights = []
    top_insights = []

   # 3. Display the top correlated pairs of metrics
    console.print("\n[bold]Top Correlated Pairs:[/]\n")
    for idx, ins in enumerate(top_insights, start=1):
        m1, m2 = ins['metrics']
        pearson = ins['correlation']['pearson']
        spearman = ins['correlation']['spearman']
        trend = ins.get('trend', '')
        note = ins.get('note', '')
        console.print(
            f"{idx}. [bold]{m1} ↔ {m2}[/bold]: Pearson={pearson}, Spearman={spearman} ({trend})")
        console.print(f"   {note}\n")

        # Optional scatter plot
        # (for brevity, scatter plotted only for first pair)
        if idx == 1:
            # Fetch series data from insight_engine.daily_averages
            # using generate_insights internals (not shown here)
            # Placeholder: skip plotting actual values
            console.print(
                "[yellow]Skipping scatter plot for brevity. (Enable this in future for detailed correlation visuals.)[/yellow]")

    # 4. Export if requested
    if export:
        _export_insights(top_insights, export)


# Helper function to parse the "since" argument
# and convert it to a datetime object.
def _parse_since(s: str) -> datetime:
    now = now_utc()
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


# Helper function to export insights to a file in JSON or CSV format.
# It takes a list of insights and a file path as input.
def _export_insights(insights: list[dict], filepath: str):
    ext = filepath.split('.')[-1].lower()
    if ext == 'csv':
        with open(filepath, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['metric1', 'metric2', 'pearson',
                            'spearman', 'trend', 'note'])
            for ins in insights:
                m1, m2 = ins['metrics']
                c = ins['correlation']
                writer.writerow([m1, m2, c['pearson'], c['spearman'], ins.get(
                    'trend', ''), ins.get('note', '')])
    elif ext == 'json':
        with open(filepath, 'w') as f:
            json.dump(insights, f, indent=2)
    console.print(f"[green]Exported correlation report to {filepath}[/green]")
