# lifelog/utils/insight_engine.py
'''
Lifelog Insight Engine Module
This module provides functionality to analyze user data and generate insights based on correlations between different metrics.
It includes functions to load metric and time data, compute daily averages, and generate insights based on correlation scores.
It is designed to help users identify patterns and relationships in their data, providing valuable feedback for self-improvement and habit tracking.
'''

import json
import statistics
from collections import defaultdict
from datetime import datetime
from typing import List, Dict, Any
from scipy.stats import pearsonr, spearmanr
import lifelog.config.config_manager as cf
from lifelog.utils.db import track_repository, time_repository

MIN_OVERLAP_DAYS = 7


def load_tracker_data():
    """Fetch all tracker data from SQL."""
    trackers = track_repository.get_all_trackers_with_entries()
    combined = []
    for t in trackers:
        for e in t.get("entries", []):
            combined.append({
                "tracker": t.title,
                "timestamp": e["timestamp"],
                "value": e["value"]
            })
    return combined


def load_time_data():
    """Fetch all time logs as synthetic tracker data."""
    logs = time_repository.get_all_time_logs()
    combined = []
    for l in logs:
        if l["duration_minutes"]:
            combined.append({
                "tracker": f"Time: {l.title}",
                "timestamp": l.start,
                "value": l["duration_minutes"]
            })
    return combined


def daily_averages(entries: List[Dict[str, Any]]) -> Dict[str, Dict[str, float]]:
    daily = defaultdict(lambda: defaultdict(list))
    for e in entries:
        try:
            ts = datetime.fromisoformat(e["timestamp"])
            day = ts.date().isoformat()
            daily[day][e["tracker"]].append(float(e["value"]))
        except Exception:
            continue

    result = defaultdict(dict)
    for day, metrics in daily.items():
        for metric, values in metrics.items():
            result[metric][day] = statistics.mean(values)
    return result


def compute_correlation(x: List[float], y: List[float]) -> Dict[str, float]:
    if len(x) < 2 or len(x) != len(y):
        return {"pearson": 0.0, "spearman": 0.0}
    try:
        return {
            "pearson": round(pearsonr(x, y)[0], 3),
            "spearman": round(spearmanr(x, y)[0], 3),
        }
    except Exception:
        return {"pearson": 0.0, "spearman": 0.0}


def generate_insights():
    entries = load_tracker_data() + load_time_data()
    metrics_data = daily_averages(entries)
    metric_names = list(metrics_data.keys())
    insights = []

    for i in range(len(metric_names)):
        for j in range(i + 1, len(metric_names)):
            m1 = metric_names[i]
            m2 = metric_names[j]

            days = set(metrics_data[m1].keys()) & set(metrics_data[m2].keys())
            if len(days) < MIN_OVERLAP_DAYS:
                continue

            x = [metrics_data[m1][d] for d in sorted(days)]
            y = [metrics_data[m2][d] for d in sorted(days)]
            scores = compute_correlation(x, y)

            if abs(scores["pearson"]) > 0.4 or abs(scores["spearman"]) > 0.4:
                trend = "positive" if scores["pearson"] > 0 else "negative"
                insights.append(
                    {
                        "metrics": (m1, m2),
                        "correlation": scores,
                        "trend": trend,
                        "strength": abs(scores["pearson"]),
                        "note": f"When {m1} is higher, {m2} tends to be {trend}."
                    }
                )

    insights.sort(key=lambda i: i["strength"], reverse=True)
    return insights[:10]


if __name__ == "__main__":
    print("🔍 Analyzing your lifelog for meaningful patterns...")
    insights = generate_insights()
    print("\n✨ Top Correlated Patterns Found:")
    for i, insight in enumerate(insights, 1):
        print(
            f"{i}. {insight['note']} (Pearson: {insight['correlation']['pearson']})")
