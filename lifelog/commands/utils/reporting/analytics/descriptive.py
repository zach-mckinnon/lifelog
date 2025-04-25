from datetime import datetime, timedelta
import statistics, json, csv
from rich.console import Console
from lifelog.commands.utils.reporting.insight_engine import load_metric_data, daily_averages
from lifelog.config.config_manager import get_time_file
from lifelog.commands.utils.reporting.analytics.report_utils import render_radar_chart
console = Console()

def report_descriptive(since: str = "30d", export: str = None):
    """
    📊 Descriptive analytics: overview of tracker stats, time usage, and tasks.
    """
    cutoff = _parse_since(since)
    console.print(f"[bold]Descriptive Analytics:[/] since {cutoff.date().isoformat()}\n")

    # 1. Tracker statistics (mean, median, stdev)
    entries = load_metric_data()
    tracker_daily = daily_averages(entries)  # {tracker: {date: value}}
    stats: dict[str, dict[str, float]] = {}
    for tracker, day_map in tracker_daily.items():
        values = [v for d, v in day_map.items() if datetime.fromisoformat(d) >= cutoff]
        if not values:
            continue
        stats[tracker] = {
            "mean": round(statistics.mean(values), 2),
            "median": round(statistics.median(values), 2),
            "stdev": round(statistics.stdev(values), 2) if len(values) > 1 else 0.0,
        }
    console.print("[blue]Tracker Statistics (Mean):[/blue]")
    render_radar_chart({k: v["mean"] for k, v in stats.items()})

    # 2. Time usage stats
    tf = get_time_file()
    time_data = json.load(open(tf, 'r')).get('history', [])
    filtered = [h for h in time_data if datetime.fromisoformat(h['start']) >= cutoff]
    total_time = sum(rec.get('duration_minutes', 0) for rec in filtered)
    days = (datetime.now().date() - cutoff.date()).days + 1
    avg_time = round(total_time / days, 2) if days > 0 else 0.0
    console.print(f"\n[blue]Time Usage:[/] total {total_time} min — avg/day {avg_time} min")

    # 3. Task summary
    console.print("\n[blue]Task Summary:[/blue]")
    
    # summary_tasks(since, None)

    # 4. Export if requested
    if export:
        _export(stats, total_time, avg_time, export)


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
        return now - timedelta(days=30 * amt)
    return now - timedelta(days=amt)


def _export(stats: dict, total_time: float, avg_time: float, filepath: str):
    ext = filepath.split('.')[-1].lower()
    out = {
        'tracker_stats': stats,
        'total_time_min': total_time,
        'avg_time_per_day_min': avg_time,
    }
    if ext == 'json':
        with open(filepath, 'w') as f:
            json.dump(out, f, indent=2)
    elif ext == 'csv':
        with open(filepath, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['category', 'stat', 'value'])
            for tr, s in stats.items():
                for stat, val in s.items():
                    writer.writerow([tr, stat, val])
            writer.writerow(['time', 'total', total_time])
            writer.writerow(['time', 'avg_per_day', avg_time])
    console.print(f"[green]Exported descriptive report to {filepath}[/green]")