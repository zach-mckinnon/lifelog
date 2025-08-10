# lifelog/commands/report.py
import toml
import json
from typing import Dict, Any, Optional
from datetime import datetime
import pandas as pd
from enum import Enum
import typer

from rich.table import Table
from rich.console import Console
from rich.panel import Panel

from lifelog.utils.reporting.clinical_insight_engine import generate_clinical_insights
from lifelog.utils.db import environment_repository, task_repository
from lifelog.utils.db import report_repository
from lifelog.utils.db import track_repository, time_repository
import lifelog.config.config_manager as cf
from lifelog.utils.db import track_repository
from lifelog.utils.db.models import Tracker


app = typer.Typer(help="Generate a report for your goal progress.")
console = Console()


class ReportType(str, Enum):
    RANGE_MEASUREMENT = "range_measurement"
    SUM_ACCUMULATION = "sum_accumulation"
    COUNT_FREQUENCY = "count_frequency"
    BOOL_COMPLETION = "bool_completion"
    STREAK_CURRENT = "streak_current"
    DURATION_TIME = "duration_time"
    MILESTONE_PROGRESS = "milestone_progress"
    REDUCTION_TREND = "reduction_trend"
    PERCENTAGE_PROGRESS = "percentage_progress"
    REPLACEMENT_RATIO = "replacement_ratio"
    UNKNOWN = "unknown"


def generate_goal_report(tracker: Tracker) -> Dict[str, Any]:
    """
    Generate a structured goal progress report for a given Tracker instance.
    Pulls entries and goals from SQL.
    """
    # Fetch goals and entries via repository
    goals = track_repository.get_goals_for_tracker(tracker.id)
    entries = track_repository.get_entries_for_tracker(tracker.id)

    # Convert list of TrackerEntry to DataFrame via dicts
    if entries:
        entry_dicts = [e.to_dict() for e in entries]
        df = pd.DataFrame(entry_dicts)
    else:
        df = pd.DataFrame(
            columns=["id", "tracker_id", "timestamp", "value", "uid"])

    # Handle empty DataFrame
    if df.empty:
        return {
            "report_type": "empty",
            "status": "This tracker is ready for your first entry! 📝",
            "completed": False,
            "display_format": {
                "primary": "-",
                "secondary": "-",
                "tertiary": "-"
            },
            "metrics": {}
        }

    if not goals:
        return {
            "report_type": "no_goal",
            "status": "No goal defined.",
            "completed": False,
            "display_format": {
                "primary": "-",
                "secondary": "-",
                "tertiary": "-"
            },
            "metrics": {}
        }

    # Use first goal for now
    goal = goals[0]
    goal_id = goal.id
    kind = goal.kind  # attribute

    # Dispatch handlers
    # Use the new get_goal_details or named wrappers
    if kind == "range":
        details = track_repository.get_goal_range(goal_id)
        return _report_range(tracker, goal, details, df)
    if kind == "sum":
        details = track_repository.get_goal_sum(goal_id)
        return _report_sum(tracker, goal, details, df)
    if kind == "count":
        details = track_repository.get_goal_count(goal_id)
        return _report_count(tracker, goal, details, df)
    if kind == "bool":
        # bool goals often have no detail fields; can pass empty details dict
        return _report_bool(tracker, goal, {}, df)
    if kind == "streak":
        details = track_repository.get_goal_streak(goal_id)
        return _report_streak(tracker, goal, details, df)
    if kind == "duration":
        details = track_repository.get_goal_duration(goal_id)
        return _report_duration(tracker, goal, details, df)
    if kind == "milestone":
        details = track_repository.get_goal_milestone(goal_id)
        return _report_milestone(tracker, goal, details, df)
    if kind == "reduction":
        details = track_repository.get_goal_reduction(goal_id)
        return _report_reduction(tracker, goal, details, df)
    if kind == "percentage":
        details = track_repository.get_goal_percentage(goal_id)
        return _report_percentage(tracker, goal, details, df)
    if kind == "replacement":
        details = track_repository.get_goal_replacement(goal_id)
        return _report_replacement(tracker, goal, details, df)

    # Unknown kind
    return _empty_report(f"Unknown goal kind: {kind}")


def _empty_report(status):
    return {
        "report_type": "empty",
        "status": status,
        "completed": False,
        "display_format": {
            "primary": "-",
            "secondary": "-",
            "tertiary": "-"
        },
        "metrics": {}
    }


# Enhanced reporting commands with comprehensive analytics

@app.command("summary")
def comprehensive_summary(
    days: int = typer.Option(
        7, "--days", "-d", help="Number of days to analyze"),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Show detailed breakdown")
):
    """📊 Generate comprehensive productivity summary with insights and recommendations."""
    from lifelog.utils.reporting.comprehensive_reports import PersonalAnalytics, create_ascii_chart
    from rich.panel import Panel
    from rich.columns import Columns

    console.print(
        f"[bold cyan]📊 Personal Analytics Summary - Last {days} Days[/bold cyan]\n")

    analytics = PersonalAnalytics(fallback_local=True)
    insights = analytics.generate_productivity_insights(days)

    # Task Insights
    task_insights = insights.get('task_insights', {})
    if 'error' not in task_insights:
        task_panel = Panel(
            f"Tasks Created: {task_insights.get('recent_tasks', 0)}\n"
            f"Completed: {task_insights.get('completed_tasks', 0)}\n"
            f"Completion Rate: {task_insights.get('completion_rate', 0)}%\n"
            f"Overdue: {task_insights.get('overdue_tasks', 0)}\n"
            f"Avg/Day: {task_insights.get('avg_tasks_per_day', 0)}",
            title="📋 Tasks",
            border_style="blue"
        )
    else:
        task_panel = Panel(
            f"❌ {task_insights['error']}", title="📋 Tasks", border_style="red")

    # Time Insights
    time_insights = insights.get('time_insights', {})
    if 'error' not in time_insights:
        time_panel = Panel(
            f"Total Time: {time_insights.get('total_time_hours', 0):.1f}h\n"
            f"Daily Average: {time_insights.get('avg_daily_hours', 0):.1f}h\n"
            f"Categories: {time_insights.get('category_count', 0)}\n"
            f"Most Productive: {time_insights.get('top_categories', [{}])[0].get('category', 'N/A') if time_insights.get('top_categories') else 'N/A'}",
            title="⏱️ Time Tracking",
            border_style="green"
        )
    else:
        time_panel = Panel(
            f"❌ {time_insights['error']}", title="⏱️ Time Tracking", border_style="red")

    # Tracker Insights
    tracker_insights = insights.get('tracker_insights', {})
    if 'error' not in tracker_insights:
        tracker_panel = Panel(
            f"Total Entries: {tracker_insights.get('total_entries', 0)}\n"
            f"Active Trackers: {tracker_insights.get('unique_trackers', 0)}\n"
            f"Entries/Day: {tracker_insights.get('avg_entries_per_day', 0)}\n"
            f"Consistency: {'Good' if tracker_insights.get('unique_trackers', 0) > 0 else 'Low'}",
            title="📊 Trackers",
            border_style="yellow"
        )
    else:
        tracker_panel = Panel(
            f"❌ {tracker_insights['error']}", title="📊 Trackers", border_style="red")

    # Display summary panels
    console.print(Columns([task_panel, time_panel, tracker_panel]))

    # Show recommendations
    recommendations = insights.get('recommendations', [])
    if recommendations:
        console.print(
            "\n[bold green]💡 Personalized Recommendations:[/bold green]")
        for i, rec in enumerate(recommendations[:5], 1):  # Limit to top 5
            console.print(f"  {i}. {rec}")

    # Verbose details
    if verbose:
        console.print("\n[bold cyan]📈 Detailed Breakdown:[/bold cyan]")

        # Category breakdown for tasks
        if 'error' not in task_insights:
            category_stats = task_insights.get('category_breakdown', {})
            if category_stats:
                console.print("\n[bold]Task Categories:[/bold]")
                for cat, stats in category_stats.items():
                    completion = (stats['completed'] / stats['total']
                                  * 100) if stats['total'] > 0 else 0
                    console.print(
                        f"  • {cat}: {stats['completed']}/{stats['total']} ({completion:.0f}%)")

        # Time breakdown
        if 'error' not in time_insights:
            top_categories = time_insights.get('top_categories', [])
            if top_categories:
                console.print("\n[bold]Time Categories:[/bold]")
                chart_data = [(cat['category'], cat['duration_minutes'])
                              for cat in top_categories[:5]]
                chart = create_ascii_chart(
                    chart_data, "Time Distribution (minutes)", 30)
                console.print(f"[cyan]{chart}[/cyan]")

        # Tracker details
        if 'error' not in tracker_insights:
            tracker_stats = tracker_insights.get('tracker_stats', {})
            if tracker_stats:
                console.print("\n[bold]Tracker Statistics:[/bold]")
                for name, stats in list(tracker_stats.items())[:5]:  # Top 5
                    trend_emoji = {"increasing": "📈", "decreasing": "📉", "stable": "➡️"}.get(
                        stats['trend'], "❓")
                    console.print(
                        f"  • {name}: Avg {stats['avg_value']:.1f} {trend_emoji} ({stats['entries']} entries)")


@app.command("trackers")
def tracker_report(
    days: int = typer.Option(
        7, "--days", "-d", help="Number of days to analyze"),
    tracker: Optional[str] = typer.Option(
        None, "--tracker", "-t", help="Focus on specific tracker")
):
    """📊 Detailed tracker analysis with trends and patterns."""
    from lifelog.utils.reporting.comprehensive_reports import PersonalAnalytics, create_ascii_chart

    console.print(
        f"[bold cyan]📊 Tracker Analysis - Last {days} Days[/bold cyan]\n")

    analytics = PersonalAnalytics(fallback_local=True)
    insights = analytics.generate_productivity_insights(days)
    tracker_insights = insights.get('tracker_insights', {})

    if 'error' in tracker_insights:
        console.print(f"[red]❌ {tracker_insights['error']}[/red]")
        return

    tracker_stats = tracker_insights.get('tracker_stats', {})

    if not tracker_stats:
        console.print(
            "[yellow]⚠️ No tracker data found for the specified period.[/yellow]")
        return

    # Filter to specific tracker if requested
    if tracker:
        matching_trackers = {
            k: v for k, v in tracker_stats.items() if tracker.lower() in k.lower()}
        if not matching_trackers:
            console.print(
                f"[yellow]⚠️ No trackers found matching '{tracker}'[/yellow]")
            return
        tracker_stats = matching_trackers

    # Display detailed tracker information
    for name, stats in tracker_stats.items():
        trend_emoji = {"increasing": "📈", "decreasing": "📉",
                       "stable": "➡️"}.get(stats['trend'], "❓")
        consistency_emoji = "🎯" if stats['consistency_score'] > 0.7 else "⚡" if stats['consistency_score'] > 0.4 else "📊"

        panel_content = (
            f"Entries: {stats['entries']}\n"
            f"Average: {stats['avg_value']:.2f}\n"
            f"Range: {stats['min_value']:.1f} - {stats['max_value']:.1f}\n"
            f"Trend: {stats['trend'].title()} {trend_emoji}\n"
            f"Consistency: {stats['consistency_score']:.2f} {consistency_emoji}\n"
            f"Std Dev: {stats['std_dev']:.2f}"
        )

        console.print(
            Panel(panel_content, title=f"📊 {name}", border_style="cyan"))


@app.command("time")
def time_report(
    days: int = typer.Option(
        7, "--days", "-d", help="Number of days to analyze"),
    chart: bool = typer.Option(False, "--chart", "-c", help="Show ASCII chart")
):
    """⏱️ Time tracking analysis with productivity insights."""
    from lifelog.utils.reporting.comprehensive_reports import PersonalAnalytics, create_ascii_chart
    from lifelog.utils.db.report_repository import get_time_summary

    console.print(
        f"[bold cyan]⏱️ Time Tracking Analysis - Last {days} Days[/bold cyan]\n")

    analytics = PersonalAnalytics(fallback_local=True)
    insights = analytics.generate_productivity_insights(days)
    time_insights = insights.get('time_insights', {})

    if 'error' in time_insights:
        console.print(f"[red]❌ {time_insights['error']}[/red]")
        return

    # Summary metrics
    total_hours = time_insights.get('total_time_hours', 0)
    avg_daily = time_insights.get('avg_daily_hours', 0)
    top_categories = time_insights.get('top_categories', [])

    console.print(f"[bold]📈 Summary:[/bold]")
    console.print(f"  Total Time Tracked: {total_hours:.1f} hours")
    console.print(f"  Daily Average: {avg_daily:.1f} hours")
    console.print(
        f"  Active Categories: {time_insights.get('category_count', 0)}")

    if top_categories:
        console.print(f"\n[bold]🏆 Top Categories:[/bold]")

        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("Category", style="cyan")
        table.add_column("Time (hours)", justify="right", style="green")
        table.add_column("% of Total", justify="right", style="yellow")

        total_minutes = sum(cat['duration_minutes'] for cat in top_categories)

        for cat in top_categories:
            hours = cat['duration_minutes'] / 60
            percentage = (cat['duration_minutes'] /
                          total_minutes * 100) if total_minutes > 0 else 0

            # Handle nan/null category names
            category_name = cat['category']
            if pd.isna(category_name) or category_name is None:
                category_name = "Uncategorized"

            table.add_row(
                str(category_name),
                f"{hours:.1f}",
                f"{percentage:.1f}%"
            )

        console.print(table)

        # ASCII Chart if requested
        if chart and len(top_categories) > 1:
            console.print(f"\n[bold]📊 Visual Distribution:[/bold]")
            chart_data = []
            for cat in top_categories[:8]:
                # Handle nan/null category names for chart
                category_name = cat['category']
                if pd.isna(category_name) or category_name is None:
                    category_name = "Uncategorized"
                chart_data.append(
                    (str(category_name), cat['duration_minutes']/60))

            ascii_chart = create_ascii_chart(
                chart_data, "Time Distribution (hours)", 40)
            console.print(f"[cyan]{ascii_chart}[/cyan]")


@app.command("goals")
def goals_report(
    tracker_name: Optional[str] = typer.Option(
        None, "--tracker", "-t", help="Focus on specific tracker")
):
    """🎯 Goal progress analysis with achievement insights."""
    console.print("[bold cyan]🎯 Goal Progress Analysis[/bold cyan]\n")

    try:
        # Get all trackers with goals
        trackers = track_repository.get_all_trackers()

        if not trackers:
            console.print("[yellow]⚠️ No trackers found.[/yellow]")
            return

        # Filter by tracker name if specified
        if tracker_name:
            trackers = [t for t in trackers if tracker_name.lower()
                        in t.title.lower()]
            if not trackers:
                console.print(
                    f"[yellow]⚠️ No trackers found matching '{tracker_name}'[/yellow]")
                return

        goals_found = False

        for tracker in trackers:
            goals = track_repository.get_goals_for_tracker(tracker.id)

            if goals:
                goals_found = True
                console.print(
                    f"[bold]📊 {tracker.title}[/bold] ({tracker.category or 'uncategorized'})")

                for goal in goals:
                    # Generate goal-specific report
                    goal_report = generate_goal_report(tracker)

                    if goal_report and goal_report.get('current_status'):
                        status = goal_report['current_status']
                        progress_emoji = "🎯" if status.get(
                            'on_track', False) else "⚠️"

                        console.print(
                            f"  {progress_emoji} {goal.kind.value.title()} Goal:")
                        console.print(
                            f"    Current: {status.get('current_value', 'N/A')}")
                        console.print(
                            f"    Target: {status.get('target_description', 'N/A')}")
                        console.print(
                            f"    Status: {status.get('status_message', 'Unknown')}")
                console.print()

        if not goals_found:
            console.print(
                "[yellow]ℹ️ No goals found. Create goals with 'llog track' command in the UI.[/yellow]")

    except Exception as e:
        console.print(f"[red]❌ Error analyzing goals: {e}[/red]")


@app.command("insights")
def comprehensive_insights(
    days: int = typer.Option(
        30, "--days", "-d", help="Number of days to analyze")
):
    """🧠 Advanced insights with correlations and recommendations."""
    from lifelog.utils.reporting.comprehensive_reports import PersonalAnalytics

    console.print(
        f"[bold cyan]🧠 Personal Analytics Insights - Last {days} Days[/bold cyan]\n")

    analytics = PersonalAnalytics(fallback_local=True)
    insights = analytics.generate_productivity_insights(days)

    # Correlation insights
    corr_insights = insights.get('correlation_insights', {})
    correlations = corr_insights.get('correlations', [])

    if correlations:
        console.print("[bold green]🔗 Discovered Correlations:[/bold green]")
        for corr in correlations:
            strength_emoji = "💪" if corr['strength'] == 'strong' else "👍"
            direction_emoji = "📈" if corr['direction'] == 'positive' else "📉"

            console.print(
                f"  {strength_emoji} {direction_emoji} {corr['tracker']} ↔ Daily Time")
            console.print(
                f"    Correlation: {corr['correlation']:.3f} ({corr['strength']} {corr['direction']})")
        console.print()

    # Recommendations
    recommendations = insights.get('recommendations', [])
    if recommendations:
        console.print(
            "[bold green]💡 Personalized Recommendations:[/bold green]")
        for i, rec in enumerate(recommendations, 1):
            console.print(f"  {i}. {rec}")
        console.print()

    # Detailed analysis summary
    console.print("[bold]📊 Analysis Summary:[/bold]")

    # Tasks
    task_insights = insights.get('task_insights', {})
    if 'error' not in task_insights:
        console.print(
            f"  📋 Tasks: {task_insights.get('completion_rate', 0)}% completion rate")

    # Time
    time_insights = insights.get('time_insights', {})
    if 'error' not in time_insights:
        console.print(
            f"  ⏱️ Time: {time_insights.get('avg_daily_hours', 0):.1f}h daily average")

    # Trackers
    tracker_insights = insights.get('tracker_insights', {})
    if 'error' not in tracker_insights:
        console.print(
            f"  📊 Trackers: {tracker_insights.get('unique_trackers', 0)} active metrics")

    console.print(
        f"\n[dim]Analysis period: {days} days | Generated: {insights.get('generated_at', 'Unknown')}[/dim]")


@app.command("export")
def export_report(
    days: int = typer.Option(
        30, "--days", "-d", help="Number of days to analyze"),
    format: str = typer.Option(
        "json", "--format", "-f", help="Export format: json, csv"),
    output: Optional[str] = typer.Option(
        None, "--output", "-o", help="Output file path")
):
    """💾 Export comprehensive analytics data."""
    from lifelog.utils.reporting.comprehensive_reports import PersonalAnalytics
    import json

    console.print(
        f"[bold cyan]💾 Exporting Analytics Data - Last {days} Days[/bold cyan]\n")

    analytics = PersonalAnalytics(fallback_local=True)
    insights = analytics.generate_productivity_insights(days)

    # Determine output file
    if not output:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output = f"lifelog_analytics_{timestamp}.{format}"

    try:
        if format.lower() == "json":
            with open(output, 'w') as f:
                json.dump(insights, f, indent=2, default=str)
        elif format.lower() == "csv":
            # Export main metrics as CSV
            import pandas as pd

            # Flatten key metrics
            data = []
            task_insights = insights.get('task_insights', {})
            time_insights = insights.get('time_insights', {})
            tracker_insights = insights.get('tracker_insights', {})

            summary_row = {
                'analysis_date': insights.get('generated_at', ''),
                'period_days': days,
                'tasks_created': task_insights.get('recent_tasks', 0),
                'tasks_completed': task_insights.get('completed_tasks', 0),
                'completion_rate': task_insights.get('completion_rate', 0),
                'total_time_hours': time_insights.get('total_time_hours', 0),
                'avg_daily_hours': time_insights.get('avg_daily_hours', 0),
                'active_trackers': tracker_insights.get('unique_trackers', 0),
                'tracker_entries': tracker_insights.get('total_entries', 0)
            }

            df = pd.DataFrame([summary_row])
            df.to_csv(output, index=False)
        else:
            console.print(f"[red]❌ Unsupported format: {format}[/red]")
            return

        console.print(f"[green]✅ Analytics exported to: {output}[/green]")

    except Exception as e:
        console.print(f"[red]❌ Export failed: {e}[/red]")


# Legacy commands for backwards compatibility
@app.command("summary-trackers")
def summary_trackers(since_days: int = 7):
    """📊 Legacy tracker summary (use 'llog report trackers' instead)."""
    console.print(
        "[yellow]⚠️ This command is deprecated. Use 'llog report trackers' instead.[/yellow]")
    tracker_report(days=since_days)


@app.command("summary-time")
def summary_time(since_days: int = 7):
    """⏱️ Legacy time summary (use 'llog report time' instead)."""
    console.print(
        "[yellow]⚠️ This command is deprecated. Use 'llog report time' instead.[/yellow]")
    time_report(days=since_days)


@app.command("daily-tracker")
def daily_tracker(metric_name: str, since_days: int = 7):
    """📊 Legacy daily tracker (use 'llog report trackers --tracker' instead)."""
    console.print(
        "[yellow]⚠️ This command is deprecated. Use 'llog report trackers --tracker' instead.[/yellow]")
    tracker_report(days=since_days, tracker=metric_name)


def print_dataframe(df):
    if df.empty:
        print("[yellow]⚠️ No data found.[/yellow]")
        return
    table = Table(show_header=True, header_style="bold magenta")
    for col in df.columns:
        table.add_column(col)
    for _, row in df.iterrows():
        table.add_row(*[str(val) for val in row])
    console = Console()
    console.print(table)


def _report_range(tracker, goal, details, df):
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    latest_value = df['value'].iloc[-1]
    min_val = details["min_amount"]
    max_val = details["max_amount"]
    mode = details.get("mode", "goal")

    if mode == "goal":
        completed = bool(min_val <= latest_value <= max_val)
        status = "✓ In range" if completed else "✗ Out of range"
    else:
        completed = False
        status = f"Scale entry logged: {latest_value} (range {min_val}-{max_val})"

    return {
        "report_type": ReportType.RANGE_MEASUREMENT.value,
        "completed": completed,
        "metrics": {
            "latest": latest_value,
            "min": min_val,
            "max": max_val
        },
        "display_format": {
            "primary": f"{latest_value} ({min_val}-{max_val})",
            "secondary": "",
            "tertiary": ""
        },
        "status": status
    }


def _report_sum(tracker, goal, details, df):
    total = df['value'].sum()
    target = details['amount']

    pct = (total / target) * 100 if target else 0
    completed = bool(total >= target)
    return {
        "report_type": ReportType.SUM_ACCUMULATION.value,
        "completed": completed,
        "metrics": {
            "total": total,
            "target": target,
            "percent": pct
        },
        "display_format": {
            "primary": f"{total:.1f}/{target:.1f}",
            "secondary": f"{pct:.1f}%",
            "tertiary": f"{target-total:.1f} left" if total < target else "🎉 Goal completed!"
        },
        "status": "✓ Goal reached" if total >= target else "⏳ Keep going"
    }


def _report_count(tracker, goal, details, df):
    count = len(df)
    target = details['amount']

    pct = (count / target) * 100 if target else 0

    return {
        "report_type": ReportType.COUNT_FREQUENCY.value,
        "completed": bool(count >= target),
        "metrics": {
            "count": count,
            "target": target,
            "percent": pct
        },
        "display_format": {
            "primary": f"{count}/{target}",
            "secondary": f"{pct:.1f}%",
            "tertiary": f"{target-count} left" if count < target else "🎉 Completed"
        },
        "status": "✓ Goal reached" if count >= target else "⏳ Progressing"
    }


def _report_bool(tracker, goal, df):
    true_count = df['value'].sum()
    total = len(df)

    pct = (true_count / total) * 100 if total else 0

    return {
        "report_type": ReportType.BOOL_COMPLETION.value,
        "completed": bool(pct == 100.0),
        "metrics": {
            "true": true_count,
            "false": total-true_count,
            "percent": pct
        },
        "display_format": {
            "primary": f"{true_count}/{total} days",
            "secondary": f"{pct:.1f}% complete",
            "tertiary": ""
        },
        "status": "✓ All completed" if pct == 100 else "⏳ Partial completion"
    }


def _report_streak(tracker, goal, details, df):
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df['date'] = df['timestamp'].dt.date

    dates = sorted(df['date'])
    today = datetime.today().date()

    streak = 0
    for d in reversed(dates):
        if (today - d).days == streak:
            streak += 1
        else:
            break

    target = details['target_streak']

    return {
        "report_type": ReportType.STREAK_CURRENT.value,
        "completed": bool(streak >= target),
        "metrics": {
            "streak": streak,
            "target": target
        },
        "display_format": {
            "primary": f"{streak} days",
            "secondary": f"Target: {target} days",
            "tertiary": ""
        },
        "status": "🔥 Streak growing!" if streak < target else "🏆 Target Streak Achieved"
    }


def _report_duration(tracker, goal, details, df):
    total_minutes = df['value'].sum()
    target_minutes = details['amount']
    unit = details.get('unit', 'minutes')

    pct = (total_minutes / target_minutes) * 100 if target_minutes else 0

    def format_time(minutes):
        if unit.lower() == "minutes" and minutes >= 60:
            hours = int(minutes // 60)
            mins = int(minutes % 60)
            return f"{hours}h {mins}m"
        else:
            return f"{minutes:.0f} {unit}"

    return {
        "report_type": ReportType.DURATION_TIME.value,
        "completed": bool(total_minutes >= target_minutes),
        "metrics": {
            "total_minutes": total_minutes,
            "target_minutes": target_minutes,
            "percent": pct
        },
        "display_format": {
            "primary": f"{format_time(total_minutes)} / {format_time(target_minutes)}",
            "secondary": f"{pct:.1f}% complete",
            "tertiary": f"{target_minutes-total_minutes:.0f} minutes remaining" if total_minutes < target_minutes else "🎉 Goal done!"
        },
        "status": "✓ Goal reached!" if total_minutes >= target_minutes else "⏳ Keep going"
    }


def _report_milestone(tracker, goal, details, df):
    current = df['value'].sum()
    target = details['target']
    unit = details.get('unit', '')

    # ------------------------- NEW LOGIC --------------------------
    # A milestone is complete only if
    #   • total progress ≥ target, and
    #   • the last reading repeats the previous one (stable)
    stable = len(df) >= 2 and df['value'].iloc[-1] == df['value'].iloc[-2]
    completed = bool(current >= target and stable)
    # --------------------------------------------------------------

    pct = (current / target) * 100 if target else 0
    remaining = max(0, target - current)

    return {
        "report_type": ReportType.MILESTONE_PROGRESS.value,
        "completed": completed,
        "metrics": {
            "current": current,
            "target": target,
            "percent": pct,
        },
        "display_format": {
            "primary": f"{current:.1f}/{target:.1f} {unit}",
            "secondary": f"{pct:.1f}% complete",
            "tertiary": f"{remaining:.1f} {unit} remaining" if remaining else "Completed!",
        },
        "status": "🏆 Milestone achieved!" if completed else "⏳ Progressing toward milestone",
    }


def _report_percentage(tracker, goal, details, df):
    latest_pct = df['value'].iloc[-1]
    target_pct = details['target_percentage']

    completed = bool(latest_pct >= target_pct
                     )
    return {
        "report_type": ReportType.PERCENTAGE_PROGRESS.value,
        "completed": completed,
        "metrics": {
            "current_percentage": latest_pct,
            "target_percentage": target_pct
        },
        "display_format": {
            "primary": f"{latest_pct:.1f}% / {target_pct}%",
            "secondary": f"{(latest_pct/target_pct)*100:.1f}% of goal",
            "tertiary": "✓ Reached" if completed else f"{target_pct-latest_pct:.1f}% remaining"
        },
        "status": "🏆 Target percentage reached!" if completed else "⏳ Keep progressing"
    }


def _report_reduction(tracker, goal, details, df):
    latest = df['value'].iloc[-1]
    target = details['amount']
    unit = details.get('unit', '')

    improvement = "✓ Below target" if latest <= target else f"✗ Above target ({latest-target:+.1f})"

    return {
        "report_type": ReportType.REDUCTION_TREND.value,
        "completed": bool(latest <= target),
        "metrics": {
            "latest": latest,
            "target": target
        },
        "display_format": {
            "primary": f"{latest} {unit}",
            "secondary": f"Target: {target} {unit}",
            "tertiary": improvement
        },
        "status": improvement
    }


def _report_replacement(tracker, goal, details, df):
    new_behavior_count = df[df['value'] > 0].shape[0]
    old_behavior_count = df[df['value'] < 0].shape[0]
    total = new_behavior_count + old_behavior_count

    ratio = (new_behavior_count / total) * 100 if total else 0

    original = details.get('old_behavior', 'old habit')
    new = details.get('new_behavior', 'new habit')

    return {
        "report_type": ReportType.REPLACEMENT_RATIO.value,
        "completed": bool(ratio >= 75),
        "metrics": {
            "new_behavior": new_behavior_count,
            "old_behavior": old_behavior_count,
            "replacement_ratio": ratio
        },
        "display_format": {
            "primary": f"{new_behavior_count}:{old_behavior_count} replacements",
            "secondary": f"{ratio:.1f}% new behavior",
            "tertiary": f"Replacing '{original}' ➡ '{new}'"
        },
        "status": "✅ Strong replacement habit!" if ratio >= 75 else "🔄 Still replacing..."
    }

# --- Clinical/AI Insights Command ---


def setup_ai_credentials():
    cfg_path = "config.toml"
    try:
        cfg = toml.load(cfg_path)
    except Exception:
        cfg = {}

    ai = cfg.get("ai", {})
    changed = False

    if not ai.get("chatgpt_api_key"):
        ai["chatgpt_api_key"] = input(
            "Enter your ChatGPT/OpenAI API key (or leave blank): ").strip()
        changed = True
    if not ai.get("gemini_api_key"):
        ai["gemini_api_key"] = input(
            "Enter your Gemini API key (or leave blank): ").strip()
        changed = True
    if not ai.get("preferred_ai_model"):
        model = input(
            "Preferred AI model for insights? (chatgpt/gemini): ").strip().lower()
        if model in ("chatgpt", "gemini"):
            ai["preferred_ai_model"] = model
            changed = True

    if changed:
        cfg["ai"] = ai
        with open(cfg_path, "w") as f:
            toml.dump(cfg, f)
        print("AI configuration updated.")
    else:
        print("AI configuration unchanged.")


def gather_all_data():
    return {
        "tasks": task_repository.get_all_tasks(),
        "trackers": track_repository.get_all_trackers(),
        "tracker_entries": track_repository.get_all_entries(),
        "goals": [g for t in track_repository.get_all_trackers() for g in track_repository.get_goals_for_tracker(t.id)],
        "time_logs": time_repository.get_all_time_logs(),
        "environment": environment_repository.get_all_environmental_data() if hasattr(environment_repository, "get_all_environmental_data") else [],
    }


def format_insight_prompt(user_data):
    prompt = (
        "You are a clinical behavioral analyst AI. Analyze the user's tracked data and deliver meaningful, valuable, and actionable insights."
        "\n\nDATA TO ANALYZE (JSON):\n"
        f"{json.dumps(user_data, indent=2)}"
        "\n\nInstructions: "
        "1. Identify trends, problems, and strengths in productivity, habits, and well-being.\n"
        "2. Surface any patterns between time use, tasks, and environment.\n"
        "3. Highlight unusual behaviors, suggest possible explanations, and offer practical advice for improvement.\n"
        "4. Use bullet points and concise explanations, suitable for a self-tracking user.\n"
        "Do NOT repeat the raw data."
    )
    return prompt


@app.command("clinical-insights")
def show_clinical_insights(
    use_ai: bool = True,
    model: str = None
):
    """
    Run clinical/behavioral insight engine (optionally via AI, with model selection).
    """

    # Get model/key from config (unless overridden)
    config_model, api_key = cf.get_ai_credentials()
    model = model or config_model

    if use_ai and (not api_key or not model):
        print(
            "[red]AI API key or model missing. Set them in config.toml under [ai].[/red]")
        use_ai = False

    result = generate_clinical_insights(
        use_ai=use_ai and bool(api_key),
        ai_key=api_key,
        ai_model=model
    )

    print("\n[bold blue]Clinical/Behavioral Insight Report[/bold blue]")
    if isinstance(result, dict):
        for section, value in result.items():
            print(f"[bold]{section}[/bold]:\n{value}\n")
    else:
        print(result)
